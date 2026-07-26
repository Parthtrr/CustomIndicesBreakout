#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
PYTHON_BIN="${PYTHON_BIN:-$PWD/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

until curl --silent --fail http://localhost:9200 >/dev/null; do
  echo "Waiting for Elasticsearch at http://localhost:9200..."
  sleep 2
done

"$PYTHON_BIN" technical/customIndex/custom_index_pipeline.py --reset
# The technical indexer writes in bulk. Make every newly indexed custom symbol
# visible before the pattern enricher discovers its universe.
curl --silent --show-error --fail --request POST http://localhost:9200/nifty_custom_index_breakout/_refresh >/dev/null
"$PYTHON_BIN" stock-pattern-enricher/main.py
# The enricher upserts the latest candle, so refresh once more before reporting.
curl --silent --show-error --fail --request POST http://localhost:9200/nifty_custom_index_breakout/_refresh >/dev/null
"$PYTHON_BIN" technical/customIndex/report_breakouts.py
"$PYTHON_BIN" technical/customIndex/report_workbook.py
