# spi-hid: HID over SPI transport (out-of-tree)

The driver from the "Add spi-hid transport driver" series, v4 (Jingyuan Liang, Google, continuing
Jarrett Schultz's Microsoft driver), posted 2026-06-09 and not merged as of 2026-11-08:
<https://patchew.org/linux/20260609-send-upstream-v4-0-b843d5e6ced3@chromium.org/>.

The files here are `drivers/hid/spi-hid/` after `git am` of all 11 patches onto Linux 7.0
(the orig tarball of NV-Kernels 7.0.0-1022), unchanged. The series' two HID-core changes are
left out: one only names the bus "SPI" in a log line, the other adds a `HID_SPI_DEVICE` macro
that this driver does not use; `BUS_SPI` is already in the UAPI headers. `nix/spi-hid.nix`
builds `spi-hid.ko` and `spi-hid-acpi.ko` against the image's kernel.

Why: bbaum-pc-7's sensor hub (accelerometer, ambient light) is `\_SB.SENH`, `MSFW1111` with
`_CID PNP0C51` on `\_SB.SPI3` (48 MHz) with a GPIO interrupt on `\_SB.GIO0` pin 0xBE: the
standard Microsoft HID-over-SPI ACPI binding, which `spi-hid-acpi` matches. Above it,
`hid-sensor-hub` and `hid-sensor-accel-3d` are already in the kernel.

Local change (marked `anvesana` in `spi-hid-acpi.c`): the first laptop boot failed with
`spi_hid_acpi spi-MSFW1111:00: error -EINVAL: Missing IRQ` (2026-11-08). The SPI core resolves an
ACPI `GpioInt` with `acpi_dev_gpio_irq_get()` and turns any error into `spi->irq = 0`, so the
reason is lost. The probe now asks again, logs both values, and uses the IRQ if the second
lookup succeeds.

Result (2026-11-09): `acpi_dev_gpio_irq_get(0)` returns -EINVAL. The `GpioInt` pin, 0xBE (190),
is past the end of the GPIO chip: the MT8901 pinctrl driver has 182 GPIOs (0-181) but 209
external interrupts (`ap_num`). The pins that are both (touchpad 43, touchscreen 31, keyboard 33)
have GPIO number = EINT number, which is how Windows numbers `GpioInt` pins on this SoC; EINT
190 is interrupt-only, with no GPIO behind it. gpiolib cannot describe it, and `mtk-eint`
requests every EINT through its GPIO, so the fix is in the kernel's pinctrl/EINT code (support
for EINTs without a GPIO, and an ACPI `GpioInt` lookup that falls back to the EINT domain), not
in this driver.

Fix being tested (2026-11-09), in two parts:

- Kernel: `nix/patches/0002-pinctrl-mediatek-eint-allow-EINTs-that-have-no-GPIO.patch` lets
  `mtk-eint` hand out an EINT with no GPIO (no pin to lock or mux; both-edge refused, since it is
  emulated by reading the pin). The EINT domain already maps all 209 EINTs: GIO0's `_CRS` has 15
  memory ranges, 11 for pin registers and 4 for EINT blocks, and EINT 181-208 are block 3
  (0x1C54A000). All four blocks share GIO0's one interrupt (GIC 0x233); whether block 3 really
  raises it is what the laptop test shows.
- This driver: when gpiolib fails, `spi_hid_acpi_eint_irq()` reads the first `GpioInt` from
  `_CRS`, finds the controller's IRQ domain by its ACPI node, maps the pin number (= EINT
  number) and sets the trigger from the descriptor (edge, active low: falling).

Result (2026-11-09/10, bbaum-pc-7): both parts work (probe binds IRQ 232, EINT 190, falling
edge; the EINT table puts 190 in block 3, index 9, as `_CRS` does), but the interrupt never
fires (0 counts). The hub is not a separate chip: `SENH._RST` only writes 1 to a register at
0x1AB20008, which belongs to `\_SB.SCP0` (NVDA8200, the SoC's sensor coprocessor), and
NVDA8200 has no Linux driver. On Windows it is `nvSCP.sys` (NVIDIA, 2.19.0.0): a mailbox driver
(`DMF_Mailbox`, an `EnableHtCmd` command, an SRAM recovery dump) with no firmware file of its
own, so the coprocessor is already running and most likely waits for the host to switch the hub
on over that mailbox. Next step for the accelerometer: work out that mailbox protocol (SCP0's
`_CRS` has five memory ranges, among them 0x1AB20000 and 0x1AAA0000/0x1AAB0000, and interrupts
0x2EA-0x2EE and 0x198; which are the mailbox is not known yet), not this driver.

Licence: GPL-2.0 (SPDX headers in each file).
