"""Where runs live, and how to refer to them.

Results store (outside the repo; one per site or a shared/synced folder):
  $ANVESANA_RESULTS_DIR (default ~/anvesana-results)/
    <machine>/
      <machine>_<YYYY-MM-DD_HHMMSS>_<os>[_tag]/
        run.json  telemetry.csv  run.log

Baselines (in the repo, reviewed like code):
  baselines/<machine>/<os>.json   a promoted run.json, the health-check reference

Run references accepted by compare / history / health:
  path/to/run_dir | path/to/run.json | legacy telemetry .csv
  <machine> | <machine>@latest       newest run in the store
  <machine>@-1                       the run before the newest (@-2, ...)
  <machine>@2026-10-29               first run on that date
  <machine>@baseline[:<os>]          committed baseline (OS defaults to this host's, else the only one)
  <run_id>                           exact run directory name
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from .environment import os_tag
from .machine import REPO_ROOT
from .records import RunRecord

BASELINES_DIR = REPO_ROOT / "baselines"
DEFAULT_STORE = Path.home() / "anvesana-results"


def store_root(override: str | None = None) -> Path:
    return Path(override or os.environ.get("ANVESANA_RESULTS_DIR") or DEFAULT_STORE).expanduser()


def new_run_dir(root: Path, machine_id: str, started: dt.datetime, tag: str | None) -> tuple[str, Path]:
    run_id = f"{machine_id}_{started.strftime('%Y-%m-%d_%H%M%S')}_{os_tag()}{'_' + tag if tag else ''}"
    path = root / machine_id / run_id
    path.mkdir(parents=True, exist_ok=False)
    return run_id, path


def list_runs(root: Path, machine_id: str | None = None, os: str | None = None,
              include_partial: bool = True) -> list[RunRecord]:
    """Runs oldest first."""
    pattern = f"{machine_id}/*/run.json" if machine_id else "*/*/run.json"
    runs = []
    for p in root.glob(pattern):
        try:
            r = RunRecord.load(p)
        except (OSError, ValueError):
            continue
        if os and r.os != os:
            continue
        if r.status == "aborted" or (not include_partial and r.status != "complete"):
            continue
        runs.append(r)
    return sorted(runs, key=lambda r: r.data.get("started_at", ""))


def baseline_path(machine_id: str, os: str) -> Path:
    return BASELINES_DIR / machine_id / f"{os}.json"


def load_baseline(machine_id: str, os: str | None = None) -> RunRecord | None:
    folder = BASELINES_DIR / machine_id
    if os:
        p = baseline_path(machine_id, os)
        return RunRecord.load(p) if p.exists() else None
    here = baseline_path(machine_id, os_tag())
    if here.exists():
        return RunRecord.load(here)
    found = sorted(folder.glob("*.json")) if folder.exists() else []
    return RunRecord.load(found[0]) if len(found) == 1 else None


def promote(record: RunRecord) -> Path:
    """Copies a run's record into the repo as the machine's baseline for its OS."""
    data = dict(record.data)
    data["baseline"] = {"promoted_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                        "source_run_id": record.run_id}
    path = baseline_path(record.machine_id, record.os)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def resolve(ref: str, root: Path) -> RunRecord:
    p = Path(ref).expanduser()
    if p.exists():
        return RunRecord.load(p)

    machine_id, _, selector = ref.partition("@")
    selector = selector or "latest"
    if selector.startswith("baseline"):
        _, _, os = selector.partition(":")
        rec = load_baseline(machine_id, os or None)
        if rec is None:
            raise SystemExit(f"No baseline for '{machine_id}'{' on ' + os if os else ''} in {BASELINES_DIR}")
        return rec

    runs = list_runs(root, machine_id)
    if not runs:
        # Maybe an exact run id.
        for cand in root.glob(f"*/{ref}/run.json"):
            return RunRecord.load(cand)
        raise SystemExit(f"No runs found for '{ref}' in {root}")
    if selector == "latest":
        return runs[-1]
    if selector.lstrip("-").isdigit():
        idx = -1 + int(selector)  # @-1 -> second newest
        if -idx > len(runs):
            raise SystemExit(f"'{ref}': only {len(runs)} runs stored")
        return runs[idx]
    for r in runs:
        if r.data.get("started_at", "").startswith(selector):
            return r
    raise SystemExit(f"No run of '{machine_id}' matches '{selector}'")


class RunLock:
    """Prevents two suite runs on one machine at once (e.g. a scheduled run
    starting while a manual one is going), which would ruin both."""

    def __init__(self, root: Path, machine_id: str):
        self.path = root / machine_id / ".run.lock"

    def __enter__(self):
        import psutil

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text().strip())
            except ValueError:
                pid = -1
            if pid > 0 and psutil.pid_exists(pid):
                raise SystemExit(f"Another run (pid {pid}) holds {self.path}")
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
