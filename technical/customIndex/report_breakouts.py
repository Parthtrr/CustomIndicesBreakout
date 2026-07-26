"""Print the custom indices matching the existing stock breakout screen."""

from __future__ import annotations

from elasticsearch import Elasticsearch


ES_HOST = "http://localhost:9200"
INDEX_NAME = "nifty_custom_index_breakout"


def latest_custom_index_date(es: Elasticsearch) -> str | None:
    response = es.search(
        index=INDEX_NAME,
        size=1,
        sort=[{"date": {"order": "desc"}}],
        _source=["date"],
        query={"term": {"isCustom": True}},
    )
    hits = response.get("hits", {}).get("hits", [])
    return hits[0]["_source"].get("date") if hits else None


def find_breakouts(es: Elasticsearch, candle_date: str) -> list[dict]:
    """Use the same VCP + nearby-support criteria as the stock scanner."""
    query = {
        "size": 1_000,
        "_source": [
            "ticker", "index_name", "sector_or_industry", "classification_type",
            "definition_id", "source_file", "source_files", "constituents", "constituent_count",
            "tradingview_equation", "index_formula",
            "calculation_method", "rebalance_frequency", "close", "date", "rsi",
            "roc", "dist_from_52w_high_pct", "crossed_resistance",
        ],
        "query": {
            "bool": {
                "must": [
                    {"term": {"isCustom": True}},
                    {"term": {"vcp_trend_template": True}},
                    {"term": {"date": candle_date}},
                    {"range": {"crossed_resistance.support_distance_pct": {"lte": 10}}},
                ]
            }
        },
        "sort": [{"sector_or_industry": {"order": "asc"}}, {"ticker": {"order": "asc"}}],
    }
    response = es.search(index=INDEX_NAME, body=query)
    return [hit["_source"] for hit in response.get("hits", {}).get("hits", [])]


def main() -> int:
    es = Elasticsearch(ES_HOST)
    candle_date = latest_custom_index_date(es)
    if candle_date is None:
        print("No custom-index candles are indexed yet.")
        return 0

    breakouts = find_breakouts(es, candle_date)
    print(f"Custom-index breakout screen for week starting {candle_date}")
    if not breakouts:
        print("No custom indices match the stock breakout criteria.")
        return 0

    for document in breakouts:
        closest_level = next(
            (
                level for level in document.get("crossed_resistance", [])
                if level.get("support_distance_pct") is not None
                and level["support_distance_pct"] <= 10
            ),
            {},
        )
        print(
            " | ".join(
                [
                    document.get("index_name", document["ticker"]),
                    document.get("classification_type", "custom"),
                    document.get("sector_or_industry", ""),
                    f"close={document.get('close')}",
                    f"support={closest_level.get('support_level')}",
                    f"resistance={closest_level.get('resistance_level')}",
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
