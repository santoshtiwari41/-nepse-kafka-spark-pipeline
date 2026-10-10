#!/usr/bin/env bash
# Start the whole stack, wait until it is healthy, then create topics/HDFS dirs.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Starting containers..."
# No --build: images are built once (online) and reused, so this also works offline on demo day.
# Compose still builds an image that doesn't exist yet. After editing a Dockerfile: docker compose build
docker compose up -d

wait_healthy() {  # container timeout_seconds
  local status
  for _ in $(seq "$2"); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null || echo missing)
    [ "$status" = healthy ] && { echo "  $1 healthy"; return 0; }
    sleep 1
  done
  echo "  $1 NOT healthy after $2s (status: $status) — check: docker logs $1" >&2
  return 1
}

echo "Waiting for services..."
wait_healthy kafka 120
wait_healthy namenode 120

# NameNode stays in safe mode until the DataNode reports in
docker exec namenode hdfs dfsadmin -safemode wait > /dev/null
echo "  hdfs out of safe mode"

./scripts/init.sh

cat <<EOF

NEPSE platform is up:
  Kafka UI         http://localhost:8085
  HDFS NameNode    http://localhost:9870
  Spark Master     http://localhost:8080
  Spark Worker     http://localhost:8081
  Kafka (host)     localhost:9094
EOF
