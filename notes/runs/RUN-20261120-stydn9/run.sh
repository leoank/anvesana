#!/usr/bin/env bash
# Does MSI Center's top power mode, set on Windows, carry over to Linux? Run after setting MSI
# Center's highest mode on Windows and rebooting straight into curiosity (stock 620.70.06, no
# nvidia-powerd): cuBLASLt alone with the bench's telemetry, plus the GPU's power and throttle
# reasons sampled beside it. Compare the sustained GPU power with ~51 W (Linux so far) and ~61 W
# (Windows). Runs from the repo root as the desktop user; performance power profile for the run.
set -eu
out=${YAJNA_RUN_DIR:-$(dirname "$0")}
export ANVESANA_RESULTS_DIR=${ANVESANA_RESULTS_DIR:-$out/results}
mkdir -p "$ANVESANA_RESULTS_DIR"
pp() { gdbus call --system --dest org.freedesktop.UPower.PowerProfiles \
  --object-path /org/freedesktop/UPower/PowerProfiles "$@"; }
before=$(pp --method org.freedesktop.DBus.Properties.Get org.freedesktop.UPower.PowerProfiles ActiveProfile | grep -o "'[a-z-]*'" | tr -d "'")
nvidia-smi --query-gpu=timestamp,power.draw,clocks.sm,temperature.gpu,clocks_throttle_reasons.active,clocks_throttle_reasons.sw_power_cap,clocks_throttle_reasons.hw_slowdown,clocks_throttle_reasons.sw_thermal_slowdown \
  --format=csv -lms 500 > "$out/smi.csv" & smi=$!
trap 'kill $smi; pp --method org.freedesktop.DBus.Properties.Set org.freedesktop.UPower.PowerProfiles ActiveProfile "<\"$before\">" >/dev/null' EXIT
pp --method org.freedesktop.DBus.Properties.Set org.freedesktop.UPower.PowerProfiles ActiveProfile '<"performance">' >/dev/null
echo "power profile: $before -> performance; AC: $(cat /sys/class/power_supply/*/online | tr '\n' ' ')"
nix develop -c anvesana-fhs -c "uv run bench setup --machine bbaum-pc-7"
nix develop -c anvesana-fhs -c "uv run bench run --machine bbaum-pc-7 --only cublaslt --tag nixos-curiosity-msi-top"
nix develop -c anvesana-fhs -c "uv run bench compare bbaum-pc-7@baseline:windows bbaum-pc-7@latest --markdown $out/compare.md"
