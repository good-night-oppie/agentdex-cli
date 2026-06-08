#!/usr/bin/env bash
# tail_logs.sh <area>  — peek recent logs without flooding context.
AREA="${1:-app}"
LOG_DIR="${LOG_DIR:-./logs}"
tail -n 50 "$LOG_DIR/$AREA.log" 2>/dev/null || echo "no log file for $AREA at $LOG_DIR/$AREA.log"
