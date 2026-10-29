"""Captures everything about the machine and software that can move benchmark results."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

LIBRARIES = ["cuda-bindings", "nvidia-cublas", "nvidia-cuda-nvrtc", "tensorrt-rtx", "tensorrt-cu13", "nvidia-cutlass",
             "nvidia-cuda-nvcc", "numpy"]


def os_tag() -> str:
    return {"win32": "windows", "linux": "linux", "darwin": "macos"}.get(sys.platform, sys.platform)


def hostname() -> str:
    return socket.gethostname().lower()


def capture() -> dict:
    import psutil

    info = {
        "os": os_tag(),
        "hostname": hostname(),
        "platform": platform.platform(),
        "kernel": platform.release() if sys.platform != "win32" else platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu": _cpu_name(),
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 2),
        "power_profile": _power_profile(),
        "on_ac_power": _on_ac_power(),
        "libraries": _library_versions(),
    }
    try:
        from ..hw import cuda

        dev = cuda.get_device()
        info["gpu"] = dev.info()
        info["nvrtc"] = cuda.nvrtc_version()
    except Exception as e:  # a missing GPU stack must not break CPU/disk-only machines
        info["gpu_error"] = str(e)
    try:
        import pynvml

        from ..hw.telemetry import max_sm_clock_mhz, power_limit_w

        pynvml.nvmlInit()
        info["nvidia_driver"] = pynvml.nvmlSystemGetDriverVersion()
        info["gpu_power_limit_w"] = power_limit_w()
        info["gpu_max_sm_clock_mhz"] = max_sm_clock_mhz()
        # On unified-memory SoCs the CPU/GPU split is configurable (e.g. 64/64 vs 32/96 GB
        # on the N1X) and changes results; record the GPU side next to ram_gb.
        mem = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
        info["gpu_mem_total_gb"] = round(mem.total / 1e9, 2)
    except Exception:
        pass
    return info


def source_revision() -> dict:
    """Git commit of the benchmark code, so a methodology change shows up in the record."""
    root = Path(__file__).resolve().parents[3]
    git = shutil.which("git")
    if not git:
        return {}
    try:
        commit = subprocess.run([git, "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        if commit.returncode != 0:
            return {}
        dirty = subprocess.run([git, "status", "--porcelain", "--", "src"], cwd=root, capture_output=True, text=True,
                               timeout=10)
        return {"git_commit": commit.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return {}


def _library_versions() -> dict:
    out = {}
    for lib in LIBRARIES:
        try:
            out[lib] = version(lib)
        except PackageNotFoundError:
            continue
    return out


def _on_ac_power():
    import psutil

    try:
        battery = psutil.sensors_battery()
    except Exception:
        return None
    return None if battery is None else bool(battery.power_plugged)


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    elif os.path.exists("/proc/cpuinfo"):
        # aarch64 /proc/cpuinfo has no model name; the device-tree / DMI model is the best label.
        for path in ("/sys/firmware/devicetree/base/model", "/sys/devices/virtual/dmi/id/product_name"):
            try:
                with open(path) as f:
                    return f.read().strip("\0\n ")
            except OSError:
                continue
    return platform.processor() or platform.machine()


# Windows 11 "power mode" (Settings > Power) is an overlay on top of the power
# plan; powercfg /getactivescheme only reports the plan.
_OVERLAYS = {
    "00000000-0000-0000-0000-000000000000": "Balanced",
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best power efficiency",
    "3af9b8d9-7c97-431d-ad78-34a8bfea439f": "Better performance",
    "ded574b5-45a0-4f42-8737-46345c09c238": "Best performance",
}


def _power_profile() -> str:
    """Active OS power policy; the likeliest cause of run-to-run and OS differences."""
    if sys.platform == "win32":
        return _windows_power_profile()
    parts = []
    for label, path in (("governor", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
                        ("platform_profile", "/sys/firmware/acpi/platform_profile")):
        try:
            with open(path) as f:
                parts.append(f"{label}={f.read().strip()}")
        except OSError:
            continue
    return ", ".join(parts)


def _windows_power_profile() -> str:
    """e.g. "mode=Best performance, plan=Balanced" (mode for the current AC/battery state)."""
    import winreg

    parts = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes")
        value = "ActiveOverlayDcPowerScheme" if _on_ac_power() is False else "ActiveOverlayAcPowerScheme"
        try:
            guid = winreg.QueryValueEx(key, value)[0].lower()
        except OSError:
            guid = "00000000-0000-0000-0000-000000000000"
        parts.append(f"mode={_OVERLAYS.get(guid, guid)}")
    except OSError:
        pass
    try:
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=10).stdout
        parts.append(f"plan={out.split('(')[-1].rstrip(')\n ') if '(' in out else out.strip()}")
    except (OSError, subprocess.SubprocessError):
        pass
    return ", ".join(parts)
