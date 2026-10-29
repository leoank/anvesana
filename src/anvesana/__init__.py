"""anvesana: node health benchmarks. Run the same GPU/CPU/memory/disk suite on every
machine on a schedule and track the results over time.

  framework/  run records, results store, machine profiles, runner, compare/history/health
  hw/         CUDA driver/NVRTC wrapper, sensors, telemetry logger
  suite/      the benchmarks themselves
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("anvesana")
except PackageNotFoundError:
    __version__ = "0+unknown"
