#!/usr/bin/env bash
# Success criteria of EXP-20261113-0c42xp on a boot of curiosity-live with patch 0004, the
# spi-hid GET_INPUT_REPORT change and the hysteresis udev rule. Runs as the desktop user.
set -u
echo "== kernel"; uname -r; uptime
echo "== spi-hid timeouts / hub resets (expect none)"
journalctl -k -b --no-pager | grep -iE 'timed out|reset|MSFW|spi_hid' || true
echo "== accelerometer hysteresis (expect 0)"
for d in /sys/bus/iio/devices/iio:device*; do
  echo "$d $(cat "$d/name") $(cat "$d/in_accel_hysteresis" 2>/dev/null)"
done
echo "== runtime PM (expect no resuming)"
grep -H . /sys/bus/platform/devices/HID-SENSOR-*/power/runtime_status
echo "== iio-sensor-proxy (laptop untouched on the desk)"
systemctl is-active iio-sensor-proxy
timeout 6 monitor-sensor --accel 2>&1 | head
gdbus call --system --dest net.hadess.SensorProxy --object-path /net/hadess/SensorProxy \
  --method org.freedesktop.DBus.Properties.GetAll net.hadess.SensorProxy
