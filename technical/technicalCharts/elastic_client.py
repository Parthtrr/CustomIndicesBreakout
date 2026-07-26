from elasticsearch import Elasticsearch

import Constant


def get_es_client():
    return Elasticsearch([Constant.host])