#!/usr/bin/env bash
#
# Multi-threaded CPU & Memory Stress Benchmark for Linux (aarch64)
# Matches the mathematical workload and memory throughput of stress_cpu_ram.ps1.
#

set -euo pipefail

DURATION="${1:-30}"
CORES=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 20)

echo "=========================================================="
echo " NVIDIA RTX Spark - CPU & Memory Benchmark (Linux) "
echo " Threads: $CORES | Target Duration: ${DURATION}s"
echo "=========================================================="

python3 - "$DURATION" "$CORES" << 'EOF'
import sys
import time
import math
import multiprocessing as mp

duration = int(sys.argv[1])
threads = int(sys.argv[2])

def cpu_worker(duration_sec, return_dict, proc_id):
    start = time.perf_counter()
    ops = 0
    a = 1.000001
    b = 0.999999
    c = 1.5
    while (time.perf_counter() - start) < duration_sec:
        for _ in range(20000):
            a = math.sqrt(a * b + c) * math.sin(a)
            b = math.cos(b * 1.0001) + a * 0.00001
        ops += 20000
    return_dict[proc_id] = ops

def mem_worker(duration_sec, return_dict, proc_id):
    start = time.perf_counter()
    buf_size = 32 * 1024 * 1024  # 32 MB per worker
    src = bytearray(buf_size)
    bytes_moved = 0
    while (time.perf_counter() - start) < duration_sec:
        dst = src[:]
        dst[0] = (dst[0] + 1) & 0xFF
        bytes_moved += buf_size
    return_dict[proc_id] = bytes_moved

# 1. CPU Stress
print(f"\n[1/2] Running Multi-threaded CPU Stress ({threads} threads, {duration}s)...")
manager = mp.Manager()
return_dict = manager.dict()
procs = []

t0 = time.perf_counter()
for i in range(threads):
    p = mp.Process(target=cpu_worker, args=(duration, return_dict, i))
    procs.append(p)
    p.start()
for p in procs:
    p.join()
elapsed_cpu = time.perf_counter() - t0

total_ops = sum(return_dict.values())
mops_sec = round((total_ops / elapsed_cpu) / 1e6, 2)
print(f"  -> CPU Stress Completed in {round(elapsed_cpu, 2)}s")
print(f"  -> Total Operations: {total_ops:,}")
print(f"  -> Throughput Score: {mops_sec} Million Math Ops/sec (MOps/s) ({round(mops_sec/threads, 2)} MOps/s per core)")

# 2. Memory Stress
print(f"\n[2/2] Running Multi-threaded Memory Bandwidth Stress ({threads} threads, {duration}s)...")
return_dict_mem = manager.dict()
procs_mem = []

t1 = time.perf_counter()
for i in range(threads):
    p = mp.Process(target=mem_worker, args=(duration, return_dict_mem, i))
    procs_mem.append(p)
    p.start()
for p in procs_mem:
    p.join()
elapsed_mem = time.perf_counter() - t1

total_bytes = sum(return_dict_mem.values())
total_gb = round(total_bytes / (1024**3), 2)
gb_sec = round(total_gb / elapsed_mem, 2)
print(f"  -> Memory Stress Completed in {round(elapsed_mem, 2)}s")
print(f"  -> Total Data Streamed: {total_gb} GB")
print(f"  -> Memory Bandwidth: {gb_sec} GB/s")

print("\nAll tests completed successfully.")
EOF
