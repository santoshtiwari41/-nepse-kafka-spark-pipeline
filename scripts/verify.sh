#!/usr/bin/env bash
# Phase 0 verification: every component is up and Spark ↔ Kafka ↔ HDFS works.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Containers =="
docker compose ps --format 'table {{.Name}}\t{{.Status}}'

echo; echo "== Kafka topics =="
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

echo; echo "== HDFS report =="
docker exec namenode hdfs dfsadmin -report 2>/dev/null | grep -E 'Live datanodes|Configured Capacity|DFS Remaining' | head -3
docker exec namenode hdfs dfs -ls /nepse

echo; echo "== Spark workers =="
curl -s http://localhost:8080/json/ | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"  alive workers: {d['aliveworkers']}, cores: {d['cores']}, memory: {d['memory']} MB\")"

echo; echo "== Spark ↔ Kafka ↔ HDFS smoke test =="
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists --topic nepse.smoke --partitions 1 --replication-factor 1 > /dev/null
trap 'docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic nepse.smoke > /dev/null 2>&1 || true;
      docker exec namenode hdfs dfs -rm -r -f -skipTrash /nepse/_smoke > /dev/null 2>&1 || true' EXIT

docker exec spark-master /opt/spark/bin/spark-submit /opt/spark-apps/smoke_test.py 2>&1 \
  | grep -vE '^\s*$|WARN NativeCodeLoader|Using Spark'\''s default log4j'
