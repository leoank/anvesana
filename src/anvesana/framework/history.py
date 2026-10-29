"""Trends: one machine's headline metrics across its stored runs.

  bench history                      this host's machine, last 6 runs
  bench history dgx-01 --metrics "tensor.*,cublaslt.*" --last 12 --csv trend.csv

Rows are metrics, columns are runs (oldest -> newest), and the last column is
the newest run's change vs the median of the earlier ones shown. Values
measured with a different benchmark VERSION than the newest run are shown in
brackets and left out of the median.
"""

from __future__ import annotations

import csv
import fnmatch
import statistics

from . import machine as machines, store
from .console import Table
from .records import CONTEXT_UNITS, benchmark_of, is_headline


def add_arguments(p):
    p.add_argument("machine", nargs="?", help="machine id (default: this host's)")
    p.add_argument("--metrics", help="comma-separated globs, e.g. 'tensor.*,disk.seq_*' (default: all headline)")
    p.add_argument("--last", type=int, default=6, help="number of runs (default 6)")
    p.add_argument("--os", help="only runs on this OS (windows / linux)")
    p.add_argument("--include-partial", action="store_true", help="include runs where some benchmark failed")
    p.add_argument("--store", help="results store")
    p.add_argument("--csv", help="also write the full series to this CSV")


def main(args) -> int:
    machine_id = args.machine or machines.resolve(None).id
    root = store.store_root(args.store)
    runs = store.list_runs(root, machine_id, os=args.os, include_partial=args.include_partial)[-args.last:]
    if not runs:
        print(f"No runs for '{machine_id}' in {root}")
        return 1
    patterns = [p.strip() for p in args.metrics.split(",")] if args.metrics else None
    names = []
    for r in runs:
        for n, m in r.metrics.items():
            if n in names or not is_headline(n) or m["unit"] in CONTEXT_UNITS:
                continue
            if patterns and not any(fnmatch.fnmatch(n, p) for p in patterns):
                continue
            names.append(n)

    newest_versions = runs[-1].benchmark_versions()
    headers = ["metric", "unit"] + [f"{r.date} {r.os[:3]}{' ' + r.tag if r.tag else ''}" for r in runs] + ["latest vs median"]
    t = Table(f"History: {machine_id} ({len(runs)} runs)", headers)
    rows = []
    for n in names:
        bench = benchmark_of(n)
        unit, cells, comparable = "", [], []
        for r in runs:
            m = r.metrics.get(n)
            if not m:
                cells.append("-")
                continue
            unit = m["unit"]
            same = r.benchmark_versions().get(bench) == newest_versions.get(bench)
            cells.append(f"{m['value']:,.2f}" if same else f"[{m['value']:,.2f}]")
            if same and r is not runs[-1]:
                comparable.append(m["value"])
        latest = runs[-1].metrics.get(n)
        trend = ""
        if latest and comparable:
            med = statistics.median(comparable)
            if med:
                d = (latest["value"] - med) / abs(med) * 100
                better = (d > 0) == latest.get("higher_is_better", True)
                trend = f"{d:+.1f}%" + ("" if abs(d) < 1 else " better" if better else " worse")
        t.add(n, unit, *cells, trend)
        rows.append([n, unit, *[(r.metrics.get(n) or {}).get("value", "") for r in runs]])
    print(t.text())

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "unit"] + [r.run_id for r in runs])
            w.writerows(rows)
        print(f"\nCSV written to {args.csv}")
    return 0
