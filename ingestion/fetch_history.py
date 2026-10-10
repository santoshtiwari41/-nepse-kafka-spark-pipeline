"""Download historical daily OHLCV data for NEPSE companies and the NEPSE index.

Sources
  github      (default) bulk CSVs for ~370 companies, updated daily, includes turnover
              https://github.com/Aabishkar2/nepse-data
  merolagani  per-symbol chart API (fallback / top-up), no turnover

The NEPSE index itself always comes from MeroLagani.

Output (normalised columns, see common.HISTORY_COLUMNS)
  data/historical/prices/<SYMBOL>.csv
  data/historical/index/NEPSE.csv

    python ingestion/fetch_history.py                          # all companies via GitHub
    python ingestion/fetch_history.py --source merolagani --symbols NABIL,NTC
"""
import argparse
import io
import time
import zipfile
from datetime import datetime, timezone

import pandas as pd
import requests

from common import HISTORY_COLUMNS, HTTP_HEADERS, INDEX_DIR, PRICES_DIR

GITHUB_ZIP = "https://codeload.github.com/Aabishkar2/nepse-data/zip/refs/heads/main"
MEROLAGANI_CHART = "https://merolagani.com/handlers/TechnicalChartHandler.ashx"


def fetch_github() -> int:
    print("Downloading GitHub dataset (~30 MB)...")
    resp = requests.get(GITHUB_ZIP, headers=HTTP_HEADERS, timeout=300)
    resp.raise_for_status()

    count = 0
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if "/data/company-wise/" not in name or not name.endswith(".csv"):
                continue
            symbol = name.rsplit("/", 1)[1][:-4].upper()
            raw = pd.read_csv(zf.open(name))
            if raw.empty:
                continue
            df = raw.rename(columns={
                "published_date": "date",
                "traded_quantity": "volume",
                "traded_amount": "turnover",
                "per_change": "change_pct"})
            df["symbol"] = symbol
            save(df[HISTORY_COLUMNS], PRICES_DIR / f"{symbol}.csv")
            count += 1
    return count


def fetch_merolagani(symbol: str, start: str = "2000-01-01") -> pd.DataFrame:
    """Daily candles from MeroLagani's TradingView-style chart endpoint."""
    params = {
        "type": "get_advanced_chart",
        "symbol": symbol,
        "resolution": "1D",
        "rangeStartDate": int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()),
        "rangeEndDate": int(time.time()) + 86400,
        "from": "",
        "isAdjust": 1,
        "currencyCode": "NPR",
    }
    resp = requests.get(MEROLAGANI_CHART, params=params, headers=HTTP_HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("s") != "ok" or not data.get("t"):
        raise ValueError(f"no data for {symbol}: status={data.get('s')}")

    df = pd.DataFrame({
        # Bar timestamps fall between 05:45 and 20:45 UTC of the trading day, so the
        # UTC date is the trading date (converting to NPT would push late bars +1 day)
        "date": pd.to_datetime(data["t"], unit="s", utc=True).date,
        "open": data["o"], "high": data["h"], "low": data["l"],
        "close": data["c"], "volume": data["v"],
    })
    df["symbol"] = symbol
    df["turnover"] = None
    df["change_pct"] = (df["close"].pct_change() * 100).round(2)
    return df[HISTORY_COLUMNS]


def save(df: pd.DataFrame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.sort_values("date").drop_duplicates("date", keep="last").to_csv(path, index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["github", "merolagani"], default="github")
    parser.add_argument("--symbols", help="comma-separated symbols (required for merolagani)")
    parser.add_argument("--no-index", action="store_true", help="skip NEPSE index download")
    args = parser.parse_args()

    if args.source == "github":
        print(f"Saved {fetch_github()} company files → {PRICES_DIR}")
    else:
        if not args.symbols:
            parser.error("--symbols is required with --source merolagani")
        for symbol in [s.strip().upper() for s in args.symbols.split(",")]:
            try:
                df = fetch_merolagani(symbol)
                save(df, PRICES_DIR / f"{symbol}.csv")
                print(f"  {symbol}: {len(df)} days ({df['date'].min()} → {df['date'].max()})")
            except Exception as exc:
                print(f"  {symbol}: FAILED ({exc})")
            time.sleep(0.5)  # be polite to the server

    if not args.no_index:
        idx = fetch_merolagani("NEPSE")
        # For the index, MeroLagani's "volume" is market turnover in NPR
        idx["turnover"], idx["volume"] = idx["volume"], None
        save(idx, INDEX_DIR / "NEPSE.csv")
        print(f"NEPSE index: {len(idx)} days ({idx['date'].min()} → {idx['date'].max()}) → {INDEX_DIR}")


if __name__ == "__main__":
    main()
