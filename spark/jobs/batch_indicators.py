"""Batch layer, step 2: silver → gold analytics (technical indicators & aggregates).

Gold outputs (/nepse/gold/...)
  indicators       per symbol per day: SMA 20/50/200, RSI 14, Bollinger bands,
                   volatility, 52-week high/low, returns, volume ratio, signals
  latest_snapshot  latest row per actively traded symbol (stock screener)
  volume_baseline  20-day average volume per symbol → used by streaming spike alerts
  sector_daily     per sector per day: turnover, average return, advancers/decliners
  market_daily     NEPSE index + SMA/RSI + whole-market breadth

All price indicators use the corporate-action adjusted prices (adj_*). Sector and
market statistics count ordinary shares only (no debentures / mutual funds).

    spark-submit /opt/spark-apps/batch_indicators.py
"""
import math

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

LAKE = "/nepse"
TRADING_DAYS_PER_YEAR = 252


def rolling(n, end=0):
    return Window.partitionBy("symbol").orderBy("date").rowsBetween(-(n - 1) + end, end)


def sma(col, n):
    """n-day simple moving average, null until n days of history exist."""
    return F.when(F.count(col).over(rolling(n)) >= n, F.avg(col).over(rolling(n)))


def add_rsi(df, price, n=14):
    w = Window.partitionBy("symbol").orderBy("date")
    delta = F.col(price) - F.lag(price).over(w)
    df = (df.withColumn("_gain", F.greatest(delta, F.lit(0.0)))
            .withColumn("_loss", F.greatest(-delta, F.lit(0.0)))
            .withColumn("_avg_gain", sma("_gain", n))
            .withColumn("_avg_loss", sma("_loss", n)))
    rsi = F.when(F.col("_avg_loss") == 0, F.lit(100.0)).otherwise(
        100 - 100 / (1 + F.col("_avg_gain") / F.col("_avg_loss")))
    return df.withColumn(f"rsi_{n}", F.round(rsi, 2)).drop("_gain", "_loss", "_avg_gain", "_avg_loss")


def indicators(prices):
    w = Window.partitionBy("symbol").orderBy("date")
    year_range = Window.partitionBy("symbol").orderBy(F.expr("unix_date(date)")).rangeBetween(-365, 0)

    df = (prices
        .withColumn("daily_return", F.col("adj_close") / F.lag("adj_close").over(w) - 1)
        .withColumn("sma_20", F.round(sma("adj_close", 20), 2))
        .withColumn("sma_50", F.round(sma("adj_close", 50), 2))
        .withColumn("sma_200", F.round(sma("adj_close", 200), 2))
        .withColumn("_std_20", F.stddev("adj_close").over(rolling(20)))
        .withColumn("bb_upper", F.round(F.col("sma_20") + 2 * F.col("_std_20"), 2))
        .withColumn("bb_lower", F.round(F.col("sma_20") - 2 * F.col("_std_20"), 2))
        .withColumn("volatility_20", F.round(
            F.stddev("daily_return").over(rolling(20)) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2))
        .withColumn("high_52w", F.max("adj_high").over(year_range))
        .withColumn("low_52w", F.min("adj_low").over(year_range))
        # average volume of the 20 sessions BEFORE today, so a spike is compared to "normal"
        .withColumn("avg_volume_20", F.round(F.avg("volume").over(rolling(20, end=-1))))
        .withColumn("volume_ratio", F.round(F.col("volume") / F.col("avg_volume_20"), 2)))

    for label, n in [("1w", 5), ("1m", 21), ("3m", 63), ("1y", TRADING_DAYS_PER_YEAR)]:
        df = df.withColumn(f"ret_{label}", F.round((F.col("adj_close") / F.lag("adj_close", n).over(w) - 1) * 100, 2))

    df = add_rsi(df, "adj_close")

    above = F.col("sma_50") > F.col("sma_200")
    was_above = F.lag("sma_50").over(w) > F.lag("sma_200").over(w)
    df = (df
        .withColumn("daily_return", F.round(F.col("daily_return") * 100, 3))
        .withColumn("golden_cross", F.coalesce(above & ~was_above, F.lit(False)))
        .withColumn("death_cross", F.coalesce(~above & was_above, F.lit(False)))
        .withColumn("trend", F.when((F.col("adj_close") > F.col("sma_50")) & above, "UPTREND")
                              .when((F.col("adj_close") < F.col("sma_50")) & ~above, "DOWNTREND")
                              .otherwise("SIDEWAYS"))
        .withColumn("rsi_signal", F.when(F.col("rsi_14") >= 70, "OVERBOUGHT")
                                   .when(F.col("rsi_14") <= 30, "OVERSOLD")
                                   .otherwise("NEUTRAL"))
        .withColumn("volume_spike", F.coalesce(F.col("volume_ratio") >= 3, F.lit(False)))
        .drop("_std_20"))
    return df


def latest_snapshot(ind):
    last_date = ind.agg(F.max("date")).first()[0]
    w = Window.partitionBy("symbol").orderBy(F.col("date").desc())
    return (ind.filter(F.col("date") >= F.date_sub(F.lit(last_date), 30))   # still trading
               .withColumn("_rn", F.row_number().over(w))
               .filter("_rn = 1").drop("_rn", "year"))


def volume_baseline(ind):
    """Normal daily volume per symbol from its last 20 sessions (streaming alert reference)."""
    w = Window.partitionBy("symbol").orderBy(F.col("date").desc())
    return (ind.withColumn("_rn", F.row_number().over(w))
               .filter("_rn <= 20")
               .groupBy("symbol", "sector")
               .agg(F.round(F.avg("volume")).alias("avg_volume_20"),
                    F.round(F.avg("turnover")).alias("avg_turnover_20"),
                    F.max("date").alias("as_of"),
                    F.max_by("close", "date").alias("last_close")))


def equities(df):
    return df.filter(F.col("instrument_type") == "Equity")


def sector_daily(ind):
    return (equities(ind).groupBy("sector", "date")
               .agg(F.count("*").alias("stocks"),
                    F.round(F.sum("turnover")).alias("turnover"),
                    F.sum("volume").alias("volume"),
                    F.round(F.avg("daily_return"), 3).alias("avg_return_pct"),
                    F.sum((F.col("daily_return") > 0).cast("int")).alias("advancers"),
                    F.sum((F.col("daily_return") < 0).cast("int")).alias("decliners"))
               .withColumn("year", F.year("date")))


def market_daily(index, ind):
    breadth = (equities(ind).groupBy("date")
                  .agg(F.sum((F.col("daily_return") > 0).cast("int")).alias("advancers"),
                       F.sum((F.col("daily_return") < 0).cast("int")).alias("decliners"),
                       F.count("*").alias("stocks_traded")))
    nepse = (index.filter(F.col("symbol") == "NEPSE")
                  .withColumn("adj_close", F.col("close"))
                  .withColumn("sma_50", F.round(sma("close", 50), 2))
                  .withColumn("sma_200", F.round(sma("close", 200), 2)))
    nepse = add_rsi(nepse, "close").drop("adj_close")
    return nepse.join(breadth, "date", "left").orderBy("date")


def main():
    spark = SparkSession.builder.appName("nepse-batch-indicators").getOrCreate()
    prices = spark.read.parquet(f"{LAKE}/silver/prices")
    index = spark.read.parquet(f"{LAKE}/silver/index")

    ind = indicators(prices)
    ind.write.mode("overwrite").partitionBy("year").parquet(f"{LAKE}/gold/indicators")
    ind = spark.read.parquet(f"{LAKE}/gold/indicators")   # reuse the materialised result
    print("gold  indicators")

    outputs = {
        "latest_snapshot": latest_snapshot(ind),
        "volume_baseline": volume_baseline(ind),
        "sector_daily": sector_daily(ind),
        "market_daily": market_daily(index, ind),
    }
    for name, df in outputs.items():
        writer = df.coalesce(1).write.mode("overwrite")
        if name == "sector_daily":
            writer = writer.partitionBy("year")
        writer.parquet(f"{LAKE}/gold/{name}")
        print(f"gold  {name}")

    snap = spark.read.parquet(f"{LAKE}/gold/latest_snapshot")
    print(f"\nLatest snapshot: {snap.count()} active symbols as of {snap.agg(F.max('date')).first()[0]}")
    snap.filter(F.col("symbol").isin("NABIL", "NTC", "UPPER", "NICA")) \
        .select("symbol", "date", "close", "sma_50", "sma_200", "rsi_14", "high_52w", "low_52w",
                "ret_1y", "trend", "rsi_signal").show(truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
