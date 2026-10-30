"""Linux inventory from sysfs, in the same device schema as the Windows one so the two join.

  devices   ACPI devices (status from _STA, driver from the physical node that binds it: the
            platform / I2C / SPI / serial-bus child, not the ACPI node itself), PCI and USB
            devices, and platform devices with no ACPI companion
  drivers   loaded modules (/proc/modules) with their versions
  kernel    release, command line, deferred probes, missing firmware, probe errors
  firmware  ACPI tables and SMBIOS (root only), DMI identity (any user)
  cpu       per-core MIDR_EL1, cluster, cpufreq range; the Features line

Run it as root for the full picture: ACPI tables, the raw SMBIOS table, debugfs
devices_deferred and an unrestricted kernel log are root-only. Without root it records
what it could not read under ``notes``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import firmware

# ACPI pseudo-devices (system bus, power/sleep buttons, thermal zones as containers...) and
# namespace objects without _HID ("device:1a") have no Windows counterpart worth matching.
_PSEUDO_HID = re.compile(r"^(LNX|device:)")


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def collect(out_dir: Path, sysfs: Path = Path("/sys")) -> dict:
    notes = []
    deferred = _deferred(sysfs, notes)
    kernel = _kernel(out_dir, notes)
    return {"devices": devices(sysfs, deferred), "drivers": _modules(sysfs), "kernel": {**kernel, "deferred": deferred},
            "firmware": _firmware(sysfs, out_dir, notes), "cpu": _cpu(sysfs), "notes": notes}


# ------------------------------------------------------------------ devices

def devices(sysfs: Path, deferred: dict[str, list[str]]) -> list[dict]:
    out = _acpi_devices(sysfs) + _pci_devices(sysfs) + _usb_devices(sysfs) + _bare_platform_devices(sysfs)
    for d in out:
        reasons = [r for node in d.pop("_nodes") for r in deferred.get(node.split("/", 1)[-1], [])]
        if reasons and d["status"] != "ok":
            d["status"], d["problem"] = "deferred", "probe deferred: " + "; ".join(reasons)
    return out

def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace").strip("\0\n ")
    except OSError:
        return None


def _driver_of(dev: Path) -> dict | None:
    link = dev / "driver"
    if not link.exists():
        return None
    name = os.path.basename(os.readlink(link))
    module = (link / "module")
    mod = os.path.basename(os.readlink(module)) if module.exists() else None
    return {"name": name, "module": mod, "version": _read(module / "version") if mod else None}


def _node_id(dev: Path) -> str:
    """platform/NVDA0200:00, i2c/i2c-ELAN9024:00, pci/0000:00:01.0"""
    return f"{os.path.basename(os.readlink(dev / 'subsystem')) if (dev / 'subsystem').exists() else '?'}/{dev.name}"


def _acpi_devices(sysfs: Path) -> list[dict]:
    out = []
    for adev in sorted((sysfs / "bus/acpi/devices").glob("*")):
        hid = _read(adev / "hid")
        if not hid or _PSEUDO_HID.match(hid):
            continue
        sta = _read(adev / "status")
        if sta is not None and not int(sta) & 1:
            continue  # _STA says not present: Windows does not enumerate it either
        nodes = [Path(os.path.realpath(p)) for p in sorted(adev.glob("physical_node*"))]
        node_ids = [_node_id(n) for n in nodes]
        # PCI / USB devices with an ACPI companion are listed once, from their own bus.
        if any(n.startswith(("pci/", "usb/")) for n in node_ids):
            continue
        driver = next((drv for n in nodes if (drv := _driver_of(n))), None)
        out.append(_record(f"acpi/{adev.name}", "acpi", f"acpi:{hid}", _read(adev / "path"), driver,
                           name=_read(adev / "description") or hid, hardware_ids=[hid, *_cids(adev)],
                           extra={"physical_nodes": node_ids, "sta": sta}, nodes=node_ids))
    return out


def _cids(adev: Path) -> list[str]:
    """Compatible IDs from the modalias: acpi:NVDA0200:PNP0C50: -> [PNP0C50]."""
    alias = _read(adev / "modalias") or ""
    return [c for c in alias.split(":")[2:] if c]


def _pci_devices(sysfs: Path) -> list[dict]:
    out = []
    for dev in sorted((sysfs / "bus/pci/devices").glob("*")):
        ven, did = (_read(dev / f) or "0x0000" for f in ("vendor", "device"))
        mid = f"pci:{ven[2:]}:{did[2:]}"
        out.append(_record(f"pci/{dev.name}", "pci", mid, _read(dev / "firmware_node/path"), _driver_of(dev),
                           name=f"{mid} class {_read(dev / 'class')}", hardware_ids=[mid],
                           extra={"class_code": _read(dev / "class")}, nodes=[f"pci/{dev.name}"]))
    return out


def _usb_devices(sysfs: Path) -> list[dict]:
    out = []
    for dev in sorted((sysfs / "bus/usb/devices").glob("*")):
        if not (dev / "idVendor").exists():
            continue  # an interface; its device is listed
        mid = f"usb:{_read(dev / 'idVendor')}:{_read(dev / 'idProduct')}"
        name = " ".join(filter(None, (_read(dev / "manufacturer"), _read(dev / "product")))) or mid
        removable = _read(dev / "removable")
        # Interfaces carry the class drivers (usbhid, btusb, uvcvideo); the device itself only "usb".
        ifaces = sorted(d for d in dev.glob(f"{dev.name}:*") if (d / "bInterfaceClass").exists())
        drivers = [drv for i in ifaces if (drv := _driver_of(i))]
        out.append(_record(f"usb/{dev.name}", "usb", mid, _read(dev / "firmware_node/path"),
                           drivers[0] if drivers else _driver_of(dev), name=name, hardware_ids=[mid],
                           internal={"fixed": True, "removable": False}.get(removable),
                           extra={"interface_drivers": sorted({d["name"] for d in drivers})},
                           nodes=[f"usb/{dev.name}", *(f"usb/{i.name}" for i in ifaces)]))
    return out


def _bare_platform_devices(sysfs: Path) -> list[dict]:
    """Platform devices registered by drivers or DT overlays rather than from ACPI."""
    out = []
    for dev in sorted((sysfs / "bus/platform/devices").glob("*")):
        if (dev / "firmware_node").exists():
            continue
        out.append(_record(f"platform/{dev.name}", "platform", f"platform:{dev.name}", None, _driver_of(dev),
                           name=dev.name, hardware_ids=[], nodes=[f"platform/{dev.name}"]))
    return out


def _record(id_, bus, mid, acpi_path, driver, *, name, hardware_ids, nodes, internal=None, extra=None) -> dict:
    return {"id": id_, "name": name, "bus": bus, "match_id": mid, "class": None, "manufacturer": None,
            "hardware_ids": hardware_ids, "compatible_ids": [], "acpi_path": acpi_path, "location": [],
            "parent": None, "internal": internal, "status": "ok" if driver else "no-driver", "problem": None,
            "driver": driver, "resources": {}, **(extra or {}), "_nodes": nodes}


def _deferred(sysfs: Path, notes: list[str]) -> dict[str, list[str]]:
    """debugfs devices_deferred: "<device name>\\t<reason>" lines; the usual bring-up blocker.
    Keyed by device name (NVDA9221:00), which is how it lists them."""
    path = sysfs / "kernel/debug/devices_deferred"
    text = _read(path)
    if text is None:
        notes.append(f"{path} not readable (needs root and debugfs); deferred probes not captured")
        return {}
    out: dict[str, list[str]] = {}
    for line in filter(None, text.splitlines()):
        dev, _, reason = line.partition("\t")
        out.setdefault(dev.strip(), []).append(reason.strip() or "no reason given")
    return out


def _modules(sysfs: Path) -> list[dict]:
    out = []
    for line in (_read(Path("/proc/modules")) or "").splitlines():
        name, size, refs, used_by, *_ = line.split() + ["", "", ""]
        out.append({"name": name, "size": int(size) if size.isdigit() else None,
                    "used_by": [u for u in used_by.strip(",").split(",") if u and u != "-"],
                    "version": _read(sysfs / f"module/{name}/version")})
    return out


# ------------------------------------------------------------------ kernel

_LOG_PATTERNS = {
    "missing_firmware": re.compile(r"(Direct firmware load for \S+ failed|firmware: failed to load \S+)"),
    "probe_errors": re.compile(r"(probe .*failed|failed to probe|probe of \S+ failed with error -?\d+)", re.I),
    "acpi_errors": re.compile(r"ACPI (Error|BIOS Error|Warning)|AE_\w+"),
}


def _kernel(out_dir: Path, notes: list[str]) -> dict:
    info = {"release": os.uname().release, "cmdline": _read(Path("/proc/cmdline"))}
    log = None
    for cmd in (["dmesg"], ["journalctl", "-k", "-b", "--no-pager", "-o", "short-monotonic"]):
        if shutil.which(cmd[0]):
            proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
            if proc.returncode == 0 and proc.stdout.strip():
                log = proc.stdout
                break
    if log is None:
        notes.append("kernel log not readable (dmesg_restrict?); run as root")
        return info
    (out_dir / "kernel.log").write_text(log, encoding="utf-8")
    info["log_file"] = "kernel.log"
    for key, pattern in _LOG_PATTERNS.items():
        hits = [line.strip() for line in log.splitlines() if pattern.search(line)]
        info[key] = list(dict.fromkeys(hits))[:200]
    return info


# ------------------------------------------------------------------ firmware

def _firmware(sysfs: Path, out_dir: Path, notes: list[str]) -> dict:
    tables = []
    root = sysfs / "firmware/acpi/tables"
    for p in sorted(root.rglob("*")) if root.exists() else []:
        try:
            if p.is_file():
                tables.append(p.read_bytes())
        except PermissionError:
            notes.append(f"ACPI tables in {root} are root-only; not captured")
            tables = []
            break
    acpi = firmware.save_acpi_tables(tables, out_dir / "acpi") if tables else []

    dmi = {k: _read(sysfs / f"class/dmi/id/{k}") for k in
           ("bios_vendor", "bios_version", "bios_date", "bios_release", "ec_firmware_release", "sys_vendor",
            "product_name", "product_version", "product_sku", "board_vendor", "board_name")}
    smbios = {"dmi": {k: v for k, v in dmi.items() if v}}
    try:
        table = (sysfs / "firmware/dmi/tables/DMI").read_bytes()
        ep = (sysfs / "firmware/dmi/tables/smbios_entry_point").read_bytes()
        major, minor, docrev = (ep[7], ep[8], ep[9]) if ep[:5] == b"_SM3_" else (ep[6], ep[7], 0)
        (out_dir / "smbios.bin").write_bytes(firmware.smbios_dump(table, major, minor, docrev))
        smbios.update({"version": f"{major}.{minor}", "file": "smbios.bin", **firmware.smbios_summary(table)})
    except OSError:
        notes.append("raw SMBIOS table is root-only; only /sys/class/dmi/id captured")
    return {"acpi_tables": acpi, "smbios": smbios}


# ------------------------------------------------------------------ CPU

def _cpu(sysfs: Path) -> dict:
    cores = []
    for d in sorted((sysfs / "devices/system/cpu").glob("cpu[0-9]*"), key=lambda p: int(p.name[3:])):
        core = {"cpu": int(d.name[3:]), "cluster_id": _read(d / "topology/cluster_id"),
                "package_id": _read(d / "topology/physical_package_id")}
        khz = _read(d / "cpufreq/cpuinfo_max_freq")
        core["max_mhz"] = int(khz) // 1000 if khz and khz.isdigit() else None
        khz = _read(d / "cpufreq/cpuinfo_min_freq")
        core["min_mhz"] = int(khz) // 1000 if khz and khz.isdigit() else None
        core["cpufreq_driver"] = _read(d / "cpufreq/scaling_driver")
        core["idle_states"] = [_read(s / "name") for s in sorted(d.glob("cpuidle/state*"))]
        midr = _read(d / "regs/identification/midr_el1")
        if midr:
            core.update(firmware.decode_midr(int(midr, 16)))
            core["registers"] = {"MIDR_EL1": midr, "REVIDR_EL1": _read(d / "regs/identification/revidr_el1")}
        cores.append(core)
    features = next((line.split(":", 1)[1].split() for line in (_read(Path("/proc/cpuinfo")) or "").splitlines()
                     if line.startswith("Features")), [])
    return {"cores": cores, "clusters": firmware.cpu_clusters(cores), "count": len(cores), "features": features}
