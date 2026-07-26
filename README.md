# Custom Indices Breakout

This project builds one synthetic index for every unique TradingView basket in
`technical/customIndex/data/tradingview_index_definitions.json`, then applies
the same weekly breakout enrichment used by the stock workflow. The manifest
is checked in, so `run.sh` does not need the local source Excel directory.

Each index is calculated from daily constituent data beginning on 2010-01-01.
It is rebalanced to equal weight every trading day, then converted to weekly
OHLCV. This preserves the live, unclosed current-week candle.

All weekly documents are stored only in Elasticsearch index
`nifty_custom_index_breakout`; the stock index `nifty_data_weekly` is neither
read nor modified.

Each document includes the custom-index metadata requested for filtering:

- `sector_or_industry` and `classification_type` (`sector` for `NIFTY_*`
  source rows and `industry` for `SCREENER_*` source rows);
- exact `tradingview_equation` / `index_formula`, plus formula source provenance;
- `calculation_method: equal_weight` and `rebalance_frequency: daily`;
- checked-in source-workbook provenance, current constituent list, tags, and
  constituent count.

## Full pipeline

With Elasticsearch running on `http://localhost:9200`:

```bash
bash run.sh
```

The script rebuilds only `nifty_custom_index_breakout`, enriches the latest
weekly candle with the shared support/resistance calculation, prints the
indices that match the existing stock breakout criteria, and creates a dated
Excel report in `outputs/custom-index-breakouts/`.

The report filename uses the current IST weekday while the week is in progress.
Once the week closes, Saturday and Sunday runs use the preceding Friday's date.
It contains `Breakouts`, `Breakout Constituents`, `Methodology`, and
`Fundamentals` sheets. The final sheet fetches live Screener.in values only for
the unique stocks in the final breakout-constituent set; it does not save those
fundamentals in Elasticsearch. Its fields include Market Cap, Stock P/E, ROCE,
ROE, revenue/profit QoQ and YoY, current-quarter result status, source URLs,
and the checked-in broad-market, sectoral, sub-sector, and industry taxonomy.

Screener requests are sequential and use a 1.25-second minimum delay between
requests, with retries for temporary server responses. The report can take a
few minutes when there are many breakout constituents. QoQ compares the latest
reported quarter with its prior quarter and YoY compares it with the same
quarter a year earlier. `Latest Quarter Result Out?` is `Yes` only when
Screener reports revenue, net profit, and EPS for the latest completed quarter.

For an offline layout check, omit live requests with:

```bash
python technical/customIndex/report_workbook.py --skip-fundamentals
```

To retain existing documents while refreshing them by deterministic
`ticker_date` IDs, omit `--reset`:

```bash
python technical/customIndex/custom_index_pipeline.py
```

Run tests with:

```bash
python -m unittest discover -s tests -v
```
