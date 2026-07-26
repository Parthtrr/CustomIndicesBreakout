import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import List
from services.service import StockEnrichmentService
from utils.logger import get_logger
from config.config import STOCK_SYMBOLS, START_DATE, MAX_WORKERS, BATCH_SIZE

logger = get_logger(__name__)

class ThreadExecutor:
    def __init__(self,
                 max_workers: int = MAX_WORKERS,
                 batch_size: int = BATCH_SIZE):
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.service = StockEnrichmentService()

    def _chunk_symbols(self, symbols: List[str]) -> List[List[str]]:
        """Split symbol list into chunks of batch_size"""
        return [symbols[i:i + self.batch_size] for i in range(0, len(symbols), self.batch_size)]

    def process_symbols(self, symbols: List[str], start_date: str, end_date: str) -> None:
        symbols = list(dict.fromkeys(symbols))
        logger.info(f"processing patterns from {start_date} to {end_date}")

        chunks = self._chunk_symbols(symbols)
        logger.info(f"Processing {len(symbols)} symbols in {len(chunks)} batches using {self.max_workers} threads")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self.service.process_multiple_stocks, chunk, start_date, end_date): chunk
                for chunk in chunks
            }

            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                try:
                    future.result()
                    logger.info(f"Completed batch for symbols: {chunk}")
                except Exception as e:
                    logger.error(f"Batch processing failed for symbols {chunk} with error: {e}")
                    logger.error("Traceback:\n" + traceback.format_exc())

    def process_all_from_config(self) -> None:
        try:
            custom_index_symbols = self.service.get_custom_index_symbols()
        except Exception as e:
            logger.warning(f"Could not discover custom indexes: {e}")
            return

        # This standalone project scans only its own custom-index universe.
        symbols = list(dict.fromkeys(custom_index_symbols))
        if not symbols:
            logger.warning("No custom-index candles are available to enrich.")
            return
        start_date = START_DATE
        end_date = date.today().strftime("%Y-%m-%d")
        self.process_symbols(symbols, start_date, end_date)
