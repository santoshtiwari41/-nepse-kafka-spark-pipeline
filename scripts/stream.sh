#!/usr/bin/env bash
# Manage the Spark Structured Streaming job (runs in the background on spark-master).
#   ./scripts/stream.sh start [--from-beginning]
#   ./scripts/stream.sh stop | status | logs | reset
set -euo pipefail

LOG=/tmp/stream_processor.log
running() { docker exec spark-master pgrep -f stream_processor.py > /dev/null; }

case "${1:-}" in
  start)
    if running; then echo "already running"; exit 0; fi
    shift
    docker exec -d spark-master bash -c \
      "/opt/spark/bin/spark-submit /opt/spark-apps/stream_processor.py $* > $LOG 2>&1"
    echo -n "starting"
    for _ in $(seq 60); do
      if docker exec spark-master grep -q "Streaming queries running" $LOG 2>/dev/null; then
        echo; docker exec spark-master grep "Streaming queries running" $LOG; exit 0
      fi
      if ! running; then echo; echo "failed — log:"; docker exec spark-master tail -30 $LOG; exit 1; fi
      echo -n "."; sleep 2
    done
    echo; echo "still starting — check: $0 logs" ;;
  stop)
    # SIGTERM → Spark stops the queries; checkpoints let the next start resume exactly
    docker exec spark-master pkill -f stream_processor.py && echo "stopped" || echo "not running" ;;
  status)
    if running; then
      echo "running — Spark UI: http://localhost:4040/StreamingQuery/"
    else
      echo "not running"
    fi ;;
  logs)
    docker exec spark-master tail -f $LOG ;;
  reset)
    # Forget stream progress and streaming outputs (batch-layer data is kept)
    if running; then echo "stop the stream first"; exit 1; fi
    docker exec namenode hdfs dfs -rm -r -f -skipTrash /nepse/checkpoints/* /nepse/bronze/ticks \
      /nepse/gold/candles_1m /nepse/gold/sector_flow_1m /nepse/gold/alerts > /dev/null
    echo "streaming checkpoints and outputs removed" ;;
  *)
    sed -n '2,4p' "$0"; exit 1 ;;
esac
