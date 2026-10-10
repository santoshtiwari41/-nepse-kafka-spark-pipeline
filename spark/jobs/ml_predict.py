"""Bonus: Spark MLlib — will a stock close higher tomorrow?

Random-forest classifier on the technical indicators from the batch layer.
Trained on history before --split-date, evaluated on everything after it
(time-based split: no peeking into the future), then used to score the
latest trading day.

Outputs (/nepse/gold/...)
  ml_metrics       accuracy, AUC, baseline, train/test sizes
  ml_features      feature importances
  ml_predictions   probability of "up next day" for every symbol on the latest day

Daily price moves are mostly noise, so expect accuracy only a little above the
baseline — the point is to demonstrate a distributed ML pipeline, not to give
investment advice.

    spark-submit /opt/spark-apps/ml_predict.py [--split-date 2025-01-01]
"""
import argparse

from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import VectorAssembler
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

LAKE = "/nepse"
# P(up) = second element of the probability vector (UDF avoids pyspark.ml.functions → pandas)
prob_up = F.udf(lambda v: float(v[1]), DoubleType())

FEATURES = ["daily_return", "ret_1w", "ret_1m", "rsi_14", "dist_sma20", "dist_sma50",
            "sma50_vs_200", "bb_position", "volume_ratio", "volatility_20"]


def build_dataset(spark):
    w = Window.partitionBy("symbol").orderBy("date")
    ind = spark.read.parquet(f"{LAKE}/gold/indicators").filter(
        (F.col("instrument_type") == "Equity") & (F.col("date") >= "2015-01-01"))
    next_return = F.lead("adj_close").over(w) / F.col("adj_close") - 1
    return (ind
        .withColumn("dist_sma20", F.col("adj_close") / F.col("sma_20") - 1)
        .withColumn("dist_sma50", F.col("adj_close") / F.col("sma_50") - 1)
        .withColumn("sma50_vs_200", F.col("sma_50") / F.col("sma_200") - 1)
        .withColumn("bb_position", (F.col("adj_close") - F.col("bb_lower")) /
                                   (F.col("bb_upper") - F.col("bb_lower")))
        .withColumn("next_return", next_return)
        .withColumn("label", (F.col("next_return") > 0).cast("double"))
        .select("symbol", "sector", "date", "adj_close", "next_return", "label", *FEATURES)
        .replace(float("inf"), None).replace(float("-inf"), None))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-date", default="2025-01-01")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("nepse-ml-predict").getOrCreate()
    data = build_dataset(spark).cache()
    last_date = data.agg(F.max("date")).first()[0]

    # unchanged-price days (common for illiquid stocks) are neither up nor down → leave them out
    labelled = data.filter(F.col("next_return").isNotNull() & (F.col("next_return") != 0)).dropna(subset=FEATURES)
    train = labelled.filter(F.col("date") < args.split_date)
    test = labelled.filter(F.col("date") >= args.split_date)

    model = Pipeline(stages=[
        VectorAssembler(inputCols=FEATURES, outputCol="features"),
        RandomForestClassifier(numTrees=60, maxDepth=7, minInstancesPerNode=50, seed=42),
    ]).fit(train)

    scored = model.transform(test).withColumn("p_up", prob_up("probability"))
    auc = BinaryClassificationEvaluator(metricName="areaUnderROC").evaluate(scored)
    stats = scored.agg(
        F.count("*").alias("n"),
        F.avg((F.col("prediction") == F.col("label")).cast("double")).alias("accuracy"),
        F.avg("label").alias("up_share")).first()
    baseline = max(stats["up_share"], 1 - stats["up_share"])     # always guess the majority
    confident = scored.filter((F.col("p_up") >= 0.6) | (F.col("p_up") <= 0.4))
    conf_acc = confident.agg(F.avg((F.col("prediction") == F.col("label")).cast("double"))).first()[0]

    metrics = [
        ("train_rows", train.count()), ("test_rows", stats["n"]),
        ("split_date", args.split_date),
        ("accuracy", round(stats["accuracy"], 4)), ("baseline_accuracy", round(baseline, 4)),
        ("auc", round(auc, 4)),
        ("confident_rows", confident.count()),
        ("confident_accuracy", round(conf_acc, 4) if conf_acc is not None else None),
    ]
    spark.createDataFrame([(k, str(v)) for k, v in metrics], ["metric", "value"]).coalesce(1) \
        .write.mode("overwrite").parquet(f"{LAKE}/gold/ml_metrics")

    importances = model.stages[-1].featureImportances.toArray().tolist()
    spark.createDataFrame(sorted(zip(FEATURES, importances), key=lambda x: -x[1]), ["feature", "importance"]) \
        .coalesce(1).write.mode("overwrite").parquet(f"{LAKE}/gold/ml_features")

    latest = data.filter(F.col("date") == last_date).dropna(subset=FEATURES)
    preds = (model.transform(latest)
             .withColumn("p_up", F.round(prob_up("probability"), 4))
             .withColumn("signal", F.when(F.col("p_up") >= 0.6, "LIKELY UP")
                                    .when(F.col("p_up") <= 0.4, "LIKELY DOWN").otherwise("UNCERTAIN"))
             .select("symbol", "sector", "date", "adj_close", "p_up", "signal"))
    preds.coalesce(1).write.mode("overwrite").parquet(f"{LAKE}/gold/ml_predictions")

    print("\nModel evaluation (test = trading days from %s)" % args.split_date)
    for k, v in metrics:
        print(f"  {k:<20} {v}")
    print("\nFeature importance")
    for f, imp in sorted(zip(FEATURES, importances), key=lambda x: -x[1]):
        print(f"  {f:<14} {imp:.3f}")
    print(f"\nPredictions for {last_date} (next trading day):")
    spark.read.parquet(f"{LAKE}/gold/ml_predictions").groupBy("signal").count().show()
    spark.stop()


if __name__ == "__main__":
    main()
