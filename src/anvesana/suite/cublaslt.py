"""Dense GEMM throughput through cuBLASLt, NVIDIA's production GEMM library.

On Blackwell cuBLASLt dispatches to CUTLASS-derived kernels, so this is what
real applications (PyTorch, TensorRT-LLM, llama.cpp CUDA) get for a large
matmul. Bound via ctypes to the cublasLt library from the nvidia-cublas wheel,
which exists for both win_arm64 and linux_aarch64.

Each precision asks the heuristic for several candidate algorithms, times
them briefly, then runs the fastest for the sustained measurement.
"""

from __future__ import annotations

import ctypes
import time

import numpy as np

from ..hw import cuda
from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, power_metrics

NAME = "cublaslt"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "cuBLASLt GEMM TFLOPS for FP32/TF32/FP16/BF16/FP8/NVFP4"

# cudaDataType_t
R_32F, R_16F, R_16BF, R_8F_E4M3, R_4F_E2M1 = 0, 2, 14, 28, 33
# cublasComputeType_t
COMPUTE_32F, COMPUTE_32F_FAST_TF32 = 68, 77
# cublasLtMatmulDescAttributes_t
DESC_TRANSA, DESC_TRANSB = 3, 4
DESC_A_SCALE_POINTER, DESC_B_SCALE_POINTER = 17, 18
DESC_A_SCALE_MODE, DESC_B_SCALE_MODE = 31, 32
SCALE_MODE_VEC16_UE4M3 = 1
PREF_MAX_WORKSPACE_BYTES = 1
OP_N, OP_T = 0, 1

WORKSPACE_BYTES = 64 * 2**20


class Algo(ctypes.Structure):
    _fields_ = [("data", ctypes.c_uint64 * 8)]


class HeuristicResult(ctypes.Structure):
    _fields_ = [("algo", Algo), ("workspaceSize", ctypes.c_size_t), ("state", ctypes.c_int),
                ("wavesCount", ctypes.c_float), ("reserved", ctypes.c_int * 4)]


# name: (A/B type, C/D type, compute type, element bits of A/B, block-scaled)
PRECISIONS = {
    "fp32": (R_32F, R_32F, COMPUTE_32F, 32, False),
    "tf32": (R_32F, R_32F, COMPUTE_32F_FAST_TF32, 32, False),
    "fp16": (R_16F, R_16F, COMPUTE_32F, 16, False),
    "bf16": (R_16BF, R_16BF, COMPUTE_32F, 16, False),
    "fp8": (R_8F_E4M3, R_16BF, COMPUTE_32F, 8, False),
    "nvfp4": (R_4F_E2M1, R_16BF, COMPUTE_32F, 4, True),
}


def _load_library():
    from cuda import pathfinder

    lib = ctypes.CDLL(pathfinder.load_nvidia_dynamic_lib("cublasLt").abs_path)
    for fn in ("cublasLtCreate", "cublasLtMatmulDescCreate", "cublasLtMatmulDescSetAttribute",
               "cublasLtMatrixLayoutCreate", "cublasLtMatmulPreferenceCreate",
               "cublasLtMatmulPreferenceSetAttribute", "cublasLtMatmulAlgoGetHeuristic", "cublasLtMatmul",
               "cublasLtMatmulDescDestroy", "cublasLtMatrixLayoutDestroy", "cublasLtMatmulPreferenceDestroy"):
        getattr(lib, fn).restype = ctypes.c_int
    lib.cublasLtMatrixLayoutCreate.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint64, ctypes.c_uint64,
                                               ctypes.c_int64]
    lib.cublasLtGetVersion.restype = ctypes.c_size_t
    return lib


class CublasLtError(RuntimeError):
    pass


def _ok(status: int, what: str):
    if status != 0:
        raise CublasLtError(f"{what} failed with cublasStatus {status}")


def random_bytes(nbytes: int, bits: int, rng: np.random.Generator) -> np.ndarray:
    """Random operands in a sane numeric range. Real data matters: constant
    operands toggle fewer bits, draw less power and inflate clocks."""
    if bits == 32:
        return rng.uniform(-1, 1, nbytes // 4).astype(np.float32).view(np.uint8)
    if bits == 16:
        return rng.uniform(-1, 1, nbytes // 2).astype(np.float16).view(np.uint8)
    raw = rng.integers(0, 256, nbytes, dtype=np.uint8)
    if bits == 8:
        return raw & 0xB7  # E4M3 with exponent <= 0110: |x| < 2, never NaN
    return raw  # every E2M1 nibble is a finite value


class Gemm:
    """One cuBLASLt matmul D = A^T * B (the "TN" layout FP8/FP4 require)."""

    def __init__(self, lib, handle, precision: str, m: int, n: int, k: int, rng: np.random.Generator):
        ab_type, cd_type, compute, bits, scaled = PRECISIONS[precision]
        self.lib, self.handle = lib, handle
        self.flops = 2.0 * m * n * k
        self._bufs = []

        def buf(nbytes):
            b = cuda.DeviceBuffer(nbytes)
            self._bufs.append(b)
            return b

        cd_bytes = 4 if cd_type == R_32F else 2
        self.a = buf(m * k * bits // 8)
        self.b = buf(n * k * bits // 8)
        self.d = buf(m * n * cd_bytes)
        self.a.upload(random_bytes(self.a.nbytes, bits, rng))
        self.b.upload(random_bytes(self.b.nbytes, bits, rng))
        self.workspace = buf(WORKSPACE_BYTES)

        self.desc = ctypes.c_void_p()
        _ok(lib.cublasLtMatmulDescCreate(ctypes.byref(self.desc), compute, R_32F), "MatmulDescCreate")
        self._set(DESC_TRANSA, ctypes.c_int32(OP_T))
        self._set(DESC_TRANSB, ctypes.c_int32(OP_N))
        if scaled:
            # One UE4M3 scale per 16 elements along K, 1.0 everywhere. Sized
            # generously: cuBLASLt pads the scale tensors to 128x4 tiles.
            sfa = buf((m + 128) * (k // 16 + 4))
            sfb = buf((n + 128) * (k // 16 + 4))
            sfa.fill_u8(0x38)
            sfb.fill_u8(0x38)
            self._set(DESC_A_SCALE_MODE, ctypes.c_int32(SCALE_MODE_VEC16_UE4M3))
            self._set(DESC_B_SCALE_MODE, ctypes.c_int32(SCALE_MODE_VEC16_UE4M3))
            self._set(DESC_A_SCALE_POINTER, ctypes.c_void_p(sfa.ptr))
            self._set(DESC_B_SCALE_POINTER, ctypes.c_void_p(sfb.ptr))

        self.layouts = []
        for dtype, rows, cols in ((ab_type, k, m), (ab_type, k, n), (cd_type, m, n)):
            layout = ctypes.c_void_p()
            _ok(lib.cublasLtMatrixLayoutCreate(ctypes.byref(layout), dtype, rows, cols, rows), "MatrixLayoutCreate")
            self.layouts.append(layout)
        self.alpha, self.beta = ctypes.c_float(1.0), ctypes.c_float(0.0)
        self.algo = None

    def _set(self, attr, value):
        _ok(self.lib.cublasLtMatmulDescSetAttribute(self.desc, attr, ctypes.byref(value), ctypes.sizeof(value)),
            f"MatmulDescSetAttribute({attr})")

    def candidates(self, count: int = 8) -> list[Algo]:
        pref = ctypes.c_void_p()
        _ok(self.lib.cublasLtMatmulPreferenceCreate(ctypes.byref(pref)), "PreferenceCreate")
        ws = ctypes.c_uint64(WORKSPACE_BYTES)
        _ok(self.lib.cublasLtMatmulPreferenceSetAttribute(pref, PREF_MAX_WORKSPACE_BYTES, ctypes.byref(ws), 8),
            "PreferenceSetAttribute")
        results = (HeuristicResult * count)()
        returned = ctypes.c_int(0)
        a, b, c = self.layouts
        status = self.lib.cublasLtMatmulAlgoGetHeuristic(self.handle, self.desc, a, b, c, c, pref, count, results,
                                                         ctypes.byref(returned))
        self.lib.cublasLtMatmulPreferenceDestroy(pref)
        _ok(status, "MatmulAlgoGetHeuristic")
        if returned.value == 0:
            raise CublasLtError("no algorithm available for this precision/shape")
        return [results[i].algo for i in range(returned.value)]

    def launch(self, algo: Algo):
        a, b, c = self.layouts
        _ok(self.lib.cublasLtMatmul(self.handle, self.desc, ctypes.byref(self.alpha),
                                    ctypes.c_void_p(self.a.ptr), a, ctypes.c_void_p(self.b.ptr), b,
                                    ctypes.byref(self.beta), ctypes.c_void_p(self.d.ptr), c,
                                    ctypes.c_void_p(self.d.ptr), c, ctypes.byref(algo),
                                    ctypes.c_void_p(self.workspace.ptr), ctypes.c_size_t(WORKSPACE_BYTES), None),
            "Matmul")

    def time(self, algo: Algo, seconds: float = 0.0, min_iters: int = 3) -> tuple[float, int]:
        """Runs ``algo`` for at least ``min_iters`` launches / ``seconds``; returns TFLOPS."""
        self.launch(algo)
        timer = cuda.EventTimer()
        timer.start()
        t0, iters = time.perf_counter(), 0
        while iters < min_iters or time.perf_counter() - t0 < seconds:
            self.launch(algo)
            iters += 1
        elapsed = timer.stop()
        return self.flops * iters / elapsed / 1e12, iters

    def autotune(self) -> float:
        best = 0.0
        for algo in self.candidates():
            try:
                tflops, _ = self.time(algo, min_iters=5)
            except CublasLtError:
                continue
            if tflops > best:
                best, self.algo = tflops, algo
        if self.algo is None:
            raise CublasLtError("every candidate algorithm failed")
        return best

    def close(self):
        for layout in self.layouts:
            self.lib.cublasLtMatrixLayoutDestroy(layout)
        self.lib.cublasLtMatmulDescDestroy(self.desc)
        for b in self._bufs:
            b.free()


def add_arguments(p):
    p.add_argument("--precisions", default=",".join(PRECISIONS), help="subset of: " + ", ".join(PRECISIONS))
    p.add_argument("--size", type=int, default=8192, help="M = N = K")


def run(args) -> list[Metric]:
    cuda.get_device()  # makes the primary context current before cuBLASLt loads the runtime
    lib = _load_library()
    handle = ctypes.c_void_p()
    _ok(lib.cublasLtCreate(ctypes.byref(handle)), "cublasLtCreate")
    names = [n.strip() for n in args.precisions.split(",") if n.strip()]
    per_test = max(2.0, args.duration / 3)
    size = args.size
    banner("cuBLASLt GEMM throughput", f"cuBLASLt {lib.cublasLtGetVersion()} | M=N=K={size} | {per_test:.0f}s per precision")

    rng = np.random.default_rng(0)
    metrics = []
    for i, name in enumerate(names, 1):
        step(f"[{i}/{len(names)}] {name}: autotuning...")
        gemm = None
        try:
            gemm = Gemm(lib, handle, name, size, size, size, rng)
            gemm.autotune()
            with GpuSampler() as s:
                tflops, _ = gemm.time(gemm.algo, seconds=per_test)
        except (CublasLtError, cuda.CudaError) as e:
            print(f"  !! skipped: {e}")
            continue
        finally:
            if gemm:
                gemm.close()
        report(name, tflops, "TFLOPS", s.describe())
        metrics.append(Metric(f"cublaslt.{name}", tflops, "TFLOPS"))
        metrics += power_metrics(f"cublaslt.{name}", tflops, s)

    summary("cuBLASLt Summary", [m for m in metrics if m.unit == "TFLOPS"])
    return metrics
