#!/usr/bin/env bash
# Boot an anvesana live ISO in QEMU (aarch64 `virt`, UEFI) and keep everything it shows:
#
#   scripts/vm-test.sh <iso> <out-dir> [seconds=900] [entry=serial] [mode=kernel|uefi]
#
#   mode kernel  (default) the kernel, initrd and command line of the ISO's boot entry whose menu
#                label contains <entry>, loaded by UEFI firmware; the ISO is attached as a disk,
#                so stage 1 finds it by label as on hardware. Use the `serial` entry: the console
#                then also goes to ttyAMA0, captured in serial.log.
#   mode uefi    the ISO itself through the firmware and its GRUB menu (default entry); screen only.
#
# Output in <out-dir>: serial.log, shots/NNNN.png (the screen every 10 s), qemu.log, and
# sparkdata/: the contents of the blank exFAT "SPARKDATA" disk the VM wrote its logs to.
# After <seconds> the VM gets an ACPI power button press (so shutdown collection runs), then
# up to 3 min to power off. Runs in WSL or on any aarch64 Linux with Nix; uses sudo for loop
# mounts. Without KVM the CPU is emulated (TCG): boot takes minutes.
set -euo pipefail
iso=$(readlink -f "$1"); out=$2; secs=${3:-900}; entry=${4:-serial}; mode=${5:-kernel}
repo=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$out/shots"; out=$(cd "$out" && pwd)

if ! command -v qemu-system-aarch64 >/dev/null || ! command -v mkfs.exfat >/dev/null || ! command -v socat >/dev/null; then
  exec nix shell --inputs-from "$repo" nixpkgs#qemu nixpkgs#exfatprogs nixpkgs#socat -c "$0" "$@"
fi
share=$(dirname "$(readlink -f "$(command -v qemu-system-aarch64)")")/../share/qemu
fw=$share/edk2-aarch64-code.fd

# Blank data drive, like the real SPARKDATA stick
spark=$out/sparkdata.img
rm -f "$spark"; truncate -s 4G "$spark"; mkfs.exfat -L SPARKDATA "$spark" >/dev/null

boot=()
if [ "$mode" = kernel ]; then
  mnt=$(mktemp -d); sudo mount -o loop,ro "$iso" "$mnt"
  cfg=$mnt/EFI/BOOT/grub.cfg
  # first menuentry whose label contains $entry: its linux and initrd lines
  block=$(awk -v e="$entry" '/^ *menuentry /{inb = index($0, e) > 0 && !done} inb && /^ *linux /{print; } inb && /^ *initrd /{print; done=1; inb=0}' "$cfg" | head -2)
  linux=$(printf '%s\n' "$block" | awk '/linux /{print $2}')
  args=$(printf '%s\n' "$block" | sed -n 's/^ *linux [^ ]* //p' | sed 's/\${isoboot}//')
  initrd=$(printf '%s\n' "$block" | awk '/initrd /{print $2}')
  [ -n "$linux" ] && [ -n "$initrd" ] || { echo "no boot entry matching '$entry' in $cfg" >&2; sudo umount "$mnt"; exit 1; }
  cp "$mnt$linux" "$out/Image"; cp "$mnt$initrd" "$out/initrd"; sudo umount "$mnt"; rmdir "$mnt"
  echo "$args" >"$out/cmdline.txt"
  boot=(-kernel "$out/Image" -initrd "$out/initrd" -append "$args")
  echo "entry '$entry': $args"
fi

mon=$out/qemu-monitor.sock; rm -f "$mon"
qemu-system-aarch64 \
  -machine virt -cpu max -smp 8 -m 8G -accel tcg,thread=multi \
  -bios "$fw" \
  "${boot[@]}" \
  -drive if=none,id=iso,file="$iso",format=raw,readonly=on -device virtio-blk-pci,drive=iso \
  -drive if=none,id=spark,file="$spark",format=raw -device virtio-blk-pci,drive=spark \
  -device virtio-gpu-pci -display none \
  -device qemu-xhci -device usb-kbd -device usb-tablet \
  -nic user,model=virtio-net-pci \
  -serial file:"$out/serial.log" \
  -monitor unix:"$mon",server,nowait \
  -no-reboot >"$out/qemu.log" 2>&1 &
qpid=$!

# The monitor runs a command only while the connection is open: keep it open for 2 s.
monitor() { { printf '%s\n' "$1"; sleep 2; } | timeout 8 socat - UNIX-CONNECT:"$mon" >>"$out/monitor.log" 2>&1 || true; }

n=0; t0=$(date +%s); stop_at=$((t0 + secs)); sent=0
while kill -0 "$qpid" 2>/dev/null; do
  n=$((n + 1)); monitor "screendump $out/shots/$(printf %04d $n).ppm"   # QEMU 10 HMP: PPM only
  now=$(date +%s)
  if [ "$sent" = 0 ] && [ "$now" -ge "$stop_at" ]; then
    echo "$(date +%T) power button (shutdown collection)"; monitor "system_powerdown"; sent=1
  fi
  if [ "$sent" = 1 ] && [ "$now" -ge $((stop_at + 180)) ]; then echo "no power-off after 3 min: quitting"; monitor quit; fi
  sleep 10
done
wait "$qpid" || true
echo "VM stopped after $(( $(date +%s) - t0 )) s; $n screenshots"

# PPM -> PNG (standard library only), skipping repeats of the previous screen
python3 - "$out/shots" <<'PY'
import sys, zlib, struct, hashlib
from pathlib import Path
def png(w, h, rgb):
    raw = b"".join(b"\0" + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
last = None; kept = 0
for f in sorted(Path(sys.argv[1]).glob("*.ppm")):
    data = f.read_bytes(); parts = data.split(maxsplit=4)       # P6 w h maxval pixels
    if len(parts) < 5 or parts[0] != b"P6":
        f.unlink(); continue
    w, h = int(parts[1]), int(parts[2]); pix = parts[4][: w * h * 3]
    digest = hashlib.sha1(pix).digest()
    if digest != last:
        f.with_suffix(".png").write_bytes(png(w, h, pix)); kept += 1
    last = digest; f.unlink()
print(f"{kept} distinct screens kept as PNG")
PY

# What the VM wrote to SPARKDATA
mnt=$(mktemp -d); sudo mount -o loop,ro "$spark" "$mnt"
rm -rf "$out/sparkdata"; cp -r "$mnt" "$out/sparkdata"; sudo umount "$mnt"; rmdir "$mnt"
find "$out/sparkdata" -type f | sed "s|$out/||" | sort
