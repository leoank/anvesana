#!/usr/bin/env bash
#
# NVMe Storage Benchmark for Linux (direct I/O bypassing page cache)
# Matches the Sequential & Random 4K metrics of stress_disk.ps1.
#

set -euo pipefail

TEST_FILE="${1:-/tmp/disk_bench_temp.dat}"
SEQ_SIZE_MB="${2:-1024}"
RAND_OPS="${3:-5000}"

echo "=========================================================="
echo " NVIDIA RTX Spark - NVMe Storage Benchmark (Linux) "
echo " Target File: $TEST_FILE"
echo "=========================================================="

cleanup() {
    rm -f "$TEST_FILE"
}
trap cleanup EXIT

# 1. Sequential Write (Direct I/O)
echo ""
echo "[1/4] Sequential Write ($SEQ_SIZE_MB MB, oflag=direct)..."
t0=$(date +%s%N)
dd if=/dev/zero of="$TEST_FILE" bs=1M count="$SEQ_SIZE_MB" oflag=direct status=none
t1=$(date +%s%N)
elapsed_write=$(awk "BEGIN {printf \"%.3f\", ($t1 - $t0)/1000000000.0}")
seq_write_mb=$(awk "BEGIN {printf \"%.2f\", $SEQ_SIZE_MB / $elapsed_write}")
echo "  -> Sequential Write: $seq_write_mb MB/s"

# 2. Sequential Read (Direct I/O)
echo ""
echo "[2/4] Sequential Read ($SEQ_SIZE_MB MB, iflag=direct)..."
t0=$(date +%s%N)
dd if="$TEST_FILE" of=/dev/null bs=1M count="$SEQ_SIZE_MB" iflag=direct status=none
t1=$(date +%s%N)
elapsed_read=$(awk "BEGIN {printf \"%.3f\", ($t1 - $t0)/1000000000.0}")
seq_read_mb=$(awk "BEGIN {printf \"%.2f\", $SEQ_SIZE_MB / $elapsed_read}")
echo "  -> Sequential Read : $seq_read_mb MB/s"

# 3 & 4. Random 4K via Python direct I/O
echo ""
echo "[3/4] Random 4KB Write & [4/4] Random 4KB Read ($RAND_OPS ops)..."

python3 - "$TEST_FILE" "$RAND_OPS" << 'EOF'
import os
import sys
import time
import random

path = sys.argv[1]
num_ops = int(sys.argv[2])
block_size = 4096
buf = os.urandom(block_size)

file_size = os.path.getsize(path)
max_blocks = (file_size // block_size) - 1
random.seed(42)
offsets = [random.randint(0, max_blocks) * block_size for _ in range(num_ops)]

# Random 4K Write with O_SYNC / O_DIRECT
flags_write = os.O_RDWR | getattr(os, 'O_DIRECT', 0) | os.O_SYNC
fd = os.open(path, flags_write)
try:
    t0 = time.perf_counter()
    for off in offsets:
        os.lseek(fd, off, os.SEEK_SET)
        os.write(fd, buf)
    dt_write = time.perf_counter() - t0
    write_iops = round(num_ops / dt_write)
    write_lat = round((dt_write * 1000.0) / num_ops, 3)
    print(f"  -> Random 4K Write : {write_iops} IOPS (Latency: {write_lat} ms)")
finally:
    os.close(fd)

# Random 4K Read
flags_read = os.O_RDONLY | getattr(os, 'O_DIRECT', 0)
fd = os.open(path, flags_read)
try:
    t0 = time.perf_counter()
    for off in offsets:
        os.lseek(fd, off, os.SEEK_SET)
        _ = os.read(fd, block_size)
    dt_read = time.perf_counter() - t0
    read_iops = round(num_ops / dt_read)
    read_lat = round((dt_read * 1000.0) / num_ops, 3)
    print(f"  -> Random 4K Read  : {read_iops} IOPS (Latency: {read_lat} ms)")
finally:
    os.close(fd)
EOF

echo ""
echo "================ Disk Benchmark Summary ================"
echo " Sequential Write : $seq_write_mb MB/s"
echo " Sequential Read  : $seq_read_mb MB/s"
echo "========================================================="
