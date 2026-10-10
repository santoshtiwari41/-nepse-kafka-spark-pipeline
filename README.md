# NEPSE Real-Time & Historical Stock Analytics (Big Data Project)

Kafka + Spark + HDFS pipeline for Nepal Stock Exchange data. See [plan.md](plan.md) for the full design.

## Requirements
- Docker + Docker Compose v2
- ~4 GB free RAM (stack uses ~1.7 GB idle), 8 GB+ total recommended
- Python 3.10+ on the host (for producers, later phases)

## Quick start

```bash
./scripts/start.sh     # build + start everything, create Kafka topics & HDFS dirs
./scripts/verify.sh    # health check + Spark ↔ Kafka ↔ HDFS smoke test
./scripts/stop.sh      # stop (data kept);  ./scripts/stop.sh --clean wipes all data
```

## Services

| Service | URL / Address | Purpose |
|---------|---------------|---------|
| Kafka UI | http://localhost:8085 | Browse topics and messages |
| HDFS NameNode | http://localhost:9870 | Browse the data lake (Utilities → Browse) |
| Spark Master | http://localhost:8080 | Cluster and running applications |
| Spark Worker | http://localhost:8081 | Executor details |
| Spark job UI | http://localhost:4040 | Visible while a job is running |
| Kafka (host) | `localhost:9094` | Bootstrap server for producers on the host |
| Kafka (containers) | `kafka:9092` | Bootstrap server inside Docker network |

## Kafka topics

| Topic | Partitions | Content |
|-------|-----------|---------|
| `nepse.ticks` | 3 | Raw price ticks (LIVE or REPLAY), keyed by symbol |
| `nepse.alerts` | 1 | Volume spike / price jump / circuit alerts |
| `nepse.analytics` | 1 | Latest computed market snapshot |

## HDFS layout

```
/nepse/bronze        raw data as received
/nepse/silver        cleaned, deduplicated, partitioned by date
/nepse/gold          indicators, candles, sector stats, alerts
/nepse/checkpoints   Spark streaming checkpoints
```

## Running a Spark job

Jobs live in `spark/jobs/` (mounted at `/opt/spark-apps`); `data/` is mounted at `/opt/data`.

```bash
docker exec spark-master /opt/spark/bin/spark-submit /opt/spark-apps/<job>.py
```

## Project layout

```
docker-compose.yml     all services
config/hadoop.env      HDFS configuration
spark/Dockerfile       Spark image with Kafka connector baked in (works offline)
spark/conf/            spark-defaults.conf, log4j2.properties
spark/jobs/            PySpark jobs
scripts/               start / stop / init / verify
data/                  sample, historical, recordings (host side)
```

## Troubleshooting
- **Port already in use:** change the left side of the port mapping in `docker-compose.yml`.
- **NameNode stuck in safe mode:** `docker exec namenode hdfs dfsadmin -safemode leave`.
- **Service unhealthy:** `docker logs <container>`.
- **Start from scratch:** `./scripts/stop.sh --clean && ./scripts/start.sh`.
