#!/usr/bin/env bash
#
# Master benchmark orchestrator for Linux (run locally on curiosity or via SSH)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"

DURATION="${1:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
METRIC_FILE="$RESULTS_DIR/metrics_linux_${TIMESTAMP}.csv"

echo "=========================================================="
echo " Starting Benchmark Run on Curiosity (Linux on ARM) "
echo " Stress Duration: ${DURATION}s per phase"
echo " Timestamp: $TIMESTAMP"
echo "=========================================================="

# 1. Start background telemetry monitor
echo "[1/5] Starting background telemetry monitor..."
"$SCRIPT_DIR/monitor_system.sh" "$METRIC_FILE" 1 0 &
MONITOR_PID=$!

echo "[2/5] Recording 5s baseline (idle)..."
sleep 5

# 2. Run CPU & RAM stress
echo "[3/5] Executing CPU & Memory stress test (${DURATION}s)..."
"$SCRIPT_DIR/stress_cpu_ram.sh" "$DURATION"

# 3. Run GPU Blackwell benchmark
echo "[4/5] Executing Blackwell GPU Benchmark (${DURATION}s)..."
"$SCRIPT_DIR/stress_gpu.sh" "$DURATION"

# 4. Run Disk benchmark
echo "[5/5] Executing NVMe Disk benchmark..."
"$SCRIPT_DIR/stress_disk.sh"

echo "Recording 5s cooldown (thermal descent)..."
sleep 5

# 5. Stop telemetry monitor
kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true

echo ""
echo "=========================================================="
echo " Linux Benchmark Run Completed Successfully!"
echo " Telemetry Metrics: $METRIC_FILE"
echo "=========================================================="
