# Replicating "RTX Spark runs at a third of its speed on Linux"

Claims from [MindStudio's post](https://www.mindstudio.ai/blog/linux-nvidia-rtx-spark-laptop)
(discussed on [Hacker News](https://news.ycombinator.com/item?id=50362905)), tested on the
same laptop model: bbaum-pc-7, MSI Prestige N16 Flip AI+ (MS-2621), 128 GB. The post gives no
versions, commands or quantisation, so everything below is pinned here instead.

| # | Claim | Their numbers | Tested by |
|---|---|---|---|
| C1 | Native Linux inference is ~20–35 % of Windows | GPT-OSS-120B 65.4 tok/s Windows, 13.9 Linux | [[EXP-20261104-ssfqvw]] vs [[EXP-20261104-ssfv1c]] |
| C2 | On Linux the GPU locks low on AC only | ~780 MHz on AC, ~1.8 GHz on battery; Windows ~2.2 GHz | [[EXP-20261104-ssfv1c]] |
| C3 | Not thermal | 40–47 °C during the slow runs | [[EXP-20261104-ssfqvw]], [[EXP-20261104-ssfv1c]] (`gpu_temp_c`, throttle bits) |
| C4 | Disabling NVPCF on Windows reproduces it | ~83 → ~31 tok/s, 2 GHz → 786 MHz | [[EXP-20261104-ssfqvw]] |
| C5 | WSL matches Windows | 65.1 tok/s; vLLM, 8 clients: 127 WSL vs 39.5 native | [[EXP-20261104-ssfs86]] |
| C6 | The firmware GPU reservation starves Linux | Linux saw 28 GB until it was lowered to 4 GB in Windows | [[EXP-20261104-ssfv1c]] |
| C7 | NVPCF's power table is encrypted; only Windows can use it | none given | [[EXP-20261104-ssfn9a]], [[EXP-20261104-ssfy1p]] |

The experiments are on the project page ([[PRJ-0001]]). What already exists on Windows: the GPU
sees 110.5 GiB through CUDA with the default 96 GB reservation; `ACPI\NVDA0820\NPCF` runs
`nvpcf` 32.0.16.1679 (driver 621.01).

## What is measured, and how

- **Engine.** llama.cpp `b12119` (commit `6f1e654`), the official CUDA 13.4 ARM64 builds: the
  Windows one on Windows, the Ubuntu one in WSL *and* on NixOS (through nix-ld), so WSL and
  native Linux run identical binaries. `bench llm` runs `llama-bench` with flash attention, all
  layers on the GPU, mmap off, 5 repetitions, prefill (pp512) and decode (tg128) separately.
- **Models.** `ggml-org/gpt-oss-20b-GGUF` and `ggml-org/gpt-oss-120b-GGUF` (MXFP4), pinned by
  revision and sha256 in `src/anvesana/suite/llm.py`. 20B for the condition sweeps, 120B for
  the article's headline number. vLLM (C5) uses `openai/gpt-oss-20b` @ `6cee5e8`.
- **Telemetry.** The run's `telemetry.csv` samples SM clock, power, GPU temperature, NVML
  clock-event (throttle) bits and, new, `on_ac` per row; each `llm.*` metric carries the
  average power, SM clock and the OR of the throttle bits measured during it.
- **Conditions.** `scripts/llm-conditions.py --label <setup> --conditions ac,dc` asks for the
  charger to be plugged in or pulled, waits until the battery says so, settles 60 s, then runs
  `bench run --only llm --tag <setup>-<ac|dc>`. It refuses a battery run below 50 %.

Run tags: `win-npcf-on`, `win-npcf-off`, `wsl`, `nixos-default`, `nixos-osi`, `nixos-sspm`, each
`-ac` / `-dc`. Compare with `bench compare <run> <run>`.

## Safety gates (nothing irreversible)

Each state change is done by `scripts/rtx-spark-state.ps1 <action>` from an elevated
PowerShell: it says what it will change and how to undo it, waits for `YES`, and appends the
state before and after to `<results>/bbaum-pc-7/state/journal.jsonl`.

1. **Read-only preflight first:** `scripts/rtx-spark-preflight.ps1`. It prints GO / NO-GO for the
   Secure Boot change, restore points and the NVPCF test.
2. **BitLocker.** C: has a pre-boot password and no saved recovery key. If BitLocker also
   seals to the TPM (`Tpm*` protector type in the preflight), turning Secure Boot off makes the
   next Windows boot ask for the recovery key; without one the disk is lost. So:
   `bitlocker-recovery-key` adds a recovery password (shown once on screen, never written to
   disk) which you store off the machine; then `bitlocker-suspend` right before entering firmware
   setup, so the Secure Boot change does not trigger recovery at all.
3. **Restore point** (`restore-point`) before every Windows change; `npcf-disable` refuses to run
   without one from today.
4. **NVPCF test** is `npcf-disable` → reboot → benchmark → `npcf-enable` → reboot.
5. **The GPU reservation** is changed in the NVIDIA app (your note); record the value before and
   after in the log, change it only when [[EXP-20261104-ssfv1c]] needs the memory, and set it back after.
6. **Nothing is flashed.** The SSPM boot entry's DSDT override exists only in RAM for that boot;
   the BIOS and EC are not written. The live USB never mounts the internal NVMe.

## Steps

### 1. Windows ([[EXP-20261104-ssfqvw]])

```powershell
powershell -ExecutionPolicy Bypass -File scripts\rtx-spark-preflight.ps1      # elevated, read-only
uv run python scripts/llm-fetch.py llama-cpp
uv run python scripts/llm-fetch.py models --models gpt-oss-20b,gpt-oss-120b --dir D:\models
$env:ANVESANA_MODELS_DIR = "D:\models"          # the SPARKDATA drive; one copy for every OS
uv run python scripts/llm-conditions.py --label win-npcf-on --conditions ac,dc
# elevated: rtx-spark-state.ps1 restore-point; rtx-spark-state.ps1 npcf-disable; reboot
uv run python scripts/llm-conditions.py --label win-npcf-off --conditions ac,dc
# elevated: rtx-spark-state.ps1 npcf-enable; reboot
```

### 2. WSL ([[EXP-20261104-ssfs86]]; also the build host)

`wsl --install -d Ubuntu-24.04` (elevated, a state change: ask first), clone the repo inside
WSL (not under `/mnt`), then `bash scripts/wsl-setup.sh --nix --vllm`. WSL gets half of
Windows' RAM by default (about 15 GB while 96 GB is reserved for the GPU); the GPU memory is
what the model uses.

```bash
export ANVESANA_MODELS_DIR=/mnt/d/models
uv run python scripts/llm-conditions.py --label wsl --conditions ac,dc
~/.cache/anvesana/vllm-0.33.0/bin/vllm serve openai/gpt-oss-20b --revision 6cee5e81ee83917806bbde320786a8fb61efebee &
uv run python scripts/llm-concurrency.py --model openai/gpt-oss-20b --clients 8 --label wsl-vllm
```

### 3. Build the live image (in WSL)

```bash
nix build .#rtx-spark-live                                  # first build stops at openSha256
# put the printed "got: sha256-..." into nix/live.nix (openSha256), build again
uv run python scripts/acpi-hidden-devices.py <inventory snapshot>/acpi --expose SSPM --out nix/local/acpi
ANVESANA_ACPI_OVERRIDE=$PWD/nix/local/acpi/acpi-override.cpio nix build --impure .#rtx-spark-live
```

Write `result/iso/*.iso` to the boot USB (Rufus in DD mode, or `dd`). Format the second drive
exFAT with the label `SPARKDATA`, holding `models/` (and optionally `ssh/authorized_keys`).

### 4. Native NixOS ([[EXP-20261104-ssfv1c]], [[EXP-20261104-ssfy1p]])

Secure Boot off (after gate 2), boot the USB from the firmware boot menu, choose an entry:

```bash
cat /etc/anvesana-boot-entry                     # default | osi | sspm | simpledrm
bench inventory collect                          # snapshot of this boot: drivers, ACPI devices, firmware
ls /sys/bus/acpi/devices | grep -E 'NVDA8400|NVDA3000|MTK00055|NVDA300[AB]'
python3 /root/anvesana/scripts/llm-conditions.py --label nixos-$(cat /etc/anvesana-boot-entry) --conditions ac,dc
nvidia-smi -q -d PERFORMANCE,CLOCK,POWER         # clock-event reasons and limits, saved with the log
```

`bench` on the image runs from `/root/anvesana` with Nix's Python; results go to
`/mnt/sparkdata/results`, so they survive the reboot. vLLM on NixOS needs network (USB
Ethernet: the article's Debian install did not get Wi-Fi).

## Not verified yet

The NixOS image has not been built: there is no Nix on this machine until WSL is set up.
Things that may need fixing on the first build: the `openSha256` of the open kernel modules
(deliberately a fake hash), whether NixOS's ISO menu lists the specialisations as boot entries,
`modDirVersion` (the config says 7.0.14), and whether the Ubuntu config builds unchanged with
Nix's compiler.

## Sources

- Article: <https://www.mindstudio.ai/blog/linux-nvidia-rtx-spark-laptop>
- ASUS ProArt P16 on Arch Linux ARM: <https://josie.lol/blog/linux-rtx-spark> and its build,
  <https://github.com/pfeifferj/archlinuxarm-proart-p16> (@ `3484cc0`, MIT): kernel sources and
  hashes, the ACPI-override allocation patch, CPPC init, driver tuple, initrd modules, sleep policy.
