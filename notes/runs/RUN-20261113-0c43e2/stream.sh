#!/bin/sh
# Run as root, with the laptop in hand. Does the screen-side accelerometer (iio:device1,
# HID-SENSOR-200073.36) stream when the laptop moves?
# Writes sampling_frequency first: that sets the hub's report interval, so the power-on read
# gets 100 ms instead of 0xffffffff and the buffer enable does not hang (without patch 0004).
# 10 s still on the desk, then 20 s of tilting. Counts DATA reports per report id from the
# spi_hid trace. No raw reads (the hub does not answer GET_INPUT_REPORT).
# iio-sensor-proxy stays stopped. Output: /tmp/claude-1000/n1x-hub-stream.txt
T=/sys/kernel/tracing
D=/sys/bus/iio/devices/iio:device1
S=/sys/bus/platform/devices/HID-SENSOR-200073.36.auto/power/runtime_status
out=/tmp/claude-1000/n1x-hub-stream.txt
irq() { grep MSFW /proc/interrupts | awk '{print $2}'; }
data_ids() { grep -o 'input_body_complete: spi2.0: len=[0-9]* tx=\[[^]]*\] rx=\[01-..-..-..' $T/trace | sed -E 's/.*-(..)$/report id \1/' | sort | uniq -c; }
cleanup() {
  [ -n "$w" ] && kill -9 "$w" 2>/dev/null
  echo 0 > $D/buffer/enable 2>/dev/null
  echo 0 > $T/tracing_on
  echo 0 > $T/events/spi_hid/enable
}
trap cleanup EXIT
{
  systemctl stop iio-sensor-proxy
  echo 0 > $D/buffer/enable
  sleep 4
  echo "== start $(date +%T)  accel: $(cat $S)"
  echo 0 > $T/tracing_on; echo > $T/trace; echo 16384 > $T/buffer_size_kb
  echo 1 > $T/events/spi_hid/enable; echo 1 > $T/tracing_on

  echo accel_3d-dev1 > $D/trigger/current_trigger
  for c in x y z; do echo 1 > $D/scan_elements/in_accel_${c}_en; done
  echo 1 > $D/scan_elements/in_timestamp_en
  echo 64 > $D/buffer/length
  # Stock kernel: the power-on sleeps on the hub's 0xffffffff interval. The sleep is
  # interruptible, so killing the writer lets the power-on and the buffer enable finish.
  ( echo 1 > $D/buffer/enable ) & w=$!
  sleep 2
  if kill -0 $w 2>/dev/null; then
    echo "buffer enable in the power-on sleep (accel $(cat $S)); killing the writer"
    kill -9 $w; sleep 1
  fi
  w=
  echo "accel $(cat $S), buffer enable=$(cat $D/buffer/enable)"
  [ "$(cat $D/buffer/enable)" = 1 ] || { echo "!! buffer not enabled"; exit 1; }
  echo 10 > $D/in_accel_sampling_frequency
  echo "sampling_frequency: $(cat $D/in_accel_sampling_frequency)  hysteresis: $(cat $D/in_accel_hysteresis)"

  i0=$(irq)
  echo "== phase 1: 10 s STILL $(date +%T)"
  b1=$(timeout 10 cat /dev/iio:device1 | wc -c)
  i1=$(irq)
  echo "bytes: $b1   IRQ 232: $i0 -> $i1"
  echo "== phase 2: 20 s TILTING $(date +%T)"
  b2=$(timeout 20 cat /dev/iio:device1 | wc -c)
  i2=$(irq)
  echo "bytes: $b2   IRQ 232: $i1 -> $i2"
  echo 0 > $T/tracing_on
  echo "== DATA reports by report id (both phases)"
  data_ids
  echo "== kernel log"
  journalctl -k -b --no-pager --since "-45s" | grep -iE "spi_hid|MSFW|hid.sensor" | tail -20
  echo "== first DATA reports"
  grep 'rx=\[01-' $T/trace | head -20
} > "$out" 2>&1
chmod 644 "$out"
grep -vE "^ " "$out" | grep -v "input_body_complete"
echo "(full output in $out)"
