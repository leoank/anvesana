"""Runs a machine's benchmark suite and writes one run directory to the store.

  1. resolve the machine profile (by --machine or this host's name)
  2. start the telemetry monitor (separate process, rows tagged by phase)
  3. idle baseline, then each benchmark in its own process with cooldowns between
  4. write run.json (settings, environment, metrics, per-phase telemetry summary)
  5. optionally health-check the run against the machine's baseline

Each benchmark runs in a fresh Python process: a crash or leaked GPU memory
in one cannot affect the next, and TensorRT / TensorRT-RTX never share a process.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time

from .. import __version__
from . import environment, machine as machines, registry, store
from .console import RULE
from .records import SCHEMA_VERSION, RunRecord, is_headline, summarize_telemetry

HEADLINE_UNITS = {"TFLOPS", "GB/s", "MB/s", "IOPS", "GFLOPS", "MOps/s", "ms"}


def add_arguments(p):
    p.add_argument("--machine", help="profile id (default: the profile listing this hostname)")
    p.add_argument("--duration", type=float, help="seconds per sustained test (default: from the profile)")
    p.add_argument("--cooldown", type=float, help="idle seconds between benchmarks (default: from the profile)")
    p.add_argument("--only", help="comma-separated benchmark ids to run")
    p.add_argument("--skip", help="comma-separated benchmark ids to skip")
    p.add_argument("--tag", help="label for this run, e.g. 'best-perf' (part of the run id)")
    p.add_argument("--store", help="results store (default: $ANVESANA_RESULTS_DIR or ~/anvesana-results)")
    p.add_argument("--health", action="store_true",
                   help="health-check the finished run against the baseline; exit 1 on failure")


class _Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def write(self, text: str):
        sys.stdout.write(text)
        sys.stdout.flush()
        self.f.write(text)
        self.f.flush()


def _select(profile, args) -> list:
    specs = [s for s in profile.benchmarks if s.applies_here()]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        unknown = wanted - {s.id for s in specs}
        if unknown:
            raise SystemExit(f"--only: not in profile '{profile.id}' for this OS: {', '.join(sorted(unknown))}")
        specs = [s for s in specs if s.id in wanted]
    if args.skip:
        unwanted = {s.strip() for s in args.skip.split(",")}
        specs = [s for s in specs if s.id not in unwanted]
    return specs


def _preflight(env: dict) -> list[str]:
    """Conditions that make a run unrepresentative. Recorded, not fatal."""
    import psutil

    notes = []
    if env.get("on_ac_power") is False:
        notes.append("running on battery")
    load = psutil.cpu_percent(interval=2.0)
    if load > 20:
        notes.append(f"system busy before start: {load:.0f}% CPU")
    return notes


def main(args) -> int:
    profile = machines.resolve(args.machine)
    duration = args.duration or profile.duration_s
    cooldown = profile.cooldown_s if args.cooldown is None else args.cooldown
    specs = _select(profile, args)
    modules = registry.load_all()
    root = store.store_root(args.store)

    with store.RunLock(root, profile.id):
        started = dt.datetime.now().astimezone()
        run_id, run_dir = store.new_run_dir(root, profile.id, started, args.tag)
        log = _Tee(run_dir / "run.log")
        phase_file, stop_file = run_dir / ".phase", run_dir / ".stop"

        env = environment.capture()
        preflight = _preflight(env)
        log.write(f"{RULE}\n Benchmark run {run_id}\n Machine : {profile.id} - {profile.description}\n"
                  f" Store   : {run_dir}\n Plan    : {', '.join(s.id for s in specs)}\n"
                  f" Settings: {duration:.0f}s per sustained test, {cooldown:.0f}s cooldown\n{RULE}\n")
        for note in preflight:
            log.write(f" !! {note}\n")

        child_env = dict(os.environ, PYTHONUNBUFFERED="1")
        phase_file.write_text("startup")
        monitor = subprocess.Popen(
            [sys.executable, "-m", "anvesana", "monitor", "--output", str(run_dir / "telemetry.csv"),
             "--phase-file", str(phase_file), "--stop-file", str(stop_file), "--quiet"],
            env=child_env, stdout=subprocess.DEVNULL)

        t0 = time.time()
        phases, metrics, bench_results, failures = [], {}, [], []
        status = "complete"

        def enter(name: str):
            phase_file.write_text(name)
            phases.append({"phase": name, "start_s": round(time.time() - t0, 2)})

        def leave(**extra):
            phases[-1]["end_s"] = round(time.time() - t0, 2)
            phases[-1].update(extra)

        try:
            enter("idle")
            log.write(f"\n[idle] {profile.idle_s:.0f}s baseline...\n")
            time.sleep(profile.idle_s)
            leave()

            for i, spec in enumerate(specs, 1):
                mod = modules.get(spec.module)
                entry = {"id": spec.id, "module": spec.module, "args": spec.args,
                         "version": getattr(mod, "VERSION", None) if mod and not isinstance(mod, Exception) else None}
                if mod is None or isinstance(mod, Exception):
                    reason = str(mod) if mod else f"unknown benchmark module '{spec.module}'"
                    log.write(f"\n[{i}/{len(specs)}] {spec.id}: unavailable ({reason})\n")
                    bench_results.append({**entry, "status": "unavailable", "reason": reason})
                    failures.append(spec.id)
                    continue
                if i > 1 and cooldown > 0:
                    enter("cooldown")
                    time.sleep(cooldown)
                    leave()

                enter(spec.id)
                log.write(f"\n[{i}/{len(specs)}] {spec.id}\n")
                out_json = run_dir / f".{spec.id}.json"
                cmd = [sys.executable, "-m", "anvesana", spec.module, *spec.cli_args(),
                       "--duration", str(duration), "--json", str(out_json)]
                b0 = time.time()
                proc = subprocess.Popen(cmd, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace")
                for line in proc.stdout:
                    log.write(line)
                proc.wait()
                leave(exit_code=proc.returncode)

                produced = {}
                if out_json.exists():
                    produced = json.loads(out_json.read_text())
                    out_json.unlink()
                # Metric names are re-prefixed with the profile id so one module can
                # appear twice (e.g. tensorrt with two backends, disk on two drives).
                for name, m in produced.items():
                    metrics[f"{spec.id}.{name.split('.', 1)[1]}"] = m
                ok = proc.returncode == 0 and bool(produced)
                bench_results.append({**entry, "status": "ok" if ok else "failed", "exit_code": proc.returncode,
                                      "elapsed_s": round(time.time() - b0, 1), "metric_count": len(produced)})
                if not ok:
                    failures.append(spec.id)
                    log.write(f"  !! {spec.id} {'produced no metrics' if proc.returncode == 0 else f'exited with {proc.returncode}'}\n")

            enter("cooldown_final")
            log.write("\n[cooldown] 10s thermal descent...\n")
            time.sleep(10)
            leave()
        except KeyboardInterrupt:
            status = "aborted"
            log.write("\nInterrupted; saving partial results.\n")
        finally:
            stop_file.write_text("stop")
            try:
                monitor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                monitor.kill()
            for p in (phase_file, stop_file):
                p.unlink(missing_ok=True)

        if status != "aborted" and failures:
            status = "partial"
        finished = dt.datetime.now().astimezone()
        record = RunRecord({
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "machine": profile.summary(),
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": finished.isoformat(timespec="seconds"),
            "duration_s": round((finished - started).total_seconds()),
            "status": status,
            "settings": {
                "tag": args.tag,
                "duration_s": duration,
                "cooldown_s": cooldown,
                "idle_s": profile.idle_s,
                "only": args.only, "skip": args.skip,
                "benchmarks": bench_results,
                "framework_version": __version__,
                **environment.source_revision(),
                # argv[0] is a local path (and so a username); records may be published.
                "command": " ".join(["anvesana", *sys.argv[1:]]),
            },
            "environment": env,
            "preflight": preflight,
            "phases": phases,
            "phase_telemetry": summarize_telemetry(run_dir / "telemetry.csv"),
            "metrics": metrics,
            "failures": failures,
        }, run_dir / "run.json")
        record.save(run_dir)

    _print_summary(log, record, profile)
    log.write(f"\n Status: {status}{' (failed: ' + ', '.join(failures) + ')' if failures else ''}\n")
    log.write(f" Saved : {run_dir / 'run.json'}\n")
    exit_code = 0 if status == "complete" else 1
    if args.health:
        from . import health

        exit_code = max(exit_code, health.check(profile, record, root, log=log.write))
    return exit_code


def _print_summary(log, record: RunRecord, profile):
    log.write(f"\n{RULE}\n Results\n{RULE}\n")
    for name, m in record.metrics.items():
        if not is_headline(name) or m["unit"] not in HEADLINE_UNITS:
            continue
        spec = profile.expected.get(name)
        pct = f"  ({100 * m['value'] / spec:.0f}% of {spec:g} advertised)" if spec else ""
        log.write(f" {name:<40} {m['value']:>12,.2f} {m['unit']}{pct}\n")
