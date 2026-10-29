#!/usr/bin/env bash
# Scheduled node-health run for Linux: sync dependencies, run the suite, health-check it.
# Exit code 0 = healthy, 1 = a benchmark failed or regressed beyond tolerance.
#
# Monthly via cron (first Sunday 03:00; cron can't say "first Sunday", so check the day):
#   0 3 1-7 * * [ "$(date +\%u)" = 7 ] && ANVESANA_RESULTS_DIR=/srv/anvesana-results /path/to/anvesana/scripts/scheduled-run.sh
# or a systemd timer with OnCalendar=Sun *-*-01..07 03:00:00
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --extra tensorrt --extra cutlass --quiet
exec uv run bench run --health "$@"
