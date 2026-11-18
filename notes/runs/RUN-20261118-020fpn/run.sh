#!/usr/bin/env bash
# Try the internal-keyboard quirk on the running live system (tmpfs /etc; gone on reboot).
# Run: sudo /tmp/claude-1000/n1x-kbd-quirk-test.sh, then log out and back in (libinput reads
# quirks when GNOME starts), then run sudo /tmp/claude-1000/n1x-tablet-test.sh again.
set -eu
mkdir -p /etc/libinput
cat > /etc/libinput/local-overrides.quirks <<'Q'
[N1X MKB0001 internal keyboard]
MatchUdevType=keyboard
MatchBus=i2c
MatchVendor=0x0DB0
MatchProduct=0x1606
AttrKeyboardIntegration=internal
Q
kbd=$(grep -l 'MKB0001' /sys/class/input/event*/device/name | head -1 | cut -d/ -f5)
echo "keyboard: /dev/input/$kbd; libinput quirks (expect AttrKeyboardIntegration=internal):"
/nix/store/fjgcp2669hp1rcynh0jw33hvbibvpjld-libinput-1.31.3-bin/bin/libinput quirks list "/dev/input/$kbd"
