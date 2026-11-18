# bbaum-pc-7 windows 2026-10-29 vs bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac


### System

|  | bbaum-pc-7 windows 2026-10-29 | bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac |
|---|---:|---:|
| run | bbaum-pc-7_2026-10-29_152707_windows | bbaum-pc-7_2026-11-18_143844_linux_nixos-curiosity-perf-ac |
| started | 2026-10-29T15:27:07+00:00 | 2026-11-18T14:38:44+00:00 |
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
| cpu.math_mops | MOps/s | 1,919.56 | 1,687.20 | -12.1% worse |
| cpu.math_mops_1core | MOps/s | 148.56 | 136.05 | -8.4% worse |
| cpu.fp64_gemm | GFLOPS | 426.54 | 411.79 | -3.5% worse |
| cpu.mem_copy_bandwidth | GB/s | 150.76 | 156.75 | +4.0% better |
| cpu.mem_copy_bandwidth_1core | GB/s | 45.66 | 48.35 | +5.9% better |
| gpu.mem_copy_bandwidth | GB/s | 251.57 | 253.13 | +0.6% |
| gpu.fp32_fma | TFLOPS | 29.49 | 29.41 | -0.3% |
| gpu.fp16_mma_legacy | TFLOPS | 124.31 | 123.35 | -0.8% |
| tensor.fp16 | TFLOPS | 125.44 | 124.73 | -0.6% |
| tensor.fp16_f16acc | TFLOPS | 125.49 | 124.58 | -0.7% |
| tensor.bf16 | TFLOPS | 125.46 | 124.56 | -0.7% |
| tensor.fp8 | TFLOPS | 247.23 | 248.07 | +0.3% |
| tensor.nvfp4 | TFLOPS | 484.32 | 486.76 | +0.5% |
| tensor.mxfp4 | TFLOPS | 496.07 | 488.33 | -1.6% worse |
| tensor.fp16_sparse | TFLOPS | 245.93 | 243.38 | -1.0% worse |
| tensor.fp8_sparse | TFLOPS | 490.31 | 480.12 | -2.1% worse |
| tensor.nvfp4_sparse | TFLOPS | 973.29 | 944.09 | -3.0% worse |
| cublaslt.fp32 | TFLOPS | 14.63 | 13.33 | -8.9% worse |
| cublaslt.tf32 | TFLOPS | 47.29 | 44.35 | -6.2% worse |
| cublaslt.fp16 | TFLOPS | 85.63 | 76.35 | -10.8% worse |
| cublaslt.bf16 | TFLOPS | 86.34 | 79.00 | -8.5% worse |
| cublaslt.fp8 | TFLOPS | 170.20 | 158.42 | -6.9% worse |
| cublaslt.nvfp4 | TFLOPS | 330.70 | 288.44 | -12.8% worse |
| tensorrt_rtx.fp16 | TFLOPS | 28.34 | 33.70 | +18.9% better |
| tensorrt_rtx.bf16 | TFLOPS | 28.21 | 33.97 | +20.4% better |
| tensorrt_rtx.fp8 | TFLOPS | 63.63 | 77.79 | +22.2% better |
| tensorrt_rtx.nvfp4 | TFLOPS | 25.99 | 32.14 | +23.7% better |
| tensorrt_rtx.fp16_sparse | TFLOPS | 27.97 | 33.00 | +18.0% better |
| tensorrt_rtx.fp8_sparse | TFLOPS | 63.07 | 79.93 | +26.7% better |
| disk.seq_write | MB/s | 2,777.03 | - |  |
| disk.seq_read | MB/s | 4,058.18 | - |  |
| disk.rand4k_write_qd1 | IOPS | 35,947.17 | - |  |
| disk.rand4k_write_qd1_latency | ms | 0.03 | - |  |
| disk.rand4k_read_qd1 | IOPS | 12,029.98 | - |  |
| disk.rand4k_read_qd1_latency | ms | 0.08 | - |  |
| disk.rand4k_read_qd8 | IOPS | 125,899.27 | - |  |
| tensorrt.fp16 | TFLOPS | - | 78.13 |  |
| tensorrt.bf16 | TFLOPS | - | 80.84 |  |
| tensorrt.fp8 | TFLOPS | - | 138.58 |  |
| tensorrt.nvfp4 | TFLOPS | - | 65.83 |  |
| tensorrt.fp16_sparse | TFLOPS | - | 85.66 |  |
| tensorrt.fp8_sparse | TFLOPS | - | 185.02 |  |
| cutlass.nvfp4 | TFLOPS | - | 108.21 |  |
| cutlass.mxfp4 | TFLOPS | - | 105.78 |  |
| cutlass.mxfp8 | TFLOPS | - | 49.07 |  |
| cutlass.fp8_blockwise | TFLOPS | - | 52.06 |  |
| cutlass.fp4_sparse | TFLOPS | - | 93.58 |  |
| cutlass.fp8_sparse | TFLOPS | - | 57.82 |  |

### Telemetry per phase

| phase | measure | bbaum-pc-7 windows 2026-10-29 | bbaum-pc-7 linux 2026-11-18 nixos-curiosity-perf-ac | change |
|---|---:|---:|---:|---:|
| idle | avg_gpu_power_w | 1.5 | 4.1 | +173.5% worse |
| idle | peak_gpu_power_w | 2.9 | 4.7 | +62.9% worse |
| idle | avg_gpu_sm_clock_mhz | 1,536.5 | 2,353.9 | +53.2% better |
| idle | avg_gpu_clock_mhz | 1,536.5 | 2,353.9 | +53.2% better |
| idle | peak_gpu_temp_c | 43.0 | 50.0 | +16.3% worse |
| idle | peak_soc_temp_c | 63.7 | 52.8 | -17.1% better |
| idle | peak_thermal_c | 63.7 | 52.8 | -17.1% better |
| idle | avg_cpu_util_pct | 6.0 | 2.4 | -59.8% worse |
| idle | avg_cpu_freq_mhz | 2,199.0 | 3,406.0 | +54.9% better |
| idle | peak_ram_used_gb | 8.7 | 24.7 | +182.9% worse |
| idle | gpu_energy_wh | 0.0038 | 0.0104 | +173.7% worse |
| cpu | avg_gpu_power_w | 0.7 | 4.7 | +594.0% worse |
| cpu | peak_gpu_power_w | 4.7 | 5.9 | +25.1% worse |
| cpu | avg_gpu_sm_clock_mhz | 1,115.8 | 2,271.4 | +103.6% better |
| cpu | avg_gpu_clock_mhz | 1,115.8 | 2,271.4 | +103.6% better |
| cpu | peak_gpu_temp_c | 58.0 | 67.0 | +15.5% worse |
| cpu | peak_soc_temp_c | 98.4 | 89.3 | -9.2% better |
| cpu | peak_thermal_c | 98.4 | 89.3 | -9.2% better |
| cpu | avg_cpu_util_pct | 78.4 | 81.0 | +3.3% better |
| cpu | avg_cpu_freq_mhz | 3,144.8 | 3,406.0 | +8.3% better |
| cpu | peak_ram_used_gb | 11.8 | 27.6 | +134.0% worse |
| cpu | gpu_energy_wh | 0.0223 | 0.1525 | +583.9% worse |
| gpu | avg_gpu_power_w | 59.8 | 60.7 | +1.6% worse |
| gpu | peak_gpu_power_w | 70.8 | 74.3 | +5.0% worse |
| gpu | avg_gpu_sm_clock_mhz | 2,547.8 | 2,519.3 | -1.1% worse |
| gpu | avg_gpu_clock_mhz | 2,547.8 | 2,519.3 | -1.1% worse |
| gpu | peak_gpu_temp_c | 72.0 | 78.0 | +8.3% worse |
| gpu | peak_soc_temp_c | 83.9 | 85.7 | +2.1% worse |
| gpu | peak_thermal_c | 83.9 | 85.7 | +2.1% worse |
| gpu | avg_cpu_util_pct | 4.0 | 5.6 | +37.6% better |
| gpu | avg_cpu_freq_mhz | 1,660.3 | 3,406.0 | +105.1% better |
| gpu | peak_ram_used_gb | 8.9 | 24.9 | +179.8% worse |
| gpu | gpu_energy_wh | 1.3348 | 1.3747 | +3.0% worse |
| tensor | avg_gpu_power_w | 64.3 | 59.7 | -7.2% better |
| tensor | peak_gpu_power_w | 76.3 | 70.4 | -7.7% better |
| tensor | avg_gpu_sm_clock_mhz | 2,520.3 | 2,489.6 | -1.2% worse |
| tensor | avg_gpu_clock_mhz | 2,520.3 | 2,489.6 | -1.2% worse |
| tensor | peak_gpu_temp_c | 78.0 | 81.0 | +3.8% worse |
| tensor | peak_soc_temp_c | 94.8 | 76.7 | -19.1% better |
| tensor | peak_thermal_c | 94.8 | 76.7 | -19.1% better |
| tensor | avg_cpu_util_pct | 4.5 | 5.6 | +24.7% better |
| tensor | avg_cpu_freq_mhz | 1,477.0 | 3,406.0 | +130.6% better |
| tensor | peak_ram_used_gb | 8.9 | 24.9 | +181.3% worse |
| tensor | gpu_energy_wh | 1.8661 | 1.7485 | -6.3% better |
| cublaslt | avg_gpu_power_w | 61.3 | 51.9 | -15.4% better |
| cublaslt | peak_gpu_power_w | 71.1 | 61.9 | -13.0% better |
| cublaslt | avg_gpu_sm_clock_mhz | 2,005.5 | 1,899.3 | -5.3% worse |
| cublaslt | avg_gpu_clock_mhz | 2,005.5 | 1,899.3 | -5.3% worse |
| cublaslt | peak_gpu_temp_c | 76.0 | 83.0 | +9.2% worse |
| cublaslt | peak_soc_temp_c | 85.8 | 82.7 | -3.6% better |
| cublaslt | peak_thermal_c | 85.8 | 82.7 | -3.6% better |
| cublaslt | avg_cpu_util_pct | 6.0 | 5.6 | -6.0% worse |
| cublaslt | avg_cpu_freq_mhz | 1,660.8 | 3,406.0 | +105.1% better |
| cublaslt | peak_ram_used_gb | 9.6 | 26.1 | +171.4% worse |
| cublaslt | gpu_energy_wh | 2.7357 | 2.5860 | -5.5% better |
| tensorrt_rtx | avg_gpu_power_w | 39.6 | 45.0 | +13.6% worse |
| tensorrt_rtx | peak_gpu_power_w | 61.0 | 51.5 | -15.5% better |
| tensorrt_rtx | avg_gpu_sm_clock_mhz | 2,061.7 | 2,301.8 | +11.6% better |
| tensorrt_rtx | avg_gpu_clock_mhz | 2,061.7 | 2,301.8 | +11.6% better |
| tensorrt_rtx | peak_gpu_temp_c | 74.0 | 81.0 | +9.5% worse |
| tensorrt_rtx | peak_soc_temp_c | 87.5 | 87.3 | -0.2% |
| tensorrt_rtx | peak_thermal_c | 87.5 | 87.3 | -0.2% |
| tensorrt_rtx | avg_cpu_util_pct | 9.7 | 6.1 | -37.0% worse |
| tensorrt_rtx | avg_cpu_freq_mhz | 2,159.3 | 3,406.0 | +57.7% better |
| tensorrt_rtx | peak_ram_used_gb | 9.5 | 25.9 | +173.3% worse |
| tensorrt_rtx | gpu_energy_wh | 2.4131 | 2.4156 | +0.1% |
| whole run | avg_gpu_power_w | 38.6 | 34.9 | -9.8% better |
| whole run | peak_gpu_power_w | 76.3 | 74.3 | -2.7% better |
| whole run | avg_gpu_sm_clock_mhz | 1,874.5 | 2,277.5 | +21.5% better |
| whole run | avg_gpu_clock_mhz | 1,874.5 | 2,277.5 | +21.5% better |
| whole run | peak_gpu_temp_c | 78.0 | 83.0 | +6.4% worse |
| whole run | peak_soc_temp_c | 98.4 | 89.3 | -9.2% better |
| whole run | peak_thermal_c | 98.4 | 89.3 | -9.2% better |
| whole run | avg_cpu_util_pct | 17.4 | 11.3 | -35.3% worse |
| whole run | avg_cpu_freq_mhz | 2,004.2 | 3,406.0 | +69.9% better |
| whole run | peak_ram_used_gb | 11.8 | 29.7 | +152.1% worse |
| whole run | gpu_energy_wh | 8.4697 | 15.5213 | +83.3% worse |
