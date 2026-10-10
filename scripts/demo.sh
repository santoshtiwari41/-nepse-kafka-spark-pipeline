#!/usr/bin/env bash
# Guided demo: runs every part of the pipeline in order and pauses (Enter) between steps.
#
#   ./scripts/demo.sh                  # LIVE if NEPSE is open, otherwise REPLAY of the latest day
#   ./scripts/demo.sh --replay         # always REPLAY (e.g. no internet)
#   ./scripts/demo.sh --speed 10       # slower replay → more intraday candles
#   ./scripts/demo.sh --date 2026-10-09 --batch   # replay a given day; re-run the batch layer first
set -euo pipefail
cd "$(dirname "$0")/.."

SPEED=60; DATE=""; FORCE_REPLAY=false; RUN_BATCH=false
while [ $# -gt 0 ]; do
  case $1 in
    --speed) SPEED=$2; shift ;;
    --date) DATE=$2; shift ;;
    --replay) FORCE_REPLAY=true ;;
    --batch) RUN_BATCH=true ;;
    *) sed -n '2,8p' "$0"; exit 1 ;;
  esac
  shift
done

PY=.venv/bin/python
mkdir -p logs
PRODUCER_PID=""
cleanup() {
  [ -n "$PRODUCER_PID" ] && kill "$PRODUCER_PID" 2>/dev/null && echo "producer stopped"
}
trap cleanup EXIT

step() { printf '\n\033[1;34m━━ %s ━━\033[0m\n' "$1"; }
say()  { printf '   %s\n' "$@"; }
pause() { read -r -p $'\n   ⏎  Enter to continue… ' _; }

# ── 1 ───────────────────────────────────────────────────────────────
step "1/6  Start the big data stack (Kafka, HDFS, Spark, dashboard)"
./scripts/start.sh
say "" "Open in the browser:" \
    "  Dashboard   http://localhost:8501" \
    "  Kafka UI    http://localhost:8085" \
    "  HDFS        http://localhost:9870   (Utilities → Browse the file system → /nepse)" \
    "  Spark       http://localhost:8080"
pause

# ── 2 ───────────────────────────────────────────────────────────────
step "2/6  Batch layer — historical data in HDFS (Spark SQL + MLlib)"
if $RUN_BATCH || ! docker exec namenode hdfs dfs -test -e /nepse/gold/latest_snapshot; then
  say "Running: CSV → bronze → silver (cleaning) → gold (indicators) → MLlib → SQL (~5 min)"
  ./scripts/run_batch.sh
else
  say "Gold layer already in HDFS — showing the Spark SQL answers (use --batch to recompute everything)"
  ./scripts/spark_submit.sh batch_queries.py 2>&1 | grep -v -E "WARN|NativeCodeLoader"
fi
say "" "Dashboard → 'Stock explorer', 'Market & sectors', 'Screener' tabs show this batch output."
pause

# ── 3 ───────────────────────────────────────────────────────────────
step "3/6  Speed layer — start Spark Structured Streaming"
./scripts/stream.sh start
say "Spark UI → http://localhost:4040/StreamingQuery/ shows the 5 streaming queries."
pause

# ── 4 ───────────────────────────────────────────────────────────────
step "4/6  Feed the stream: LIVE if NEPSE is open, otherwise REPLAY"
MODE=REPLAY
if ! $FORCE_REPLAY; then
  say "Asking the NEPSE API whether the market is open…"
  OPEN=$(timeout 30 $PY -c "import sys; sys.path.insert(0, 'ingestion')
from live_producer import NepseApi; print(NepseApi().market_open())" 2>/dev/null || echo "unreachable")
  say "market open: $OPEN"
  [ "$OPEN" = "True" ] && MODE=LIVE
fi
if [ "$MODE" = LIVE ]; then
  $PY -u ingestion/live_producer.py > logs/producer.log 2>&1 &
else
  $PY -u ingestion/replay_producer.py --speed "$SPEED" --loop ${DATE:+--date "$DATE"} > logs/producer.log 2>&1 &
fi
PRODUCER_PID=$!
sleep 4
say "$MODE producer running (log: logs/producer.log)" "$(head -1 logs/producer.log)" "" \
    "Show: Kafka UI → Topics → nepse.ticks → Messages (ticks arriving)" \
    "      Dashboard → 'Live market' (badge = $MODE, movers, sector map, alerts, intraday candles)"
pause

# ── 5 ───────────────────────────────────────────────────────────────
step "5/6  Fault tolerance — kill the streaming job while ticks keep arriving"
./scripts/stream.sh stop
say "Stream is down; the producer keeps writing to Kafka. Waiting 20 s…"
sleep 20
./scripts/stream.sh start
say "Restarted from the checkpoint: Spark resumes at the exact Kafka offset — nothing lost," \
    "nothing duplicated. Check:  ./scripts/spark_submit.sh stream_report.py"
pause

# ── 6 ───────────────────────────────────────────────────────────────
step "6/6  Pipeline overview"
say "Dashboard → 'Pipeline' tab: architecture, Kafka topic sizes, HDFS datasets, data quality, MLlib model." \
    "" "The stack keeps running. Stop with:  ./scripts/stream.sh stop && ./scripts/stop.sh"
pause
