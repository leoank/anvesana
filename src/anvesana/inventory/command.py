"""Hardware / driver inventory of a node, and the Windows-to-Linux porting gap.

  bench inventory collect                       snapshot this host into the store
  bench inventory list [MACHINE]                stored snapshots
  bench inventory show [REF] [--grep NVDA]      devices with driver, version, ACPI path, MMIO/IRQ
  bench inventory compare A B                   join two snapshots device by device

`compare bbaum-pc-7@windows bbaum-pc-7@linux` is the bring-up list: every device Windows
drives, and whether Linux binds a driver to it (GAP: present but unbound or deferred;
MISSING: not enumerated at all). Two snapshots from the same OS show driver and firmware
drift instead (CHANGED). Devices are joined on their ACPI namespace path, then on the
cross-OS hardware id (acpi:NVDA0200, pci:10de:2e03, usb:046d:c548).

References: a path, <machine>[@latest], <machine>@-1, <machine>@<date>, <machine>@windows|linux.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from ..framework import store
from ..framework.console import RULE, Table
from . import snapshot

# Enumerators of software-only devices (volumes, software components, root-enumerated
# virtual devices, hub/terminal-services stubs): no hardware to port.
SOFTWARE_BUSES = {"swd", "root", "sw", "htree", "storage", "vhf", "ts_usb_hub_enumerator", "umb",
                  "buttonconverter"}
# What the Linux collector enumerates; a cross-OS compare only lists these.
PORTING_BUSES = {"acpi", "pci", "usb"}
# Most actionable first.
VERDICTS = ["GAP", "MISSING", "PROBLEM", "CHANGED", "NEW", "EXTRA", "OK", "-"]


def add_arguments(p):
    sub = p.add_subparsers(dest="action", required=True)
    c = sub.add_parser("collect", help="snapshot this host's devices, drivers and firmware tables")
    c.add_argument("--machine", help="machine id (default: this host's profile, else its hostname)")
    c.add_argument("--store", help="results store")

    c = sub.add_parser("list", help="stored snapshots")
    c.add_argument("machine", nargs="?")
    c.add_argument("--store", help="results store")

    c = sub.add_parser("show", help="one snapshot: devices, drivers, CPU, ACPI tables")
    c.add_argument("ref", nargs="?", help="snapshot reference (default: newest of this host)")
    _filters(c)
    c.add_argument("--resources", action="store_true", help="add MMIO ranges and IRQs (Windows snapshots)")
    c.add_argument("--packages", action="store_true", help="list every file of each driver package")
    c.add_argument("--json", action="store_true", help="print the selected devices as JSON")
    c.add_argument("--store", help="results store")

    c = sub.add_parser("compare", help="device-by-device comparison of two snapshots")
    c.add_argument("a", help="reference snapshot, e.g. bbaum-pc-7@windows")
    c.add_argument("b", help="snapshot to compare, e.g. bbaum-pc-7@linux")
    _filters(c)
    c.add_argument("--changes-only", action="store_true", help="omit OK and unchanged rows")
    c.add_argument("--expand", action="store_true", help="one row per device instead of grouping identical ones")
    c.add_argument("--markdown", help="also write the comparison as a Markdown file")
    c.add_argument("--store", help="results store")


def _filters(p):
    p.add_argument("--all", action="store_true",
                   help="include software devices and external peripherals (default: SoC and internal hardware)")
    p.add_argument("--bus", help="comma-separated buses, e.g. acpi,pci")
    p.add_argument("--grep", help="regex over id, name, driver and ACPI path, e.g. NVDA")


def main(args) -> int:
    root = store.store_root(args.store)
    return {"collect": _collect, "list": _list, "show": _show, "compare": _compare}[args.action](args, root)


# ------------------------------------------------------------------ collect / list

def _collect(args, root: Path) -> int:
    path = snapshot.collect(root, snapshot.machine_id(args.machine))
    doc = snapshot.load(path)
    devs = doc["devices"]
    hw = [d for d in devs if _is_hardware(d)]
    unbound = [d for d in hw if d["status"] != "ok"]
    print(f"{len(devs)} devices ({len(hw)} hardware, {len(unbound)} without a working driver), "
          f"{len(doc.get('drivers', []))} drivers, {len(doc['firmware'].get('acpi_tables', []))} ACPI tables, "
          f"{len(doc.get('cpu', {}).get('cores', []))} CPUs")
    for note in doc.get("notes", []):
        print(f" !! {note}")
    print(f"Saved {path}\nNext: bench inventory show {doc['snapshot_id']}")
    return 0


def _list(args, root: Path) -> int:
    snaps = snapshot.list_snapshots(root, args.machine)
    for s in snaps:
        print(f"{s['snapshot_id']:<52} {len(s.get('devices', [])):>4} devices  "
              f"{'privileged' if s.get('privileged') else 'unprivileged'}")
    print(f"\n{len(snaps)} snapshots in {root}")
    return 0


# ------------------------------------------------------------------ show

def _is_hardware(d: dict) -> bool:
    return d.get("bus") not in SOFTWARE_BUSES and not d.get("bus", "").startswith("{") and d.get("internal") is not False


def _select(devices: list[dict], args, buses: set[str] | None = None) -> list[dict]:
    out = [d for d in devices if args.all or _is_hardware(d)]
    wanted = {b.strip().lower() for b in args.bus.split(",")} if args.bus else buses
    if wanted:
        out = [d for d in out if d.get("bus") in wanted]
    if args.grep:
        rx = re.compile(args.grep, re.I)
        out = [d for d in out if rx.search(" ".join(str(x) for x in (
            d.get("id"), d.get("name"), d.get("acpi_path"), _driver_text(d), d.get("match_id")) if x))]
    return out


def _driver_text(d: dict) -> str:
    drv = d.get("driver") or {}
    parts = [drv.get("name") or ""]
    if drv.get("upper_filters"):
        parts.append("+" + "+".join(drv["upper_filters"]))
    if drv.get("lower_filters"):
        parts.append("-" + "-".join(drv["lower_filters"]))
    return "".join(parts) or "-"


def _resources_text(d: dict) -> str:
    r = d.get("resources") or {}
    mem = [f"{a:#x}-{b:#x}" if b else f"{a:#x}" for a, b in r.get("mem", [])]
    irq = [f"irq {i}" for i in r.get("irq", [])]
    return " ".join(mem + irq)


def _show(args, root: Path) -> int:
    doc = snapshot.resolve(args.ref or snapshot.machine_id(None), root)
    devices = sorted(_select(doc["devices"], args), key=lambda d: (d["bus"], d["match_id"], d["id"]))
    if args.json:
        print(json.dumps(devices, indent=2))
        return 0
    env = doc.get("environment", {})
    smb = doc.get("firmware", {}).get("smbios", {})
    bios = smb.get("bios") or {}
    print(RULE)
    print(f" {doc['snapshot_id']}   ({'privileged' if doc.get('privileged') else 'unprivileged'})")
    print(f" {env.get('platform', '')}   kernel {env.get('kernel', '?')}")
    system = smb.get("system") or {}
    print(f" {system.get('manufacturer') or ''} {system.get('product') or ''}   BIOS {bios.get('vendor') or ''} "
          f"{bios.get('version') or env.get('bios', '')} {bios.get('date') or ''}")
    print(f" stored in {doc['_path']}")
    print(RULE)
    for note in doc.get("notes", []):
        print(f" !! {note}")

    cpu = doc.get("cpu") or {}
    if cpu.get("clusters"):
        t = Table("CPU core types", ["core", "MIDR", "rev", "count", "cpus", "max MHz"])
        for c in cpu["clusters"]:
            t.add(c.get("core") or "?", c.get("midr") or "?", c.get("revision") or "", c["count"], c["cpus"],
                  c.get("max_mhz") or "-")
        print(t.text())

    tables = doc.get("firmware", {}).get("acpi_tables", [])
    if tables:
        t = Table("ACPI tables", ["sig", "OEM", "table id", "OEM rev", "bytes", "crc32", "file"])
        for h in tables:
            t.add(h["signature"], h["oem_id"], h["oem_table_id"], f"{h['oem_revision']:#x}", h["length"],
                  h["crc32"], h["file"])
        print(t.text())
        print("  disassemble: iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat   (in the snapshot folder)")

    headers = ["device", "name", "driver", "version", "ACPI path", "status"]
    if args.resources:
        headers.append("resources")
    t = Table(f"Devices ({len(devices)} of {len(doc['devices'])})", headers)
    for d in devices:
        drv = d.get("driver") or {}
        row = [d["match_id"], (d.get("name") or "")[:44], _driver_text(d), drv.get("version") or "",
               d.get("acpi_path") or "", d["status"] if d["status"] == "ok" else f"{d['status']} {d.get('problem') or ''}"]
        if args.resources:
            row.append(_resources_text(d))
        t.add(*row)
    print(t.text())

    if doc.get("packages"):
        t = Table("Third-party driver packages (INFs copied to drivers/)", ["package", "services", "files", "firmware/data files"])
        for pkg in doc["packages"]:
            data = [f["file"] for f in pkg["files"]
                    if Path(f["file"]).suffix.lower() not in (".sys", ".inf", ".cat", ".dll", ".pnf")]
            t.add(pkg["package"], ",".join(pkg["services"]), len(pkg["files"]), ", ".join(data)[:70] or "-")
        print(t.text())
        if args.packages:
            for pkg in doc["packages"]:
                print(f"\n {pkg['package']}")
                for f in pkg["files"]:
                    print(f"   {f['file']:<48} {f['size']:>10,}  {(f.get('sha256') or '')[:16]}")

    kernel = doc.get("kernel") or {}
    for key, title in (("deferred", "Deferred probes"), ("missing_firmware", "Missing firmware"),
                       ("probe_errors", "Probe errors"), ("acpi_errors", "ACPI errors")):
        items = kernel.get(key)
        if items:
            print(f"\n{title} ({len(items)})")
            lines = [f"{k}: {'; '.join(v)}" for k, v in items.items()] if isinstance(items, dict) else items
            for line in lines[:25]:
                print(f"  {line}")
    return 0


# ------------------------------------------------------------------ compare

def _norm_path(path: str | None) -> str | None:
    r"""Windows reports \_SB.I2C0, Linux \_SB_.I2C0 (segments padded to 4 with '_')."""
    if not path:
        return None
    return ".".join(seg.rstrip("_") for seg in path.upper().split("."))


def pair(a: list[dict], b: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """Joins devices on ACPI path, then on match_id (in id order for repeated ids)."""
    by_path = {}
    for d in b:
        if (p := _norm_path(d.get("acpi_path"))) and p not in by_path:
            by_path[p] = d
    used, pairs = set(), []
    for d in a:
        m = by_path.get(_norm_path(d.get("acpi_path")))
        if m is not None and id(m) not in used:
            used.add(id(m))
        else:
            m = None
        pairs.append([d, m])
    remaining = defaultdict(list)
    for d in sorted(b, key=lambda d: d["id"]):
        if id(d) not in used:
            remaining[d["match_id"]].append(d)
    for p in pairs:
        if p[1] is None and remaining.get(p[0]["match_id"]):
            p[1] = remaining[p[0]["match_id"]].pop(0)
    pairs += [[None, d] for ds in remaining.values() for d in ds]
    return [tuple(p) for p in pairs]


def _state(d: dict | None) -> str:
    if d is None:
        return "absent"
    if d["status"] == "ok":
        return "driven" if (d.get("driver") or {}).get("name") else "idle"
    return d["status"]


def verdict(a: dict | None, b: dict | None, same_os: bool) -> str:
    sa, sb = _state(a), _state(b)
    if sa == "driven" and sb == "driven":
        if same_os and (_driver_text(a), a["driver"].get("version")) != (_driver_text(b), b["driver"].get("version")):
            return "CHANGED"
        return "OK"
    if sa == "driven" and sb == "absent":
        return "MISSING"
    if sa == "driven":
        return "GAP"
    if sb in ("problem", "deferred") or (same_os and sb == "no-driver" and sa != "no-driver"):
        return "PROBLEM"
    if sb == "driven" and sa != "absent":
        return "NEW"
    if sa == "absent":
        return "EXTRA"
    return "-"


def _side(d: dict | None) -> str:
    if d is None:
        return "-"
    drv = d.get("driver") or {}
    text = _driver_text(d) if drv else ""
    if drv.get("version"):
        text += f" {drv['version']}"
    if d["status"] != "ok":
        text += f" [{d['status']}{': ' + d['problem'] if d.get('problem') else ''}]"
    return text.strip() or "(no driver)"


def _compare(args, root: Path) -> int:
    a, b = snapshot.resolve(args.a, root), snapshot.resolve(args.b, root)
    same_os = a.get("os") == b.get("os")
    buses = None if same_os else PORTING_BUSES
    da = [d for d in _select(a["devices"], args, buses) if same_os or ":if" not in d["match_id"]]
    db = [d for d in _select(b["devices"], args, buses) if same_os or ":if" not in d["match_id"]]
    la, lb = f"{a['os']} {a['collected_at'][:10]}", f"{b['os']} {b['collected_at'][:10]}"
    if la == lb:
        la, lb = a["snapshot_id"], b["snapshot_id"]

    # Identical instances (20 CPUs, 7 I2C controllers in the same state) collapse into one row.
    groups: dict[tuple, list] = {}
    for x, y in pair(da, db):
        v = verdict(x, y, same_os)
        if args.changes_only and v in ("OK", "-"):
            continue
        ref = x or y
        key = (v, ref["match_id"], _side(x), _side(y)) if not args.expand else (id(ref),)
        groups.setdefault(key, []).append((v, ref, x, y))
    rows = sorted(groups.values(), key=lambda g: (VERDICTS.index(g[0][0]), not g[0][1]["match_id"].startswith("acpi:NVDA"),
                                                  g[0][1]["match_id"], g[0][1].get("acpi_path") or ""))

    tables = [_firmware_table(a, b, la, lb)]
    t = Table(f"Devices: {a['snapshot_id']} vs {b['snapshot_id']}",
              ["verdict", "device", "n", "name", "ACPI path", la, lb])
    counts = defaultdict(int)
    for g in rows:
        v, ref, x, y = g[0]
        counts[v] += len(g)
        paths = sorted(p for _, r, _, _ in g if (p := r.get("acpi_path")))
        where = paths[0] + (f" +{len(paths) - 1} more" if len(paths) > 1 else "") if paths else ""
        t.add(v, ref["match_id"], len(g), (ref.get("name") or "")[:40], where, _side(x), _side(y))
    tables.append(t)

    summary = ", ".join(f"{counts[v]} {v}" for v in VERDICTS if counts[v]) or "no differences"
    legend = ("GAP: driven on A, present but not driven on B.  MISSING: driven on A, not enumerated on B.  "
              "PROBLEM: B reports a problem / deferred probe.  NEW: driven only on B.  EXTRA: only on B."
              if not same_os else
              "CHANGED: driver, filters or version differ.  PROBLEM: B lost its driver or reports a problem.")
    for tb in tables:
        print(tb.text())
    print(f"\n{summary}\n{legend}")
    if args.markdown:
        Path(args.markdown).write_text(
            f"# Inventory: {a['snapshot_id']} vs {b['snapshot_id']}\n\n{summary}\n\n{legend}\n"
            + "\n".join(tb.markdown() for tb in tables) + "\n", encoding="utf-8")
        print(f"Wrote {args.markdown}")
    return 1 if counts["GAP"] or counts["MISSING"] or counts["PROBLEM"] else 0


def _bios(doc: dict) -> str | None:
    bios = doc.get("firmware", {}).get("smbios", {}).get("bios") or {}
    return " ".join(filter(None, (bios.get(k) for k in ("vendor", "version", "date")))) or         doc.get("environment", {}).get("bios")


def _firmware_table(a: dict, b: dict, la: str, lb: str) -> Table:
    """Firmware, CPU and ACPI tables. Cross-OS the tables should be byte-identical: a
    difference means Linux booted a different firmware configuration or loaded an override."""
    t = Table("Firmware and CPU", ["", la, lb])
    for label, get in (("BIOS", _bios),
                       ("kernel", lambda d: d.get("environment", {}).get("kernel")),
                       ("NVIDIA driver", lambda d: d.get("environment", {}).get("nvidia_driver")),
                       ("CPUs", lambda d: ", ".join(f"{c['count']}x {c.get('core')} @{c.get('max_mhz') or '?'} MHz"
                                                     for c in (d.get("cpu") or {}).get("clusters", [])))):
        t.add(label, get(a) or "-", get(b) or "-")
    ta = {(h["signature"], h["oem_table_id"]): h for h in a.get("firmware", {}).get("acpi_tables", [])}
    tb = {(h["signature"], h["oem_table_id"]): h for h in b.get("firmware", {}).get("acpi_tables", [])}
    for key in sorted(set(ta) | set(tb)):
        x, y = ta.get(key), tb.get(key)
        fmt = lambda h: f"{h['length']} B rev {h['oem_revision']:#x} crc {h['crc32']}" if h else "-"  # noqa: E731
        if not x or not y or x["crc32"] != y["crc32"]:
            t.add(f"ACPI {key[0]} {key[1]}", fmt(x), fmt(y))
    if ta and tb and all(ta[k]["crc32"] == tb[k]["crc32"] for k in set(ta) & set(tb)):
        t.add("ACPI tables in both", f"{len(set(ta) & set(tb))} identical", "")
    return t

