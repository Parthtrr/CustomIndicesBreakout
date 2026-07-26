"""Build daily-rebalanced TradingView basket indices and index weekly candles.

The checked-in manifest contains the exact TradingView equal-weight equations,
their constituent metadata, and source provenance.  Runtime execution never
requires the local source Excel directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf
from elasticsearch import Elasticsearch


BASE_VALUE = 1000.0
ES_HOST = "http://localhost:9200"
TARGET_INDEX = "nifty_custom_index_breakout"
DEFAULT_START_DATE = "2010-01-01"
DEFAULT_DEFINITION_FILE = Path(__file__).with_name("data") / "tradingview_index_definitions.json"
INDEX_FORMULA = (
    "Base 1000; each trading day the index return is the arithmetic mean of "
    "available constituent OHLC returns versus the prior close; weekly OHLC "
    "is aggregated from the resulting daily index candles."
)


@dataclass(frozen=True)
class CustomIndexDefinition:
    """A custom sector or industry basket stored in the checked-in manifest."""

    ticker: str
    index_name: str
    sector_or_industry: str
    classification_type: str
    source_file: str
    constituents: tuple[str, ...]
    definition_id: str = ""
    tradingview_equation: str = ""
    source_files: tuple[str, ...] = ()
    constituent_details: tuple[dict[str, object], ...] = ()

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "index_name": self.index_name,
            "sector_or_industry": self.sector_or_industry,
            "classification_type": self.classification_type,
            "source_file": self.source_file,
            "source_files": list(self.source_files),
            "definition_id": self.definition_id,
            "tradingview_equation": self.tradingview_equation,
            "index_formula": self.tradingview_equation or INDEX_FORMULA,
            "calculation_formula": INDEX_FORMULA,
            "calculation_method": "equal_weight",
            "rebalance_frequency": "daily",
            "constituents": list(self.constituents),
            "constituent_count": len(self.constituents),
            "constituent_details": list(self.constituent_details),
        }


def normalise_ticker(raw_ticker: object) -> str | None:
    """Convert a manifest ticker to the Yahoo Finance NSE/BSE symbol format."""
    if raw_ticker is None or pd.isna(raw_ticker):
        return None

    ticker = str(raw_ticker).strip().upper()
    if not ticker or ticker == "NAN":
        return None
    if re.fullmatch(r"\d+\.0", ticker):
        ticker = ticker[:-2]
    if ticker.endswith((".NS", ".BO")):
        return ticker
    if re.fullmatch(r"\d{6}", ticker):
        return f"{ticker}.BO"
    return f"{ticker}.NS"


def load_index_definitions(
    definition_file: Path = DEFAULT_DEFINITION_FILE,
) -> list[CustomIndexDefinition]:
    """Load the checked-in, source-path-independent TradingView definitions."""
    if not definition_file.is_file():
        raise ValueError(f"TradingView definition manifest not found: {definition_file}")

    payload = json.loads(definition_file.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported TradingView definition manifest schema")

    definitions: list[CustomIndexDefinition] = []
    ids: set[str] = set()
    for raw_definition in payload.get("definitions", []):
        definition_id = str(raw_definition.get("id", "")).strip()
        if not definition_id or definition_id in ids:
            raise ValueError(f"TradingView definition id is missing or duplicated: {definition_id!r}")
        ids.add(definition_id)

        constituent_details = tuple(raw_definition.get("constituents", []))
        constituents = tuple(
            dict.fromkeys(
                ticker
                for detail in constituent_details
                if (ticker := normalise_ticker(detail.get("yahoo_symbol"))) is not None
            )
        )
        if not constituents:
            raise ValueError(f"{definition_id} has no usable Yahoo Finance constituents")

        provenance = raw_definition.get("provenance", [])
        source_files = tuple(
            dict.fromkeys(
                str(item.get("workbook", "")).strip()
                for item in provenance
                if str(item.get("workbook", "")).strip()
            )
        )
        definitions.append(
            CustomIndexDefinition(
                ticker=f"CUSTOM_{definition_id}",
                index_name=str(raw_definition["index_name"]),
                sector_or_industry=str(raw_definition["sector_or_industry"]),
                classification_type=str(raw_definition["classification_type"]),
                source_file=definition_file.name,
                constituents=constituents,
                definition_id=definition_id,
                tradingview_equation=str(raw_definition["tradingview_equation"]),
                source_files=source_files,
                constituent_details=constituent_details,
            )
        )

    if not definitions:
        raise ValueError("TradingView definition manifest has no usable basket definitions")
    return definitions


def _chunks(items: Iterable[str], size: int) -> Iterable[list[str]]:
    values = list(items)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _extract_downloaded_ticker(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        level_zero = data.columns.get_level_values(0)
        level_one = data.columns.get_level_values(1)
        if ticker in level_zero:
            frame = data.xs(ticker, axis=1, level=0).copy()
        elif ticker in level_one:
            frame = data.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        frame = data.copy()

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not set(required).issubset(frame.columns):
        return pd.DataFrame()

    frame = frame[required].apply(pd.to_numeric, errors="coerce").dropna(how="all")
    frame.index = pd.to_datetime(frame.index)
    return frame.sort_index()


def download_daily_ohlcv(
    tickers: Iterable[str], start_date: str, end_date: str, batch_size: int
) -> dict[str, pd.DataFrame]:
    """Download daily price data once for the union of all basket members."""
    market_data: dict[str, pd.DataFrame] = {}
    unique_tickers = sorted(set(tickers))

    for batch in _chunks(unique_tickers, batch_size):
        print(f"Downloading {len(batch)} constituents ({batch[0]} … {batch[-1]})")
        try:
            downloaded = yf.download(
                batch,
                start=start_date,
                end=end_date,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            print(f"Download failed for batch starting {batch[0]}: {exc}", file=sys.stderr)
            continue

        for ticker in batch:
            ticker_data = _extract_downloaded_ticker(downloaded, ticker)
            if not ticker_data.empty:
                market_data[ticker] = ticker_data

    return market_data


def calculate_daily_equal_weight_index(
    definition: CustomIndexDefinition, market_data: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """Calculate a daily rebalanced equal-weight OHLC index from constituents."""
    constituent_data = {
        ticker: market_data[ticker]
        for ticker in definition.constituents
        if ticker in market_data and not market_data[ticker].empty
    }
    if not constituent_data:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    dates = sorted(set().union(*(frame.index for frame in constituent_data.values())))
    previous_closes: dict[str, float | None] = {ticker: None for ticker in constituent_data}
    candles: list[dict[str, object]] = []

    for current_date in dates:
        daily_returns = {field: [] for field in ("Open", "High", "Low", "Close")}
        total_volume = 0

        for ticker, frame in constituent_data.items():
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            values = {field: float(row[field]) for field in daily_returns}
            if any(pd.isna(value) or value <= 0 for value in values.values()):
                continue

            previous_close = previous_closes[ticker]
            if previous_close is None or previous_close <= 0:
                previous_close = values["Close"]

            for field, value in values.items():
                daily_returns[field].append((value / previous_close) - 1)
            total_volume += int(row["Volume"]) if pd.notna(row["Volume"]) else 0
            previous_closes[ticker] = values["Close"]

        if not daily_returns["Close"]:
            continue

        previous_index_close = float(candles[-1]["Close"]) if candles else BASE_VALUE
        index_values = {
            field: previous_index_close * (1 + (sum(returns) / len(returns)))
            for field, returns in daily_returns.items()
        }
        candles.append(
            {
                "Date": pd.Timestamp(current_date),
                "Open": index_values["Open"],
                "High": index_values["High"],
                "Low": index_values["Low"],
                "Close": index_values["Close"],
                "Volume": total_volume,
            }
        )

    return pd.DataFrame(candles)


def aggregate_to_weekly(daily_candles: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Monday-to-date weekly candles, including the active week."""
    if daily_candles.empty:
        return daily_candles.copy()

    daily = daily_candles.copy()
    daily["Date"] = pd.to_datetime(daily["Date"])
    daily["WeekStart"] = daily["Date"] - pd.to_timedelta(daily["Date"].dt.weekday, unit="d")
    weekly = (
        daily.groupby("WeekStart", sort=True)
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        .reset_index()
        .rename(columns={"WeekStart": "Date"})
    )
    return weekly


def _to_technical_frame(weekly_candles: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frame = weekly_candles.copy()
    frame["Ticker"] = ticker
    frame["indices"] = [[] for _ in range(len(frame))]
    frame["type"] = "index"
    frame["isCustom"] = True
    return frame


def _load_technical_indexer():
    technical_charts_dir = Path(__file__).resolve().parents[1] / "technicalCharts"
    if str(technical_charts_dir) not in sys.path:
        sys.path.insert(0, str(technical_charts_dir))
    from indexer import index_data  # pylint: disable=import-outside-toplevel

    return index_data


def index_custom_index(definition: CustomIndexDefinition, weekly_candles: pd.DataFrame) -> int:
    """Calculate shared technical fields and write a custom index to ES."""
    if weekly_candles.empty:
        return 0

    _load_technical_indexer()(
        TARGET_INDEX,
        _to_technical_frame(weekly_candles, definition.ticker),
        definition.ticker,
        metadata=definition.metadata,
    )
    return len(weekly_candles)


def reset_target_index() -> None:
    es = Elasticsearch(ES_HOST)
    if es.indices.exists(index=TARGET_INDEX):
        es.indices.delete(index=TARGET_INDEX)
        print(f"Deleted existing Elasticsearch index: {TARGET_INDEX}")


def build_and_index_all(
    definition_file: Path,
    start_date: str,
    end_date: str,
    batch_size: int,
    reset: bool,
) -> dict[str, int]:
    definitions = load_index_definitions(definition_file)
    if reset:
        reset_target_index()

    all_tickers = [ticker for definition in definitions for ticker in definition.constituents]
    market_data = download_daily_ohlcv(all_tickers, start_date, end_date, batch_size)
    summary = {"definitions": len(definitions), "downloaded_constituents": len(market_data), "indexed_indices": 0, "indexed_candles": 0}

    for definition in definitions:
        daily_candles = calculate_daily_equal_weight_index(definition, market_data)
        weekly_candles = aggregate_to_weekly(daily_candles)
        candle_count = index_custom_index(definition, weekly_candles)
        if candle_count:
            summary["indexed_indices"] += 1
            summary["indexed_candles"] += candle_count
            print(f"Indexed {definition.index_name}: {candle_count} weekly candles")
        else:
            print(f"No usable market data for {definition.index_name}", file=sys.stderr)

    # The caller may invoke the enricher immediately after this command.
    # Explicit refresh removes the normal Elasticsearch refresh-interval race.
    Elasticsearch(ES_HOST).indices.refresh(index=TARGET_INDEX)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and index all custom sector/industry indices.")
    parser.add_argument(
        "--definition-file",
        type=Path,
        default=DEFAULT_DEFINITION_FILE,
        help="Checked-in TradingView basket definition manifest.",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument(
        "--end-date",
        default=(date.today() + timedelta(days=1)).isoformat(),
        help="Exclusive Yahoo Finance end date; defaults to tomorrow so the active week is included.",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--reset", action="store_true", help="Delete and rebuild only the dedicated target index.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least one")
    summary = build_and_index_all(
        definition_file=args.definition_file,
        start_date=args.start_date,
        end_date=args.end_date,
        batch_size=args.batch_size,
        reset=args.reset,
    )
    print("Custom-index indexing complete:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
