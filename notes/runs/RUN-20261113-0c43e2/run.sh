#!/bin/sh
# Run as root, with the laptop ON THE DESK, UNTOUCHED for the whole run (~30 s).
# Does hysteresis 0 make the screen-side accelerometer (iio:device1) stream while still?
#  1. write in_accel_hysteresis=0 while the sensor is off (as a udev rule would at boot)
#  2. power on (stock kernel: kill the writer stuck in the power-on sleep)
#  3. 10 s capture with the current hysteresis, then (if it was not accepted while off)
#     write 0 while on and capture 10 s again
#  4. restore the original hysteresis, buffer off. iio-sensor-proxy stays stopped.
D=/sys/bus/iio/devices/iio:device1
S=/sys/bus/platform/devices/HID-SENSOR-200073.36.auto/power/runtime_status
out=/tmp/claude-1000/n1x-hub-hyst.txt
cleanup() {
  [ -n "$w" ] && kill -9 "$w" 2>/dev/null
  echo "$orig" > $D/in_accel_hysteresis 2>/dev/null
  echo 0 > $D/buffer/enable 2>/dev/null
}
trap cleanup EXIT
cap() { timeout 10 cat /dev/iio:device1 | wc -c; }
irq() { grep MSFW /proc/interrupts | awk '{print $2}'; }
{
  systemctl stop iio-sensor-proxy
  echo 0 > $D/buffer/enable
  sleep 4
  orig=$(cat $D/in_accel_hysteresis)
  echo "== accel $(cat $S), hysteresis $orig"
  echo "== 1. hysteresis 0 while off"
  echo 0 > $D/in_accel_hysteresis; echo "write rc $?, reads $(cat $D/in_accel_hysteresis 2>&1)"

  echo accel_3d-dev1 > $D/trigger/current_trigger
  for c in x y z; do echo 1 > $D/scan_elements/in_accel_${c}_en; done
  echo 1 > $D/scan_elements/in_timestamp_en
  echo 256 > $D/buffer/length
  ( echo 1 > $D/buffer/enable ) & w=$!
  sleep 2
  kill -0 $w 2>/dev/null && { kill -9 $w; sleep 1; }
  w=
  echo "== 2. accel $(cat $S), buffer=$(cat $D/buffer/enable), hysteresis now $(cat $D/in_accel_hysteresis 2>&1)"

  i0=$(irq); b=$(cap); echo "== 3a. 10 s still: $b bytes ($((b / 24)) samples), IRQ +$(( $(irq) - i0 ))"
  echo 0 > $D/in_accel_hysteresis; echo "hysteresis 0 while on: rc $?, reads $(cat $D/in_accel_hysteresis 2>&1)"
  i0=$(irq); b=$(cap); echo "== 3b. 10 s still: $b bytes ($((b / 24)) samples), IRQ +$(( $(irq) - i0 ))"
  echo "== kernel log"
  journalctl -k -b --no-pager --since "-40s" | grep -iE "spi_hid|MSFW|hid.sensor" | tail -10
} > "$out" 2>&1
chmod 644 "$out"
cat "$out"
