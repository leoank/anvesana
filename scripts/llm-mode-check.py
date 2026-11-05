"""Exit 0 only if the Windows power state matches what a sweep run is labelled with.

    uv run python scripts/llm-mode-check.py --msi ECO-Silent --energy-saver off --power dc

Reads the same fields `bench run` records (framework/environment.py: MSI Center
scenario, Energy Saver, Windows overlay, AC/battery) and prints them, so a mode
sweep never runs under the wrong label. Changing the mode is left to the person
at the machine (MSI Center, Quick Settings).
"""

from __future__ import annotations

import argparse
import sys

from anvesana.framework import environment


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--msi", required=True, help="ECO-Silent, Balanced, Performance, Performance Boost, AI Engine")
    p.add_argument("--energy-saver", choices=["on", "off"], required=True)
    p.add_argument("--power", choices=["ac", "dc"], required=True)
    args = p.parse_args(argv)

    profile = environment._power_profile()
    on_ac = environment._on_ac_power()
    print(f"{profile}, {'AC' if on_ac else 'battery'}")
    fields = dict(part.split("=", 1) for part in profile.split(", ") if "=" in part)
    problems = []
    if fields.get("msi", "").split(" (")[0] != args.msi:
        problems.append(f"MSI scenario is {fields.get('msi')!r}, want {args.msi!r}")
    if fields.get("energy_saver") != args.energy_saver:
        problems.append(f"Energy Saver is {fields.get('energy_saver')!r}, want {args.energy_saver!r}")
    if on_ac is not None and on_ac != (args.power == "ac"):
        problems.append(f"on {'AC' if on_ac else 'battery'}, want {args.power}")
    for problem in problems:
        print("MISMATCH: " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
