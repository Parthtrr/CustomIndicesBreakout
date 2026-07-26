from typing import List, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

class StockPatternPipeline:
    def __init__(self,
                 dao,
                 resistance_support_helpers: List):
        self.dao = dao
        self.resistance_support_helpers = resistance_support_helpers

    def process_batch(self, symbols: List[str], start_date: str, end_date: str) -> None:
        # 1. Fetch batch data
        raw_data = self.dao.fetch_batch_stock_ohlcv(symbols, start_date, end_date)

        # 2. Enrich data
        enriched_data = {}

        for symbol, records in raw_data.items():
            if not records:
                continue

            try:
                # Ensure data is sorted by date ascending
                records.sort(key=lambda r: r["date"])
                for helper in self.resistance_support_helpers:
                    helper.apply_pattern(records)

                # Take only the latest day's enriched record
                latest_record = records[-1]
                enriched_data[symbol] = [latest_record]

            except Exception as e:
                logger.error(f"Error processing symbol {symbol}: {e}", exc_info=True)
                # Skip this symbol but continue processing others

        # 3. Index the latest enriched record for each symbol
        if enriched_data:
            self.dao.index_batch_stock_data(enriched_data)
        else:
            logger.info("No enriched data to index after processing batch.")
