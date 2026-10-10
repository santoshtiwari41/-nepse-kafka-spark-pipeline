"""Data access for the dashboard.

Serving layer:
  Kafka  nepse.analytics  latest state per symbol (from Spark streaming)  → live view
  Kafka  nepse.alerts     alerts (from Spark streaming)                    → alerts feed
  HDFS   /nepse/gold/*    batch + streaming Parquet outputs, read over WebHDFS
"""
import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

import fsspec
import pandas as pd
import pyarrow.dataset as ds
import streamlit as st
from kafka import KafkaConsumer, TopicPartition

KAFKA = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
WEBHDFS_HOST = os.getenv("WEBHDFS_HOST", "namenode")
WEBHDFS_PORT = int(os.getenv("WEBHDFS_PORT", "9870"))
LAKE = "/nepse"
STREAM_IDLE_SECONDS = 90   # no stream update for this long ⇒ show HISTORICAL mode
NPT = ZoneInfo("Asia/Kathmandu")


# ───────────────────────── HDFS (WebHDFS) ─────────────────────────

@st.cache_resource
def hdfs():
    return fsspec.filesystem("webhdfs", host=WEBHDFS_HOST, port=WEBHDFS_PORT, user="spark")


def read_parquet(path, columns=None, filter=None) -> pd.DataFrame:
    """Read a (possibly hive-partitioned) Parquet directory from HDFS; empty if missing."""
    fs = hdfs()
    if not fs.exists(path):
        return pd.DataFrame(columns=columns or [])
    dataset = ds.dataset(path, filesystem=fs, format="parquet", partitioning="hive")
    if not dataset.files:          # e.g. a streaming output whose first files aren't written yet
        return pd.DataFrame(columns=columns or [])
    return dataset.to_table(columns=columns, filter=filter).to_pandas()


@st.cache_data(ttl=600, show_spinner="Reading latest snapshot from HDFS…")
def latest_snapshot():
    return read_parquet(f"{LAKE}/gold/latest_snapshot")


PRICE_COLS = ["date", "adj_open", "adj_high", "adj_low", "adj_close", "volume", "turnover",
              "sma_20", "sma_50", "sma_200", "bb_upper", "bb_lower", "rsi_14",
              "corporate_action", "open", "close", "prev_close"]


@st.cache_data(ttl=600, show_spinner="Reading price history from HDFS…")
def price_history(symbol):
    df = read_parquet(f"{LAKE}/gold/indicators", PRICE_COLS, ds.field("symbol") == symbol)
    return df.sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner="Reading market data from HDFS…")
def market_daily():
    return read_parquet(f"{LAKE}/gold/market_daily").sort_values("date")


@st.cache_data(ttl=600)
def sector_daily():
    return read_parquet(f"{LAKE}/gold/sector_daily")


@st.cache_data(ttl=600)
def data_quality():
    return read_parquet(f"{LAKE}/gold/data_quality")


@st.cache_data(ttl=600)
def ml_results():
    """MLlib output: (metrics dict, feature importances, latest-day predictions)."""
    metrics = read_parquet(f"{LAKE}/gold/ml_metrics")
    return (dict(zip(metrics["metric"], metrics["value"])) if not metrics.empty else {},
            read_parquet(f"{LAKE}/gold/ml_features"),
            read_parquet(f"{LAKE}/gold/ml_predictions"))


@st.cache_data(ttl=15)
def intraday_candles(symbol, session_start):
    """1-minute candles of one symbol since the session started (excludes earlier replay loops)."""
    start = pd.Timestamp(session_start).tz_convert(NPT).tz_localize(None)
    df = read_parquet(f"{LAKE}/gold/candles_1m",
                      filter=(ds.field("trade_date") == str(start.date())) & (ds.field("symbol") == symbol))
    for col in ["window_start", "window_end"]:     # Spark stores UTC instants → show Nepal time
        ts = pd.to_datetime(df[col])
        ts = ts.dt.tz_localize("UTC") if ts.dt.tz is None else ts
        df[col] = ts.dt.tz_convert(NPT).dt.tz_localize(None)
    return df[df["window_end"] > start].sort_values("window_start")


@st.cache_data(ttl=60)
def hdfs_usage():
    fs = hdfs()
    rows = []
    for layer in ["bronze", "silver", "gold"]:
        for path in fs.ls(f"{LAKE}/{layer}", detail=False):
            rows.append({"layer": layer, "dataset": path.rsplit("/", 1)[-1],
                         "size_mb": round(fs.du(path) / 1e6, 2)})
    return pd.DataFrame(rows)


# ───────────────────────── Kafka (live serving layer) ─────────────────────────

class LiveFeed:
    """Background consumer keeping the latest market state in memory."""

    def __init__(self):
        self.lock = threading.Lock()
        self.snapshot: dict[str, dict] = {}
        self.session = ""          # session_start of the newest stream session
        self.session_date = None
        self.alerts: deque = deque(maxlen=300)
        self.last_update = 0.0
        self.error = None
        self.ready = False         # True once the backlog in Kafka has been read
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                consumer = KafkaConsumer(bootstrap_servers=KAFKA, consumer_timeout_ms=1000,
                                         max_partition_fetch_bytes=16 * 1024 * 1024,
                                         fetch_max_bytes=64 * 1024 * 1024,
                                         value_deserializer=lambda v: json.loads(v))
                parts = [TopicPartition(t, p) for t in ["nepse.analytics", "nepse.alerts"]
                         for p in consumer.partitions_for_topic(t) or []]
                consumer.assign(parts)
                consumer.seek_to_beginning(*parts)
                self.error = None
                while True:
                    for msg in consumer:
                        self._handle(msg.topic, msg.value)
                    self.ready = True      # iterator timed out → caught up with the topic
            except Exception as exc:          # Kafka not up yet → retry
                self.error = str(exc)
                time.sleep(5)

    def _handle(self, topic, value):
        with self.lock:
            if topic == "nepse.alerts":
                self.alerts.appendleft(value)
                return
            session = value.get("session_start") or ""   # messages from older versions have none
            if session > self.session:                     # a new session (next day / next replay loop)
                self.session, self.session_date, self.snapshot = session, value.get("session_date"), {}
            if session == self.session:
                self.snapshot[value["symbol"]] = value
                # when Spark produced it (not when we read it) — old messages replayed
                # at dashboard start-up must not look like an active stream
                processed = datetime.fromisoformat(value["processed_at"]).timestamp()
                self.last_update = max(self.last_update, processed)

    def state(self):
        with self.lock:
            snap = pd.DataFrame(list(self.snapshot.values()))
            alerts = pd.DataFrame([a for a in self.alerts if a.get("session_start") == self.session])
            age = time.time() - self.last_update if self.last_update else None
            session, session_date = self.session, self.session_date
        mode = "HISTORICAL"
        if age is not None and age < STREAM_IDLE_SECONDS and not snap.empty:
            mode = snap["mode"].mode().iat[0]
        return snap, alerts, mode, age, session, session_date

    def topic_offsets(self):
        consumer = KafkaConsumer(bootstrap_servers=KAFKA)
        rows = []
        for topic in ["nepse.ticks", "nepse.analytics", "nepse.alerts"]:
            parts = [TopicPartition(topic, p) for p in consumer.partitions_for_topic(topic) or []]
            end, start = consumer.end_offsets(parts), consumer.beginning_offsets(parts)
            rows.append({"topic": topic, "partitions": len(parts),
                         "messages retained": sum(end[p] - start[p] for p in parts)})
        consumer.close()
        return pd.DataFrame(rows)


@st.cache_resource
def live_feed():
    return LiveFeed()


def fmt_age(seconds):
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    return datetime.fromtimestamp(time.time() - seconds, NPT).strftime("%Y-%m-%d %H:%M NPT")
