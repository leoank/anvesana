"""Node health: is this run as good as the machine's reference?

Reference, in order of preference:
  1. the committed baseline for the machine and OS (baselines/<machine>/<os>.json)
  2. the per-metric median of the last N earlier complete runs in the store
(or whatever --against names).

Per headline metric, the change in the "better" direction is compared with
the profile's tolerance (health.tolerance_pct, per-metric overrides):
  FAIL   worse by more than the tolerance
  WARN   worse by more than half of it
  OK     otherwise (large improvements are noted: they can also mean a broken measurement)
  SKIP   the benchmark's methodology VERSION differs, so values are not comparable
  MISSING a metric the reference has but this run did not produce

Telemetry under the same load is checked too: a GPU running hotter or
clocking lower than before is an early sign of cooling or power problems.

Exit code 1 if anything FAILs or is MISSING, else 0.
"""

from __future__ import annotations

import json
import statistics

from . import machine as machines, store
from .console import Table, num
from .records import ALL_PHASES, CONTEXT_UNITS, RunRecord, benchmark_of, is_headline

TEMP_WARN_C, TEMP_FAIL_C = 8.0, 15.0
CONTEXT_KEYS = [("os", "environment"), ("nvidia_driver", "environment"), ("power_profile", "environment"),
                ("on_ac_power", "environment"), ("ram_gb", "environment"), ("gpu_mem_total_gb", "environment"),
                ("duration_s", "settings"), ("framework_version", "settings")]


def add_arguments(p):
    p.add_argument("run", nargs="?", help="run reference (default: newest run of this host's machine)")
    p.add_argument("--against", help="reference run; 'median' for the rolling median of earlier runs")
    p.add_argument("--last", type=int, default=3, help="runs in the rolling median (default 3)")
    p.add_argument("--store", help="results store")
    p.add_argument("--json", help="also write the verdicts to this JSON file")


class Reference:
    def __init__(self, label: str, metrics: dict, versions: dict, telemetry: dict, context: dict):
        self.label, self.metrics, self.versions, self.telemetry, self.context = label, metrics, versions, telemetry, context

    @classmethod
    def from_run(cls, rec: RunRecord, label: str):
        return cls(label, {k: v["value"] for k, v in rec.metrics.items()}, rec.benchmark_versions(),
                   rec.phase_telemetry, _context(rec))

    @classmethod
    def median_of(cls, runs: list[RunRecord], versions: dict):
        """Median per metric over runs whose benchmark version matches the current one."""
        values: dict[str, list[float]] = {}
        temps: dict[str, dict[str, list[float]]] = {}
        for r in runs:
            rv = r.benchmark_versions()
            for name, m in r.metrics.items():
                b = benchmark_of(name)
                if rv.get(b) == versions.get(b):
                    values.setdefault(name, []).append(m["value"])
            for phase, stats in r.phase_telemetry.items():
                for k, v in stats.items():
                    temps.setdefault(phase, {}).setdefault(k, []).append(v)
        telemetry = {ph: {k: statistics.median(v) for k, v in st.items()} for ph, st in temps.items()}
        label = f"median of {len(runs)} runs ({runs[0].date} .. {runs[-1].date})"
        return cls(label, {k: statistics.median(v) for k, v in values.items()}, versions, telemetry,
                   _context(runs[-1]))


def _context(rec: RunRecord) -> dict:
    return {k: rec.data.get(section, {}).get(k) for k, section in CONTEXT_KEYS}


def pick_reference(profile, current: RunRecord, root, against: str | None, last: int) -> Reference | None:
    if against and against != "median":
        rec = store.resolve(against, root)
        return Reference.from_run(rec, f"{rec.run_id}")
    if not against:
        base = store.load_baseline(profile.id, current.os)
        if base:
            return Reference.from_run(base, f"baseline {base.run_id}")
    earlier = [r for r in store.list_runs(root, profile.id, os=current.os, include_partial=False)
               if r.data.get("started_at", "") < current.data.get("started_at", "")]
    if not earlier:
        return None
    return Reference.median_of(earlier[-last:], current.benchmark_versions())


def evaluate(profile, current: RunRecord, ref: Reference) -> list[dict]:
    verdicts = []
    benchmarks = current.data.get("settings", {}).get("benchmarks", [])
    # A benchmark that could not run is a failure whatever the reference holds
    # (a new profile entry, or an earlier run that never had it either).
    for b in benchmarks:
        if b.get("status") not in (None, "ok"):
            detail = b.get("reason") or f"exit code {b.get('exit_code')}"
            verdicts.append({"metric": f"{b['id']}:run", "unit": "", "current": None, "reference": None,
                             "status": "FAIL", "detail": f"{b['status']}: {detail}"})
    ran = {b["id"] for b in benchmarks if b.get("status") in (None, "ok")}
    cur_versions = current.benchmark_versions()
    names = [n for n in dict.fromkeys([*ref.metrics, *current.metrics]) if is_headline(n)]
    for name in names:
        bench = benchmark_of(name)
        cur = current.metrics.get(name)
        unit = (cur or {}).get("unit")
        if unit in CONTEXT_UNITS:
            continue
        ref_val = ref.metrics.get(name)
        v = {"metric": name, "unit": unit or "", "current": cur["value"] if cur else None, "reference": ref_val}
        if cur is None:
            if bench not in ran:
                continue  # not part of this run (--only / OS-specific)
            verdicts.append({**v, "status": "MISSING", "detail": "reference has it, this run did not produce it"})
            continue
        if ref_val is None:
            verdicts.append({**v, "status": "NEW", "detail": "no reference value"})
            continue
        if cur_versions.get(bench) != ref.versions.get(bench):
            verdicts.append({**v, "status": "SKIP",
                             "detail": f"{bench} v{ref.versions.get(bench)} -> v{cur_versions.get(bench)}: methodology changed"})
            continue
        tol = profile.tolerance_for(name)
        sign = 1 if cur.get("higher_is_better", True) else -1
        change = sign * (cur["value"] - ref_val) / abs(ref_val) * 100 if ref_val else 0.0
        status = "FAIL" if change < -tol else "WARN" if change < -tol / 2 else "OK"
        detail = f"{change:+.1f}% vs tolerance {tol:g}%"
        if change > 2 * tol:
            detail += " (large improvement: check the measurement)"
        verdicts.append({**v, "status": status, "change_pct": round(change, 2), "detail": detail})

    # Thermals and clocks per benchmark phase.
    for phase, stats in current.phase_telemetry.items():
        if phase in (ALL_PHASES, "idle", "cooldown", "cooldown_final") or phase not in ref.telemetry:
            continue
        rstats = ref.telemetry[phase]
        for key in ("peak_gpu_temp_c", "peak_soc_temp_c"):
            if key in stats and key in rstats:
                rise = stats[key] - rstats[key]
                status = "FAIL" if rise > TEMP_FAIL_C else "WARN" if rise > TEMP_WARN_C else "OK"
                verdicts.append({"metric": f"{phase}:{key}", "unit": "C", "current": stats[key],
                                 "reference": rstats[key], "status": status, "detail": f"{rise:+.1f} C"})
        key = "avg_gpu_sm_clock_mhz"
        if stats.get(key) and rstats.get(key):
            change = (stats[key] - rstats[key]) / rstats[key] * 100
            tol = profile.tolerance_pct
            status = "FAIL" if change < -tol else "WARN" if change < -tol / 2 else "OK"
            verdicts.append({"metric": f"{phase}:{key}", "unit": "MHz", "current": stats[key],
                             "reference": rstats[key], "status": status, "detail": f"{change:+.1f}%"})
    return verdicts


ORDER = {"FAIL": 0, "MISSING": 1, "WARN": 2, "SKIP": 3, "NEW": 4, "OK": 5}


def assess(profile, current: RunRecord, root, against: str | None = None, last: int = 3):
    """(reference or None, verdicts sorted worst first, overall "PASS"/"WARN"/"FAIL"/"NO REFERENCE")."""
    ref = pick_reference(profile, current, root, against, last)
    if ref is None:
        return None, [], "NO REFERENCE"
    verdicts = sorted(evaluate(profile, current, ref), key=lambda v: (ORDER[v["status"]], v["metric"]))
    statuses = {v["status"] for v in verdicts}
    overall = "FAIL" if statuses & {"FAIL", "MISSING"} else "WARN" if "WARN" in statuses else "PASS"
    return ref, verdicts, overall


def check(profile, current: RunRecord, root, against: str | None = None, last: int = 3, log=print,
          json_path: str | None = None) -> int:
    ref, verdicts, verdict = assess(profile, current, root, against, last)
    log(f"\nHealth check: {current.run_id}\n")
    if ref is None:
        log("  No baseline and no earlier runs: nothing to compare yet. "
            "Promote a good run with `bench baseline promote <run>`.\n")
        return 0
    log(f"  Reference: {ref.label}\n")
    cur_ctx = _context(current)
    for key, _ in CONTEXT_KEYS:
        if cur_ctx.get(key) != ref.context.get(key):
            log(f"  note: {key} differs: {ref.context.get(key)!r} -> {cur_ctx.get(key)!r}\n")
    for note in current.data.get("preflight", []):
        log(f"  note: preflight: {note}\n")

    t = Table("Health", ["metric", "unit", "reference", "current", "status", "detail"])
    for v in verdicts:
        t.add(v["metric"], v["unit"], num(v["reference"]), num(v["current"]), v["status"], v["detail"])
    log(t.text() + "\n")
    counts = {s: sum(v["status"] == s for v in verdicts) for s in ORDER}
    bad = counts["FAIL"] + counts["MISSING"]
    log(f"\n  {verdict}: " + ", ".join(f"{n} {s}" for s, n in counts.items() if n) + "\n")
    if json_path:
        with open(json_path, "w") as f:
            json.dump({"run_id": current.run_id, "reference": ref.label, "verdict": verdict,
                       "counts": counts, "checks": verdicts}, f, indent=2)
    return 1 if bad else 0


def main(args) -> int:
    root = store.store_root(args.store)
    if args.run:
        current = store.resolve(args.run, root)
        profile = machines.resolve(current.machine_id)
    else:
        profile = machines.resolve(None)
        current = store.resolve(profile.id, root)
    return check(profile, current, root, args.against, args.last, log=lambda s: print(s, end=""),
                 json_path=args.json)
