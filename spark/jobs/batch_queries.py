"""Spark SQL over the data lake — example analytical queries for the demo/report.

Registers the silver/gold Parquet datasets as SQL views and runs a set of
questions an investor would ask. Run a single query with --only <name>.

    spark-submit /opt/spark-apps/batch_queries.py
    spark-submit /opt/spark-apps/batch_queries.py --only oversold
"""
import argparse

from pyspark.sql import SparkSession

LAKE = "/nepse"
VIEWS = {
    "prices": "silver/prices",
    "indicators": "gold/indicators",
    "latest": "gold/latest_snapshot",
    "sector_daily": "gold/sector_daily",
    "market": "gold/market_daily",
    "data_quality": "gold/data_quality",
}

QUERIES = {
    "data_quality": ("What did the cleaning step do?", """
        SELECT metric, value FROM data_quality"""),

    "top_gainers_1y": ("Top 10 stocks by 1-year return (bonus-adjusted)", """
        SELECT symbol, sector, close, ret_1y AS return_1y_pct, trend
        FROM latest WHERE ret_1y IS NOT NULL AND instrument_type = 'Equity'
        ORDER BY ret_1y DESC LIMIT 10"""),

    "sector_turnover_30d": ("Where did money flow in the last 30 days? (turnover by sector)", """
        SELECT sector,
               ROUND(SUM(turnover) / 1e9, 2)          AS turnover_billion_npr,
               ROUND(AVG(avg_return_pct), 3)          AS avg_daily_return_pct,
               SUM(advancers) AS advances, SUM(decliners) AS declines
        FROM sector_daily
        WHERE date >= date_sub((SELECT MAX(date) FROM sector_daily), 30)
        GROUP BY sector ORDER BY turnover_billion_npr DESC"""),

    "oversold": ("Oversold stocks (RSI ≤ 30) — potential rebound candidates", """
        SELECT symbol, sector, close, rsi_14, sma_50, low_52w, high_52w
        FROM latest WHERE rsi_signal = 'OVERSOLD' AND instrument_type = 'Equity' ORDER BY rsi_14 LIMIT 15"""),

    "golden_cross": ("Golden crosses (SMA50 crossed above SMA200) in the last 60 days", """
        SELECT symbol, sector, date, adj_close, sma_50, sma_200
        FROM indicators
        WHERE golden_cross AND instrument_type = 'Equity' AND date >= date_sub((SELECT MAX(date) FROM indicators), 60)
        ORDER BY date DESC LIMIT 15"""),

    "volume_spikes": ("Biggest volume spikes on the latest trading day (vs 20-day average)", """
        SELECT symbol, sector, close, change_pct, volume, avg_volume_20, volume_ratio
        FROM latest WHERE volume_spike AND instrument_type = 'Equity' ORDER BY volume_ratio DESC LIMIT 10"""),

    "most_volatile": ("Most volatile stocks (20-day annualised volatility)", """
        SELECT symbol, sector, close, volatility_20 AS volatility_pct, ret_1m
        FROM latest WHERE volatility_20 IS NOT NULL AND instrument_type = 'Equity'
        ORDER BY volatility_20 DESC LIMIT 10"""),

    "nepse_yearly": ("NEPSE index: yearly performance", """
        SELECT year(date) AS year,
               ROUND(MIN_BY(close, date), 2) AS first_close,
               ROUND(MAX_BY(close, date), 2) AS last_close,
               ROUND((MAX_BY(close, date) / MIN_BY(close, date) - 1) * 100, 2) AS return_pct,
               ROUND(MAX(high), 2) AS year_high, ROUND(MIN(low), 2) AS year_low
        FROM market WHERE date >= '2010-01-01'
        GROUP BY year(date) ORDER BY year"""),

    "nabil_corporate_actions": ("NABIL: detected bonus/right share adjustments", """
        SELECT date, prev_close, open, close, ROUND(open / prev_close, 3) AS gap_ratio,
               ROUND(adj_factor, 3) AS adj_factor_before_this
        FROM prices WHERE symbol = 'NABIL' AND corporate_action ORDER BY date"""),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(QUERIES))
    args = parser.parse_args()

    spark = SparkSession.builder.appName("nepse-batch-queries").getOrCreate()
    for view, path in VIEWS.items():
        spark.read.parquet(f"{LAKE}/{path}").createOrReplaceTempView(view)

    for name, (title, sql) in QUERIES.items():
        if args.only and name != args.only:
            continue
        print(f"\n▶ {title}   [{name}]")
        spark.sql(sql).show(20, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
