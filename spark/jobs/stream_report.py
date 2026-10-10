"""Summarise what the streaming job has written to HDFS (demo + fault-tolerance check).

    spark-submit /opt/spark-apps/stream_report.py [--symbol NABIL]
"""
import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

LAKE = "/nepse"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NABIL")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("nepse-stream-report").getOrCreate()
    ticks = spark.read.parquet(f"{LAKE}/bronze/ticks")
    candles = spark.read.parquet(f"{LAKE}/gold/candles_1m")
    flow = spark.read.parquet(f"{LAKE}/gold/sector_flow_1m")
    alerts = spark.read.parquet(f"{LAKE}/gold/alerts")

    print("\n▶ Ticks stored in HDFS (bronze/ticks)")
    ticks.groupBy("trade_date", "mode").agg(
        F.count("*").alias("ticks"),
        F.countDistinct("symbol").alias("symbols"),
        F.countDistinct("symbol", "ts", "volume").alias("distinct_ticks")).orderBy("trade_date").show()

    print(f"▶ 1-minute candles for {args.symbol}")
    candles.filter(F.col("symbol") == args.symbol).orderBy("window_start") \
        .select("window_start", "open", "high", "low", "close", "volume", "vwap", "trades").show(10, False)

    print("▶ Sector money flow (turnover in streamed windows)")
    flow.groupBy("sector").agg(F.round(F.sum("turnover") / 1e6, 1).alias("turnover_million_npr"),
                               F.sum("trades").alias("trades")) \
        .orderBy(F.desc("turnover_million_npr")).show(truncate=False)

    print("▶ Alerts by type")
    alerts.groupBy("alert_type", "severity").count().orderBy(F.desc("count")).show()
    alerts.orderBy("event_time").select("event_time", "alert_type", "message").show(10, False)
    spark.stop()


if __name__ == "__main__":
    main()
