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

Licence: GPL-2.0 (SPDX headers in each file).
