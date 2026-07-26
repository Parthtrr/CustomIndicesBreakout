from abc import ABC, abstractmethod
from typing import List, Dict, Any


class CandlePatternHelper(ABC):
    @abstractmethod
    def apply_pattern(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detects a specific pattern in the given list of candle data.
        Each dict in the result contains at least a `date` and `pattern_name`.

        :param candles: List of OHLCV dictionaries.
        :return: List of pattern match metadata dictionaries.
        """
        pass
