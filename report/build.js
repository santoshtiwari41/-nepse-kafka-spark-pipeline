// Builds the project report as Word (.docx), a self-contained HTML page AND a print-ready A4 PDF from
// ONE content definition, so all three are always identical:
//   cd report && npm install docx@9.5.1 pdf-lib@1.17.1 && node build.js
//                                              → NEPSE_BigData_Project_Report.{docx,html,pdf}
// The PDF is printed by headless Google Chrome (set CHROME=/path if it is not on PATH) and needs
// pdftotext (poppler-utils). It is built in two passes: pass 1 finds the page of every heading and
// caption, pass 2 prints the table of contents and lists with those page numbers. The same numbers are
// cached in the Word file's table of contents, so it is filled in every viewer (Word refreshes it).
// Figures live in figures/ (architecture.png is rendered from figures/diagram.html).
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, TableOfContents, PageBreak, Footer, PageNumber,
  LevelFormat, VerticalAlign, PageOrientation, NumberFormat, StyleLevel,
} = require("docx");

const BASE = process.argv[2] || path.join(__dirname, "NEPSE_BigData_Project_Report");
const IMG = (f) => fs.readFileSync(path.join(__dirname, "figures", f));

// ───────────── page & style constants (Word) ─────────────
// Standard academic layout: A4, Times New Roman 12 pt, 1.5 line spacing, 1.5" binding margin, 1" elsewhere.
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1440, MARGIN_L = 2160;
const TEXT_W = PAGE_W - MARGIN_L - MARGIN;                  // 8306 DXA ≈ 5.77"
const PX_W = 550;                                           // full-width image, px at 96 dpi
const FONT = "Times New Roman", MONO = "Consolas";
const ACCENT = "000000", HEADER_FILL = "DCE6F1", CODE_FILL = "F2F2F2";

// ───────────── content helpers → IR nodes (rendered to Word and HTML below) ─────────────
// inline markup in text: **bold**, `code`
const P = (text, opts = {}) => ({ t: "p", text, center: !!opts.center });
const H1 = (text) => ({ t: "h1", text, pageBreak: true });
const H1keep = (text) => ({ t: "h1", text, pageBreak: false });
const FM = (text) => ({ t: "h1", text, pageBreak: false, fm: true });     // centred front-matter title
const FMtitle = (text) => ({ t: "fmtitle", text });                       // like FM, but not in the contents
const H2 = (text) => ({ t: "h2", text });
const H3 = (text) => ({ t: "h3", text });
const bullet = (text, level = 0) => ({ t: "bullet", text, level });
const numbered = (text, ref = "steps") => ({ t: "num", text, ref });
const code = (lines) => [{ t: "code", lines }];
let tableNo = 0, figNo = 0;
const caption = (kind, text) => ({ t: "caption", kind, n: kind === "Table" ? ++tableNo : ++figNo, text });
const table = (headers, rows, widths, opts = {}) => ({ t: "table", headers, rows, widths, align: opts.align || [] });
const figure = (file, w, h, text) => [{ t: "img", file, w, h, alt: text }, caption("Figure", text)];
const imgH = (w, h, targetW = PX_W) => Math.round((h * targetW) / w);
const PAGEBREAK = { t: "pagebreak" };

// table captions are written after each table in the content; move them above it
function captionsAbove(items) {
  const out = [...items];
  for (let i = 0; i < out.length - 1; i++) {
    if (out[i].t === "table" && out[i + 1].t === "caption" && out[i + 1].kind === "Table") {
      [out[i], out[i + 1]] = [out[i + 1], out[i]]; i++;
      out.splice(i + 1, 0, { t: "spacer" });
    }
  }
  return out;
}

// ───────────── content ─────────────
const titlePage = [{
  t: "title",
  institution: ["Tribhuvan University", "Institute of Engineering", "Pulchowk Campus"],
  pre: "A Project Report on",
  title: ["Real-Time and Historical Analytics of the", "Nepal Stock Exchange (NEPSE) using a Big Data Stack"],
  tools: "Apache Kafka · Apache Spark (Structured Streaming, SQL, MLlib) · Hadoop HDFS",
  course: "Submitted for the course Big Data Technology",
  by: ["Santosh Tiwari (082MSDSA024)", "Arbind Sah (082MSDSA006)"],
  to: "Basanta Joshi",
  date: "11 October 2026",
}];

const abstract = [
  FM("Abstract"),
  P("Retail investors in Nepal follow the Nepal Stock Exchange (NEPSE) through several separate websites that show current prices but offer no combined view of real-time activity and long-term history. This project builds a big data system that collects NEPSE market data, processes it both as a live stream and as a 31-year historical batch, stores it in a Hadoop data lake and presents the results on an interactive dashboard."),
  P("The system uses **Apache Kafka** for ingestion and **Apache Spark** for processing, with **HDFS** (Parquet files) as the storage layer, following a Lambda-style architecture. Live prices come from the official NEPSE API; when the market is closed, a replay producer streams any past trading day through the same pipeline, so the demonstration never depends on market hours. The batch layer cleans 514,018 historical price records for 372 companies (repairing 40,552 inconsistent rows and correcting 731 bonus/right-share price adjustments) and computes technical indicators such as moving averages, RSI, Bollinger bands and 52-week ranges. The streaming layer produces 1-minute candles, sector money flow, a live market snapshot and alerts for circuit hits, volume spikes and large price moves. A fault-tolerance test in which the streaming job was killed mid-session showed no data loss and no duplication (15,142 of 15,142 ticks stored exactly once). As a bonus, a Spark MLlib random forest predicts next-day price direction; its honest result (55.8 % accuracy against a 55.9 % baseline) illustrates how close daily price moves are to random."),
  P("**Keywords:** big data, Apache Kafka, Apache Spark, Structured Streaming, HDFS, Parquet, Lambda architecture, NEPSE, stock market analytics."),
];

const toc = [FMtitle("Table of Contents"), { t: "toc" }];

const lists = [
  PAGEBREAK, FM("List of Figures"), { t: "lof" },
  PAGEBREAK, FM("List of Tables"), { t: "lot" },
  PAGEBREAK, FM("List of Abbreviations"),
  table(["Abbreviation", "Meaning"], [
    ["API", "Application Programming Interface"],
    ["AUC", "Area Under the (ROC) Curve"],
    ["CSV", "Comma-Separated Values"],
    ["HDFS", "Hadoop Distributed File System"],
    ["JSON / JSONL", "JavaScript Object Notation / JSON Lines (one JSON object per line)"],
    ["ML / MLlib", "Machine Learning / Spark's Machine Learning Library"],
    ["NEPSE", "Nepal Stock Exchange"],
    ["NPT", "Nepal Time (UTC+05:45)"],
    ["OHLC / OHLCV", "Open, High, Low, Close (and Volume) prices of a period"],
    ["RSI", "Relative Strength Index"],
    ["SMA", "Simple Moving Average"],
    ["SQL", "Structured Query Language"],
    ["UI", "User Interface"],
    ["VWAP", "Volume-Weighted Average Price"],
    ["WebHDFS", "HTTP REST interface to HDFS"],
  ], [28, 72]),
];

const ch1 = [
  H1("1. Introduction"),
  H2("1.1 Background"),
  P("The Nepal Stock Exchange (NEPSE) is the only stock exchange in Nepal. Trading takes place on working days between 11:00 and 15:00 Nepal Time (NPT). The official company list used in this project contains 649 listed securities — 489 ordinary shares, 89 debentures, 63 mutual funds and 8 preference shares — across sectors such as commercial banks, hydropower, development banks, microfinance, insurance and manufacturing."),
  P("Market data is published by the exchange itself and by financial portals such as ShareSansar and MeroLagani. These sites show the current price of each stock, but an investor who wants to know whether a price move is unusual, how a sector has performed over the last month, or how today compares with the last ten years has to collect and combine the data manually."),
  H2("1.2 Motivation"),
  P("Stock market data is a natural big data problem: during trading hours hundreds of symbols change price many times per minute (velocity), the history spans decades (volume), and the data comes from several sources in different formats with real quality problems (variety and veracity). A single script and a relational database struggle to ingest a live stream, analyse half a million historical rows and serve the results at the same time. A distributed stack built from Kafka, Spark and HDFS handles each of these jobs with a tool designed for it."),
  H2("1.3 Objectives"),
  bullet("Collect real-time and historical NEPSE data from public sources."),
  bullet("Ingest live (or replayed) price ticks through **Apache Kafka**."),
  bullet("Process the stream in real time with **Spark Structured Streaming**: candles, market snapshot, sector flow and alerts."),
  bullet("Process 31 years of history with **Spark batch / Spark SQL**: cleaning and technical indicators."),
  bullet("Store raw, cleaned and analytical data in an **HDFS** data lake using Parquet."),
  bullet("Present everything on a dashboard that works whether or not the market is open."),
  bullet("Demonstrate fault tolerance and, as a bonus, a distributed machine-learning model (Spark MLlib)."),
  H2("1.4 Scope"),
  P("The system covers all securities traded on NEPSE, daily price history from 1995 (dense from 2011) to the present, and intraday ticks for live or replayed sessions. It runs on a single machine with Docker; every component is a real distributed service (Kafka broker, HDFS NameNode and DataNode, Spark master and worker) and would scale out by adding nodes. The project is an analytics tool, not a trading system, and nothing in it is investment advice."),
];

const ch2 = [
  H1("2. Problem Definition"),
  H2("2.1 Problem statement"),
  P("**Retail investors in Nepal have no single, free tool that combines real-time NEPSE market monitoring with historical context.** In particular they cannot easily:"),
  bullet("see live prices, turnover and the day's biggest movers for the whole market in one place;"),
  bullet("get notified automatically about unusual activity — volume spikes, sudden price moves, or stocks hitting the ±10 % daily circuit limit;"),
  bullet("compare today's behaviour with years of history through technical indicators (moving averages, RSI, 52-week range) and sector trends;"),
  bullet("trust the historical numbers — raw data contains inconsistent rows and price drops caused by bonus and right shares that look like crashes."),
  P("The goal of this project is to design and build a big data pipeline that ingests NEPSE data **live or as a replay of any past day**, processes it **in real time and in batch**, stores it in a **data lake**, and presents insights and alerts on a dashboard."),
  H2("2.2 Why this is a big data problem"),
  table(["Characteristic", "How it appears in NEPSE data"], [
    ["Volume", "514,018 daily price records for 372 companies (1995–2026), 6,196 days of NEPSE index; a single replayed trading day produces 15,142 intraday ticks for 327 symbols, and a live day produces more."],
    ["Velocity", "Live prices for ~350 symbols polled every 5 seconds during trading hours; alerts must be raised within seconds."],
    ["Variety", "JSON from the NEPSE API, HTML tables from ShareSansar, CSV files from GitHub, TradingView-style JSON from MeroLagani, reference data (company list) and recorded sessions (JSONL)."],
    ["Veracity", "40,552 rows (8 %) with a high/low that does not contain the open/close, 20 invalid rows, and 731 artificial price drops from bonus/right-share adjustments."],
    ["Value", "Market overview, unusual-activity alerts, technical analysis and sector money flow that are not available in one place today."],
  ], [22, 78]),
  caption("Table", "The five Vs of big data applied to NEPSE"),
];

const ch3 = [
  H1("3. Data Sources"),
  P("All sources are public. Each was tested during the project; Table 2 lists what is collected from each and how."),
  table(["#", "Data", "Source", "Type / format", "Collected by"], [
    ["1", "Live market: last traded price, open/high/low, volume, turnover, last trade quantity, % change", "nepalstock.com official API (via the open-source NepseUnofficialApi library)", "Real-time · JSON", "`live_producer.py` (polls every 5 s)"],
    ["2", "Live market (fallback)", "ShareSansar live-trading page", "Real-time · HTML table", "`live_producer.py` (used automatically if the API fails)"],
    ["3", "Daily OHLCV + turnover for ~370 companies, 1995 → today", "GitHub dataset Aabishkar2/nepse-data (updated daily from the exchange)", "Batch · CSV", "`fetch_history.py`"],
    ["4", "NEPSE index history since 2000; per-symbol history (fallback)", "MeroLagani chart API", "Batch · JSON", "`fetch_history.py`"],
    ["5", "Company master: symbol, name, sector, instrument type (649 securities)", "nepalstock.com official API", "Reference · JSON → CSV", "`fetch_companies.py`"],
    ["6", "Recorded live sessions", "Our own live producer, saved during market hours", "Replay · JSONL", "`live_producer.py`"],
  ], [4, 28, 26, 16, 26]),
  caption("Table", "Data sources"),
  P("A small **offline sample** (42 stocks — the three most traded in every sector plus well-known blue chips — from 2019 to today, 4 MB) is committed to the project repository so the complete system can run without internet access."),
  H2("3.1 Common message format"),
  P("Both live and replay producers publish the same JSON message to Kafka, keyed by stock symbol. Because the format is identical, the Spark jobs do not need to know which mode is running:"),
  ...code([
    '{"symbol": "NABIL", "ts": "2026-10-09T14:59:59+05:45", "ltp": 536.2,',
    ' "open": 532.0, "high": 538.0, "low": 531.0, "prev_close": 533.0,',
    ' "volume": 48779, "turnover": 26163739.6, "last_qty": 10, "change_pct": 0.6,',
    ' "source": "nepse-api", "mode": "LIVE",',
    ' "session_start": "2026-10-09T11:00:00+05:45", "session_date": "2026-10-09"}',
  ]),
];

const ch4 = [
  H1("4. Important Features Considered"),
  H2("4.1 Data features (raw)"),
  table(["Feature", "Meaning"], [
    ["symbol, company_name, sector, instrument_type", "Identity and classification of the security (from the company master)"],
    ["date / ts", "Trading day (history) or event time of a tick (stream), Nepal time"],
    ["open, high, low, close / ltp", "Prices; ltp = last traded price"],
    ["prev_close, change_pct", "Previous day's close and percentage change — basis for the ±10 % circuit rule"],
    ["volume, turnover", "Shares traded and value traded in NPR (cumulative for the day in ticks)"],
    ["last_qty", "Quantity of the most recent trade — used for per-minute volume and VWAP"],
  ], [38, 62]),
  caption("Table", "Raw data features"),
  H2("4.2 Derived analytical features"),
  table(["Feature", "Layer", "Purpose"], [
    ["1-minute OHLC candles, VWAP", "Streaming", "Intraday price chart; volume-weighted average price"],
    ["Live state per symbol, gainers/losers, most active", "Streaming", "Market overview"],
    ["Sector money flow per minute", "Streaming", "Which sectors are attracting money right now"],
    ["Circuit alert (|change| ≥ 9.5 %)", "Streaming", "Stocks at or near NEPSE's ±10 % daily limit"],
    ["Volume-spike alert (volume ≥ 3 × 20-day average)", "Streaming + batch", "Unusual activity (stream joined with batch baseline)"],
    ["Big-move alert (≥ 5 % from today's open)", "Streaming", "Sudden intraday swings"],
    ["SMA 20 / 50 / 200, Bollinger bands, RSI 14", "Batch", "Trend and momentum"],
    ["52-week high/low, 1w/1m/3m/1y returns, volatility", "Batch", "Long-term context and risk"],
    ["Golden / death cross, trend label, RSI signal", "Batch", "Simple, explainable signals for the screener"],
    ["Sector and market daily aggregates, breadth", "Batch", "Sector rotation and market health"],
    ["Corporate-action adjusted prices (adj_*)", "Batch", "Remove artificial drops caused by bonus/right shares"],
    ["Next-day up/down probability", "Batch (MLlib)", "Bonus: machine-learning demonstration"],
  ], [40, 20, 40]),
  caption("Table", "Derived features"),
  H2("4.3 System design features"),
  bullet("**Scalability** — Kafka partitions the tick topic by symbol; Spark processes partitions in parallel; HDFS distributes blocks over DataNodes."),
  bullet("**Fault tolerance** — Kafka retains messages for 7 days; Spark Structured Streaming checkpoints offsets and state in HDFS, so a crashed job resumes exactly where it stopped."),
  bullet("**Low latency** — alerts and the live snapshot are updated every 5 seconds; 1-minute candles are written about 10–20 seconds after the minute closes."),
  bullet("**Data quality** — validation, de-duplication, OHLC repair and corporate-action adjustment in the batch layer, with a stored data-quality report."),
  bullet("**Source independence** — LIVE, REPLAY and HISTORICAL modes share one message schema and one pipeline, so the demo never depends on market hours."),
  bullet("**Efficient storage** — columnar Parquet, sensible partitioning, and a log-compacted Kafka topic for the latest state."),
];

const ch5 = [
  H1("5. System Design"),
  H2("5.1 Choice of big data components"),
  P("The assignment asks for two big data tools. This project uses **Apache Kafka** and **Apache Spark** as its two main tools, with **Hadoop HDFS** as the storage layer that both of them use."),
  H3("Apache Kafka — ingestion and messaging"),
  P("Kafka is a distributed, partitioned commit log. Producers append messages to topics and consumers read them at their own pace using offsets. It was chosen because it **decouples** the data sources from processing (if Spark is restarted, ticks wait safely in Kafka), **absorbs bursts** at market open, keeps data for **replay**, and lets the live and replay producers write to the same topic. Kafka also serves processed results to the dashboard: the `nepse.analytics` topic is log-compacted, so it keeps only the latest message per symbol."),
  H3("Apache Spark — stream and batch processing"),
  P("Spark offers one engine and one DataFrame API for both **Structured Streaming** (micro-batch stream processing with event-time windows, watermarks, stateful aggregation and exactly-once file sinks) and **batch** processing with Spark SQL and window functions. The same team can therefore write the speed layer and the batch layer with the same skills. Spark MLlib adds distributed machine learning on the same data."),
  H3("Hadoop HDFS — storage"),
  P("HDFS stores large files as blocks spread over DataNodes, with the NameNode keeping the metadata. It suits write-once, read-many analytical data, integrates natively with Spark, and stores Spark's streaming checkpoints. Data is kept as **Parquet**, a compressed columnar format: Spark reads only the columns a query needs."),
  table(["Need", "Chosen", "Alternatives considered", "Reason for the choice"], [
    ["Ingestion / messaging", "Kafka", "Apache Flume, RabbitMQ", "Flume moves data into Hadoop but cannot replay to many consumers; RabbitMQ deletes messages once consumed. Kafka keeps an ordered, replayable log."],
    ["Stream processing", "Spark Structured Streaming", "Apache Flink, Kafka Streams", "Flink has lower latency, but Spark gives one API for streaming, batch, SQL and ML; 5-second micro-batches are fast enough for NEPSE."],
    ["Batch processing", "Spark SQL", "Hadoop MapReduce, Hive", "Spark runs window-heavy indicator jobs in memory, far faster than MapReduce, and shares code with the stream."],
    ["Storage", "HDFS + Parquet", "Cassandra, HBase, MongoDB", "Analytics scan whole columns over years of data — a columnar data lake fits better than key-value stores, which suit single-row lookups."],
    ["Serving latest state", "Compacted Kafka topic", "Redis, Cassandra", "Avoids another database: compaction keeps only the newest message per symbol."],
  ], [17, 17, 22, 44]),
  caption("Table", "Big data components chosen and alternatives"),
];
const LAND_PX = 925;
const ch5diagram = [
  H2("5.2 Block diagram"),
  ...figure("architecture.png", LAND_PX, imgH(3400, 1720, LAND_PX), "Block diagram of the NEPSE big data system (speed layer above, batch layer below)"),
];
const ch5b = [
  P("Data flows through the system as follows (Figure 1):"),
  numbered("**Sources → ingestion.** The live producer polls the NEPSE API every 5 seconds (ShareSansar as fallback) and publishes only ticks whose price or volume changed. The replay producer streams a recorded session, or simulates intraday ticks from a day's open/high/low/close/volume, at a chosen speed.", "flow"),
  numbered("**Kafka.** Ticks land in `nepse.ticks` (3 partitions, keyed by symbol, so each stock's ticks stay in order).", "flow"),
  numbered("**Spark Structured Streaming** reads the topic, applies an event-time watermark, and runs five queries: raw ticks → HDFS bronze; 1-minute candles and sector flow → HDFS gold; live state per symbol → Kafka `nepse.analytics`; alerts → Kafka `nepse.alerts` and HDFS gold.", "flow"),
  numbered("**Batch layer.** Spark loads the historical CSV files into HDFS bronze, cleans them into silver, computes indicators and aggregates into gold, trains the MLlib model and answers analytical questions with Spark SQL.", "flow"),
  numbered("**Stream-static join.** The streaming job enriches every tick with batch results (sector, normal 20-day volume), which connects the two layers.", "flow"),
  numbered("**Dashboard.** Streamlit consumes the two Kafka output topics for the live view and reads gold Parquet files from HDFS (WebHDFS) for history.", "flow"),
  H2("5.3 Data storage design"),
  H3("5.3.1 HDFS data lake: bronze, silver and gold layers"),
  P("The data lake follows the common bronze / silver / gold (medallion) layout. Each layer has a single job, and any layer can be rebuilt from the one below it."),
  table(["Layer", "HDFS path", "Content", "Partitioning", "Size"], [
    ["Bronze (raw)", "/nepse/bronze/prices, index, companies", "CSV data exactly as received + lineage columns (_source_file, _ingested_at)", "—", "11.9 MB"],
    ["Bronze (raw)", "/nepse/bronze/ticks", "Every streamed tick", "trade_date", "grows per session"],
    ["Silver (clean)", "/nepse/silver/prices, index, companies", "Validated, de-duplicated, OHLC-repaired, bonus-adjusted prices with sector", "year", "23.1 MB"],
    ["Gold (analytics)", "/nepse/gold/indicators", "SMA, RSI, Bollinger, volatility, returns, signals per symbol per day", "year", "51.7 MB"],
    ["Gold (analytics)", "/nepse/gold/latest_snapshot, volume_baseline, sector_daily, market_daily, data_quality, ml_*", "Screener, alert baseline, sector/market history, quality report, ML results", "year (sector_daily)", "≈ 1.5 MB"],
    ["Gold (streaming)", "/nepse/gold/candles_1m, sector_flow_1m, alerts", "Outputs of Spark Structured Streaming", "trade_date", "grows per session"],
    ["Checkpoints", "/nepse/checkpoints/<query>", "Kafka offsets and streaming state for exactly-once recovery", "—", "small"],
  ], [14, 26, 34, 13, 13]),
  caption("Table", "HDFS data lake layout"),
  H3("5.3.2 File format: Parquet"),
  P("All HDFS data is stored as Parquet. Being columnar, a query that needs only `date` and `adj_close` reads only those columns, and similar values in a column compress well. The 33 MB of raw price CSV files occupy **11.7 MB** as Parquet in the bronze layer — about **2.8 × smaller** — even after adding two lineage columns."),
  H3("5.3.3 Partitioning strategy"),
  P("Historical tables are partitioned by **year**, not by day. Partitioning by day would create about 3,500 directories of tiny files — the well-known HDFS **small-files problem**, where every file costs NameNode memory and adds task overhead. Yearly partitions still let queries such as “last 5 years” skip old data. Streaming outputs are partitioned by `trade_date`, which suits their append-only, per-session nature."),
  H3("5.3.4 Kafka topics"),
  table(["Topic", "Partitions", "Key", "Retention / cleanup", "Content"], [
    ["nepse.ticks", "3", "symbol", "7 days (delete)", "Raw ticks from the live or replay producer"],
    ["nepse.analytics", "1", "symbol", "log compaction", "Latest state per symbol computed by Spark"],
    ["nepse.alerts", "1", "symbol", "7 days (delete)", "Circuit, volume-spike and big-move alerts"],
  ], [18, 12, 10, 20, 40]),
  caption("Table", "Kafka topics"),
  P("Log compaction on `nepse.analytics` made a measurable difference: after many replays the topic shrank from 23 MB to 1.5 MB and the dashboard's start-up catch-up time fell from **19.2 s to 1.4 s**."),
  H3("5.3.5 Replication"),
  P("HDFS normally keeps three copies of every block on different DataNodes. This single-machine deployment has one DataNode, so the replication factor is set to 1 (for both the NameNode configuration and the Spark HDFS client). Moving to a real cluster only requires more DataNodes and raising `dfs.replication` to 3; no code changes."),
  H2("5.4 Operating modes"),
  P("NEPSE trades only about four hours per working day, and the demonstration may take place when the market is closed. The system therefore supports three modes that share one pipeline:"),
  table(["Mode", "When used", "Data path", "Dashboard badge"], [
    ["LIVE", "Market open", "NEPSE API → live producer → Kafka → Spark Streaming", "red “LIVE”"],
    ["REPLAY", "Market closed", "Recording or historical day → replay producer (e.g. 60×) → Kafka → Spark Streaming", "orange “REPLAY · replaying the 2026-10-09 session”"],
    ["HISTORICAL", "Always", "History CSV → Spark batch → HDFS gold", "blue “HISTORICAL” (no active stream)"],
  ], [14, 16, 45, 25]),
  caption("Table", "Operating modes"),
  P("In REPLAY mode the timestamps are shifted to the current time and compressed by the replay speed, so Spark sees a fresh, live-looking stream every time. Each replay loop is tagged as a separate **session**, so results from two loops are never mixed."),
];

const ch6 = [
  H1("6. Implementation"),
  H2("6.1 Environment and technology stack"),
  table(["Component", "Version", "Role"], [
    ["Docker / Docker Compose", "29.1 / 5.4", "Runs every service as a container on one machine"],
    ["Apache Kafka (KRaft mode, no ZooKeeper)", "3.9.0", "Message broker"],
    ["Kafka UI (provectuslabs)", "0.7.2", "Topic and message browser for the demo"],
    ["Apache Hadoop HDFS (NameNode + DataNode)", "3.3.6", "Distributed file system / data lake"],
    ["Apache Spark (master + worker, PySpark)", "3.5.3", "Structured Streaming, Spark SQL, MLlib"],
    ["Python + uv (ingestion container)", "3.12 / 0.4", "Data collection, live and replay producers"],
    ["Streamlit + Plotly", "1.45 / 5.24", "Dashboard"],
  ], [45, 15, 40]),
  caption("Table", "Technology stack"),
  P("The Spark image has the Kafka connector JARs built in, so jobs start without downloading anything and the whole stack works offline once the images are built. Each Spark application may use at most two of the worker's four cores, so the streaming job and a batch job can run at the same time."),
  H2("6.2 Data collection and ingestion"),
  bullet("`fetch_companies.py` downloads the 649-security company list with sectors from the NEPSE API."),
  bullet("`fetch_history.py` downloads daily OHLCV and turnover for all companies (GitHub dataset) and the NEPSE index (MeroLagani), and normalises them into one CSV schema."),
  bullet("`live_producer.py` checks the NEPSE market-status API, polls live prices every 5 seconds, sends only changed ticks to Kafka and records the session to a JSONL file for later replay."),
  bullet("`replay_producer.py` streams a recorded session, or simulates a session from daily data: the simulated price path starts at the day's open, touches its high and low and ends exactly at its close, with the day's volume split across trades. The NABIL replay for 2026-10-09 ends at the real close (536.2), high (538), low (531) and volume (48,779); simulated turnover is within 0.4 % of the real value."),
  H2("6.3 Batch processing (Spark SQL)"),
  P("`batch_load_history.py` loads the CSV files into bronze and builds silver with these rules:"),
  numbered("Drop rows with missing or non-positive prices or zero volume (20 rows).", "clean"),
  numbered("Drop duplicate (symbol, date) rows (none found).", "clean"),
  numbered("Repair OHLC: widen high/low to include open and close (40,552 rows).", "clean"),
  numbered("Detect corporate actions: NEPSE's daily circuit is ±10 %, so an opening gap below −10.5 % must be a bonus or right-share adjustment rather than trading. Earlier prices are multiplied by the gap ratio (back-adjustment) into `adj_*` columns, using a window sum of log-ratios over later rows (731 adjustments).", "clean"),
  numbered("Recompute change % from the previous close and attach sector and instrument type.", "clean"),
  P("`batch_indicators.py` then computes all indicators with Spark window functions partitioned by symbol and ordered by date, and writes the gold tables. Sector and market statistics count ordinary shares only, so debentures and mutual funds do not distort them. `batch_queries.py` answers analytical questions in Spark SQL, for example:"),
  ...code([
    "SELECT sector, ROUND(SUM(turnover) / 1e9, 2) AS turnover_billion_npr,",
    "       SUM(advancers) AS advances, SUM(decliners) AS declines",
    "FROM sector_daily",
    "WHERE date >= date_sub((SELECT MAX(date) FROM sector_daily), 30)",
    "GROUP BY sector ORDER BY turnover_billion_npr DESC",
  ]),
  H2("6.4 Stream processing (Spark Structured Streaming)"),
  table(["Query", "Output", "Technique"], [
    ["ticks", "HDFS bronze/ticks", "Exactly-once Parquet file sink, partitioned by trade_date"],
    ["candles_1m", "HDFS gold/candles_1m", "1-minute event-time tumbling windows, 10 s watermark, OHLC + VWAP"],
    ["sector_flow", "HDFS gold/sector_flow_1m", "Windowed aggregation by sector after a stream-static join"],
    ["live_snapshot", "Kafka nepse.analytics", "Stateful aggregation (latest tick per symbol per session), update output mode"],
    ["alerts", "Kafka nepse.alerts + HDFS gold/alerts", "Filters on enriched ticks, de-duplicated with dropDuplicatesWithinWatermark, written by foreachBatch to both sinks"],
  ], [16, 28, 56]),
  caption("Table", "Streaming queries"),
  P("All five queries run in one Spark application, each with its own checkpoint directory in HDFS. Ticks are joined with two batch-layer tables — the company list (sector) and the 20-day volume baseline — so the volume-spike alert compares today's volume with the stock's normal volume."),
  H2("6.5 Machine learning (Spark MLlib, bonus)"),
  P("`ml_predict.py` builds ten features from the gold indicators — daily return, 1-week and 1-month return, RSI, distance from SMA 20 and SMA 50, SMA 50 vs SMA 200, position within the Bollinger band, volume ratio and volatility — and a label that is 1 if the stock closes higher the next day. A random forest (60 trees, depth 7) is trained on 2015–2024 and tested on 2025 onward. This **time-based split** prevents the model from learning from the future, a common mistake with random splits on time series."),
  H2("6.6 Dashboard"),
  P("The Streamlit dashboard has five tabs. The live tab refreshes every 3 seconds; the others read the gold layer from HDFS."),
  ...figure("dash_live.png", PX_W, imgH(1980, 2409, PX_W), "Live market tab during a REPLAY session: mode badge, market KPIs, movers, sector map and Spark alerts"),
  ...figure("dash_stock.png", PX_W, imgH(1980, 1491), "Stock explorer: bonus-adjusted candlesticks with SMA 20/50/200, Bollinger band, volume and RSI"),
  ...figure("dash_market.png", PX_W, imgH(1980, 1730), "Market & sectors tab: NEPSE index with moving averages, yearly returns and turnover by sector"),
  ...figure("dash_screener.png", PX_W, imgH(1980, 1145), "Screener: all securities filtered by sector, trend, RSI signal and volume spike"),
  ...figure("dash_pipeline.png", PX_W, imgH(1980, 1563), "Pipeline tab: architecture, Kafka topic sizes, data-quality report and HDFS datasets"),
];

const ch7 = [
  H1("7. Results and Evaluation"),
  H2("7.1 Data quality"),
  table(["Metric", "Value"], [
    ["Raw price rows loaded", "514,018"],
    ["Invalid rows dropped", "20"],
    ["Duplicate rows dropped", "0"],
    ["Rows with OHLC repaired", "40,552 (7.9 %)"],
    ["Bonus/right-share adjustments detected", "731"],
    ["Clean rows in silver", "513,998"],
    ["Companies", "372"],
    ["Date range", "1995-07-20 → 2026-10-09"],
  ], [60, 40], { align: ["l", "r"] }),
  caption("Table", "Data-quality report produced by the batch layer"),
  P("The corporate-action detection is easy to verify on NABIL Bank: it found ten adjustments, including 2017-09-12, when the price opened at 1,254 after closing at 1,630 — a ratio of 0.769, i.e. a 30 % bonus share. Without the adjustment, moving averages and 52-week ranges would treat these days as crashes."),
  H2("7.2 Sample analytical results"),
  table(["Year", "2012", "2013", "2016", "2017", "2018", "2020", "2021", "2022", "2024", "2025"], [
    ["NEPSE return (%)", "+67.6", "+45.2", "+24.3", "−5.1", "−17.3", "+78.5", "+16.1", "−21.5", "+25.1", "+2.0"],
  ], [17.0, 8.3, 8.3, 8.3, 8.3, 8.3, 8.3, 8.3, 8.3, 8.3, 8.3], { align: ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r"] }),
  caption("Table", "NEPSE yearly returns computed with Spark SQL (selected years)"),
  P("Over the last 30 trading days, hydropower was by far the most traded sector (NPR 43.4 billion), followed by commercial banks (15.4 billion) and manufacturing (13.9 billion). On the latest trading day (2026-10-09) the screener flagged NABIL as oversold (RSI 29.7) and found six ordinary shares trading at three or more times their normal volume."),
  H2("7.3 Streaming results"),
  bullet("A full trading day (2026-10-09) replayed at 60× produced **15,142 ticks for 327 symbols** in about 4 minutes, all received by Kafka and stored in HDFS."),
  bullet("Each replayed session raised about 30 alerts — mostly big intraday moves (e.g. MABEL +7.7 % from the open) and volume spikes (KBSH, CGH, BHL at 3× their normal volume)."),
  bullet("The final live state of each stock matched the real end-of-day data; for NABIL: 536.2, +0.6 %, 48,779 shares, VWAP 534.19."),
  bullet("Latency: the live snapshot and alerts refresh every 5 seconds; a 1-minute candle is written 10–20 seconds after its minute closes."),
  H2("7.4 Fault-tolerance test"),
  P("A full day was replayed while the streaming job was deliberately stopped about one minute into the session and restarted 50 seconds later; ticks kept arriving in Kafka while Spark was down. Afterwards HDFS contained **15,142 ticks, all distinct, out of 15,142 sent** — nothing lost and nothing duplicated. This works because Spark stores its Kafka offsets in the checkpoint and the Parquet file sink commits each micro-batch exactly once. The 1-minute candles were continuous across the outage. (Alerts use `foreachBatch`, which is at-least-once; a duplicate alert after a crash is acceptable.)"),
  H2("7.5 Performance and resources"),
  table(["Measurement", "Result"], [
    ["Load + clean 514 k rows (CSV → bronze → silver)", "≈ 1.5 min"],
    ["Indicators and gold tables", "≈ 1.7 min"],
    ["MLlib training and evaluation (351 k labelled rows)", "≈ 2 min"],
    ["Whole batch layer incl. SQL showcase", "≈ 5.5 min"],
    ["Compression: raw CSV → Parquet (bronze)", "33 MB → 11.7 MB"],
    ["Dashboard start-up catch-up (after log compaction)", "19.2 s → 1.4 s"],
    ["Memory used by the stack when idle", "≈ 1.7 GB"],
    ["Hardware", "8 CPU cores, 11 GB RAM laptop; Spark worker: 4 cores, 2 GB"],
  ], [62, 38]),
  caption("Table", "Performance measurements"),
  H2("7.6 Machine-learning results"),
  table(["Metric", "Value"], [
    ["Training rows (2015–2024)", "255,557"],
    ["Test rows (2025 → 2026-10)", "95,838"],
    ["Test accuracy", "55.8 %"],
    ["Baseline: always predict the majority class (“down”)", "55.9 %"],
    ["AUC", "0.519"],
    ["Accuracy of confident predictions (p ≥ 0.6 or ≤ 0.4; 965 rows)", "64 %"],
  ], [70, 30], { align: ["l", "r"] }),
  caption("Table", "Spark MLlib random forest — next-day direction"),
  ...figure("dash_ml.png", 330, imgH(1020, 840, 330), "MLlib results and feature importance shown on the dashboard"),
  P("Overall the model is no better than always guessing “down”, and its AUC is only slightly above 0.5. This is the expected and honest outcome: daily price changes are close to random, and publicly available technical indicators carry little predictive information. The model's rare confident calls were right 64 % of the time, which hints at a weak signal, but on too few cases to act on. The most useful features were volume ratio, the latest daily return, the 1-week return and the Bollinger-band position. The value of this part is to show a distributed, leakage-free ML pipeline, not to predict prices."),
  H2("7.7 Problems encountered and solutions"),
  table(["Problem", "Solution"], [
    ["The demo may happen when NEPSE is closed", "REPLAY mode streams any past day through the same pipeline"],
    ["Bonus/right shares look like 20–30 % crashes", "Detect gaps beyond the ±10 % circuit and back-adjust prices"],
    ["Debentures and mutual funds appeared as top-gaining “bank” stocks", "Filter statistics to ordinary shares using the instrument type"],
    ["Spark wrote HDFS files with 3 replicas on a 1-DataNode cluster", "Set the HDFS client replication to 1 in Spark's configuration"],
    ["Streaming job took all 4 worker cores; batch jobs waited forever", "Cap every Spark application at 2 cores (spark.cores.max)"],
    ["Replaying the same day twice would be dropped as late data", "Replay shifts timestamps to now; each loop is a new session"],
    ["Back-to-back replay loops suppressed each other's alerts", "Include the session in the alert de-duplication key"],
    ["Dashboard needed 19 s to read the analytics topic", "Kafka log compaction on nepse.analytics (1.4 s)"],
    ["Candles stored in UTC, compared with Nepal time", "Convert timestamps explicitly in the dashboard"],
    ["Forced image rebuild needs internet (would fail offline)", "Start script reuses built images"],
  ], [50, 50]),
  caption("Table", "Problems encountered and how they were solved"),
];

const ch8 = [
  H1("8. Demonstration Plan"),
  P("The demo is run by one script, `./scripts/demo.sh`, which pauses between steps:"),
  numbered("Start the stack (Kafka, HDFS, Spark, dashboard) and show the Kafka UI, HDFS and Spark web interfaces.", "demo"),
  numbered("Batch layer: show the Spark SQL answers and the HDFS bronze/silver/gold folders; dashboard tabs Stock explorer, Market & sectors and Screener.", "demo"),
  numbered("Start Spark Structured Streaming and show its five queries in the Spark UI.", "demo"),
  numbered("Start the LIVE producer if NEPSE is open, otherwise REPLAY the latest trading day; show messages arriving in the Kafka UI and the Live market tab updating with alerts.", "demo"),
  numbered("Fault tolerance: kill the streaming job, wait 20 seconds, restart it and show that it resumes without loss.", "demo"),
  numbered("Pipeline tab: architecture, topic and dataset sizes, data quality and the MLlib result.", "demo"),
  P("The demo works fully offline: the images are pre-built, the Spark image contains the Kafka connector, the dashboard loads no external resources (verified with all non-local network requests blocked) and the replay uses local data."),
];

const ch9 = [
  H1("9. Limitations and Future Work"),
  H2("9.1 Limitations"),
  bullet("Runs on one machine: one Kafka broker, one DataNode (replication 1), one Spark worker. The design is distributed, but the deployment is not."),
  bullet("Bonus shares smaller than about 10 % cannot be distinguished from normal price moves, so they are not adjusted; a few early records are also inconsistent."),
  bullet("Simulated replay ticks follow the real daily open/high/low/close/volume but not the real intraday order of trades; recorded sessions solve this."),
  bullet("RSI uses a simple moving average of gains and losses rather than Wilder's smoothing."),
  bullet("The live source relies on an unofficial client for the NEPSE website, which may break if the website changes (ShareSansar is the fallback)."),
  bullet("The machine-learning model has no practical predictive power for daily moves."),
  H2("9.2 Future work"),
  bullet("Deploy on a real multi-node cluster (3 Kafka brokers, 3 DataNodes with replication 3, several Spark workers)."),
  bullet("Use the official corporate-action (bonus/right/dividend) records for exact price adjustment."),
  bullet("Add news and social-media sentiment (e.g. ShareSansar and MeroLagani headlines) as another stream and study its link with price moves."),
  bullet("Compact small streaming output files periodically and register tables in a Hive metastore."),
  bullet("Add user watchlists and push notifications for alerts on chosen stocks."),
];

const ch10 = [
  H1("10. Conclusion"),
  P("This project designed and implemented a working big data system for the Nepal Stock Exchange. **Apache Kafka** ingests live or replayed market ticks and serves processed results; **Apache Spark** processes the same data as a real-time stream (candles, market state, sector flow and alerts) and as a 31-year batch (cleaning, technical indicators, SQL analytics and an MLlib model); **HDFS** stores raw, clean and analytical data in Parquet in a bronze/silver/gold layout. Joining the batch outputs into the stream links the two layers, and the replay mode means the system can be demonstrated at any time."),
  P("The evaluation showed concrete results: half a million historical rows cleaned with real data-quality problems fixed, a full trading day streamed and analysed in minutes, exactly-once recovery after a crash, and an honest assessment of what machine learning can and cannot do with daily stock data. The project shows how components of the big data ecosystem combine to solve a real problem that is relevant to investors in Nepal."),
];

const refs = [
  H1("References"),
  ...[
    "Apache Software Foundation, “Apache Kafka Documentation.” https://kafka.apache.org/documentation/",
    "Apache Software Foundation, “Structured Streaming Programming Guide,” Apache Spark 3.5.3. https://spark.apache.org/docs/3.5.3/structured-streaming-programming-guide.html",
    "Apache Software Foundation, “Spark SQL, DataFrames and Datasets Guide,” Apache Spark 3.5.3. https://spark.apache.org/docs/3.5.3/sql-programming-guide.html",
    "Apache Software Foundation, “Machine Learning Library (MLlib) Guide,” Apache Spark 3.5.3. https://spark.apache.org/docs/3.5.3/ml-guide.html",
    "Apache Software Foundation, “HDFS Architecture,” Apache Hadoop 3.3.6. https://hadoop.apache.org/docs/r3.3.6/hadoop-project-dist/hadoop-hdfs/HdfsDesign.html",
    "Apache Software Foundation, “Apache Parquet Documentation.” https://parquet.apache.org/docs/",
    "N. Marz and J. Warren, Big Data: Principles and Best Practices of Scalable Realtime Data Systems. Manning, 2015.",
    "Nepal Stock Exchange Ltd. https://www.nepalstock.com",
    "basic-bgnr, “NepseUnofficialApi,” GitHub. https://github.com/basic-bgnr/NepseUnofficialApi",
    "Aabishkar2, “nepse-data: Historical and current datasets of Nepal Stock Market listed companies,” GitHub. https://github.com/Aabishkar2/nepse-data",
    "MeroLagani. https://merolagani.com",
    "ShareSansar. https://www.sharesansar.com",
    "Streamlit Documentation. https://docs.streamlit.io",
  ].map((r) => numbered(r, "refs")),
];

const appendix = [
  H1("Appendix A: Installation and Execution"),
  P("All components of the system run as Docker containers managed with Docker Compose, including the Python data-collection and producer scripts, so no local Python installation is required. Table 16 lists the commands used to set up and operate the system, in order."),
  table(["Step", "Command", "Purpose"], [
    ["1. Start services", "`./scripts/start.sh`", "Starts Kafka, HDFS, Spark and the dashboard; creates the Kafka topics and HDFS directories"],
    ["2. Verify", "`./scripts/verify.sh`", "Checks every service and runs an end-to-end Spark–Kafka–HDFS test"],
    ["3. Collect data", "`./scripts/ingest.sh fetch_history`", "Downloads daily price history and the NEPSE index (the company list is included in the repository)"],
    ["4. Batch processing", "`./scripts/run_batch.sh`", "Builds the bronze, silver and gold layers and trains the MLlib model"],
    ["5. Stream processing", "`./scripts/stream.sh start`", "Starts the Spark Structured Streaming job"],
    ["6. Data ingestion", "`./scripts/ingest.sh live_producer`", "Publishes live ticks to Kafka; `replay_producer` replays a past trading day instead"],
  ], [20, 34, 46]),
  caption("Table", "Setup and execution commands"),
  table(["Service", "Address"], [
    ["Dashboard", "http://localhost:8501"],
    ["Kafka UI", "http://localhost:8085"],
    ["HDFS NameNode", "http://localhost:9870"],
    ["Spark master / streaming UI", "http://localhost:8080 / http://localhost:4040"],
  ], [40, 60]),
  caption("Table", "Web interfaces"),
  H1keep("Appendix B: Project Structure"),
  ...code([
    "docker-compose.yml      all services",
    "config/hadoop.env       HDFS configuration",
    "ingestion/              fetch_companies.py, fetch_history.py, build_sample.py,",
    "                        live_producer.py, replay_producer.py, common.py, Dockerfile",
    "spark/Dockerfile        Spark 3.5.3 image with the Kafka connector built in",
    "spark/conf/             spark-defaults.conf, log4j2.properties",
    "spark/jobs/             batch_load_history.py, batch_indicators.py, batch_queries.py,",
    "                        ml_predict.py, stream_processor.py, stream_report.py",
    "dashboard/              Streamlit app (app.py, data.py)",
    "scripts/                start, stop, init, verify, run_batch, stream,",
    "                        spark_submit, ingest, demo",
    "data/                   sample/ (offline dataset), reference/,",
    "                        historical/, recordings/",
    "plan.md, README.md      design document and setup guide",
  ]),
  H1("Appendix C: Division of Work"),
  table(["Santosh Tiwari (082MSDSA024) — ingestion and storage", "Arbind Sah (082MSDSA006) — processing and visualisation"], [
    ["Docker Compose setup (Kafka, HDFS)", "Spark cluster configuration"],
    ["Data collection scripts and data cleaning rules", "Batch indicators and Spark SQL queries"],
    ["Live producer and session recordings", "Spark Structured Streaming job and alerts"],
    ["Replay producer", "Streamlit dashboard"],
    ["HDFS data-lake layout (bronze/silver/gold)", "MLlib model"],
    ["Report: problem, sources and features (part a)", "Report: storage, components and block diagram (part b)"],
  ], [50, 50]),
  caption("Table", "Division of work"),
];

// ───────────── document order ─────────────
const front = captionsAbove([...titlePage, PAGEBREAK, ...abstract, PAGEBREAK, ...toc, ...lists]);   // roman pages
const partA = captionsAbove([...ch1, ...ch2, ...ch3, ...ch4, ...ch5]);                      // page 1 onwards
const partB = ch5diagram;                                  // landscape page
const partC = captionsAbove([...ch5b, ...ch6, ...ch7, ...ch8, ...ch9, ...ch10, ...refs, ...appendix]);
const isPlaceholder = (t) => /^\[.*\]$/.test(t);

// ═════════════════════════════ Word renderer ═════════════════════════════
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: 19, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const centered = (children, spacing = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing, children });
const textRun = (text, opts = {}) => new TextRun(isPlaceholder(text)
  ? { text, ...opts, shading: { type: ShadingType.CLEAR, color: "auto", fill: "FFFF00" } } : { text, ...opts });
const border = { style: BorderStyle.SINGLE, size: 4, color: "A6A6A6" };
const borders = { top: border, bottom: border, left: border, right: border };

function docxTable(n) {
  const widths = n.widths.map((p) => Math.round((TEXT_W * p) / 100));
  widths[widths.length - 1] = TEXT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (text, i, header) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA }, borders,
    shading: header ? { type: ShadingType.CLEAR, color: "auto", fill: HEADER_FILL } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 }, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { after: 0, line: 252 },
      alignment: n.align[i] === "r" ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: runs(String(text), { size: 19, bold: header || undefined }) })],
  });
  return new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: n.headers.map((h, i) => cell(h, i, true)) }),
           ...n.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) }))],
  });
}

function docxTitle(n) {
  const [uni, inst, campus] = n.institution;
  return [
    centered([textRun(uni, { size: 28, bold: true })], { before: 900, after: 60 }),
    centered([textRun(inst, { size: 26 })], { after: 60 }),
    centered([textRun(campus, { size: 28, bold: true })], { after: 700 }),
    centered([textRun(n.pre, { size: 26 })], { after: 160 }),
    ...n.title.map((t, i) => centered([textRun(t, { bold: true, size: 40, color: ACCENT })],
      { after: i === n.title.length - 1 ? 300 : 120 })),
    centered([textRun(n.tools, { size: 24, italics: true })], { after: 400 }),
    centered(runs(n.course.replace("Big Data Technology", "**Big Data Technology**"), { size: 26 }), { after: 700 }),
    centered([textRun("Submitted by", { size: 24, bold: true })], { after: 120 }),
    ...n.by.map((t, i) => centered([textRun(t, { size: 24 })], { after: i === n.by.length - 1 ? 500 : 60 })),
    centered([textRun("Submitted to", { size: 24, bold: true })], { after: 120 }),
    centered([textRun(n.to, { size: 24 })], { after: 500 }),
    centered([textRun(n.date, { size: 24 })]),
  ];
}

function docxNode(n) {
  switch (n.t) {
    case "title": return docxTitle(n);
    case "p": return [new Paragraph({ children: runs(n.text), spacing: { after: 120, line: 360 },
      alignment: n.center ? AlignmentType.CENTER : AlignmentType.JUSTIFIED })];
    case "h1": return [new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(n.text)], pageBreakBefore: n.pageBreak,
      alignment: n.fm ? AlignmentType.CENTER : undefined })];
    case "fmtitle": return [new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 240 },
      children: [new TextRun({ text: n.text, bold: true, size: 32 })] })];
    case "h2": return [new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, children: [new TextRun(n.text)] })];
    case "h3": return [new Paragraph({ heading: HeadingLevel.HEADING_3, keepNext: true, children: [new TextRun(n.text)] })];
    case "bullet": return [new Paragraph({ numbering: { reference: "bullets", level: n.level }, children: runs(n.text),
      spacing: { after: 60, line: 312 } })];
    case "num": return [new Paragraph({ numbering: { reference: n.ref, level: 0 }, children: runs(n.text),
      spacing: { after: 60, line: 312 } })];
    case "code": return n.lines.map((l, i) => new Paragraph({
      children: [new TextRun({ text: l || " ", font: MONO, size: 18 })],
      shading: { type: ShadingType.CLEAR, color: "auto", fill: CODE_FILL },
      spacing: { before: i === 0 ? 60 : 0, after: i === n.lines.length - 1 ? 160 : 0, line: 240 },
      indent: { left: 120, right: 120 } }));
    case "caption": return [new Paragraph({ style: `${n.kind}Caption`, alignment: AlignmentType.CENTER, keepNext: n.kind === "Table",
      spacing: n.kind === "Table" ? { before: 220, after: 80 } : { before: 60, after: 200 },
      children: [new TextRun({ text: `${n.kind} ${n.n}: `, bold: true, size: 22 }),
                 new TextRun({ text: n.text, size: 22 })] })];
    case "table": return [docxTable(n)];
    case "img": return [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: IMG(n.file), transformation: { width: n.w, height: n.h },
        altText: { title: n.alt, description: n.alt, name: n.file } })] })];
    case "pagebreak": return [new Paragraph({ children: [new PageBreak()] })];
    case "spacer": return [new Paragraph({ spacing: { after: 120 }, children: [] })];
    // Word fields; their entries and page numbers are filled in by fillDocxLists() after packing
    case "toc": return [new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-2" })];
    case "lof": return [new TableOfContents("List of Figures", { hyperlink: true, stylesWithLevels: [new StyleLevel("Figure Caption", 1)] })];
    case "lot": return [new TableOfContents("List of Tables", { hyperlink: true, stylesWithLevels: [new StyleLevel("Table Caption", 1)] })];
    default: throw new Error(`unknown node ${n.t}`);
  }
}
const toDocx = (nodes) => nodes.flatMap(docxNode);

const margin = { top: MARGIN, bottom: MARGIN, left: MARGIN_L, right: MARGIN };
const portrait = { size: { width: PAGE_W, height: PAGE_H }, margin };
const landscape = { size: { width: PAGE_W, height: PAGE_H, orientation: PageOrientation.LANDSCAPE },
  margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } };
const footer = () => new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
  children: [new TextRun({ children: [PageNumber.CURRENT], size: 22 })] })] });
const noFooter = () => new Footer({ children: [new Paragraph({ children: [] })] });
// a section always starts on a new page, so its first heading needs no extra page break
const sectionStart = (nodes) => nodes.map((n, i) => (i === 0 && n.t === "h1" ? { ...n, pageBreak: false } : n));

const doc = new Document({
  creator: "Santosh Tiwari, Arbind Sah",
  title: "Real-Time and Historical Analytics of NEPSE using a Big Data Stack",
  description: "Big Data Technology project report, Pulchowk Campus: Kafka, Spark, HDFS",
  features: { updateFields: true },
  styles: {
    default: {
      document: { run: { font: FONT, size: 24 } },
      heading1: { run: { font: FONT, size: 32, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 120, after: 280 }, keepNext: true, outlineLevel: 0 } },
      heading2: { run: { font: FONT, size: 28, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 300, after: 120 }, keepNext: true, outlineLevel: 1 } },
      heading3: { run: { font: FONT, size: 24, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 220, after: 80 }, keepNext: true, outlineLevel: 2 } },
    },
    paragraphStyles: ["Figure", "Table"].map((kind) => ({ id: `${kind}Caption`, name: `${kind} Caption`,
      basedOn: "Normal", next: "Normal", quickFormat: true, paragraph: { alignment: AlignmentType.CENTER } })),
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 270 } } } }] },
      ...["steps", "flow", "clean", "demo", "refs"].map((ref) => ({ reference: ref, levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: ref === "refs" ? "[%1]" : "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 540, hanging: 400 } } } }] })),
    ],
  },
  sections: [
    // cover (counted as page i, not printed) and front matter: roman page numbers
    { properties: { titlePage: true, page: { ...portrait, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } },
      footers: { default: footer(), first: noFooter() }, children: toDocx(front) },
    // chapters: arabic page numbers from 1
    { properties: { page: { ...portrait, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
      footers: { default: footer() }, children: toDocx(sectionStart(partA)) },
    { properties: { page: landscape }, footers: { default: footer() }, children: toDocx(partB) },
    { properties: { page: portrait }, footers: { default: footer() }, children: toDocx(partC) },
  ],
});

// ═════════════════════════════ HTML renderer ═════════════════════════════
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const inline = (text) => esc(text)
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  .replace(/`([^`]+)`/g, "<code>$1</code>")
  .replace(/(https?:\/\/[^\s<]+[^\s<.,)])/g, '<a href="$1">$1</a>');
const ph = (text) => (isPlaceholder(text) ? `<mark>${esc(text)}</mark>` : esc(text));
const slug = (t) => "s-" + t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const dataUri = (file) => `data:image/png;base64,${IMG(file).toString("base64")}`;

function htmlTitle(n) {
  const [uni, inst, campus] = n.institution;
  return `<section class="cover">
  <div class="inst"><div class="uni">${esc(uni)}</div><div>${esc(inst)}</div><div class="campus">${esc(campus)}</div></div>
  <div class="pre">${esc(n.pre)}</div>
  <h1 class="title">${n.title.map(esc).join(" <br>")}</h1>
  <div class="tools">${esc(n.tools)}</div>
  <div class="course">${inline(n.course.replace("Big Data Technology", "**Big Data Technology**"))}</div>
  <div class="who"><div class="label">Submitted by</div>${n.by.map((b) => `<div>${esc(b)}</div>`).join("")}</div>
  <div class="who"><div class="label">Submitted to</div><div>${ph(n.to)}</div></div>
  <div class="date">${ph(n.date)}</div>
</section>`;
}

function htmlTable(n) {
  const cols = n.widths.map((w) => `<col style="width:${w}%">`).join("");
  const cell = (tag, v, i) => `<${tag}${n.align[i] === "r" ? ' class="r"' : ""}>${inline(String(v))}</${tag}>`;
  return `<div class="tbl"><table><colgroup>${cols}</colgroup>
<thead><tr>${n.headers.map((h, i) => cell("th", h, i)).join("")}</tr></thead>
<tbody>${n.rows.map((r) => `<tr>${r.map((v, i) => cell("td", v, i)).join("")}</tr>`).join("\n")}</tbody></table></div>`;
}

const capId = (n) => `${n.kind.toLowerCase()}-${n.n}`;
const markerTag = (id) => `QQ${id}QQ`;                     // invisible text that pass 1 finds with pdftotext

// ctx: { headings, figures, tables } for the contents lists; print: { pages: {id: label} | null, markers }
function toHtml(nodes, ctx, print = null) {
  const out = [];
  const mk = (id) => (print && print.markers ? `<span class="mk">${markerTag(id)}</span>` : "");
  const pg = (id) => (print ? `<span class="dots"></span><span class="pg">${esc((print.pages && print.pages[id]) || "000")}</span>` : "");
  const entryList = (cls, items) => `<nav class="toc ${cls}"><ol>${items.map((it) =>
    `<li class="${it.cls}"><a href="#${it.id}"><span class="t">${it.label}</span>${pg(it.id)}</a></li>`).join("")}</ol></nav>`;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.t === "bullet" || n.t === "num") {            // group consecutive list items
      const items = [];
      while (i < nodes.length && nodes[i].t === n.t && (n.t === "bullet" || nodes[i].ref === n.ref)) items.push(nodes[i++]);
      i--;
      out.push(n.t === "bullet"
        ? `<ul>${items.map((it) => `<li class="l${it.level}">${inline(it.text)}</li>`).join("")}</ul>`
        : `<ol class="${n.ref === "refs" ? "refs" : ""}">${items.map((it) => `<li>${inline(it.text)}</li>`).join("")}</ol>`);
      continue;
    }
    switch (n.t) {
      case "title": out.push(htmlTitle(n)); break;
      case "p": out.push(`<p${n.center ? ' class="c"' : ""}>${inline(n.text)}</p>`); break;
      case "h1": {
        const cls = [n.pageBreak && "chapter", n.fm && "fm"].filter(Boolean).join(" ");
        out.push(`<h1 id="${slug(n.text)}"${cls ? ` class="${cls}"` : ""}>${mk(slug(n.text))}${esc(n.text)}</h1>`); break;
      }
      case "fmtitle": out.push(`<h1 class="fm">${esc(n.text)}</h1>`); break;
      case "h2": out.push(`<h2 id="${slug(n.text)}">${mk(slug(n.text))}${esc(n.text)}</h2>`); break;
      case "h3": out.push(`<h3>${esc(n.text)}</h3>`); break;
      case "code": {                                       // in print, shrink wide blocks to fit instead of wrapping
        const longest = Math.max(...n.lines.map((l) => l.length));
        const size = print ? Math.max(7, Math.min(9, Math.floor((PRINT_TEXT_PT - 18) / (longest * 0.6) * 10) / 10)) : 0;
        out.push(`<pre${size ? ` style="font-size:${size}pt"` : ""}><code>${esc(n.lines.join("\n"))}</code></pre>`); break;
      }
      case "caption": out.push(`<p class="caption ${n.kind.toLowerCase()}" id="${capId(n)}">${mk(capId(n))}<b>${n.kind} ${n.n}:</b> <i>${esc(n.text)}</i></p>`); break;
      case "table": out.push(htmlTable(n)); break;
      case "img": {
        const wide = n.file === "architecture.png";
        if (print) {                                       // keep a figure and its caption on one page
          const cap = nodes[i + 1] && nodes[i + 1].t === "caption" ? nodes[++i] : null;
          out.push(`<figure><img src="${dataUri(n.file)}" alt="${esc(n.alt)}" style="width:${n.w}px">${cap
            ? `<figcaption class="caption figure" id="${capId(cap)}">${mk(capId(cap))}<b>${cap.kind} ${cap.n}:</b> ${esc(cap.text)}</figcaption>` : ""}</figure>`);
          break;
        }
        const maxW = wide ? 1400 : Math.round(n.w * 1.5);
        out.push(`<div class="fig${wide ? " wide" : ""}"><img src="${dataUri(n.file)}" alt="${esc(n.alt)}" style="max-width:min(100%,${maxW}px)" loading="lazy" title="Click to enlarge"></div>`);
        break;
      }
      case "toc": out.push(entryList("contents", ctx.headings.map((h) => ({ id: slug(h.text), cls: h.t, label: esc(h.text) })))); break;
      case "lof": case "lot": out.push(entryList("captions", (n.t === "lof" ? ctx.figures : ctx.tables).map((c) =>
        ({ id: capId(c), cls: "cap", label: `${c.kind} ${c.n}: ${esc(c.text)}` })))); break;
      case "pagebreak": if (print) out.push('<div class="pb"></div>'); break;
      case "spacer": break;
      default: throw new Error(`unknown node ${n.t}`);
    }
  }
  return out.join("\n");
}

const CSS = `
:root { --ink:#1a1a1a; --muted:#5f6368; --accent:#1F4E79; --line:#A6A6A6; --head:#DCE6F1; --code:#F2F2F2;
        --code-inline:#eef1f4; --paper:#ffffff; --desk:#e9ecf1; --mark:#fff176; --mark-ink:#1a1a1a;
        --side:#f7f8fa; --side-line:#d9dde3; --side-ink:#33393f; --side-hover:#e3ebf5; --h3:#404040;
        --soft-ink:#333333; --img-line:#e3e5e8; --link:#1f63a8; --shadow:rgba(0,0,0,.08); --overlay:rgba(15,18,24,.86); }
html { scroll-padding-top: 16px; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
body { margin: 0; background: var(--desk); color: var(--ink); text-rendering: optimizeLegibility;
       font: 17px/1.65 Calibri, Carlito, "Segoe UI", system-ui, -apple-system, sans-serif; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr); }
.side { display: none; }
@media (min-width: 1360px) {
  .layout { grid-template-columns: 290px minmax(0, 1fr); }
  .side { display: block; position: sticky; top: env(safe-area-inset-top, 0px); height: 100vh; overflow-y: auto; padding: 28px 18px 28px 26px;
          background: var(--side); border-right: 1px solid var(--side-line); font-size: 14px; line-height: 1.4; }
  .side .h { font-weight: 700; color: var(--accent); margin-bottom: 10px; font-size: 15px; }
  .side a { display: block; color: var(--side-ink); text-decoration: none; padding: 3px 6px; border-radius: 4px; }
  .side a.h2 { padding-left: 20px; color: var(--muted); font-size: 13px; }
  .side a:hover, .side a.on { background: var(--side-hover); color: var(--accent); }
}
main { width: 100%; max-width: 940px; margin: 28px auto 60px; background: var(--paper);
       padding: 64px 72px; box-shadow: 0 2px 14px var(--shadow); border-radius: 4px; min-width: 0; }
@media (max-width: 720px) { main { margin: 0; padding: 24px 16px; border-radius: 0; box-shadow: none; } body { font-size: 16px; } }
h1, h2, h3 { color: var(--accent); line-height: 1.25; text-wrap: balance; }
h1 { font-size: 1.85em; margin: 1.4em 0 .6em; }
h1.chapter { border-top: 3px solid var(--head); padding-top: 1.1em; margin-top: 2.2em; }
h2 { font-size: 1.4em; margin: 1.5em 0 .5em; }
h3 { font-size: 1.12em; color: var(--h3); margin: 1.2em 0 .4em; }
p { margin: 0 0 .75em; text-align: justify; hyphens: auto; }
p.c { text-align: center; }
ul, ol { margin: .2em 0 .9em; padding-left: 1.8em; }
li { margin: .25em 0; }
li.l1 { margin-left: 1.6em; list-style: "– "; }
ol.refs { list-style: none; counter-reset: ref; padding-left: 2.6em; }
ol.refs li { counter-increment: ref; position: relative; overflow-wrap: anywhere; }
ol.refs li::before { content: "[" counter(ref) "]"; position: absolute; left: -2.6em; color: var(--muted); }
code { font-family: Consolas, "DejaVu Sans Mono", Menlo, monospace; font-size: .88em; background: var(--code-inline); padding: .05em .3em; border-radius: 3px; }
pre { background: var(--code); padding: 12px 16px; border-radius: 4px; overflow-x: auto; line-height: 1.45; margin: .3em 0 1em; }
pre code { background: none; padding: 0; font-size: .82em; }
a { color: var(--link); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
mark { background: var(--mark); color: var(--mark-ink); padding: 0 .2em; }
.tbl { overflow-x: auto; margin: .2em 0 1.1em; }
table { width: 100%; border-collapse: collapse; font-size: .9em; line-height: 1.4; }
th, td { border: 1px solid var(--line); padding: 6px 9px; text-align: left; vertical-align: middle; }
th { background: var(--head); font-weight: 700; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; }
.caption { text-align: center; font-size: .92em; margin: .3em 0 1.2em; }
.caption b { color: var(--accent); }
.caption.table { margin: 1.2em 0 .4em; }
.fig { text-align: center; margin: 1em 0 .3em; }
.fig img { width: 100%; height: auto; border: 1px solid var(--img-line); border-radius: 3px; cursor: zoom-in; }
@media (min-width: 1100px) { .fig.wide { margin-left: -60px; margin-right: -60px; } }
.toc ol { list-style: none; padding: 0; margin: 0 0 1em; columns: 1; }
.toc li { margin: .15em 0; }
.toc li.h2 { padding-left: 1.6em; font-size: .95em; }
.toc a { text-decoration: none; color: var(--ink); }
.toc a:hover { color: var(--accent); text-decoration: underline; }
.cover { text-align: center; padding: 30px 0 50px; border-bottom: 3px solid var(--head); margin-bottom: 20px; }
.cover .inst { font-size: 1.15em; line-height: 1.5; }
.cover .uni, .cover .campus { font-weight: 700; }
.cover .pre { margin-top: 48px; font-size: 1.1em; }
.cover h1.title { font-size: 2em; margin: 12px 0 18px; }
.cover .tools { font-style: italic; color: var(--soft-ink); }
.cover .course { margin-top: 30px; font-size: 1.12em; }
.cover .who { margin-top: 34px; font-size: 1.05em; }
.cover .label { font-weight: 700; margin-bottom: 6px; }
.cover .date { margin-top: 30px; }
#lb { position: fixed; inset: 0; background: var(--overlay); display: none; align-items: center; justify-content: center;
      padding: 20px; cursor: zoom-out; z-index: 10; }
#lb.on { display: flex; }
#lb img { max-width: 100%; max-height: 100%; background: var(--paper); border-radius: 4px; }
@media print {
  body { background: var(--paper); font-size: 11pt; }
  .side, #lb { display: none !important; }
  .layout { display: block; }
  main { box-shadow: none; margin: 0; padding: 0; max-width: none; }
  .cover { border: none; page-break-after: always; min-height: 90vh; }
  h1.chapter { page-break-before: always; border: none; padding-top: 0; margin-top: 0; }
  h2, h3, .caption.table { page-break-after: avoid; }
  tr, img, pre { page-break-inside: avoid; }
  .fig.wide { margin: 0; }
}`;

const JS = `
const lb = document.getElementById("lb"), lbImg = lb.querySelector("img");
document.querySelectorAll(".fig img").forEach((img) => img.addEventListener("click", () => {
  lbImg.src = img.src; lbImg.alt = img.alt; lb.classList.add("on"); }));
lb.addEventListener("click", () => lb.classList.remove("on"));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") lb.classList.remove("on"); });
const links = [...document.querySelectorAll(".side a")];
const targets = links.map((a) => document.getElementById(a.hash.slice(1))).filter(Boolean);
const spy = () => {
  let cur = targets[0];
  for (const t of targets) if (t.getBoundingClientRect().top < 120) cur = t;
  links.forEach((a) => a.classList.toggle("on", cur && a.hash === "#" + cur.id));
};
document.addEventListener("scroll", spy, { passive: true }); spy();`;

const allNodes = [...front, ...partA, ...partB, ...partC];
const ctx = {
  headings: allNodes.filter((n) => n.t === "h1" || n.t === "h2"),
  figures: allNodes.filter((n) => n.t === "caption" && n.kind === "Figure"),
  tables: allNodes.filter((n) => n.t === "caption" && n.kind === "Table"),
};

function buildHtml({ artifact = false } = {}) {
  const side = ctx.headings.map((h) => `<a class="${h.t}" href="#${slug(h.text)}">${esc(h.text)}</a>`).join("\n");
  const body = `<div class="layout">
<aside class="side"><div class="h">Contents</div>
${side}
</aside>
<main>
${toHtml(allNodes, ctx)}
</main>
</div>
<div id="lb" role="dialog" aria-label="Enlarged figure"><img alt=""></div>
<script>${JS}</script>`;
  if (artifact) return `<title>NEPSE Big Data Report</title>\n<style>${CSS}</style>\n${body}\n`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEPSE Big Data Report</title>
<meta name="description" content="Big Data Technology project report (Pulchowk Campus): real-time and historical NEPSE analytics with Kafka, Spark and HDFS — Santosh Tiwari, Arbind Sah">
<style>${CSS}</style>
</head>
<body>
${body}
</body>
</html>
`;
}

// ═════════════════════════════ PDF (print HTML → headless Chrome) ═════════════════════════════
const PRINT_TEXT_PT = (8.27 - 2.5) * 72;                   // A4 width minus the 1.5" + 1" margins
const PRINT_CSS = `
@page { size: A4; margin: 1in 1in 1in 1.5in; }
@page wide { size: A4 landscape; margin: 0.9in 1in; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: #000; background: #fff; font: 12pt/1.5 "Times New Roman", "Liberation Serif", Tinos, serif;
       font-kerning: normal; text-rendering: optimizeLegibility; }
.pb { break-after: page; }
.mk { position: absolute; font-size: 3pt; color: #fff; white-space: nowrap; }
.landscape { page: wide; }
h1, h2, h3 { font-weight: 700; line-height: 1.3; break-after: avoid; }
h1 { font-size: 16pt; margin: 0 0 16pt; }
h1.chapter { break-before: page; }
h1.fm { text-align: center; margin-bottom: 20pt; }
h2 { font-size: 14pt; margin: 16pt 0 6pt; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; }
p { margin: 0 0 8pt; text-align: justify; hyphens: auto; orphans: 2; widows: 2; }
p.c { text-align: center; }
ul, ol { margin: 0 0 8pt; padding-left: 1.6em; }
li { margin: 0 0 3pt; text-align: justify; }
li.l1 { margin-left: 1.6em; list-style: "– "; }
ol.refs { list-style: none; counter-reset: ref; padding-left: 2.4em; }
ol.refs li { counter-increment: ref; position: relative; text-align: left; overflow-wrap: anywhere; }
ol.refs li::before { content: "[" counter(ref) "]"; position: absolute; left: -2.4em; }
code { font-family: "Liberation Mono", "DejaVu Sans Mono", Consolas, monospace; font-size: 10pt; }
pre { background: #f2f2f2; border: 0.75pt solid #d0d0d0; padding: 6pt 8pt; margin: 4pt 0 10pt; font-size: 9pt;
      line-height: 1.35; white-space: pre-wrap; break-inside: avoid; }
pre code { font-size: inherit; }
a { color: inherit; text-decoration: none; }
mark { background: #fff176; }
.tbl { margin: 0 0 12pt; }
table { width: 100%; border-collapse: collapse; font-size: 10.5pt; line-height: 1.3; }
th, td { border: 0.75pt solid #808080; padding: 3pt 5pt; text-align: left; vertical-align: top; overflow-wrap: break-word; }
th { background: #DCE6F1; vertical-align: middle; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
td.r, th.r { text-align: right; font-variant-numeric: tabular-nums; }
.caption { text-align: center; font-size: 11pt; margin: 4pt 0 10pt; }
.caption i { font-style: normal; }
.caption.table { margin: 12pt 0 4pt; break-after: avoid; }
figure { margin: 10pt 0 12pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; height: auto; border: 0.5pt solid #bfbfbf; }
figcaption { margin-top: 6pt; }
.toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { margin: 0 0 3pt; text-align: left; }
.toc a { display: flex; align-items: baseline; }
.toc .dots { flex: 1 1 auto; min-width: 14pt; margin: 0 4pt; border-bottom: 1.2pt dotted #000; transform: translateY(-3pt); }
.toc .pg { flex: none; min-width: 1.8em; text-align: right; }
.toc.contents li.h1 { font-weight: 700; margin-top: 7pt; }
.toc.contents li.h2 { padding-left: 1.6em; }
.toc.captions li { margin-bottom: 6pt; }
.cover { height: 9.5in; display: flex; flex-direction: column; text-align: center; }
.cover .inst { font-size: 15pt; line-height: 1.5; }
.cover .uni, .cover .campus { font-weight: 700; }
.cover .pre { margin-top: 1.1in; font-size: 13pt; font-style: italic; }
.cover h1.title { font-size: 20pt; line-height: 1.35; margin: 12pt 0 14pt; text-wrap: balance; }
.cover h1.title br { display: none; }
.cover .tools { font-style: italic; }
.cover .course { margin-top: 0.7in; font-size: 13pt; }
.cover .who { margin-top: 0.5in; }
.cover .label { font-weight: 700; margin-bottom: 4pt; }
.cover .date { margin-top: auto; font-size: 13pt; }`;

function buildPrintHtml(print) {
  const part = (nodes) => toHtml(nodes, ctx, print);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Real-Time and Historical Analytics of NEPSE using a Big Data Stack</title>
<style>${PRINT_CSS}</style>
</head>
<body>
${part(front)}
${part(partA)}
<section class="landscape">
${part(partB)}
</section>
${part(partC)}
</body>
</html>
`;
}

const roman = (n) => [[10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]]
  .reduce((acc, [v, r]) => { while (n >= v) { acc += r; n -= v; } return acc; }, "");
const which = (cmd) => { try { return execFileSync("sh", ["-c", `command -v ${cmd}`]).toString().trim(); } catch { return null; } };

function chromePdf(html, pdfFile, tmp) {
  const chrome = process.env.CHROME || ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"].map(which).find(Boolean);
  if (!chrome) throw new Error("Google Chrome or Chromium not found (set CHROME=/path/to/chrome)");
  const htmlFile = path.join(tmp, "print.html");
  fs.writeFileSync(htmlFile, html);
  execFileSync(chrome, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${path.join(tmp, "profile")}`, "--no-pdf-header-footer", "--generate-pdf-document-outline",
    `--print-to-pdf=${pdfFile}`, `file://${htmlFile}`], { stdio: "pipe" });
}
const pdfText = (pdfFile) => execFileSync("pdftotext", ["-enc", "UTF-8", pdfFile, "-"]).toString().split("\f").slice(0, -1);

// Returns the page label ("iv", "12") of every heading and caption, or null when the PDF cannot be built.
async function buildPdf() {
  if (!which("pdftotext")) throw new Error("pdftotext not found (install poppler-utils)");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nepse-report-"));
  try {
    // pass 1: find the physical page of every marker
    const pass1 = path.join(tmp, "pass1.pdf");
    chromePdf(buildPrintHtml({ pages: null, markers: true }), pass1, tmp);
    const phys = {};
    pdfText(pass1).forEach((text, i) => {
      for (const m of text.matchAll(/QQ([a-z0-9-]+)QQ/g)) if (!(m[1] in phys)) phys[m[1]] = i + 1;
    });
    const bodyStart = phys[slug(partA[0].text)];
    const label = (p) => (p < bodyStart ? roman(p) : String(p - bodyStart + 1));
    const pages = Object.fromEntries(Object.entries(phys).map(([id, p]) => [id, label(p)]));
    const missing = [...ctx.headings.map((h) => slug(h.text)), ...[...ctx.figures, ...ctx.tables].map(capId)].filter((id) => !pages[id]);
    if (missing.length) throw new Error(`page not found for ${missing.join(", ")}`);

    // pass 2: the same layout without markers, with the page numbers filled in
    const pass2 = path.join(tmp, "pass2.pdf");
    chromePdf(buildPrintHtml({ pages, markers: false }), pass2, tmp);
    const text = pdfText(pass2);
    const norm = (t) => t.replace(/\s+/g, "");
    for (const h of ctx.headings) {
      if (!norm(text[phys[slug(h.text)] - 1] || "").includes(norm(h.text))) console.warn(`warning: "${h.text}" moved off page ${pages[slug(h.text)]}`);
    }

    // page numbers in the footer (none on the cover), document properties
    const { PDFDocument, StandardFonts } = require("pdf-lib");
    const pdf = await PDFDocument.load(fs.readFileSync(pass2));
    const font = await pdf.embedFont(StandardFonts.TimesRoman);
    pdf.getPages().forEach((page, i) => {
      if (i === 0) return;
      const s = label(i + 1), size = 11;
      page.drawText(s, { x: (page.getWidth() - font.widthOfTextAtSize(s, size)) / 2, y: 36, size, font });
    });
    pdf.setTitle("Real-Time and Historical Analytics of the Nepal Stock Exchange (NEPSE) using a Big Data Stack", { showInWindowTitleBar: true });
    pdf.setAuthor("Santosh Tiwari (082MSDSA024), Arbind Sah (082MSDSA006)");
    pdf.setSubject("Big Data Technology project report, Institute of Engineering, Pulchowk Campus");
    pdf.setKeywords(["big data", "Apache Kafka", "Apache Spark", "HDFS", "NEPSE", "Lambda architecture"]);
    pdf.setCreator("report/build.js");
    const out = await pdf.save();
    fs.writeFileSync(`${BASE}.pdf`, out);
    console.log(`wrote ${BASE}.pdf (${(out.length / 1024).toFixed(0)} KB, ${pdf.getPageCount()} pages)`);
    return pages;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

// ═════════════════════════════ Word: cached contents entries ═════════════════════════════
// The docx library writes the three lists as empty Word fields. Fill each with its entries and page numbers
// so the lists show in every viewer (LibreOffice, Google Docs, WPS); Word recomputes them when it opens the file.
const xmlEsc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
async function fillDocxLists(buf, pages) {
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(buf);
  let xml = await zip.file("word/document.xml").async("string");
  const lists = {
    "Table of Contents": ctx.headings.map((h) => ({ text: h.text, id: slug(h.text), level: h.t === "h1" ? 1 : 2 })),
    "List of Figures": ctx.figures.map((c) => ({ text: `${c.kind} ${c.n}: ${c.text}`, id: capId(c), level: 0 })),
    "List of Tables": ctx.tables.map((c) => ({ text: `${c.kind} ${c.n}: ${c.text}`, id: capId(c), level: 0 })),
  };
  for (const [alias, entries] of Object.entries(lists)) {
    const re = new RegExp(`(<w:sdt><w:sdtPr><w:alias w:val="${alias}"/></w:sdtPr><w:sdtContent>)([\\s\\S]*?)(</w:sdtContent></w:sdt>)`);
    const m = xml.match(re);
    if (!m) throw new Error(`Word field "${alias}" not found`);
    const begin = m[2].match(/<w:r><w:fldChar w:fldCharType="begin"[\s\S]*?w:fldCharType="separate"\/><\/w:r>/)[0];
    const paras = entries.map((e, i) => {
      const indent = e.level === 2 ? 440 : 0;
      const spacing = e.level === 1 ? 'w:before="120" w:after="40"' : e.level === 2 ? 'w:after="40"' : 'w:after="100"';
      const rPr = e.level === 1 ? "<w:rPr><w:b/><w:bCs/></w:rPr>" : "";
      return `<w:p><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="${TEXT_W}"/></w:tabs>`
        + `<w:spacing ${spacing} w:line="276" w:lineRule="auto"/><w:ind w:left="${indent}" w:right="560"/></w:pPr>`
        + (i === 0 ? begin : "")
        + `<w:r>${rPr}<w:t xml:space="preserve">${xmlEsc(e.text)}</w:t></w:r><w:r>${rPr}<w:tab/></w:r>`
        + `<w:r>${rPr}<w:t>${xmlEsc((pages && pages[e.id]) || "")}</w:t></w:r>`
        + (i === entries.length - 1 ? '<w:r><w:fldChar w:fldCharType="end"/></w:r>' : "")
        + "</w:p>";
    });
    xml = xml.replace(re, (_, a, __, c) => a + paras.join("") + c);
  }
  zip.file("word/document.xml", xml);
  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

// ═════════════════════════════ write all three ═════════════════════════════
(async () => {
  fs.writeFileSync(`${BASE}.html`, buildHtml());
  if (process.env.ARTIFACT_HTML) fs.writeFileSync(process.env.ARTIFACT_HTML, buildHtml({ artifact: true }));  // for publishing
  console.log(`wrote ${BASE}.html (${(fs.statSync(`${BASE}.html`).size / 1024).toFixed(0)} KB)`);
  let pages = null;
  try { pages = await buildPdf(); } catch (e) { console.warn(`PDF skipped: ${e.message}`); }
  const buf = await fillDocxLists(await Packer.toBuffer(doc), pages);
  fs.writeFileSync(`${BASE}.docx`, buf);
  console.log(`wrote ${BASE}.docx (${(buf.length / 1024).toFixed(0)} KB)`);
})().catch((e) => { console.error(e); process.exit(1); });
