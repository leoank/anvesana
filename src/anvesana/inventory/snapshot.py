"""Inventory snapshots: one directory per collection, next to the machine's runs in the store.

  $ANVESANA_RESULTS_DIR/<machine>/inventory/<machine>_<YYYY-MM-DD_HHMMSS>_<os>/
    inventory.json     the schema below
    acpi/*.dat         raw ACPI tables (iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat)
    smbios.bin         raw SMBIOS in dmidecode --dump-bin layout (dmidecode --from-dump smbios.bin)
    drivers/<pkg>/     Windows: the INF of every third-party driver package a device uses
    hid/*.bin          Linux: raw HID report descriptors
  $ANVESANA_RESULTS_DIR/<machine>/inventory/firmware/<sha256[:16]>_<name>
                       Windows with --copy-firmware: firmware blobs from driver packages, stored
                       once per content and referenced from each snapshot's packages[].files[]
    kernel.log         Linux: the boot's kernel log

inventory.json (schema version 1):
  schema_version, snapshot_id, collected_at, os, privileged (admin / root)
  machine        {id, hostname}
  environment    as in run.json (OS, kernel, CPU, BIOS, NVIDIA driver, ...)
  devices        [{id, name, bus, match_id, class, manufacturer, hardware_ids, compatible_ids,
                   acpi_path, location, parent, internal, status, problem, driver, resources}]
                 match_id is the cross-OS identity: acpi:NVDA0200, pci:10de:2e03, usb:046d:c548
                 status: ok | no-driver | problem | deferred (Linux)
                 driver: {name, version, ...}: Windows adds inf/provider/date and filters,
                 Linux the module
                 resources (Windows): {mem: [[start, end]], irq: [...], io, dma}
  drivers        Windows: kernel driver services; Linux: loaded modules
  packages       Windows: third-party driver-store folders and their files
  hid            [{device, name, bus, acpi_path, vendor, product, collections: [{usage_page, usage,
                   name, reports: {input|output|feature: [{report_id, usage_page, usages, bits, count}]}}]}]
  kernel         Linux: release, cmdline, deferred probes, missing firmware, probe/ACPI errors
  firmware       {acpi_tables: [header + crc32 + file], smbios: summary,
                  wmi: [ACPI-WMI blocks from _WDG: guid, kind, object_id], esrt: [capsule-updatable firmware]}
  cpu            {cores: [{cpu, midr, core, registers, max_mhz, ...}], clusters, features}
  notes          what could not be collected and why

Snapshot references: a path, <machine>[@latest], <machine>@-1, <machine>@<date>, or
<machine>@windows / @linux for the newest snapshot from that OS.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from ..framework import environment, machine as machines

SCHEMA_VERSION = 1


def machine_id(requested: str | None) -> str:
    """The profile's id; a brand-new node with no profile yet falls back to its hostname."""
    if requested:
        return requested
    host = environment.hostname()
    return next((p.id for p in machines.all_profiles() if host in p.hostnames), host)


def inventory_root(root: Path, mid: str) -> Path:
    return root / mid / "inventory"


def collect(root: Path, mid: str, copy_firmware: bool = False, log=print) -> Path:
    started = dt.datetime.now().astimezone()
    snapshot_id = f"{mid}_{started.strftime('%Y-%m-%d_%H%M%S')}_{environment.os_tag()}"
    out = inventory_root(root, mid) / snapshot_id
    out.mkdir(parents=True, exist_ok=False)
    try:
        if sys.platform == "win32":
            from . import windows as collector

            privileged = collector.is_admin()
        elif sys.platform == "linux":
            from . import linux as collector

            privileged = collector.is_root()
        else:
            raise SystemExit(f"no inventory collector for {sys.platform}")
        log(f"Collecting inventory for {mid} into {out} ...")
        # Firmware blobs are shared by the machine's snapshots (content-addressed), not per snapshot.
        fw_dir = inventory_root(root, mid) / "firmware" if copy_firmware else None
        data = collector.collect(out, fw_dir) if sys.platform == "win32" else collector.collect(out)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    doc = {"schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id,
           "collected_at": started.isoformat(timespec="seconds"), "os": environment.os_tag(),
           "privileged": privileged, "machine": {"id": mid, "hostname": environment.hostname()},
           "environment": environment.capture(), **data}
    (out / "inventory.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def load(path: Path) -> dict:
    p = path / "inventory.json" if path.is_dir() else path
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["_path"] = str(p.parent)
    return doc


def list_snapshots(root: Path, mid: str | None = None) -> list[dict]:
    """Oldest first."""
    out = []
    for p in root.glob(f"{mid or '*'}/inventory/*/inventory.json"):
        try:
            out.append(load(p))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda d: d.get("collected_at", ""))


def resolve(ref: str, root: Path) -> dict:
    p = Path(ref).expanduser()
    if p.exists():
        return load(p)
    mid, _, selector = ref.partition("@")
    selector = selector or "latest"
    snaps = list_snapshots(root, mid)
    if selector in ("windows", "linux", "macos"):
        snaps = [s for s in snaps if s.get("os") == selector]
        selector = "latest"
    if not snaps:
        for cand in root.glob(f"*/inventory/{ref}/inventory.json"):
            return load(cand)
        raise SystemExit(f"No inventory snapshots for '{ref}' in {root}; run `bench inventory collect`")
    if selector == "latest":
        return snaps[-1]
    if selector.lstrip("-").isdigit():
        idx = -1 + int(selector)
        if -idx > len(snaps):
            raise SystemExit(f"'{ref}': only {len(snaps)} snapshots stored")
        return snaps[idx]
    for s in snaps:
        if s.get("collected_at", "").startswith(selector):
            return s
    raise SystemExit(f"No snapshot of '{mid}' matches '{selector}'")
