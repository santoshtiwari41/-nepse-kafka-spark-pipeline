"""Speed layer: Spark Structured Streaming over the nepse.ticks Kafka topic.

Ticks come from live_producer.py (LIVE) or replay_producer.py (REPLAY); this job
cannot tell the difference except for the `mode` field it passes through.

Streaming queries (one Spark application, each with its own checkpoint):
  ticks          raw ticks             → HDFS /nepse/bronze/ticks        (exactly-once file sink)
  candles_1m     1-minute OHLCV + VWAP → HDFS /nepse/gold/candles_1m     (event-time windows, 10 s watermark)
  sector_flow    turnover per sector per minute → HDFS /nepse/gold/sector_flow_1m
  live_snapshot  latest state of every symbol   → Kafka nepse.analytics (stateful, update mode)
  alerts         circuit / volume spike / big move → Kafka nepse.alerts + HDFS /nepse/gold/alerts

Ticks are enriched with a stream-static join against batch-layer outputs:
sector (silver/companies) and normal volume (gold/volume_baseline).

    spark-submit /opt/spark-apps/stream_processor.py [--from-beginning]
"""
import argparse

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

LAKE = "/nepse"
CHECKPOINTS = f"{LAKE}/checkpoints"
BOOTSTRAP = "kafka:9092"

TICK_SCHEMA = StructType([
    StructField("symbol", StringType()), StructField("ts", StringType()),
    *[StructField(c, DoubleType()) for c in
      ["ltp", "open", "high", "low", "prev_close", "volume", "turnover", "last_qty", "change_pct"]],
    StructField("source", StringType()), StructField("mode", StringType()),
    StructField("session_start", StringType()), StructField("session_date", StringType()),
])

# Producers emit ticks in time order, so little lateness is expected: a short watermark
# lets 1-minute windows be written ~10 s after they close
WATERMARK = "10 seconds"

# Alert thresholds
CIRCUIT_PCT = 9.5        # NEPSE circuit is ±10 %; alert when a stock is about to hit it
SPIKE_RATIO = 3.0        # today's volume ≥ 3 × the 20-day average
BIG_MOVE_PCT = 5.0       # price moved ≥ 5 % away from today's open


def read_ticks(spark, from_beginning: bool):
    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", BOOTSTRAP)
           .option("subscribe", "nepse.ticks")
           .option("startingOffsets", "earliest" if from_beginning else "latest")
           .option("maxOffsetsPerTrigger", 20000)
           .option("failOnDataLoss", "false")
           .load())
    return (raw.select(F.from_json(F.col("value").cast("string"), TICK_SCHEMA).alias("t"),
                       F.col("timestamp").alias("kafka_time"))
               .select("t.*", "kafka_time")
               .filter(F.col("symbol").isNotNull() & (F.col("ltp") > 0))
               .withColumn("event_time", F.col("ts").cast("timestamp"))
               .withColumn("trade_date", F.to_date("event_time"))
               .withColumn("volume", F.col("volume").cast("long"))
               .withColumn("last_qty", F.col("last_qty").cast("long")))


def enrich(spark, ticks):
    """Stream-static join with the batch layer (reference data is read once at start)."""
    companies = spark.read.parquet(f"{LAKE}/silver/companies").select("symbol", "sector", "instrument_type")
    baseline = spark.read.parquet(f"{LAKE}/gold/volume_baseline").select("symbol", "avg_volume_20")
    return (ticks.join(F.broadcast(companies), "symbol", "left")
                 .join(F.broadcast(baseline), "symbol", "left")
                 .fillna({"sector": "Unknown", "instrument_type": "Unknown"})
                 .withColumn("volume_ratio", F.round(F.col("volume") / F.col("avg_volume_20"), 2)))


def candles(ticks):
    return (ticks.withWatermark("event_time", WATERMARK)
                 .groupBy(F.window("event_time", "1 minute").alias("w"), "symbol")
                 .agg(F.min_by("ltp", "event_time").alias("open"),
                      F.max("ltp").alias("high"),
                      F.min("ltp").alias("low"),
                      F.max_by("ltp", "event_time").alias("close"),
                      F.sum("last_qty").alias("volume"),
                      F.round(F.sum(F.col("ltp") * F.col("last_qty")) / F.sum("last_qty"), 2).alias("vwap"),
                      F.count("*").alias("trades"),
                      F.first("mode").alias("mode"))
                 .select(F.col("w.start").alias("window_start"), F.col("w.end").alias("window_end"),
                         F.to_date("w.start").alias("trade_date"), "symbol",
                         "open", "high", "low", "close", "volume", "vwap", "trades", "mode"))


def sector_flow(enriched):
    return (enriched.filter(F.col("instrument_type") == "Equity")
                    .withWatermark("event_time", WATERMARK)
                    .groupBy(F.window("event_time", "1 minute").alias("w"), "sector")
                    .agg(F.round(F.sum(F.col("ltp") * F.col("last_qty"))).alias("turnover"),
                         F.sum("last_qty").alias("volume"),
                         F.count("*").alias("trades"),
                         F.approx_count_distinct("symbol").alias("active_symbols"))
                    .select(F.col("w.start").alias("window_start"), F.col("w.end").alias("window_end"),
                            F.to_date("w.start").alias("trade_date"),
                            "sector", "turnover", "volume", "trades", "active_symbols"))


def live_snapshot(enriched):
    """Latest tick per symbol per stream session, kept in Spark state; emits only symbols that changed."""
    cols = ["ltp", "open", "high", "low", "prev_close", "change_pct", "volume", "turnover",
            "volume_ratio", "sector", "instrument_type", "mode", "source", "ts", "trade_date", "session_date"]
    latest = (enriched.groupBy("symbol", "session_start")
                      .agg(F.max_by(F.struct(*cols), "event_time").alias("s"),
                           F.count("*").alias("ticks_today")))
    value = F.to_json(F.struct(
        "symbol", *[F.col(f"s.{c}").alias(c) for c in cols],
        F.round(F.col("s.turnover") / F.col("s.volume"), 2).alias("vwap"),
        "session_start", "ticks_today", F.date_format(F.current_timestamp(), "yyyy-MM-dd'T'HH:mm:ssXXX").alias("processed_at")))
    return latest.select(F.col("symbol").alias("key"), value.alias("value"))


def alerts(enriched):
    base = (enriched.filter(F.col("instrument_type") == "Equity")   # no debentures / mutual funds
                    .withWatermark("event_time", "5 minutes"))
    move_pct = F.round((F.col("ltp") / F.col("open") - 1) * 100, 2)

    def alert(cond, kind, severity, message):
        return (base.filter(cond)
                    .withColumn("alert_type", F.lit(kind))
                    .withColumn("severity", F.lit(severity))
                    .withColumn("message", message))

    circuit_up = alert(F.col("change_pct") >= CIRCUIT_PCT, "UPPER_CIRCUIT", "HIGH",
                       F.format_string("%s up %.2f%% — at/near upper circuit (Rs %.1f)",
                                       "symbol", "change_pct", "ltp"))
    circuit_down = alert(F.col("change_pct") <= -CIRCUIT_PCT, "LOWER_CIRCUIT", "HIGH",
                         F.format_string("%s down %.2f%% — at/near lower circuit (Rs %.1f)",
                                         "symbol", "change_pct", "ltp"))
    spike = alert(F.col("volume_ratio") >= SPIKE_RATIO, "VOLUME_SPIKE", "MEDIUM",
                  F.format_string("%s volume %,d is %.1fx its 20-day average",
                                  "symbol", "volume", "volume_ratio"))
    big_move = alert((F.abs(move_pct) >= BIG_MOVE_PCT) & (F.abs(F.col("change_pct")) < CIRCUIT_PCT),
                     "BIG_MOVE", "MEDIUM",
                     F.format_string("%s moved %.2f%% from today's open (Rs %.1f → %.1f)",
                                     "symbol", move_pct, "open", "ltp"))

    return (circuit_up.unionByName(circuit_down).unionByName(spike).unionByName(big_move)
            # one alert per symbol & type per session until the watermark moves on (no alert storms);
            # session in the key so back-to-back replay loops each get their own alerts
            .dropDuplicatesWithinWatermark(["symbol", "alert_type", "session_start"])
            .select("symbol", "sector", "alert_type", "severity", "message", "ltp", "change_pct",
                    "volume", "volume_ratio", "mode", "session_start", "session_date",
                    "event_time", "trade_date"))


def write_alerts(batch, batch_id):
    """foreachBatch: same micro-batch goes to Kafka (dashboard) and HDFS (history)."""
    if batch.isEmpty():
        return
    batch.persist()
    batch.write.mode("append").partitionBy("trade_date").parquet(f"{LAKE}/gold/alerts")
    (batch.select(F.col("symbol").alias("key"),
                  F.to_json(F.struct(*[c for c in batch.columns if c != "trade_date"])).alias("value"))
          .write.format("kafka").option("kafka.bootstrap.servers", BOOTSTRAP)
          .option("topic", "nepse.alerts").save())
    print(f"[alerts] batch {batch_id}: {batch.count()} alerts")
    batch.unpersist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-beginning", action="store_true",
                        help="first start only: read all ticks still in Kafka instead of new ones")
    args = parser.parse_args()

    spark = (SparkSession.builder.appName("nepse-stream-processor")
             .config("spark.sql.shuffle.partitions", 3)
             .config("spark.sql.streaming.stateStore.stateSchemaCheck", "true")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    ticks = read_ticks(spark, args.from_beginning)
    enriched = enrich(spark, ticks)

    def to_files(df, name, path, trigger="30 seconds"):
        return (df.writeStream.queryName(name).format("parquet").outputMode("append")
                  .option("path", path).option("checkpointLocation", f"{CHECKPOINTS}/{name}")
                  .partitionBy("trade_date").trigger(processingTime=trigger).start())

    to_files(ticks.drop("kafka_time"), "ticks", f"{LAKE}/bronze/ticks")
    to_files(candles(ticks), "candles_1m", f"{LAKE}/gold/candles_1m", trigger="10 seconds")
    to_files(sector_flow(enriched), "sector_flow", f"{LAKE}/gold/sector_flow_1m", trigger="10 seconds")

    (live_snapshot(enriched).writeStream.queryName("live_snapshot").outputMode("update")
        .format("kafka").option("kafka.bootstrap.servers", BOOTSTRAP).option("topic", "nepse.analytics")
        .option("checkpointLocation", f"{CHECKPOINTS}/live_snapshot")
        .trigger(processingTime="5 seconds").start())

    (alerts(enriched).writeStream.queryName("alerts").outputMode("append")
        .foreachBatch(write_alerts)
        .option("checkpointLocation", f"{CHECKPOINTS}/alerts")
        .trigger(processingTime="5 seconds").start())

    print("Streaming queries running:", ", ".join(q.name for q in spark.streams.active))
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
