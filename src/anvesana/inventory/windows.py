"""Windows inventory. Everything here works without administrator rights.

  devices   present PnP devices: hardware IDs, ACPI namespace path, parent, function driver
            and filter drivers, INF / version / provider, problem code, MMIO / IRQ resources
  drivers   every kernel driver service with its binary's version resource
  packages  third-party driver-store folders: the INF (copied) and every file it installs
            (listed with size and hash; DSP / NPU firmware blobs show up here)
  firmware  ACPI tables (GetSystemFirmwareTable; SSDTs from the HKLM\\HARDWARE\\ACPI mirror,
            since the API returns only the first table of a signature), raw SMBIOS
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
@{ devices = @($devices); drivers = @($drivers) } | ConvertTo-Json -Depth 6 -Compress
"""

HASH_LIMIT = 32 << 20

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


def collect(out_dir: Path) -> dict:
    raw = _powershell(_SCRIPT)
    devices = [_device(d) for d in raw.get("devices") or []]
    drivers = sorted(raw.get("drivers") or [], key=lambda d: d["name"].lower())
    notes = []

    tables = _acpi_tables()
    acpi = firmware.save_acpi_tables(tables, out_dir / "acpi") if tables else []
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

    return {"devices": devices, "drivers": drivers, "packages": _driver_packages(devices, drivers, out_dir),
            "firmware": {"acpi_tables": acpi, "smbios": smbios}, "cpu": _cpu(), "notes": notes}


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

def _driver_packages(devices: list[dict], drivers: list[dict], out_dir: Path) -> list[dict]:
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
