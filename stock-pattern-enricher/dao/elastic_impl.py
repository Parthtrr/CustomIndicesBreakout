from typing import List, Dict, Any
from elasticsearch import helpers
from .elastic_interface import ElasticDAOInterface
from .es_client import get_es_client
from utils.logger import get_logger
import config.config as config

logger = get_logger(__name__)

class ElasticDAOImpl(ElasticDAOInterface):
    def __init__(self, es_host: str = "localhost", es_port: int = 9200):
        self.es = get_es_client(es_host, es_port)
        logger.info(f"Using shared Elasticsearch client at {es_host}:{es_port}")

    def fetch_stock_ohlcv(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"ticker": symbol}},
                        {"range": {"date": {"gte": start_date, "lte": end_date}}}
                    ]
                }
            },
            "sort": [{"date": {"order": "asc"}}]
        }
        logger.debug(f"Querying ES for {symbol} from {start_date} to {end_date}")
        response = self.es.search(index="stock_ohlcv", body=query, size=10000)
        hits = response.get("hits", {}).get("hits", [])
        results = [hit["_source"] for hit in hits]
        logger.info(f"Fetched {len(results)} OHLCV records for {symbol}")
        return results

    def fetch_batch_stock_ohlcv(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, List[Dict[str, Any]]]:
        logger.debug(f"Batch fetching OHLCV for symbols: {symbols}")

        query = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"ticker": symbols}},
                        {
                            "range": {
                                "date": {
                                    "gte": start_date,
                                    "lte": end_date
                                }
                            }
                        }
                        # filter for multiple symbols
                    ]
                }
            },
            "sort": [{"date": {"order": "desc"}}],  # sort by latest date
            "size": 1000  # limit to last 100 documents
        }

        response = self.es.search(index=config.index_name, body=query)
        hits = response.get("hits", {}).get("hits", [])

        results = {}
        for hit in hits:
            source = hit["_source"]
            sym = source.get("ticker")
            if sym not in results:
                results[sym] = []
            results[sym].append(source)

        for sym in symbols:
            results.setdefault(sym, [])

        logger.info(f"Batch fetched data for {len(symbols)} symbols, total records: {len(hits)}")
        return results

    def fetch_custom_index_symbols(self) -> List[str]:
        """Discover the custom-index universe from its dedicated candle index."""
        query = {
            "size": 0,
            "query": {"term": {"isCustom": True}},
            "aggs": {
                "tickers": {
                    "terms": {
                        "field": "ticker",
                        "size": 10_000,
                    }
                }
            },
        }
        response = self.es.search(index=config.index_name, body=query)
        return [
            bucket["key"]
            for bucket in response.get("aggregations", {}).get("tickers", {}).get("buckets", [])
            if bucket.get("key")
        ]

    def index_stock_data(self, symbol: str, data: List[Dict[str, Any]]) -> None:
        for record in data:
            date = record.get("date")
            if not date:
                logger.warning(f"Skipping record for symbol {symbol} due to missing date: {record}")
                continue
            doc_id = f"{symbol}_{date}"
            res = self.es.index(index="stock_ohlcv_enriched", id=doc_id, body=record)
            logger.debug(f"Indexed record for {symbol} at {date}: {res['result']}")
        logger.info(f"Indexed {len(data)} records for {symbol} into enriched index")

    def index_batch_stock_data(self, batch_data: Dict[str, List[Dict[str, Any]]]) -> None:
        logger.debug(f"Batch indexing (upsert) data for {len(batch_data)} symbols")
        actions = []
        for symbol, records in batch_data.items():
            for record in records:
                date = record.get("date")
                if not date:
                    logger.warning(f"Skipping record for symbol {symbol} due to missing date: {record}")
                    continue
                doc_id = f"{symbol}_{date}"
                action = {
                    "_op_type": "update",  # update (upsert)
                    "_index": config.index_name,
                    "_id": doc_id,
                    "doc": record,
                    "doc_as_upsert": True
                }
                actions.append(action)
        if actions:
            try:
                helpers.bulk(self.es, actions)
                logger.info(f"Batch up-serted {len(actions)} records across {len(batch_data)} symbols")
            except helpers.BulkIndexError as e:
                logger.error(f"Failed to upsert batch data: {len(e.errors)} document(s) failed to index.")
                for error in e.errors[:5]:  # Log first 5 errors for debugging
                    logger.error(f"Index error: {error}")
            except Exception as e:
                logger.error(f"Failed to upsert batch data: {e}", exc_info=True)
        else:
            logger.info("No records to upsert in batch")
