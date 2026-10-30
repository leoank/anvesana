"""Print one run in full: what was measured, how, on what, and under which conditions.

  bench show                          newest run of this host's machine
  bench show bbaum-pc-7@baseline      any run reference (see store.py)
  bench show dgx-01 --metrics "tensor.*" --no-telemetry
"""

from __future__ import annotations

import fnmatch

from . import machine as machines, store
from .console import RULE, Table, num
from .records import ALL_PHASES, RunRecord, benchmark_of, is_headline

ENV_KEYS = ["os", "hostname", "platform", "kernel", "system_product", "bios", "cpu", "logical_cpus", "ram_gb", "gpu_mem_total_gb",
            "nvidia_driver", "nvrtc", "power_profile", "on_ac_power", "gpu_power_limit_w", "gpu_max_sm_clock_mhz",
            "python"]
SUBMETRICS = [("avg_power", "avg W", 1), ("efficiency", "per W", 2), ("avg_sm_clock", "SM MHz", 0)]
# Telemetry columns: (phase_telemetry key, header, digits). The graphics clock and
# hottest-zone columns are left out; they duplicate SM clock and SoC temp here.
TELEMETRY = [("avg_gpu_power_w", "GPU W", 1), ("peak_gpu_power_w", "peak W", 1),
             ("avg_gpu_sm_clock_mhz", "SM MHz", 0), ("peak_gpu_temp_c", "GPU C", 0),
             ("peak_soc_temp_c", "SoC C", 0), ("avg_cpu_util_pct", "CPU %", 0),
             ("avg_cpu_freq_mhz", "CPU MHz", 0), ("peak_ram_used_gb", "RAM GB", 1), ("gpu_energy_wh", "GPU Wh", 3)]


def add_arguments(p):
    p.add_argument("run", nargs="?", help="run reference (default: newest run of this host's machine)")
    p.add_argument("--metrics", help="comma-separated globs, e.g. 'tensor.*,disk.*' (default: all)")
    p.add_argument("--no-telemetry", action="store_true", help="omit the per-phase sensor summary")
    p.add_argument("--no-environment", action="store_true", help="omit settings and environment")
    p.add_argument("--store", help="results store")


def _profile_for(rec: RunRecord):
    try:
        return machines.resolve(rec.machine_id)
    except SystemExit:
        return None  # run of a machine whose profile is not in this checkout


def main(args) -> int:
    root = store.store_root(args.store)
    rec = store.resolve(args.run or machines.resolve(None).id, root)
    profile = _profile_for(rec)
    d = rec.data
    s = d.get("settings", {})

    print(RULE)
    print(f" {rec.run_id}")
    print(f" {d.get('machine', {}).get('description', '')}")
    print(RULE)
    print(f" started   {d.get('started_at', '?')}   ({d.get('duration_s', '?')} s total)")
    print(f" status    {rec.status}" + (f"   failed: {', '.join(d['failures'])}" if d.get("failures") else ""))
    if rec.tag:
        print(f" tag       {rec.tag}")
    if d.get("baseline"):
        print(f" baseline  promoted {d['baseline'].get('promoted_at')} from {d['baseline'].get('source_run_id')}")
    for note in d.get("preflight", []):
        print(f" !! {note}")
    for note in d.get("corrections", []):
        print(f" correction: {note}")

    if not args.no_environment:
        print(f"\n settings  {s.get('duration_s', '?')} s per test, {s.get('cooldown_s', '?')} s cooldown, "
              f"framework {s.get('framework_version', '?')}"
              + (f", commit {s['git_commit'][:8]}{' (dirty)' if s.get('git_dirty') else ''}" if s.get("git_commit") else ""))
        t = Table("Benchmarks run", ["id", "module", "version", "status", "time", "args"])
        for b in s.get("benchmarks", []):
            t.add(b["id"], b.get("module", ""), b.get("version") or "-", b.get("status", "?"),
                  f"{b['elapsed_s']:.0f}s" if b.get("elapsed_s") else "-",
                  ", ".join(f"{k}={v}" for k, v in (b.get("args") or {}).items()) or b.get("reason", ""))
        print(t.text())
        env = d.get("environment", {})
        t = Table("Environment", ["field", "value"])
        for k in ENV_KEYS:
            if env.get(k) is not None:
                t.add(k, env[k])
        if env.get("gpu"):
            t.add("gpu", f"{env['gpu'].get('name')} (cc {env['gpu'].get('compute_capability')}, "
                         f"{env['gpu'].get('sm_count')} SMs)")
        print(t.text())

    patterns = [p.strip() for p in args.metrics.split(",")] if args.metrics else None
    metrics = rec.metrics
    expected = profile.expected if profile else {}
    t = Table("Metrics", ["metric", "value", "unit", "% of spec", *(h for _, h, _ in SUBMETRICS)])
    current_bench = None
    for name, m in metrics.items():
        if not is_headline(name) or (patterns and not any(fnmatch.fnmatch(name, p) for p in patterns)):
            continue
        if current_bench and benchmark_of(name) != current_bench:
            t.add("", "", "", "", *("" for _ in SUBMETRICS))  # blank row between benchmarks
        current_bench = benchmark_of(name)
        spec = expected.get(name)
        subs = []
        for key, _, digits in SUBMETRICS:
            sub = metrics.get(f"{name}.{key}")
            subs.append(num(sub["value"], digits) if sub else "")
        t.add(name, num(m["value"]), m["unit"], f"{100 * m['value'] / spec:.0f}%" if spec else "", *subs)
    print(t.text())

    if not args.no_telemetry and rec.phase_telemetry:
        cols = [c for c in TELEMETRY if any(c[0] in v for v in rec.phase_telemetry.values())]
        t = Table("Telemetry per phase (averages and peaks)", ["phase", *(h for _, h, _ in cols)])
        phases = [p for p in rec.phase_telemetry if p not in ("cooldown", "cooldown_final", ALL_PHASES)]
        for ph in phases + [ALL_PHASES]:
            stats = rec.phase_telemetry.get(ph, {})
            t.add("whole run" if ph == ALL_PHASES else ph, *(num(stats.get(k), d) for k, _, d in cols))
        print(t.text())
    return 0
