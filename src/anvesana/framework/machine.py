"""Machine profiles: machines/<id>.toml in the repository.

A profile says which benchmarks a machine runs and how, what the vendor
advertises (for "% of spec"), and how much a metric may drift before the
health check flags it. See machines/_template.toml for every field.
"""

from __future__ import annotations

import fnmatch
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .environment import hostname, os_tag

REPO_ROOT = Path(__file__).resolve().parents[3]
MACHINES_DIR = REPO_ROOT / "machines"


@dataclass
class BenchmarkSpec:
    id: str  # phase / metric prefix, unique within the profile
    module: str  # registry NAME
    args: dict = field(default_factory=dict)
    os: list[str] = field(default_factory=list)  # empty = every OS

    def applies_here(self) -> bool:
        return not self.os or os_tag() in self.os

    def cli_args(self) -> list[str]:
        """Profile args -> CLI flags: {"size_mb": 2048, "show_kernels": true} -> --size-mb 2048 --show-kernels"""
        out = []
        for key, value in self.args.items():
            flag = "--" + key.replace("_", "-")
            if value is True:
                out.append(flag)
            elif value is not False and value is not None:
                out += [flag, str(value)]
        return out


@dataclass
class Machine:
    id: str
    description: str
    hostnames: list[str]
    benchmarks: list[BenchmarkSpec]
    duration_s: float = 30.0
    cooldown_s: float = 15.0
    idle_s: float = 10.0
    expected: dict[str, float] = field(default_factory=dict)
    tolerance_pct: float = 10.0
    tolerance_overrides: dict[str, float] = field(default_factory=dict)
    source: Path | None = None

    def tolerance_for(self, metric: str) -> float:
        """Most specific matching glob wins (longest pattern)."""
        matches = [(len(p), t) for p, t in self.tolerance_overrides.items() if fnmatch.fnmatch(metric, p)]
        return max(matches)[1] if matches else self.tolerance_pct

    def summary(self) -> dict:
        return {"id": self.id, "description": self.description, "hostname": hostname(),
                "profile": str(self.source.relative_to(REPO_ROOT)) if self.source else None}


def load(path: Path) -> Machine:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    m = data.get("machine", {})
    run = data.get("run", {})
    health = data.get("health", {})
    specs = []
    for b in data.get("benchmarks", []):
        specs.append(BenchmarkSpec(id=b["id"], module=b.get("module", b["id"]), args=b.get("args", {}),
                                   os=b.get("os", [])))
    ids = [s.id for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: duplicate benchmark ids")
    return Machine(
        id=m.get("id", path.stem), description=m.get("description", ""),
        hostnames=[h.lower() for h in m.get("hostnames", [])], benchmarks=specs,
        duration_s=run.get("duration_s", 30.0), cooldown_s=run.get("cooldown_s", 15.0), idle_s=run.get("idle_s", 10.0),
        expected=data.get("expected", {}),
        tolerance_pct=health.get("tolerance_pct", 10.0), tolerance_overrides=health.get("tolerance_overrides", {}),
        source=path,
    )


def all_profiles() -> list[Machine]:
    return [load(p) for p in sorted(MACHINES_DIR.glob("*.toml")) if not p.name.startswith("_")]


def resolve(machine_id: str | None) -> Machine:
    """By id, or by matching this host's name when no id is given."""
    profiles = all_profiles()
    if machine_id:
        for p in profiles:
            if p.id == machine_id:
                return p
        raise SystemExit(f"No profile '{machine_id}' in {MACHINES_DIR} (have: {', '.join(p.id for p in profiles)})")
    host = hostname()
    for p in profiles:
        if host in p.hostnames:
            return p
    raise SystemExit(f"No machine profile lists hostname '{host}'. Create one with:\n"
                     f"  {Path(sys.argv[0]).stem} machines init <id>")


TEMPLATE = (MACHINES_DIR / "_template.toml")


def init_profile(machine_id: str) -> Path:
    """New profile from the template, pre-filled with this host's name."""
    path = MACHINES_DIR / f"{machine_id}.toml"
    if path.exists():
        raise SystemExit(f"{path} already exists")
    from .environment import capture

    env = capture()
    gpu = env.get("gpu", {}).get("name", "no CUDA GPU detected")
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace('id = "example"', f'id = "{machine_id}"')
    text = text.replace('hostnames = ["example-host"]', f'hostnames = ["{hostname()}"]')
    text = text.replace('description = "..."', f'description = "{env["cpu"]}, {gpu}, {env["ram_gb"]:.0f} GB"')
    path.write_text(text, encoding="utf-8")
    return path
