"""Side-by-side comparison of any two runs: same machine across months or
OSes, or two machines. Accepts any run reference (see store.py), including
committed baselines and legacy telemetry CSVs.
"""

from __future__ import annotations

from pathlib import Path

from . import store
from .console import Table, num
from .records import ALL_PHASES, STAT_HIGHER_IS_BETTER, RunRecord, benchmark_of

SYSTEM_KEYS = ["hostname", "platform", "nvidia_driver", "power_profile", "on_ac_power", "ram_gb", "gpu_mem_total_gb",
               "gpu_power_limit_w", "gpu_max_sm_clock_mhz", "python"]


def add_arguments(p):
    p.add_argument("a", help="reference run (e.g. bbaum-pc-7@baseline)")
    p.add_argument("b", help="run to compare (e.g. bbaum-pc-7@latest)")
    p.add_argument("--store", help="results store")
    p.add_argument("--all-metrics", action="store_true", help="include power/clock/efficiency sub-metrics")
    p.add_argument("--markdown", help="also write the comparison as a Markdown file")


def pct_change(a, b, higher_is_better=True) -> str:
    if not a or b is None:
        return ""
    d = (b - a) / abs(a) * 100
    if abs(d) < 1.0:
        return f"{d:+.1f}%"
    return f"{d:+.1f}% {'better' if (d > 0) == higher_is_better else 'worse'}"


def warnings(a: RunRecord, b: RunRecord) -> list[str]:
    out = []
    va, vb = a.benchmark_versions(), b.benchmark_versions()
    for bench in sorted(set(va) & set(vb)):
        if va[bench] != vb[bench]:
            out.append(f"{bench}: methodology version {va[bench]} vs {vb[bench]}; values are not comparable")
    sa, sb = a.data.get("settings", {}), b.data.get("settings", {})
    for key in ("duration_s", "cooldown_s"):
        if sa.get(key) and sb.get(key) and sa[key] != sb[key]:
            out.append(f"settings differ: {key} {sa[key]} vs {sb[key]}")
    for rec in (a, b):
        if rec.status not in ("complete", "legacy"):
            out.append(f"{rec.run_id} is {rec.status}")
    return out


def build_tables(a: RunRecord, b: RunRecord, all_metrics: bool = False) -> list[Table]:
    la, lb = a.label(), b.label()
    tables = []

    ea, eb = a.data.get("environment", {}), b.data.get("environment", {})
    if ea or eb:
        t = Table("System", ["", la, lb])
        t.add("run", a.run_id, b.run_id)
        t.add("started", a.data.get("started_at", "-"), b.data.get("started_at", "-"))
        for key in SYSTEM_KEYS:
            t.add(key, ea.get(key, "-"), eb.get(key, "-"))
        t.add("gpu", ea.get("gpu", {}).get("name", "-"), eb.get("gpu", {}).get("name", "-"))
        tables.append(t)

    names = [n for n in dict.fromkeys([*a.metrics, *b.metrics]) if all_metrics or n.count(".") == 1]
    if names:
        va, vb = a.benchmark_versions(), b.benchmark_versions()
        t = Table("Benchmarks", ["metric", "unit", la, lb, "change"])
        for n in names:
            ma, mb = a.metrics.get(n), b.metrics.get(n)
            m = ma or mb
            x, y = (ma or {}).get("value"), (mb or {}).get("value")
            bench = benchmark_of(n)
            change = pct_change(x, y, m.get("higher_is_better", True))
            if bench in va and bench in vb and va[bench] != vb[bench]:
                change = "n/a (version)"
            t.add(n, m["unit"], num(x), num(y), change)
        tables.append(t)

    ta, tb = a.phase_telemetry, b.phase_telemetry
    phases = [p for p in ta if p in tb and p not in ("cooldown", "cooldown_final", ALL_PHASES)]
    if ta or tb:
        t = Table("Telemetry per phase", ["phase", "measure", la, lb, "change"])
        for ph in phases + [ALL_PHASES]:
            sa, sb = ta.get(ph, {}), tb.get(ph, {})
            for key, hib in STAT_HIGHER_IS_BETTER.items():
                x, y = sa.get(key), sb.get(key)
                if x is None and y is None:
                    continue
                digits = 4 if key == "gpu_energy_wh" else 1
                t.add("whole run" if ph == ALL_PHASES else ph, key, num(x, digits), num(y, digits),
                      pct_change(x, y, hib))
        tables.append(t)
    return tables


def main(args) -> int:
    root = store.store_root(args.store)
    a, b = store.resolve(args.a, root), store.resolve(args.b, root)
    tables = build_tables(a, b, args.all_metrics)
    print("=" * 72)
    print(f" {a.label()}  vs  {b.label()}")
    print("=" * 72)
    for w in warnings(a, b):
        print(f" !! {w}")
    for t in tables:
        print(t.text())
    if args.markdown:
        md = f"# {a.label()} vs {b.label()}\n\n" + "".join(f"- {w}\n" for w in warnings(a, b))
        md += "\n".join(t.markdown() for t in tables) + "\n"
        Path(args.markdown).write_text(md, encoding="utf-8")
        print(f"\nMarkdown written to {args.markdown}")
    return 0
