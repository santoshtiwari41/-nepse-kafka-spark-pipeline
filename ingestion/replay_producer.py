"""REPLAY mode: stream a past trading day into Kafka as if it were live.

Two sources:
  recording   a session recorded by live_producer.py (data/recordings/<date>.jsonl)
              → real intraday ticks, replayed with their original spacing
  historical  daily OHLCV from data/historical (or data/sample when offline)
              → intraday ticks are simulated: a random price path from open to
                close that touches the day's high and low, with the day's volume
                split across trades. Reproducible (seeded by symbol + date).

Timestamps are shifted to "now" and compressed by --speed, so a 4-hour session
at 60x plays in 4 minutes and Spark's 1-minute windows each hold an hour of
trading. Every message has mode=REPLAY.

    python ingestion/replay_producer.py --list
    python ingestion/replay_producer.py --source historical                 # latest trading day
    python ingestion/replay_producer.py --source historical --date 2026-10-09 --speed 120 --loop
    python ingestion/replay_producer.py --source recording --date 2026-10-09
"""
import argparse
import json
import random
import time
from datetime import datetime, timedelta

import pandas as pd

from common import (HISTORICAL, NPT, RECORDINGS, SAMPLE, TICKS_TOPIC,
                    kafka_producer, make_tick, now_npt, send_tick)

MARKET_OPEN, MARKET_CLOSE = (11, 0), (15, 0)


# ───────────────────────── sources ─────────────────────────

def history_dir():
    """Full history if downloaded, otherwise the committed offline sample."""
    full = HISTORICAL / "prices"
    return full if any(full.glob("*.csv")) else SAMPLE / "prices"


def load_history(symbols=None) -> pd.DataFrame:
    files = sorted(history_dir().glob("*.csv"))
    if symbols:
        files = [f for f in files if f.stem in symbols]
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def recording_ticks(date: str) -> list[dict]:
    path = RECORDINGS / f"{date}.jsonl"
    if not path.exists():
        raise SystemExit(f"No recording for {date}. Available: {available_recordings() or 'none'}")
    with path.open() as f:
        ticks = [json.loads(line) for line in f]
    for t in ticks:
        t["source"] = "recording"
    return sorted(ticks, key=lambda t: t["ts"])


def historical_ticks(date: str, symbols=None) -> list[dict]:
    history = load_history(symbols).sort_values(["symbol", "date"])
    history["prev_close"] = history.groupby("symbol")["close"].shift()
    day = history[(history["date"] == date) & (history["volume"] > 0)].dropna(subset=["open", "close"])
    if day.empty:
        raise SystemExit(f"No trading data for {date} in {history_dir()}")

    session_start = datetime(*map(int, date.split("-")), *MARKET_OPEN, tzinfo=NPT)
    ticks = []
    for row in day.itertuples():
        ticks.extend(simulate_day(row, session_start))
    return sorted(ticks, key=lambda t: t["ts"])


def simulate_day(row, session_start: datetime) -> list[dict]:
    """Synthesise intraday trades consistent with one day's OHLCV."""
    rng = random.Random(f"{row.symbol}-{row.date}")
    session_secs = (MARKET_CLOSE[0] - MARKET_OPEN[0]) * 3600
    o, h, l, c = row.open, max(row.high, row.open, row.close), min(row.low, row.open, row.close), row.close
    prev = row.prev_close if pd.notna(row.prev_close) else o

    # More trades for heavily traded stocks (10 … 120 per day)
    n = int(min(120, max(10, row.volume ** 0.4)))
    times = sorted(rng.uniform(0, session_secs - 1) for _ in range(n - 1)) + [session_secs]

    # Path: open → (high, low in random order) → close, with noise in between
    first, second = (h, l) if rng.random() < 0.5 else (l, h)
    t1, t2 = sorted(rng.sample(range(1, n - 1), 2)) if n > 3 else (1, 2)
    anchors = [(0, o), (t1, first), (t2, second), (n - 1, c)]

    prices = []
    for (i0, p0), (i1, p1) in zip(anchors, anchors[1:]):
        for i in range(i0, i1):
            base = p0 + (p1 - p0) * (i - i0) / (i1 - i0)
            prices.append(base + rng.gauss(0, (h - l) * 0.08))
    prices.append(c)
    prices = [min(h, max(l, round(p, 1))) for p in prices]
    for i, p in anchors[:-1]:
        prices[i] = p  # make sure open/high/low are actually hit

    weights = [rng.expovariate(1) for _ in range(n)]
    qtys = [max(1, round(row.volume * w / sum(weights))) for w in weights]
    qtys[-1] = max(1, int(row.volume) - sum(qtys[:-1]))  # cumulative = day's volume

    ticks, vol, turnover, hi, lo = [], 0, 0.0, prices[0], prices[0]
    for t, p, q in zip(times, prices, qtys):
        vol, turnover, hi, lo = vol + q, turnover + p * q, max(hi, p), min(lo, p)
        ticks.append(make_tick(
            symbol=row.symbol, ts=(session_start + timedelta(seconds=t)).isoformat(timespec="seconds"),
            ltp=p, open=o, high=hi, low=lo, prev_close=prev, volume=vol,
            turnover=round(turnover, 2), last_qty=q,
            change_pct=round((p - prev) / prev * 100, 2), source="historical", mode="REPLAY"))
    return ticks


# ───────────────────────── listing ─────────────────────────

def available_recordings() -> list[str]:
    return sorted(p.stem for p in RECORDINGS.glob("*.jsonl"))


def available_dates() -> list[str]:
    return sorted(pd.read_csv(f, usecols=["date"])["date"].iloc[-1] for f in history_dir().glob("*.csv"))


def latest_trading_day() -> str:
    dates = load_history(["NABIL", "NTC", "NICA"])["date"]  # liquid stocks trade every session
    return dates.max()


# ───────────────────────── replay ─────────────────────────

def replay(ticks: list[dict], speed: float, producer, keep_time: bool) -> int:
    orig_start = datetime.fromisoformat(ticks[0]["ts"])
    wall_start = time.monotonic()
    new_start = now_npt()
    last_report = 0.0

    for i, tick in enumerate(ticks, 1):
        offset = (datetime.fromisoformat(tick["ts"]) - orig_start).total_seconds() / speed
        delay = offset - (time.monotonic() - wall_start)
        if delay > 0:
            time.sleep(delay)

        tick = dict(tick, mode="REPLAY")
        if not keep_time:
            tick["ts"] = (new_start + timedelta(seconds=offset)).isoformat(timespec="seconds")
        if producer:
            send_tick(producer, TICKS_TOPIC, tick)
        else:
            print(json.dumps(tick))

        if time.monotonic() - last_report >= 5 or i == len(ticks):
            last_report = time.monotonic()
            market_clock = orig_start + timedelta(seconds=offset * speed)
            print(f"  market time {market_clock:%H:%M:%S}  sent {i:,}/{len(ticks):,} ticks", flush=True)

    if producer:
        producer.flush()
    return len(ticks)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["historical", "recording"], default="historical")
    parser.add_argument("--date", help="trading day YYYY-MM-DD (default: latest available)")
    parser.add_argument("--symbols", help="comma-separated symbols (historical only; default all)")
    parser.add_argument("--speed", type=float, default=60, help="replay speed multiplier (default 60)")
    parser.add_argument("--loop", action="store_true", help="replay again and again until Ctrl+C")
    parser.add_argument("--keep-time", action="store_true",
                        help="keep original timestamps instead of shifting them to now")
    parser.add_argument("--dry-run", action="store_true", help="print ticks instead of sending")
    parser.add_argument("--list", action="store_true", help="show what can be replayed")
    args = parser.parse_args()

    if args.list:
        dates = available_dates()
        print(f"Historical data ({history_dir()}): latest trading day {latest_trading_day()}"
              f", files end between {dates[0]} and {dates[-1]}")
        print(f"Recordings ({RECORDINGS}): {', '.join(available_recordings()) or 'none yet'}")
        return

    symbols = {s.strip().upper() for s in args.symbols.split(",")} if args.symbols else None
    if args.source == "recording":
        date = args.date or (available_recordings() or [None])[-1]
        if not date:
            raise SystemExit("No recordings yet — use --source historical or record with live_producer.py")
        ticks = recording_ticks(date)
    else:
        date = args.date or latest_trading_day()
        ticks = historical_ticks(date, symbols)

    n_symbols = len({t["symbol"] for t in ticks})
    span = datetime.fromisoformat(ticks[-1]["ts"]) - datetime.fromisoformat(ticks[0]["ts"])
    print(f"REPLAY {date} from {args.source}: {len(ticks):,} ticks, {n_symbols} symbols, "
          f"{span} of trading at {args.speed:g}x ≈ {span / args.speed} "
          f"→ {'stdout' if args.dry_run else TICKS_TOPIC}")

    producer = None if args.dry_run else kafka_producer()
    try:
        while True:
            replay(ticks, args.speed, producer, args.keep_time)
            if not args.loop:
                break
            print("  session finished — looping")
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if producer:
            producer.close()


if __name__ == "__main__":
    main()
