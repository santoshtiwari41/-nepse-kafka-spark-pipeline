# NEPSE Real-Time & Historical Stock Analytics (Big Data Project)

A big data pipeline for the Nepal Stock Exchange (NEPSE) built with **Apache Kafka** (ingestion) and
**Apache Spark** (stream + batch processing), storing data in an **HDFS** data lake (Parquet) and
serving it on a **Streamlit** dashboard. It works with the **live market** (NEPSE API), a **replay** of
any past trading day (when the market is closed), and **31 years of history** (1995 → today).
Design and rationale: [plan.md](plan.md).

```
NEPSE API / ShareSansar ──LIVE──┐
Recordings / history CSV ─REPLAY┴─▶ Kafka nepse.ticks ─▶ Spark Structured Streaming ─▶ Kafka nepse.analytics / alerts ─┐
History CSV ──bulk load──▶ HDFS bronze ─▶ Spark batch (SQL, MLlib) ─▶ HDFS silver / gold ◀── stream outputs ─────────────┤
                                               (reference data → stream-static join)                                    ▼
                                                                                                          Streamlit dashboard
```

## Requirements
- Linux/macOS with Docker + Docker Compose v2 (Windows: WSL2)
- 8 GB RAM or more (the stack uses ~2–3 GB while streaming), ~6 GB disk for images
- Python 3.10+ on the host (data collection and producers)
- Internet **only for the first-time setup** — the demo itself runs fully offline

## First-time setup (once, online)

```bash
git clone <repo> nepse && cd nepse
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

./scripts/start.sh            # pulls/builds images (~10 min first time), starts everything
./scripts/verify.sh           # health check + Spark ↔ Kafka ↔ HDFS smoke test → "SMOKE TEST PASSED"

# full history (optional — without it everything uses the committed 42-stock sample)
.venv/bin/python ingestion/fetch_companies.py
.venv/bin/python ingestion/fetch_history.py

./scripts/run_batch.sh        # history → HDFS bronze/silver/gold + MLlib model (~5 min)
```

On every trading day before the demo, record the live session (market ~11:00–15:00 NPT):

```bash
.venv/bin/python ingestion/live_producer.py --no-kafka     # → data/recordings/<date>.jsonl
```

## Demo day

```bash
./scripts/demo.sh             # guided, step by step (Enter between steps)
./scripts/demo.sh --replay --speed 10    # force REPLAY, slower → more intraday candles
```

The script starts the stack, shows the batch results (Spark SQL), starts Spark Streaming, streams
**LIVE** if NEPSE is open or otherwise **REPLAYs** the latest trading day, demonstrates fault tolerance
(kills and restarts the stream) and points to each dashboard tab. Everything works without internet:
images are already built, Spark's Kafka connector is baked into the image, the dashboard loads no
external resources, and replay uses local data.

Manual equivalent:

```bash
./scripts/start.sh
./scripts/stream.sh start
.venv/bin/python ingestion/replay_producer.py --loop      # or live_producer.py when the market is open
# open http://localhost:8501
```

## Services

| Service | URL / Address | Purpose |
|---------|---------------|---------|
| Kafka UI | http://localhost:8085 | Browse topics and messages |
| HDFS NameNode | http://localhost:9870 | Browse the data lake (Utilities → Browse) |
| Spark Master | http://localhost:8080 | Cluster and running applications |
| Spark Worker | http://localhost:8081 | Executor details |
| Spark job UI | http://localhost:4040 | Visible while a job is running |
| **Dashboard** | http://localhost:8501 | Streamlit app (live + historical analytics) |
| Kafka (host) | `localhost:9094` | Bootstrap server for producers on the host |
| Kafka (containers) | `kafka:9092` | Bootstrap server inside Docker network |

## Kafka topics

| Topic | Partitions | Content |
|-------|-----------|---------|
| `nepse.ticks` | 3 | Raw price ticks (LIVE or REPLAY), keyed by symbol |
| `nepse.alerts` | 1 | Volume spike / price jump / circuit alerts |
| `nepse.analytics` | 1 | Latest state per symbol from Spark (log-compacted) |

## HDFS layout

```
/nepse/bronze        raw data as received
/nepse/silver        cleaned, deduplicated, bonus-adjusted (partitioned by year)
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
./scripts/run_batch.sh                 # load → clean → indicators → MLlib → SQL showcase (~5 min, full history)
./scripts/run_batch.sh --source sample # same, from the offline sample (faster)
./scripts/spark_submit.sh batch_queries.py --only oversold   # one Spark SQL query
```

| Job | Reads | Writes |
|-----|-------|--------|
| `batch_load_history.py` | CSVs in `data/` | `bronze/{prices,index,companies}` (raw + lineage), `silver/{prices,index,companies}`, `gold/data_quality` |
| `batch_indicators.py` | silver | `gold/indicators` (per symbol/day), `latest_snapshot`, `volume_baseline`, `sector_daily`, `market_daily` |
| `ml_predict.py` | gold/indicators | `gold/ml_metrics`, `ml_features`, `ml_predictions` (random forest: up/down next day) |
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
| `candles_1m` | HDFS `gold/candles_1m` | 1-min event-time windows, 10 s watermark: OHLC, volume, VWAP, trades |
| `sector_flow` | HDFS `gold/sector_flow_1m` | turnover/volume/trades per sector per minute (equities) |
| `live_snapshot` | Kafka `nepse.analytics` | latest state per symbol per session (stateful aggregation, update mode) |
| `alerts` | Kafka `nepse.alerts` + HDFS `gold/alerts` | UPPER/LOWER_CIRCUIT (±9.5 %), VOLUME_SPIKE (≥ 3× 20-day avg), BIG_MOVE (≥ 5 % from open); de-duplicated per symbol/type/session within the watermark |

Ticks are joined (stream-static) with `silver/companies` (sector) and `gold/volume_baseline`
(normal volume) from the batch layer — restart the stream after re-running the batch layer to
pick up new reference data.

Notes
- A 1-minute candle is written once the watermark (10 s) passes its end, i.e. when newer ticks
  arrive — about 10–20 s after the minute closes.
- Each Spark app may use at most 2 of the worker's 4 cores (`spark.cores.max`), so the
  stream and a batch job can run at the same time.
- Fault tolerance: stopping the stream mid-session and starting it again loses and duplicates
  nothing (checkpointed Kafka offsets + exactly-once file sink). Alerts use `foreachBatch` → at-least-once.

## Dashboard (Streamlit)

http://localhost:8501 — starts with `./scripts/start.sh` (container `dashboard`, code in `dashboard/`,
hot-reloads on save).

| Tab | Shows | Source |
|-----|-------|--------|
| Live market | mode badge, KPIs, top gainers/losers/most active, sector treemap, alerts feed, 1-min intraday candles | Kafka `nepse.analytics` + `nepse.alerts`, HDFS `gold/candles_1m` |
| Stock explorer | candlesticks (bonus-adjusted) + SMA 20/50/200 + Bollinger band, volume, RSI; corporate actions | HDFS `gold/indicators`, `latest_snapshot` |
| Market & sectors | NEPSE index + SMAs, yearly returns, sector turnover and average return | HDFS `gold/market_daily`, `sector_daily` |
| Screener | filter all securities by sector / trend / RSI signal / volume spike | HDFS `gold/latest_snapshot` |
| Pipeline | architecture diagram, Kafka topic sizes, HDFS dataset sizes, data-quality report, MLlib results | Kafka + WebHDFS |

**Mode badge:** `LIVE` / `REPLAY` while the stream has produced output in the last 90 s (REPLAY also
names the trading day being replayed); otherwise `HISTORICAL`, and the Live tab shows the last trading
day from the batch layer. Every replay loop is a new *session* (`session_start` field on each tick), so
the live view and alerts never mix two loops.

**Tip for the demo:** at `--speed 60` one 1-minute candle = one market hour (4 candles per session);
use `--speed 10` (24-minute session) when showing intraday candles.

`nepse.analytics` is **log-compacted** (`scripts/init.sh`): Kafka keeps only the newest message per
symbol, so the dashboard loads the current market state in ~1 s however long the stream has run.

## MLlib model (bonus)

`ml_predict.py` trains a random forest on 10 technical features (returns, RSI, distance from
SMAs, Bollinger position, volume ratio, volatility) to predict whether a stock closes higher the next
day. Time-based split: trained on 2015–2024, tested on 2025 onward (no look-ahead).

| Metric | Value |
|--------|-------|
| Test accuracy | 55.8 % (baseline "always guess the majority": 55.9 %) |
| AUC | 0.519 |
| Accuracy of confident calls (p ≥ 0.6 or ≤ 0.4, ~1 % of days) | 64 % |

Daily moves are mostly noise, so overall the model is no better than the baseline — an honest
result worth discussing; the confident calls show a weak signal. Shown for demonstration, not advice.

## Running a Spark job

Jobs live in `spark/jobs/` (mounted at `/opt/spark-apps`); `data/` is mounted at `/opt/data`.

```bash
docker exec spark-master /opt/spark/bin/spark-submit /opt/spark-apps/<job>.py
```

## Project layout

```
docker-compose.yml      all services (Kafka, Kafka UI, HDFS, Spark, dashboard)
config/hadoop.env       HDFS configuration
ingestion/              host-side Python: fetch_*.py (data collection), live_producer.py, replay_producer.py
spark/Dockerfile        Spark image with the Kafka connector baked in (works offline)
spark/conf/             spark-defaults.conf, log4j2.properties
spark/jobs/             PySpark jobs: batch_*.py, ml_predict.py, stream_processor.py, stream_report.py
dashboard/              Streamlit app (app.py = UI, data.py = Kafka + WebHDFS access)
scripts/                start / stop / init / verify / run_batch / stream / spark_submit / demo
data/                   sample (in git), reference (in git), historical + recordings (downloaded/recorded)
plan.md                 design document: problem, sources, features, architecture
```

## Report

The project report (problem, data sources, features, storage design, component choice, block
diagram, implementation, results, demo plan) in two identical forms:

- `report/NEPSE_BigData_Project_Report.docx` — Word document (27 pages)
- `report/NEPSE_BigData_Project_Report.html` — single self-contained page (open in any browser; sidebar
  navigation, click a figure to enlarge, prints like the Word version)

Both are generated from the same content in `report/build.js`; only the teacher's name and the
submission date are left as yellow placeholders. Regenerate both after editing:
`cd report && npm install docx@9.5.1 && node build.js`.

## Troubleshooting
- **Port already in use:** change the left side of the port mapping in `docker-compose.yml`.
- **NameNode stuck in safe mode:** `docker exec namenode hdfs dfsadmin -safemode leave`.
- **Service unhealthy:** `docker logs <container>`.
- **Edited `spark/conf/*` or `config/hadoop.env`:** restart the containers (`docker compose restart spark-master spark-worker`) — single-file mounts don't pick up edits made by tools that replace the file.
- **Dashboard shows HISTORICAL while replaying:** the stream isn't running (`./scripts/stream.sh status`) or hasn't produced output in 90 s.
- **Replay shows nothing new / alerts missing after code changes:** `./scripts/stream.sh stop && ./scripts/stream.sh reset && ./scripts/stream.sh start`.
- **Changed a Dockerfile or requirements:** `docker compose build` (needs internet), then `./scripts/start.sh`.
- **Start from scratch:** `./scripts/stop.sh --clean && ./scripts/start.sh`.
