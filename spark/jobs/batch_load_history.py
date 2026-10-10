"""Batch layer, step 1: historical CSV → HDFS bronze → cleaned silver.

Bronze  /nepse/bronze/{prices,index,companies}   data exactly as received + lineage columns
Silver  /nepse/silver/{prices,index,companies}   validated, deduplicated, repaired, adjusted
Gold    /nepse/gold/data_quality                 what the cleaning did (for the report/demo)

Cleaning rules (prices)
  1. drop rows with missing/non-positive prices or zero volume
  2. drop duplicate (symbol, date) rows
  3. repair OHLC: high/low widened to include open and close
  4. detect corporate actions: NEPSE's daily circuit is ±10 %, so an opening gap
     below -10.5 % means bonus/right shares, not trading. Earlier prices are
     multiplied by the gap ratio (back-adjustment) into adj_* columns, so charts
     and indicators don't show fake crashes.
  5. recompute change_pct from the previous close; attach sector and instrument type

    spark-submit /opt/spark-apps/batch_load_history.py [--source full|sample]
"""
import argparse
import os

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

DATA = "/opt/data"
LAKE = "/nepse"
CIRCUIT_GAP = 0.895  # opening below 89.5 % of previous close ⇒ corporate action

PRICE_SCHEMA = StructType([
    StructField("date", StringType()),
    StructField("symbol", StringType()),
    *[StructField(c, DoubleType()) for c in
      ["open", "high", "low", "close", "volume", "turnover", "change_pct"]],
])


def input_paths(source: str) -> dict:
    full = os.path.isdir(f"{DATA}/historical/prices") and os.listdir(f"{DATA}/historical/prices")
    if source == "full" or (source == "auto" and full):
        return {"prices": f"{DATA}/historical/prices", "index": f"{DATA}/historical/index",
                "companies": f"{DATA}/reference/companies.csv", "name": "full history"}
    return {"prices": f"{DATA}/sample/prices", "index": f"{DATA}/sample/index",
            "companies": f"{DATA}/sample/companies.csv", "name": "offline sample"}


def read_csv(spark, path, schema=None):
    reader = spark.read.option("header", True)
    reader = reader.schema(schema) if schema else reader.option("inferSchema", True)
    return (reader.csv(f"file://{path}")
            .withColumn("_source_file", F.input_file_name())
            .withColumn("_ingested_at", F.current_timestamp()))


def to_bronze(spark, paths):
    for name, schema in [("prices", PRICE_SCHEMA), ("index", PRICE_SCHEMA), ("companies", None)]:
        read_csv(spark, paths[name], schema).write.mode("overwrite").parquet(f"{LAKE}/bronze/{name}")
    return {n: spark.read.parquet(f"{LAKE}/bronze/{n}") for n in ["prices", "index", "companies"]}


def clean_prices(raw, companies, quality):
    total = raw.count()
    quality["raw_rows"] = total

    valid = raw.withColumn("date", F.to_date("date")).filter(
        F.col("date").isNotNull() & (F.col("volume") > 0) &
        (F.least("open", "high", "low", "close") > 0))
    quality["invalid_rows_dropped"] = total - valid.count()

    deduped = valid.dropDuplicates(["symbol", "date"])
    quality["duplicate_rows_dropped"] = valid.count() - deduped.count()

    w = Window.partitionBy("symbol").orderBy("date")
    after = Window.partitionBy("symbol").orderBy("date").rowsBetween(1, Window.unboundedFollowing)

    df = (deduped
        .withColumn("ohlc_repaired", (F.col("high") < F.greatest("open", "close")) |
                                     (F.col("low") > F.least("open", "close")))
        .withColumn("high", F.greatest("open", "high", "low", "close"))
        .withColumn("low", F.least("open", "high", "low", "close"))
        .withColumn("volume", F.col("volume").cast("long"))
        .withColumn("prev_close", F.lag("close").over(w))
        .withColumn("change_pct", F.round((F.col("close") / F.col("prev_close") - 1) * 100, 2))
        .withColumn("gap_ratio", F.col("open") / F.col("prev_close"))
        .withColumn("corporate_action", F.coalesce(F.col("gap_ratio") < CIRCUIT_GAP, F.lit(False)))
        # adj factor = product of all LATER corporate-action gap ratios (sum of logs)
        .withColumn("adj_factor", F.exp(F.coalesce(F.sum(
            F.when(F.col("corporate_action"), F.log("gap_ratio")).otherwise(0.0)).over(after), F.lit(0.0)))))

    for c in ["open", "high", "low", "close"]:
        df = df.withColumn(f"adj_{c}", F.round(F.col(c) * F.col("adj_factor"), 2))

    df = (df.join(F.broadcast(companies.select("symbol", "company_name", "sector", "instrument_type")), "symbol", "left")
            .fillna({"sector": "Unknown", "company_name": "", "instrument_type": "Unknown"})
            .withColumn("year", F.year("date"))
            .select("symbol", "company_name", "sector", "instrument_type", "date", "year",
                    "open", "high", "low", "close", "prev_close", "change_pct",
                    "volume", "turnover",
                    "adj_open", "adj_high", "adj_low", "adj_close", "adj_factor",
                    "corporate_action", "ohlc_repaired"))

    stats = df.agg(F.count("*").alias("rows"), F.countDistinct("symbol").alias("symbols"),
                   F.sum(F.col("ohlc_repaired").cast("int")).alias("rep"),
                   F.sum(F.col("corporate_action").cast("int")).alias("ca"),
                   F.min("date").alias("first"), F.max("date").alias("last")).first()
    quality.update({"ohlc_rows_repaired": stats["rep"], "corporate_actions_detected": stats["ca"],
                    "clean_rows": stats["rows"], "symbols": stats["symbols"],
                    "first_date": str(stats["first"]), "last_date": str(stats["last"])})
    return df


def clean_index(raw):
    w = Window.partitionBy("symbol").orderBy("date")
    return (raw.withColumn("date", F.to_date("date"))
               .filter(F.col("date").isNotNull() & (F.col("close") > 0))
               .dropDuplicates(["symbol", "date"])
               .withColumn("prev_close", F.lag("close").over(w))
               .withColumn("change_pct", F.round((F.col("close") / F.col("prev_close") - 1) * 100, 2))
               .select("symbol", "date", "open", "high", "low", "close", "prev_close",
                       "change_pct", "turnover"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["auto", "full", "sample"], default="auto")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("nepse-batch-load-history").getOrCreate()
    paths = input_paths(args.source)
    print(f"Loading {paths['name']} from {paths['prices']}")

    bronze = to_bronze(spark, paths)
    print("bronze  written: prices, index, companies")

    companies = bronze["companies"].drop("_source_file", "_ingested_at")
    companies.write.mode("overwrite").parquet(f"{LAKE}/silver/companies")

    quality = {"input": paths["name"]}
    prices = clean_prices(bronze["prices"], companies, quality)
    prices.write.mode("overwrite").partitionBy("year").parquet(f"{LAKE}/silver/prices")
    clean_index(bronze["index"]).write.mode("overwrite").parquet(f"{LAKE}/silver/index")
    print("silver  written: prices (partitioned by year), index, companies")

    rows = [(k, str(v)) for k, v in quality.items()]
    spark.createDataFrame(rows, ["metric", "value"]).coalesce(1) \
        .write.mode("overwrite").parquet(f"{LAKE}/gold/data_quality")
    print("\nData quality report")
    for k, v in rows:
        print(f"  {k:<28} {v}")
    spark.stop()


if __name__ == "__main__":
    main()
