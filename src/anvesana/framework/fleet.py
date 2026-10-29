"""Fleet overview: the latest health of every machine in the results store.

  anvesana fleet [--stale-days 35] [--store PATH] [--json out.json]

One row per machine and OS with its newest run, that run's age and status,
and its health verdict against the machine's reference (see health.py).
Machines that have a profile but no recent run are STALE: a node that stopped
reporting is a health problem too. Exit code 1 if any row FAILs or is STALE.
"""

from __future__ import annotations

import datetime as dt
import json

from . import health, machine as machines, store
from .console import Table


def add_arguments(p):
    p.add_argument("--stale-days", type=int, default=35, help="flag machines whose newest run is older (default 35)")
    p.add_argument("--store", help="results store")
    p.add_argument("--json", help="also write the overview to this JSON file")


def main(args) -> int:
    root = store.store_root(args.store)
    profiles = {p.id: p for p in machines.all_profiles()}
    runs = store.list_runs(root)
    latest: dict[tuple[str, str], object] = {}
    for r in runs:  # oldest first, so the last one wins
        latest[(r.machine_id, r.os)] = r
    now = dt.datetime.now().astimezone()

    rows = []
    for (machine_id, os), rec in sorted(latest.items()):
        age = (now - rec.started_at).days if rec.started_at else None
        profile = profiles.get(machine_id)
        if profile is None:
            verdict, worst = "NO PROFILE", ""
        else:
            _, verdicts, verdict = health.assess(profile, rec, root)
            worst = ", ".join(f"{v['metric']} {v['status']}" for v in verdicts
                              if v["status"] in ("FAIL", "MISSING", "WARN"))
        stale = age is not None and age > args.stale_days
        rows.append({"machine": machine_id, "os": os, "run_id": rec.run_id, "date": rec.date, "age_days": age,
                     "status": rec.status, "health": verdict, "stale": stale, "issues": worst})
    reported = {m for m, _ in latest}
    for machine_id in sorted(set(profiles) - reported):
        rows.append({"machine": machine_id, "os": "-", "run_id": None, "date": "never", "age_days": None,
                     "status": "-", "health": "-", "stale": True, "issues": "no runs in the store"})

    t = Table(f"Fleet ({len(profiles)} profiles, store {root})",
              ["machine", "os", "last run", "age", "run status", "health", "issues"])
    for r in rows:
        age = "-" if r["age_days"] is None else f"{r['age_days']}d"
        health_col = r["health"] + (" STALE" if r["stale"] else "")
        issues = r["issues"] if len(r["issues"]) <= 70 else r["issues"][:67] + "..."
        t.add(r["machine"], r["os"], r["date"], age, r["status"], health_col, issues)
    print(t.text())

    bad = [r for r in rows if r["health"] == "FAIL" or r["stale"]]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} healthy and current" + (f"; attention: "
          f"{', '.join(sorted({r['machine'] for r in bad}))}" if bad else ""))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=2)
    return 1 if bad else 0
