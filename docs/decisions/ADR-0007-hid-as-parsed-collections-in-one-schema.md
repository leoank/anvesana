# ADR-0007: Record HID devices as parsed top-level collections in one schema for both operating systems

Status: accepted
Date: 2026-10-30

## Context
On the N1X convertible, every input and control device is HID over I2C, SPI or USB:
- the touch screen and pen (ELAN);
- the haptic touchpad (Synaptics);
- the keyboard;
- the button array;
- the sensor hub;
- the RGB controller.

What a Linux driver needs is the report layout. Windows exposes only parsed caps from
`hid.dll`; the raw report descriptor is not available to user mode. Linux exposes the raw
descriptor in sysfs.

Alternatives considered:
- **Raw descriptors only.** Not available on Windows.
- **Windows caps as-is.** Not comparable with Linux.
- **List only the collections' top-level usages.** Loses the detail that answered the
  porting questions: the pen's tilt, azimuth, battery strength and transducer serial; the
  touchpad's RMI-over-HID vendor reports; the RGB controller's 64-byte feature reports.

## Decision
A snapshot's `hid` section lists HID devices grouped under their parent device, with ACPI
path, vendor and product. Each top-level collection records its usage and name and, per
input, output and feature report, its fields: report id, usage page, usages, bits and
count. Windows builds this from `HidP_GetCaps` / `GetButtonCaps` / `GetValueCaps`. Linux
parses `report_descriptor` with a small parser in `inventory/hid.py` (constant padding
fields skipped) and saves the raw descriptor. Common usages have names; vendor pages show
as `vendor 0xff00:0x01`.

## Consequences
- `show --hid` answers "what does this device report" without a HID tool on the machine.
- The Windows view is a reconstruction: report order inside a collection and constant
  fields are lost.
- Collections held exclusively by the Windows sensor stack are missing (ADR-0002).
