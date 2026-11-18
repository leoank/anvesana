# bbaum-pc-7 windows 2026-10-29 vs bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac

- bbaum-pc-7_2026-11-18_131646_linux_nixos-curiosity-perf-ac is partial

### System

|  | bbaum-pc-7 windows 2026-10-29 | bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac |
|---|---:|---:|
| run | bbaum-pc-7_2026-10-29_152707_windows | bbaum-pc-7_2026-11-18_131646_linux_nixos-curiosity-perf-ac |
| started | 2026-10-29T15:27:07+00:00 | 2026-11-18T13:16:46+00:00 |
| hostname | bbaum-pc-7 | curiosity |
| platform | Windows-11-10.0.28000-SP0 | Linux-7.0.14-aarch64-with-glibc2.42 |
| bios | - | Insyde G2621NMS.10B (09/30/2026) |
| nvidia_driver | 621.01 | 615.78.08 |
| power_profile | mode=Best performance, plan=Balanced | governor=performance |
| on_ac_power | True | True |
| ram_gb | 32.75 | 128.9 |
| gpu_mem_total_gb | 103.08 | - |
| gpu_power_limit_w | None | None |
| gpu_max_sm_clock_mhz | 3003 | 3003 |
| python | 3.12.16 | 3.12.15 |
| gpu | NVIDIA RTX Spark N1X (6144-core Blackwell RTX GPU) | NVIDIA RTX Spark N1X (6144-core Blackwell RTX GPU) |

### Benchmarks

| metric | unit | bbaum-pc-7 windows 2026-10-29 | bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac | change |
|---|---:|---:|---:|---:|
| cpu.math_mops | MOps/s | 1,919.56 | 1,694.86 | -11.7% worse |
| cpu.math_mops_1core | MOps/s | 148.56 | 131.65 | -11.4% worse |
| cpu.fp64_gemm | GFLOPS | 426.54 | 389.29 | -8.7% worse |
| cpu.mem_copy_bandwidth | GB/s | 150.76 | 155.74 | +3.3% better |
| cpu.mem_copy_bandwidth_1core | GB/s | 45.66 | 47.66 | +4.4% better |
| gpu.mem_copy_bandwidth | GB/s | 251.57 | 244.39 | -2.9% worse |
| gpu.fp32_fma | TFLOPS | 29.49 | 29.39 | -0.3% |
| gpu.fp16_mma_legacy | TFLOPS | 124.31 | 123.18 | -0.9% |
| tensor.fp16 | TFLOPS | 125.44 | 124.86 | -0.5% |
| tensor.fp16_f16acc | TFLOPS | 125.49 | 124.58 | -0.7% |
| tensor.bf16 | TFLOPS | 125.46 | 124.57 | -0.7% |
| tensor.fp8 | TFLOPS | 247.23 | 248.02 | +0.3% |
| tensor.nvfp4 | TFLOPS | 484.32 | 486.46 | +0.4% |
| tensor.mxfp4 | TFLOPS | 496.07 | 488.30 | -1.6% worse |
| tensor.fp16_sparse | TFLOPS | 245.93 | 244.27 | -0.7% |
| tensor.fp8_sparse | TFLOPS | 490.31 | 480.74 | -2.0% worse |
| tensor.nvfp4_sparse | TFLOPS | 973.29 | 946.83 | -2.7% worse |
| cublaslt.fp32 | TFLOPS | 14.63 | 13.27 | -9.3% worse |
| cublaslt.tf32 | TFLOPS | 47.29 | 44.06 | -6.8% worse |
| cublaslt.fp16 | TFLOPS | 85.63 | 76.52 | -10.6% worse |
| cublaslt.bf16 | TFLOPS | 86.34 | 76.56 | -11.3% worse |
| cublaslt.fp8 | TFLOPS | 170.20 | 157.33 | -7.6% worse |
| cublaslt.nvfp4 | TFLOPS | 330.70 | 286.80 | -13.3% worse |
| tensorrt_rtx.fp16 | TFLOPS | 28.34 | 32.24 | +13.8% better |
| tensorrt_rtx.bf16 | TFLOPS | 28.21 | 33.28 | +18.0% better |
| tensorrt_rtx.fp8 | TFLOPS | 63.63 | 74.40 | +16.9% better |
| tensorrt_rtx.nvfp4 | TFLOPS | 25.99 | 32.37 | +24.5% better |
| tensorrt_rtx.fp16_sparse | TFLOPS | 27.97 | 32.40 | +15.8% better |
| tensorrt_rtx.fp8_sparse | TFLOPS | 63.07 | 80.23 | +27.2% better |
| disk.seq_write | MB/s | 2,777.03 | - |  |
| disk.seq_read | MB/s | 4,058.18 | - |  |
| disk.rand4k_write_qd1 | IOPS | 35,947.17 | - |  |
| disk.rand4k_write_qd1_latency | ms | 0.03 | - |  |
| disk.rand4k_read_qd1 | IOPS | 12,029.98 | - |  |
| disk.rand4k_read_qd1_latency | ms | 0.08 | - |  |
| disk.rand4k_read_qd8 | IOPS | 125,899.27 | - |  |

### Telemetry per phase

| phase | measure | bbaum-pc-7 windows 2026-10-29 | bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac | change |
|---|---:|---:|---:|---:|
| idle | avg_gpu_power_w | 1.5 | 3.6 | +138.4% worse |
| idle | peak_gpu_power_w | 2.9 | 4.2 | +48.3% worse |
| idle | avg_gpu_sm_clock_mhz | 1,536.5 | 2,355.9 | +53.3% better |
| idle | avg_gpu_clock_mhz | 1,536.5 | 2,355.9 | +53.3% better |
| idle | peak_gpu_temp_c | 43.0 | 43.0 | +0.0% |
| idle | peak_soc_temp_c | 63.7 | 44.2 | -30.6% better |
| idle | peak_thermal_c | 63.7 | 44.2 | -30.6% better |
| idle | avg_cpu_util_pct | 6.0 | 1.6 | -73.1% worse |
| idle | avg_cpu_freq_mhz | 2,199.0 | 3,406.0 | +54.9% better |
| idle | peak_ram_used_gb | 8.7 | 18.4 | +110.9% worse |
| idle | gpu_energy_wh | 0.0038 | 0.0090 | +136.8% worse |
| cpu | avg_gpu_power_w | 0.7 | 4.9 | +634.3% worse |
| cpu | peak_gpu_power_w | 4.7 | 6.5 | +36.9% worse |
| cpu | avg_gpu_sm_clock_mhz | 1,115.8 | 2,250.3 | +101.7% better |
| cpu | avg_gpu_clock_mhz | 1,115.8 | 2,250.3 | +101.7% better |
| cpu | peak_gpu_temp_c | 58.0 | 67.0 | +15.5% worse |
| cpu | peak_soc_temp_c | 98.4 | 88.1 | -10.5% better |
| cpu | peak_thermal_c | 98.4 | 88.1 | -10.5% better |
| cpu | avg_cpu_util_pct | 78.4 | 81.9 | +4.5% better |
| cpu | avg_cpu_freq_mhz | 3,144.8 | 3,406.0 | +8.3% better |
| cpu | peak_ram_used_gb | 11.8 | 21.2 | +80.0% worse |
| cpu | gpu_energy_wh | 0.0223 | 0.1616 | +624.7% worse |
| gpu | avg_gpu_power_w | 59.8 | 60.9 | +1.8% worse |
| gpu | peak_gpu_power_w | 70.8 | 73.8 | +4.3% worse |
| gpu | avg_gpu_sm_clock_mhz | 2,547.8 | 2,521.5 | -1.0% worse |
| gpu | avg_gpu_clock_mhz | 2,547.8 | 2,521.5 | -1.0% worse |
| gpu | peak_gpu_temp_c | 72.0 | 78.0 | +8.3% worse |
| gpu | peak_soc_temp_c | 83.9 | 73.7 | -12.2% better |
| gpu | peak_thermal_c | 83.9 | 73.7 | -12.2% better |
| gpu | avg_cpu_util_pct | 4.0 | 5.6 | +39.6% better |
| gpu | avg_cpu_freq_mhz | 1,660.3 | 3,406.0 | +105.1% better |
| gpu | peak_ram_used_gb | 8.9 | 18.5 | +108.1% worse |
| gpu | gpu_energy_wh | 1.3348 | 1.3778 | +3.2% worse |
| tensor | avg_gpu_power_w | 64.3 | 59.8 | -7.1% better |
| tensor | peak_gpu_power_w | 76.3 | 70.1 | -8.2% better |
| tensor | avg_gpu_sm_clock_mhz | 2,520.3 | 2,491.7 | -1.1% worse |
| tensor | avg_gpu_clock_mhz | 2,520.3 | 2,491.7 | -1.1% worse |
| tensor | peak_gpu_temp_c | 78.0 | 81.0 | +3.8% worse |
| tensor | peak_soc_temp_c | 94.8 | 76.0 | -19.8% better |
| tensor | peak_thermal_c | 94.8 | 76.0 | -19.8% better |
| tensor | avg_cpu_util_pct | 4.5 | 5.6 | +24.9% better |
| tensor | avg_cpu_freq_mhz | 1,477.0 | 3,406.0 | +130.6% better |
| tensor | peak_ram_used_gb | 8.9 | 18.5 | +109.3% worse |
| tensor | gpu_energy_wh | 1.8661 | 1.7506 | -6.2% better |
| cublaslt | avg_gpu_power_w | 61.3 | 51.5 | -16.0% better |
| cublaslt | peak_gpu_power_w | 71.1 | 61.4 | -13.7% better |
| cublaslt | avg_gpu_sm_clock_mhz | 2,005.5 | 1,907.2 | -4.9% worse |
| cublaslt | avg_gpu_clock_mhz | 2,005.5 | 1,907.2 | -4.9% worse |
| cublaslt | peak_gpu_temp_c | 76.0 | 83.0 | +9.2% worse |
| cublaslt | peak_soc_temp_c | 85.8 | 88.7 | +3.4% worse |
| cublaslt | peak_thermal_c | 85.8 | 88.7 | +3.4% worse |
| cublaslt | avg_cpu_util_pct | 6.0 | 5.6 | -5.8% worse |
| cublaslt | avg_cpu_freq_mhz | 1,660.8 | 3,406.0 | +105.1% better |
| cublaslt | peak_ram_used_gb | 9.6 | 19.9 | +106.9% worse |
| cublaslt | gpu_energy_wh | 2.7357 | 2.5823 | -5.6% better |
| tensorrt_rtx | avg_gpu_power_w | 39.6 | 42.9 | +8.4% worse |
| tensorrt_rtx | peak_gpu_power_w | 61.0 | 50.1 | -17.9% better |
| tensorrt_rtx | avg_gpu_sm_clock_mhz | 2,061.7 | 2,285.3 | +10.8% better |
| tensorrt_rtx | avg_gpu_clock_mhz | 2,061.7 | 2,285.3 | +10.8% better |
| tensorrt_rtx | peak_gpu_temp_c | 74.0 | 80.0 | +8.1% worse |
| tensorrt_rtx | peak_soc_temp_c | 87.5 | 88.7 | +1.4% worse |
| tensorrt_rtx | peak_thermal_c | 87.5 | 88.7 | +1.4% worse |
| tensorrt_rtx | avg_cpu_util_pct | 9.7 | 8.0 | -18.0% worse |
| tensorrt_rtx | avg_cpu_freq_mhz | 2,159.3 | 3,406.0 | +57.7% better |
| tensorrt_rtx | peak_ram_used_gb | 9.5 | 19.8 | +108.6% worse |
| tensorrt_rtx | gpu_energy_wh | 2.4131 | 2.3542 | -2.4% better |
| whole run | avg_gpu_power_w | 38.6 | 37.9 | -1.9% better |
| whole run | peak_gpu_power_w | 76.3 | 73.8 | -3.3% better |
| whole run | avg_gpu_sm_clock_mhz | 1,874.5 | 2,263.0 | +20.7% better |
| whole run | avg_gpu_clock_mhz | 1,874.5 | 2,263.0 | +20.7% better |
| whole run | peak_gpu_temp_c | 78.0 | 83.0 | +6.4% worse |
| whole run | peak_soc_temp_c | 98.4 | 88.7 | -9.9% better |
| whole run | peak_thermal_c | 98.4 | 88.7 | -9.9% better |
| whole run | avg_cpu_util_pct | 17.4 | 16.2 | -7.4% worse |
| whole run | avg_cpu_freq_mhz | 2,004.2 | 3,406.0 | +69.9% better |
| whole run | peak_ram_used_gb | 11.8 | 22.5 | +91.1% worse |
| whole run | gpu_energy_wh | 8.4697 | 8.9048 | +5.1% worse |
