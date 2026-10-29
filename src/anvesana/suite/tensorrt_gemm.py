"""TensorRT GEMM engines: a single large linear layer Y = X * W^T per precision.

Networks are strongly typed (TensorRT 11 has no weakly-typed precision flags),
so precision is expressed the way quantized models are exported:
  fp16 / bf16   plain typed matmul
  fp8           static per-tensor Q/DQ on activations and weights
  nvfp4         dynamic block (1x16) quantization of the activations at runtime,
                static block-quantized weights; TensorRT fuses both into an FP4 GEMM
  *_sparse      weights pruned to a 2:4 pattern and built with SPARSE_WEIGHTS

The measured time includes whatever TensorRT fuses into the layer (e.g. the
runtime FP4 quantization of X), so this is a deployment number, not a pure
tensor-core one. Compare with `tensor` (ceiling) and `cublaslt` (bare GEMM).

Two backends with the same Python API:
  rtx   TensorRT for RTX (tensorrt_rtx): JIT-compiles kernels on the device and
        is the only one that builds engines on Windows on ARM. Use this for the
        Windows-vs-Linux comparison.
  trt   Full TensorRT (tensorrt): Linux only. Its win_arm64 wheel lacks the
        Myelin resource DLLs, so every MatMul/Conv build fails on Windows.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import time

import numpy as np
from cuda.bindings import driver as cu

from ..hw import cuda
from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, power_metrics

NAME = "tensorrt"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "TensorRT / TensorRT-RTX linear-layer engines (FP16/BF16/FP8/NVFP4, dense and 2:4 sparse)"

PRECISIONS = ["fp16", "bf16", "fp8", "nvfp4", "fp16_sparse", "fp8_sparse"]
BACKENDS = {"rtx": ("tensorrt_rtx", "tensorrt_rtx"), "trt": ("tensorrt", "tensorrt")}  # name: (module, metric prefix)

trt = None  # the selected backend module, bound by use_backend()
_LOGGER = None


def use_backend(name: str):
    global trt, _LOGGER
    trt = importlib.import_module(BACKENDS[name][0])
    _LOGGER = trt.Logger(trt.Logger.ERROR)
    return trt


def available_backends() -> list[str]:
    out = []
    for name, (module, _) in BACKENDS.items():
        if importlib.util.find_spec(module) is not None:
            out.append(name)
    return out


class _Builder:
    """Keeps numpy arrays alive until the engine is serialized (TensorRT
    references host weight memory rather than copying it)."""

    def __init__(self):
        self.builder = trt.Builder(_LOGGER)
        self.network = self.builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED))
        self._keep = []

    def const(self, array: np.ndarray, dtype=None):
        array = np.ascontiguousarray(array)
        self._keep.append(array)
        if dtype is None:
            weights = trt.Weights(array)
        else:
            weights = trt.Weights(dtype, array.ctypes.data, array.size)
        return self.network.add_constant(array.shape, weights).get_output(0)

    def scalar(self, value: float):
        return self.const(np.array(value, dtype=np.float32))


def make_weights(n: int, k: int, sparse: bool, rng) -> np.ndarray:
    w = rng.uniform(-1, 1, (n, k)).astype(np.float32)
    if sparse:
        # 2:4 structured sparsity along K: keep the first two of every four.
        w.reshape(n, k // 4, 4)[:, :, 2:] = 0
    return w


def build_engine(precision: str, m: int, n: int, k: int, rng) -> bytes:
    base, _, sparse = precision.partition("_")
    b = _Builder()
    net = b.network
    act_type = trt.DataType.BF16 if base == "bf16" else trt.DataType.HALF
    x = net.add_input("X", act_type, (m, k))
    w = make_weights(n, k, bool(sparse), rng)

    if base in ("fp16", "bf16"):
        if base == "bf16":
            wt = b.const(w)
            wt = net.add_cast(wt, trt.DataType.BF16).get_output(0)
        else:
            wt = b.const(w.astype(np.float16))
        xin = x
    elif base == "fp8":
        # Scales sized so |x| <= 1 uses the E4M3 range (max 448).
        sx, sw = b.scalar(1 / 256), b.scalar(1 / 256)
        q = net.add_quantize(x, sx, trt.DataType.FP8)
        xin = net.add_dequantize(q.get_output(0), sx, trt.DataType.HALF).get_output(0)
        wq = net.add_quantize(b.const(w.astype(np.float16)), sw, trt.DataType.FP8)
        wt = net.add_dequantize(wq.get_output(0), sw, trt.DataType.HALF).get_output(0)
    elif base == "nvfp4":
        # Activations: dynamic 1x16 block quantization -> FP4 data + FP8 block scales,
        # with a global FP32 scale applied to the block scales (two-level NVFP4 scaling).
        global_scale = b.scalar(1 / (6 * 448))
        dq = net.add_dynamic_quantize(x, 1, 16, trt.DataType.FP4, trt.DataType.FP8)
        dq.set_input(1, global_scale)
        x_scales = net.add_dequantize(dq.get_output(1), global_scale, trt.DataType.HALF).get_output(0)
        xin = net.add_dequantize(dq.get_output(0), x_scales, trt.DataType.HALF).get_output(0)
        # Weights: static block quantization with one scale per 16 values along K.
        w_scale = np.abs(w.reshape(n, k // 16, 16)).max(axis=2) / 6.0 + 1e-6
        ws = b.const(w_scale.astype(np.float16))
        wq = net.add_quantize(b.const(w.astype(np.float16)), ws, trt.DataType.FP4)
        wt = net.add_dequantize(wq.get_output(0), ws, trt.DataType.HALF).get_output(0)
    else:
        raise ValueError(precision)

    mm = net.add_matrix_multiply(xin, trt.MatrixOperation.NONE, wt, trt.MatrixOperation.TRANSPOSE)
    y = mm.get_output(0)
    y.name = "Y"
    net.mark_output(y)

    config = b.builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)
    config.builder_optimization_level = 5
    if hasattr(config, "set_compute_capability"):
        # TensorRT-RTX defaults to portable kernels for every supported GPU;
        # build for this GPU only so it can use arch-specific (sm_121a) kernels.
        config.num_compute_capabilities = 1
        config.set_compute_capability(trt.ComputeCapability.CURRENT, 0)
    if sparse:
        config.set_flag(trt.BuilderFlag.SPARSE_WEIGHTS)
    config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
    engine = b.builder.build_serialized_network(net, config)
    if engine is None:
        raise RuntimeError(f"TensorRT could not build a {precision} engine")
    return bytes(engine)


class Engine:
    def __init__(self, plan: bytes, m: int, n: int, k: int):
        self.runtime = trt.Runtime(_LOGGER)
        self.engine = self.runtime.deserialize_cuda_engine(plan)
        if hasattr(self.engine, "create_runtime_config"):
            # TensorRT-RTX JIT-compiles kernels on the device; compile them all up front.
            config = self.engine.create_runtime_config()
            config.dynamic_shapes_kernel_specialization_strategy = trt.DynamicShapesKernelSpecializationStrategy.EAGER
            self.context = self.engine.create_execution_context(config)
        else:
            self.context = self.engine.create_execution_context()
        # X is FP16 or BF16; random FP16 bit patterns are finite in either.
        self.x = cuda.DeviceBuffer(m * k * 2)
        self.y = cuda.DeviceBuffer(m * n * 2)
        self.x.upload(np.random.default_rng(1).uniform(-1, 1, m * k).astype(np.float16).view(np.uint8))
        self.context.set_tensor_address("X", self.x.ptr)
        self.context.set_tensor_address("Y", self.y.ptr)
        self.stream = cuda.check(cu.cuStreamCreate(0))
        self.flops = 2.0 * m * n * k

    def gemm_kernels(self) -> list[str]:
        """Names of the kernels TensorRT picked, to confirm the precision path."""
        import json

        info = json.loads(self.engine.create_engine_inspector().get_engine_information(trt.LayerInformationFormat.JSON))
        names = []
        for layer in info.get("Layers", []):
            if isinstance(layer, dict) and layer.get("TacticName"):
                names.append(f"{layer.get('LayerType', '?')}: {layer['TacticName']}")
        return names

    def time(self, seconds: float) -> float:
        stream = int(self.stream)
        for _ in range(10):  # warm-up, includes any first-run JIT
            self.context.execute_async_v3(stream)
        cuda.check(cu.cuStreamSynchronize(self.stream))
        timer = cuda.EventTimer(self.stream)
        timer.start()
        t0, iters = time.perf_counter(), 0
        while iters < 3 or time.perf_counter() - t0 < seconds:
            self.context.execute_async_v3(stream)
            iters += 1
        elapsed = timer.stop()
        return self.flops * iters / elapsed / 1e12

    def close(self):
        self.x.free()
        self.y.free()
        cuda.check(cu.cuStreamDestroy(self.stream))


def add_arguments(p):
    p.add_argument("--backend", choices=list(BACKENDS), default="rtx",
                   help="rtx = TensorRT for RTX (both OSes), trt = full TensorRT (Linux only)")
    p.add_argument("--precisions", default=",".join(PRECISIONS), help="subset of: " + ", ".join(PRECISIONS))
    p.add_argument("--size", type=int, default=8192, help="M = N = K")
    p.add_argument("--show-kernels", action="store_true", help="print the kernels TensorRT selected")


def run(args) -> list[Metric]:
    if args.backend == "trt" and sys.platform == "win32":
        print("Full TensorRT cannot build engines on Windows on ARM (wheel lacks Myelin resources); "
              "use --backend rtx.")
        return []
    try:
        use_backend(args.backend)
    except ImportError:
        print(f"{BACKENDS[args.backend][0]} is not installed (uv sync --extra tensorrt); skipping.")
        return []
    prefix = BACKENDS[args.backend][1]
    cuda.get_device()
    names = [n.strip() for n in args.precisions.split(",") if n.strip()]
    per_test = max(2.0, args.duration / 3)
    m = n = k = args.size
    banner(f"{prefix} linear-layer throughput", f"{prefix} {trt.__version__} | M=N=K={m} | {per_test:.0f}s per precision")
    rng = np.random.default_rng(0)
    metrics = []
    for i, name in enumerate(names, 1):
        step(f"[{i}/{len(names)}] {name}: building engine...")
        engine = None
        try:
            t0 = time.perf_counter()
            plan = build_engine(name, m, n, k, rng)
            print(f"     built in {time.perf_counter() - t0:.1f}s")
            engine = Engine(plan, m, n, k)
            if args.show_kernels:
                for kname in engine.gemm_kernels():
                    print(f"     {kname}")
            with GpuSampler() as s:
                tflops = engine.time(per_test)
        except Exception as e:  # TensorRT reports unsupported precisions as generic errors
            print(f"  !! skipped: {e}")
            continue
        finally:
            if engine:
                engine.close()
        report(name, tflops, "TFLOPS", s.describe())
        metrics.append(Metric(f"{prefix}.{name}", tflops, "TFLOPS"))
        metrics += power_metrics(f"{prefix}.{name}", tflops, s)

    summary(f"{prefix} Summary", [m for m in metrics if m.unit == "TFLOPS"])
    return metrics
