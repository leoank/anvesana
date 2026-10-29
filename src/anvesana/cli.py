"""Command line: ``bench <command>`` (or ``python -m anvesana <command>``).

Node setup
  bench machines [init ID]                list profiles / create one for this host
  bench setup [--machine ID]              install exactly the extras this node's profile needs
  bench check [--machine ID]              can every benchmark in the profile run here?

Fleet workflow
  bench run [--machine ID] [--health]     run the machine's suite, store the results
  bench health [RUN] [--against REF]      check a run against baseline / recent median
  bench fleet                             latest health of every machine; flags stale nodes
  bench show [RUN]                        one run in full: metrics, settings, environment, telemetry
  bench history [MACHINE]                 metric trends across stored runs
  bench compare A B                       any two runs side by side
  bench runs [MACHINE]                    list stored runs
  bench baseline promote RUN              make a run the committed reference

Single pieces
  bench <benchmark> [...]                 one benchmark, e.g. `bench tensor --duration 10`
  bench monitor --output m.csv            telemetry logger
  bench info                              environment as recorded in run.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .framework import compare, fleet, health, history, provision, registry, runner, show, store
from .framework import machine as machines
from .hw import monitor


def _cmd_info(args) -> int:
    from .framework.environment import capture

    print(json.dumps(capture(), indent=2))
    return 0


def _cmd_machines(args) -> int:
    if args.action == "init":
        if not args.id:
            raise SystemExit("usage: bench machines init <id>")
        path = machines.init_profile(args.id)
        print(f"Created {path}; review the benchmark list, [expected] and [health] sections.")
        return 0
    from .framework.environment import hostname

    host = hostname()
    for p in machines.all_profiles():
        here = "  <- this host" if host in p.hostnames else ""
        print(f"{p.id:<20} {', '.join(b.id for b in p.benchmarks)}{here}\n{'':<20} {p.description}")
    return 0


def _cmd_runs(args) -> int:
    root = store.store_root(args.store)
    runs = store.list_runs(root, args.machine)
    if not runs:
        print(f"No runs in {root}")
        return 0
    for r in runs:
        failed = r.data.get("failures") or []
        print(f"{r.run_id:<52} {r.status:<9} {r.data.get('settings', {}).get('duration_s', '?'):>4}s"
              f"{'  failed: ' + ','.join(failed) if failed else ''}")
    print(f"\n{len(runs)} runs in {root}")
    return 0


def _cmd_baseline(args) -> int:
    root = store.store_root(args.store)
    if args.action == "promote":
        rec = store.resolve(args.run, root)
        if rec.status != "complete" and not args.force:
            raise SystemExit(f"{rec.run_id} is {rec.status}; use --force to promote it anyway")
        path = store.promote(rec)
        print(f"{rec.run_id} -> {path}\nCommit it so every checkout health-checks against it.")
        return 0
    found = sorted(store.BASELINES_DIR.glob("*/*.json"))
    for p in found:
        from .framework.records import RunRecord

        r = RunRecord.load(p)
        print(f"{p.relative_to(store.BASELINES_DIR)}: {r.run_id} ({r.data.get('baseline', {}).get('promoted_at', '?')})")
    if not found:
        print(f"No baselines in {store.BASELINES_DIR}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bench", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, module, help_ in (("run", runner, "run a machine's suite"),
                                ("health", health, "health-check a run"),
                                ("show", show, "print one run in full"),
                                ("history", history, "metric trends for a machine"),
                                ("compare", compare, "compare two runs"),
                                ("monitor", monitor, "telemetry logger only")):
        p = sub.add_parser(name, help=help_, description=module.__doc__,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        module.add_arguments(p)
        p.set_defaults(func=module.main)

    p = sub.add_parser("runs", help="list stored runs")
    p.add_argument("machine", nargs="?")
    p.add_argument("--store")
    p.set_defaults(func=_cmd_runs)

    p = sub.add_parser("baseline", help="show or promote baselines")
    p.add_argument("action", nargs="?", choices=["list", "promote"], default="list")
    p.add_argument("run", nargs="?", help="run reference to promote")
    p.add_argument("--force", action="store_true", help="promote a partial run")
    p.add_argument("--store")
    p.set_defaults(func=_cmd_baseline)

    p = sub.add_parser("machines", help="list machine profiles, or `init <id>` one for this host")
    p.add_argument("action", nargs="?", choices=["list", "init"], default="list")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=_cmd_machines)

    p = sub.add_parser("info", help="print the environment as recorded in run.json")
    p.set_defaults(func=_cmd_info)

    for name, add, func, help_ in (
            ("setup", provision.add_setup_arguments, provision.setup, "install exactly this node's dependencies"),
            ("check", provision.add_check_arguments, provision.check, "can every profiled benchmark run here?")):
        p = sub.add_parser(name, help=help_, description=provision.__doc__,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        add(p)
        p.set_defaults(func=func)
    p = sub.add_parser("fleet", help="latest health of every machine", description=fleet.__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    fleet.add_arguments(p)
    p.set_defaults(func=fleet.main)

    # Benchmark modules import their (optional, heavy) dependencies, so load only
    # the one being invoked, or all of them for --help. `setup` in particular must
    # not hold CUDA libraries open while uv replaces them.
    argv = sys.argv[1:] if argv is None else argv
    command = next((a for a in argv if not a.startswith("-")), None)
    names = [command] if command in registry.SUITE else list(registry.SUITE) if command is None else []
    for name in names:
        try:
            mod = registry.load(name)
        except ImportError as e:
            p = sub.add_parser(name, help=f"[benchmark, unavailable: missing {e.name}; run `anvesana setup`]")
            p.set_defaults(func=lambda a, e=e: _unavailable(e))
            continue
        p = sub.add_parser(name, help=f"[benchmark v{mod.VERSION}] {mod.DESCRIPTION}")
        p.add_argument("--duration", type=float, default=30.0, help="seconds per sustained test")
        p.add_argument("--json", help="also write metrics to this JSON file")
        mod.add_arguments(p)
        p.set_defaults(func=lambda a, mod=mod: _run_single(mod, a))

    args = parser.parse_args(argv)
    return args.func(args)


def _unavailable(e: ImportError) -> int:
    print(f"This benchmark's dependencies are not installed ({e}). Run `anvesana setup` "
          f"(or `uv sync --extra <extra>`).")
    return 2


def _run_single(mod, args) -> int:
    metrics = mod.run(args)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({m.name: m.to_dict() for m in metrics}, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
