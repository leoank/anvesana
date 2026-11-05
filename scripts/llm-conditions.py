"""Run `bench run --only llm` once per power condition, checking the condition first.

    uv run python scripts/llm-conditions.py --label npcf-on --conditions ac,dc [--models gpt-oss-20b]

For each condition it asks you to plug in or unplug the charger, waits until
the battery reports that state (psutil; in WSL, where Windows' battery is not
visible, it asks you to confirm instead), then runs the benchmark tagged
`<label>-<condition>`. On battery it refuses to start below --min-battery
percent so a run never ends in a flat battery. The telemetry's on_ac column
records the state for every sample, so a charger pulled mid-run shows up.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import psutil

WANT = {"ac": True, "dc": False}


def battery():
    try:
        return psutil.sensors_battery()
    except Exception:
        return None


def wait_for(condition: str, timeout_s: float) -> bool:
    want = WANT[condition]
    b = battery()
    if b is None:
        answer = input(f"No battery visible here. Is the laptop {'plugged in' if want else 'on battery'}? [y/N] ")
        return answer.strip().lower() == "y"
    if b.power_plugged != want:
        print(f"Please {'plug in the charger' if want else 'unplug the charger'} now ...", flush=True)
        t0 = time.monotonic()
        while (b := battery()) is not None and b.power_plugged != want:
            if time.monotonic() - t0 > timeout_s:
                print("timed out waiting for the power state")
                return False
            time.sleep(1)
    print(f"power: {'AC' if b.power_plugged else 'battery'}, {b.percent:.0f} %")
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True, help="what else is set, e.g. npcf-on, npcf-off, wsl, nixos-stock")
    p.add_argument("--conditions", default="ac,dc", help="comma list of: ac, dc (run in this order)")
    p.add_argument("--models", default="gpt-oss-20b,gpt-oss-120b")
    p.add_argument("--min-battery", type=float, default=50.0, help="refuse a battery run below this percent")
    p.add_argument("--settle-s", type=float, default=60.0, help="wait after a power change before running")
    p.add_argument("--timeout-s", type=float, default=600.0)
    p.add_argument("extra", nargs=argparse.REMAINDER, help="passed to `bench run` after --")
    args = p.parse_args(argv)

    for condition in [c.strip() for c in args.conditions.split(",") if c.strip()]:
        if condition not in WANT:
            p.error(f"unknown condition '{condition}'")
        if not wait_for(condition, args.timeout_s):
            return 1
        b = battery()
        if condition == "dc" and b is not None and b.percent < args.min_battery:
            print(f"battery at {b.percent:.0f} % (< {args.min_battery:.0f} %): charge first")
            return 1
        print(f"settling {args.settle_s:.0f} s so the firmware applies the new power state ...", flush=True)
        time.sleep(args.settle_s)
        extra = [a for a in args.extra if a != "--"]
        cmd = ["run", "--only", "llm", "--tag", f"{args.label}-{condition}", "--set", f"llm.models={args.models}",
               *extra]
        print("$ bench " + " ".join(cmd), flush=True)
        rc = subprocess.call([sys.executable, "-m", "anvesana", *cmd])
        if rc not in (0, 1):  # 1 = health FAIL, still a result
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
