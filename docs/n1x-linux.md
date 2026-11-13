# Linux on N1X: what it takes (bbaum-pc-7)

MSI Prestige N16 Flip AI+, NVIDIA RTX Spark N1X (MediaTek MT8901 SoC + Blackwell GPU). Status as
of 2026-11-11 on NixOS 26.05 (`nixosModules.n1x`, desktop parts in `nix/desktop-live.nix`).
Details: [bring-up log](n1x-bringup-log.md), [project page](../notes/README.md) (Lessons, Open
questions), experiments in `notes/experiments/`, daily logs in `notes/log/`, raw boot logs on the
SPARKDATA drive under `bootlogs/bbaum-pc-7/`.

## Boot and kernel
- Kernel: NVIDIA's Ubuntu `linux-nvidia-7.0` 7.0.0-1022 with its config (`nix/kernel.nix`), plus
  patches 0001 (ACPI override in one EFI descriptor), 0002 (EINTs without a GPIO), 0003 (MSI EC
  FF-A service), 0004 (hid-sensor power-on sleep).
- The firmware hides SSPM (NVDA8400) and four other devices from `_OSI("Windows 2022")`; without
  SSPM the USB and I2C controllers do not probe. Boot with `acpi_osi="!Windows 2022"` or the SSPM
  DSDT override (vendor tables, not in git; never through Ventoy). Same results either way
  ([[EXP-20261104-ssfy1p]]).
- USB storage enumerates late (after power_wrap): mount data drives with `x-systemd.automount`.
- GPU memory carve-out is firmware-fixed: 96 GB reserved leaves Linux 30 GB; 4 GB leaves 120 GiB
  ([[EXP-20261104-ssfv1c]]).

## Working
- GPU and display: nvidia open driver, nvidia-drm modeset, VA-API (nvidia-vaapi-driver). eDP OLED
  3840x2400 at 60/120 Hz with VRR; `n1x-display-power` picks 120 Hz on AC, 60 Hz on battery. Do
  not use `gdctl --persistent` (GNOME asks to keep the settings every time).
- CPU: `cppc_cpufreq` in autonomous mode (`n1x-cppc-init`); tuned-ppd gives power-saver /
  balanced / performance through the energy-performance preference.
- Suspend: s2idle, ~1 s user space + 2.2-3.1 s kernel per cycle (slowest: RT1320 amps 0.5 s each
  on resume, GPU 0.4 s, NVMe 0.3 s). logind `HoldoffTimeoutSec=5s`. Nothing slow in the
  pre-suspend path.
- Keyboard light off in standby: the firmware's LPS0 `_DSM` calls (`n1x-lps0`, Linux makes them
  only on x86) reach MSI's EC over FF-A service 78b04d80, which NVIDIA's `nvidia_ffa_ec` does not
  list: patch 0003 + `nvidia_ffa_ec.oem_msi_ec=1`.
- Audio: SoundWire RT712 + two RT1320 amps with NVIDIA's UCM. Optional "Speakers (DSP)"
  filter-chain; it holds the speaker sink at 100 % while selected and restarts when a resume
  re-creates the sink (SoundWire bus clash).
- Input: keyboard (Fn + F8 backlight via EC), touchpad, ELAN9024 touchscreen + pen (needs the
  libwacom entry `i2c|04f3|4516`). Pen pressure feel: `n1x-pen` (GNOME `pressure-range` /
  `pressure-curve`).
- Wi-Fi MT7925 (WPA2/WPA3, 802.1X), Bluetooth, cameras enumerate.
- Sensor hub (accelerometer x2, gyro, ambient light, two custom/hinge sensors): see below.

## Sensor hub
- `\_SB.SENH` (MSFW1111, HID over SPI on SPI3) is served by the SoC's sensor coprocessor SCP0
  (Cortex-M4, MediaTek FreeRTOS firmware, already running at boot). It needs nothing from
  Windows' nvSCP.sys ([[RUN-20261110-rgc7bg]], [[RUN-20261110-rs3p36]]).
- Out-of-tree spi-hid v4 (`nix/spi-hid/`, see its README) with fixes, each marked `anvesana`:
  interrupt is EINT 190, which has no GPIO (patch 0002 + `_CRS` lookup); `_RST` was never
  evaluated (`device_reset()` on the acpi_device) ([[RUN-20261110-sd3esk]]); the 2972-byte report
  descriptor exceeded the input-size check ([[RUN-20261110-t3crtm]]); GET_REPORT on input reports
  is sent as GET_INPUT_REPORT; remove the HID device before disabling the IRQ; an unanswered
  GET_INPUT_REPORT no longer resets the hub.
- The hub never answers GET_INPUT_REPORT, so `in_accel_*_raw` reads fail after ~6 s; read the
  sensors through the IIO buffer (as iio-sensor-proxy does) ([[RUN-20261113-0c43e2]]).
- A powered-off sensor reports its interval as 0xffffffff; stock hid-sensor-trigger turned that
  into a ~49.7-day sleep on every power-on (the "hang in rpm_resume"): kernel patch 0004
  ([[RUN-20261113-0c42vk]]).
- The accelerometers report only on a 0.02 g change, so on a desk iio-sensor-proxy got no first
  sample; a udev rule sets their hysteresis to 0 (`nixosModules.n1x`).
- Works through iio-sensor-proxy (streaming) ([[RUN-20261111-0sdjbf]]).

## Open
- Patch 0004, the hysteresis rule and the spi-hid change are not booted yet. `n1x-sensors` reads
  `in_accel_*_raw`, which this hub cannot answer; it needs to read the IIO buffer instead. The
  custom sensors expose no input fields.
- Auto-rotate: GNOME rotates only in touch mode, which needs a SW_TABLET_MODE switch; none exists.
  Needs a hinge-angle (or two-accelerometer) to tablet-mode bridge.
- Pen strokes skip and need force (likely libinput's tip threshold; `sudo n1x-pen record` to
  check).
- `nvidia_drm vblank=1` stalls GNOME (kept as a boot entry to retest).
- After resume mutter restores fixed 120 Hz; `n1x-display-power` switches again ~3 s later.
- Not tested yet: external displays, camera capture, microphones.

## Windows side (dual boot)
- BitLocker is TPM+PIN: suspend it and keep the recovery key off the machine before changing
  Secure Boot or boot order (ADR-0016). Restore the GPU reservation when done.
