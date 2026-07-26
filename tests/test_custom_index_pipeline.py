import unittest
from pathlib import Path

import pandas as pd

from technical.customIndex.custom_index_pipeline import (
    BASE_VALUE,
    CustomIndexDefinition,
    DEFAULT_DEFINITION_FILE,
    aggregate_to_weekly,
    calculate_daily_equal_weight_index,
    load_index_definitions,
    normalise_ticker,
)


class CustomIndexPipelineTests(unittest.TestCase):
    def setUp(self):
        self.definition = CustomIndexDefinition(
            ticker="CUSTOM_TEST",
            index_name="TEST",
            sector_or_industry="TEST",
            classification_type="industry",
            source_file="test.xlsx",
            constituents=("A.NS", "B.NS"),
        )

    def test_normalise_ticker_uses_bse_for_six_digit_codes(self):
        self.assertEqual(normalise_ticker("TCS"), "TCS.NS")
        self.assertEqual(normalise_ticker("506854"), "506854.BO")
        self.assertEqual(normalise_ticker(506854.0), "506854.BO")

    def test_checked_in_manifest_loads_unique_tradingview_baskets(self):
        definitions = load_index_definitions()

        self.assertEqual(DEFAULT_DEFINITION_FILE.name, "tradingview_index_definitions.json")
        self.assertEqual(len(definitions), 230)
        carbon_black = next(
            definition
            for definition in definitions
            if definition.tradingview_equation == "(NSE:HSCL+NSE:PCBL)/2"
        )
        self.assertEqual(carbon_black.index_name, "NIFTY CHEMICAL — Carbon Black")
        self.assertEqual(carbon_black.constituents, ("HSCL.NS", "PCBL.NS"))
        self.assertEqual(len(carbon_black.source_files), 2)

    def test_daily_equal_weight_rebalances_each_day(self):
        index = pd.to_datetime(["2026-01-05", "2026-01-06"])
        market_data = {
            "A.NS": pd.DataFrame(
                {"Open": [100, 110], "High": [100, 120], "Low": [100, 105], "Close": [100, 120], "Volume": [10, 11]},
                index=index,
            ),
            "B.NS": pd.DataFrame(
                {"Open": [200, 200], "High": [200, 210], "Low": [200, 190], "Close": [200, 200], "Volume": [20, 21]},
                index=index,
            ),
        }

        daily = calculate_daily_equal_weight_index(self.definition, market_data)

        self.assertEqual(daily.iloc[0]["Close"], BASE_VALUE)
        self.assertEqual(daily.iloc[1]["Close"], 1100.0)
        self.assertEqual(daily.iloc[1]["Volume"], 32)
        self.assertEqual(self.definition.metadata["calculation_method"], "equal_weight")
        self.assertEqual(self.definition.metadata["rebalance_frequency"], "daily")

    def test_weekly_aggregation_retains_current_partial_week(self):
        daily = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-12"]),
                "Open": [1000.0, 1010.0, 1020.0],
                "High": [1020.0, 1030.0, 1040.0],
                "Low": [990.0, 1000.0, 1010.0],
                "Close": [1010.0, 1020.0, 1030.0],
                "Volume": [10, 20, 30],
            }
        )

        weekly = aggregate_to_weekly(daily)

        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly.iloc[0]["Open"], 1000.0)
        self.assertEqual(weekly.iloc[0]["Close"], 1020.0)
        self.assertEqual(weekly.iloc[0]["Volume"], 30)
        self.assertEqual(weekly.iloc[1]["Date"], pd.Timestamp("2026-01-12"))


if __name__ == "__main__":
    unittest.main()
