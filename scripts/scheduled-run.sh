#!/usr/bin/env bash
# Scheduled node-health run for Linux: install this node's dependencies, run its suite, health-check it.
# Exit code 0 = healthy, 1 = a benchmark failed or regressed beyond tolerance.
# Extra arguments are passed to `anvesana run` (e.g. --machine ID --tag NAME).
#
# Monthly via cron (first Sunday 03:00; cron can't say "first Sunday", so check the day):
#   0 3 1-7 * * [ "$(date +\%u)" = 7 ] && ANVESANA_RESULTS_DIR=/srv/anvesana-results /path/to/anvesana/scripts/scheduled-run.sh
# or a systemd timer with OnCalendar=Sun *-*-01..07 03:00:00
set -euo pipefail
cd "$(dirname "$0")/.."

machine_args=()
for ((i = 1; i <= $#; i++)); do
  if [ "${!i}" = "--machine" ]; then j=$((i + 1)); machine_args=(--machine "${!j}"); fi
done

# Core packages first (inexact: keep whatever extras are installed), then exactly
# the extras this node's profile needs, from the committed uv.lock.
uv sync --inexact --locked --quiet
uv run --no-sync anvesana setup "${machine_args[@]}"
exec uv run --no-sync anvesana run --health "$@"
