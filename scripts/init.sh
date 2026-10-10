#!/usr/bin/env bash
# Create Kafka topics and the HDFS data-lake layout. Safe to run repeatedly.
set -euo pipefail

KAFKA_TOPICS="docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092"

create_topic() {  # name partitions
  $KAFKA_TOPICS --create --if-not-exists --topic "$1" --partitions "$2" --replication-factor 1 > /dev/null
  echo "  topic  $1 ($2 partitions)"
}

echo "Kafka topics:"
create_topic nepse.ticks     3   # raw ticks (live / replay), keyed by symbol
create_topic nepse.alerts    1   # spike / jump / circuit alerts from Spark
create_topic nepse.analytics 1   # latest computed market snapshot

# nepse.analytics is a "latest state per symbol" topic → log compaction keeps only the newest
# message per key, so the dashboard reads ~1 message per symbol instead of the whole history
docker exec kafka /opt/kafka/bin/kafka-configs.sh --bootstrap-server localhost:9092 --alter \
  --entity-type topics --entity-name nepse.analytics \
  --add-config cleanup.policy=compact,segment.ms=60000,min.cleanable.dirty.ratio=0.01,delete.retention.ms=60000 > /dev/null
echo "  topic  nepse.analytics → log-compacted (latest message per symbol)"

echo "HDFS data lake:"
for dir in /nepse/bronze /nepse/silver /nepse/gold /nepse/checkpoints; do
  docker exec namenode hdfs dfs -mkdir -p "$dir"
  echo "  dir    hdfs://$dir"
done
