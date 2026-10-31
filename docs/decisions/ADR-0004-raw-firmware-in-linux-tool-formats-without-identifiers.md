# ADR-0004: Keep raw firmware in formats Linux tools read, and leave out keys and serial numbers

Status: accepted
Date: 2026-10-30

## Context
Bring-up engineers work on the ACPI tables, SMBIOS and EDIDs with Linux tools (`iasl`,
`dmidecode`, `edid-decode`), not with our JSON. Snapshots go to a shared results store and
may be published. Some firmware data identifies a unit or a person:
- the MSDM table holds the OEM Windows product key;
- SMBIOS and EDID carry serial numbers and UUIDs;
- MSI Center's registry holds the unit serial, barcode, product key and Windows user names.

Alternatives considered:
- **Parsed JSON only.** Loses detail that tools like `iasl` decode better than we could.
- **Raw files exactly as the OS exposes them.** Windows gives SMBIOS with a private header,
  which no Linux tool reads.
- **Redact serials inside the raw binaries.** Breaks checksums and makes the files lie
  about the firmware.

## Decision
- ACPI tables are saved as `acpi/<sig>[n].dat` (acpixtract naming), so
  `iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat` works on them.
- SMBIOS is saved as `smbios.bin` in `dmidecode --dump-bin` layout: a synthesized `_SM3_`
  entry point and the table at offset 0x20.
- EDIDs are saved as `display/<model>.edid`, and Linux HID descriptors as `hid/*.bin`.
- MSDM is never saved.
- The JSON summaries (SMBIOS, EDID) leave out serial numbers and UUIDs, and the vendor
  settings drop serials, barcodes, product keys and user names by an explicit name list.

## Consequences
- The raw `smbios.bin`, EDIDs and some instance ids still contain serials; the results store
  must stay internal.
- The serial filter is an allow-by-default list: a new vendor key with a serial in an
  unexpected name would get through. The first version leaked `OS_Product_Key` through
  substring matching, which is why it is now a list of exact names.
