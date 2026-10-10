#!/usr/bin/env bash
# Run a PySpark job from spark/jobs on the cluster.
#   ./scripts/spark_submit.sh batch_indicators.py [job args...]
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: $0 <job.py> [args...]" >&2; exit 1; }
job=$1; shift
docker exec spark-master /opt/spark/bin/spark-submit "/opt/spark-apps/$job" "$@"
