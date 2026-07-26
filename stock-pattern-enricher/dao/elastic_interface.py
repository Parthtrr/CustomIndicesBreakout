from abc import ABC, abstractmethod
from typing import List, Dict, Any

class ElasticDAOInterface(ABC):

    @abstractmethod
    def fetch_stock_ohlcv(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def fetch_batch_stock_ohlcv(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, List[Dict[str, Any]]]:
        pass

    @abstractmethod
    def index_stock_data(self, symbol: str, data: List[Dict[str, Any]]) -> None:
        pass

    @abstractmethod
    def index_batch_stock_data(self, batch_data: Dict[str, List[Dict[str, Any]]]) -> None:
        pass

    @abstractmethod
    def fetch_custom_index_symbols(self) -> List[str]:
        """Return synthetic custom-index tickers registered in metadata."""
        pass
