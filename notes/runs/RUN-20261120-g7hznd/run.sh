#!/usr/bin/env bash
# nvidia-powerd against NPCF with driver 620.70.06 on curiosity: build the open modules with the
# NVPCF 3.x read-size patch for the booted kernel, swap them in without a reboot, then run powerd
# once under gdb, printing every RM control's real status and saving each NVPCF exchange.
# Needs root for the module swap and powerd; run from the repo root on a booted curiosity, from
# a text console (step 2 stops GNOME). The NVPCF dumps are vendor data and stay out of git.
set -u
here=${YAJNA_RUN_DIR:-$(dirname "$0")}
nvpcf=$here/tables/nvpcf; mkdir -p "$nvpcf"

# 1. The patched modules, built from neusis's curiosity config (its kernel is the booted one)
#    with anvesana at this checkout.
mods=$(nix build --no-link --print-out-paths ~/workspace/repos/leoank/neusis/main#nixosConfigurations.curiosity.config.hardware.nvidia.package.open \
  --override-input anvesana "path:$PWD")/lib/modules/$(uname -r)/kernel/drivers/video

# 2. Swap them in. modprobe -r also drops nvidia-drm's two DRM helpers; load them back first.
sudo sh -c "
  systemctl stop display-manager nvidia-powerd; sleep 3
  modprobe -r nvidia_drm nvidia_modeset nvidia_uvm nvidia || exit 1
  insmod $mods/nvidia.ko && insmod $mods/nvidia-uvm.ko && insmod $mods/nvidia-modeset.ko
  modprobe drm_ttm_helper; modprobe drm_display_helper
  insmod $mods/nvidia-drm.ko modeset=1 fbdev=1
  systemctl start display-manager"
journalctl -k -b --no-pager --since -2min | grep -E 'NVRM.*(DSM|NVPCF)'   # nothing expected

# 3. powerd once, under gdb, with the service's PATH (it runs lscpu and dmidecode).
gdb=$(nix build --no-link --print-out-paths nixpkgs#gdb | grep -v -- -man)/bin/gdb
powerd=$(dirname "$(readlink -f "$(command -v nvidia-smi)")")/nvidia-powerd
path=$(systemctl show nvidia-powerd -p Environment | grep -o 'PATH=[^ ]*')
sudo env "$path" NVPCF_DIR="$nvpcf" "$gdb" -q -batch -x "$(dirname "$0")/rmctl.py" -x "$(dirname "$0")/rmctl.gdb" \
  --args "$powerd" 2>&1 | grep -vE '^\[|^$|^Using host|^Catchpoint' > "$here/powerd-gdb.out"
sudo chown -R "$(id -un)" "$nvpcf"
grep -E 'nvpcf #|exited' "$here/powerd-gdb.out"

# 4. powerd once more with every log level promoted to ERROR (its sink passes ERROR only).
sudo env "$path" "$gdb" -q -batch -ex "set pagination off" -ex "set follow-fork-mode parent" \
  -ex "handle SIGUSR1 SIGCHLD SIGPIPE nostop noprint pass" -x "$(dirname "$0")/loglevel.py" \
  --args "$powerd" 2>&1 | grep -vE '^\[|libthread_db' > "$here/powerd-log.out"
journalctl -b --no-pager -t nvidia-powerd --since -1min >> "$here/powerd-log.out"
