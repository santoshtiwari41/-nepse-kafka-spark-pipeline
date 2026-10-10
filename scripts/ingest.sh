#!/usr/bin/env bash
# Run a data-collection or producer script inside the ingestion container (no local Python needed).
#
#   ./scripts/ingest.sh replay_producer --loop          # REPLAY the latest trading day into Kafka
#   ./scripts/ingest.sh live_producer                   # LIVE: stream NEPSE while the market is open
#   ./scripts/ingest.sh live_producer --no-kafka        # only record today's session to data/recordings/
#   ./scripts/ingest.sh fetch_companies                 # company list → data/reference/
#   ./scripts/ingest.sh fetch_history                   # full price history → data/historical/
#   ./scripts/ingest.sh build_sample                    # offline sample → data/sample/
#
# Extra docker options go in INGEST_DOCKER_OPTS, e.g. INGEST_DOCKER_OPTS="-d --name nepse-producer"
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then sed -n '2,10p' "$0"; exit 1; fi
script=${1%.py}; shift
[ -f "ingestion/$script.py" ] || { echo "no such script: ingestion/$script.py" >&2; exit 1; }

# Build the image once (needs internet the first time); afterwards this works offline
docker image inspect nepse-ingestion:1.0 > /dev/null 2>&1 || docker compose build producer

# Run as the current user so files written to data/ belong to you, not root
# shellcheck disable=SC2086
exec docker compose run --rm ${INGEST_DOCKER_OPTS:-} --user "$(id -u):$(id -g)" producer \
  python "ingestion/$script.py" "$@"
