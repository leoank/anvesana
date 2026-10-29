"""Hardware sensor readers shared by the telemetry monitor and the GPU benchmarks.

GPU/NPU sensors come from NVML (same library nvidia-smi uses) on both OSes.
CPU frequency and thermal zones come from PDH performance counters on Windows
(no admin rights or WMI round-trips needed) and from sysfs on Linux.
"""

from __future__ import annotations

import ctypes
import glob
import sys
import threading
import time

try:
    import pynvml
except ImportError:  # GPU telemetry is optional for CPU/disk-only runs
    pynvml = None


class Gpu:
    """NVML view of one device. Every reading returns None if unsupported."""

    def __init__(self, index: int = 0):
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        self.name = pynvml.nvmlDeviceGetName(self.handle)

    @staticmethod
    def count() -> int:
        if pynvml is None:
            return 0
        try:
            pynvml.nvmlInit()
            return pynvml.nvmlDeviceGetCount()
        except pynvml.NVMLError:
            return 0

    def _get(self, fn, *args):
        try:
            return fn(self.handle, *args)
        except pynvml.NVMLError:
            return None

    def read(self) -> dict:
        util = self._get(pynvml.nvmlDeviceGetUtilizationRates)
        mem = self._get(pynvml.nvmlDeviceGetMemoryInfo)
        power_mw = self._get(pynvml.nvmlDeviceGetPowerUsage)
        return {
            "util_pct": util.gpu if util else None,
            "mem_used_mb": round(mem.used / 2**20) if mem else None,
            "mem_total_mb": round(mem.total / 2**20) if mem else None,
            "temp_c": self._get(pynvml.nvmlDeviceGetTemperature, pynvml.NVML_TEMPERATURE_GPU),
            "power_w": round(power_mw / 1000.0, 2) if power_mw is not None else None,
            "gfx_clock_mhz": self._get(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_GRAPHICS),
            "sm_clock_mhz": self._get(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_SM),
            "mem_clock_mhz": self._get(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_MEM),
            "throttle_reasons": self._get(pynvml.nvmlDeviceGetCurrentClocksEventReasons),
        }


def max_sm_clock_mhz(index: int = 0) -> int | None:
    """From NVML; the driver API's CLOCK_RATE attribute is bogus under WDDM."""
    try:
        gpu = Gpu(index)
        return pynvml.nvmlDeviceGetMaxClockInfo(gpu.handle, pynvml.NVML_CLOCK_SM)
    except Exception:
        return None


def power_limit_w(index: int = 0) -> float | None:
    try:
        gpu = Gpu(index)
        return pynvml.nvmlDeviceGetEnforcedPowerLimit(gpu.handle) / 1000.0
    except Exception:
        return None


class GpuSampler:
    """Samples GPU power/clock/temperature on a background thread while a
    benchmark runs, so results can be reported per watt and per clock."""

    def __init__(self, interval_s: float = 0.1, index: int = 0):
        self.interval_s = interval_s
        self.samples: list[dict] = []
        self._stop = threading.Event()
        try:
            self._gpu = Gpu(index)
        except Exception:
            self._gpu = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.wait(self.interval_s):
            self.samples.append(self._gpu.read())

    def __enter__(self):
        if self._gpu:
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._gpu:
            self._thread.join()

    def _values(self, key: str) -> list[float]:
        # Skip the first samples while the GPU ramps up from idle.
        warm = self.samples[len(self.samples) // 10:]
        return [s[key] for s in warm if s.get(key) is not None]

    def avg(self, key: str) -> float | None:
        vals = self._values(key)
        return sum(vals) / len(vals) if vals else None

    def peak(self, key: str) -> float | None:
        vals = self._values(key)
        return max(vals) if vals else None

    def describe(self) -> str:
        p, c, t = self.avg("power_w"), self.avg("sm_clock_mhz"), self.peak("temp_c")
        if p is None:
            return ""
        return f"[{p:.1f} W avg, {c or 0:.0f} MHz SM, {t or 0:.0f} C peak]"


def power_metrics(prefix: str, value: float, sampler: GpuSampler, unit: str = "TFLOPS"):
    """Average power, efficiency and SM clock recorded while ``value`` was measured."""
    from ..framework.records import Metric

    power, clock = sampler.avg("power_w"), sampler.avg("sm_clock_mhz")
    out = []
    if power:
        out.append(Metric(f"{prefix}.avg_power", power, "W", higher_is_better=False))
        out.append(Metric(f"{prefix}.efficiency", value / power, f"{unit}/W"))
    if clock:
        out.append(Metric(f"{prefix}.avg_sm_clock", clock, "MHz"))
    return out


# --------------------------------------------------------------------------- Windows PDH


class _PdhValue(ctypes.Structure):
    _fields_ = [("CStatus", ctypes.c_ulong), ("doubleValue", ctypes.c_double)]


class _PdhItem(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _PdhValue)]


class PdhCounters:
    """Reads wildcard performance counters, e.g. every thermal zone at once."""

    PDH_FMT_DOUBLE = 0x00000200
    PDH_FMT_NOCAP100 = 0x00008000
    PDH_MORE_DATA = 0x800007D2

    def __init__(self, paths: dict[str, str]):
        self._pdh = ctypes.WinDLL("pdh")
        for fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW"):
            getattr(self._pdh, fn).restype = ctypes.c_ulong
        self._query = ctypes.c_void_p()
        self._check(self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)))
        self._counters = {}
        for key, path in paths.items():
            handle = ctypes.c_void_p()
            if self._pdh.PdhAddEnglishCounterW(self._query, path, 0, ctypes.byref(handle)) == 0:
                self._counters[key] = handle
        self._pdh.PdhCollectQueryData(self._query)  # rate counters need a priming sample

    @staticmethod
    def _check(status):
        if status != 0:
            raise OSError(f"PDH error 0x{status:08X}")

    def read(self) -> dict[str, dict[str, float]]:
        self._pdh.PdhCollectQueryData(self._query)
        out = {}
        fmt = self.PDH_FMT_DOUBLE | self.PDH_FMT_NOCAP100
        for key, handle in self._counters.items():
            size, count = ctypes.c_ulong(0), ctypes.c_ulong(0)
            status = self._pdh.PdhGetFormattedCounterArrayW(handle, fmt, ctypes.byref(size), ctypes.byref(count), None)
            if status != self.PDH_MORE_DATA:
                continue
            buf = ctypes.create_string_buffer(size.value)
            if self._pdh.PdhGetFormattedCounterArrayW(handle, fmt, ctypes.byref(size), ctypes.byref(count), buf) != 0:
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_PdhItem))
            out[key] = {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value)}
        return out


# --------------------------------------------------------------------------- CPU / thermal


class HostSensors:
    """CPU frequency and thermal zones.

    ``soc_temp_c`` is the SoC zone (ACPI TSOC on Windows, a *soc* sysfs zone on
    Linux, else the hottest zone); ``thermal_max_c`` is the hottest zone overall.
    """

    def __init__(self):
        self._pdh = None
        if sys.platform == "win32":
            try:
                self._pdh = PdhCounters({
                    "temp": r"\Thermal Zone Information(*)\High Precision Temperature",
                    "perf": r"\Processor Information(_Total)\% Processor Performance",
                    "freq": r"\Processor Information(_Total)\Processor Frequency",
                })
            except OSError:
                self._pdh = None
        else:
            self._zones = []
            for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
                try:
                    with open(f"{zone}/type") as f:
                        self._zones.append((f.read().strip(), f"{zone}/temp"))
                except OSError:
                    continue

    def read(self) -> dict:
        if sys.platform == "win32":
            return self._read_windows()
        return self._read_linux()

    def _read_windows(self) -> dict:
        data = self._pdh.read() if self._pdh else {}
        # High Precision Temperature is in tenths of a Kelvin. Only the T* zones
        # are sensors; PSOC/PSYS are policy zones whose values swing from
        # -26 C to 90 C at idle.
        zones = {}
        for name, v in data.get("temp", {}).items():
            zone = name.split(".")[-1].upper()
            if zone.startswith("T") and v > 0:
                zones[zone] = v / 10.0 - 273.15
        perf = next(iter(data.get("perf", {}).values()), None)
        nominal = next(iter(data.get("freq", {}).values()), None)
        return {
            "soc_temp_c": zones.get("TSOC", max(zones.values(), default=None)),
            "thermal_max_c": max(zones.values(), default=None),
            "cpu_freq_mhz": nominal * perf / 100.0 if perf and nominal else None,
            "zones": zones,
        }

    def _read_linux(self) -> dict:
        zones = {}
        for name, path in self._zones:
            try:
                with open(path) as f:
                    raw = int(f.read())
            except (OSError, ValueError):
                continue
            if raw > 1000:
                zones[name] = raw / 1000.0
        soc = next((v for k, v in zones.items() if "soc" in k.lower()), max(zones.values(), default=None))
        freqs = []
        for path in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"):
            try:
                with open(path) as f:
                    freqs.append(int(f.read()) / 1000.0)
            except (OSError, ValueError):
                continue
        return {
            "soc_temp_c": soc,
            "thermal_max_c": max(zones.values(), default=None),
            "cpu_freq_mhz": sum(freqs) / len(freqs) if freqs else None,
            "zones": zones,
        }


def wait_for_idle(max_wait_s: float = 30.0, temp_c: float = 50.0):
    """Lets the GPU cool between benchmarks so each starts from a similar state."""
    try:
        gpu = Gpu(0)
    except Exception:
        return
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        t = gpu.read()["temp_c"]
        if t is None or t <= temp_c:
            return
        time.sleep(1.0)
