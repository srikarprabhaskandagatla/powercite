import argparse
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from config.towns import DATA_CACHE, DATA_PROCESSED, INPUTS, ROOT, load_towns
from research.extractors import MODEL, extract_llm, extract_rules, has_key
from research.fetch_pages import load_page, load_sources
from research.validate import validate

EXTRACT_CACHE = DATA_CACHE / "extractions"
RATE_CLASSES = ["G-2", "G-3"]

load_dotenv(ROOT / ".env")


def llm_path(page_id):
    return EXTRACT_CACHE / f"{page_id}.llm.json"


def run_llm(page):
    first = validate(extract_llm(page), page["text"])
    if not first["rejected"]:
        return first, 1
    feedback = json.dumps(first["rejected"], indent=2)
    second = validate(extract_llm(page, feedback), page["text"])
    best = second if len(second["rejected"]) < len(first["rejected"]) else first
    return best, 2


def save(page, result, method, attempts, path):
    record = {
        "page_id": page["id"],
        "url": page["url"],
        "method": method,
        "attempts": attempts,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **result,
        "utility_named": result.get("utility"),
        "utility": page["utility"],
    }
    EXTRACT_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record


def extract(page, refresh=False):
    path = llm_path(page["id"])
    if path.exists() and not refresh:
        return json.loads(path.read_text()), "llm cached"
    if has_key():
        result, attempts = run_llm(page)
        return save(page, result, MODEL, attempts, path), "llm live"
    result = validate(extract_rules(page), page["text"])
    return save(page, result, "rules", 1, EXTRACT_CACHE / f"{page['id']}.rules.json"), "rules"


def tariff_table(records):
    utility_of_town = json.loads((INPUTS / "sources.json").read_text())["utility_by_town"]
    by_utility = {}
    for record in records:
        for charge in record["demand_charges"]:
            if charge["rate_class"] not in RATE_CLASSES or charge["optional"]:
                continue
            entry = by_utility.setdefault(record["utility"], {}).setdefault(charge["rate_class"], {
                "usd_per_kw": 0.0, "components": [], "effective_date": record["effective_date"],
                "url": record["url"], "method": record["method"],
            })
            entry["usd_per_kw"] = round(entry["usd_per_kw"] + charge["usd_per_unit"], 2)
            entry["components"].append(charge)
    return {
        town["id"]: {"utility": utility_of_town[town["id"]], **by_utility.get(utility_of_town[town["id"]], {})}
        for town in load_towns()
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    print(f"Extractor: {MODEL if has_key() else 'rules (no ANTHROPIC_API_KEY)'}")
    records = []
    for source in load_sources():
        page = load_page(source["id"])
        record, status = extract(page, args.refresh)
        records.append(record)
        print(
            f"{status:11s} {page['id']:40s} charges {len(record['demand_charges']):2d}  "
            f"incentives {len(record['incentives']):2d}  rejected {len(record['rejected']):2d}  "
            f"effective {record['effective_date']}"
        )

    table = tariff_table([r for r in records if r["utility"]])
    (DATA_PROCESSED / "tariffs.json").write_text(json.dumps(table, indent=2, ensure_ascii=False))
    for town_id, info in table.items():
        classes = {c: info[c]["usd_per_kw"] for c in RATE_CLASSES if c in info}
        print(f"{town_id:12s} {info['utility']:24s} demand $/kW {classes}")
