"""Benchmark registry.

A benchmark is a module in ``anvesana.suite`` exposing:

  NAME          CLI / profile name, e.g. "tensor"
  VERSION       int; bump whenever a change makes new results incomparable with
                old ones (different kernel, problem size, units, ...). Health
                checks refuse to compare metrics across versions.
  DESCRIPTION   one line for --help
  add_arguments(parser)
  run(args) -> list[Metric]   args always has .duration (seconds per sustained test)

To add one: write the module, add it to SUITE (NAME -> module file), and list
it in the machine profiles that should run it.
"""

from __future__ import annotations

import importlib
from types import ModuleType

# Benchmark NAME -> module in anvesana.suite, in suggested run order.
SUITE = {
    "cpu": "cpu_ram",
    "gpu": "gpu",
    "tensor": "tensor_peak",
    "cublaslt": "cublaslt",
    "tensorrt": "tensorrt_gemm",
    "cutlass": "cutlass_gemm",
    "disk": "disk",
}


def load_all() -> dict[str, ModuleType | Exception]:
    """{NAME: module}, or the ImportError for a module whose optional
    dependency is missing, so one absent library disables one benchmark only."""
    out = {}
    for name, module_name in SUITE.items():
        try:
            out[name] = importlib.import_module(f"anvesana.suite.{module_name}")
        except ImportError as e:
            out[name] = e
    return out


def get(name: str) -> ModuleType:
    mods = load_all()
    mod = mods.get(name)
    if mod is None:
        raise KeyError(f"unknown benchmark '{name}' (known: {', '.join(k for k in mods)})")
    if isinstance(mod, Exception):
        raise mod
    return mod
