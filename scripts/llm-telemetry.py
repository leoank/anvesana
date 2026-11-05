"""Busy-only GPU power, clock and temperature for `bench llm` runs, from telemetry.csv.

    uv run python scripts/llm-telemetry.py <run dir> [<run dir> ...] [--busy 50]

The monitor samples the whole `llm` phase, including model loading. This keeps the
samples where GPU utilisation is at least --busy percent, splits them into
contiguous segments (each llama-bench call is one: prefill first, then decode),
and prints per-segment averages next to the run's tok/s. Used to recompute runs
made before suite/llm.py filtered its own samples (2026-11-05).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def segments(rows: list[dict], busy: float, gap_s: float) -> list[list[dict]]:
    out, cur, last = [], [], None
    for r in rows:
        if r["phase"] != "llm" or not r["gpu_util_pct"] or float(r["gpu_util_pct"]) < busy:
            continue
        t = float(r["elapsed_sec"])
        if last is not None and t - last > gap_s:
            out.append(cur)
            cur = []
        cur.append(r)
        last = t
    if cur:
        out.append(cur)
    return out


def avg(rows: list[dict], key: str) -> float | None:
    vals = [float(r[key]) for r in rows if r.get(key)]
    return sum(vals) / len(vals) if vals else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--busy", type=float, default=50.0, help="minimum GPU utilisation in percent")
    p.add_argument("--gap", type=float, default=5.0, help="seconds without a busy sample that end a segment")
    p.add_argument("--json", action="store_true", help="print one JSON object per run")
    args = p.parse_args(argv)

    for run in args.runs:
        rows = list(csv.DictReader(open(run / "telemetry.csv", newline="")))
        record = json.load(open(run / "run.json"))
        metrics = record.get("metrics", {})
        segs = segments(rows, args.busy, args.gap)
        result = {"run": run.name, "power_profile": record["environment"].get("power_profile"),
                  "on_ac": record["environment"].get("on_ac_power"), "segments": []}
        for seg in segs:
            mask = 0
            for r in seg:
                mask |= int(float(r["gpu_throttle_reasons"] or 0))
            result["segments"].append({
                "samples": len(seg), "seconds": round(float(seg[-1]["elapsed_sec"]) - float(seg[0]["elapsed_sec"]), 1),
                "power_w": round(avg(seg, "gpu_power_w") or 0, 1), "sm_clock_mhz": round(avg(seg, "gpu_sm_clock_mhz") or 0),
                "temp_max_c": max(float(r["gpu_temp_c"]) for r in seg if r["gpu_temp_c"]),
                "throttle_mask": mask, "on_ac": sorted({r.get("on_ac", "") for r in seg}),
            })
        tps = {k: v["value"] for k, v in metrics.items() if k.count(".") == 1 and k.startswith("llm.")}
        result["tok_s"] = tps
        if args.json:
            print(json.dumps(result))
            continue
        print(f"{run.name}\n  {result['power_profile']}, {'AC' if result['on_ac'] else 'battery'}; "
              + ", ".join(f"{k.split('.', 1)[1]} {v:.1f}" for k, v in tps.items()))
        for i, s in enumerate(result["segments"]):
            print(f"  segment {i}: {s['samples']} samples / {s['seconds']} s, {s['power_w']} W, "
                  f"{s['sm_clock_mhz']} MHz SM, {s['temp_max_c']:.0f} C max, mask {s['throttle_mask']}, on_ac {s['on_ac']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
