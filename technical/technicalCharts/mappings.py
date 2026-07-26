index_mapping = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s"
    },
    "mappings": {
        "properties": {
            # Core price fields
            "date": {"type": "date"},
            "ticker": {"type": "keyword"},
            "open": {"type": "float"},
            "close": {"type": "float"},
            "high": {"type": "float"},
            "low": {"type": "float"},
            "volume": {"type": "long"},
            "indices": {"type": "keyword"},  # Array of index names

            # Indicators
            "rsi": {"type": "float"},
            "roc": {"type": "float"},
            "roc_nifty": {"type": "float"},
            "atr": {"type": "float"},

            # Moving Averages
            "ma_10": {"type": "float"},
            "ma_30": {"type": "float"},
            "ma_40": {"type": "float"},

            # Trend flags
            "ma_10_above_30": {"type": "boolean"},
            "ma_30_above_40": {"type": "boolean"},
            "ma_10_above_40": {"type": "boolean"},

            # Trend classification
            "trend": {"type": "keyword"},

            # 52 Week Metrics (weekly candles)
            "high_52w": {"type": "float"},
            "low_52w": {"type": "float"},
            "dist_from_52w_high_pct": {"type": "float"},
            "dist_from_52w_low_pct": {"type": "float"},

            # VCP Template Filter
            "vcp_trend_template": {"type": "boolean"},

            # Metadata
            "type": {"type": "keyword"},
            "isCustom": {"type": "boolean"},
            "index_name": {"type": "keyword"},
            "source_file": {"type": "keyword"},
            "sector_or_industry": {"type": "keyword"},
            "classification_type": {"type": "keyword"},
            "index_formula": {"type": "keyword"},
            "calculation_method": {"type": "keyword"},
            "rebalance_frequency": {"type": "keyword"},
            "constituents": {"type": "keyword"},
            "constituent_count": {"type": "integer"},
            "crossed_resistance": {
                "properties": {
                    "support_level": {"type": "float"},
                    "resistance_level": {"type": "float"},
                    "near_support": {"type": "boolean"},
                    "near_resistance": {"type": "boolean"},
                    "support_distance_pct": {"type": "float"},
                    "resistance_distance_pct": {"type": "float"},
                    "days": {"type": "integer"}
                }
            }
        }
    }
}
