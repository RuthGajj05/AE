#!/bin/sh
# Run the competitor monitor from cron and append its output to state/cron.log.
# Usage: scripts/run_monitor.sh "Business Name" business_type "Location" [--sms +1...]
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$REPO/state"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') $1 ==="
  "$REPO/.venv/bin/python" "$REPO/agent/monitor.py" "$@" 2>&1
  echo "=== exit $? ==="
} >> "$REPO/state/cron.log"
