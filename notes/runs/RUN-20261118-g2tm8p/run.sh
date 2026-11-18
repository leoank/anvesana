#!/usr/bin/env bash
# Phase 5: the compute suite on native Linux (curiosity: NixOS, kernel 7.0.14-1022-nvidia,
# driver 615.78.08), compared with the Windows baseline. Runs from the repo root as the desktop
# user, in the flake's FHS environment (anvesana-fhs: uv + Nix's Python 3.12, and pip's cmake,
# ninja and nvcc runnable for CUTLASS). Second run, after the full TensorRT and CUTLASS fixes.
# Disk and llm are skipped: no like-for-like disk on the live system, and llm was compared in the
# RTX Spark replication. Power profile "performance" for the run, back to the previous one after.
set -eu
out=${YAJNA_RUN_DIR:-$(dirname "$0")}
export ANVESANA_RESULTS_DIR=${ANVESANA_RESULTS_DIR:-$out/results}
mkdir -p "$ANVESANA_RESULTS_DIR"
pp() { gdbus call --system --dest org.freedesktop.UPower.PowerProfiles \
  --object-path /org/freedesktop/UPower/PowerProfiles "$@"; }
before=$(pp --method org.freedesktop.DBus.Properties.Get org.freedesktop.UPower.PowerProfiles ActiveProfile | grep -o "'[a-z-]*'" | tr -d "'")
trap 'pp --method org.freedesktop.DBus.Properties.Set org.freedesktop.UPower.PowerProfiles ActiveProfile "<\"$before\">" >/dev/null' EXIT
pp --method org.freedesktop.DBus.Properties.Set org.freedesktop.UPower.PowerProfiles ActiveProfile '<"performance">' >/dev/null
echo "power profile: $before -> performance; AC: $(cat /sys/class/power_supply/*/online | tr '\n' ' ')"
nix develop -c anvesana-fhs -c "uv run bench setup --machine bbaum-pc-7"
nix develop -c anvesana-fhs -c "uv run bench run --machine bbaum-pc-7 --skip disk,llm --tag nixos-curiosity-perf-ac" \
  || echo "bench run exited $? (a partial run still gets compared)"
nix develop -c anvesana-fhs -c "uv run bench compare bbaum-pc-7@baseline:windows bbaum-pc-7@latest --markdown $out/compare.md"
