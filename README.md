# anvesana: node health tracking

Run the same GPU / CPU / memory / disk benchmark suite on every machine on a schedule (monthly),
keep every run, and flag nodes that are getting slower, hotter or broken.

```
machines/<id>.toml        what each machine runs, its advertised specs, its health tolerances
baselines/<id>/<os>.json  the reviewed reference run per machine and OS (committed)
$ANVESANA_RESULTS_DIR/       every run: run.json + telemetry.csv + run.log (outside the repo)
```

## Setup

Each node installs only what its own profile needs. [uv](https://docs.astral.sh/uv/) manages Python
and the packages, all from one shared `uv.lock`, so a library has the same version on every node.

```bash
uv sync --inexact                 # core only: numpy, psutil (CPU, memory, disk, run records, health)
uv run anvesana setup             # + exactly the extras this host's profile needs, then `check`
export ANVESANA_RESULTS_DIR=/shared/anvesana-results     # Windows: setx ANVESANA_RESULTS_DIR \\server\anvesana-results
```

| Extra | Contents | Needed by |
|---|---|---|
| (core) | numpy, psutil | `cpu`, `disk`, telemetry, all commands |
| `nvidia` | cuda-python, NVRTC, CUDA runtime, cuBLAS, NVML (pip wheels; no CUDA toolkit) | `gpu`, `tensor`, `cublaslt`, GPU telemetry |
| `tensorrt` | `nvidia` + TensorRT for RTX, full TensorRT (Linux) | `tensorrt` |
| `cutlass` | `nvidia` + CUTLASS, nvcc, CMake, Ninja | `cutlass` |

`anvesana setup` works out the extras from the benchmarks the profile runs on this OS, plus any listed
under `[install] extras`. It runs `uv sync --locked` with exactly those, removing extras the node no
longer needs. Things uv can't install are only checked: GPU drivers, compilers, and in the future
InfiniBand `perftest` or FPGA runtimes. Each benchmark declares those as `tools` / `hardware` in
`framework/registry.py`, and `anvesana check` reports what's missing:

```
$ anvesana check
benchmark  module   status   detail
cpu        cpu      OK
gpu        gpu      MISSING  missing Python packages (cuda); run `anvesana setup` (extras: nvidia)
```

A suite run applies the same check up front. A benchmark that can't run is recorded as
`unavailable`, with the reason, and fails the health check.

The lock covers win_arm64, linux_aarch64 and linux_x86_64 (`required-environments` in
`pyproject.toml`). Add a platform there before adding a node of a new kind. If two extras ever need
incompatible versions (say CUDA 12 for older GPUs vs CUDA 13), declare them in uv's `conflicts`
setting.

The CUTLASS benchmark runs on Linux only and needs the system `g++`. Its first run builds NVIDIA's
`cutlass_profiler` once and caches it in `~/.cache/anvesana/cutlass`. On Windows, CUTLASS's
SM90+ kernels can't be compiled: nvcc only accepts MSVC there, and MSVC rejects their 128-byte-aligned
kernel parameters (error C2719).

## Adding a machine

```bash
uv sync --inexact
uv run bench machines init dgx-01      # writes machines/dgx-01.toml with this host's name
# edit: benchmark list/args, [install] extras, [expected] vendor peaks, [health] tolerances
uv run bench setup                     # install what it needs, then check readiness
uv run bench run                       # first run
uv run bench baseline promote dgx-01@latest   # once a run looks right; commit the baseline
```

## Monthly workflow

```bash
uv run bench run --health        # run this host's profile, store it, check it; exit 1 on regression
uv run bench fleet               # every machine's latest health; flags nodes with no run in 35 days
uv run bench show                # newest run in full: metrics with % of spec, W, TFLOPS/W, clocks; settings; telemetry
uv run bench show dgx-01@baseline --metrics "tensor.*" --no-environment
uv run bench history             # trends across the last 6 runs
uv run bench health dgx-01@latest --against median   # vs the median of the last 3 runs instead of the baseline
uv run bench compare dgx-01@baseline dgx-01@latest --markdown report.md
uv run bench runs                # everything in the store
```

`scripts/scheduled-run.ps1` and `scripts/scheduled-run.sh` wrap setup, run and health for Task
Scheduler, cron or systemd, so a profile change reaches the node's dependencies on its next run. Their headers show how to register them for the first Sunday of each month.

Run references accept a path, a run id, `<machine>` / `<machine>@latest`, `<machine>@-1` (the run before
the newest), `<machine>@2026-10-29`, or `<machine>@baseline[:<os>]`.

## The run record (`run.json`)

One JSON document per run (schema version 1, details in `src/anvesana/framework/records.py`):

| Field | Contents |
|---|---|
| `run_id`, `started_at`, `finished_at`, `status` | `<machine>_<date>_<os>[_tag]`, ISO 8601 with timezone, complete / partial / aborted |
| `machine` | profile id, description, hostname, profile file |
| `settings` | duration, cooldown, tag, `--only/--skip`, every benchmark with its args, **methodology `version`** and outcome, framework version, git commit, command line |
| `environment` | OS, kernel, NVIDIA driver, CUDA/library versions, GPU, CPU, RAM, **power plan / governor**, **AC power**, GPU power limit |
| `preflight` | conditions that make the run less representative (on battery, busy system) |
| `phases`, `phase_telemetry` | per-benchmark timing, and avg/peak GPU power, SM clock, GPU/SoC temperature, CPU clock, energy |
| `metrics` | `<benchmark>.<measure>` → value, unit, higher_is_better |

Each benchmark module has a `VERSION`. Bump it when a change makes new numbers incomparable with
old ones; `health`, `history` and `compare` then refuse to compare across the change, so re-baseline.

## Health check

`bench health` compares a run with the machine's baseline. Without a baseline, it uses the median of
the last 3 runs on the same OS. Each headline metric gets a status:

- **FAIL**: worse than the tolerance (`[health]` in the profile; per-metric globs, longest match wins)
- **WARN**: worse than half the tolerance
- **MISSING**: a benchmark that used to produce a metric no longer does
- **SKIP**: the methodology version changed

It also flags a GPU or SoC running 8 °C (WARN) or 15 °C (FAIL) hotter, or clocking lower, under the
same load, which catches cooling problems before they turn into throughput losses. Exit code 1 on
FAIL or MISSING.

## Benchmarks

| Benchmark | Measures | Notes |
|---|---|---|
| `cpu` | FP64 math (all cores / 1 core), FP64 DGEMM, memory copy bandwidth | numpy, one process per core |
| `gpu` | device memory copy bandwidth, FP32 FMA, FP16 `mma.sync` | PTX through the CUDA driver API |
| `tensor` | peak tensor-core TFLOPS: FP16/BF16/FP8/NVFP4/MXFP4, dense and 2:4 sparse | NVRTC-compiled `mma.sync` microbenchmark; unsupported precisions are skipped on older GPUs |
| `cublaslt` | GEMM TFLOPS FP32/TF32/FP16/BF16/FP8/NVFP4, autotuned, random data | what frameworks actually get |
| `tensorrt` | linear-layer engines FP16/BF16/FP8/NVFP4, dense and 2:4 sparse | `backend = "rtx"` (TensorRT for RTX) or `"trt"` (full TensorRT) |
| `cutlass` | best `cutlass_profiler` kernel per family: NVFP4, MXFP4, MXFP8, FP8 blockwise, sparse FP4/FP8 | Linux only; builds CUTLASS 4.2 once for the local arch; families are SM120-specific (add patterns for other GPUs) |
| `disk` | sequential R/W, random 4K QD1 R/W + latency, random 4K QD8 | page cache bypassed (`O_DIRECT` / `FILE_FLAG_NO_BUFFERING`) |

Every GPU benchmark also records average power, SM clock and TFLOPS/W while it runs. Each benchmark
runs in its own process, with a cooldown between benchmarks.

To add a benchmark, write `src/anvesana/suite/<name>.py` with `NAME`, `VERSION`, `DESCRIPTION`,
`add_arguments(parser)` and `run(args) -> list[Metric]`. Then add a `Requirement` to `SUITE` in
`framework/registry.py`, with its extras, required system tools, supported OSes and hardware probe.
If it needs new Python packages, add an extra in `pyproject.toml` and run `uv lock`. Finally, list it
in the relevant machine profiles. For example, an InfiniBand benchmark would be
`Requirement("ib_perf", tools=("ib_write_bw", "ib_read_lat"), os=("linux",), hardware="infiniband")`,
with an `infiniband` probe added to `HARDWARE_PROBES`.

Run any single benchmark directly: `uv run bench tensor --duration 10 --precisions fp16,nvfp4`.

## Hardware inventory and Linux bring-up

Benchmarks say how fast a node is; `bench inventory` records what it is made of and which driver
runs each part. On a new SoC that is moving from Windows to Linux, the Windows inventory is the
bring-up reference, and comparing it with a Linux inventory gives the list of gaps to close.

```bash
uv run bench inventory collect                 # this host -> $ANVESANA_RESULTS_DIR/<machine>/inventory/<snapshot>/
uv run bench inventory show --grep NVDA --resources    # SoC blocks: driver, version, ACPI path, MMIO, IRQ
uv run bench inventory show --packages         # driver packages and the firmware files they install
uv run bench inventory show --hid              # every HID report field: touch, pen, touchpad, keyboard, RGB
uv run bench inventory collect --copy-firmware # also keep the firmware blobs (deduplicated per machine)
uv run bench inventory compare bbaum-pc-7@windows bbaum-pc-7@linux --markdown gap.md
uv run bench inventory compare bbaum-pc-7@-1 bbaum-pc-7@latest       # driver / firmware drift on one OS
```

A snapshot contains `inventory.json` (schema in `src/anvesana/inventory/snapshot.py`) and the raw
firmware the OS was handed:

| Collected | Windows (no admin needed) | Linux (run as root for everything) |
|---|---|---|
| devices | present PnP devices: hardware/compatible IDs, ACPI path, parent, function + filter drivers, INF, version, problem code, MMIO/IRQ | ACPI devices (`_STA`, driver bound to the physical node), PCI, USB, platform devices without ACPI |
| drivers | every kernel driver service and its binary's version | loaded modules |
| driver packages | third-party driver-store folders: INF copied, every file hashed; `--copy-firmware` copies firmware blobs to `<machine>/inventory/firmware/` once per content | – |
| HID | every top-level collection with its per-report fields (from `hid.dll` caps; sensor-stack collections are not readable) | raw `report_descriptor` per device (`hid/*.bin`) and the same parsed collections |
| ACPI-WMI | `_WDG` blocks parsed from the tables: the GUIDs Linux's WMI bus binds drivers to | same, plus each WMI device's bound driver |
| ESRT | capsule-updatable firmware (GUID, type, version) | `/sys/firmware/efi/esrt` (what fwupd uses) |
| kernel | – | release, cmdline, `devices_deferred`, missing firmware, probe and ACPI errors, `kernel.log` |
| ACPI | `acpi/*.dat`: every table except MSDM (license key), all SSDTs | `acpi/*.dat` from `/sys/firmware/acpi/tables` |
| SMBIOS | `smbios.bin` (`dmidecode --from-dump`) and a summary without serials | same, or `/sys/class/dmi/id` without root |
| CPU | per-core MIDR / ID_AA64* registers, core types and clusters | per-core MIDR, cluster, cpufreq range and driver, idle states, Features |

`compare` joins devices on their ACPI namespace path (`\_SB.I2C0`), then on a cross-OS id
(`acpi:NVDA0200`, `pci:10de:2e03`, `usb:27c6:6090`). Each device gets a verdict:

- **GAP**: Windows drives it; Linux enumerates it but binds no driver, or the probe is deferred (the reason is shown)
- **MISSING**: Windows drives it; Linux doesn't enumerate it at all. Often a missing bus driver: everything behind an unsupported I2C/SPI/SoundWire controller shows up here.
- **PROBLEM / NEW / EXTRA / OK**: a problem on the second snapshot / driven only there / present only there / both fine

It also checks that both OSes were handed byte-identical ACPI tables and the same BIOS. If they
weren't, Linux booted with a different firmware configuration or an override. The exit code is 1
while any GAP, MISSING or PROBLEM remains, so a scheduled Linux run can track bring-up progress.
`scripts/scheduled-run.*` collect an inventory before every benchmark run.

Bring-up loop for a new SoC:

1. On Windows: `bench inventory collect`. Review `show --grep <vendor ACPI prefix> --resources`
   (here `NVDA`) and `show --packages`. These give the block list, its MMIO/IRQ map, and the firmware
   blobs Linux will need in `/lib/firmware`.
2. Disassemble the tables: `iasl -e acpi/ssdt*.dat -d acpi/dsdt.dat`. The `_HID`/`_CID`, `_CRS` and
   `_DSD` of each block are what a Linux driver's ACPI match table and probe read.
3. Boot Linux on the same BIOS, run `sudo bench inventory collect`, then `compare <machine>@windows
   <machine>@linux`. Work through the list top-down: controllers (I2C, SPI, GPIO, SoundWire, xHCI)
   before the devices behind them.
4. Re-collect after each kernel or firmware change; `compare <machine>@-1 <machine>@latest` on Linux
   shows what changed.

## Platform notes (NVIDIA RTX Spark N1X, Windows on ARM)

- First inventory (BIOS Insyde G2621NMS.10B): 10× Cortex-X925 (MIDR `0x410fd851`, cpus 5-9,15-19) and
  10× Cortex-A725 (`0x410fd871`, cpus 0-4,10-14). There are 32 NVIDIA ACPI devices (`NVDA*`) of 19 types: 7 I2C,
  3 SPI, GPIO, HD Audio, 6 xHCI (Microsoft's inbox `USBXHCI` plus an NVIDIA lower filter, `nvxhcifilter`, which
  points to controller quirks), 2 USB4 routers, SoundWire, three HiFi DSPs (`nvadsp`, loading
  signed `hifi*_cose_sign_image.bin` firmware), NPU (`\_SB.DLA0`, driven by the GPU driver), SCP,
  platform extension (PEP), root-of-trust mailbox, and Pluton. The IORT comes from MediaTek (`MEDTEK MTKSGI`).
- Vendor controls (MSI Center S, inventory of 2026-10-30, EC firmware 2621EMS1.109):
  - **Power / fan:** the `MSI_ACPI` WMI class. Its methods `Get/Set_EC`, `_Fan`, `_Thermal`, `_Power`,
    `_Device`, `_AP` and others are the ACPI-WMI method block `ABBC0F6E-8EA1-11D1-00A0-C90629100000`
    (object `AM`). Events arrive on `5B3CC38A-…` (notify 0xC0). MSI Center keeps the "Shift mode"
    in an EC register and also drives Windows power-mode overlays and NVIDIA PCF power tables
    (`NVDA0820`). Querying the class needs admin.
  - **Keyboard RGB** ("4 Zone"): the internal USB HID `1462:1609` "MysticLight MS-1609". It has
    vendor page 0xFF and 64-byte reports, and is written with HID feature/output reports. The
    I2C keyboard (`0db0:1606`, `\_SB.I2C2.TPD0`) carries no lighting controls.
  - **Touchpad:** Synaptics `06cb:d022` on `\_SB.I2C3.TPD3`, a standard Precision Touchpad plus a
    vendor collection with reports 9–12. That matches RMI-over-HID, and the Synaptics install sets
    `SynRMIHID=1`. Haptic intensity and edge-slide volume/brightness gestures are set by
    Synaptics' `SynTPEnh` over that vendor channel; there is no standard HID haptics collection.
  - **Touch screen + pen:** ELAN `04f3:4516` on `\_SB.I2C1.TPL1`. The pen collection reports pressure
    (16-bit), X/Y tilt, azimuth, eraser, two barrel buttons, battery strength and a transducer
    serial. MSI Pen reads the battery from an ELAN vendor collection and also handles the pen
    garage and a Bluetooth shortcut button.

- Full TensorRT's win_arm64 wheel lacks its Myelin resource DLLs, so it cannot build engines on
  Windows. Profiles list it with `os = ["linux"]`. TensorRT for RTX works on both OSes but picks slow
  kernels in 1.7 (FP16 ≈ 28 TFLOPS).
- The N1X GPU is power-capped at about 47 W. Instruction-level kernels hold ~2.4 GHz; real GEMMs drop
  to ~1.3–1.5 GHz. Power and clock are therefore recorded alongside throughput.
- The "1 PFLOP" spec is NVFP4 with 2:4 sparsity. `tensor.nvfp4_sparse` reaches 91–97% of it.
- Old PowerShell/bash scripts and their CSVs are in `legacy/`; `bench compare` still reads those CSVs.
