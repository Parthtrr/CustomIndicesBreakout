from typing import List
from dao.elastic_impl import ElasticDAOImpl
from services.pipeline import StockPatternPipeline
from utils.logger import get_logger
from utils.helper_loader import load_helpers_from_package
import config.config as config

logger = get_logger(__name__)

class StockEnrichmentService:
    def __init__(self):
        self.dao = ElasticDAOImpl(config.host,config.port)

        # Dynamically load pattern helpers from their respective directories

        self.resistance_support_helpers = load_helpers_from_package("pattern_helpers.resistance_support")

        self.pipeline = StockPatternPipeline(
            dao=self.dao,
            resistance_support_helpers=self.resistance_support_helpers
        )

    def process_single_stock(self, symbol: str, start_date: str, end_date: str) -> None:
        logger.info(f"Processing single stock {symbol} from {start_date} to {end_date}")
        self.pipeline.process_batch([symbol], start_date, end_date)

    def process_multiple_stocks(self, symbols: List[str], start_date: str, end_date: str) -> None:
        logger.info(f"Processing multiple stocks: {symbols} from {start_date} to {end_date}")
        self.pipeline.process_batch(symbols, start_date, end_date)

    def get_custom_index_symbols(self) -> List[str]:
        return self.dao.fetch_custom_index_symbols()
