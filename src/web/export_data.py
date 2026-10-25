import json
import geopandas as gpd
import pandas as pd
from config.assumptions import MASS_STATE_PLANE, SCORE_WEIGHTS
from config.towns import DATA_PROCESSED, ROOT, load_towns, raw_dir
from scoring.explain import display_name

DOCS_DATA = ROOT / "docs" / "data"
SITE_FIELDS = {
    "loc_id": "id", "display_name": "name", "site_addr": "addr", "lat": "lat", "lon": "lon",
    "score": "score", "rank_in_town": "rank", "value_month": "value", "bill_savings_month": "bill",
    "incentive_month": "incentive", "rate_class": "rate_class", "demand_usd_per_kw": "rate",
    "battery_kw": "battery_kw", "peak_kw_est": "peak_kw", "use_desc": "use", "load_profile": "load",
    "owner1": "owner", "dist_substation_m": "dist_sub", "substation_name": "substation",
    "open_lot_m2": "open_lot", "confidence_label": "confidence", "reason": "reason",
    "weak_point": "weak", "pitch": "pitch", "floor_area_m2": "floor_area",
}
LOOKALIKE_FIELDS = ["site_addr", "town", "use_desc", "floor_area_m2", "score", "value_month", "rank_in_town"]
SIMPLIFY_M = 20


def clean_records(frame):
    return json.loads(frame.to_json(orient="records", double_precision=6))


def site_records(town):
    ranked = pd.read_csv(DATA_PROCESSED / town["id"] / "ranked.csv")
    sites = ranked[list(SITE_FIELDS) + [f"f_{f}" for f in SCORE_WEIGHTS]].rename(columns=SITE_FIELDS)
    for col in ["value", "bill", "incentive", "peak_kw", "dist_sub", "open_lot", "floor_area"]:
        sites[col] = sites[col].round(0)
    return clean_records(sites.round({f"f_{f}": 3 for f in SCORE_WEIGHTS}))


def boundary(town):
    gdf = gpd.read_file(raw_dir(town["id"]) / "boundary.gpkg").to_crs(MASS_STATE_PLANE)
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_M)
    return json.loads(gdf.to_crs("EPSG:4326").to_json(drop_id=True))


def substations(town):
    gdf = gpd.read_file(raw_dir(town["id"]) / "substations.gpkg")
    return [
        {"name": n if pd.notna(n) else "Unnamed substation", "type": s if pd.notna(s) else "unknown",
         "voltage": v if pd.notna(v) else None, "lat": round(p.y, 6), "lon": round(p.x, 6)}
        for n, s, v, p in zip(gdf["name"], gdf["substation"], gdf["voltage"], gdf.geometry)
    ]


def all_sites():
    sites = pd.read_csv(DATA_PROCESSED / "scored_sites.csv")
    sites["name"] = [display_name(row) for _, row in sites.iterrows()]
    return sites.set_index("loc_id")


def lookalikes(town, sites_by_id, lookalike_table, shown_ids):
    rows = lookalike_table[lookalike_table["loc_id"].isin(shown_ids)]
    out = {}
    for loc_id, group in rows.groupby("loc_id"):
        matches = []
        for _, m in group.sort_values("rank").iterrows():
            info = sites_by_id.loc[m["match_loc_id"]]
            matches.append({
                "id": m["match_loc_id"], "name": info["name"], "addr": info["site_addr"], "town": info["town"],
                "use": info["use_desc"], "floor_area": round(float(info["floor_area_m2"])),
                "score": round(float(info["score"]), 1), "value": round(float(info["value_month"])),
                "rank": int(info["rank_in_town"]), "similarity": round(float(m["score"]), 3),
            })
        out[loc_id] = matches
    return out


def tariff(town, tariffs):
    info = tariffs[town["id"]]
    classes = {}
    for rate_class in ["G-2", "G-3"]:
        if rate_class in info:
            entry = info[rate_class]
            classes[rate_class] = {
                "usd_per_kw": entry["usd_per_kw"], "url": entry["url"], "effective": entry["effective_date"],
                "quotes": [c["quote"] for c in entry["components"]],
            }
    return {"utility": info["utility"], "classes": classes}


def export_town(town, sites_by_id, lookalike_table, tariffs):
    sites = site_records(town)
    data = {
        "id": town["id"], "name": town["name"], "weights": SCORE_WEIGHTS,
        "sites": sites, "boundary": boundary(town), "substations": substations(town),
        "lookalikes": lookalikes(town, sites_by_id, lookalike_table, {s["id"] for s in sites}),
        "tariff": tariff(town, tariffs),
    }
    path = DOCS_DATA / f"{town['id']}.json"
    path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    return path, len(data["sites"])


if __name__ == "__main__":
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    sites_by_id = all_sites()
    lookalike_table = pd.read_csv(DATA_PROCESSED / "lookalikes.csv")
    tariffs = json.loads((DATA_PROCESSED / "tariffs.json").read_text())
    rag = json.loads((DATA_PROCESSED / "rag_answers.json").read_text())
    (DOCS_DATA / "rag.json").write_text(json.dumps(rag, separators=(",", ":"), ensure_ascii=False))
    index = []
    for town in load_towns():
        path, n = export_town(town, sites_by_id, lookalike_table, tariffs)
        index.append({"id": town["id"], "name": town["name"]})
        print(f"{town['name']:12s} sites {n}  {path.stat().st_size / 1024:.0f} KB")
    (DOCS_DATA / "towns.json").write_text(json.dumps(index, indent=2))
