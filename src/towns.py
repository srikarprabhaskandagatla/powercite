import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_CACHE = ROOT / "data" / "cache"
DATA_PROCESSED = ROOT / "data" / "processed"


def load_towns(choosen_towns=None):
    towns = json.loads((ROOT / "towns.json").read_text())
    if choosen_towns:
        towns = [t for t in towns if t["id"] in choosen_towns]
    return towns


def raw_dir(town_id):
    path = DATA_RAW / town_id
    path.mkdir(parents=True, exist_ok=True)
    return path
