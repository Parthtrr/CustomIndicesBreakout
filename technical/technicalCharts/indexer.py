import pandas as pd
from elasticsearch import helpers

from Constant import rsi_window, roc_period, atr_period
from elastic_client import get_es_client
from logging_config import get_logger
from mappings import index_mapping
import numpy as np

logger = get_logger(__name__)


# ================= INDICATORS ================= #
def calculate_rsi(data, period):
    data = data.copy()

    # Drop rows where Close is NaN (only for calculation)
    valid_data = data[data["Close"].notna()].copy()

    # If not enough data, return original with NaN RSI
    if len(valid_data) <= period:
        data["rsi"] = np.nan
        return data

    valid_data["change"] = valid_data["Close"].diff()
    valid_data["gain"] = valid_data["change"].clip(lower=0)
    valid_data["loss"] = -valid_data["change"].clip(upper=0)

    valid_data["avg_gain"] = np.nan
    valid_data["avg_loss"] = np.nan

    # First SMA
    valid_data.iloc[period, valid_data.columns.get_loc("avg_gain")] = \
        valid_data["gain"].iloc[1:period+1].mean()

    valid_data.iloc[period, valid_data.columns.get_loc("avg_loss")] = \
        valid_data["loss"].iloc[1:period+1].mean()

    # Wilder smoothing
    for i in range(period + 1, len(valid_data)):
        valid_data.iloc[i, valid_data.columns.get_loc("avg_gain")] = (
            (valid_data.iloc[i-1]["avg_gain"] * (period - 1)
             + valid_data.iloc[i]["gain"]) / period
        )

        valid_data.iloc[i, valid_data.columns.get_loc("avg_loss")] = (
            (valid_data.iloc[i-1]["avg_loss"] * (period - 1)
             + valid_data.iloc[i]["loss"]) / period
        )

    valid_data["rs"] = valid_data["avg_gain"] / valid_data["avg_loss"]
    valid_data["rsi"] = 100 - (100 / (1 + valid_data["rs"]))

    # Merge back into original dataframe
    data["rsi"] = valid_data["rsi"]

    return data


def calculate_atr(data, period):
    # data = data.copy()

    data["high_low"] = data["High"] - data["Low"]
    data["high_close_prev"] = (data["High"] - data["Close"].shift()).abs()
    data["low_close_prev"] = (data["Low"] - data["Close"].shift()).abs()

    data["tr"] = data[["high_low", "high_close_prev", "low_close_prev"]].max(axis=1)
    data["atr"] = data["tr"].rolling(period).mean()
    data["atr"] = data["atr"].fillna(0.0)

    return data


def calculate_roc(data, period):
    # data = data.copy()
    data["roc"] = data["Close"].pct_change(periods=period, fill_method=None) * 100
    data["roc"] = data["roc"].fillna(0.0)
    return data


def calculate_ma(data, ma_period, ma_type="sma"):
    # data = data.copy()
    col = f"ma_{ma_period}"

    if ma_type == "sma":
        data[col] = data["Close"].rolling(ma_period).mean()
    elif ma_type == "ema":
        data[col] = data["Close"].ewm(span=ma_period, adjust=False).mean()
    else:
        raise ValueError("ma_type must be sma or ema")

    data[col] = data[col].fillna(0.0)
    return data


def calculate_ma_crossover_flags(data):
    # data = data.copy()

    data["ma_10_above_30"] = data["ma_10"] > data["ma_30"]
    data["ma_30_above_40"] = data["ma_30"] > data["ma_40"]
    data["ma_10_above_40"] = data["ma_10"] > data["ma_40"]

    # Trend classification
    data["trend"] = "sideways"
    data.loc[(data["ma_10_above_30"]) & (data["ma_30_above_40"]), "trend"] = "bullish"
    data.loc[(~data["ma_10_above_30"]) & (~data["ma_30_above_40"]), "trend"] = "bearish"

    return data

def calculate_52w_high_low(data, window=52):
    """
    For weekly candles: 52 candles = 52 weeks = 1 year
    """
    # data = data.copy()

    data["high_52w"] = data["High"].rolling(window=window, min_periods=1).max()
    data["low_52w"] = data["Low"].rolling(window=window, min_periods=1).min()

    data["dist_from_52w_high_pct"] = ((data["Close"] - data["high_52w"]) / data["high_52w"].replace(0, pd.NA)) * 100
    data["dist_from_52w_low_pct"] = ((data["Close"] - data["low_52w"]) / data["low_52w"].replace(0, pd.NA)) * 100

    data[["high_52w","low_52w","dist_from_52w_high_pct","dist_from_52w_low_pct"]] = \
        data[["high_52w","low_52w","dist_from_52w_high_pct","dist_from_52w_low_pct"]].fillna(0.0)

    return data

def calculate_vcp_trend_template(data):
    """
    VCP Trend Template:
    - At least 30% above 52W low
    - At most 25% below 52W high
    - MA trend bullish (10 > 30 > 40)
    - Price above 30W and 40W MA
    """

    data["price_above_ma_30"] = data["Close"] > data["ma_30"]
    data["price_above_ma_40"] = data["Close"] > data["ma_40"]

    data["vcp_trend_template"] = (
        (data["dist_from_52w_low_pct"] >= 30) &
        (data["dist_from_52w_high_pct"] >= -25) &
        (data["trend"] == "bullish") &
        (data["price_above_ma_30"]) &
        (data["price_above_ma_40"])
    )

    return data





# ================= FULL BULK INDEX ================= #

def index_data(index_name, data, ticker, nifty_data=None, metadata=None):
    es = get_es_client()
    logger.info(f"Indexing stock = {ticker}")

    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=index_mapping)

    # Sort by date
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.sort_values("Date")

    # Indicators
    data = data.copy()
    data = calculate_atr(data, atr_period)
    data = calculate_rsi(data, rsi_window)
    data = calculate_roc(data, roc_period)

    for p in [10, 30, 40]:
        data = calculate_ma(data, p)

    data = calculate_ma_crossover_flags(data)
    data = calculate_52w_high_low(data)
    data = calculate_vcp_trend_template(data)

    data = data.copy()
    logger.info(f"demerger = {data._mgr.nblocks}")

    # NIFTY ROC merge
    if nifty_data is not None:
        nifty_data["Date"] = pd.to_datetime(nifty_data["Date"], errors="coerce")
        nifty_data = nifty_data.sort_values("Date")
        nifty_data = calculate_roc(nifty_data, roc_period)
        nifty_data.rename(columns={"roc": "roc_nifty"}, inplace=True)
        data = pd.merge(data, nifty_data[["Date", "roc_nifty"]], on="Date", how="left")
    else:
        # Custom indices are standalone baskets. They intentionally do not
        # depend on the stock pipeline's NIFTY benchmark series.
        data["roc_nifty"] = 0.0

    # Fill defaults
    data.fillna({
        "Open": 0.0, "Close": 0.0, "High": 0.0, "Low": 0.0, "Volume": 0,
        "rsi": 0.0, "roc": 0.0, "roc_nifty": 0.0, "atr": 0.0,
        "ma_10": 0.0, "ma_30": 0.0, "ma_40": 0.0,
        "ma_10_above_30": False, "ma_30_above_40": False, "ma_10_above_40": False,
        "trend": "sideways",
        "high_52w": 0.0,
        "low_52w": 0.0,
        "dist_from_52w_high_pct": 0.0,
        "dist_from_52w_low_pct": 0.0,
        "vcp_trend_template": False,
        "type": "stock", "isCustom": False
    }, inplace=True)

    def actions():
        for _, r in data.iterrows():
            if r["Open"] == 0:
                continue

            date = r["Date"].strftime("%Y-%m-%d")

            source = {
                "ticker": ticker,
                "date": date,
                "open": float(r["Open"]),
                "close": float(r["Close"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "volume": int(r["Volume"]),
                "rsi": float(r["rsi"]),
                "roc": float(r["roc"]),
                "roc_nifty": float(r["roc_nifty"]),
                "atr": float(r["atr"]),
                "ma_10": float(r["ma_10"]),
                "ma_30": float(r["ma_30"]),
                "ma_40": float(r["ma_40"]),
                "ma_10_above_30": bool(r["ma_10_above_30"]),
                "ma_30_above_40": bool(r["ma_30_above_40"]),
                "ma_10_above_40": bool(r["ma_10_above_40"]),
                "trend": r["trend"],
                "high_52w": float(r["high_52w"]),
                "low_52w": float(r["low_52w"]),
                "dist_from_52w_high_pct": float(r["dist_from_52w_high_pct"]),
                "dist_from_52w_low_pct": float(r["dist_from_52w_low_pct"]),
                "vcp_trend_template": bool(r["vcp_trend_template"]),
                "indices": r["indices"],
                "type": r["type"],
                "isCustom": r["isCustom"]
            }
            if metadata:
                source.update(metadata)

            yield {
                "_op_type": "index",
                "_index": index_name,
                "_id": f"{ticker}_{date}",
                "_source": source,
            }

    logger.info(f"demerger 2 = {data._mgr.nblocks}")
    helpers.bulk(es, actions(), raise_on_error=True)


# ================= INCREMENTAL INDEX ================= #

# def index_data_incremental(index_name, data, ticker, nifty_data=None):
#     es = get_es_client()
#     logger.info(f"Incremental indexing {ticker}")
#
#     if not es.indices.exists(index=index_name):
#         es.indices.create(index=index_name, body=index_mapping)
#
#     data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
#     data = data.sort_values("Date")
#
#     # Indicators
#     data = data.copy()
#     data = calculate_atr(data, atr_period)
#     data = calculate_rsi(data, rsi_window)
#     data = calculate_roc(data, roc_period)
#
#     for p in [10, 30, 40]:
#         data = calculate_ma(data, p)
#
#     data = calculate_ma_crossover_flags(data)
#     data = calculate_52w_high_low(data)
#
#     data = data.copy()
#     logger.info(f"demerger = {data._mgr.nblocks}")
#
#     # NIFTY ROC
#     if nifty_data is not None:
#         nifty_data["Date"] = pd.to_datetime(nifty_data["Date"], errors="coerce")
#         nifty_data = nifty_data.sort_values("Date")
#         nifty_data = calculate_roc(nifty_data, roc_period)
#         nifty_data.rename(columns={"roc": "roc_nifty"}, inplace=True)
#         data = pd.merge(data, nifty_data[["Date", "roc_nifty"]], on="Date", how="left")
#
#     # Only last 5 rows
#     data = data.tail(5)
#
#     def actions():
#         for _, r in data.iterrows():
#             date = r["Date"].strftime("%Y-%m-%d")
#             doc = {}
#
#             for f in ["Open","Close","High","Low","Volume","rsi","roc","roc_nifty","atr","ma_10","ma_30","ma_40","high_52w","low_52w","dist_from_52w_high_pct","dist_from_52w_low_pct"]:
#                 if pd.isna(r[f]) or r[f] == 0:
#                     continue
#                 doc[f.lower()] = float(r[f]) if isinstance(r[f], float) else int(r[f])
#
#             # booleans + trend
#             doc["ma_10_above_30"] = bool(r["ma_10_above_30"])
#             doc["ma_30_above_40"] = bool(r["ma_30_above_40"])
#             doc["ma_10_above_40"] = bool(r["ma_10_above_40"])
#             doc["trend"] = r["trend"]
#
#             doc["ticker"] = ticker
#             doc["date"] = date
#
#             yield {
#                 "_op_type": "update",
#                 "_index": index_name,
#                 "_id": f"{ticker}_{date}",
#                 "doc": doc,
#                 "doc_as_upsert": True
#             }
#
#     helpers.bulk(es, actions(), raise_on_error=True)
