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

## Data collection (host side)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python ingestion/fetch_companies.py   # 649 companies + sector → data/reference/
.venv/bin/python ingestion/fetch_history.py     # ~370 companies + NEPSE index → data/historical/
.venv/bin/python ingestion/build_sample.py      # small offline dataset → data/sample/ (committed)
```

| Folder | Content | In git? |
|--------|---------|---------|
| `data/reference/` | `companies.csv` (symbol, name, sector, instrument type) | yes |
| `data/sample/` | 42 symbols (top 3 per sector + blue chips) since 2019, NEPSE index, companies — **offline backup** | yes |
| `data/historical/` | full history: `prices/<SYMBOL>.csv`, `index/NEPSE.csv` (~33 MB) | no (re-download) |
| `data/recordings/` | recorded live sessions `<date>.jsonl` | no |

All price CSVs share the columns `date,symbol,open,high,low,close,volume,turnover,change_pct`.

### Live producer (LIVE mode)

```bash
.venv/bin/python ingestion/live_producer.py              # waits for market open, streams to nepse.ticks
.venv/bin/python ingestion/live_producer.py --no-kafka   # just record the session to data/recordings/
.venv/bin/python ingestion/live_producer.py --once --force   # single poll even when closed (testing)
```

Each Kafka message on `nepse.ticks` (key = symbol):

```json
{"symbol": "NABIL", "ts": "2026-10-09T14:59:59+05:45", "ltp": 536.2, "open": 532.0,
 "high": 538.0, "low": 531.0, "prev_close": 533.0, "volume": 48779, "turnover": 26163739.6,
 "last_qty": 10, "change_pct": 0.6, "source": "nepse-api", "mode": "LIVE"}
```

**Record sessions before the demo:** run the live producer on as many trading days as possible
(market ~11:00–15:00 NPT). These recordings make REPLAY mode look exactly like a live market.

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
