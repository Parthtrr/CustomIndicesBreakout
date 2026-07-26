import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


TECHNICAL_CHARTS_DIR = Path(__file__).resolve().parents[1] / "technical" / "technicalCharts"
if str(TECHNICAL_CHARTS_DIR) not in sys.path:
    sys.path.insert(0, str(TECHNICAL_CHARTS_DIR))

# The production logger writes ``app.log`` beside the project.  Keep this
# focused unit test filesystem-independent while the live pipeline uses the
# real logger unchanged.
logging_config = types.ModuleType("logging_config")
logging_config.get_logger = logging.getLogger
sys.modules["logging_config"] = logging_config

import indexer  # noqa: E402  pylint: disable=wrong-import-position


class _FakeIndices:
    def exists(self, index):
        return True


class _FakeElasticsearch:
    def __init__(self):
        self.indices = _FakeIndices()


class TechnicalIndexerTests(unittest.TestCase):
    def test_standalone_index_defaults_benchmark_roc_to_zero(self):
        frame = pd.DataFrame(
            {
                "Date": [pd.Timestamp("2026-07-20")],
                "Open": [1000.0],
                "High": [1010.0],
                "Low": [990.0],
                "Close": [1005.0],
                "Volume": [100],
                "indices": [[]],
                "type": ["index"],
                "isCustom": [True],
            }
        )
        captured_actions = []

        def capture_bulk(_es, actions, **_kwargs):
            captured_actions.extend(actions)
            return 1, []

        with patch.object(indexer, "get_es_client", return_value=_FakeElasticsearch()):
            with patch.object(indexer.helpers, "bulk", side_effect=capture_bulk):
                indexer.index_data("nifty_custom_index_breakout", frame, "CUSTOM_TEST")

        self.assertEqual(captured_actions[0]["_source"]["roc_nifty"], 0.0)


if __name__ == "__main__":
    unittest.main()
