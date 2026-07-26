# Custom bucket indexes

The primary project workflow is now the manifest-driven pipeline documented in
the repository-level `README.md`. It builds all sector and industry baskets
from the checked-in TradingView definition manifest and stores them exclusively
in `nifty_custom_index_breakout`.

The commands below are retained only for manually maintained legacy buckets.
They are not used by `run.sh` and continue to target the historical shared
index for backwards compatibility.

Create a saved equal-weight bucket with its own synthetic ticker:

```bash
python technical/customIndex/createCustomIndex.py \
  --name "AI Leaders" \
  --ticker "^AI_LEADERS" \
  --constituents "TCS.NS,INFY.NS,PERSISTENT.NS"
```

The command writes the bucket definition to `custom_buckets.json`, upserts the
same definition into Elasticsearch's `indices` metadata index, and materialises
its historical candles in `nifty_data_weekly`.

Those candles go through the existing technical indexer, so they receive the
same weekly MA/VCP fields as the `macTesting` universe.  To process just the
new bucket with the existing support/resistance helper, run:

```bash
python stock-pattern-enricher/main.py --symbols "^AI_LEADERS"
```

The regular `./run.sh` pipeline also rebuilds all saved buckets and enriches
them automatically before it runs the existing screen.
