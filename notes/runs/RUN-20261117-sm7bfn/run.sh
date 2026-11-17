#!/usr/bin/env bash
# Posture walk on curiosity: both accelerometers and both custom sensors, 8 s in each of
# laptop, flat, tent and tablet; Enter between postures. Needs root and a person to move
# the laptop. Writes summary.txt to SPARKDATA (or /tmp); the copy beside this script is
# the one from 2026-11-17. Then prints the hinge angle per posture from that summary.
set -eu
here=$(dirname "$0")
[ "${1:-}" = --analyse ] || sudo python3 nix/n1x-sensors.py
python3 "$here/hinge.py" "${2:-$here/summary.txt}"
