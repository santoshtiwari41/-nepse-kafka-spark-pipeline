"""Phase 0 smoke test: proves Spark can talk to both Kafka and HDFS.

1. Write a few fake NEPSE ticks to a Kafka topic (Spark → Kafka)
2. Read them back from Kafka (Kafka → Spark)
3. Save them as Parquet in HDFS and read the Parquet back (Spark ↔ HDFS)

Run:  ./scripts/verify.sh   (or spark-submit /opt/spark-apps/smoke_test.py)
"""
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

TOPIC = "nepse.smoke"
BOOTSTRAP = "kafka:9092"
HDFS_PATH = "/nepse/_smoke/ticks"

spark = SparkSession.builder.appName("nepse-smoke-test").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

schema = StructType([
    StructField("symbol", StringType()),
    StructField("ltp", DoubleType()),
    StructField("volume", LongType()),
])
sample = [("NABIL", 512.0, 1200), ("NTC", 880.5, 340), ("UPPER", 210.3, 5600)]

# 1. Spark → Kafka
(spark.createDataFrame(sample, schema)
    .select(F.col("symbol").alias("key"), F.to_json(F.struct("*")).alias("value"))
    .write.format("kafka")
    .option("kafka.bootstrap.servers", BOOTSTRAP)
    .option("topic", TOPIC)
    .save())
print(f"[1/3] wrote {len(sample)} messages to Kafka topic '{TOPIC}'")

# 2. Kafka → Spark
ticks = (spark.read.format("kafka")
    .option("kafka.bootstrap.servers", BOOTSTRAP)
    .option("subscribe", TOPIC)
    .option("startingOffsets", "earliest")
    .load()
    .select(F.from_json(F.col("value").cast("string"), schema).alias("t"))
    .select("t.*"))
n_kafka = ticks.count()
print(f"[2/3] read {n_kafka} messages back from Kafka")

# 3. Spark ↔ HDFS
ticks.write.mode("overwrite").parquet(HDFS_PATH)
n_hdfs = spark.read.parquet(HDFS_PATH).count()
print(f"[3/3] wrote and read back {n_hdfs} rows as Parquet at hdfs://{HDFS_PATH}")

spark.read.parquet(HDFS_PATH).show()
spark.stop()

if n_kafka < len(sample) or n_hdfs != n_kafka:
    print("SMOKE TEST FAILED")
    sys.exit(1)
print("SMOKE TEST PASSED")
