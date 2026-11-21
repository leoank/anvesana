#!/usr/bin/env bash
# Does the GPU's ~52 W cap on curiosity follow the SoC's power limit (PL1), as on the HP OmniBook
# X 14 (NVIDIA/open-gpu-kernel-modules#1521)? Samples the SoC power-budget page (budget.py,
# read-only, root, every 2 s) while cuBLASLt runs alone, 120 s per data type, first with the
# balanced profile (EPP 127), then with power-saver (EPP 255), and back to balanced. Runs from
# the repo root as the desktop user; sudo for the sampler. Done on stock 620.70.06, on AC.
set -eu
out=${YAJNA_RUN_DIR:-$(dirname "$0")}
pp() { gdbus call --system --dest org.freedesktop.UPower.PowerProfiles \
  --object-path /org/freedesktop/UPower/PowerProfiles --method org.freedesktop.DBus.Properties.Set \
  org.freedesktop.UPower.PowerProfiles ActiveProfile "<\"$1\">" >/dev/null; }
sudo python3 "$(dirname "$0")/budget.py" 1800 "$out/budget-all.tsv" & bud=$!
trap 'pp balanced; sudo kill $bud 2>/dev/null || true' EXIT
nix develop -c anvesana-fhs -c "uv run bench setup --machine bbaum-pc-7"
one() {  # $1 profile, $2 output dir
  pp "$1"; mkdir -p "$2/results"
  nvidia-smi --query-gpu=timestamp,power.draw,clocks.sm,temperature.gpu,clocks_throttle_reasons.active \
    --format=csv -lms 2000 > "$2/smi.csv" & local smi=$!
  sleep 60
  ANVESANA_RESULTS_DIR="$2/results" nix develop -c anvesana-fhs -c \
    "uv run bench run --machine bbaum-pc-7 --only cublaslt --duration 120 --tag nixos-curiosity-pl1-$1" > "$2/run.log" 2>&1
  sleep 120; kill $smi
}
one balanced "$out"
one power-saver "$out/power-saver"
cp "$out/budget-all.tsv" "$out/power-saver/budget.tsv"
