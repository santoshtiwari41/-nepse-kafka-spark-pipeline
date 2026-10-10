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

### Replay producer (REPLAY mode — works when the market is closed)

```bash
.venv/bin/python ingestion/replay_producer.py --list                      # what can be replayed
.venv/bin/python ingestion/replay_producer.py                             # latest trading day, 60x (4 h → 4 min)
.venv/bin/python ingestion/replay_producer.py --date 2026-10-09 --speed 120 --loop
.venv/bin/python ingestion/replay_producer.py --source recording          # latest recorded live session
.venv/bin/python ingestion/replay_producer.py --symbols NABIL --dry-run   # print instead of sending
```

- `--source historical` (default) simulates intraday trades from each stock's daily OHLCV: the
  price path starts at the open, touches the day's high and low, and ends exactly at the close,
  with the day's volume split across trades (seeded → the same day always replays identically).
- `--source recording` replays real ticks captured by `live_producer.py`.
- Timestamps are shifted to *now* and compressed by `--speed`, so Spark sees a fresh, live-looking
  stream every time; use `--keep-time` to keep the original timestamps.
- Uses `data/historical/` if downloaded, otherwise falls back to the committed `data/sample/`.

## Batch layer (Spark)

```bash
./scripts/run_batch.sh                 # load → clean → indicators → SQL showcase (~3.5 min, full history)
./scripts/run_batch.sh --source sample # same, from the offline sample (faster)
./scripts/spark_submit.sh batch_queries.py --only oversold   # one Spark SQL query
```

| Job | Reads | Writes |
|-----|-------|--------|
| `batch_load_history.py` | CSVs in `data/` | `bronze/{prices,index,companies}` (raw + lineage), `silver/{prices,index,companies}`, `gold/data_quality` |
| `batch_indicators.py` | silver | `gold/indicators` (per symbol/day), `latest_snapshot`, `volume_baseline`, `sector_daily`, `market_daily` |
| `batch_queries.py` | silver + gold | prints answers: top gainers, sector money flow, oversold, golden crosses, volume spikes, volatility, NEPSE yearly returns, bonus-share adjustments |

**Cleaning rules (silver):** drop rows with non-positive prices or zero volume; drop duplicate
(symbol, date); widen high/low to include open/close; flag an opening gap below −10.5 %
(beyond NEPSE's ±10 % circuit) as a bonus/right-share adjustment and back-adjust earlier prices
into `adj_*` columns, so indicators don't see fake crashes. Sector/market statistics use
ordinary shares only (no debentures, mutual funds).

**Indicators (gold):** SMA 20/50/200, RSI 14, Bollinger bands (20, 2σ), 20-day annualised
volatility, 52-week high/low, 1w/1m/3m/1y returns, volume ratio vs prior 20-day average,
golden/death cross, trend (UPTREND/DOWNTREND/SIDEWAYS), RSI signal (OVERSOLD/OVERBOUGHT).

## Speed layer (Spark Structured Streaming)

```bash
./scripts/stream.sh start      # start the streaming job in the background (resumes from checkpoint)
./scripts/stream.sh status     # running? → Spark UI http://localhost:4040/StreamingQuery/
./scripts/stream.sh logs       # follow the log (alerts per micro-batch)
./scripts/stream.sh stop       # graceful stop
./scripts/stream.sh reset      # forget checkpoints + streaming outputs (batch data kept)

# feed it:  .venv/bin/python ingestion/replay_producer.py --loop     (or live_producer.py)
./scripts/spark_submit.sh stream_report.py --symbol NABIL   # what the stream has written to HDFS
```

| Query | Output | How |
|-------|--------|-----|
| `ticks` | HDFS `bronze/ticks` | raw ticks, exactly-once file sink, partitioned by trade_date |
| `candles_1m` | HDFS `gold/candles_1m` | 1-min event-time windows, 1-min watermark: OHLC, volume, VWAP, trades |
| `sector_flow` | HDFS `gold/sector_flow_1m` | turnover/volume/trades per sector per minute (equities) |
| `live_snapshot` | Kafka `nepse.analytics` | latest state per symbol per day (stateful aggregation, update mode) |
| `alerts` | Kafka `nepse.alerts` + HDFS `gold/alerts` | UPPER/LOWER_CIRCUIT (±9.5 %), VOLUME_SPIKE (≥ 3× 20-day avg), BIG_MOVE (≥ 5 % from open); de-duplicated per symbol/type within the watermark |

Ticks are joined (stream-static) with `silver/companies` (sector) and `gold/volume_baseline`
(normal volume) from the batch layer — restart the stream after re-running the batch layer to
pick up new reference data.

Notes
- A 1-minute candle is written once the watermark passes its end, i.e. when newer ticks
  arrive — so the last minute of a replay appears when the next replay (`--loop`) starts.
- Each Spark app may use at most 2 of the worker's 4 cores (`spark.cores.max`), so the
  stream and a batch job can run at the same time.
- Fault tolerance: stopping the stream mid-session and starting it again loses and duplicates
  nothing (checkpointed Kafka offsets + exactly-once file sink). Alerts use `foreachBatch` → at-least-once.

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
- **Edited `spark/conf/*` or `config/hadoop.env`:** restart the containers (`docker compose restart spark-master spark-worker`) — single-file mounts don't pick up edits made by tools that replace the file.
- **Start from scratch:** `./scripts/stop.sh --clean && ./scripts/start.sh`.
