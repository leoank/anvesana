# ADR-0009: Take the keyboard RGB protocol from the vendor's code, and never write the controller's flash

Status: accepted
Date: 2026-10-30

## Context
The keyboard lighting is a separate USB HID controller (`1462:1609`, "MysticLight
MS-1609"). It has no Linux driver, and its command bytes are not documented. Two capture
routes failed or were ruled out:
- **ETW tracing (USBXHCI / UCX / USBHUB3), with `PartialDataBusTrace` and with
  `FullDataBusTrace`.** It logged the setup packets but not the payloads of HID control
  transfers.
- **USBPcap.** A kernel capture-driver install, and there may be no ARM64 build; not tried.

MSI Center's `API_MysticLight.dll` is a .NET assembly. Its enums carry the command
constants in metadata, and its IL shows how each 64-byte report is built. The protocol
includes save-to-flash (`02 a0`), which writes the controller's MCU.

## Decision
The protocol was read statically from the assembly (`dnfile` for metadata, a minimal CIL
disassembler for `Class_NB`), without running or modifying MSI's code. It was then checked
on the hardware with the user watching:
- steady colours;
- the 4 zones, left to right;
- Breath and Color Cycle;
- Wave, which looked right but was hard to judge.

`scripts/msi-mystic-light.py` drives the controller and refuses to send `02 a0`.
Backlight on/off stays with the keyboard's Fn + F8.

## Consequences
- A Linux userspace tool can drive the lighting over hidraw with the documented bytes; no
  kernel driver is needed.
- Changes are temporary: they last until MSI Center re-applies its profile or the machine
  reboots, and nothing persists across boots without the flash write.
- The layout rests on one firmware version of the controller; a new MSI Center or
  controller firmware may change it.
