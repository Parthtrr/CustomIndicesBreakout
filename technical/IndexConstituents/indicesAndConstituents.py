import json
from pathlib import Path
from elasticsearch import Elasticsearch, helpers

ES_INDEX = "indices"

mapping = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
    },
    "mappings": {
        "properties": {
            "Name": {"type": "keyword"},
            "ticker": {"type": "keyword"},
            "constituents": {"type": "keyword"},
            "link": {"type": "keyword"},
            "IsCustom": {"type": "boolean"},
            "id": {"type": "keyword"}
        }
    }
}

# Local Elasticsearch instance without auth
es = Elasticsearch("http://localhost:9200", verify_certs=False)
SCRIPT_DIR = Path(__file__).resolve().parent


def create_index():
    if not es.indices.exists(index=ES_INDEX):
        es.indices.create(index=ES_INDEX, body=mapping)
        print(f"🆕 Created index: {ES_INDEX}")
    else:
        print(f"ℹ Index already exists: {ES_INDEX}")


def build_doc(key, value):
    # Ensure value is a dict
    if not isinstance(value, dict):
        print(f"⚠ Skipping invalid entry for key: {key}")
        return None

    name = value.get("Name")
    ticker = value.get("ticker")

    if not name or not ticker:
        print(f"⚠ Skipping entry missing Name or ticker for key: {key}")
        return None

    doc_id = f"{name}:{ticker}"
    value["id"] = doc_id

    return {
        "_index": ES_INDEX,
        "_id": doc_id,
        "_source": value
    }


def index_file(file_path):
    print(f"\n📂 Processing file: {file_path}")

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read {file_path}: {e}")
        return

    documents = []

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                for key, value in entry.items():
                    doc = build_doc(key, value)
                    if doc:
                        documents.append(doc)

    elif isinstance(data, dict):
        for key, value in data.items():
            doc = build_doc(key, value)
            if doc:
                documents.append(doc)

    if not data:
        print(f"ℹ No index definitions in {file_path}")
        return

    if documents:
        try:
            helpers.bulk(es, documents)
            print(f"✔ Indexed {len(documents)} records from {file_path}")
        except Exception as e:
            print(f"❌ Failed to index from {file_path}: {e}")
    else:
        print(f"❌ No valid JSON objects found in {file_path}")


if __name__ == "__main__":
    create_index()

    # Keep built-in and user-created custom buckets available regardless of
    # the caller's working directory.
    index_file(SCRIPT_DIR / "custom_indices_json.txt")
    index_file(SCRIPT_DIR.parent / "customIndex" / "custom_buckets.json")
    index_file(SCRIPT_DIR / "nifty_indices_list_json.txt")
