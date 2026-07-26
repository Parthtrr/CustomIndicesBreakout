"""Rate-limited, in-memory Screener.in fundamentals for breakout constituents.

The custom-index pipeline intentionally does not index fundamental data.  This
module is used only while producing the Excel report, so every run fetches the
current values for the final breakout-constituent set and keeps them in memory
until the workbook is saved.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import Callable, Iterable
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup


SCREENER_CONSOLIDATED_URL = "https://www.screener.in/company/{ticker}/consolidated/"
SCREENER_STANDALONE_URL = "https://www.screener.in/company/{ticker}/"
DEFAULT_REQUEST_DELAY_SECONDS = 1.25
DEFAULT_TIMEOUT_SECONDS = 25
MAX_REQUEST_ATTEMPTS = 3
REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 "
        "CustomIndicesBreakout/1.0"
    ),
}


@dataclass(frozen=True)
class FundamentalMetrics:
    """The values displayed on the workbook's Fundamentals worksheet."""

    ticker: str
    screener_url: str = ""
    market_cap_cr: float | None = None
    stock_pe: float | None = None
    roce_pct: float | None = None
    roe_pct: float | None = None
    revenue_qoq_pct: float | None = None
    revenue_yoy_pct: float | None = None
    profit_qoq_pct: float | None = None
    profit_yoy_pct: float | None = None
    current_quarter_result_out: bool | None = None
    expected_result_quarter: str = ""
    latest_reported_quarter: str = ""
    screener_broad_sector: str = ""
    screener_sector: str = ""
    screener_industry: str = ""
    fetch_status: str = "Not fetched"


def screener_ticker(ticker: str) -> str:
    """Convert the Yahoo-normalised symbol used by the manifest to Screener's slug."""
    return ticker.removesuffix(".NS").removesuffix(".BO").strip()


def _safe_float(value: object) -> float | None:
    """Parse Screener's formatted numbers without turning unavailable values into zero."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    if not text or text.casefold() in {"-", "--", "na", "n/a"}:
        return None

    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text.replace("₹", ""))
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def calculate_growth(current: float | None, previous: float | None) -> float | None:
    """Match the Momentum framework's percentage-growth calculation."""
    if current is None or previous in (None, 0):
        return None
    return round(((current - previous) / previous) * 100, 2)


def current_result_period(as_of: date | None = None) -> date:
    """Return the latest completed quarter for which Indian results may be reported."""
    current_date = as_of or datetime.now().date()
    if current_date.month <= 3:
        return date(current_date.year - 1, 12, 1)
    if current_date.month <= 6:
        return date(current_date.year, 3, 1)
    if current_date.month <= 9:
        return date(current_date.year, 6, 1)
    return date(current_date.year, 9, 1)


def _display_quarter(period: date) -> str:
    return period.strftime("%b %Y")


def _parse_quarter_label(value: object) -> date | None:
    text = str(value).replace("\xa0", " ").strip()
    for pattern in ("%b %Y", "%B %Y"):
        try:
            return datetime.strptime(text, pattern).date().replace(day=1)
        except ValueError:
            continue
    return None


def _normalise_metric(value: object) -> str:
    return str(value).replace("\xa0", " ").replace("+", "").strip()


def _parse_top_ratios(soup: BeautifulSoup) -> dict[str, float | None]:
    ratios: dict[str, float | None] = {}
    for item in soup.select("ul#top-ratios li"):
        name = item.select_one("span.name")
        value = item.select_one("span.number")
        if name is None:
            continue
        ratios[name.get_text(" ", strip=True).casefold()] = _safe_float(
            value.get_text(" ", strip=True) if value is not None else None
        )
    return ratios


def _parse_sector_hierarchy(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Return Screener's broad sector, sector, and industry where available."""
    peer_section = soup.select_one("section#peers p.sub")
    if peer_section is None:
        return "", "", ""

    values = [link.get_text(" ", strip=True) for link in peer_section.find_all("a")]
    broad_sector = values[0] if len(values) >= 1 else ""
    sector = values[1] if len(values) >= 2 else ""
    industry = values[3] if len(values) >= 4 else (values[-1] if values else "")
    return broad_sector, sector, industry


def _parse_quarterly_table(
    soup: BeautifulSoup, as_of: date | None = None
) -> tuple[dict[str, float], str, bool | None]:
    """Extract quarterly growth and result availability from Screener's table."""
    table = soup.select_one("section#quarters table")
    if table is None:
        raise ValueError("Quarterly results table not found")

    dataframe = pd.read_html(StringIO(str(table)), header=0)[0]
    if dataframe.empty or len(dataframe.columns) < 2:
        raise ValueError("Quarterly results table has no period columns")

    first_column = dataframe.columns[0]
    dataframe = dataframe.rename(columns={first_column: "metric"})
    dataframe["metric"] = dataframe["metric"].map(_normalise_metric)

    periods: list[tuple[date, object]] = []
    for column in dataframe.columns[1:]:
        quarter = _parse_quarter_label(column)
        if quarter is not None:
            periods.append((quarter, column))
    periods.sort(key=lambda item: item[0])
    if not periods:
        raise ValueError("Quarterly results table has no dated quarter columns")

    def metric_values(metric_names: set[str]) -> dict[date, float | None]:
        matches = dataframe[dataframe["metric"].isin(metric_names)]
        if matches.empty:
            return {}
        row = matches.iloc[0]
        return {quarter: _safe_float(row[column]) for quarter, column in periods}

    revenue = metric_values({"Sales", "Revenue"})
    profit = metric_values({"Net Profit"})
    eps = metric_values({"EPS in Rs"})

    complete_periods = [
        quarter
        for quarter, _ in periods
        if revenue.get(quarter) is not None
        and profit.get(quarter) is not None
        and eps.get(quarter) is not None
    ]
    latest_reported = _display_quarter(complete_periods[-1]) if complete_periods else ""

    values: dict[str, float] = {}
    if len(complete_periods) >= 5:
        latest, prior, year_ago = complete_periods[-1], complete_periods[-2], complete_periods[-5]
        growth_values = {
            "revenue_qoq_pct": calculate_growth(revenue[latest], revenue[prior]),
            "revenue_yoy_pct": calculate_growth(revenue[latest], revenue[year_ago]),
            "profit_qoq_pct": calculate_growth(profit[latest], profit[prior]),
            "profit_yoy_pct": calculate_growth(profit[latest], profit[year_ago]),
        }
        values = {
            name: growth
            for name, growth in growth_values.items()
            if growth is not None
        }

    expected_period = current_result_period(as_of)
    result_out = (
        revenue.get(expected_period) is not None
        and profit.get(expected_period) is not None
        and eps.get(expected_period) is not None
    )
    return values, latest_reported, result_out


def parse_screener_html(
    ticker: str,
    html: str,
    screener_url: str,
    *,
    as_of: date | None = None,
) -> FundamentalMetrics:
    """Parse one Screener page into only the report's required metrics."""
    soup = BeautifulSoup(html, "html.parser")
    ratios = _parse_top_ratios(soup)
    quarterly_values, latest_reported, result_out = _parse_quarterly_table(soup, as_of)
    broad_sector, sector, industry = _parse_sector_hierarchy(soup)

    return FundamentalMetrics(
        ticker=ticker,
        screener_url=screener_url,
        market_cap_cr=ratios.get("market cap"),
        stock_pe=ratios.get("stock p/e"),
        roce_pct=ratios.get("roce"),
        roe_pct=ratios.get("roe"),
        revenue_qoq_pct=quarterly_values.get("revenue_qoq_pct"),
        revenue_yoy_pct=quarterly_values.get("revenue_yoy_pct"),
        profit_qoq_pct=quarterly_values.get("profit_qoq_pct"),
        profit_yoy_pct=quarterly_values.get("profit_yoy_pct"),
        current_quarter_result_out=result_out,
        expected_result_quarter=_display_quarter(current_result_period(as_of)),
        latest_reported_quarter=latest_reported,
        screener_broad_sector=broad_sector,
        screener_sector=sector,
        screener_industry=industry,
        fetch_status="Retrieved",
    )


class ScreenerFundamentalsClient:
    """Polite sequential Screener client with a minimum delay between requests."""

    def __init__(
        self,
        *,
        delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be zero or positive")
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.sleep = sleep
        self.monotonic = monotonic
        self._next_request_at = 0.0

    def _wait_for_request_slot(self) -> None:
        remaining = self._next_request_at - self.monotonic()
        if remaining > 0:
            self.sleep(remaining)

    def _get(self, url: str) -> requests.Response:
        last_error: requests.RequestException | None = None
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            self._wait_for_request_slot()
            try:
                response = self.session.get(
                    url,
                    headers=REQUEST_HEADERS,
                    timeout=self.timeout_seconds,
                )
                self._next_request_at = self.monotonic() + self.delay_seconds
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                        self.sleep(self.delay_seconds * (attempt + 1))
                        continue
                response.raise_for_status()
                return response
            except requests.RequestException as error:
                last_error = error
                if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                    self.sleep(self.delay_seconds * (attempt + 1))

        raise last_error or requests.RequestException("Screener request failed")

    def fetch(self, ticker: str) -> FundamentalMetrics:
        slug = screener_ticker(ticker)
        if not slug:
            return FundamentalMetrics(ticker=ticker, fetch_status="Unavailable: blank ticker")

        urls = (
            SCREENER_CONSOLIDATED_URL.format(ticker=quote(slug, safe="")),
            SCREENER_STANDALONE_URL.format(ticker=quote(slug, safe="")),
        )
        last_error: Exception | None = None
        for position, url in enumerate(urls):
            try:
                parsed = parse_screener_html(ticker, self._get(url).text, url)
                if position:
                    return FundamentalMetrics(
                        **{**parsed.__dict__, "fetch_status": "Retrieved (standalone fallback)"}
                    )
                return parsed
            except (requests.RequestException, ValueError, pd.errors.EmptyDataError) as error:
                last_error = error

        detail = "Screener page unavailable"
        if isinstance(last_error, requests.HTTPError) and last_error.response is not None:
            detail = f"Screener HTTP {last_error.response.status_code}"
        return FundamentalMetrics(
            ticker=ticker,
            screener_url=urls[0],
            expected_result_quarter=_display_quarter(current_result_period()),
            fetch_status=f"Unavailable: {detail}",
        )


def fetch_constituent_fundamentals(
    tickers: Iterable[str],
    *,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, FundamentalMetrics]:
    """Fetch each unique constituent once, sequentially, with no persistent cache."""
    client = ScreenerFundamentalsClient(
        delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds,
    )
    metrics_by_ticker: dict[str, FundamentalMetrics] = {}
    for ticker in tickers:
        if ticker not in metrics_by_ticker:
            metrics_by_ticker[ticker] = client.fetch(ticker)
    return metrics_by_ticker
