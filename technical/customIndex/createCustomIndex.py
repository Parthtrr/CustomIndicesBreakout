"""Persist, build, and index equal-weight custom buckets.

The output candles are deliberately sent through the same ``index_data``
function as the rest of the macTesting universe.  That gives a custom bucket
the identical weekly MA, VCP, and 52-week fields before the existing pattern
enricher adds support/resistance information.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
from elasticsearch import Elasticsearch, helpers


ES = Elasticsearch("http://localhost:9200")
SRC_INDEX = "nifty_data_weekly"
META_INDEX = "indices"
BASE_VALUE = 1000.0
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BUCKET_FILE = SCRIPT_DIR / "custom_buckets.json"

METADATA_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "Name": {"type": "keyword"},
            "ticker": {"type": "keyword"},
            "constituents": {"type": "keyword"},
            "link": {"type": "keyword"},
            "IsCustom": {"type": "boolean"},
            "id": {"type": "keyword"},
        }
    },
}


def _normalise_constituents(constituents: Iterable[str]) -> list[str]:
    """Return clean, stable, de-duplicated Yahoo-style ticker symbols."""
    normalised: list[str] = []
    seen: set[str] = set()

    for constituent in constituents:
        if not isinstance(constituent, str):
            raise ValueError("Every constituent must be a ticker string")

        for ticker in constituent.split(","):
            ticker = ticker.strip().upper()
            if not ticker:
                continue
            if ticker not in seen:
                normalised.append(ticker)
                seen.add(ticker)

    if not normalised:
        raise ValueError("A custom bucket must contain at least one constituent")

    return normalised


def build_custom_bucket_definition(
    name: str, ticker: str, constituents: Iterable[str]
) -> dict[str, Any]:
    """Validate a new bucket and return the metadata stored in ``indices``."""
    clean_name = name.strip()
    clean_ticker = ticker.strip().upper()

    if not clean_name:
        raise ValueError("Custom bucket name is required")
    if not clean_ticker:
        raise ValueError("Custom bucket ticker is required")
    if not re.fullmatch(r"\^?[A-Z0-9&_-]+", clean_ticker):
        raise ValueError(
            "Custom bucket ticker may contain letters, numbers, '&', '_', or '-'."
        )
    if not clean_ticker.startswith("^"):
        clean_ticker = f"^{clean_ticker}"

    clean_constituents = _normalise_constituents(constituents)
    document_id = f"{clean_name}:{clean_ticker}"
    return {
        "Name": clean_name,
        "ticker": clean_ticker,
        "constituents": clean_constituents,
        "IsCustom": True,
        "id": document_id,
    }


def _read_bucket_file(bucket_file: Path) -> dict[str, Any]:
    if not bucket_file.exists():
        return {}

    with bucket_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(f"{bucket_file} must contain a JSON object")
    return data


def save_custom_bucket_definition(
    definition: dict[str, Any], bucket_file: Path = DEFAULT_BUCKET_FILE
) -> None:
    """Persist a bucket definition so subsequent full pipeline runs retain it."""
    bucket_file = Path(bucket_file)
    buckets = _read_bucket_file(bucket_file)
    buckets[definition["ticker"]] = {
        "Name": definition["Name"],
        "ticker": definition["ticker"],
        "constituents": definition["constituents"],
        "IsCustom": True,
    }

    bucket_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = bucket_file.with_suffix(f"{bucket_file.suffix}.tmp")
    with temporary_file.open("w", encoding="utf-8") as handle:
        json.dump(buckets, handle, indent=2)
        handle.write("\n")
    temporary_file.replace(bucket_file)


def ensure_metadata_index(es: Elasticsearch = ES) -> None:
    if not es.indices.exists(index=META_INDEX):
        es.indices.create(index=META_INDEX, body=METADATA_MAPPING)


def persist_custom_bucket(
    definition: dict[str, Any], es: Elasticsearch = ES
) -> None:
    """Upsert a bucket definition into the canonical ``indices`` metadata index."""
    ensure_metadata_index(es)
    es.index(
        index=META_INDEX,
        id=definition["id"],
        document=definition,
        refresh="wait_for",
    )


def get_custom_indices(es: Elasticsearch = ES) -> list[dict[str, Any]]:
    query = {
        "_source": ["ticker", "Name", "constituents"],
        "query": {"term": {"IsCustom": True}},
    }
    response = es.search(index=META_INDEX, body=query, size=500)
    return [hit["_source"] for hit in response["hits"]["hits"]]


def fetch_ohlcv_for_constituents(
    tickers: list[str], es: Elasticsearch = ES
) -> pd.DataFrame:
    """Fetch all available constituent candles, not merely Elasticsearch's first page."""
    query = {
        "_source": ["ticker", "close", "open", "high", "low", "volume", "date"],
        "query": {"bool": {"must": [{"terms": {"ticker": tickers}}]}},
    }
    records = [
        hit["_source"]
        for hit in helpers.scan(es, index=SRC_INDEX, query=query, size=1_000)
    ]
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["ticker", "date"])


def calculate_equal_weight_index(df: pd.DataFrame, ticker: str) -> list[dict[str, Any]]:
    """Build the historical equal-weight OHLC series used by the existing indexes."""
    if df.empty:
        return []

    result: list[dict[str, Any]] = []
    previous_close_by_ticker: dict[str, float | None] = {
        constituent: None for constituent in df["ticker"].unique()
    }

    for date, group in df.groupby("date", sort=True):
        returns = {"open": [], "high": [], "low": [], "close": []}
        total_volume = 0

        for _, row in group.iterrows():
            constituent = row["ticker"]
            previous_close = previous_close_by_ticker[constituent]
            if previous_close is None:
                previous_close = row["close"]

            for price_field in returns:
                returns[price_field].append((row[price_field] / previous_close) - 1)

            total_volume += int(row["volume"])
            previous_close_by_ticker[constituent] = row["close"]

        previous_index_close = result[-1]["close"] if result else BASE_VALUE
        index_values = {
            price_field: round(
                previous_index_close * (1 + (sum(values) / len(values))), 2
            )
            for price_field, values in returns.items()
        }

        result.append(
            {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "ticker": ticker,
                "open": index_values["open"],
                "high": index_values["high"],
                "low": index_values["low"],
                "close": index_values["close"],
                "volume": total_volume,
                "type": "index",
                "isCustom": True,
            }
        )

    return result


def _to_technical_index_frame(
    candles: list[dict[str, Any]], ticker: str
) -> pd.DataFrame:
    """Adapt generated candles to the existing technical indexer input schema."""
    frame = pd.DataFrame(candles).rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame["Ticker"] = ticker
    frame["indices"] = [[] for _ in range(len(frame))]
    frame["type"] = "index"
    frame["isCustom"] = True
    return frame


def _load_technical_indexer() -> Callable[..., None]:
    """Load the established indicator calculation without duplicating its rules."""
    technical_charts_dir = Path(__file__).resolve().parents[1] / "technicalCharts"
    directory = str(technical_charts_dir)
    if directory not in sys.path:
        sys.path.insert(0, directory)

    from indexer import index_data  # pylint: disable=import-outside-toplevel

    return index_data


def index_custom_index(
    candles: list[dict[str, Any]],
    ticker: str,
    index_data_fn: Callable[..., None] | None = None,
) -> None:
    """Index custom candles with the macTesting technical-indicator pipeline."""
    if not candles:
        return

    technical_frame = _to_technical_index_frame(candles, ticker)
    (index_data_fn or _load_technical_indexer())(SRC_INDEX, technical_frame, ticker)
    print(f"✔ Indexed {len(candles)} candles and technical fields for {ticker}")


def build_and_index_custom_bucket(
    definition: dict[str, Any], es: Elasticsearch = ES
) -> int:
    constituents = definition["constituents"]
    ticker = definition["ticker"]
    print(f"\n📍 Building custom index: {ticker}")
    print(f"  → Constituents: {len(constituents)}")

    data = fetch_ohlcv_for_constituents(constituents, es)
    if data.empty:
        print(f"❌ No OHLCV found for {ticker}")
        return 0

    candles = calculate_equal_weight_index(data, ticker)
    index_custom_index(candles, ticker)
    return len(candles)


def register_and_build_custom_bucket(
    definition: dict[str, Any],
    bucket_file: Path = DEFAULT_BUCKET_FILE,
    es: Elasticsearch = ES,
) -> int:
    save_custom_bucket_definition(definition, bucket_file)
    persist_custom_bucket(definition, es)
    return build_and_index_custom_bucket(definition, es)


def rebuild_all_custom_indices(es: Elasticsearch = ES) -> int:
    custom_indices = get_custom_indices(es)
    print(f"Found {len(custom_indices)} custom indices")
    built = 0

    for index_definition in custom_indices:
        built += int(build_and_index_custom_bucket(index_definition, es) > 0)

    print(f"\n🎯 Completed {built} custom index generation(s)!")
    return built


def _constituents_from_file(constituents_file: Path) -> list[str]:
    content = constituents_file.read_text(encoding="utf-8")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return [line.strip() for line in content.splitlines() if line.strip()]

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("constituents"), list):
        return parsed["constituents"]
    raise ValueError(
        "Constituent file must be a JSON list, a JSON object with a "
        "'constituents' list, or a newline-separated text file."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save and materialise a custom equal-weight index bucket."
    )
    parser.add_argument("--all", action="store_true", help="Rebuild all saved custom buckets")
    parser.add_argument("--name", help="Readable bucket name, for example 'AI Leaders'")
    parser.add_argument("--ticker", help="Synthetic ticker, for example '^AI_LEADERS'")
    parser.add_argument(
        "--constituents",
        action="append",
        default=[],
        help="Comma-separated constituent tickers; may be supplied more than once",
    )
    parser.add_argument(
        "--constituents-file",
        type=Path,
        help="JSON/list or newline-delimited constituent ticker file",
    )
    parser.add_argument(
        "--bucket-file",
        type=Path,
        default=DEFAULT_BUCKET_FILE,
        help=f"Persistent bucket definition file (default: {DEFAULT_BUCKET_FILE})",
    )
    args = parser.parse_args(argv)

    has_definition_input = bool(
        args.name or args.ticker or args.constituents or args.constituents_file
    )
    if args.all and has_definition_input:
        parser.error("--all cannot be combined with a new bucket definition")
    if not args.all and not (args.name and args.ticker):
        parser.error("provide --all or a new bucket with --name and --ticker")
    if not args.all and not (args.constituents or args.constituents_file):
        parser.error("a new bucket needs --constituents or --constituents-file")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all:
        rebuild_all_custom_indices()
        return 0

    constituents = list(args.constituents)
    if args.constituents_file:
        constituents.extend(_constituents_from_file(args.constituents_file))

    definition = build_custom_bucket_definition(args.name, args.ticker, constituents)
    candle_count = register_and_build_custom_bucket(definition, args.bucket_file)
    print(
        f"🎯 Saved {definition['ticker']} and materialised {candle_count} custom index candles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
