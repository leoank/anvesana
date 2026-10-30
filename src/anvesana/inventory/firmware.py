"""OS-neutral parsing of what firmware hands the OS: ACPI tables, SMBIOS, ARM64 CPU ID registers.

The raw bytes are saved next to the snapshot (acpi/*.dat, smbios.bin) so Linux tools can
work on them directly:

  iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat     # disassemble the namespace a Linux driver binds against
  dmidecode --from-dump smbios.bin
"""

from __future__ import annotations

import struct
import zlib

# MSDM holds the OEM Windows product key; it says nothing about the hardware.
SKIP_TABLES = {"MSDM"}

_ACPI_HEADER = struct.Struct("<4sIBB6s8sI4sI")


def acpi_header(data: bytes) -> dict:
    sig, length, rev, _checksum, oem, oem_table, oem_rev, creator, creator_rev = _ACPI_HEADER.unpack_from(data)
    return {"signature": _text(sig), "length": length, "revision": rev, "oem_id": _text(oem),
            "oem_table_id": _text(oem_table), "oem_revision": oem_rev, "creator_id": _text(creator),
            "creator_revision": creator_rev, "crc32": f"{zlib.crc32(data[:length]):08x}"}


def save_acpi_tables(tables: list[bytes], out_dir) -> list[dict]:
    """Writes each table as acpi/<sig>[n].dat (acpixtract's naming) and returns their headers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    headers = []
    for data in tables:
        if len(data) < _ACPI_HEADER.size:
            continue
        h = acpi_header(data)
        if h["signature"] in SKIP_TABLES:
            continue
        n = seen.get(h["signature"], 0)
        seen[h["signature"]] = n + 1
        name = f"{h['signature'].lower()}{n or ''}.dat"
        (out_dir / name).write_bytes(data[:h["length"]])
        headers.append({**h, "file": f"acpi/{name}"})
    return headers


# ------------------------------------------------------------------ SMBIOS

def smbios_dump(table: bytes, major: int, minor: int, docrev: int = 0) -> bytes:
    """``dmidecode --dump-bin`` layout: a 64-bit (_SM3_) entry point at 0, the table at 0x20."""
    ep = bytearray(struct.pack("<5sBBBBBBBIQ", b"_SM3_", 0, 0x18, major, minor, docrev, 1, 0, len(table), 0x20))
    ep[5] = (-sum(ep)) & 0xFF
    return bytes(ep).ljust(0x20, b"\0") + table


def smbios_structures(table: bytes):
    """Yields (type, formatted area, strings) for each structure in a raw SMBIOS table."""
    i = 0
    while i + 4 <= len(table):
        stype, length = table[i], table[i + 1]
        if length < 4:
            return
        formatted = table[i:i + length]
        end = table.find(b"\0\0", i + length)
        if end < 0:
            return
        strings = [s.decode("ascii", "replace").strip() for s in table[i + length:end].split(b"\0") if s]
        yield stype, formatted, strings
        if stype == 127:  # end-of-table
            return
        i = end + 2


def smbios_summary(table: bytes) -> dict:
    """BIOS, system, board, processor and memory devices. Serial numbers and UUIDs are left out:
    snapshots go to a shared store and serials are no use for bring-up."""
    out: dict = {"memory_devices": []}
    for stype, f, strings in smbios_structures(table):
        s = lambda off: _smbios_string(f, strings, off)  # noqa: E731
        if stype == 0:
            out["bios"] = {"vendor": s(0x04), "version": s(0x05), "date": s(0x08)}
            if len(f) > 0x15:
                out["bios"]["release"] = f"{f[0x14]}.{f[0x15]}"
            if len(f) > 0x17 and f[0x16] != 0xFF:
                out["bios"]["ec_firmware"] = f"{f[0x16]}.{f[0x17]}"
        elif stype == 1:
            out["system"] = {"manufacturer": s(0x04), "product": s(0x05), "version": s(0x06),
                             "sku": s(0x19), "family": s(0x1A)}
        elif stype == 2:
            out["baseboard"] = {"manufacturer": s(0x04), "product": s(0x05), "version": s(0x06)}
        elif stype == 4:
            out.setdefault("processors", []).append({
                "socket": s(0x04), "manufacturer": s(0x07), "version": s(0x10),
                "max_mhz": _word(f, 0x14), "current_mhz": _word(f, 0x16),
                "cores": _word(f, 0x2A) if len(f) > 0x2B else (f[0x23] if len(f) > 0x23 else None),
                "threads": _word(f, 0x2E) if len(f) > 0x2F else (f[0x25] if len(f) > 0x25 else None)})
        elif stype == 17:
            size = _word(f, 0x0C)
            if not size or size == 0xFFFF:
                continue  # empty slot / unknown
            # bit 15 set: KB granularity; 0x7FFF: real size (MB) is in the extended field
            mb = _dword(f, 0x1C) if size == 0x7FFF else (size & 0x7FFF) // 1024 if size & 0x8000 else size
            out["memory_devices"].append({
                "locator": s(0x10), "size_mb": mb, "type": _MEMORY_TYPES.get(f[0x12] if len(f) > 0x12 else 0),
                "speed_mts": _word(f, 0x15), "configured_mts": _word(f, 0x20),
                "manufacturer": s(0x17), "part_number": s(0x1A)})
    return out


_MEMORY_TYPES = {0x1A: "DDR4", 0x1E: "LPDDR4", 0x22: "DDR5", 0x23: "LPDDR5"}


def _smbios_string(f: bytes, strings: list[str], off: int):
    if off >= len(f) or f[off] == 0 or f[off] > len(strings):
        return None
    return strings[f[off] - 1] or None


def _word(f: bytes, off: int):
    return struct.unpack_from("<H", f, off)[0] if off + 2 <= len(f) else None


def _dword(f: bytes, off: int):
    return struct.unpack_from("<I", f, off)[0] if off + 4 <= len(f) else None


def _text(b: bytes) -> str:
    return b.decode("ascii", "replace").rstrip("\0 ")


# ------------------------------------------------------------------ ARM64 CPUs

IMPLEMENTERS = {0x41: "Arm", 0x4E: "NVIDIA", 0x51: "Qualcomm", 0x61: "Apple", 0x6D: "Microsoft"}
# Linux arch/arm64/include/asm/cputype.h names, for the parts likely in this fleet.
ARM_PARTS = {0xD0C: "Neoverse-N1", 0xD40: "Neoverse-V1", 0xD49: "Neoverse-N2", 0xD4F: "Neoverse-V2",
             0xD80: "Cortex-A520", 0xD81: "Cortex-A720", 0xD82: "Cortex-X4", 0xD84: "Neoverse-V3",
             0xD85: "Cortex-X925", 0xD87: "Cortex-A725", 0xD8E: "Neoverse-N3"}

# System register names by (op1, CRn, CRm, op2) with op0 = 3. Windows exposes ID registers
# per core as "CP <encoding>" registry values; Linux spells unnamed ones S3_<op1>_C<n>_C<m>_<op2>.
SYSREGS = {(0, 0, 0, 0): "MIDR_EL1", (0, 0, 0, 5): "MPIDR_EL1", (0, 0, 0, 6): "REVIDR_EL1",
           (0, 0, 4, 0): "ID_AA64PFR0_EL1", (0, 0, 4, 1): "ID_AA64PFR1_EL1", (0, 0, 4, 4): "ID_AA64ZFR0_EL1",
           (0, 0, 4, 5): "ID_AA64SMFR0_EL1", (0, 0, 5, 0): "ID_AA64DFR0_EL1", (0, 0, 5, 1): "ID_AA64DFR1_EL1",
           (0, 0, 5, 4): "ID_AA64AFR0_EL1", (0, 0, 5, 5): "ID_AA64AFR1_EL1", (0, 0, 6, 0): "ID_AA64ISAR0_EL1",
           (0, 0, 6, 1): "ID_AA64ISAR1_EL1", (0, 0, 6, 2): "ID_AA64ISAR2_EL1", (0, 0, 7, 0): "ID_AA64MMFR0_EL1",
           (0, 0, 7, 1): "ID_AA64MMFR1_EL1", (0, 0, 7, 2): "ID_AA64MMFR2_EL1", (3, 0, 0, 1): "CTR_EL0",
           (3, 0, 0, 7): "DCZID_EL0"}


def sysreg_name(encoding: int) -> str:
    """Windows "CP 4020" -> ID_AA64PFR0_EL1 (encoding = op0[0]:op1:CRn:CRm:op2 packed into 15 bits)."""
    op1, crn, crm, op2 = (encoding >> 11) & 7, (encoding >> 7) & 0xF, (encoding >> 3) & 0xF, encoding & 7
    return SYSREGS.get((op1, crn, crm, op2), f"S3_{op1}_C{crn}_C{crm}_{op2}")


def decode_midr(midr: int) -> dict:
    implementer, part = (midr >> 24) & 0xFF, (midr >> 4) & 0xFFF
    name = ARM_PARTS.get(part) if implementer == 0x41 else None
    return {"midr": f"0x{midr:08x}", "implementer": IMPLEMENTERS.get(implementer, f"0x{implementer:02x}"),
            "part": f"0x{part:03x}", "core": name or f"part 0x{part:03x}",
            "revision": f"r{(midr >> 20) & 0xF}p{midr & 0xF}"}


def cpu_clusters(cores: list[dict]) -> list[dict]:
    """Groups per-core records by core type (MIDR): the big/little layout the Linux scheduler,
    cpufreq and the PPTT-derived topology all have to agree with."""
    groups: dict[str, dict] = {}
    for c in cores:
        g = groups.setdefault(c.get("midr", "?"), {**{k: c.get(k) for k in ("core", "midr", "revision")},
                                                    "cpus": [], "max_mhz": c.get("max_mhz")})
        g["cpus"].append(c["cpu"])
    return [{**g, "cpus": _ranges(sorted(g["cpus"])), "count": len(g["cpus"])} for g in groups.values()]


def _ranges(nums: list[int]) -> str:
    """[0, 1, 2, 4, 5] -> "0-2,4-5" (Linux cpulist format)."""
    out, start = [], None
    for i, n in enumerate(nums):
        if start is None:
            start = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(f"{start}" if start == n else f"{start}-{n}")
            start = None
    return ",".join(out)
