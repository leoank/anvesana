# ADR-0008: Probe vendor firmware interfaces read-only, from a separate elevated script

Status: accepted
Date: 2026-10-30

## Context
MSI Center S drives power modes, fans, battery and the keyboard through the ACPI-WMI class
`MSI_ACPI` (method block `ABBC0F6E-8EA1-11D1-00A0-C90629100000`). Its methods include
`Get/Set_EC`, `_Fan`, `_Thermal`, `_Power` and `_AP`. Mapping which EC bytes back which
mode is essential for Linux, but:
- the class needs administrator rights;
- the mapping needs a person to switch modes in MSI Center between reads;
- a `Set_*` call with a wrong byte layout writes the embedded controller.

Alternatives considered:
- **Fold it into `bench inventory`.** That would make collection need admin and a person,
  and tie a generic tool to one vendor.
- **Call `Set_*` to map the layout directly.** Faster, but it risks the EC.
- **Install a capture driver to watch MSI Center's traffic.** Not needed for WMI: the
  getters before and after each mode change show it.

## Decision
`scripts/msi-admin-probe.ps1` runs elevated and is guided:
1. It dumps every `Get_*` method, with all-zero input, or no input for `Get_WMI`, `Get_EC`
   and `Get_EC2`.
2. It records MSI Center's own registry view and the power plan next to each dump.
3. It prompts the person to switch modes, then labels a new dump for each.
4. It runs an optional USB ETW trace while the lighting changes.

It never calls a `Set_*` method. Results are interpreted in the bring-up log.

## Consequences
- The EC shift-mode byte (`Get_AP` byte 3: `c1` balanced, `c2` eco, `c4` performance, `c5`
  boost) and the EC firmware string were found with no writes.
- Mapping needs a person at the machine, and its findings are only as good as the modes
  they selected.
- Writing EC values from Linux still needs a separate, deliberate test.
