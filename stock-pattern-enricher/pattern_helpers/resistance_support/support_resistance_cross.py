from typing import List, Dict, Any
import numpy as np
from scipy.signal import argrelextrema
from pattern_helpers.base import CandlePatternHelper


class ResistanceBreakoutHelper(CandlePatternHelper):
    # ================= UPDATED =================
    def apply_pattern(self, candles: List[Dict[str, Any]]) -> None:
        if not candles:
            return

        latest_candle = candles[-1]
        previous_candle = candles[-2]

        if "crossed_resistance" not in latest_candle:
            latest_candle["crossed_resistance"] = []

        lookback_periods = [50]
        ticker = latest_candle["ticker"]

        for days in lookback_periods:
            if len(candles) >= days:
                levels = self._find_major_support_and_resistance(candles, days)
                if levels:
                    latest_candle["crossed_resistance"].append({
                        "support_level": levels["nearest_support"],
                        "resistance_level": levels["nearest_resistance"],
                        "near_support": levels["near_support"],
                        "near_resistance": levels["near_resistance"],
                        "support_distance_pct": levels["support_distance_pct"],
                        "resistance_distance_pct": levels["resistance_distance_pct"],
                        "days": days
                    })

    # ================= UPDATED (ROLE FLIP LOGIC FIXED) =================
    def _find_major_support_and_resistance(self, candles: List[Dict[str, Any]], lookback_days: int) -> dict | None:
        if len(candles) < lookback_days:
            return None

        period_candles = candles[-(lookback_days + 10):-1]
        prices = np.array([candle["close"] for candle in period_candles])

        window = 5
        ticker = candles[-1]["ticker"]

        # ---- strict swing detection ----
        swing_indices = []

        for i in range(window, len(prices) - window):
            left = prices[i-window:i]
            right = prices[i+1:i+window+1]

            if np.all(prices[i] < left) and np.all(prices[i] < right):
                swing_indices.append(i)   # swing low

            if np.all(prices[i] > left) and np.all(prices[i] > right):
                swing_indices.append(i)   # swing high

        swing_indices = np.array(swing_indices)

        if len(swing_indices) == 0:
            return None

        swing_levels = prices[swing_indices]

        # ---- CLUSTER ALL LEVELS TOGETHER (ROLE REVERSAL SAFE) ----
        clustered_levels = self._cluster_levels(np.sort(swing_levels), tolerance=0.01)

        current_price = candles[-1]["close"]

        # classify levels relative to CMP
        supports = [lvl for lvl in clustered_levels if lvl < current_price]
        resistances = [lvl for lvl in clustered_levels if lvl > current_price]

        nearest_support = max(supports) if supports else None
        nearest_resistance = min(resistances) if resistances else None

        if nearest_support is None and nearest_resistance is None:
            return None

        # proximity flags
        near_support = self.is_close_to_support(current_price, nearest_support) if nearest_support else False
        near_resistance = self.is_close_to_resistance(current_price, nearest_resistance) if nearest_resistance else False

        # distance %
        support_distance_pct = None
        resistance_distance_pct = None

        if nearest_support:
            support_distance_pct = ((current_price - nearest_support) / current_price) * 100

        if nearest_resistance:
            resistance_distance_pct = ((nearest_resistance - current_price) / current_price) * 100

        return {
            "nearest_support": float(nearest_support) if nearest_support else None,
            "nearest_resistance": float(nearest_resistance) if nearest_resistance else None,
            "near_support": bool(near_support),
            "near_resistance": bool(near_resistance),
            "support_distance_pct": float(support_distance_pct) if support_distance_pct is not None else None,
            "resistance_distance_pct": float(resistance_distance_pct) if resistance_distance_pct is not None else None
        }

    # ================= UNCHANGED =================
    def _cluster_levels(self, levels: np.ndarray, tolerance: float = 0.01) -> List[float]:
        if len(levels) == 0:
            return []

        clustered = []
        cluster = [levels[0]]

        for level in levels[1:]:
            if abs(level - cluster[-1]) < tolerance * cluster[-1]:
                cluster.append(level)
            else:
                clustered.append(float(np.mean(cluster)))
                cluster = [level]

        clustered.append(float(np.mean(cluster)))
        return clustered

    def _get_nearest_supports(self, levels: List[float], current_price: float) -> List[float]:
        if not levels:
            return []
        supports_below = [level for level in levels if level < current_price]
        return sorted(supports_below, reverse=True)[:2]

    def _get_nearest_resistances(self, levels: List[float], current_price: float) -> List[float]:
        if not levels:
            return []
        resistances_above = [level for level in levels if level > current_price]
        return sorted(resistances_above)[:2]

    def is_close_to_support(self, current_price: float, nearest_support: float) -> bool:
        if current_price <= nearest_support:
            return False
        risk_ratio = (current_price - nearest_support) / current_price
        return risk_ratio <= 0.05

    def is_close_to_resistance(self, current_price: float, nearest_resistance: float) -> bool:
        if current_price >= nearest_resistance:
            return False
        risk_ratio = (nearest_resistance - current_price) / current_price
        return risk_ratio <= 0.05

    def _validate_touch_count(self, lows: np.ndarray, highs: np.ndarray, level: float, lookback_days: int) -> bool:
        tolerance = 0.005
        support_touches = np.sum(np.abs(lows - level) < tolerance * level)
        resistance_touches = np.sum(np.abs(highs - level) < tolerance * level)
        total_touches = support_touches + resistance_touches

        if lookback_days in [5, 10]:
            return total_touches >= 2
        elif lookback_days in [20, 50, 100]:
            return total_touches >= 3
        elif lookback_days in [150, 200]:
            return total_touches >= 4

        return total_touches >= 2

    def _crossed_resistance(self, prev_candle: Dict[str, Any], curr_candle: Dict[str, Any], level: float) -> bool:
        return curr_candle["close"] > level
