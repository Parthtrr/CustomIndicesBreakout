from elasticsearch import Elasticsearch

_es_client = None

def get_es_client(host="localhost", port=9200) -> Elasticsearch:
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch([{"host": host, "port": int(port), "scheme": "http"}])
    return _es_client
