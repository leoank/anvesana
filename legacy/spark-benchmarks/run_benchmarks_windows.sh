#!/usr/bin/env bash
#
# Master benchmark orchestrator for Windows (runs from your Mac via SSH to curiosity)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"

DURATION="${1:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REMOTE_DIR="${REMOTE_DIR:?set REMOTE_DIR to the benchmarks folder on the Windows host, e.g. C:/Users/<you>/benchmarks}"

echo "=========================================================="
echo " Starting Benchmark Run on Curiosity (Windows on ARM) "
echo " Stress Duration: ${DURATION}s per phase"
echo " Timestamp: $TIMESTAMP"
echo "=========================================================="

# 1. Prepare remote folder and copy scripts
echo "[1/3] Syncing benchmark suite to curiosity..."
ssh curiosity "New-Item -ItemType Directory -Path '$REMOTE_DIR' -Force | Out-Null"
scp -q "$SCRIPT_DIR/monitor_system.ps1" \
       "$SCRIPT_DIR/stress_cpu_ram.ps1" \
       "$SCRIPT_DIR/stress_gpu.ps1" \
       "$SCRIPT_DIR/stress_disk.ps1" \
       "$SCRIPT_DIR/run_benchmarks.ps1" \
       "curiosity:$REMOTE_DIR/"

# 2. Run master benchmark sequence on curiosity
echo "[2/3] Executing benchmark suite on curiosity..."
ssh curiosity "powershell -ExecutionPolicy Bypass -File '$REMOTE_DIR/run_benchmarks.ps1' -DurationSeconds $DURATION -Timestamp $TIMESTAMP"

# 3. Retrieve results to Mac
echo "[3/3] Downloading telemetry metrics to Mac..."
scp -q "curiosity:$REMOTE_DIR/metrics_windows_${TIMESTAMP}.csv" "$RESULTS_DIR/"

echo ""
echo "=========================================================="
echo " Benchmark Run Completed Successfully!"
echo " Telemetry Metrics: $RESULTS_DIR/metrics_windows_${TIMESTAMP}.csv"
echo "=========================================================="
