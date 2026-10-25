import argparse
import hashlib
import json
import os
import pandas as pd
from dotenv import load_dotenv
from config.towns import DATA_CACHE, DATA_PROCESSED, ROOT, load_towns

SEARCH_CACHE = DATA_CACHE / "search"
TOP_SITES = 20
MAX_RESULTS = 3

load_dotenv(ROOT / ".env")


def cache_path(query):
    return SEARCH_CACHE / f"{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"


def live_search(query):
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(query, max_results=MAX_RESULTS, include_raw_content=True)
    return [
        {"url": r["url"], "title": r.get("title"), "snippet": r.get("content"), "text": r.get("raw_content") or ""}
        for r in response["results"]
    ]


def search(query, refresh=False):
    path = cache_path(query)
    if path.exists() and not refresh:
        return json.loads(path.read_text())["results"], "cached"
    if os.getenv("TAVILY_API_KEY"):
        results = live_search(query)
        SEARCH_CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"query": query, "results": results}, indent=2, ensure_ascii=False))
        return results, "live"
    return [], "no key, no cache"


def site_query(site, town_name):
    who = site["osm_name"] if pd.notna(site["osm_name"]) else site["owner1"]
    return f"{who} {site['site_addr']} {town_name} MA"


def top_sites(town):
    sites = pd.read_csv(DATA_PROCESSED / town["id"] / "sites.csv")
    return sites.sort_values("peak_kw_est", ascending=False).head(TOP_SITES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    mode = "live" if os.getenv("TAVILY_API_KEY") else "cache only"
    print(f"Tavily mode: {mode}")
    for town in load_towns(args.towns):
        counts = {}
        for _, site in top_sites(town).iterrows():
            _, status = search(site_query(site, town["name"]), args.refresh)
            counts[status] = counts.get(status, 0) + 1
        print(f"{town['name']:12s} {counts}")
