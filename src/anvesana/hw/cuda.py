"""Thin wrapper over the CUDA driver API (cuda-python) and NVRTC.

Everything runs in the device's *primary* context so that runtime-API
libraries loaded into the same process (cuBLASLt, TensorRT) share it.
No CUDA toolkit is required: kernels are either PTX (JIT-compiled by the
driver) or CUDA C++ compiled at runtime by NVRTC from the pip wheel.
"""

from __future__ import annotations

import functools

import numpy as np
from cuda.bindings import driver as cu
from cuda.bindings import nvrtc


class CudaError(RuntimeError):
    pass


def check(result):
    """Unpack a cuda-python ``(err, *values)`` tuple, raising on failure."""
    err, *values = result
    if isinstance(err, nvrtc.nvrtcResult):
        if err != nvrtc.nvrtcResult.NVRTC_SUCCESS:
            raise CudaError(f"NVRTC error: {err.name}")
    elif int(err) != 0:
        _, name = cu.cuGetErrorName(err)
        raise CudaError(f"CUDA error: {name.decode() if name else err}")
    if not values:
        return None
    return values[0] if len(values) == 1 else tuple(values)


class Device:
    def __init__(self, ordinal: int = 0):
        check(cu.cuInit(0))
        self.handle = check(cu.cuDeviceGet(ordinal))
        self.ctx = check(cu.cuDevicePrimaryCtxRetain(self.handle))
        check(cu.cuCtxSetCurrent(self.ctx))

    def attr(self, name: str) -> int:
        enum = getattr(cu.CUdevice_attribute, "CU_DEVICE_ATTRIBUTE_" + name)
        return check(cu.cuDeviceGetAttribute(enum, self.handle))

    @functools.cached_property
    def name(self) -> str:
        return check(cu.cuDeviceGetName(256, self.handle)).split(b"\0")[0].decode()

    @functools.cached_property
    def cc(self) -> tuple[int, int]:
        return self.attr("COMPUTE_CAPABILITY_MAJOR"), self.attr("COMPUTE_CAPABILITY_MINOR")

    @property
    def sm_count(self) -> int:
        return self.attr("MULTIPROCESSOR_COUNT")

    @property
    def total_mem_bytes(self) -> int:
        return check(cu.cuDeviceTotalMem(self.handle))

    @property
    def arch(self) -> str:
        """NVRTC target, using the arch-specific ('a') variant where it exists
        so Blackwell-only instructions (block-scaled FP4 MMA) are available."""
        major, minor = self.cc
        return f"sm_{major}{minor}" + ("a" if major >= 9 else "")

    def info(self) -> dict:
        return {
            "name": self.name,
            "compute_capability": "%d.%d" % self.cc,
            "sm_count": self.sm_count,
            "total_mem_gb": round(self.total_mem_bytes / 1e9, 2),
            "driver_version": check(cu.cuDriverGetVersion()),
        }

    @staticmethod
    def synchronize():
        check(cu.cuCtxSynchronize())


@functools.lru_cache(maxsize=None)
def get_device(ordinal: int = 0) -> Device:
    return Device(ordinal)


def compile_cuda(source: str, arch: str, name: str = "kernel.cu", options: list[str] = ()) -> bytes:
    """Compile CUDA C++ to a cubin with NVRTC."""
    prog = check(nvrtc.nvrtcCreateProgram(source.encode(), name.encode(), 0, [], []))
    opts = [f"--gpu-architecture={arch}".encode(), b"--std=c++17", *(o.encode() for o in options)]
    err, = nvrtc.nvrtcCompileProgram(prog, len(opts), opts)
    if err != nvrtc.nvrtcResult.NVRTC_SUCCESS:
        size = check(nvrtc.nvrtcGetProgramLogSize(prog))
        log = b" " * size
        nvrtc.nvrtcGetProgramLog(prog, log)
        raise CudaError(f"NVRTC compilation of {name} failed:\n{log.decode(errors='replace')}")
    size = check(nvrtc.nvrtcGetCUBINSize(prog))
    cubin = b" " * size
    check(nvrtc.nvrtcGetCUBIN(prog, cubin))
    check(nvrtc.nvrtcDestroyProgram(prog))
    return cubin


def nvrtc_version() -> str:
    return "%d.%d" % check(nvrtc.nvrtcVersion())


class Module:
    """A loaded CUDA module from a cubin or a PTX string (driver JIT)."""

    def __init__(self, image: bytes | str):
        if isinstance(image, str):
            image = image.encode() + b"\0"
        self.handle = check(cu.cuModuleLoadData(image))

    def kernel(self, name: str) -> "Kernel":
        return Kernel(check(cu.cuModuleGetFunction(self.handle, name.encode())))

    def unload(self):
        check(cu.cuModuleUnload(self.handle))


class KernelArgs:
    """Kernel parameters as numpy scalars, kept alive for repeated launches."""

    def __init__(self, *args):
        self._values = [np.array([a], dtype=a.dtype) for a in args]
        self._ptrs = np.array([v.ctypes.data for v in self._values], dtype=np.uint64)

    @property
    def address(self) -> int:
        return self._ptrs.ctypes.data


class Kernel:
    def __init__(self, fn):
        self.fn = fn

    def launch(self, grid: int, block: int, args: KernelArgs, shmem: int = 0, stream=0):
        check(cu.cuLaunchKernel(self.fn, grid, 1, 1, block, 1, 1, shmem, stream, args.address, 0))


class DeviceBuffer:
    def __init__(self, nbytes: int):
        self.nbytes = nbytes
        self.ptr = int(check(cu.cuMemAlloc(nbytes)))

    def upload(self, array: np.ndarray):
        assert array.nbytes <= self.nbytes
        check(cu.cuMemcpyHtoD(self.ptr, np.ascontiguousarray(array).ctypes.data, array.nbytes))

    def fill_u8(self, value: int):
        check(cu.cuMemsetD8(self.ptr, value, self.nbytes))

    def free(self):
        if self.ptr:
            check(cu.cuMemFree(self.ptr))
            self.ptr = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.free()


class EventTimer:
    """Measures GPU time between two points in a stream with CUDA events."""

    def __init__(self, stream=0):
        self.stream = stream
        self._start = check(cu.cuEventCreate(0))
        self._stop = check(cu.cuEventCreate(0))

    def start(self):
        check(cu.cuEventRecord(self._start, self.stream))

    def stop(self) -> float:
        """Returns elapsed seconds."""
        check(cu.cuEventRecord(self._stop, self.stream))
        check(cu.cuEventSynchronize(self._stop))
        return check(cu.cuEventElapsedTime(self._start, self._stop)) / 1000.0
