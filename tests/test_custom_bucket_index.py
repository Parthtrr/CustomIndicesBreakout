import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from technical.customIndex.createCustomIndex import (
    BASE_VALUE,
    SRC_INDEX,
    _to_technical_index_frame,
    build_custom_bucket_definition,
    calculate_equal_weight_index,
    index_custom_index,
    persist_custom_bucket,
    save_custom_bucket_definition,
)


class FakeIndicesClient:
    def __init__(self):
        self.created = []
        self.exists_result = False

    def exists(self, index):
        return self.exists_result

    def create(self, index, body):
        self.created.append((index, body))
        self.exists_result = True


class FakeElasticsearch:
    def __init__(self):
        self.indices = FakeIndicesClient()
        self.indexed = []

    def index(self, **kwargs):
        self.indexed.append(kwargs)


class CustomBucketIndexTests(unittest.TestCase):
    def test_definition_normalises_bucket_ticker_and_constituents(self):
        definition = build_custom_bucket_definition(
            " AI Leaders ", "ai_leaders", ["infy.ns, tcs.ns", "INFY.NS"]
        )

        self.assertEqual(definition["Name"], "AI Leaders")
        self.assertEqual(definition["ticker"], "^AI_LEADERS")
        self.assertEqual(definition["constituents"], ["INFY.NS", "TCS.NS"])
        self.assertTrue(definition["IsCustom"])

    def test_definition_rejects_an_invalid_synthetic_ticker(self):
        with self.assertRaises(ValueError):
            build_custom_bucket_definition("Bad", "^NOT A TICKER", ["TCS.NS"])

    def test_save_and_persist_bucket_definition(self):
        definition = build_custom_bucket_definition(
            "AI Leaders", "^AI_LEADERS", ["INFY.NS", "TCS.NS"]
        )
        fake_es = FakeElasticsearch()

        with tempfile.TemporaryDirectory() as temporary_directory:
            bucket_file = Path(temporary_directory) / "buckets.json"
            save_custom_bucket_definition(definition, bucket_file)
            persisted_file = json.loads(bucket_file.read_text(encoding="utf-8"))

        persist_custom_bucket(definition, fake_es)

        self.assertEqual(persisted_file["^AI_LEADERS"]["constituents"], ["INFY.NS", "TCS.NS"])
        self.assertEqual(len(fake_es.indices.created), 1)
        self.assertEqual(fake_es.indexed[0]["id"], "AI Leaders:^AI_LEADERS")
        self.assertEqual(fake_es.indexed[0]["document"], definition)

    def test_equal_weight_candles_and_technical_adapter(self):
        rows = [
            {
                "ticker": "A.NS",
                "date": "2026-01-05",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0,
                "volume": 10,
            },
            {
                "ticker": "B.NS",
                "date": "2026-01-05",
                "open": 200.0,
                "high": 220.0,
                "low": 180.0,
                "close": 200.0,
                "volume": 20,
            },
            {
                "ticker": "A.NS",
                "date": "2026-01-12",
                "open": 100.0,
                "high": 130.0,
                "low": 95.0,
                "close": 120.0,
                "volume": 11,
            },
            {
                "ticker": "B.NS",
                "date": "2026-01-12",
                "open": 200.0,
                "high": 210.0,
                "low": 190.0,
                "close": 200.0,
                "volume": 21,
            },
        ]

        candles = calculate_equal_weight_index(pd.DataFrame(rows), "^AI_LEADERS")
        frame = _to_technical_index_frame(candles, "^AI_LEADERS")

        self.assertEqual(candles[0]["close"], BASE_VALUE)
        self.assertEqual(candles[1]["close"], 1100.0)
        self.assertEqual(candles[1]["volume"], 32)
        self.assertEqual(frame.loc[0, "type"], "index")
        self.assertTrue(frame.loc[0, "isCustom"])
        self.assertEqual(frame.loc[0, "indices"], [])

    def test_indexing_delegates_to_the_shared_technical_indexer(self):
        candles = [
            {
                "date": "2026-01-05",
                "ticker": "^AI_LEADERS",
                "open": 1000.0,
                "high": 1000.0,
                "low": 1000.0,
                "close": 1000.0,
                "volume": 10,
                "type": "index",
                "isCustom": True,
            }
        ]
        calls = []

        def fake_index_data(index_name, frame, ticker):
            calls.append((index_name, frame, ticker))

        index_custom_index(candles, "^AI_LEADERS", index_data_fn=fake_index_data)

        self.assertEqual(calls[0][0], SRC_INDEX)
        self.assertEqual(calls[0][2], "^AI_LEADERS")
        self.assertEqual(calls[0][1].loc[0, "type"], "index")
        self.assertEqual(
            set(["Date", "Open", "High", "Low", "Close", "Volume", "indices"]),
            set(calls[0][1].columns) & {"Date", "Open", "High", "Low", "Close", "Volume", "indices"},
        )


if __name__ == "__main__":
    unittest.main()
