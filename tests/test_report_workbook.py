import unittest
from datetime import datetime

from technical.customIndex.fundamentals import FundamentalMetrics
from technical.customIndex.report_workbook import (
    ConstituentRow,
    build_workbook,
    collect_constituents,
    fundamentals_table_rows,
    report_as_of_date,
    tradingview_formula,
    tradingview_symbol,
)


class ReportWorkbookTests(unittest.TestCase):
    def test_report_date_uses_live_weekday(self):
        self.assertEqual(report_as_of_date(datetime(2026, 7, 22, 12, 0)), datetime(2026, 7, 22).date())

    def test_report_date_uses_friday_after_the_week_closes(self):
        self.assertEqual(report_as_of_date(datetime(2026, 7, 25, 12, 0)), datetime(2026, 7, 24).date())
        self.assertEqual(report_as_of_date(datetime(2026, 7, 26, 12, 0)), datetime(2026, 7, 24).date())

    def test_tradingview_formula_keeps_nse_and_bse_symbols(self):
        self.assertEqual(tradingview_symbol("TCS.NS"), "NSE:TCS")
        self.assertEqual(tradingview_symbol("506854.BO"), "BSE:506854")
        self.assertEqual(tradingview_formula(["TCS.NS", "506854.BO"]), "(NSE:TCS + BSE:506854)/2")

    def test_constituent_tags_are_loaded_from_checked_in_manifest(self):
        constituents = collect_constituents(
            [{"definition_id": "TVI_4643141B92444130", "index_name": "NIFTY CHEMICAL — Carbon Black"}]
        )

        self.assertEqual([row.ticker for row in constituents], ["HSCL", "PCBL"])
        self.assertEqual(constituents[0].breakout_indices, ["NIFTY CHEMICAL — Carbon Black"])

    def test_fundamentals_sheet_has_live_metrics_and_taxonomy_columns(self):
        constituent = ConstituentRow(
            ticker="DEMO",
            tradingview_symbol="NSE:DEMO",
            company_name="Demo Industries",
            breakout_indices=["Demo Sector Index"],
            tags={
                "Screener Sub-Sector": ["Industrial Components"],
                "Primary Sub-Sector": ["Capital Goods"],
                "Secondary Tags": ["Manufacturing"],
                "Broad Market Indices (NIFTY ES tags)": ["NIFTY 500"],
            },
        )
        metrics = FundamentalMetrics(
            ticker="DEMO",
            market_cap_cr=123456.0,
            stock_pe=23.5,
            roce_pct=18.7,
            roe_pct=15.2,
            revenue_qoq_pct=25.0,
            revenue_yoy_pct=50.0,
            profit_qoq_pct=50.0,
            profit_yoy_pct=200.0,
            current_quarter_result_out=True,
            expected_result_quarter="Jun 2026",
            latest_reported_quarter="Jun 2026",
            screener_sector="Capital Goods",
            screener_industry="Industrial Components",
            screener_url="https://www.screener.in/company/DEMO/consolidated/",
            fetch_status="Retrieved",
        )

        rows = fundamentals_table_rows([constituent], {"DEMO": metrics})
        self.assertEqual(rows[0][4], 123456.0)
        self.assertEqual(rows[0][12], "Yes")
        self.assertEqual(rows[0][15], "NIFTY 500")
        self.assertEqual(rows[0][19], "Industrial Components")

        workbook = build_workbook([], [constituent], "2026-07-20", datetime(2026, 7, 24).date(), {"DEMO": metrics})
        sheet = workbook["Fundamentals"]
        self.assertEqual(sheet["E7"].value, 123456.0)
        self.assertEqual(sheet["M7"].value, "Yes")
        self.assertEqual(sheet["T7"].value, "Industrial Components")
        self.assertEqual(sheet["X7"].value, "Retrieved")


if __name__ == "__main__":
    unittest.main()
