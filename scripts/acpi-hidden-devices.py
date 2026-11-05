"""List, and optionally expose, ACPI devices that the firmware hides from "Windows 2022".

    uv run python scripts/acpi-hidden-devices.py <dump-dir>                      # list
    uv run python scripts/acpi-hidden-devices.py <dump-dir> --expose SSPM --out nix/local/acpi

On the N1X laptops some devices have exactly this status method:

    Method (_STA) { If (_OSI ("Windows 2022")) { Return (0) } Else { Return (0x0F) } }

Windows 11 answers that _OSI query true, so the device is hidden; Linux answers
true to the Windows strings it knows, so it is likely hidden there as well (the live image checks). On bbaum-pc-7
(DSDT/SSDT from `bench inventory collect`): SVP0 NVDA3000, SSPM NVDA8400,
HFRP MTK00055 (DSDT); NH1X NVDA300A, NMAP NVDA300B (SSDT). The ASUS ProArt P16 Arch build exposes
SSPM the same way (github.com/pfeifferj/archlinuxarm-proart-p16, sspm-patch.json).

--expose rewrites only the predicate of the named devices' _STA to `Zero`
followed by Noops, so the Else branch (present, 0x0F) runs; the table keeps its
length, every other byte is unchanged except the OEM revision (+1, so Linux's
initrd table upgrade accepts it) and the checksum. It writes the patched tables
and `acpi-override.cpio` (kernel/firmware/acpi/*.aml, newc) for
boot.initrd.prepend. Nothing is flashed; the override exists only in RAM for
that boot. The output contains the vendor's tables: keep it out of git.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

PREDICATE = b"\x5f\x4f\x53\x49\x0dWindows 2022\x00"                    # _OSI ("Windows 2022")
STA = b"\x14\x21_STA\x00\xa0\x15" + PREDICATE + b"\xa4\x00\xa1\x04\xa4\x0a\x0f"
PATCHED_PREDICATE = b"\x00" + b"\xa3" * (len(PREDICATE) - 1)            # Zero, then Noop x17


def device_name(table: bytes, at: int) -> tuple[str, str]:
    """(name, _HID) of the Device() enclosing offset ``at``: the nearest DeviceOp before it."""
    start = table.rfind(b"\x5b\x82", 0, at)
    if start < 0:
        return "?", "?"
    pkg = table[start + 2]
    nbytes = (pkg >> 6) + 1                     # PkgLength: bits 7-6 = extra bytes
    name = table[start + 2 + nbytes:start + 6 + nbytes].decode("ascii", "replace")
    hid_at = table.find(b"_HID\x0d", start, at)
    hid = table[hid_at + 5:table.index(b"\x00", hid_at + 5)].decode("ascii", "replace") if hid_at > 0 else "?"
    return name, hid


def hidden_devices(table: bytes) -> list[tuple[int, str, str]]:
    out, i = [], table.find(STA)
    while i != -1:
        name, hid = device_name(table, i)
        out.append((i, name, hid))
        i = table.find(STA, i + 1)
    return out


def patch(table: bytes, names: set[str]) -> tuple[bytes, list[str]]:
    b = bytearray(table)
    done = []
    for at, name, _hid in hidden_devices(table):
        if name in names:
            p = at + 9                          # after 14 21 _STA 00 a0 15
            assert bytes(b[p:p + len(PREDICATE)]) == PREDICATE
            b[p:p + len(PREDICATE)] = PATCHED_PREDICATE
            done.append(name)
    if done:
        rev = struct.unpack_from("<I", b, 24)[0]
        struct.pack_into("<I", b, 24, rev + 1)
        b[9] = 0
        b[9] = (-sum(b)) & 0xFF
    return bytes(b), done


def cpio_newc(members: list[tuple[str, bytes]]) -> bytes:
    def entry(name: str, data: bytes, mode: int, ino: int) -> bytes:
        n = name.encode() + b"\x00"
        hdr = b"070701" + b"".join(f"{v:08x}".encode() for v in (
            ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(n), 0))
        pad = lambda x: b"\x00" * ((4 - x % 4) % 4)
        return hdr + n + pad(len(hdr) + len(n)) + data + pad(len(data))
    out, ino = b"", 1
    for d in ("kernel", "kernel/firmware", "kernel/firmware/acpi"):
        out += entry(d, b"", 0o040755, ino); ino += 1
    for name, data in members:
        out += entry(name, data, 0o100644, ino); ino += 1
    return out + entry("TRAILER!!!", b"", 0, 0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dump", type=Path, help="directory with dsdt.dat / ssdt*.dat (inventory) or DSDT / SSDT* (sysfs)")
    p.add_argument("--expose", default="", help="comma list of device names to make present, e.g. SSPM")
    p.add_argument("--out", type=Path, help="output directory for the patched tables and acpi-override.cpio")
    args = p.parse_args(argv)

    tables = sorted(f for f in args.dump.iterdir()
                    if f.is_file() and f.name.lower().split(".")[0].rstrip("0123456789") in ("dsdt", "ssdt"))
    wanted = {n.strip().upper() for n in args.expose.split(",") if n.strip()}
    members, exposed = [], set()
    for f in tables:
        data = f.read_bytes()
        if struct.unpack_from("<I", data, 4)[0] != len(data):
            print(f"{f.name}: header length does not match the file; skipped")
            continue
        found = hidden_devices(data)
        for at, name, hid in found:
            print(f"{f.name:<12} {name:<5} {hid:<10} _STA at {at:#07x}: hidden when _OSI(\"Windows 2022\")")
        if wanted:
            patched, done = patch(data, wanted)
            if done:
                exposed |= set(done)
                stem = f.name.split(".")[0].lower()
                members.append((f"kernel/firmware/acpi/{stem}.aml", patched))
                print(f"{f.name}: exposed {', '.join(done)}; OEM revision "
                      f"{struct.unpack_from('<I', data, 24)[0]} -> {struct.unpack_from('<I', patched, 24)[0]}")
    missing = wanted - exposed
    if missing:
        print(f"not found with the expected _STA: {', '.join(sorted(missing))}; nothing written")
        return 1
    if wanted:
        if not args.out:
            p.error("--expose needs --out")
        args.out.mkdir(parents=True, exist_ok=True)
        for name, data in members:
            (args.out / Path(name).name).write_bytes(data)
        (args.out / "acpi-override.cpio").write_bytes(cpio_newc(members))
        print(f"written: {args.out / 'acpi-override.cpio'} ({len(members)} table(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
