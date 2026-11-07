# NixOS live image, `default` entry: no USB, no keyboard (2026-11-06)

bbaum-pc-7 (MSI Prestige N16 Flip AI+), ISO `anvesana-rtx-spark-live-94cc22fc.iso` booted from a
Ventoy 1.1.18 stick, entry `- default` (stock ACPI tables), Secure Boot off. Transcribed from a photo
of the console; the photo stays out of git. Kernel lines before 2.16 s had scrolled off.

The boot ended in the initrd's emergency mode. Neither the internal keyboard (I2C2) nor USB
worked, so only a forced power-off left it.

```
         Starting Coldplug All udev Devices...
[  OK  ] Finished Create List of Static Device Nodes.
         Starting Create Static Device Nodes in /dev gracefully...
[  OK  ] Mounted Kernel Configuration File System.
[  OK  ] Finished Create Static Device Nodes in /dev gracefully.
         Starting Create Static Device Nodes in /dev...
[  OK  ] Finished Load Kernel Modules.
         Starting Apply Kernel Variables...
[  OK  ] Finished Create Static Device Nodes in /dev.
[  OK  ] Reached target Preparation for Local File Systems.
[  OK  ] Reached target Local File Systems.
         Starting Rule-based Manager for Device Events and Files...
[  OK  ] Finished Apply Kernel Variables.
[  OK  ] Started Journal Service.
         Starting Create System Files and Directories...
[  OK  ] Started Rule-based Manager for Device Events and Files.
[  OK  ] Finished Create System Files and Directories.
[  OK  ] Finished Coldplug All udev Devices.
[  OK  ] Reached target System Initialization.
[  OK  ] Reached target Basic System.
         Expecting device /dev/tpm0...
[  OK  ] Found device /dev/tpm0.
[  OK  ] Reached target Trusted Platform Module.
[    2.165848] i2c-mt65xx NVDA0200:00: error -ENODEV: pwrap probe failed for \_SB_.I2C0
[    2.174300] i2c-mt65xx NVDA0200:01: error -ENODEV: pwrap probe failed for \_SB_.I2C1
[    2.183771] i2c-mt65xx NVDA0200:02: error -ENODEV: pwrap probe failed for \_SB_.I2C2
[    2.190050] xhci-hcd NVDA8000:00: Not find power wrap config data
[    2.190082] xhci-hcd NVDA8000:00: probe with driver xhci-hcd failed with error -22
[    2.192335] i2c-mt65xx NVDA0200:03: error -ENODEV: pwrap probe failed for \_SB_.I2C3
[    2.195980] xhci-hcd NVDA8000:01: Not find power wrap config data
[    2.196009] xhci-hcd NVDA8000:01: probe with driver xhci-hcd failed with error -22
[    2.197162] i2c-mt65xx NVDA0200:04: error -ENODEV: pwrap probe failed for \_SB_.I2C4
[    2.200007] xhci-hcd NVDA8000:02: Not find power wrap config data
[    2.200025] xhci-hcd NVDA8000:02: probe with driver xhci-hcd failed with error -22
[    2.200535] i2c-mt65xx NVDA0200:05: error -ENODEV: pwrap probe failed for \_SB_.I2C5
[    2.203174] xhci-hcd NVDA8000:03: Not find power wrap config data
[    2.203192] xhci-hcd NVDA8000:03: probe with driver xhci-hcd failed with error -22
[    2.203222] i2c-mt65xx NVDA0200:06: error -ENODEV: pwrap probe failed for \_SB_.I2C6
[    2.206104] xhci-hcd NVDA8001:00: Not find power wrap config data
[    2.206121] xhci-hcd NVDA8001:00: probe with driver xhci-hcd failed with error -22
[    2.206296] xhci-hcd NVDA8000:04: Not find power wrap config data
[    2.206308] xhci-hcd NVDA8000:04: probe with driver xhci-hcd failed with error -22
         Starting Virtual Console Setup...
[  OK  ] Finished Virtual Console Setup.
         Mounting /sysroot...
[  OK  ] Mounted /sysroot.
[  OK  ] Reached target Initrd Root File System.
         Mounting /sysroot/nix/.rw-store...
         Mounting /sysroot/run...
         Starting Mountpoints Configured in the Real Root...
[  OK  ] Mounted /sysroot/nix/.rw-store.
[  OK  ] Mounted /sysroot/run.
         Starting rw-sysroot-nix-store.service...
[  OK  ] Finished rw-sysroot-nix-store.service.
         Starting rw-sysroot-nix-store.service...
[  OK  ] Finished Mountpoints Configured in the Real Root.
[  OK  ] Finished rw-sysroot-nix-store.service.
[ TIME ] Timed out waiting for device /dev/disk/by-label/ANV_SPARK.
[DEPEND] Dependency failed for /sysroot/iso.
[DEPEND] Dependency failed for /sysroot/nix/.ro-store.
[DEPEND] Dependency failed for Initrd File Systems.
[DEPEND] Dependency failed for /sysroot/nix/store.
[DEPEND] Dependency failed for Find NixOS closure.
[  OK  ] Stopped Dispatch Password Requests to Console Directory Watch.
[  OK  ] Stopped target Basic System.
[  OK  ] Stopped target System Initialization.
[  OK  ] Started Emergency Shell.
[  OK  ] Reached target Emergency Mode.
         Starting Create Volatile Files and Directories in the Real Root...
[  OK  ] Finished Create Volatile Files and Directories in the Real Root.
You are in emergency mode. After logging in, type "journalctl -xb" to view
system logs, "systemctl reboot" to reboot, or "exit"
to continue bootup.
Press Enter for system maintenance
(or press Control-D to continue): _
```

## Reading

All seven I2C controllers (NVDA0200, `\_SB.I2C0`..`I2C6`) and all six xHCI controllers (NVDA8000
`USB0`..`USB4`, NVDA8001 `USB5`) fail in the same place. NVIDIA's kernel (Ubuntu linux-nvidia-7.0
1022.23) powers each of them on through the built-in `power_wrap` driver:

1. `power_wrap` binds to `\_SB.PEPD` (NVDA6210) and reads its device table from `PEPD._DSM`
   (UUID 64B66B51, function 1, `DPMT`). There, USB0..5 and the I2C controllers have control type 2,
   SCMI.
2. For an SCMI device, `mtk_pwrap_dev_probe()` sends a probe request with `sspm_ci_set()`. That
   returns `-ENODEV` when the SSPM mailbox was never mapped, and the lookup then returns NULL:
   `pwrap probe failed` (I2C) and `Not find power wrap config data` (xHCI).
3. The mailbox belongs to `\_SB.SSPM` (NVDA8400), whose `_STA` is
   `If (_OSI ("Windows 2022")) Return (Zero)`. Linux answers yes to every Windows `_OSI` string, so
   SSPM is absent and `sspm_ci` never probes.

With no USB host, the initrd never sees the boot stick (`ANV_SPARK`). Fix: expose SSPM, either with
`acpi_osi="!Windows 2022"` (the `osi` entry, which exposes all five hidden devices) or with the
DSDT override from `scripts/acpi-hidden-devices.py --expose SSPM` (the `sspm` entry, which exposes
SSPM only). Both are in ISO `0f0f6f14`.

## Second attempt: ISO `0f0f6f14`, `sspm` and `osi` entries (2026-11-06, 23:49 and 23:57)

Two boots, transcribed from two photos; which photo is which entry was not recorded. Both end the
same way as above (`Timed out waiting for device /dev/disk/by-label/ANV_SPARK`, emergency mode),
and the on-screen diagnostics (last 40 matching dmesg lines) show, per xHCI controller:

```
[    2.211107] xhci-hcd NVDA8000:03: eye swing: val[0]=0x0, val[1]=0x0
[    2.211107] mtk_pwrap_dev_probe: Device found at path \_SB_.USB3
[    2.211107] mtk_pwrap_dev_probe: control type is scmi, payload: 0xd, 0x3, 0x1000000, 0x0, 0x0, 0x0
[    2.211108] mtk_pwrap_dev_probe: scmi ret = -19 for device "\_SB_.USB3"
[    2.211119] xhci-hcd NVDA8000:03: probe with driver xhci-hcd failed with error -22
```

(the same for USB2, USB4 and USB5, with payload dev_id 0x2, 0x4, 0x5). So power_wrap now finds its
device table, but `sspm_ci_set()` still returns `-ENODEV`: the SSPM mailbox is not mapped, i.e. the
`SSPM_CI` driver did not bind to NVDA8400 even with SSPM exposed. The filter cut off the earlier
lines that would say why. ISO `fea43045` prints the kernel command line, SSPM's `_STA` and driver,
and the ACPI override / SSPM / power_wrap probe lines instead.

## Third attempt: ISO `fea43045`, three boots (2026-11-07, 00:24 to 00:34)

Transcribed from three photos the author labelled with the entry used.

### `sspm`, Ventoy normal mode: override not applied

```
cmdline: init=/nix/store/mi7w0lrxzwrq7fwpwivxy3i76xq4k1gp-nixos-system-bbaum-pc-7-26.05.20261102.7dcdd87/init
NVDA8400:00: _STA=0 driver=none
NVDA6210:00: _STA=15 driver=mtk_pwrap
[    0.028529] ACPI: Added _OSI(Module Device)
[    0.028531] ACPI: Added _OSI(Processor Device)
[    0.028532] ACPI: Added _OSI(Processor Aggregator Device)
[    0.038413] ACPI: USB4 _OSC: OS supports USB3+ DisplayPort+ PCIe+ XDomain+
[    0.038415] ACPI: USB4 _OSC: OS controls USB3+ DisplayPort+ PCIe+ XDomain+
[    0.110699] mtk_pwrap NVDA6210:00: device probe for "NVDA6210"
[    0.110704] mtk_pwrap NVDA6210:00: ACPI MEM index 0x0: start = 0x1c8b0000, size = 0x100
[    0.110706] mtk_pwrap NVDA6210:00: ACPI IRQ index 0x0: number = 39
[    0.110707] mtk_pwrap NVDA6210:00: Config dev ctrl info from ACPI data
[    0.111019] mtk_pwrap NVDA6210:00: DPM config from ACPI: revision=0, 75 devices
[    0.111253] mtk_pwrap NVDA6210:00: DPMT: "\_SB_.DSP1" SCMI dev_id=0x19
   ... DSP2 0x1a, DSP3 0x1b, USB0..USB5 0x0..0x5, UBF0..UBF3 0x6..0x9, COM3 0x2a,
       SPI0 0x23, SPI2 0x25, SPI3 0x26, I2C0 0x1e, I2C1 0x1f, I2C2 0x20 ...
[    0.506299] mtk_pwrap_dev_probe: scmi ret = -19 for device "\_SB_.PCI0"
[    0.507350] mtk_pwrap_dev_probe: scmi ret = -19 for device "\_SB_.PCI6"
```

No `Table Upgrade` line and SSPM still `_STA=0`: Ventoy adds its own initramfs to Linux ISOs, and
with it in front, the kernel does not find the uncompressed override cpio that the `sspm` entry's
initrd starts with.

### `sspm`, Ventoy GRUB2 mode: override applied, SSPM bound, USB and keyboard work

```
cmdline:
NVDA8400:00: _STA=15 driver=SSPM_CI
NVDA6210:00: _STA=15 driver=mtk_pwrap
[    0.000000] ACPI: Table override allocation 0x0000000080141000 (299008 bytes) within EFI region 0x0000000080000000-0x000000008018a000
[    0.000000] ACPI: Table Upgrade: override [DSDT-  NVDA-ANGUS   ]
[    0.000000] ACPI: DSDT 0x0000000087031018 Physical table override, new table: 0x0000000080141000
[    0.029820] ACPI: Added _OSI(Module Device)
   ...
[    0.112692] SSPM_CI NVDA8400:00: SSPM_CI_SET IRQ = 39.
[    0.112700] SSPM_CI NVDA8400:00: SSPM_CI_GET IRQ = 40.
[    0.112726] mtk_pwrap NVDA6210:00: device probe for "NVDA6210"
   ... DPM config from ACPI: revision=0, 75 devices (as above)
```

The keyboard worked. The boot still stopped at `Timed out waiting for device
/dev/disk/by-label/ANV_SPARK`: in GRUB2 mode Ventoy does not map the ISO to a device, and the
ISO lives as a file on Ventoy's exFAT partition (the empty `cmdline:` field is a diagnostics bug:
the grep found no `init=` in that command line).

### `osi`, Ventoy normal mode: boots to a shell

`acpi_osi="!Windows 2022"` exposes SSPM without a table override, so Ventoy's initramfs does not
matter. Logged in automatically as `nixos`; `cat /etc/anvesana-boot-entry` gives `osi`.

```
[   14.019210] ucsi_acpi USBC000:00: GET_CURRENT_CAM command failed
$ nvidia-smi
NVIDIA-SMI 615.78.08    KMD Version: 615.78.08    CUDA UMD Version: 13.4
  0  NVIDIA RTX Spark N1X (61...  Off | 0000000F:01:00.0  On | N/A
N/A  40C  P8   1W / N/A | Not Supported | 0%  Default
$ lsblk
loop0        7:0    0   2.8G  1 loop /nix/.ro-store
sda          8:0    1 117.2G  0 disk
└─sda1       8:1    1 117.2G  0 part
sdb          8:16   1  57.3G  0 disk
├─sdb1       8:17   1  57.3G  0 part
│ ├─ventoy   252:0  0     3G  1 dm   /iso
│ └─VentoyPart 252:1 0  57.3G  0 dm
└─sdb2       8:18   1    32M  0 part
nvme0n1    259:0    0   1.9T  0 disk   (5 partitions, not mounted)
$ ls /mnt/sparkdata
ls: cannot access '/mnt/sparkdata': No such file or directory
```

SPARKDATA (`sda1`) was present but not mounted: the `x-systemd.device-timeout=10s` mount ran out
before the late USB enumeration. ISO `e6a2cb99` mounts it on first access instead.
