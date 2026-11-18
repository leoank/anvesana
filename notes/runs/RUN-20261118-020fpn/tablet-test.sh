#!/usr/bin/env bash
# Try n1x-tablet-mode on the running live system, without a rebuild: hide the hub's IIO
# accelerometers from iio-sensor-proxy (runtime udev rule), restart the proxy, run the daemon
# in the foreground. Ctrl-C puts everything back. Run: sudo /tmp/claude-1000/n1x-tablet-test.sh
set -u
repo=/home/ank/workspace/repos/leoank/anvesana/main
rule=/run/udev/rules.d/99-n1x-tablet-test.rules
log=/tmp/claude-1000/n1x-tablet-test.log
undo() {
  rm -f "$rule"; udevadm control --reload
  udevadm trigger --action=change --subsystem-match=iio; udevadm settle
  systemctl restart iio-sensor-proxy
  echo "restored: rule removed, iio-sensor-proxy restarted"
}
trap undo EXIT
mkdir -p /run/udev/rules.d
echo 'SUBSYSTEM=="iio", DEVPATH=="*/spi-MSFW1111:00/*", ATTR{name}=="accel_3d", ENV{IIO_SENSOR_PROXY_TYPE}=""' > "$rule"
udevadm control --reload
udevadm trigger --action=change --subsystem-match=iio; udevadm settle
systemctl stop iio-sensor-proxy
echo "== udev types now:"; for d in /sys/bus/iio/devices/iio:device*; do
  echo "  $(cat $d/name): $(udevadm info -q property -p $d | grep IIO_SENSOR_PROXY_TYPE)"; done
( sleep 3; systemctl start iio-sensor-proxy
  echo "== input devices:"; grep -E 'N: Name="N1X' /proc/bus/input/devices | sed 's/^/  /'
  echo "== now fold the laptop: laptop, flat, tent, tablet (folded back), and back; Ctrl-C ends" ) &
/home/ank/.nix-profile/bin/python3 -u "$repo/nix/n1x-tablet-mode.py" 2>&1 \
  | while IFS= read -r l; do echo "$(date +%T) $l"; done | tee "$log"
