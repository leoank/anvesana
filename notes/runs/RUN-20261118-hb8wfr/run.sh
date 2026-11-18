#!/usr/bin/env bash
# NPCF (NVDA0820) on curiosity: disassemble its _DSM from this boot's DSDT, try NVIDIA's Dynamic
# Boost daemon, and show which _DSM revisions the open kernel driver sends. Root for the first
# two steps (ACPI tables and the daemon are root-only); run from the repo root.
set -u
out=${YAJNA_RUN_DIR:-$(dirname "$0")}/tables   # vendor tables: kept out of git
mkdir -p "$out"
sudo sh -c "cp /sys/firmware/acpi/tables/DSDT $out/dsdt.dat && chown $(id -un) $out/dsdt.dat"
iasl=$(nix build --no-link --print-out-paths nixpkgs#acpica-tools)/bin/iasl
(cd "$out" && $iasl -d dsdt.dat >/dev/null) && grep -n -A40 'Method (NPCF, 4' "$out/dsdt.dsl" | grep -v '/\* [0-9A-F]\{4\} \*/'
pkg=$(dirname "$(dirname "$(readlink -f "$(command -v nvidia-smi)")")")
sudo systemd-run --unit=nvidia-powerd-test --property=Type=dbus --property=BusName=nvidia.powerd.server "$pkg/bin/nvidia-powerd"
sleep 3; journalctl -u nvidia-powerd-test -b --no-pager | tail -8
src=$(nix eval --raw --impure --expr '(builtins.getFlake (toString ./.)).nixosConfigurations.rtx-spark-desktop.config.hardware.nvidia.package.open.src')
grep -n 'NVPCF.*REVISION_ID' "$src/src/nvidia/interface/acpidsmguids.h"
