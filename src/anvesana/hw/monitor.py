"""Telemetry logger (port of monitor_system.ps1 / monitor_system.sh).

Writes one CSV row per interval. The first 15 columns match the original
scripts so old CSVs stay comparable; the rest are new:
  cpu_freq_mhz          effective CPU clock (PDH % Processor Performance / sysfs cpufreq)
  thermal_max_c         hottest thermal zone
  gpu_sm_clock_mhz, gpu_mem_clock_mhz
  gpu_throttle_reasons  NVML clock-event bitmask (power cap, thermal, ...)
  phase                 benchmark phase, read from --phase-file when run by the suite

RAM "used" is total - available on both OSes (the PowerShell version used
total - free, which counts the standby cache as used).
"""

from __future__ import annotations

import csv
import datetime
import os
import time

import psutil

from .telemetry import Gpu, HostSensors

COLUMNS = [
    "timestamp_iso", "elapsed_sec", "cpu_util_pct", "soc_temp_c", "ram_used_gb", "ram_total_gb", "ram_pct",
    "gpu_util_pct", "gpu_mem_used_mb", "gpu_mem_total_mb", "gpu_temp_c", "gpu_power_w", "gpu_clock_mhz",
    "npu_temp_c", "npu_power_w",
    "cpu_freq_mhz", "thermal_max_c", "gpu_sm_clock_mhz", "gpu_mem_clock_mhz", "gpu_throttle_reasons", "phase",
]


def _fmt(v, digits=1):
    if v is None:
        return ""
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def add_arguments(p):
    p.add_argument("--output", default="metrics.csv")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    p.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = until stopped)")
    p.add_argument("--phase-file", help="file whose contents label each row's phase")
    p.add_argument("--stop-file", help="stop when this file appears")
    p.add_argument("--quiet", action="store_true", help="no live console line")


def main(args) -> int:
    host = HostSensors()
    n_gpus = Gpu.count()
    gpu = Gpu(0) if n_gpus > 0 else None
    npu = Gpu(1) if n_gpus > 1 else None  # the N1X NPU enumerates as NVML device 1 on Windows
    psutil.cpu_percent(None)  # prime: the first call has no reference interval

    print(f"Telemetry monitor started -> {args.output}", flush=True)
    t0 = time.perf_counter()
    samples, peaks = 0, {"soc": 0.0, "gpu_t": 0.0, "gpu_p": 0.0}
    power_sum = 0.0
    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        try:
            while True:
                elapsed = time.perf_counter() - t0
                if args.duration and elapsed >= args.duration:
                    break
                if args.stop_file and os.path.exists(args.stop_file):
                    break
                h = host.read()
                vm = psutil.virtual_memory()
                g = gpu.read() if gpu else {}
                n = npu.read() if npu else {}
                phase = ""
                if args.phase_file:
                    try:
                        with open(args.phase_file) as pf:
                            phase = pf.read().strip()
                    except OSError:
                        pass
                ram_used = (vm.total - vm.available) / 2**30
                row = [
                    datetime.datetime.now().isoformat(timespec="milliseconds"), f"{elapsed:.2f}",
                    _fmt(psutil.cpu_percent(None)), _fmt(h["soc_temp_c"]),
                    f"{ram_used:.2f}", f"{vm.total / 2**30:.2f}", f"{vm.percent:.1f}",
                    _fmt(g.get("util_pct")), _fmt(g.get("mem_used_mb")), _fmt(g.get("mem_total_mb")),
                    _fmt(g.get("temp_c")), _fmt(g.get("power_w"), 2), _fmt(g.get("gfx_clock_mhz")),
                    _fmt(n.get("temp_c")), _fmt(n.get("power_w"), 2),
                    _fmt(h["cpu_freq_mhz"], 0), _fmt(h["thermal_max_c"]), _fmt(g.get("sm_clock_mhz")),
                    _fmt(g.get("mem_clock_mhz")), _fmt(g.get("throttle_reasons")), phase,
                ]
                writer.writerow(row)
                f.flush()

                samples += 1
                peaks["soc"] = max(peaks["soc"], h["soc_temp_c"] or 0)
                peaks["gpu_t"] = max(peaks["gpu_t"], g.get("temp_c") or 0)
                peaks["gpu_p"] = max(peaks["gpu_p"], g.get("power_w") or 0)
                power_sum += g.get("power_w") or 0
                if not args.quiet:
                    print(f"\r[{elapsed:6.0f}s] CPU {row[2]:>5}% {row[15]:>5} MHz ({row[3]} C) | "
                          f"RAM {row[4]}/{row[5]} GB | GPU {row[7]:>3}% {row[10]} C {row[11]:>6} W "
                          f"{row[17]} MHz | {phase}   ", end="", flush=True)
                time.sleep(max(0.0, args.interval - (time.perf_counter() - t0 - elapsed)))
        except KeyboardInterrupt:
            pass

    print(f"\n\n{'=' * 16} Telemetry Summary {'=' * 16}")
    print(f" Samples          : {samples} ({time.perf_counter() - t0:.1f}s)")
    print(f" Peak SoC temp    : {peaks['soc']:.1f} C")
    print(f" Peak GPU temp    : {peaks['gpu_t']:.1f} C")
    print(f" Peak GPU power   : {peaks['gpu_p']:.2f} W")
    print(f" Avg GPU power    : {power_sum / max(samples, 1):.2f} W")
    print(f" CSV              : {args.output}")
    return 0
