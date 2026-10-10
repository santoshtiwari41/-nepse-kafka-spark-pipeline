#!/usr/bin/env bash
# Stop the stack.  ./scripts/stop.sh          → stop, keep all data
#                  ./scripts/stop.sh --clean  → remove containers AND Kafka/HDFS data
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--clean" ]; then
  read -r -p "Delete all Kafka topics and HDFS data? [y/N] " answer
  [ "$answer" = y ] || { echo "Aborted."; exit 1; }
  docker compose down -v
else
  docker compose stop
fi
