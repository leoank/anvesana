#!/bin/sh
# Run as root. Reproduce the accel power-on hang with probes armed, to see the poll_value
# _hid_sensor_power_state() sleeps on (msleep_interruptible(poll_value * 2)).
# Recipe seen on curiosity 2026-11-12: after spi-hid resets the hub (a GET_INPUT_REPORT
# timeout does that), enabling iio:device1's buffer hangs in the power-on sleep.
#  1. arm kprobes (poll read, feature get/set, power state) and the spi_hid events
#  2. one in_accel_x_raw read -> times out -> spi-hid resets the hub
#  3. enable the buffer in the background; after 5 s, if the accel is still 'resuming',
#     that is the hang: kill the writer (the sleep is interruptible) and collect the trace
# iio-sensor-proxy stays stopped. Output: /tmp/claude-1000/n1x-poll-repro.txt
T=/sys/kernel/tracing
D=/sys/bus/iio/devices/iio:device1
S=/sys/bus/platform/devices/HID-SENSOR-200073.36.auto/power/runtime_status
out=/tmp/claude-1000/n1x-poll-repro.txt
cleanup() {
  [ -n "$w" ] && kill -9 "$w" 2>/dev/null
  echo 0 > $D/buffer/enable 2>/dev/null
  echo 0 > $T/tracing_on
  echo 0 > $T/events/spi_hid/enable
  echo 0 > $T/events/kprobes/enable 2>/dev/null
  echo > $T/kprobe_events
}
trap cleanup EXIT
{
  systemctl stop iio-sensor-proxy
  echo 0 > $D/buffer/enable
  sleep 4
  echo "== start $(date +%T)  accel: $(cat $S)"

  echo 0 > $T/tracing_on
  echo > $T/trace
  echo 16384 > $T/buffer_size_kb
  echo > $T/kprobe_events
  echo 'r:pollret hid_sensor_iio_common:hid_sensor_read_poll_value ret=$retval:s32' >> $T/kprobe_events
  echo 'p:getf hid_sensor_hub:sensor_hub_get_feature rid=%x1:u32 idx=%x2:u32 size=%x3:s32 buf=%x4:x64' >> $T/kprobe_events
  echo 'r:getfret hid_sensor_hub:sensor_hub_get_feature ret=$retval:s32' >> $T/kprobe_events
  echo 'p:setf hid_sensor_hub:sensor_hub_set_feature rid=%x1:u32 idx=%x2:u32 size=%x3:s32 val=+0(%x4):s32' >> $T/kprobe_events
  echo 'r:setfret hid_sensor_hub:sensor_hub_set_feature ret=$retval:s32' >> $T/kprobe_events
  echo 'p:pstate hid_sensor_trigger:_hid_sensor_power_state on=%x1:u8' >> $T/kprobe_events
  echo 'p:msl msleep_interruptible ms=%x0:u32 comm=$comm' >> $T/kprobe_events
  echo 1 > $T/events/kprobes/enable
  echo 1 > $T/events/spi_hid/enable
  echo 1 > $T/tracing_on

  echo "== reset the hub: one raw read $(date +%T)"
  timeout 15 cat $D/in_accel_x_raw; echo " (rc $?)"
  sleep 3
  echo "== accel: $(cat $S); enabling the buffer $(date +%T)"
  echo accel_3d-dev1 > $D/trigger/current_trigger
  for c in x y z; do echo 1 > $D/scan_elements/in_accel_${c}_en; done
  ( echo 1 > $D/buffer/enable ) &
  w=$!
  sleep 5
  st=$(cat $S)
  echo "== after 5 s: accel $st, writer $(kill -0 $w 2>/dev/null && echo 'still blocked' || echo done)"
  if kill -0 $w 2>/dev/null; then
    echo "-- writer stack"; cat /proc/$w/stack
    kill -9 $w; sleep 1; w=
    echo "-- after kill: accel $(cat $S)"
  fi
  echo 0 > $T/tracing_on
  echo "== kernel log"
  journalctl -k -b --no-pager --since "-40s" | grep -iE "spi_hid|MSFW|hid.sensor" | tail -20
  echo "== trace (kprobes and spi_hid, last 400 lines)"
  grep -vE "^#" $T/trace | tail -400
} > "$out" 2>&1
chmod 644 "$out"
grep -E "^==|^--|rc " "$out"
grep -E "pollret|msl:" "$out" | tail -5
echo "(full output in $out)"
