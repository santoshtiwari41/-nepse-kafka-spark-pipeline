# NEPSE Real-Time and Historical Stock Analytics Platform — Project Plan

> **Course assignment:** solve a real-world problem with a big data stack, using two big data tools, working as a group of two.
> **Primary tools:** **Apache Kafka** (ingestion and streaming) and **Apache Spark** (stream and batch processing).
> **Storage:** **HDFS** data lake (Parquet). Everything runs with Docker Compose.

---

## 1. Problem Statement

Retail investors in Nepal follow NEPSE through scattered websites (nepalstock.com, ShareSansar, MeroLagani).
These sites show **current prices**, but none of them combine the following in one place:

- **real-time monitoring** of ~250+ listed companies (live price, volume, turnover),
- **automatic detection of unusual activity**: volume spikes, sudden price jumps, ±10% circuit hits,
- **historical context**: how today's movement compares with years of past data (moving averages, RSI, sector trends).

NEPSE data is **high velocity** during trading hours (many updates per symbol per minute) and **high volume** over time (10+ years × 250+ symbols × daily and intraday records).
A single traditional database and script do not scale for ingestion, stream processing and historical analytics together. That makes this a big data problem.

**Goal:** build a pipeline that ingests NEPSE data (live **or** historical replay), processes it in real time and in batch, stores it in a data lake, and shows insights and alerts on a dashboard.

---

## 2. Key Design Decision: The Demo Must Not Depend on Market Hours

NEPSE trades only **Sunday–Thursday, 11:00–15:00 NPT**, and closes on public holidays.
The demo day may fall outside those hours, so the system supports **three data modes**. All three feed the **same Kafka topic**, which means the Spark jobs and the dashboard behave identically in every mode.

| Mode | When to use | Source | How it works |
|------|-------------|--------|--------------|
| **LIVE** | Market is open | NEPSE live API / ShareSansar live page | Polls every 5–10 s and publishes ticks to Kafka |
| **REPLAY** | Market closed (most likely on demo day) | Recorded live sessions **or** historical daily data | Re-publishes stored data to Kafka with original timing or speed-up (e.g. 1 trading day in 2 minutes) |
| **HISTORICAL (batch)** | Any time | 10+ years of historical CSVs in HDFS | Spark batch jobs compute indicators and trends over the full history |

**Demo strategy:** show **REPLAY** (looks exactly like live streaming) and **HISTORICAL** analytics, plus LIVE if the market happens to be open.
The dashboard displays a badge showing the current mode (`LIVE` / `REPLAY` / `HISTORICAL`) so the setup is clear to the examiner.

---

## 3. Data Sources

| # | Data | Source | Type | Format |
|---|------|--------|------|--------|
| 1 | Live market (LTP, volume, change %) | nepalstock.com through the `NepseUnofficialApi` Python library; fallback: ShareSansar/MeroLagani live trading page scraper | Real-time | JSON / HTML |
| 2 | Historical daily OHLCV (2010 to present) | ShareSansar / NepseAlpha price history; Kaggle "NEPSE stock data" datasets | Batch | CSV |
| 3 | NEPSE index history | ShareSansar / NepseAlpha index history | Batch | CSV |
| 4 | Company master (symbol, name, sector, listed shares) | nepalstock.com company list | Reference | JSON / CSV |
| 5 | Recorded live sessions | Our own LIVE-mode recorder (saved while the market is open) | Replay | JSONL |

**Backup:** a curated sample dataset is committed in `data/sample/` so the demo works **fully offline**, even with no internet and a closed market.

---

## 4. Important Features

### 4.1 Data features (raw)
`symbol`, `company_name`, `sector`, `timestamp`, `open`, `high`, `low`, `close/ltp`, `prev_close`, `volume`, `turnover`, `no_of_trades`, `change`, `change_pct`

### 4.2 Analytical features (derived)
| Feature | Computed in | Purpose |
|---------|-------------|---------|
| Windowed OHLC (1-min / 5-min candles) | Spark Streaming | Live candlestick chart |
| VWAP (volume-weighted average price) | Spark Streaming | Fair-price reference |
| Top gainers / losers / most active | Spark Streaming | Market overview |
| Sector-wise turnover | Streaming and batch | Where money is flowing |
| **Volume spike alert** (volume > 3× 20-day average) | Streaming, using the batch average as reference | Unusual activity detection |
| **Price jump alert** (move > ±5% within a window) | Spark Streaming | Sudden movement detection |
| **Circuit alert** (±10% from previous close) | Spark Streaming | Circuit breaker hits |
| SMA 20/50, EMA, RSI(14), 52-week high/low | Spark Batch | Technical analysis on history |
| Daily returns, volatility, correlation | Spark Batch | Risk analysis |
| *(Bonus)* next-day trend prediction | Spark MLlib | Simple ML demo |

### 4.3 System design features
- **Scalability:** Kafka partitions by symbol, and Spark processes partitions in parallel.
- **Fault tolerance:** Kafka keeps messages for replay; Spark checkpointing gives exactly-once processing to the file sink.
- **Low latency:** alerts within seconds of a tick arriving.
- **Lambda-style architecture:** a speed layer (streaming) and a batch layer (history) share the same storage.
- **Data quality:** deduplication by (symbol, timestamp), null and outlier filtering, holiday/weekend awareness.
- **Partitioned storage:** Parquet partitioned by `date` (and `sector`) for fast queries.
- **Source independence:** the three data modes produce one schema on one topic.

---

## 5. Architecture

```
            DATA SOURCES                         INGESTION (Tool 1)
 ┌──────────────────────────────┐
 │ NEPSE Live API / ShareSansar │──LIVE──┐
 └──────────────────────────────┘        │      ┌───────────────────────────────┐
 ┌──────────────────────────────┐        ├────▶ │        APACHE KAFKA           │
 │ Recorded sessions (JSONL)    │─REPLAY─┤      │  topic: nepse.ticks  (raw)    │
 │ Historical daily CSV         │────────┘      │  topic: nepse.alerts          │
 └──────────────┬───────────────┘               │  topic: nepse.analytics       │
                │ bulk load                     └───────────────┬───────────────┘
                │                                               │
                ▼                    PROCESSING (Tool 2)        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                              APACHE SPARK                                   │
 │  ┌─────────────────────────────────┐   ┌─────────────────────────────────┐  │
 │  │  SPEED LAYER                    │   │  BATCH LAYER                    │  │
 │  │  Spark Structured Streaming     │   │  Spark SQL / DataFrames         │  │
 │  │  • parse + validate ticks       │   │  • clean historical CSVs        │  │
 │  │  • 1-min/5-min OHLC windows     │   │  • SMA / EMA / RSI / 52W H-L    │  │
 │  │  • VWAP, gainers/losers         │   │  • sector trends, volatility    │  │
 │  │  • spike / jump / circuit alerts│   │  • 20-day avg volume (ref for   │  │
 │  │                                 │◀──│    spike alerts)                │  │
 │  └───────────────┬─────────────────┘   │  • (bonus) MLlib prediction     │  │
 │                  │                     └────────────────┬────────────────┘  │
 └──────────────────┼──────────────────────────────────────┼───────────────────┘
                    ▼                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                       STORAGE — HDFS DATA LAKE (Parquet)                    │
 │   /nepse/bronze/   raw ticks + raw historical CSV (as received)             │
 │   /nepse/silver/   cleaned, deduplicated, typed  (partitioned by date)      │
 │   /nepse/gold/     indicators, candles, sector stats, alerts                │
 └─────────────────────────────────────┬───────────────────────────────────────┘
                                       ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │               DASHBOARD — Streamlit  (mode badge: LIVE/REPLAY/HISTORICAL)   │
 │   Live ticker · Gainers/Losers · Alerts feed · Candlestick + SMA/RSI ·      │
 │   Sector heatmap · Historical explorer (any symbol, any date range)         │
 └─────────────────────────────────────────────────────────────────────────────┘
```

### Why these components?
| Component | Role | Why this one and not an alternative |
|-----------|------|-------------------------------------|
| **Kafka** | Ingestion buffer | Separates producers from consumers, absorbs bursts, **keeps data so it can be replayed**, and lets live and replay sources share one topic |
| **Spark** | Processing | One engine for **both** streaming and batch (same DataFrame API), with SQL, windowing and MLlib built in |
| **HDFS + Parquet** | Storage | Distributed and fault-tolerant (replication); Parquet is column-based and compressed, which suits analytics scans; date partitions keep queries fast |
| Streamlit | Visualization | Quick to build, Python, live auto-refresh |

*(The report also compares alternatives: Flume vs Kafka, Flink vs Spark, Cassandra/HBase vs HDFS.)*

---

## 6. Tech Stack

| Layer | Technology |
|-------|-----------|
| Containers | Docker + Docker Compose |
| Ingestion | Apache Kafka (KRaft mode, no Zookeeper), Python `kafka-python`/`confluent-kafka` producers |
| Processing | Apache Spark 3.5 (PySpark): Structured Streaming + Spark SQL (+ MLlib bonus) |
| Storage | Hadoop HDFS (NameNode + DataNode), Parquet |
| Data collection | Python: `requests`, `BeautifulSoup`, `NepseUnofficialApi`, `pandas` |
| Dashboard | Streamlit + Plotly |
| Monitoring (optional) | Kafka UI (topic and message viewer, useful in the demo), Spark UI, HDFS NameNode UI |

---

## 7. Project Structure (planned)

```
project-demo/
├── plan.md                      ← this file
├── README.md                    ← setup and run guide (submitted after demo)
├── docker-compose.yml           ← Kafka, Kafka-UI, HDFS, Spark master/worker, dashboard
├── .env                         ← mode, speed, poll interval, etc.
├── data/
│   ├── sample/                  ← offline backup dataset (historical + 1 recorded day)
│   ├── historical/              ← downloaded historical CSVs
│   └── recordings/              ← recorded live sessions (JSONL)
├── ingestion/
│   ├── live_producer.py         ← LIVE mode: poll NEPSE → Kafka (+ save recording)
│   ├── replay_producer.py       ← REPLAY mode: recorded/historical → Kafka at N× speed
│   ├── fetch_history.py         ← download historical OHLCV + company list
│   └── schema.py                ← shared tick schema
├── spark/
│   ├── stream_processor.py      ← Structured Streaming: candles, VWAP, alerts → HDFS + Kafka
│   ├── batch_load_history.py    ← CSV → HDFS bronze/silver
│   ├── batch_indicators.py      ← SMA/EMA/RSI/52W/sector stats → gold
│   └── ml_predict.py            ← (bonus) MLlib trend prediction
├── dashboard/
│   └── app.py                   ← Streamlit app
├── scripts/
│   ├── start.sh / stop.sh       ← one-command start/stop
│   └── demo.sh                  ← runs the full demo sequence
└── report/
    ├── report.md                ← final report (→ PDF/DOCX)
    └── diagrams/                ← block diagram images
```

---

## 8. Implementation Phases

### Phase 0 — Environment (Day 1–2)
- [ ] Docker Compose: Kafka (KRaft), Kafka-UI, HDFS NameNode + DataNode, Spark master + worker
- [ ] Verify: create topic, write a test file to HDFS, run a test Spark job
- [ ] `start.sh` / `stop.sh`

### Phase 1 — Data Collection (Day 2–4)
- [ ] `fetch_history.py`: download historical OHLCV for all or selected symbols (plus NEPSE index and company list)
- [ ] Build `data/sample/` offline backup (e.g. top 30 symbols × 5 years, plus 1 recorded day)
- [ ] `live_producer.py`: test with the NEPSE API, fall back to the ShareSansar scraper
- [ ] **Record 3–5 real live trading sessions during market hours** (needed for a realistic replay)

### Phase 2 — Kafka Ingestion (Day 4–5)
- [ ] Topics: `nepse.ticks` (partitioned by symbol), `nepse.alerts`, `nepse.analytics`
- [ ] `replay_producer.py` with `--source recording|historical --date --speed 60x`
- [ ] Verify messages in Kafka-UI

### Phase 3 — Spark Batch Layer (Day 5–8)
- [ ] `batch_load_history.py`: CSV → HDFS bronze → cleaned silver (partitioned by date)
- [ ] `batch_indicators.py`: SMA20/50, EMA, RSI14, 52W high/low, volatility, sector aggregates, 20-day avg volume → gold
- [ ] Verify with Spark SQL queries

### Phase 4 — Spark Streaming Layer (Day 8–11)
- [ ] `stream_processor.py`: read Kafka, parse, apply watermark, 1-min/5-min windows
- [ ] VWAP, top gainers/losers, sector turnover
- [ ] Alerts: volume spike (join with batch 20-day avg), price jump, circuit hit → `nepse.alerts` + HDFS
- [ ] Checkpointing, and a test of restart recovery

### Phase 5 — Dashboard (Day 11–13)
- [ ] Mode badge, live ticker, gainers/losers, alerts feed (auto-refresh)
- [ ] Candlestick chart with SMA overlay + RSI panel (historical)
- [ ] Sector heatmap, historical explorer (symbol + date range)

### Phase 6 — Bonus and Polish (Day 13–15)
- [ ] (Bonus) MLlib next-day up/down prediction with accuracy shown
- [ ] `demo.sh` sequence, README with setup guide
- [ ] Rehearse the demo **fully offline** (Wi-Fi off) at least twice

### Phase 7 — Report (parallel, finalize after demo)
- [ ] Problem definition, sources, features (part **a**)
- [ ] Storage design, component choice and comparison, detailed block diagram (part **b**)
- [ ] Screenshots, results, limitations, future work
- [ ] Code + implementation guidelines (submitted after the demo, as instructed)

---

## 9. Work Split (2 Students)

| Student A — Ingestion and Storage | Student B — Processing and Visualization |
|-----------------------------------|------------------------------------------|
| Docker Compose setup (Kafka, HDFS) | Spark cluster config |
| `fetch_history.py`, data cleaning | `batch_indicators.py` (technical indicators) |
| `live_producer.py` + recording sessions | `stream_processor.py` (windows, alerts) |
| `replay_producer.py` | Streamlit dashboard |
| HDFS layout (bronze/silver/gold) | (Bonus) MLlib prediction |
| Report: part (a), data sources | Report: part (b), architecture and diagram |

Both: integration testing, demo rehearsal, final report review.

---

## 10. Demo Day Script (~10–12 minutes)

1. **Problem and architecture** (2 min): show the block diagram.
2. **Start the stack** (1 min): `./scripts/start.sh`; show the Kafka-UI, HDFS UI and Spark UI running.
3. **Historical (batch) analytics** (3 min):
   - Run `batch_indicators.py` live and show the Spark job in the Spark UI.
   - Show Parquet files partitioned by date in the HDFS browser.
   - Dashboard: pick a symbol (e.g. NABIL, NTC), 5-year candlestick chart + SMA + RSI, sector trends.
4. **Real-time streaming** (4 min):
   - If the market is **open**: start `live_producer.py` (**LIVE** badge).
   - If the market is **closed**: start `replay_producer.py --speed 60x` on a recorded day (**REPLAY** badge).
   - Show messages arriving in Kafka-UI, then the dashboard ticker updating, gainers/losers changing and **alerts firing**.
5. **Fault tolerance** (1 min, optional): kill the Spark streaming job, restart it, and show it resumes from the checkpoint without data loss.
6. **(Bonus) Prediction** (1 min): MLlib result.
7. **Q&A**

---

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Market closed on demo day | **REPLAY mode** with recorded sessions or historical data |
| NEPSE API changes or blocks requests | Fallback scraper (ShareSansar/MeroLagani) and recorded data |
| No internet at demo venue | Offline `data/sample/` dataset; all containers pulled in advance |
| Laptop RAM limits (Kafka + HDFS + Spark) | Single-node setup, memory limits in Compose; at least 8 GB RAM recommended |
| Historical source unavailable | Several sources (ShareSansar, NepseAlpha, Kaggle) plus the committed sample |
| Demo-time bugs | `demo.sh` scripted run; rehearse twice end-to-end |

---

## 12. Report Mapping to the Assignment

| Assignment question | Plan section |
|---------------------|--------------|
| (a) Define the problem | §1 |
| (a) Data sources | §3 |
| (a) Important features | §4 |
| (b) How data is stored | §5 (HDFS bronze/silver/gold, Parquet, partitioning) |
| (b) Which 2+ Big Data components, and why | §5 *Why these components?* (Kafka + Spark + HDFS) |
| (b) Detailed block diagram | §5 diagram (to be redrawn in draw.io for the report) |
| Demo | §10 |
| Code and implementation guidelines | §7, README.md |
