#!/usr/bin/env bash
# Why cpu.* is 9-12 % below Windows on curiosity: per-operation cost of cpu_ram's math loop on one
# core of each kind, the core's delivered clock (CPPC feedback counters, scaling_cur_freq), and
# NumPy's FP64 GEMM (OpenBLAS) on all 20 cores vs the big cores only. Run idle, on AC, from the
# repo root; the flake's dev shell provides uv and the venv's NumPy.
set -eu
here=$(dirname "$0")
echo "power profile: $(tuned-adm active)"
for c in 5 15 0; do nix develop -c uv run python "$here/cpu-probe.py" $c 2048; done
nix develop -c sh -c "
uv run python $here/gemm-probe.py all-20
OPENBLAS_NUM_THREADS=10 taskset -c 5-9,15-19 uv run python $here/gemm-probe.py big-10
OPENBLAS_NUM_THREADS=5 taskset -c 5-9 uv run python $here/gemm-probe.py big-5
OPENBLAS_NUM_THREADS=1 taskset -c 5 uv run python $here/gemm-probe.py big-1"
