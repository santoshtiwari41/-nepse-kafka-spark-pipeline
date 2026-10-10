"""LIVE mode: poll NEPSE during market hours and publish price ticks to Kafka.

Every tick is also appended to data/recordings/<date>.jsonl so the session can
be replayed later (REPLAY mode) — run this on every trading day before the demo.

Sources: official NEPSE API (via NepseUnofficialApi); if that fails, the
ShareSansar live-trading page is used for that poll.

    python ingestion/live_producer.py                 # wait for market open, stream until close
    python ingestion/live_producer.py --no-kafka      # only record to disk
    python ingestion/live_producer.py --once --force  # one poll even if market is closed (testing)
"""
import argparse
import io
import json
import time
from datetime import datetime

import pandas as pd
import requests

from common import (HTTP_HEADERS, NPT, RECORDINGS, TICKS_TOPIC, kafka_producer,
                    make_tick, now_npt, send_tick)

SHARESANSAR_LIVE = "https://www.sharesansar.com/live-trading"
MARKET_OPEN = "11:00:00"


class NepseApi:
    name = "nepse-api"

    def __init__(self):
        from nepse import Nepse
        self.client = Nepse()
        self.client.setTLSVerification(False)  # nepalstock.com serves an incomplete cert chain

    def market_open(self) -> bool:
        return self.client.getMarketStatus().get("isOpen") == "OPEN"

    def fetch(self) -> list[dict]:
        ticks = []
        for r in self.client.getLiveMarket():
            ts = datetime.fromisoformat(r["lastUpdatedDateTime"]).replace(tzinfo=NPT)
            ticks.append(make_tick(
                symbol=r["symbol"], ts=ts.isoformat(timespec="seconds"),
                ltp=r["lastTradedPrice"], open=r["openPrice"], high=r["highPrice"],
                low=r["lowPrice"], prev_close=r["previousClose"],
                volume=r["totalTradeQuantity"], turnover=r["totalTradeValue"],
                last_qty=r["lastTradedVolume"], change_pct=r["percentageChange"],
                source=self.name, mode="LIVE"))
        return ticks


class ShareSansar:
    name = "sharesansar"

    def fetch(self) -> list[dict]:
        html = requests.get(SHARESANSAR_LIVE, headers=HTTP_HEADERS, timeout=30).text
        table = pd.read_html(io.StringIO(html))[0]
        ts = now_npt().isoformat(timespec="seconds")  # page has no per-row timestamp
        return [make_tick(
            symbol=r["Symbol"], ts=ts, ltp=r["LTP"], open=r["Open"], high=r["High"],
            low=r["Low"], prev_close=r["Prev. Close"], volume=r["Volume"],
            change_pct=r["% Change"], source=self.name, mode="LIVE")
            for r in table.to_dict("records")]


def run(args):
    api = NepseApi()
    fallback = ShareSansar()
    producer = None if args.no_kafka else kafka_producer()
    last_seen: dict[str, tuple] = {}   # symbol → (ltp, volume) of last published tick

    while True:
        try:
            is_open = api.market_open()
        except Exception as exc:
            print(f"[warn] market status unavailable ({exc}); assuming open")
            is_open = True

        if not is_open and not args.force:
            if args.once:
                print("Market is closed (use --force to poll anyway).")
                return
            print(f"{now_npt():%H:%M:%S} market closed — checking again in 60 s")
            time.sleep(60)
            continue

        try:
            ticks, source = api.fetch(), api.name
        except Exception as exc:
            print(f"[warn] NEPSE API failed ({exc}); using ShareSansar")
            ticks, source = fallback.fetch(), fallback.name

        # Publish only symbols whose price or volume changed since the last poll
        changed = [t for t in ticks if last_seen.get(t["symbol"]) != (t["ltp"], t["volume"])]
        for t in changed:  # a trading day is one session, starting at market open
            t["session_date"] = t["ts"][:10]
            t["session_start"] = f"{t['session_date']}T{MARKET_OPEN}+05:45"
        for t in changed:
            last_seen[t["symbol"]] = (t["ltp"], t["volume"])
            if producer:
                send_tick(producer, TICKS_TOPIC, t)
        if producer:
            producer.flush()
        if changed and not args.no_record:
            record(changed)

        print(f"{now_npt():%H:%M:%S} [{source}] {len(ticks)} symbols, {len(changed)} changed"
              f"{' → ' + TICKS_TOPIC if producer else ''}")
        if args.once:
            return
        time.sleep(args.interval)


def record(ticks: list[dict]):
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    path = RECORDINGS / f"{ticks[0]['ts'][:10]}.jsonl"
    with path.open("a") as f:
        for t in ticks:
            f.write(json.dumps(t) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=5, help="seconds between polls (default 5)")
    parser.add_argument("--no-kafka", action="store_true", help="don't publish, only record")
    parser.add_argument("--no-record", action="store_true", help="don't save to data/recordings")
    parser.add_argument("--force", action="store_true", help="poll even when the market is closed")
    parser.add_argument("--once", action="store_true", help="single poll then exit")
    try:
        run(parser.parse_args())
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
