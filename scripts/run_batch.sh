#!/usr/bin/env bash
# Full batch layer: CSV → bronze → silver → gold, MLlib model, then the Spark SQL showcase.
#   ./scripts/run_batch.sh            (uses full history if downloaded, else data/sample)
#   ./scripts/run_batch.sh --source sample
set -euo pipefail
cd "$(dirname "$0")"
./spark_submit.sh batch_load_history.py "$@"
./spark_submit.sh batch_indicators.py
./spark_submit.sh ml_predict.py
./spark_submit.sh batch_queries.py
