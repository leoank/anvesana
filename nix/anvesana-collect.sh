#!/usr/bin/env bash
# anvesana-collect: save this boot's logs and a hardware-functionality snapshot to the SPARKDATA
# drive, so a session on the live image can be read back on Windows (or by an agent) afterwards.
#
#   anvesana-collect journal [label]   journal + dmesg of this boot (fast; timer, resume, shutdown)
#   anvesana-collect full [label]      journal + a snapshot of every subsystem, with summary.txt
#
# Layout:  <root>/bootlogs/<host>/<boot start>_<boot entry>_<boot id>/
#            journal.txt dmesg.txt events.txt
#            snapshot-<HHMMSS>-<label>/summary.txt and one file per subsystem
# <root> is /mnt/sparkdata when that drive is present, else /var/log/anvesana (RAM on a live
# image: copy it off before shutting down). Runs as root; every probe is best effort.
set -u
mode=${1:-full}
label=$(printf '%s' "${2:-manual}" | tr -c 'A-Za-z0-9_.-' '_')

root=/var/log/anvesana
# SPARKDATA: the fstab automount usually has it; otherwise mount it by label, and say what happened.
if ! mountpoint -q /mnt/sparkdata; then
  timeout 20 ls /mnt/sparkdata >/dev/null 2>&1 || true            # triggers the automount
fi
if ! mountpoint -q /mnt/sparkdata && [ -e /dev/disk/by-label/SPARKDATA ]; then
  mkdir -p /mnt/sparkdata
  timeout 30 mount -t exfat -o uid=0,gid=0,fmask=0022,dmask=0022 /dev/disk/by-label/SPARKDATA /mnt/sparkdata \
    || echo "anvesana-collect: mounting SPARKDATA failed" >&2
fi
if mountpoint -q /mnt/sparkdata && touch /mnt/sparkdata/.anvesana-write-test 2>/dev/null; then
  rm -f /mnt/sparkdata/.anvesana-write-test; root=/mnt/sparkdata
else
  echo "anvesana-collect: SPARKDATA not available (label present: $([ -e /dev/disk/by-label/SPARKDATA ] && echo yes || echo no)); writing to $root" >&2
fi
entry=$(cat /etc/anvesana-boot-entry 2>/dev/null || echo unknown)
bootid=$(tr -d '-' </proc/sys/kernel/random/boot_id | cut -c1-8)
bootstart=$(date -d "@$(awk '/^btime/{print $2}' /proc/stat)" +%Y-%m-%d_%H%M%S 2>/dev/null || echo unknown)
host=$(cat /proc/sys/kernel/hostname)
# One folder per boot: the boot start derived from /proc/stat moves when the clock is adjusted
# (NTP, RTC), so reuse the folder that already carries this boot's ID.
existing=$(ls -d "$root/bootlogs/$host/"*_"$bootid" 2>/dev/null | head -1)
dir=${existing:-"$root/bootlogs/$host/${bootstart}_${entry//[^A-Za-z0-9_-]/_}_${bootid}"}
mkdir -p "$dir" || { echo "anvesana-collect: cannot write $dir" >&2; exit 1; }

now() { date +%H:%M:%S; }
# run <file> <command...>: command output (stdout+stderr, 60 s limit) into <file>, never fails
run() { local f=$1; shift; { echo "\$ $*"; timeout 60 "$@" 2>&1; echo "[exit $?]"; } >>"$f"; }
# as_user <command...>: inside the graphical session of the auto-login user (pactl, gsettings)
user=$(awk -F: '$3 == 1000 {print $1}' /etc/passwd)   # the auto-login user (no getent on PATH)
as_user() { [ -n "$user" ] && timeout 30 runuser -u "$user" -- env XDG_RUNTIME_DIR=/run/user/1000 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 "$@"; }

echo "$(date -Iseconds) $mode $label" >>"$dir/events.txt"
journalctl -b --no-pager -o short-precise >"$dir/journal.txt" 2>&1
dmesg -T >"$dir/dmesg.txt" 2>&1 || journalctl -k -b --no-pager >"$dir/dmesg.txt" 2>&1
cat /proc/cmdline >"$dir/cmdline.txt"

# Load at every collection (journal ones included, so a laggy or hanging session leaves a trail):
# the top CPU users, GPU utilisation for 5 s, and which GL/EGL driver the compositor has loaded.
{ echo "===== $(date -Iseconds) $mode $label, uptime $(cut -d' ' -f1 /proc/uptime) s, load $(cut -d' ' -f1-3 /proc/loadavg)"
  top -b -n 1 -w 200 -o %CPU 2>&1 | head -22
  echo "--- nvidia-smi dmon (5 s)"; timeout 15 nvidia-smi dmon -c 5 -s pucm 2>&1
  for p in $(pgrep -x gnome-shell; pgrep -x .gnome-shell-wr; pgrep -x Xwayland); do
    echo "--- graphics libraries in $(cat /proc/"$p"/comm 2>/dev/null) ($p)"
    grep -oE '[^/ ]*(nvidia|gallium|swrast|llvmpipe|mesa|EGL|GLX|gbm|vulkan)[^/ ]*\.so[^ ]*' /proc/"$p"/maps 2>/dev/null | sort -u | tr '\n' ' '; echo
    # both stacks are usually mapped; the open device nodes say which one draws
    echo "--- devices open in $(cat /proc/"$p"/comm 2>/dev/null) ($p)"
    ls -l /proc/"$p"/fd 2>/dev/null | grep -oE '/dev/(nvidia[a-z0-9-]*|dri/[a-zA-Z0-9]+)' | sort | uniq -c | tr '\n' ' '; echo
  done; echo; } >>"$dir/load.txt" 2>&1

[ "$mode" = journal ] && { sync; echo "anvesana-collect: journal -> $dir"; exit 0; }

s="$dir/snapshot-$(date +%H%M%S)-$label"
mkdir -p "$s"
sum="$s/summary.txt"
check() { printf '%-22s %-8s %s\n' "$1" "$2" "$3" >>"$sum"; }   # feature, OK/MISSING/INFO, detail

{ echo "anvesana live snapshot: $(date -Iseconds), label $label"
  echo "entry $entry, kernel $(uname -r), boot $bootid, uptime $(cut -d' ' -f1 /proc/uptime) s"
  echo; } >"$sum"

# ---- system
run "$s/system.txt" uname -a
run "$s/system.txt" systemctl --failed --no-pager
run "$s/system.txt" systemd-analyze
run "$s/system.txt" systemd-analyze critical-chain --no-pager
run "$s/system.txt" free -m
run "$s/system.txt" lsblk -f
run "$s/modules.txt" lsmod
run "$s/pci.txt" lspci -nnk
run "$s/usb.txt" lsusb -tv
run "$s/usb.txt" lsusb
failed=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
check "failed units" "$([ -z "$failed" ] && echo OK || echo INFO)" "${failed:-none}"

# ---- ACPI devices: status and the driver bound to each (NVDA* first, they are the SoC)
{ for d in /sys/bus/acpi/devices/*; do
    n=${d##*/}; st=$(cat "$d/status" 2>/dev/null || echo -)
    p=/sys/bus/platform/devices/$n
    drv=$( [ -e "$p/driver" ] && basename "$(readlink "$p/driver")" || echo - )
    echo "$n status=$st driver=$drv path=$(cat "$d/path" 2>/dev/null)"
  done; } | sort >"$s/acpi-devices.txt"
unbound=$(grep -E '^(NVDA|MTK|MSFT|PNP0C0A)' "$s/acpi-devices.txt" | grep 'status=15' | grep 'driver=-' \
  | awk '{print $1}' | tr '\n' ' ')
check "SoC ACPI unbound" INFO "${unbound:-none}"
check "SSPM (NVDA8400)" "$(grep -q '^NVDA8400:00 status=15 driver=SSPM_CI' "$s/acpi-devices.txt" && echo OK || echo MISSING)" \
  "$(grep '^NVDA8400' "$s/acpi-devices.txt" | head -1)"

# ---- GPU and display
run "$s/gpu.txt" nvidia-smi
run "$s/gpu.txt" nvidia-smi -q -d PERFORMANCE,CLOCK,POWER,MEMORY,TEMPERATURE
as_user eglinfo -B >"$s/gpu-egl.txt" 2>&1
as_user vulkaninfo --summary >"$s/gpu-vulkan.txt" 2>&1
as_user glxinfo -B >"$s/gpu-glx.txt" 2>&1
check "GPU (nvidia-smi)" "$(nvidia-smi -L >/dev/null 2>&1 && echo OK || echo MISSING)" "$(nvidia-smi -L 2>/dev/null | head -1)"
as_user env LIBVA_DRIVER_NAME=nvidia NVD_BACKEND=direct vainfo >"$s/gpu-vaapi.txt" 2>&1
check "VA-API decode" "$(grep -q 'VAEntrypointVLD' "$s/gpu-vaapi.txt" && echo OK || echo MISSING)" \
  "$(grep -c 'VAEntrypointVLD' "$s/gpu-vaapi.txt") decode profiles; $(grep -m1 'Driver version' "$s/gpu-vaapi.txt" | sed 's/.*: //')"
check "Vulkan" "$(grep -q 'deviceName' "$s/gpu-vulkan.txt" && echo OK || echo MISSING)" \
  "$(grep -m1 deviceName "$s/gpu-vulkan.txt" | sed 's/.*= //')"
check "OpenGL renderer" INFO "$(grep -m1 'OpenGL renderer' "$s/gpu-glx.txt" | sed 's/.*: //')"
check "EGL (Wayland)" INFO "$(grep -m1 -iE 'OpenGL (core profile )?renderer' "$s/gpu-egl.txt" | sed 's/.*: //')"
shell_devs=$(tail -n 60 "$dir/load.txt" | grep -A1 'devices open in .*gnome-shell' | tail -1)
check "compositor GPU" "$(printf '%s' "$shell_devs" | grep -q '/dev/nvidia[0-9]' && echo OK || echo INFO)" \
  "${shell_devs:-gnome-shell not running} (/dev/nvidiaN = NVIDIA GL; only dri nodes = Mesa)"
# KMS state: planes, framebuffer formats and modifiers, CRTC mode (debugfs)
mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug 2>/dev/null
for st in /sys/kernel/debug/dri/*/state; do echo "== $st"; cat "$st"; done >"$s/kms-state.txt" 2>&1
cat /sys/module/nvidia_drm/parameters/* >"$s/nvidia-drm-params.txt" 2>&1
grep -H . /sys/module/nvidia_drm/parameters/* >>"$s/nvidia-drm-params.txt" 2>&1
{ for c in /sys/class/drm/card*-*; do
    [ -e "$c/status" ] || continue
    echo "${c##*/}: $(cat "$c/status") enabled=$(cat "$c/enabled" 2>/dev/null) modes=$(head -3 "$c/modes" 2>/dev/null | tr '\n' ' ')"
  done
  for b in /sys/class/backlight/*; do
    [ -e "$b" ] || continue
    echo "backlight ${b##*/}: brightness=$(cat "$b/brightness") actual=$(cat "$b/actual_brightness" 2>/dev/null) max=$(cat "$b/max_brightness") type=$(cat "$b/type")"
  done; } >"$s/display.txt" 2>&1
check "panel connected" "$(grep -q ': connected' "$s/display.txt" && echo OK || echo MISSING)" \
  "$(grep ': connected' "$s/display.txt" | cut -d' ' -f1 | tr '\n' ' ')"
check "backlight control" "$(grep -q '^backlight' "$s/display.txt" && echo OK || echo MISSING)" \
  "$(grep '^backlight' "$s/display.txt" | head -1)"
as_user gnome-shell --version >>"$s/display.txt" 2>&1
check "session" INFO "$(loginctl list-sessions --no-legend 2>/dev/null | head -1) type=$(loginctl show-session "$(loginctl list-sessions --no-legend | awk 'NR==1{print $1}')" -p Type --value 2>/dev/null)"

# ---- input: keyboard, touchpad, touchscreen, pen, buttons, keyboard backlight
cat /proc/bus/input/devices >"$s/input.txt" 2>&1
run "$s/input-libinput.txt" libinput list-devices
names=$(grep '^N: Name=' "$s/input.txt" | cut -d'"' -f2)
has() { printf '%s\n' "$names" | grep -qiE "$1" && echo OK || echo MISSING; }
check "keyboard" "$(has 'keyboard')" "$(printf '%s\n' "$names" | grep -iE 'keyboard' | head -1)"
check "touchpad" "$(has 'touchpad')" "$(printf '%s\n' "$names" | grep -iE 'touchpad' | head -1)"
check "touchscreen" "$(grep -q 'Capabilities:.*touch' "$s/input-libinput.txt" && echo OK || has 'touchscreen|elan|wacom|goodix|hid-over-i2c')" \
  "$(grep -B12 'Capabilities:.*touch' "$s/input-libinput.txt" | grep -m1 '^Device' | sed 's/Device: *//')"
check "pen / stylus" "$(grep -q 'Capabilities:.*tablet' "$s/input-libinput.txt" && echo OK || echo MISSING)" \
  "$(grep -B12 'Capabilities:.*tablet ' "$s/input-libinput.txt" | grep -m1 '^Device' | sed 's/Device: *//')"
ls /sys/class/leds >"$s/leds.txt" 2>&1
# On bbaum-pc-7 the EC handles Fn + F8 itself (works on Linux, 2026-11-07); there is no LED device.
check "keyboard backlight" "$(grep -qi kbd "$s/leds.txt" && echo OK || echo INFO)" \
  "$(grep -i kbd "$s/leds.txt" | tr '\n' ' ')${s:+ (no LED device; EC handles Fn+F8)}"

# ---- GPIO / interrupts (the sensor hub's GpioInt, spi-hid)
{ mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug
  echo "== /sys/kernel/debug/gpio"; cat /sys/kernel/debug/gpio
  echo "== spi-hid / gpio / eint lines in /proc/interrupts"; grep -iE 'spi|hid|gpio|eint|mtk' /proc/interrupts
  echo "== kernel lines"; grep -iE 'spi.?hid|MSFW|PNP0C51|eint|gpio' "$dir/dmesg.txt"
  echo "== spi devices"; ls -l /sys/bus/spi/devices/ 2>&1; } >"$s/gpio-irq.txt" 2>&1

# ---- sensors (accelerometer, hinge, light), tablet mode
{ for d in /sys/bus/iio/devices/iio:device*; do
    [ -e "$d/name" ] && echo "${d##*/}: $(cat "$d/name")"
  done; } >"$s/sensors.txt" 2>&1
as_user timeout 5 monitor-sensor >"$s/sensors-proxy.txt" 2>&1   # iio-sensor-proxy's view, 5 s
check "sensor hub (spi-hid)" "$(ls -d /sys/bus/spi/drivers/spi_hid_acpi/spi-* >/dev/null 2>&1 && echo OK || echo MISSING)" \
  "$(grep -m1 -E 'anvesana: spi->irq|Missing IRQ|spi_hid' "$dir/dmesg.txt" | sed 's/^\[[^]]*\] //')"
check "IIO sensors" "$(grep -q 'iio:device' "$s/sensors.txt" && echo OK || echo MISSING)" \
  "$(grep 'iio:device' "$s/sensors.txt" | cut -d' ' -f2 | tr '\n' ' ')"
check "accelerometer" "$(grep -q 'Has accelerometer' "$s/sensors-proxy.txt" && echo OK || echo MISSING)" \
  "$(grep -m1 'Has accelerometer' "$s/sensors-proxy.txt")"
check "ambient light" "$(grep -q 'Has ambient light' "$s/sensors-proxy.txt" && echo OK || echo MISSING)" \
  "$(grep -m1 'Has ambient light' "$s/sensors-proxy.txt")"

# ---- audio
cat /proc/asound/cards >"$s/audio.txt" 2>&1
run "$s/audio.txt" aplay -l
run "$s/audio.txt" arecord -l
as_user pactl info >>"$s/audio.txt" 2>&1
as_user pactl list short sinks >>"$s/audio.txt" 2>&1
as_user pactl list short sources >>"$s/audio.txt" 2>&1
ls /sys/bus/soundwire/devices >"$s/audio-soundwire.txt" 2>&1
for c in /proc/asound/card[0-9]*; do
  n=${c##*card}; echo "===== card $n: $(cat "$c/id")"; amixer -c "$n" contents 2>&1
done >"$s/audio-mixer.txt"
echo "ALSA_CONFIG_UCM2=${ALSA_CONFIG_UCM2:-unset}" >"$s/audio-ucm.txt"
run "$s/audio-ucm.txt" alsaucm listcards
as_user wpctl status >>"$s/audio.txt" 2>&1
check "audio cards" "$(grep -q '^ *[0-9]' /proc/asound/cards 2>/dev/null && echo OK || echo MISSING)" \
  "$(grep '^ *[0-9]' /proc/asound/cards 2>/dev/null | sed 's/  */ /g' | tr '\n' ';')"
sinks=$(as_user pactl list short sinks 2>/dev/null | awk '{print $2}' | tr '\n' ' ')
check "audio sinks" "$(printf '%s' "$sinks" | grep -qE 'alsa_output' && echo OK || echo MISSING)" "${sinks:-none}"

# ---- network, bluetooth
run "$s/network.txt" ip -br addr
run "$s/network.txt" iw dev
run "$s/network.txt" nmcli -f GENERAL,CAPABILITIES device show
run "$s/network.txt" rfkill list
check "Wi-Fi" "$(iw dev 2>/dev/null | grep -q Interface && echo OK || echo MISSING)" "$(iw dev 2>/dev/null | awk '/Interface/{print $2}' | tr '\n' ' ')"
check "Wi-Fi connected" INFO "$(nmcli -t -f DEVICE,STATE,CONNECTION device 2>/dev/null | grep ':connected' | tr '\n' ' ')"
run "$s/bluetooth.txt" bluetoothctl show
run "$s/bluetooth.txt" bluetoothctl list
check "Bluetooth" "$(ls /sys/class/bluetooth 2>/dev/null | grep -q hci && echo OK || echo MISSING)" "$(ls /sys/class/bluetooth 2>/dev/null | tr '\n' ' ')"

# ---- camera
run "$s/camera.txt" v4l2-ctl --list-devices
check "camera" "$(ls /dev/video* >/dev/null 2>&1 && echo OK || echo MISSING)" "$(ls /dev/video* 2>/dev/null | tr '\n' ' ')"

# ---- power: battery, AC, suspend states, CPU frequency, thermals
{ for p in /sys/class/power_supply/*; do echo "== ${p##*/}"; cat "$p/uevent"; done; } >"$s/power.txt" 2>&1
run "$s/power.txt" upower -d
{ echo "state: $(cat /sys/power/state)"; echo "mem_sleep: $(cat /sys/power/mem_sleep 2>/dev/null)"
  echo "last suspend stats:"; grep -r . /sys/power/suspend_stats/ 2>/dev/null; } >"$s/suspend.txt"
bat=$(grep -l 'POWER_SUPPLY_TYPE=Battery' /sys/class/power_supply/*/uevent 2>/dev/null | head -1)
check "battery" "$([ -n "$bat" ] && echo OK || echo MISSING)" \
  "$( [ -n "$bat" ] && grep -E 'CAPACITY=|STATUS=' "$bat" | cut -d= -f2 | tr '\n' ' ')"
check "suspend (s2idle)" INFO "mem_sleep=[$(cat /sys/power/mem_sleep 2>/dev/null)] successes=$(cat /sys/power/suspend_stats/success 2>/dev/null) failures=$(cat /sys/power/suspend_stats/fail 2>/dev/null)"
{ for c in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$c/scaling_driver" ] || continue
    echo "${c##*/}: $(cat "$c/scaling_driver") gov=$(cat "$c/scaling_governor") cur=$(cat "$c/scaling_cur_freq") min=$(cat "$c/scaling_min_freq") max=$(cat "$c/scaling_max_freq") cpus=$(cat "$c/related_cpus")"
  done
  for t in /sys/class/thermal/thermal_zone*; do echo "${t##*/} $(cat "$t/type"): $(cat "$t/temp")"; done
  run /dev/stdout powerprofilesctl; } >"$s/cpu-thermal.txt" 2>&1
check "CPU frequency" "$(grep -q cppc "$s/cpu-thermal.txt" && echo OK || echo INFO)" "$(grep -m1 '^policy' "$s/cpu-thermal.txt")"
check "power profiles" INFO "$(powerprofilesctl get 2>/dev/null)"

# ---- firmware loading and kernel trouble, from this boot's log
grep -iE 'firmware|direct firmware load|failed to load' "$dir/dmesg.txt" >"$s/firmware.txt" 2>&1
grep -iE 'error|fail|timeout|timed out|warn|bug:|oops|call trace' "$dir/dmesg.txt" | grep -viE 'ignor' >"$s/kernel-problems.txt" 2>&1
check "firmware load errors" "$(grep -qiE 'failed|error' "$s/firmware.txt" && echo INFO || echo OK)" \
  "$(grep -ciE 'failed|error' "$s/firmware.txt") lines (firmware.txt)"
check "kernel problems" INFO "$(wc -l <"$s/kernel-problems.txt") lines (kernel-problems.txt)"

# ---- full anvesana inventory, for `bench inventory compare` against Windows
ANVESANA_RESULTS_DIR="$root/results" timeout 300 /run/current-system/sw/bin/bench inventory collect >"$s/inventory.txt" 2>&1

sync
echo "anvesana-collect: snapshot -> $s"
cat "$sum"
