from elasticsearch import Elasticsearch
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
# ==========================================================
# CONFIG
# ==========================================================

from datetime import datetime, timedelta, timezone

# ==========================================================
# FILE NAME AS CURRENT WEEK FRIDAY (IST)
# Format: 7_FEB_2026.xlsx
# Works correctly in Docker (UTC → IST conversion)
# ==========================================================

IST = timezone(timedelta(hours=5, minutes=30))

def get_current_week_friday_ist():
    # Current time in IST
    today = datetime.now(IST)

    # Monday = 0, Friday = 4
    days_to_friday = 4 - today.weekday()

    # If today is Saturday (5) or Sunday (6), move to next Friday
    if days_to_friday < 0:
        days_to_friday += 7

    friday = today + timedelta(days=days_to_friday)

    # Format: 7_FEB_2026
    return friday.strftime("%-d_%b_%Y").upper()

# Final output file
OUTPUT_FILE = f"{get_current_week_friday_ist()}.xlsx"

print(f"📁 Output File (IST): {OUTPUT_FILE}")
ES_HOST = "http://localhost:9200"
TECH_INDEX = "nifty_data_weekly"
FUND_INDEX = "nifty_fundamental"

es = Elasticsearch(ES_HOST)

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

df_indices = pd.DataFrame({
    "Index Name": [
        "USDINR", "XAUINRG", "XAGINRK", "NASDAQ 100",
        "NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250", "NIFTY BANK",
        "NIFTY PRIVATE BANK", "NIFTY PSU BANK",
        "NIFTY FINANCIAL SERVICES", "NIFTY FMCG",
        "NIFTY IT", "NIFTY AUTO", "NIFTY METAL",
        "NIFTY PHARMA", "NIFTY HEALTHCARE",
        "NIFTY REALTY", "NIFTY MEDIA",
        "NIFTY CONSUMER DURABLES", "NIFTY OIL & GAS",
        "NIFTY CHEMICAL", "NIFTY DEFENCE",
        "NIFTY DIGITAL INDIA", "NIFTY EV",
        "NIfty Energy"
    ],
    "STATUS": ["" for _ in range(27)]
})

df_indices = pd.DataFrame({
    "Index Name": [
        "USDINR", "XAUINRG", "XAGINRK", "NASDAQ 100",
        "NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250", "NIFTY BANK",
        "NIFTY PRIVATE BANK", "NIFTY PSU BANK",
        "NIFTY FINANCIAL SERVICES", "NIFTY FMCG",
        "NIFTY IT", "NIFTY AUTO", "NIFTY METAL",
        "NIFTY PHARMA", "NIFTY HEALTHCARE",
        "NIFTY REALTY", "NIFTY MEDIA",
        "NIFTY CONSUMER DURABLES", "NIFTY OIL & GAS",
        "NIFTY CHEMICAL", "NIFTY DEFENCE",
        "NIFTY DIGITAL INDIA", "NIFTY EV",
        "NIfty Energy"
    ],
    "STATUS": ["" for _ in range(27)]
})

# ==========================================================
# STATIC DATA — MUTUAL FUND
# ==========================================================

df_mf = pd.DataFrame({
    "Indices": [
        "NIFTY 50",
        "NIFTY Mid cap 150",
        "NIFTY Small cap 250",
        "NIFTY Financial Services",
        "NIFTY India Digital",
        "NIFTY India Healthcare"
    ],
    "Benchmark RSI": [40, 39, 38, 41, 32, 37],
    "Current RSI": [53.26, 52.89, 42.02, 58.19, 39.91, 43.73],
    "Mutual fund to invest": [
        "Parag Parikh Flexi Cap Fund Direct Growth",
        "HDFC Mid Cap Fund Direct Growth",
        "Nippon India Small Cap Fund direct growth",
        "SBI Banking & Financial Services Fund",
        "Tata Digital India Fund",
        "ICICI Prudential Pharma Healthcare & Diagnostics Fund"
    ]
})

def get_latest_monday():
    today = datetime.today()
    # Monday = 0, Sunday = 6
    days_since_monday = today.weekday()
    latest_monday = today - timedelta(days=days_since_monday)
    return latest_monday.strftime("%Y-%m-%d")

SCAN_DATE = get_latest_monday()

print(f"📅 Scan Date (Latest Monday): {SCAN_DATE}")

def calculate_growth(current, previous):
    if previous in [0, None]:
        return np.nan
    return round(((current - previous) / previous) * 100, 2)


def calculate_slope(values):
    if len(values) < 5:
        return np.nan
    x = np.arange(len(values))
    slope = np.polyfit(x, values, 1)[0]
    return round(slope, 2)


def get_current_result_period(today=None):
    today = today or datetime.now().date()

    # Results are announced for the latest completed quarter.
    if today.month <= 3:
        year = today.year - 1
        month = 12
    elif today.month <= 6:
        year = today.year
        month = 3
    elif today.month <= 9:
        year = today.year
        month = 6
    else:
        year = today.year
        month = 9

    return f"{year:04d}-{month:02d}"


def is_current_quarter_result_out(current_quarter_result, quarterly):
    if current_quarter_result is not None:
        return bool(current_quarter_result)

    expected_period = get_current_result_period()
    metrics_found = {
        row.get("metric")
        for row in quarterly or []
        if row.get("period_date") == expected_period
    }

    has_revenue = bool({"Sales", "Revenue"} & metrics_found)
    has_profit = "Net Profit" in metrics_found
    has_eps = "EPS in Rs" in metrics_found

    return has_revenue and has_profit and has_eps


SIGNAL_SHEET_COLUMNS = [
    "Ticker",
    "Support",
    "Resistance",
    "Close",
    "Sector",
    "Industry",
    "ROCE",
    "ROE",
    "Current_Quarter_Result_Out",
    "Sales_QoQ_%",
    "Profit_QoQ_%",
    "EPS_QoQ_%",
    "Sales_YoY_%",
    "Profit_YoY_%",
    "EPS_YoY_%",
    "Sales_Slope_5Q",
    "Profit_Slope_5Q",
    "Net_Score"
]


def prepare_signal_sheet(df):
    export_df = df.copy()

    if "Current_Quarter_Result_Out" not in export_df.columns:
        export_df["Current_Quarter_Result_Out"] = "No"

    return export_df.reindex(columns=SIGNAL_SHEET_COLUMNS)


# ==========================================================
# QUALITY SCORING
# ==========================================================

def score_roce(roce):
    if roce < 0:
        return -4
    elif 0 <= roce < 5:
        return -3
    elif 5 <= roce < 8:
        return -1
    elif 8 <= roce < 12:
        return 1
    elif 12 <= roce < 18:
        return 2
    elif 18 <= roce < 25:
        return 3
    else:
        return 4


def score_roe(roe):
    if roe < 0:
        return -3
    elif 0 <= roe < 8:
        return -1
    elif 8 <= roe < 15:
        return 1
    elif 15 <= roe < 20:
        return 2
    else:
        return 3


# ==========================================================
# FINAL NET SCORE
# ==========================================================

def calculate_net_score(row):

    score = 0

    # Earnings Momentum
    score += 1 if row["Sales_QoQ_%"] > 0 else -1
    score += 1 if row["Profit_QoQ_%"] > 0 else -1
    score += 1 if row["EPS_QoQ_%"] > 0 else -1

    score += 2 if row["Sales_YoY_%"] > 0 else -2
    score += 2 if row["Profit_YoY_%"] > 0 else -2
    score += 2 if row["EPS_YoY_%"] > 0 else -2

    score += 2 if row["Sales_Slope_5Q"] > 0 else -2
    score += 2 if row["Profit_Slope_5Q"] > 0 else -2

    # Quality
    score += score_roce(row["ROCE"])
    score += score_roe(row["ROE"])

    return score


# ==========================================================
# TECHNICAL SCAN
# ==========================================================

def fetch_matched_and_all():

    query1 = {
        "track_total_hits": True,
        "size": 1000,
        "_source": ["ticker", "crossed_resistance", "close", "date"],
        "query": {
            "bool": {
                "must": [
                    {"range": {"crossed_resistance.support_distance_pct": {"lte": 10}}},
                    {"term": {"vcp_trend_template": True}},
                    {"term": {"date": SCAN_DATE}}
                ]
            }
        }
    }

    res1 = es.search(index=TECH_INDEX, body=query1)
    hits1 = res1["hits"]["hits"]

    rows1 = []
    date_value = None

    for h in hits1:
        src = h["_source"]
        ticker = src["ticker"].replace(".NS", "")
        close = src.get("close")
        date_value = src.get("date")

        for cr in src.get("crossed_resistance", []):
            rows1.append({
                "Ticker": ticker,
                "Support": cr.get("support_level"),
                "Resistance": cr.get("resistance_level"),
                "Close": close
            })

    df_matched = pd.DataFrame(rows1)

    query2 = {
        "track_total_hits": True,
        "size": 1000,
        "_source": ["ticker", "crossed_resistance", "close"],
        "query": {
            "bool": {
                "must": [
                    {"term": {"vcp_trend_template": True}},
                    {"term": {"date": date_value}}
                ]
            }
        }
    }

    res2 = es.search(index=TECH_INDEX, body=query2)
    hits2 = res2["hits"]["hits"]

    rows2 = []

    for h in hits2:
        src = h["_source"]
        ticker = src["ticker"].replace(".NS", "")
        close = src.get("close")

        for cr in src.get("crossed_resistance", []):
            rows2.append({
                "Ticker": ticker,
                "Support": cr.get("support_level"),
                "Resistance": cr.get("resistance_level"),
                "Close": close
            })

    df_all = pd.DataFrame(rows2)

    matched_tickers = set(df_matched["Ticker"])
    df_missed = df_all[~df_all["Ticker"].isin(matched_tickers)]

    return df_matched, df_missed


# ==========================================================
# FUNDAMENTAL ENRICHMENT
# ==========================================================

def get_fundamental_data(ticker):

    empty_result = {
        "Sector": np.nan,
        "Industry": np.nan,
        "ROCE": 0,
        "ROE": 0,
        "Current_Quarter_Result_Out": "No",
        "Sales_QoQ_%": 0,
        "Profit_QoQ_%": 0,
        "EPS_QoQ_%": 0,
        "Sales_YoY_%": 0,
        "Profit_YoY_%": 0,
        "EPS_YoY_%": 0,
        "Sales_Slope_5Q": 0,
        "Profit_Slope_5Q": 0
    }

    try:
        res = es.get(index=FUND_INDEX, id=ticker)
        src = res["_source"]

        sector = src.get("sector", {}).get("sector")
        industry = src.get("sector", {}).get("industry")

        ratios = src.get("ratios", {})
        roce = ratios.get("roce", 0)
        roe = ratios.get("roe", 0)

        quarterly = src.get("quarterly", [])
        current_quarter_result = is_current_quarter_result_out(
            src.get("currentQuarterResult"),
            quarterly
        )

        sales, profits, eps = [], [], []

        for q in quarterly:
            if q["metric"] == "Sales" or q["metric"] == "Revenue":
                sales.append((q["period_date"], q["value"]))
            elif q["metric"] == "Net Profit":
                profits.append((q["period_date"], q["value"]))
            elif q["metric"] == "EPS in Rs":
                eps.append((q["period_date"], q["value"]))

        sales = sorted(sales)
        profits = sorted(profits)
        eps = sorted(eps)

        if len(sales) < 5 or len(profits) < 5 or len(eps) < 5:
            empty_result["Sector"] = sector
            empty_result["Industry"] = industry
            empty_result["ROCE"] = roce
            empty_result["ROE"] = roe
            empty_result["Current_Quarter_Result_Out"] = "Yes" if current_quarter_result else "No"
            return empty_result

        sales_vals = [v for _, v in sales][-5:]
        profit_vals = [v for _, v in profits][-5:]
        eps_vals = [v for _, v in eps][-5:]

        return {
            "Sector": sector,
            "Industry": industry,
            "ROCE": roce,
            "ROE": roe,
            "Current_Quarter_Result_Out": "Yes" if current_quarter_result else "No",
            "Sales_QoQ_%": calculate_growth(sales_vals[-1], sales_vals[-2]),
            "Profit_QoQ_%": calculate_growth(profit_vals[-1], profit_vals[-2]),
            "EPS_QoQ_%": calculate_growth(eps_vals[-1], eps_vals[-2]),
            "Sales_YoY_%": calculate_growth(sales_vals[-1], sales_vals[0]),
            "Profit_YoY_%": calculate_growth(profit_vals[-1], profit_vals[0]),
            "EPS_YoY_%": calculate_growth(eps_vals[-1], eps_vals[0]),
            "Sales_Slope_5Q": calculate_slope(sales_vals),
            "Profit_Slope_5Q": calculate_slope(profit_vals)
        }

    except Exception:
        return empty_result


def enrich_dataframe(df):

    unique_tickers = df["Ticker"].unique()
    fundamentals = []

    for ticker in unique_tickers:
        data = get_fundamental_data(ticker)
        data["Ticker"] = ticker
        fundamentals.append(data)

    fund_df = pd.DataFrame(fundamentals)

    df = df.merge(fund_df, on="Ticker", how="left")

    df["Net_Score"] = df.apply(calculate_net_score, axis=1)

    df = df.sort_values(by="Net_Score", ascending=False)

    return df


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    print("🔎 Running technical scan...")
    df_matched, df_missed = fetch_matched_and_all()

    print("📊 Enriching with fundamentals...")
    df_matched = enrich_dataframe(df_matched)
    df_missed = enrich_dataframe(df_missed)

    # Sector summary for matched
    sector_matched = (
        df_matched
        .groupby("Sector")["Ticker"]
        .count()
        .reset_index()
        .rename(columns={"Ticker": "Stock_Count"})
        .sort_values(by="Stock_Count", ascending=False)
    )

    # Sector summary for missed
    sector_missed = (
        df_missed
        .groupby("Sector")["Ticker"]
        .count()
        .reset_index()
        .rename(columns={"Ticker": "Stock_Count"})
        .sort_values(by="Stock_Count", ascending=False)
    )

    print("💾 Saving Excel...")

    from openpyxl.chart import PieChart, Reference

    matched_export = prepare_signal_sheet(df_matched)
    missed_export = prepare_signal_sheet(df_missed)

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

        # Write sheets
        sector_matched.to_excel(writer, sheet_name="sector_matched", index=False)
        sector_missed.to_excel(writer, sheet_name="sector_missed", index=False)
        df_indices.to_excel(writer, sheet_name="indices", index=False)
        df_mf.to_excel(writer, sheet_name="MF", index=False)
        matched_export.to_excel(writer, sheet_name="matched", index=False)
        missed_export.to_excel(writer, sheet_name="missed", index=False)

        workbook = writer.book

        from openpyxl.chart import BarChart, Reference

        # -------- BAR CHART FOR MATCHED --------
        ws_matched = workbook["sector_matched"]

        bar1 = BarChart()
        bar1.title = "Sector Distribution (Matched)"
        bar1.y_axis.title = "Stock Count"
        bar1.x_axis.title = "Sector"
        bar1.height = 10
        bar1.width = 20

        data1 = Reference(ws_matched, min_col=2, min_row=1, max_row=len(sector_matched) + 1)
        categories1 = Reference(ws_matched, min_col=1, min_row=2, max_row=len(sector_matched) + 1)

        bar1.add_data(data1, titles_from_data=True)
        bar1.set_categories(categories1)

        ws_matched.add_chart(bar1, "E2")

        # -------- BAR CHART FOR MISSED --------
        ws_missed = workbook["sector_missed"]

        bar2 = BarChart()
        bar2.title = "Sector Distribution (Missed)"
        bar2.y_axis.title = "Stock Count"
        bar2.x_axis.title = "Sector"
        bar2.height = 10
        bar2.width = 20

        data2 = Reference(ws_missed, min_col=2, min_row=1, max_row=len(sector_missed) + 1)
        categories2 = Reference(ws_missed, min_col=1, min_row=2, max_row=len(sector_missed) + 1)

        bar2.add_data(data2, titles_from_data=True)
        bar2.set_categories(categories2)

        ws_missed.add_chart(bar2, "E2")

    print("✅ Done!")
