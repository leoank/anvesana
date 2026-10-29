"""Benchmark registry and requirements.

A benchmark is a module in ``anvesana.suite`` exposing:

  NAME          CLI / profile name, e.g. "tensor"
  VERSION       int; bump whenever a change makes new results incomparable with
                old ones (different kernel, problem size, units, ...). Health
                checks refuse to compare metrics across versions.
  DESCRIPTION   one line for --help
  add_arguments(parser)
  run(args) -> list[Metric]   args always has .duration (seconds per sustained test)

What a benchmark needs is declared here, not in the module, so it can be read
without importing a module whose dependencies are not installed:

  extras    pyproject optional-dependency groups (`anvesana setup` installs them)
  tools     executables that must be on PATH (system packages uv cannot install,
            e.g. perftest's ib_write_bw for InfiniBand, xbutil for Xilinx FPGAs)
  os        OS tags it supports; empty = any
  hardware  a device probe from HARDWARE_PROBES that must succeed

To add a benchmark: write the module, add a Requirement to SUITE (and an extra
to pyproject.toml if it needs new Python packages), and list it in the machine
profiles that should run it.
"""

from __future__ import annotations

import importlib
import shutil
from dataclasses import dataclass
from types import ModuleType

from .environment import os_tag


@dataclass(frozen=True)
class Requirement:
    module: str
    extras: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    os: tuple[str, ...] = ()
    hardware: str | None = None


# Benchmark NAME -> requirements, in suggested run order.
SUITE = {
    "cpu": Requirement("cpu_ram"),
    "gpu": Requirement("gpu", extras=("nvidia",), hardware="nvidia-gpu"),
    "tensor": Requirement("tensor_peak", extras=("nvidia",), hardware="nvidia-gpu"),
    "cublaslt": Requirement("cublaslt", extras=("nvidia",), hardware="nvidia-gpu"),
    "tensorrt": Requirement("tensorrt_gemm", extras=("nvidia", "tensorrt"), hardware="nvidia-gpu"),
    "cutlass": Requirement("cutlass_gemm", extras=("nvidia", "cutlass"), tools=("c++",), os=("linux",),
                           hardware="nvidia-gpu"),
    "disk": Requirement("disk"),
}


def _probe_nvidia_gpu() -> str | None:
    try:
        from cuda.bindings import driver as cu
    except ImportError:
        return "CUDA bindings not installed (extra 'nvidia')"
    err, = cu.cuInit(0)
    if int(err) != 0:
        return f"no usable NVIDIA GPU / driver ({err.name})"
    err, count = cu.cuDeviceGetCount()
    return None if int(err) == 0 and count > 0 else "no NVIDIA GPU found"


# Probe name -> function returning None if the device is usable, else the reason.
HARDWARE_PROBES = {"nvidia-gpu": _probe_nvidia_gpu}


def load(name: str) -> ModuleType:
    """Imports one benchmark module. Raises KeyError / ImportError."""
    req = SUITE.get(name)
    if req is None:
        raise KeyError(f"unknown benchmark '{name}' (known: {', '.join(SUITE)})")
    return importlib.import_module(f"anvesana.suite.{req.module}")


def load_all() -> dict[str, ModuleType | Exception]:
    """{NAME: module}, or the ImportError for a module whose optional
    dependency is missing, so one absent library disables one benchmark only."""
    out = {}
    for name in SUITE:
        try:
            out[name] = load(name)
        except ImportError as e:
            out[name] = e
    return out


def problems(name: str) -> list[str]:
    """Everything preventing benchmark ``name`` from running here; empty if it can."""
    req = SUITE.get(name)
    if req is None:
        return [f"unknown benchmark '{name}'"]
    if req.os and os_tag() not in req.os:
        return [f"not supported on {os_tag()} (only {', '.join(req.os)})"]
    out = []
    try:
        load(name)
    except ImportError as e:
        out.append(f"missing Python packages ({e.name or e}); run `anvesana setup` "
                   f"(extras: {', '.join(req.extras) or 'none'})")
    for tool in req.tools:
        if not shutil.which(tool):
            out.append(f"system tool '{tool}' not on PATH")
    if req.hardware and not out:
        reason = HARDWARE_PROBES[req.hardware]()
        if reason:
            out.append(reason)
    return out
