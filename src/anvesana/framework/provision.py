"""Per-node dependency setup and readiness checks.

  anvesana setup [--machine ID]   install exactly the extras this node's profile needs
  anvesana check [--machine ID]   can every benchmark in the profile run here?

Python dependencies come from the shared uv.lock (`uv sync --locked`), so every
node that installs a library gets the same version. Things uv cannot install
(GPU drivers, InfiniBand perftest, FPGA runtimes, compilers) are only checked:
`check` names what is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from . import machine as machines, registry
from .console import Table
from .environment import os_tag
from .machine import REPO_ROOT


def add_setup_arguments(p):
    p.add_argument("--machine", help="profile id (default: the profile listing this hostname)")
    p.add_argument("--dry-run", action="store_true", help="print the uv command without running it")
    p.add_argument("--no-locked", action="store_true",
                   help="allow uv to update uv.lock (default: install exactly what the committed lock pins)")


def add_check_arguments(p):
    p.add_argument("--machine", help="profile id (default: the profile listing this hostname)")


def _uv() -> str:
    uv = os.environ.get("UV") or shutil.which("uv")  # `uv run` exports UV
    if not uv:
        raise SystemExit("uv not found on PATH; install it from https://docs.astral.sh/uv/")
    return uv


def setup(args) -> int:
    profile = machines.resolve(args.machine)
    extras = profile.required_extras()
    cmd = [_uv(), "sync", *(a for e in extras for a in ("--extra", e))]
    if not args.no_locked:
        cmd.append("--locked")
    print(f"Machine {profile.id} on {os_tag()}: benchmarks "
          f"{', '.join(s.id for s in profile.runnable_here())}")
    print(f"Extras: {', '.join(extras) or '(core only)'}")
    print("$ " + " ".join(["uv", *cmd[1:]]), flush=True)
    if args.dry_run:
        return 0
    # Exact sync: extras the profile no longer needs are removed too.
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        return result.returncode
    print()
    # A fresh interpreter sees the packages just installed.
    return subprocess.run([sys.executable, "-m", "anvesana", "check", "--machine", profile.id]).returncode


def check(args) -> int:
    profile = machines.resolve(args.machine)
    t = Table(f"Readiness: {profile.id} on {os_tag()}", ["benchmark", "module", "status", "detail"])
    bad = 0
    for spec in profile.benchmarks:
        if not spec.applies_here():
            t.add(spec.id, spec.module, "SKIP", f"profile runs it on {', '.join(spec.os)} only")
            continue
        issues = registry.problems(spec.module)
        if issues:
            bad += 1
            t.add(spec.id, spec.module, "MISSING", "; ".join(issues))
        else:
            t.add(spec.id, spec.module, "OK", "")
    print(t.text())
    print(f"\n{'READY' if not bad else f'NOT READY: {bad} benchmark(s) cannot run'}")
    return 1 if bad else 0
