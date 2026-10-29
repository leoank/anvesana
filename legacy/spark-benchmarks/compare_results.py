#!/usr/bin/env python3
"""
Compare Windows vs Linux telemetry metrics for NVIDIA RTX Spark.
Usage:
    python3 compare_results.py results/metrics_windows_*.csv results/metrics_linux_*.csv
"""

import sys
import csv
import os

def load_metrics(filepath):
    data = {
        "elapsed": [],
        "cpu_util": [],
        "soc_temp": [],
        "ram_used": [],
        "gpu_util": [],
        "gpu_temp": [],
        "gpu_power": [],
        "gpu_clock": [],
    }
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                data["elapsed"].append(float(row.get("elapsed_sec", 0)))
                data["cpu_util"].append(float(row.get("cpu_util_pct", 0)))
                data["soc_temp"].append(float(row.get("soc_temp_c", 0)))
                data["ram_used"].append(float(row.get("ram_used_gb", 0)))
                data["gpu_util"].append(float(row.get("gpu_util_pct", 0)))
                data["gpu_temp"].append(float(row.get("gpu_temp_c", 0)))
                data["gpu_power"].append(float(row.get("gpu_power_w", 0)))
                data["gpu_clock"].append(float(row.get("gpu_clock_mhz", 0)))
            except (ValueError, TypeError):
                continue
    return data

def calc_stats(arr):
    if not arr:
        return 0.0, 0.0, 0.0
    valid = [x for x in arr if x > 0]
    baseline = valid[0] if valid else arr[0]
    mean_val = sum(arr) / len(arr)
    max_val = max(arr)
    return baseline, mean_val, max_val

def calc_energy_wh(powers_w, elapsed_s):
    # Numerical integration (trapezoidal rule or sum of power * dt)
    if len(powers_w) < 2 or len(elapsed_s) < 2:
        return 0.0
    total_joules = 0.0
    for i in range(1, len(powers_w)):
        dt = elapsed_s[i] - elapsed_s[i-1]
        p_avg = (powers_w[i] + powers_w[i-1]) / 2.0
        total_joules += p_avg * dt
    return total_joules / 3600.0  # Convert Joules to Watt-hours

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 compare_results.py <windows_metrics.csv> <linux_metrics.csv>")
        sys.exit(1)

    win_file = sys.argv[1]
    lin_file = sys.argv[2]

    win = load_metrics(win_file)
    lin = load_metrics(lin_file)

    win_dur = max(win["elapsed"]) if win["elapsed"] else 0
    lin_dur = max(lin["elapsed"]) if lin["elapsed"] else 0

    print("==========================================================================")
    print("      NVIDIA RTX Spark Benchmark Comparison: Windows vs Linux             ")
    print(f" Windows Log: {os.path.basename(win_file)} ({len(win['elapsed'])} samples, {win_dur:.1f}s)")
    print(f" Linux Log  : {os.path.basename(lin_file)} ({len(lin['elapsed'])} samples, {lin_dur:.1f}s)")
    print("==========================================================================")
    print(f"{'Metric':<32} | {'Windows (ARM64)':<18} | {'Linux (aarch64)':<18}")
    print("-" * 74)

    metrics_def = [
        ("Peak SoC / CPU Temp (C)", lambda d: f"{max(d['soc_temp']):.1f} C" if d['soc_temp'] else "N/A"),
        ("Avg CPU Utilization (%)", lambda d: f"{sum(d['cpu_util'])/len(d['cpu_util']):.1f}%" if d['cpu_util'] else "N/A"),
        ("Peak CPU Utilization (%)", lambda d: f"{max(d['cpu_util']):.1f}%" if d['cpu_util'] else "N/A"),
        ("Baseline GPU Temp (C)", lambda d: f"{d['gpu_temp'][0]:.1f} C" if d['gpu_temp'] else "N/A"),
        ("Peak GPU Temp (C)", lambda d: f"{max(d['gpu_temp']):.1f} C" if d['gpu_temp'] else "N/A"),
        ("Avg GPU Power (Watts)", lambda d: f"{sum(d['gpu_power'])/len(d['gpu_power']):.2f} W" if d['gpu_power'] else "N/A"),
        ("Peak GPU Power (Watts)", lambda d: f"{max(d['gpu_power']):.2f} W" if d['gpu_power'] else "N/A"),
        ("Total GPU Energy (Watt-hours)", lambda d: f"{calc_energy_wh(d['gpu_power'], d['elapsed']):.4f} Wh"),
        ("Max GPU Core Clock (MHz)", lambda d: f"{max(d['gpu_clock']):.0f} MHz" if d['gpu_clock'] else "N/A"),
        ("Peak RAM Used (GB)", lambda d: f"{max(d['ram_used']):.2f} GB" if d['ram_used'] else "N/A"),
    ]

    for label, fn in metrics_def:
        w_val = fn(win)
        l_val = fn(lin)
        print(f"{label:<32} | {w_val:<18} | {l_val:<18}")

    print("==========================================================================")

if __name__ == "__main__":
    main()
