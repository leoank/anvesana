#!/usr/bin/env bash
#
# Telemetry logger for Linux (aarch64 / NVIDIA RTX Spark)
# Generates identical CSV columns to monitor_system.ps1 for side-by-side comparison.
#

set -euo pipefail

OUTPUT_FILE="${1:-metrics_linux.csv}"
INTERVAL_SEC="${2:-1}"
DURATION_SEC="${3:-0}"

HEADERS="timestamp_iso,elapsed_sec,cpu_util_pct,soc_temp_c,ram_used_gb,ram_total_gb,ram_pct,gpu_util_pct,gpu_mem_used_mb,gpu_mem_total_mb,gpu_temp_c,gpu_power_w,gpu_clock_mhz,npu_temp_c,npu_power_w"
echo "$HEADERS" > "$OUTPUT_FILE"

echo "Telemetry Monitor Started (Linux) -> Output: $OUTPUT_FILE"
echo "Press Ctrl+C to stop logging..."

START_TIME=$(date +%s%N)
SAMPLE_COUNT=0
PEAK_CPU_TEMP=0
PEAK_GPU_TEMP=0
PEAK_GPU_POWER=0
TOTAL_GPU_POWER=0

get_cpu_util() {
    # Read /proc/stat
    read -r cpu user nice system idle iowait irq softirq steal rest < /proc/stat
    local total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    local active=$((total - idle - iowait))
    
    if [ -n "${PREV_TOTAL:-}" ]; then
        local diff_total=$((total - PREV_TOTAL))
        local diff_active=$((active - PREV_ACTIVE))
        if [ "$diff_total" -gt 0 ]; then
            echo $((diff_active * 100 / diff_total))
        else
            echo "0"
        fi
    else
        echo "0"
    fi
    PREV_TOTAL=$total
    PREV_ACTIVE=$active
}

get_soc_temp() {
    # Check thermal zones
    for tz in /sys/class/thermal/thermal_zone*/temp; do
        if [ -f "$tz" ]; then
            local raw
            raw=$(cat "$tz" 2>/dev/null || echo 0)
            if [ "$raw" -gt 1000 ]; then
                awk "BEGIN {printf \"%.1f\", $raw/1000.0}"
                return
            fi
        fi
    done
    echo "0.0"
}

trap_cleanup() {
    echo ""
    echo "================ Telemetry Summary (Linux) ================"
    echo " Total Samples     : $SAMPLE_COUNT"
    echo " CSV Log Saved to  : $OUTPUT_FILE"
    echo "==========================================================="
    exit 0
}
trap trap_cleanup INT TERM

while true; do
    CURRENT_TIME=$(date +%s%N)
    ELAPSED_NS=$((CURRENT_TIME - START_TIME))
    ELAPSED_SEC=$(awk "BEGIN {printf \"%.2f\", $ELAPSED_NS/1000000000.0}")

    if [ "$DURATION_SEC" -gt 0 ] && (( $(echo "$ELAPSED_SEC >= $DURATION_SEC" | bc -l) )); then
        break
    fi

    TIMESTAMP=$(date --iso-8601=seconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")

    # CPU & Temp
    CPU_UTIL=$(get_cpu_util)
    SOC_TEMP=$(get_soc_temp)

    # RAM
    read -r _ MEM_TOTAL _ < <(grep MemTotal /proc/meminfo)
    read -r _ MEM_AVAIL _ < <(grep MemAvailable /proc/meminfo)
    RAM_TOTAL_GB=$(awk "BEGIN {printf \"%.2f\", $MEM_TOTAL/1024.0/1024.0}")
    RAM_USED_KB=$((MEM_TOTAL - MEM_AVAIL))
    RAM_USED_GB=$(awk "BEGIN {printf \"%.2f\", $RAM_USED_KB/1024.0/1024.0}")
    RAM_PCT=$(awk "BEGIN {printf \"%.1f\", ($RAM_USED_KB/$MEM_TOTAL)*100.0}")

    # GPU (Blackwell) via nvidia-smi
    GPU_RAW=$(nvidia-smi -i 0 --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.current.graphics --format=csv,noheader,nounits 2>/dev/null || echo "0, 0, 0, 0, 0, 0")
    IFS=',' read -r GPU_UTIL GPU_MEM_USED GPU_MEM_TOTAL GPU_TEMP GPU_POWER GPU_CLOCK <<< "$GPU_RAW"
    GPU_UTIL=$(echo "$GPU_UTIL" | tr -d ' ')
    GPU_MEM_USED=$(echo "$GPU_MEM_USED" | tr -d ' ')
    GPU_MEM_TOTAL=$(echo "$GPU_MEM_TOTAL" | tr -d ' ')
    GPU_TEMP=$(echo "$GPU_TEMP" | tr -d ' ')
    GPU_POWER=$(echo "$GPU_POWER" | tr -d ' ')
    GPU_CLOCK=$(echo "$GPU_CLOCK" | tr -d ' ')

    # NPU via nvidia-smi -i 1
    NPU_RAW=$(nvidia-smi -i 1 --query-gpu=temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null || echo "0, 0")
    IFS=',' read -r NPU_TEMP NPU_POWER <<< "$NPU_RAW"
    NPU_TEMP=$(echo "$NPU_TEMP" | tr -d ' ')
    NPU_POWER=$(echo "$NPU_POWER" | tr -d ' ')

    echo "$TIMESTAMP,$ELAPSED_SEC,$CPU_UTIL,$SOC_TEMP,$RAM_USED_GB,$RAM_TOTAL_GB,$RAM_PCT,$GPU_UTIL,$GPU_MEM_USED,$GPU_MEM_TOTAL,$GPU_TEMP,$GPU_POWER,$GPU_CLOCK,$NPU_TEMP,$NPU_POWER" >> "$OUTPUT_FILE"
    SAMPLE_COUNT=$((SAMPLE_COUNT + 1))

    printf "\r[%6ss] CPU: %3s%% (%sC) | RAM: %s/%sGB | GPU: %3s%% (%sC, %5sW, %sMHz) | NPU: %sC" \
        "$ELAPSED_SEC" "$CPU_UTIL" "$SOC_TEMP" "$RAM_USED_GB" "$RAM_TOTAL_GB" "$GPU_UTIL" "$GPU_TEMP" "$GPU_POWER" "$GPU_CLOCK" "$NPU_TEMP"

    sleep "$INTERVAL_SEC"
done

trap_cleanup
