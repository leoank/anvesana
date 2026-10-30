# N1X Linux bring-up log: bbaum-pc-7 (MSI Prestige N16 Flip AI+ C1XMT)

A running record of what we know about this machine's hardware and its Windows drivers, how we found it,
and what did and didn't work. Newest entries go in the [log](#log) at the bottom; the sections above
it are kept current. Data comes from `bench inventory` snapshots (`src/anvesana/inventory/`) unless a
section says otherwise.

| | |
|---|---|
| Machine | MSI Prestige N16 Flip AI+ C1XMT (board MS-2621), convertible, 16" OLED touch, MSI Nano Pen |
| SoC | NVIDIA RTX Spark N1X: 10x Cortex-X925 + 10x Cortex-A725, Blackwell GPU (sm_121, 6,144 cores), NPU |
| Firmware | Insyde BIOS G2621NMS.10B (2026-09-30, ESRT "G-2621 SBIOS Ver.108"); EC firmware 2621EMS1.109 |
| OS | Windows 11 on ARM 10.0.28000; no Linux boot yet |
| Snapshot used | `bbaum-pc-7_2026-10-30_163444_windows` (unprivileged), store at `%TEMP%\anv-store` on the machine |

Confidence markers: **[verified]** read from the hardware, firmware or installed software on this machine;
**[inferred]** a reasonable reading of verified data that hasn't been tested; **[unverified]** from
memory or outside sources, to be checked.

---

## 1. SoC and platform

### CPU [verified]
| Core | MIDR | Rev | CPUs | Max MHz (Windows) |
|---|---|---|---|---|
| Cortex-A725 | `0x410fd871` | r0p1 | 0-4, 10-14 | 2805 |
| Cortex-X925 | `0x410fd851` | r0p1 | 5-9, 15-19 | 2990 |

Per-core ID_AA64* registers are in the snapshot (`cpu.cores[].registers`). ACPI: 20 `ACPI0007`
processors under `\_SB.SYSM.PKG0.CLU{0,1}.CPU{0..9}`, 4 `ACPI0010` containers; topology also in PPTT.

### ACPI tables [verified]
19 tables, all readable without admin: APIC, BGRT, CSRT, DBG2, DSDT (297 KB, `NVDA ANGUS`), FACP, FFT_,
FPDT, GTDT, IORT (**`MEDTEK MTKSGI`**, i.e. MediaTek-authored), MCFG, PPTT, SDEV, SPCR, TPM2, UEFI and
3 SSDTs (`NVDA ANGUS`, `NVIDIA Tpm2Tabl`, `NVDA RotSsdt`). MSDM is skipped deliberately (Windows key).
Disassemble with `iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat` from the snapshot folder.

### NVIDIA SoC blocks [verified]
32 ACPI devices of 19 types, all driven on Windows:

| HID | Count | ACPI path(s) | Windows driver | Notes |
|---|---|---|---|---|
| NVDA0200 | 7 | `\_SB.I2C0`..`I2C6` | nvi2c 2.9.0.0 | I2C1: touch screen, I2C2: keyboard, I2C3: touchpad |
| NVDA0210 | 3 | `\_SB.SPI0`, `SPI2`, `SPI3` | nvspi 2.6.0.0 | |
| NVDA9221 | 1 | `\_SB.GIO0` | nvgpio 2.9.0.0 | |
| NVDA8000 / 8001 | 5 + 1 | `\_SB.USB0`..`USB5` | inbox USBXHCI + **nvxhcifilter** lower filter 2.10.0.0 | the filter suggests controller quirks Linux xHCI will need |
| NVDA8100 | 2 | `\_SB.UBF0`, `UBF1` | Usb4HostRouter (inbox) | |
| NVDA9100 | 1 | `\_SB.CNT0` | nvSoundWireControllerDrv 2.9.0.0 | Realtek SDCA codec behind it |
| NVDA8301/8302/8303 | 3 | `\_SB.DSP1`..`DSP3` | nvadsp 2.13.0.0 | HiFi5-0, HiFi5-1, HiFi1; load signed firmware (below) |
| NVDA9022 | 1 | `\_SB.ASD0` | nvasd 2.13.0.0 | ACX audio streaming; ships `MT8901ResourceConstraints.xml` (MediaTek) |
| NVDA2014 | 1 | `\_SB.HDA0` | HDAudBus | HDMI/DP audio |
| NVDA200A | 1 | `\_SB.DLA0` | nvlddmkm (GPU driver) | NPU |
| NVDA8200 | 1 | `\_SB.SCP0` | nvSCP 2.17.0.0 | system control processor |
| NVDA6210 | 1 | `\_SB.PEPD` | nvpep 2.11.0.0 | power engine plug-in (Windows PM) |
| NVDA0820 | 1 | `\_SB.NPCF` | nvpcf 32.0.16.1679 | NVIDIA Platform Controllers and Framework: dynamic power limits |
| NVDA8600 / 8601 | 1 + 1 | `\_SB.ROT0`, `ROT1` | nvsrootmbx, PlutonNv | root-of-trust mailbox, Pluton |
| NVDA8810 | 1 | `\_SB.MTEL` | MeTelemetryKMD | MediaTek telemetry |

MMIO ranges and IRQs per device: `bench inventory show --grep NVDA --resources`.

### Firmware Linux will need [verified]
Copied with `bench inventory collect --copy-firmware` into `<store>/bbaum-pc-7/inventory/firmware/`:

| File | Size | From | For |
|---|---|---|---|
| `gsp_ga10x.bin` | 18 MB | GPU driver | GPU System Processor firmware |
| `ucodes_ga10x.bin` | 56 MB | GPU driver | GPU microcode |
| `hifi5_a_cose_sign_image.bin`, `hifi5_b_…`, `hifi1_…` | 1.3 / 0.3 / 0.7 MB | nvadsp | audio DSPs (COSE-signed) |
| `mtkwlan.dat` | 21 MB | mtkwecx | MediaTek MT7925 Wi-Fi 7 |
| `mtkbt_v2.dat` | 4 MB | MTKBTFilter | MediaTek Bluetooth |

Linux will probably use its own linux-firmware builds of GPU/Wi-Fi/BT firmware **[inferred]**; the
DSP images are the ones with no known Linux counterpart.

### Capsule-updatable firmware (ESRT) [verified]
| GUID | Name | Type | Version |
|---|---|---|---|
| `B461B3BD-E62A-4A71-841C-50BA4E500267` | G-2621 SBIOS Ver.108 | system | 0x10b |
| `12B99262-648C-4365-BAFD-EB869FB7EB47` | System Firmware | system | 0x61460032 |
| `3F56BAF1-…`, `A761B3BD-…`, `C861B3BD-…` | Device Firmware | device | 0x0 / 0x1 / 0x1 |

fwupd on Linux reads the same table, so BIOS updates should work through UEFI capsules **[inferred]**.

---

## 2. Vendor platform controls (MSI Center S)

MSI Center S 1.1.2608.1801: a UWP front end (`WindowsApps\…MSICenterS…\MSI Center S\UC_*.dll`)
plus services in `C:\Program Files (x86)\MSI\MSI Center S` (`MSI_Center_S_Server` loads `API_*.dll`,
each serving a named pipe `MCSNPS_<feature>`). Logs are in `C:\Program Files (x86)\MSI\MSI_Center_S\Log`
and `C:\ProgramData\MSI`; settings in `HKLM\SOFTWARE\WOW6432Node\MSI\MSI Center S`.

### Firmware interface: MSI_ACPI over ACPI-WMI [verified]
The DSDT has one `_WDG` with 5 blocks:

| GUID | Kind | Object | Windows class |
|---|---|---|---|
| `ABBC0F6A-8EA1-11D1-00A0-C90629100000` | data | AK | (MSI data block) |
| `ABBC0F6B-8EA1-11D1-00A0-C90629100000` | data | AL | (MSI data block) |
| `ABBC0F6D-8EA1-11D1-00A0-C90629100000` | method | AJ | |
| `ABBC0F6E-8EA1-11D1-00A0-C90629100000` | method | AM | `MSI_ACPI`, the methods below |
| `5B3CC38A-40D9-7245-8AE6-1145B751BE3F` | event | notify 0xC0 | `MSI_Event` **[inferred]** |

`MSI_ACPI` methods: `Get/Set_` EC, BIOS, SMBUS, MasterBattery, SlaveBattery, Temperature, Thermal,
Fan, Device, Power, Debug, AP, Data, Range, PE, `Get_WMI`, `Get_EC2`, plus `_64` variants; all take and
return a 32-byte `Package_32`. MSI Center logs "Get_WMI method returns WMI version = 3.0". Reading the
class needs admin (§5). Linux has an `msi-wmi-platform` driver for this GUID family **[unverified]**:
check its GUID, and whether it builds on arm64.

### Power profiles ("User Scenario") [verified: names; model support pending §5]
Defined in MSI Center's UI (shared by all MSI laptops, so this model may expose only some):
MSI AI Engine / Smart Auto, Extreme Performance, High Performance, Balanced, Silent / ECO-Silent (auto
on unplug), Super Battery, Ambient Silent AI. Performance levels Turbo / High / Medium / Low / Super
Silent. Mechanisms seen in `API_UserScenario.dll`: an EC "Shift mode" register (`Get/SetShiftModeValueInEC`),
Windows power-mode overlays (Best performance / Balanced / Best efficiency), NVIDIA PCF tables
(`NV_PCF_TABLE_ID_*`, CPU PL1 min/max on DC), NVIDIA Whisper Mode, PL1/PL2 keys. Saved state:
`User Scenario\Mode=1, Fan=0, ShiftMode=0, Boost=0, IntelligentPower=2`.

### Modes this model offers, and where they live [verified, admin probe 2026-10-30]
MSI Center offered five User Scenario modes on this machine. Each was selected in turn while
`scripts/msi-admin-probe.ps1` dumped the read-only `MSI_ACPI` getters:

| Mode (MSI Center) | `Get_AP` byte 3 | `Get_AP` byte 5 | Registry `User Scenario` Mode / Boost / ShiftMode |
|---|---|---|---|
| Performance | **`c4`** | `00` | 1 / 0 / 0 |
| Performance Boost | **`c5`** | `00` | 1 / 1 / 5 |
| Balanced | **`c1`** | `00` | 2 / – / 2 |
| ECO-Silent | **`c2`** | **`10`** | 3 / – / 3 |
| AI Engine | **`c1`** | `00` | 5 / – / 2 |

- `Get_AP` byte 3 is the EC "shift mode": `0xC0` flags plus 1 = balanced, 2 = eco, 4 = performance,
  5 = performance boost **[verified mapping]**. This matches the shift-mode values the Linux `msi-ec`
  project documents for x86 MSI ECs (eco `c2`, comfort `c1`, turbo `c4`) **[unverified recall]**.
  AI Engine sets the same EC value as Balanced and adapts on top in software.
- `Get_AP` byte 5 = `0x10` only in ECO-Silent: probably the silent fan / power-saving flag **[inferred]**.
- The Windows power plan stayed "Balanced" throughout. MSI modes do not switch `powercfg` plans
  (overlay not checked by the probe).
- Super Battery, Cooler Boost and Advanced fan were **not offered or not tried** in this run.

Other getters (bytes not yet decoded beyond these readings):

| Getter | Baseline | Reading **[inferred]** |
|---|---|---|
| `Get_Fan` | `01 27 08 49 08 …` | two 16-bit LE fan speeds: 0x0827 = 2087, 0x0849 = 2121 RPM; 0 when fans stop (2 fans) |
| `Get_Temperature` | `01 0d 01 2e 2c 00 00 29 27 …` | bytes 3, 4, 7, 8 = 46, 44, 41, 39 °C sensors; bytes 1–2 a 16-bit value that tracks fan activity |
| `Get_MasterBattery` | `01 09 00 9c 18 78 3c 76 02 e0 … 64 …` | byte 13 = 100 % charge; bytes 23–24 = 3022 → 302.2 K (29 °C); bytes 17–18 signed current (−20 once); 0x189c / 0x18e4 = 6300 / 6372 capacity-like values |
| `Get_Power` | `01 07 00 08 …` | constant across modes |
| `Get_Device` | `01 0a 05 00 00 08 20 …` | constant; likely feature flags |
| `Get_Debug` | `01 00 00 00 22 …` | constant |
| `Get_Thermal`, `Get_Data`, `Get_PE` | zeros (after the status byte) | – |
| `Get_WMI`, `Get_EC`, `Get_EC2` | not read | probe bug: these take no input; fixed in the script, needs a re-run |

For Linux: the shift mode is readable through `MSI_ACPI.Get_AP` (method block `ABBC0F6E`, object
`AM`). The matching setter `Set_AP` presumably writes it, but it was **not called**: no writes are
made until we know the full byte layout.

### Fan profiles [verified: names]
Auto, Advanced (custom speeds), Cooler Boost (full speed; `CoolerBoost_Timer`), up to 4 fans in the UI.
Registry: `GeneralSetting\Fan=2`, `FanReversedSP=0`. One ACPI fan device (`PNP0C0B`, `\_SB.FAN0`) and
10 thermal zones (`\_TZ.*`).

### Other features exposed
Battery Master (charge limit; `BatterMasteSP=1`), USB power in sleep (`USBsup=1`), NPU toggle
(`SpNPU=1`), display 60–120 Hz, OLED Care (pixel shift, dim on idle), Human Presence (camera HID
sensor), AI noise cancellation, LAN manager.

### Keyboard lighting [verified]
- The keyboard itself is I2C HID `0db0:1606` at `\_SB.I2C2.TPD0` (ACPI `MKB0001`): keyboard and consumer
  control only; its only output report is the lock LEDs. **No lighting control.**
- Lighting is a separate internal USB HID, **`1462:1609` "MysticLight MS-1609"**: vendor usage page
  0xFF, 64-byte input/output/feature reports (IDs 1–8). Mystic Light (`API_MysticLight.dll` via
  `MsiHid_ARM64.dll` → `HidD_SetFeature` / `HidD_SetOutputReport`) drives it as a "4 Zone" notebook
  device. Its code names it "APROM", Nuvoton's term for MCU application flash **[inferred: Nuvoton MCU]**.
- Styles in the saved profile: Off, Steady, Breath, ColorCycle; per-zone RGB.
- Registry says `KBBacklightSP=0` (no EC backlight control) and `KBBacklight=2`.
- **USB trace (admin probe 2026-10-30) [verified]:** full-speed device behind a hub (port path 2.1).
  Every lighting change is a burst opened by `SET_IDLE` (device resuming from selective suspend),
  then command/response pairs: `SET_REPORT` feature report **2** (64 bytes; setup `21 09 02 03 00 00 40 00`)
  followed by `GET_REPORT` feature report **1** (64 bytes; `a1 01 01 03 00 00 40 00`). 18 bursts,
  132 pairs for the six lighting steps. **Payload bytes were not captured** (see §4).
- Linux: no kernel driver; a userspace tool can drive it via hidraw (feature reports 2 → 1) once the
  payload format is known.

### Touchpad [verified]
- Synaptics `06cb:d022` on `\_SB.I2C3.TPD3` (ACPI `SYNA1513`), I2C HID, haptic.
- Collections: mouse (legacy), **touch pad** (standard Precision Touchpad: 5 contacts, contact count
  max, pad type, latency mode, THQA certification blob), **device configuration** (input mode, surface
  and button switches), **vendor 0xFF00** with output reports 9/10 and input reports 11/12 (20/61 bytes).
  That matches Synaptics RMI-over-HID; the Synaptics install has `SynRMIHID=1`.
- Windows drivers: Synaptics filter drivers 19.6.74.107 (`oem85.inf`, `oem86.inf`, suite "PUWP", OEM
  "MsiPTP_PUWP Group1") + `SynTPEnh.exe` service.
- "Advanced settings": MSI Center's touchpad page finds the pad by hardware ID (`VEN_SYNA&DEV_1513`) and
  talks to Synaptics' `SynTPEnh` over the named pipe `SYNA_TPEnh_Server` (it also knows ELAN, Hantick and
  MSI ActionTouchpad pipes). Synaptics settings (`HKLM\SOFTWARE\Synaptics\SynTPEnh`): haptic feedback on,
  intensity 50, edge-slide volume (method 2, value 25, haptic 40), brightness slide, mute toggle. MSI's
  own layer (`ActionTouchpadStatus=1`) adds "Enter characters", "Launch apps", "Key combination" gestures.
- **No HID haptics collection (usage page 0x0E)**: haptic tuning goes through Synaptics' vendor
  protocol. Linux: `hid-multitouch` for the PTP collection **[inferred]**; haptic intensity has no Linux
  interface.

### Touch screen and MSI Nano Pen [verified]
- ELAN `04f3:4516` on `\_SB.I2C1.TPL1` (ACPI `ELAN9024`), I2C HID, 9 collections.
- Touch screen: 5 contacts per report, contact count max, THQA blob (feature 68).
- **Pen** (collection 4, report 7): X, Y, tip pressure (16-bit), X/Y tilt, azimuth, tip, barrel,
  secondary barrel, eraser, invert, in range, battery strength (8-bit), scan time, **transducer serial
  number (32-bit)**. The serial points to an active-pen protocol with pen IDs (MPP 2.x or USI)
  **[inferred]**; which one is still open.
- Vendor collections: 0xFF00 (output 33 B; input 65 B), 0xFF0B (input reports up to 7.5 KB, likely raw
  data / firmware update), 0xFF0F, 0xFFF4.
- MSI Pen app (`C:\Program Files (x86)\MSI\MSI Pen`) reads HID via Raw Input. It supports ELAN, EETI,
  EMRight and DEXIN panels, gets pen battery from an ELAN vendor message (`__WM_ELAN_PenBatteryLife__`;
  last value `PenBatteryLift=100`), detects the pen garage (`isGaragePen`), and has a Bluetooth shortcut
  button and "Press to Talk". No paired Bluetooth pen is present right now.
- Retail listings: the pen stores and charges in an internal slot; 360° hinge with laptop / tent /
  tablet / presentation modes.
- Tablet mode: `MSI_Center_S_Server` sets Windows `ConvertibleSlateMode` itself (log: "Set
  ConvertibleSlateMode to 1/0"). Linux needs a `SW_TABLET_MODE` source: sensor hub hinge angle, or an
  EC/WMI event **[inferred]**.

### Other input and sensors [verified]
- `ACPI0011` HID button array at `\_SB.BTNS` (portable device control).
- `MSFW1111` SPI HID sensor hub at `\_SB.SENH` ("HID Sensor Collection V2"), likely accelerometer / hinge
  / ambient light. Collections not readable on Windows (§4).
- Camera `5986:11cc`: FHD webcam, IR camera, and a HID sensor (human presence).
- Goodix fingerprint `27c6:6090` (USB, WinUSB / WUDF).
- Realtek SoundWire SDCA codec (`025d:0712`) exposes a consumer-control HID.

---

## 3. What worked
- Everything in §1–2 was collected **without admin**: PnP properties, driver services and versions,
  MMIO/IRQ resources, driver-store contents, ACPI tables, raw SMBIOS, per-core CPU registers,
  `root\wmi` class definitions (not instances), HID caps, ESRT.
- ACPI tables via `GetSystemFirmwareTable`, with SSDTs from `HKLM\HARDWARE\ACPI\{SSDT,SSD1,SSD2}`.
- HID collections via `hid.dll` with a zero-access handle, including keyboards and digitizers that
  Windows opens exclusively.
- Two CIM queries (`Win32_PnPEntity`, `Win32_PnPSignedDriver`) give most device fields in ~4 s.
- Reading .NET UTF-16 string heaps from MSI Center DLLs gave feature names, mode names and HID/WMI paths.
- MSI Center's logs and registry gave model ID, EC version, current modes and the touchpad hand-off.
- Cross-OS compare logic, tested against a synthetic Linux sysfs: path join, GAP / MISSING verdicts,
  deferred-probe reasons, grouping, ACPI-table identity check.
- Firmware copy is content-addressed: a second collection added nothing.

## 4. What failed or is limited
| What | Why / status |
|---|---|
| `MSI_ACPI` WMI instances and methods | Access denied without admin; read with the elevated probe (§2) |
| Probe: `Get_WMI`, `Get_EC`, `Get_EC2` | script set an input `Data` these methods don't have; fixed, needs a re-run |
| Probe: USB payloads for Mystic Light | ETW `PartialDataBusTrace` logs only the setup packets of HID control transfers; the raw ETL has no report bytes. Script now uses `FullDataBusTrace`; if that also lacks payloads, the fallback is USBPcap (a capture driver install, so your call) |
| Probe: trace → XML step | `logman` names the file `usbtrace_000001.etl`, so the script's `tracerpt` pointed at a missing file; converted by hand, script fixed. `tracerpt` also needs `-lr` to keep all events |
| `Get-WindowsDriver -Online` | needs admin; the driver-store walk covers what we need |
| HID collections of `MSFW1111` sensor hub and camera sensor | not openable on Windows (sensor stack holds them); Linux raw descriptors will show them |
| MSI product pages (`us-store.msi.com`, `www.msi.com`) | HTTP 403 to automated fetches; used retailer listings instead |
| Linux collector on real Linux | no Linux boot of this SoC and no WSL distro; tested only on a synthetic sysfs (symlinks emulated, since this account can't create symlinks; kernel log path untested) |
| Mystic Light report format | not recoverable from strings; needs a USB capture (§5) |
| Which power/fan modes this model supports | UI strings are a superset; needs the WMI read and mode toggling (§5) |
| `NvWmiBrightness` (`603E9613-…`) as an ACPI interface | **wrong earlier assumption**: it is registered by NVIDIA's Windows display driver, not in the ACPI `_WDG`, so Linux's `nvidia-wmi-ec-backlight` does not apply |
| First ACPI table read returned 0 tables | my bug (provider signature byte order); fixed |
| `GetSystemFirmwareTable('ACPI','SSDT')` | returns only the first SSDT; registry mirror used |
| `Get-PnpDeviceProperty -InstanceId <array>` | returned nothing; piping devices works (~30 s for 260 devices) |
| Size-based firmware filter | `nvoptix.bin` (63 MiB) slipped under 64 MiB; NVIDIA user-mode `.bin` files now excluded by name |
| Processor and USB root hub IDs | Windows names them differently from Linux; mapped to `acpi:ACPI0007` and `usb:1d6b:000x` |
| `Win32_PnPEntity` "Unknown" status | means not present (disconnected peripherals); collector now uses present devices only |

## 5. Admin-only steps
Run with `scripts/msi-admin-probe.ps1` from an elevated PowerShell (guided; read-only).

| Step | Status |
|---|---|
| 1. `MSI_ACPI` read-only getters | **done** for 10 of 13 getters; `Get_WMI` / `Get_EC` / `Get_EC2` need a re-run |
| 2. Mode mapping (User Scenario) | **done** for 5 modes (§2); fan modes / Super Battery not covered |
| 3. Mystic Light USB capture | **partial**: report IDs and sequence known; payloads need a re-run with `FullDataBusTrace` (or USBPcap) |

Re-run only what's missing: `scripts\msi-admin-probe.ps1 -SkipModes` (getters + USB trace).

## 6. Open questions
- Pen protocol: MPP 2.x or USI? (pen serial format, ELAN vendor reports)
- What the `5B3CC38A-…` WMI event carries (hotkeys? tablet mode? AC?)
- Which EC fields hold fan mode, Cooler Boost and the battery charge limit (shift mode is answered: `Get_AP` byte 3)
- Does this model offer Super Battery, Cooler Boost or Advanced fan control at all?
- Mystic Light payload layout for feature reports 2 / 1
- Whether `nvxhcifilter` hides an xHCI quirk Linux needs
- Sensor hub contents (hinge angle for tablet mode?)

---

## Log
- **2026-10-30**: Read the codebase; designed and built `bench inventory` (collect / list / show /
  compare) for Windows and Linux; first Windows snapshot; committed `f8b9006` on branch `inventory`.
- **2026-10-30**: Surveyed MSI Center S, input devices, touchpad, pen, lighting; added HID collections,
  ACPI-WMI `_WDG` parsing, ESRT and `--copy-firmware`; committed `6a22a7d`. Started this log.
- **2026-10-30**: First elevated run of `scripts/msi-admin-probe.ps1`: baseline + 5 modes dumped, USB
  trace of 6 lighting changes. Mapped the EC shift mode (`Get_AP` byte 3) and the RGB controller's
  feature-report command/response pattern. Three getters and the USB payloads failed (script bugs /
  trace keyword); script fixed, re-run pending. Raw output kept outside the repo (session scratchpad).
