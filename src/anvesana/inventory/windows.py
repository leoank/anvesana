"""Windows inventory. Everything here works without administrator rights.

  devices   present PnP devices: hardware IDs, ACPI namespace path, parent, function driver
            and filter drivers, INF / version / provider, problem code, MMIO / IRQ resources
  drivers   every kernel driver service with its binary's version resource
  packages  third-party driver-store folders: the INF (copied) and every file it installs
            (listed with size and hash; with a firmware dir, firmware blobs are copied too)
  hid       every HID top-level collection: usage, report sizes, per-report fields (hid.dll caps)
  firmware  ACPI tables (GetSystemFirmwareTable; SSDTs from the HKLM\\HARDWARE\\ACPI mirror,
            since the API returns only the first table of a signature), raw SMBIOS, ACPI-WMI
            blocks (_WDG), UEFI ESRT
  cpu       per-core ID registers (MIDR_EL1, ID_AA64*_EL1) from the processor registry keys
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import shutil
import struct
import subprocess
import winreg
from pathlib import Path

from . import firmware

# One PowerShell pass: two CIM queries carry most fields; the per-device property call
# (the slow part, ~30 s for 250 devices) only fetches what CIM lacks.
_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ents = Get-CimInstance Win32_PnPEntity -Filter 'Present = TRUE'
$signed = @{}
Get-CimInstance Win32_PnPSignedDriver | ForEach-Object { if ($_.DeviceID) { $signed[$_.DeviceID] = $_ } }
$props = @{}
$keys = 'DEVPKEY_Device_Parent', 'DEVPKEY_Device_BiosDeviceName', 'DEVPKEY_Device_LocationPaths',
        'DEVPKEY_Device_UpperFilters', 'DEVPKEY_Device_LowerFilters', 'DEVPKEY_Device_InLocalMachineContainer'
$ents | Get-PnpDeviceProperty -KeyName $keys | ForEach-Object {
    if ($null -ne $_.Data -and $_.Type -ne 'Empty') {
        if (-not $props.ContainsKey($_.InstanceId)) { $props[$_.InstanceId] = @{} }
        $props[$_.InstanceId][$_.KeyName -replace '^DEVPKEY_Device_', ''] = $_.Data
    }
}
$memEnd = @{}
Get-CimInstance Win32_DeviceMemoryAddress | ForEach-Object { $memEnd[[string]$_.StartingAddress] = $_.EndingAddress }
$res = @{}
Get-CimInstance Win32_PnPAllocatedResource | ForEach-Object {
    $id = $_.Dependent.DeviceID; $a = $_.Antecedent
    if (-not $res.ContainsKey($id)) { $res[$id] = @{ mem = @(); irq = @(); io = @(); dma = @() } }
    switch ($a.CimClass.CimClassName) {
        'Win32_DeviceMemoryAddress' { $res[$id].mem += ,@([uint64]$a.StartingAddress, [uint64]$memEnd[[string]$a.StartingAddress]) }
        'Win32_IRQResource'         { $res[$id].irq += [int64]$a.IRQNumber }
        'Win32_PortResource'        { $res[$id].io  += [uint64]$a.StartingAddress }
        'Win32_DMAChannel'          { $res[$id].dma += [int]$a.DMAChannel }
    }
}
$devices = foreach ($e in $ents) {
    $s = $signed[$e.DeviceID]
    @{
        id = $e.DeviceID; name = $e.Name; class = $e.PNPClass; manufacturer = $e.Manufacturer
        service = $e.Service; problem = [int]$e.ConfigManagerErrorCode
        hardware_ids = @($e.HardwareID); compatible_ids = @($e.CompatibleID)
        inf = $s.InfName; driver_version = $s.DriverVersion; driver_provider = $s.DriverProviderName
        driver_date = $(if ($s.DriverDate) { $s.DriverDate.ToString('yyyy-MM-dd') })
        props = $props[$e.DeviceID]; resources = $res[$e.DeviceID]
    }
}
$drivers = foreach ($d in Get-CimInstance Win32_SystemDriver) {
    $v = $null
    if ($d.PathName) { $v = (Get-Item -LiteralPath ($d.PathName -replace '^\\\?\?\\', '')).VersionInfo }
    @{ name = $d.Name; display_name = $d.DisplayName; path = $d.PathName; state = $d.State
       start_mode = $d.StartMode; type = $d.ServiceType
       version = $(if ($v) { $v.FileVersion }); company = $(if ($v) { $v.CompanyName })
       description = $(if ($v) { $v.FileDescription }) }
}
$brightness = @(Get-CimInstance -Namespace root/wmi WmiMonitorBrightness | ForEach-Object {
    @{ instance = $_.InstanceName; current = [int]$_.CurrentBrightness; levels = @($_.Level | ForEach-Object { [int]$_ }) } })
@{ devices = @($devices); drivers = @($drivers); brightness = $brightness } | ConvertTo-Json -Depth 6 -Compress
"""

HASH_LIMIT = 96 << 20
# Firmware images the hardware loads (DSP, GSP, Wi-Fi/BT, microcode).
FIRMWARE_SUFFIXES = {".bin", ".dat", ".fw", ".img", ".elf", ".hex", ".mbn", ".ucode", ".sig"}
FIRMWARE_LIMIT = 64 << 20
# NVIDIA display-driver .bin files that are user-mode data, not firmware: CUDA fatbins,
# OptiX kernels, the driver settings database.
NOT_FIRMWARE = {"nvcubins.bin", "nvoptix.bin", "nvdrsdb.bin"}


def is_firmware(name: str, size: int) -> bool:
    return (Path(name).suffix.lower() in FIRMWARE_SUFFIXES and size <= FIRMWARE_LIMIT
            and name.lower() not in NOT_FIRMWARE)

PROBLEMS = {1: "not configured", 3: "driver may be corrupted", 10: "cannot start", 12: "resource conflict",
            18: "reinstall drivers", 19: "registry problem", 21: "being removed", 22: "disabled",
            24: "not present or not working", 28: "no driver installed", 31: "not working",
            32: "driver disabled", 37: "driver failed to initialize", 39: "driver missing or corrupt",
            43: "stopped after reporting problems", 45: "not connected", 52: "unsigned driver"}


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def collect(out_dir: Path, firmware_dir: Path | None = None) -> dict:
    raw = _powershell(_SCRIPT)
    devices = [_device(d) for d in raw.get("devices") or []]
    drivers = sorted(raw.get("drivers") or [], key=lambda d: d["name"].lower())
    notes = []

    tables = _acpi_tables()
    acpi = firmware.save_acpi_tables(tables, out_dir / "acpi") if tables else []
    wmi = firmware.wmi_blocks(tables)
    if not acpi:
        notes.append("ACPI tables not readable")
    smbios = {}
    rsmb = _firmware_table("RSMB", 0)
    if rsmb and len(rsmb) > 8:
        _, major, minor, docrev, length = struct.unpack_from("<BBBBI", rsmb)
        table = rsmb[8:8 + length]
        (out_dir / "smbios.bin").write_bytes(firmware.smbios_dump(table, major, minor, docrev))
        smbios = {"version": f"{major}.{minor}", "file": "smbios.bin", **firmware.smbios_summary(table)}
    else:
        notes.append("SMBIOS not readable")

    return {"devices": devices, "drivers": drivers,
            "packages": _driver_packages(devices, drivers, out_dir, firmware_dir), "hid": _hid_devices(devices),
            "firmware": {"acpi_tables": acpi, "smbios": smbios, "wmi": wmi, "esrt": _esrt(devices)},
            "display": _display(devices, raw.get("brightness") or [], out_dir, notes), "power": _power(out_dir),
            "vendor_settings": _vendor_settings(), "cpu": _cpu(), "notes": notes}


def _hid_devices(devices: list[dict]) -> list[dict]:
    """HID collections grouped under the device that carries them (ACPI\\ELAN9024 -> touch
    screen, pen and vendor collections), in the same shape the Linux collector produces."""
    by_id = {d["id"].upper(): d for d in devices}
    out: dict[str, dict] = {}
    for inst, col in sorted(_hid_collections().items()):
        child = by_id.get(inst) or {}
        parent = by_id.get((child.get("parent") or "").upper()) or child
        key = parent.get("id") or inst
        entry = out.setdefault(key, {"device": key, "name": parent.get("name"), "bus": parent.get("bus"),
                                     "acpi_path": parent.get("acpi_path"), "vendor": col["vendor"],
                                     "product": col["product"], "version": col["version"],
                                     "product_string": col["product_string"], "collections": []})
        entry["collections"].append({k: col[k] for k in ("usage_page", "usage", "name", "report_bytes", "reports")}
                                    | {"id": inst})
    return list(out.values())


def _esrt(devices: list[dict]) -> list[dict]:
    r"""HKLM\HARDWARE\UEFI\ESRT: firmware the platform can update by UEFI capsule (fwupd on Linux)."""
    names = {d["id"].split("\\")[1].lower().removeprefix("res_"): d.get("name")
             for d in devices if d["id"].upper().startswith("UEFI\\RES_")}
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\UEFI\ESRT")
    except OSError:
        return out
    for guid in _subkeys(root):
        key = winreg.OpenKey(root, guid)
        values = {winreg.EnumValue(key, i)[0]: winreg.EnumValue(key, i)[1] for i in range(winreg.QueryInfoKey(key)[1])}
        out.append({"guid": guid.strip("{}").upper(), "name": names.get(guid.lower()),
                    "type": {1: "system firmware", 2: "device firmware", 3: "UEFI driver"}.get(values.get("Type"),
                                                                                              values.get("Type")),
                    "version": f"0x{values.get('Version', 0):08x}",
                    "lowest_supported": f"0x{values.get('LowestSupportedVersion', 0):08x}",
                    "last_attempt_status": values.get("LastAttemptStatus")})
    return out


def _powershell(script: str) -> dict:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        raise SystemExit("PowerShell not found; the Windows inventory needs it")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    proc = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", encoded], capture_output=True, timeout=600)
    out = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not out:
        raise SystemExit(f"PowerShell device query failed ({proc.returncode}): "
                         f"{proc.stderr.decode('utf-8', 'replace').strip()[-500:]}")
    return json.loads(out[out.index("{"):])


def _device(d: dict) -> dict:
    """Raw PowerShell record -> the OS-neutral device schema (see snapshot.py)."""
    props = d.get("props") or {}
    res = d.get("resources") or {}
    problem = d.get("problem") or 0
    service = d.get("service") or None
    upper, lower = _list(props.get("UpperFilters")), _list(props.get("LowerFilters"))
    driver = None
    if service or upper or lower:
        driver = {"name": service, "inf": d.get("inf"), "version": d.get("driver_version"),
                  "date": d.get("driver_date"), "provider": d.get("driver_provider"),
                  "upper_filters": upper, "lower_filters": lower}
    return {
        "id": d["id"],
        "name": d.get("name"),
        "bus": d["id"].split("\\", 1)[0].lower(),
        "match_id": match_id(d["id"], _list(d.get("hardware_ids"))),
        "class": d.get("class"),
        "manufacturer": d.get("manufacturer"),
        "hardware_ids": _list(d.get("hardware_ids")),
        "compatible_ids": _list(d.get("compatible_ids")),
        "acpi_path": props.get("BiosDeviceName"),
        "location": _list(props.get("LocationPaths")),
        "parent": props.get("Parent"),
        "internal": props.get("InLocalMachineContainer"),
        "status": "ok" if problem == 0 else "no-driver" if problem == 28 else "problem",
        "problem": f"code {problem}: {PROBLEMS.get(problem, 'see Device Manager')}" if problem else None,
        "driver": driver,
        "resources": {k: [list(r) if isinstance(r, list) else r for r in _list(res.get(k))]
                      for k in ("mem", "irq", "io", "dma") if res.get(k)},
    }


def match_id(instance_id: str, hardware_ids: list[str] = ()) -> str:
    """Instance ID -> the cross-OS identity Linux would report for the same hardware:
    ACPI\\NVDA0200\\0 -> acpi:NVDA0200, PCI\\VEN_10DE&DEV_2E03&... -> pci:10de:2e03,
    USB\\VID_046D&PID_C548&MI_01\\... -> usb:046d:c548:if01."""
    parts = instance_id.split("\\")
    bus, ident = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
    if bus == "acpi":
        # Processors are named by marketing string; ACPI\VEN_ACPI&DEV_0007 carries the _HID.
        for hid in hardware_ids:
            f = dict(x.split("_", 1) for x in hid.split("\\")[-1].split("&") if "_" in x)
            if hid.upper().startswith("ACPI\\VEN_") and "VEN" in f and "DEV" in f:
                return f"acpi:{f['VEN']}{f['DEV']}"
    if bus == "usb" and ident in ("ROOT_HUB20", "ROOT_HUB30"):
        return f"usb:1d6b:000{ident[-2]}"  # Linux root hubs: Linux Foundation 2.0 / 3.0 root hub
    fields = dict(f.split("_", 1) for f in ident.split("&") if "_" in f)
    if bus == "pci" and "VEN" in fields and "DEV" in fields:
        return f"pci:{fields['VEN'].lower()}:{fields['DEV'].lower()}"
    if bus in ("usb", "hid") and "VID" in fields and "PID" in fields:
        mi = f":if{fields['MI'].lower()}" if "MI" in fields else ""
        return f"{bus}:{fields['VID'].lower()}:{fields['PID'].lower()}{mi}"
    return f"{bus}:{ident}"


def _list(v) -> list:
    if v is None:
        return []
    return [x for x in v if x is not None] if isinstance(v, list) else [v]


# ------------------------------------------------------------------ driver packages

def _driver_packages(devices: list[dict], drivers: list[dict], out_dir: Path,
                     firmware_dir: Path | None = None) -> list[dict]:
    """Driver-store folders behind every non-Microsoft driver a device uses: what a Linux port has
    to replace, including firmware the hardware loads at runtime (DSPs, Wi-Fi/BT, ...)."""
    used = {n.lower() for d in devices if d["driver"]
            for n in [d["driver"]["name"], *d["driver"]["upper_filters"], *d["driver"]["lower_filters"]] if n}
    folders = {}
    for drv in drivers:
        path = (drv.get("path") or "").replace("\\??\\", "")
        inbox = (drv.get("company") or "").startswith("Microsoft")
        if drv["name"].lower() in used and not inbox and "\\driverstore\\filerepository\\" in path.lower():
            folder = Path(path).parent
            folders.setdefault(folder, set()).add(drv["name"])
    out = []
    for folder, services in sorted(folders.items()):
        files = []
        try:
            entries = sorted(p for p in folder.rglob("*") if p.is_file())
        except OSError:
            continue
        for p in entries:
            rel = p.relative_to(folder).as_posix()
            size = p.stat().st_size
            # Firmware blobs are small; the GPU driver's multi-GB user-mode DLLs are not worth hashing.
            entry = {"file": rel, "size": size, "sha256": _sha256(p) if size <= HASH_LIMIT else None}
            if p.suffix.lower() == ".inf":
                dest = out_dir / "drivers" / folder.name / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dest)
                entry["copied_to"] = dest.relative_to(out_dir).as_posix()
            elif firmware_dir and is_firmware(p.name, size) and entry["sha256"]:
                # Content-addressed and shared by the machine's snapshots: a blob is stored once
                # until a driver update changes it.
                dest = firmware_dir / f"{entry['sha256'][:16]}_{p.name}"
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, dest)
                entry["copied_to"] = os.path.relpath(dest, out_dir).replace("\\", "/")
            files.append(entry)
        out.append({"package": folder.name, "services": sorted(services), "files": files})
    return out


def _sha256(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ------------------------------------------------------------------ firmware tables

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.EnumSystemFirmwareTables.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
_k32.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]


def _provider(sig: str) -> int:
    return int.from_bytes(sig.encode(), "big")


def _firmware_table(provider: str, table_id: int) -> bytes | None:
    size = _k32.GetSystemFirmwareTable(_provider(provider), table_id, None, 0)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    got = _k32.GetSystemFirmwareTable(_provider(provider), table_id, buf, size)
    return buf.raw[:got] if got else None


def _acpi_tables() -> list[bytes]:
    n = _k32.EnumSystemFirmwareTables(_provider("ACPI"), None, 0)
    buf = ctypes.create_string_buffer(n)
    _k32.EnumSystemFirmwareTables(_provider("ACPI"), buf, n)
    # DSDT is not in the enumeration but can be fetched; SSDTs come from the registry.
    sigs = {buf.raw[i:i + 4] for i in range(0, n, 4)} | {b"DSDT"}
    tables = [t for sig in sorted(sigs - {b"SSDT"})
              if (t := _firmware_table("ACPI", int.from_bytes(sig, "little")))]
    return tables + _registry_ssdts()


def _registry_ssdts() -> list[bytes]:
    r"""HKLM\HARDWARE\ACPI\{SSDT,SSD1,...}\<OEM>\<table id>\<revision> = raw table."""
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\ACPI")
    except OSError:
        return out
    for name in _subkeys(root):
        if not name.startswith("SSD"):
            continue
        stack = [winreg.OpenKey(root, name)]
        while stack:
            key = stack.pop()
            for i in range(winreg.QueryInfoKey(key)[1]):
                value = winreg.EnumValue(key, i)[1]
                if isinstance(value, bytes) and value[:4] == b"SSDT":
                    out.append(value)
            stack += [winreg.OpenKey(key, sub) for sub in _subkeys(key)]
    return out


def _subkeys(key) -> list[str]:
    return [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]


# ------------------------------------------------------------------ HID

class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]


class _IFACE(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("guid", _GUID), ("flags", ctypes.c_uint32),
                ("reserved", ctypes.c_size_t)]


class _DEVINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("guid", _GUID), ("devinst", ctypes.c_uint32),
                ("reserved", ctypes.c_size_t)]


_HIDP_SUCCESS = 0x00110000
_REPORT_TYPES = ("input", "output", "feature")


def _hid_collections() -> dict[str, dict]:
    """{instance id: collection} for every HID top-level collection, from hid.dll's parsed caps.
    A zero-access handle is enough, so collections Windows holds exclusively (keyboard, mouse,
    digitizers) are included."""
    hid, setup = ctypes.WinDLL("hid"), ctypes.WinDLL("setupapi", use_last_error=True)
    setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setup.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    setup.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                                  ctypes.c_void_p]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                       ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    setup.SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p,
                                                  ctypes.c_uint32, ctypes.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    _k32.CreateFileW.restype = ctypes.c_void_p
    _k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                 ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [ctypes.c_void_p]
    for fn in ("HidD_GetAttributes", "HidD_GetPreparsedData", "HidD_GetProductString", "HidD_GetManufacturerString"):
        getattr(hid, fn).argtypes = [ctypes.c_void_p, ctypes.c_void_p] + ([ctypes.c_uint32] if "String" in fn else [])
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    hid.HidP_GetCaps.restype = ctypes.c_uint32
    for fn in ("HidP_GetButtonCaps", "HidP_GetValueCaps"):
        getattr(hid, fn).argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        getattr(hid, fn).restype = ctypes.c_uint32

    guid = _GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    info = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x2 | 0x10)  # PRESENT | DEVICEINTERFACE
    out = {}
    try:
        for index in range(1024):
            iface = _IFACE(cbSize=ctypes.sizeof(_IFACE))
            if not setup.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), index, ctypes.byref(iface)):
                break
            need = ctypes.c_uint32()
            setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            struct.pack_into("<I", buf, 0, 8)  # SP_DEVICE_INTERFACE_DETAIL_DATA_W.cbSize on 64-bit
            dev = _DEVINFO(cbSize=ctypes.sizeof(_DEVINFO))
            if not setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), buf, need, None,
                                                         ctypes.byref(dev)):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            inst = ctypes.create_unicode_buffer(512)
            setup.SetupDiGetDeviceInstanceIdW(info, ctypes.byref(dev), inst, 512, None)
            col = _hid_caps(hid, path)
            if col:
                out[inst.value.upper()] = col
    finally:
        setup.SetupDiDestroyDeviceInfoList(info)
    return out


def _hid_caps(hid, path: str) -> dict | None:
    handle = _k32.CreateFileW(path, 0, 3, None, 3, 0, None)  # no access, share read/write, OPEN_EXISTING
    if handle in (None, ctypes.c_void_p(-1).value):
        return None
    try:
        attrs = (ctypes.c_ubyte * 12)()
        struct.pack_into("<I", attrs, 0, 12)
        hid.HidD_GetAttributes(handle, attrs)
        _, vid, pid, ver = struct.unpack("<IHHH", bytes(attrs)[:10])
        product = ctypes.create_unicode_buffer(128)
        hid.HidD_GetProductString(handle, product, ctypes.sizeof(product))
        pp = ctypes.c_void_p()
        if not hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)):
            return None
        try:
            caps = (ctypes.c_ushort * 32)()
            if hid.HidP_GetCaps(pp, caps) != _HIDP_SUCCESS:
                return None
            usage, page, in_len, out_len, feat_len = caps[0], caps[1], caps[2], caps[3], caps[4]
            reports = {}
            # HIDP_CAPS after Reserved[17]: link nodes, then (buttons, values, indices) x input/output/feature
            for rtype, n_buttons, n_values in ((0, caps[23], caps[24]), (1, caps[26], caps[27]), (2, caps[29], caps[30])):
                fields = _caps(hid.HidP_GetButtonCaps, rtype, n_buttons, pp, button=True) + \
                    _caps(hid.HidP_GetValueCaps, rtype, n_values, pp, button=False)
                if fields:
                    reports[_REPORT_TYPES[rtype]] = sorted(fields, key=lambda f: (f["report_id"], f["usage_page"]))
            from . import hid as hidinfo

            return {"vendor": f"{vid:04x}", "product": f"{pid:04x}", "version": f"{ver:04x}",
                    "product_string": product.value or None, "usage_page": page, "usage": usage,
                    "name": hidinfo.name(page, usage),
                    "report_bytes": {"input": in_len, "output": out_len, "feature": feat_len}, "reports": reports}
        finally:
            hid.HidD_FreePreparsedData(pp)
    finally:
        _k32.CloseHandle(handle)


def _caps(fn, rtype: int, count: int, pp, button: bool) -> list[dict]:
    """HIDP_BUTTON_CAPS / HIDP_VALUE_CAPS (72 bytes each), unpacked by offset."""
    if not count:
        return []
    buf = (ctypes.c_ubyte * (72 * count))()
    n = ctypes.c_ushort(count)
    if fn(rtype, buf, ctypes.byref(n), pp) != _HIDP_SUCCESS:
        return []
    raw, out = bytes(buf), []
    for k in range(n.value):
        c = raw[72 * k:72 * (k + 1)]
        page, rid = struct.unpack_from("<HB", c, 0)
        is_range = c[12]
        lo, hi = struct.unpack_from("<HH", c, 56)
        field = {"report_id": rid, "usage_page": page, "usages": [lo, hi] if is_range else [lo]}
        if is_range:
            field["range"] = True
        if button:
            field.update(bits=1, count=(hi - lo + 1) if is_range else 1)
        else:
            bits, rcount = struct.unpack_from("<HH", c, 18)
            field.update(bits=bits, count=rcount)
        out.append(field)
    return out


# ------------------------------------------------------------------ display

_OUTPUT_TECH = {0: "VGA", 4: "DVI", 5: "HDMI", 6: "LVDS", 10: "DisplayPort", 11: "eDP (embedded DisplayPort)",
                13: "UDI embedded", 15: "Miracast", 18: "DisplayPort over USB-C", 0x80000000: "internal"}
_COLOR_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"


def _display(devices: list[dict], brightness: list[dict], out_dir: Path, notes: list[str]) -> dict:
    """Monitors (EDID, connector, current and available modes, HDR state, brightness levels)
    and the colour profiles associated with them."""
    from . import display

    monitors = []
    paths = _display_paths()
    for d in devices:
        if d["bus"] != "display":
            continue
        model, inst = d["id"].split("\\")[1:3]
        mon = {"device": d["id"], "name": d.get("name")}
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{model}\{inst}\Device Parameters")
            edid = winreg.QueryValueEx(key, "EDID")[0]
            (out_dir / "display").mkdir(parents=True, exist_ok=True)
            fname = f"display/{model}.edid"
            (out_dir / fname).write_bytes(edid)
            mon.update(edid_file=fname, edid=display.parse_edid(edid))
        except OSError:
            notes.append(f"no EDID in the registry for {d['id']}")
        path = next((p for p in paths if inst.upper() in p.get("device_path", "").upper()), None)
        if path:
            mon.update({k: v for k, v in path.items() if k != "device_path"})
        b = next((b for b in brightness if b["instance"].upper().startswith(d["id"].upper())), None)
        if b:
            mon["brightness"] = {"current": b["current"], "levels": len(b["levels"]),
                                 "min": min(b["levels"], default=None), "max": max(b["levels"], default=None)}
        monitors.append(mon)

    profiles, associated = [], _icm_associations()
    for p in sorted(_COLOR_DIR.glob("*")) if _COLOR_DIR.exists() else []:
        if p.suffix.lower() not in (".icc", ".icm"):
            continue
        dest = out_dir / "display" / "color" / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        profiles.append({"file": p.name, "size": p.stat().st_size, "sha256": _sha256(p),
                         "associated": p.name.lower() in associated, "copied_to": dest.relative_to(out_dir).as_posix()})
    return {"monitors": monitors, "color_profiles": profiles}


def _icm_associations() -> set[str]:
    r"""Profile file names associated with any display (HKCU / HKLM ...\ICM\ProfileAssociations)."""
    names = set()
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            root = winreg.OpenKey(hive, r"Software\Microsoft\Windows NT\CurrentVersion\ICM\ProfileAssociations")
        except OSError:
            continue
        stack = [root]
        while stack:
            key = stack.pop()
            for i in range(winreg.QueryInfoKey(key)[1]):
                value = winreg.EnumValue(key, i)[1]
                for v in value if isinstance(value, list) else [value]:
                    if isinstance(v, str):
                        names.update(n.strip().lower() for n in v.split() if n.lower().endswith((".icc", ".icm")))
            stack += [winreg.OpenKey(key, s) for s in _subkeys(key)]
    return names


def _display_paths() -> list[dict]:
    """Active display paths from the CCD API: connector type, refresh, HDR (advanced colour)
    state and SDR white level, plus the GDI mode list of each source."""
    user32 = ctypes.WinDLL("user32")
    np_, nm = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(np_), ctypes.byref(nm)):  # QDC_ONLY_ACTIVE_PATHS
        return []
    paths, modes = (ctypes.c_ubyte * (72 * np_.value))(), (ctypes.c_ubyte * (64 * nm.value))()
    if user32.QueryDisplayConfig(2, ctypes.byref(np_), paths, ctypes.byref(nm), modes, None):
        return []
    raw, out = bytes(paths), []
    for k in range(np_.value):
        p = raw[72 * k:72 * (k + 1)]
        src_luid, src_id = p[0:8], struct.unpack_from("<I", p, 8)[0]
        luid, target_id = p[20:28], struct.unpack_from("<I", p, 28)[0]
        num, den = struct.unpack_from("<II", p, 48)

        def info(kind: int, size: int, target=True) -> bytes | None:
            buf = (ctypes.c_ubyte * size)()
            struct.pack_into("<II8sI", buf, 0, kind, size, luid if target else src_luid, target_id if target else src_id)
            return bytes(buf) if user32.DisplayConfigGetDeviceInfo(buf) == 0 else None

        entry = {"refresh_hz": round(num / den, 2) if den else None}
        name = info(2, 420)  # DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
        if name:
            tech = struct.unpack_from("<I", name, 24)[0]
            entry["connector"] = _OUTPUT_TECH.get(tech, f"type {tech}")
            entry["device_path"] = name[164:420].decode("utf-16-le").split("\0")[0]
        color = info(9, 32)  # GET_ADVANCED_COLOR_INFO
        if color:
            bits, encoding, bpc = struct.unpack_from("<III", color, 20)
            entry["hdr"] = {"supported": bool(bits & 1), "enabled": bool(bits & 2), "bits_per_channel": bpc}
        white = info(11, 24)  # GET_SDR_WHITE_LEVEL (1000 = 80 nits)
        if white:
            entry["sdr_white_nits"] = round(struct.unpack_from("<I", white, 20)[0] * 80 / 1000)
        src = info(1, 84, target=False)  # GET_SOURCE_NAME -> \\.\DISPLAYn for the GDI mode list
        if src:
            entry.update(_gdi_modes(src[20:84].decode("utf-16-le").split("\0")[0]))
        out.append(entry)
    return out


def _gdi_modes(device: str) -> dict:
    user32 = ctypes.WinDLL("user32")
    user32.EnumDisplaySettingsExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    dm = (ctypes.c_ubyte * 220)()

    def read():
        return struct.unpack_from("<I", dm, 172)[0], struct.unpack_from("<I", dm, 176)[0], \
            struct.unpack_from("<I", dm, 184)[0], struct.unpack_from("<I", dm, 168)[0]

    struct.pack_into("<H", dm, 68, 220)
    current = None
    if user32.EnumDisplaySettingsExW(device, 0xFFFFFFFF, dm, 0):  # ENUM_CURRENT_SETTINGS
        w, h, hz, bpp = read()
        current = {"width": w, "height": h, "refresh_hz": hz, "bits_per_pixel": bpp}
    modes, i = set(), 0
    while user32.EnumDisplaySettingsExW(device, i, dm, 0):
        w, h, hz, _ = read()
        modes.add((w, h, hz))
        i += 1
    return {"current_mode": current, "modes": [f"{w}x{h}@{hz}" for w, h, hz in sorted(modes, reverse=True)]}


# ------------------------------------------------------------------ power

def _power(out_dir: Path) -> dict:
    """Sleep states, active plan and overlays, and every setting of the active plan (powercfg)."""
    def run(*args) -> str:
        try:
            return subprocess.run(["powercfg", *args], capture_output=True, text=True, timeout=60,
                                  errors="replace").stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    states = run("/availablesleepstates")
    available, _, unavailable = states.partition("not available")
    query = run("/query")
    (out_dir / "power").mkdir(parents=True, exist_ok=True)
    (out_dir / "power" / "powercfg_query.txt").write_text(query, encoding="utf-8")
    (out_dir / "power" / "sleep_states.txt").write_text(states, encoding="utf-8")

    from ..framework.environment import _OVERLAYS
    overlays = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes")
        for name in ("ActiveOverlayAcPowerScheme", "ActiveOverlayDcPowerScheme"):
            try:
                guid = winreg.QueryValueEx(key, name)[0].lower()
                overlays[name[13:15].lower()] = _OVERLAYS.get(guid, guid)
            except OSError:
                pass
    except OSError:
        pass
    return {"sleep_states": [line.strip() for line in available.splitlines()[1:] if line.strip()
                             and line.startswith("    ") and not line.startswith("\t")],
            "unavailable_sleep_states": [line.strip() for line in unavailable.splitlines()
                                         if line.startswith("    ") and line.strip()],
            "plan": next((line.split(":", 1)[1].strip() for line in run("/getactivescheme").splitlines()
                          if ":" in line), None),
            "overlay": overlays, "settings": _parse_powercfg(query), "files": ["power/powercfg_query.txt",
                                                                               "power/sleep_states.txt"]}


def _parse_powercfg(text: str) -> list[dict]:
    """powercfg /query -> [{subgroup, setting, guid, ac, dc}] (indices as integers)."""
    out, subgroup, current = [], None, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Subgroup GUID:"):
            subgroup = s.split("(", 1)[1].rstrip(")") if "(" in s else s.split(":", 1)[1].strip()
        elif s.startswith("Power Setting GUID:"):
            guid, _, name = s.split(":", 1)[1].strip().partition("  ")
            current = {"subgroup": subgroup, "setting": name.strip("() "), "guid": guid}
            out.append(current)
        elif current and s.startswith(("Current AC Power Setting Index:", "Current DC Power Setting Index:")):
            current["ac" if " AC " in s else "dc"] = int(s.split(":", 1)[1].strip(), 16)
    return out


# ------------------------------------------------------------------ vendor settings

# Registry trees where OEM control software keeps per-machine state (modes, OLED care,
# colour mode, feature support flags). Values that identify the unit or user are dropped.
# (path, recurse). Synaptics' subkeys are hundreds of per-zone gesture macros: top level only.
_VENDOR_KEYS = [(r"SOFTWARE\WOW6432Node\MSI\MSI Center S", True), (r"SOFTWARE\WOW6432Node\MSI\NB", True),
                (r"SOFTWARE\Synaptics\SynTPEnh", False), (r"SOFTWARE\Synaptics\SynTP\Install", False)]
_PRIVATE_NAMES = {"productsn", "barcode", "identifyingnumber", "osproductkey", "certificatekeyname",
                  "certificateblobvalue"}
_PRIVATE_PARTS = ("serial", "username")


def _private(name: str) -> bool:
    n = name.lower().replace("_", "")
    return n in _PRIVATE_NAMES or any(p in n for p in _PRIVATE_PARTS)


def _vendor_settings() -> dict:
    out = {}
    for path, recurse in _VENDOR_KEYS:
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        except OSError:
            continue
        stack = [(path, root)]
        while stack:
            name, key = stack.pop()
            values = {}
            for i in range(winreg.QueryInfoKey(key)[1]):
                vname, value, _ = winreg.EnumValue(key, i)
                if _private(vname) or vname.endswith("FileVersion"):
                    continue
                if isinstance(value, bytes) or (isinstance(value, str) and len(value) > 300):
                    continue
                values[vname] = value
            if values:
                out[name] = values
            if recurse:
                stack += [(f"{name}\\{s}", winreg.OpenKey(key, s)) for s in _subkeys(key)]
    return out


# ------------------------------------------------------------------ CPU

def _cpu() -> dict:
    r"""HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\<n>: "CP <encoding>" = system register."""
    cores = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor")
    except OSError:
        return {}
    for name in _subkeys(root):
        key = winreg.OpenKey(root, name)
        regs, mhz = {}, None
        for i in range(winreg.QueryInfoKey(key)[1]):
            vname, value, _ = winreg.EnumValue(key, i)
            if vname.startswith("CP "):
                regs[firmware.sysreg_name(int(vname[3:], 16))] = f"0x{value:016x}"
            elif vname == "~MHz":
                mhz = value
        core = {"cpu": int(name), "max_mhz": mhz, "registers": regs}
        if "MIDR_EL1" in regs:
            core.update(firmware.decode_midr(int(regs["MIDR_EL1"], 16)))
        cores.append(core)
    cores.sort(key=lambda c: c["cpu"])
    return {"cores": cores, "clusters": firmware.cpu_clusters(cores), "count": os.cpu_count()}
