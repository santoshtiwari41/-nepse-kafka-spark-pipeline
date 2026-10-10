"""Build the small offline sample dataset committed to git (data/sample/).

Picks the most actively traded companies of every sector (by average turnover
over the last year) plus a few well-known blue chips, keeps their history from
--since onward, and adds the NEPSE index and the company master. The whole demo
can run from this if internet is down.

    python ingestion/build_sample.py --per-sector 3 --since 2019-01-01
"""
import argparse
import shutil

import pandas as pd

from common import INDEX_DIR, PRICES_DIR, REFERENCE_DIR, SAMPLE

# Familiar names that are always in the sample (good for the demo)
ALWAYS_INCLUDE = ["NABIL", "NTC", "NICA", "SCB", "UPPER", "CHCL", "NLIC", "SHL"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-sector", type=int, default=3)
    parser.add_argument("--since", default="2019-01-01")
    args = parser.parse_args()

    files = sorted(PRICES_DIR.glob("*.csv"))
    if not files:
        raise SystemExit("No history found — run fetch_history.py first.")

    prices = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    latest = prices["date"].max()
    year_ago = (pd.Timestamp(latest) - pd.DateOffset(years=1)).date().isoformat()
    companies = pd.read_csv(REFERENCE_DIR / "companies.csv")
    equities = companies[companies["instrument_type"] == "Equity"][["symbol", "sector"]]

    turnover = (prices[prices["date"] >= year_ago]
                .groupby("symbol", as_index=False)["turnover"].mean()
                .merge(equities, on="symbol"))
    top = set(turnover.sort_values("turnover", ascending=False)
                      .groupby("sector").head(args.per_sector)["symbol"])
    top |= set(ALWAYS_INCLUDE) & set(prices["symbol"])

    sample = prices[prices["symbol"].isin(top) & (prices["date"] >= args.since)]
    out = SAMPLE / "prices"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for symbol, df in sample.groupby("symbol"):
        df.to_csv(out / f"{symbol}.csv", index=False)

    (SAMPLE / "index").mkdir(exist_ok=True)
    shutil.copy(INDEX_DIR / "NEPSE.csv", SAMPLE / "index" / "NEPSE.csv")
    shutil.copy(REFERENCE_DIR / "companies.csv", SAMPLE / "companies.csv")

    print(f"Sample: {len(top)} symbols, {len(sample):,} rows ({args.since} → {latest}) → {SAMPLE}")
    print("Symbols:", ", ".join(sorted(top)))


if __name__ == "__main__":
    main()
