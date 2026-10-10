"""Shared paths, settings and the tick schema used by every producer.

A *tick* is one price update for one symbol. LIVE and REPLAY producers both
emit exactly this shape to Kafka, so Spark never needs to know which mode is
running — only the `mode` field differs.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORICAL = DATA / "historical"
PRICES_DIR = HISTORICAL / "prices"        # one CSV per symbol (daily OHLCV)
INDEX_DIR = HISTORICAL / "index"          # NEPSE index history
REFERENCE_DIR = DATA / "reference"        # company master (symbol → sector)
RECORDINGS = DATA / "recordings"          # recorded live sessions (JSONL)
SAMPLE = DATA / "sample"                  # small offline dataset committed to git

NPT = ZoneInfo("Asia/Kathmandu")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9094")
TICKS_TOPIC = os.getenv("TICKS_TOPIC", "nepse.ticks")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
}

# Normalised daily-history columns written by fetch_history.py
HISTORY_COLUMNS = ["date", "symbol", "open", "high", "low", "close",
                   "volume", "turnover", "change_pct"]

# Tick fields (JSON message value on nepse.ticks, key = symbol)
TICK_FIELDS = [
    "symbol",       # NABIL
    "ts",           # event time, ISO-8601 with +05:45 offset
    "ltp",          # last traded price
    "open", "high", "low", "prev_close",
    "volume",       # cumulative shares traded today
    "turnover",     # cumulative NPR traded today (None if source lacks it)
    "last_qty",     # quantity of the last trade (None if unknown)
    "change_pct",
    "source",       # nepse-api | sharesansar | recording | historical
    "mode",         # LIVE | REPLAY
]


def now_npt() -> datetime:
    return datetime.now(NPT)


def make_tick(**fields) -> dict:
    """Build a tick with every schema field present (missing ones → None)."""
    unknown = set(fields) - set(TICK_FIELDS)
    if unknown:
        raise ValueError(f"unknown tick fields: {unknown}")
    return {f: fields.get(f) for f in TICK_FIELDS}


def kafka_producer():
    from kafka import KafkaProducer
    return KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, linger_ms=50, acks=1)


def send_tick(producer, topic: str, tick: dict):
    """Publish a tick as JSON, keyed by symbol (same symbol → same partition)."""
    producer.send(topic, key=tick["symbol"].encode(), value=json.dumps(tick).encode())
