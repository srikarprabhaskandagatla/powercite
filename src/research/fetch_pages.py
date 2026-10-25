import argparse
import json
from config.towns import DATA_CACHE, DATA_RAW, ROOT
from research.clean import fetch_and_clean

PAGES_CACHE = DATA_CACHE / "pages"
PAGES_RAW = DATA_RAW / "pages"


def load_sources():
    return json.loads((ROOT / "sources.json").read_text())["pages"]


def cache_path(page_id):
    return PAGES_CACHE / f"{page_id}.json"


def load_page(page_id):
    return json.loads(cache_path(page_id).read_text())


def fetch(source, refresh=False):
    path = cache_path(source["id"])
    if path.exists() and not refresh:
        return load_page(source["id"]), "cached"
    raw, record = fetch_and_clean(source)
    PAGES_RAW.mkdir(parents=True, exist_ok=True)
    (PAGES_RAW / f"{source['id']}.{record['content_type']}").write_bytes(raw)
    PAGES_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record, "fetched"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    for source in load_sources():
        try:
            record, status = fetch(source, args.refresh)
            print(f"{status:8s} {source['id']:40s} {record['content_type']:5s} {record['n_chars']:7d} chars")
        except Exception as error:
            print(f"failed   {source['id']:40s} {type(error).__name__}: {error}")
