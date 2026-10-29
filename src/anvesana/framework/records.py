"""The run record: the single JSON document (run.json) describing one suite run.

Schema (version 1):
  schema_version     int, bumped on incompatible changes
  run_id             "<machine>_<YYYY-MM-DD_HHMMSS>_<os>[_tag]", also the run directory name
  machine            {id, description, hostname}
  started_at         ISO 8601 with timezone; finished_at, duration_s
  status             "complete" | "partial" (some benchmarks failed) | "aborted"
  settings           how the run was configured: tag, duration_s, cooldown_s, the resolved
                     benchmark list with args and methodology versions, framework version,
                     git commit, command line
  environment        OS, kernel, driver, CUDA/library versions, power policy, AC power, CPU/GPU
  phases             [{phase, start_s, end_s, exit_code}] relative to started_at
  phase_telemetry    {phase: {avg_gpu_power_w, avg_gpu_sm_clock_mhz, peak_gpu_temp_c, ...}}
  metrics            {name: {value, unit, higher_is_better, note}}
  failures           [benchmark ids that exited non-zero]

Metric names are "<benchmark id>.<measure>[.<qualifier>]"; a benchmark's
VERSION in settings.benchmarks says whether two values were measured the
same way.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1

# Units that describe operating conditions rather than performance. Recorded and
# compared, but not health-checked: lower power can be good or bad.
CONTEXT_UNITS = {"W", "MHz"}


@dataclass
class Metric:
    name: str
    value: float
    unit: str
    higher_is_better: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        del d["name"]
        return d


class RunRecord:
    """A loaded run.json (or, for old CSV-only runs, a telemetry-only stand-in)."""

    def __init__(self, data: dict, path: Path | None = None):
        self.data = data
        self.path = path

    @classmethod
    def load(cls, path: str | Path) -> "RunRecord":
        p = Path(path)
        if p.is_dir():
            p = p / "run.json"
        if p.suffix == ".csv":
            return cls.from_legacy_csv(p)
        return cls(json.loads(p.read_text(encoding="utf-8")), p)

    @classmethod
    def from_legacy_csv(cls, path: Path) -> "RunRecord":
        """Telemetry CSV from the original PowerShell/bash scripts."""
        return cls({"schema_version": 0, "run_id": path.stem, "machine": {"id": "?"}, "status": "legacy",
                    "environment": {}, "settings": {}, "metrics": {},
                    "phase_telemetry": summarize_telemetry(path)}, path)

    def save(self, run_dir: Path):
        (run_dir / "run.json").write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    # convenient views -------------------------------------------------------------
    @property
    def run_id(self) -> str:
        return self.data.get("run_id", "?")

    @property
    def machine_id(self) -> str:
        return self.data.get("machine", {}).get("id", "?")

    @property
    def os(self) -> str:
        return self.data.get("environment", {}).get("os", "?")

    @property
    def status(self) -> str:
        return self.data.get("status", "?")

    @property
    def started_at(self) -> dt.datetime | None:
        s = self.data.get("started_at")
        return dt.datetime.fromisoformat(s) if s else None

    @property
    def date(self) -> str:
        return self.started_at.strftime("%Y-%m-%d") if self.started_at else "?"

    @property
    def tag(self) -> str:
        return self.data.get("settings", {}).get("tag") or ""

    @property
    def metrics(self) -> dict:
        return self.data.get("metrics", {})

    @property
    def phase_telemetry(self) -> dict:
        return self.data.get("phase_telemetry", {})

    def benchmark_versions(self) -> dict[str, int]:
        return {b["id"]: b.get("version", 0) for b in self.data.get("settings", {}).get("benchmarks", [])}

    def label(self) -> str:
        return f"{self.machine_id} {self.os} {self.date}{' ' + self.tag if self.tag else ''}"


def benchmark_of(metric_name: str) -> str:
    return metric_name.split(".", 1)[0]


def is_headline(metric_name: str) -> bool:
    """"tensor.fp16" is a headline result; "tensor.fp16.avg_power" is context."""
    return metric_name.count(".") == 1


# ------------------------------------------------------------------ telemetry summary

_STATS = [
    # (key, column, reducer)
    ("avg_gpu_power_w", "gpu_power_w", "avg"),
    ("peak_gpu_power_w", "gpu_power_w", "max"),
    ("avg_gpu_sm_clock_mhz", "gpu_sm_clock_mhz", "avg"),
    ("avg_gpu_clock_mhz", "gpu_clock_mhz", "avg"),
    ("peak_gpu_temp_c", "gpu_temp_c", "max"),
    ("peak_soc_temp_c", "soc_temp_c", "max"),
    ("peak_thermal_c", "thermal_max_c", "max"),
    ("avg_cpu_util_pct", "cpu_util_pct", "avg"),
    ("avg_cpu_freq_mhz", "cpu_freq_mhz", "avg"),
    ("peak_ram_used_gb", "ram_used_gb", "max"),
]

# Whether a higher value of each telemetry stat is the healthier direction.
STAT_HIGHER_IS_BETTER = {
    "avg_gpu_power_w": False, "peak_gpu_power_w": False, "avg_gpu_sm_clock_mhz": True, "avg_gpu_clock_mhz": True,
    "peak_gpu_temp_c": False, "peak_soc_temp_c": False, "peak_thermal_c": False, "avg_cpu_util_pct": True,
    "avg_cpu_freq_mhz": True, "peak_ram_used_gb": False, "gpu_energy_wh": False,
}

ALL_PHASES = "_all"


def summarize_telemetry(csv_path: Path) -> dict[str, dict[str, float]]:
    """Per-phase sensor statistics, so run.json stays self-contained (baselines
    committed to the repo carry no CSV)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    groups: dict[str, list[dict]] = {ALL_PHASES: rows}
    for r in rows:
        ph = r.get("phase") or ""
        if ph and ph != "startup":
            groups.setdefault(ph, []).append(r)

    out = {}
    for phase, group in groups.items():
        stats: dict[str, float] = {"samples": len(group)}
        for key, col, how in _STATS:
            vals = [_float(r.get(col)) for r in group]
            vals = [v for v in vals if v is not None]
            if vals:
                stats[key] = round(max(vals) if how == "max" else sum(vals) / len(vals), 2)
        energy = _energy_wh(group)
        if energy is not None:
            stats["gpu_energy_wh"] = round(energy, 4)
        out[phase] = stats
    return out


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _energy_wh(rows: list[dict]) -> float | None:
    pts = [(_float(r.get("elapsed_sec")), _float(r.get("gpu_power_w"))) for r in rows]
    pts = [(t, p) for t, p in pts if t is not None and p is not None]
    if len(pts) < 2:
        return None
    # Trapezoid over consecutive samples; gaps between phases (>5 s) are skipped.
    joules = sum((t1 - t0) * (p0 + p1) / 2 for (t0, p0), (t1, p1) in zip(pts, pts[1:]) if 0 < t1 - t0 < 5)
    return joules / 3600
