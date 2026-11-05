#!/bin/sh
# Build the dataset on first start, then run the given command (the API by default).
set -e

if [ ! -f "$PITCHQUERY_DATA_DIR/events.parquet" ]; then
  echo "First start: building the dataset from StatsBomb open data (downloads ~190 MB)..."
  python -m pitchquery.data.build
fi

exec "$@"
