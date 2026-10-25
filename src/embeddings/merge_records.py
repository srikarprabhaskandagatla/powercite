import argparse
import hashlib
import json
import os
import re
from typing import Literal
import faiss
import geopandas as gpd
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel
from rapidfuzz import fuzz, process
from config.assumptions import MASS_STATE_PLANE
from config.towns import DATA_CACHE, DATA_PROCESSED, ROOT, load_towns, raw_dir
from embeddings.embed_records import load_store

TOP_K = 20
NEAREST_K = 5
EMB_MATCH = 0.80
TEXT_MATCH = 0.80
LOC_MATCH = 0.70
LOC_UNCLEAR = 0.55
MAX_DIST_M = 200
ADDR_MATCH = 90
JUDGE_MODEL = "claude-haiku-5-5"
JUDGE_CACHE = DATA_CACHE / "match_judge"
ABBREV = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "BOULEVARD": "BLVD",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "PLACE": "PL", "LANE": "LN",
    "COURT": "CT", "HIGHWAY": "HWY", "PARKWAY": "PKWY", "SQUARE": "SQ", "TERRACE": "TER",
}

load_dotenv(ROOT / ".env")


class MatchDecision(BaseModel):
    same_place: bool
    confidence: Literal["high", "medium", "low"]
    reason: str


def norm(text):
    text = re.sub(r"[^A-Z0-9 ]", " ", "" if pd.isna(text) else str(text).upper())
    return " ".join(ABBREV.get(word, word) for word in text.split())


def split_address(address):
    words = address.split()
    numbers = []
    while words and re.fullmatch(r"\d+[A-Z]?", words[0]):
        numbers.append(int(re.match(r"\d+", words.pop(0)).group()))
    span = (min(numbers), max(numbers)) if numbers else None
    return span, " ".join(words)


def address_score(osm_addr, site_addr):
    if not osm_addr:
        return np.nan
    osm_span, osm_street = split_address(osm_addr)
    site_span, site_street = split_address(site_addr)
    street = fuzz.token_sort_ratio(osm_street, site_street)
    if osm_span is None or site_span is None:
        return street * 0.5
    overlap = osm_span[0] <= site_span[1] and site_span[0] <= osm_span[1]
    return street if overlap else 0.0


def osm_table(town):
    cols = ["osm_id", "name", "addr:housenumber", "addr:street", "loc_id"]
    gdf = gpd.read_file(raw_dir(town["id"]) / "buildings_parcels.gpkg", columns=cols)
    gdf = gdf[gdf["name"].notna()].to_crs(MASS_STATE_PLANE)
    points = gdf.geometry.representative_point()
    street = gdf["addr:street"].fillna("")
    address = (gdf["addr:housenumber"].fillna("") + " " + street).where(street != "", "")
    return pd.DataFrame({
        "record_id": ("osm:" + gdf["osm_id"]).values, "name": gdf["name"].values,
        "addr": [norm(a) for a in address], "true_loc_id": gdf["loc_id"].values,
        "x": points.x.values, "y": points.y.values,
    })


def site_table(town):
    sites = pd.read_csv(DATA_PROCESSED / town["id"] / "sites.csv")
    points = gpd.GeoSeries(gpd.points_from_xy(sites["lon"], sites["lat"]), crs="EPSG:4326").to_crs(MASS_STATE_PLANE)
    return pd.DataFrame({
        "record_id": "site:" + sites["loc_id"], "loc_id": sites["loc_id"], "owner": sites["owner1"],
        "site_addr": sites["site_addr"], "addr": [norm(a) for a in sites["site_addr"]],
        "use_desc": sites["use_desc"], "x": points.x.values, "y": points.y.values,
    })


def candidate_pairs(town, osm, sites, records, vectors):
    town_records = records[records["town"] == town["id"]]
    row_of = pd.Series(town_records.index.values, index=town_records["record_id"])
    site_vecs = vectors[row_of[sites["record_id"]].values]
    osm_vecs = vectors[row_of[osm["record_id"]].values]
    index = faiss.IndexFlatIP(site_vecs.shape[1])
    index.add(site_vecs)
    _, nn = index.search(osm_vecs, min(TOP_K, len(sites)))
    by_text = pd.DataFrame({
        "osm_row": np.repeat(np.arange(len(osm)), nn.shape[1]),
        "site_row": nn.ravel(), "rank": np.tile(np.arange(nn.shape[1]), len(osm)),
    })

    dist = np.hypot(osm["x"].values[:, None] - sites["x"].values[None, :], osm["y"].values[:, None] - sites["y"].values[None, :])
    near = np.argsort(dist, axis=1)[:, :NEAREST_K]
    by_place = pd.DataFrame({"osm_row": np.repeat(np.arange(len(osm)), near.shape[1]), "site_row": near.ravel()})

    pairs = pd.concat([by_text, by_place]).drop_duplicates(["osm_row", "site_row"]).reset_index(drop=True)
    o = osm.iloc[pairs["osm_row"]].reset_index(drop=True)
    s = sites.iloc[pairs["site_row"]].reset_index(drop=True)
    pairs["record_id"] = o["record_id"]
    pairs["loc_id"] = s["loc_id"]
    pairs["cos"] = (osm_vecs[pairs["osm_row"]] * site_vecs[pairs["site_row"]]).sum(axis=1)
    pairs["addr_ratio"] = [fuzz.token_sort_ratio(a, b) if a else np.nan for a, b in zip(o["addr"], s["addr"])]
    pairs["addr_score"] = [address_score(a, b) for a, b in zip(o["addr"], s["addr"])]
    pairs["name_ratio"] = [fuzz.token_set_ratio(norm(a), norm(b)) for a, b in zip(o["name"], s["owner"])]
    pairs["dist_m"] = dist[pairs["osm_row"], pairs["site_row"]].round(1)
    text_part = pairs["addr_score"].fillna(pairs["name_ratio"]) / 100
    pairs["text_score"] = (0.5 * pairs["cos"] + 0.5 * text_part).round(3)
    return pairs


def best(pairs, mask, score):
    picked = pairs[mask].sort_values(score, ascending=False).drop_duplicates("record_id")
    return picked.set_index("record_id")


def predict(osm, sites, pairs):
    ids = osm["record_id"]
    emb = best(pairs, (pairs["rank"] == 0) & (pairs["cos"] >= EMB_MATCH), "cos")["loc_id"]
    text = best(pairs, pairs["text_score"] >= TEXT_MATCH, "text_score")["loc_id"]
    near = pairs["dist_m"] <= MAX_DIST_M
    loc = best(pairs, near & (pairs["text_score"] >= LOC_MATCH), "text_score")["loc_id"]

    site_addrs = sites["addr"].tolist()
    fuzzy = {}
    for rid, addr in zip(ids, osm["addr"]):
        hit = process.extractOne(addr, site_addrs, scorer=fuzz.token_sort_ratio, score_cutoff=ADDR_MATCH) if addr else None
        fuzzy[rid] = sites["loc_id"].iloc[hit[2]] if hit else None

    unclear = best(pairs, near & pairs["text_score"].between(LOC_UNCLEAR, LOC_MATCH, inclusive="left"), "text_score")
    unclear = unclear[~unclear.index.isin(loc.index)]
    return pd.DataFrame({
        "embedding_only": ids.map(emb), "fuzzy_address_only": ids.map(fuzzy),
        "text_combined": ids.map(text), "text_plus_location": ids.map(loc),
    }).set_index(ids), unclear


def judge(osm_row, site_row):
    payload = (
        f"Record A (OpenStreetMap): {osm_row['name']}, address {osm_row['addr'] or 'unknown'}\n"
        f"Record B (tax parcel): owner {site_row['owner']}, address {site_row['site_addr']}, use {site_row['use_desc']}\n"
        f"Distance between them: {osm_row['dist_m']:.0f} meters"
    )
    path = JUDGE_CACHE / f"{hashlib.sha1(payload.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text())["decision"]
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    response = anthropic.Anthropic().messages.parse(
        model=JUDGE_MODEL,
        max_tokens=2000,
        system="Decide if two records describe the same physical property. A parcel owner can be a landlord while the building name is the tenant business. Answer from the records only.",
        messages=[{"role": "user", "content": payload}],
        output_format=MatchDecision,
    )
    decision = response.parsed_output.model_dump() if response.parsed_output else None
    JUDGE_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"payload": payload, "decision": decision}, indent=2))
    return decision


def evaluate(pred, truth, site_ids):
    positives = truth.isin(site_ids)
    predicted = pred.notna()
    correct = predicted & (pred == truth)
    return {
        "predicted": int(predicted.sum()),
        "precision": round(correct.sum() / max(predicted.sum(), 1), 3),
        "recall": round(correct[positives].sum() / max(positives.sum(), 1), 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    records, vectors, _ = load_store()
    all_preds, all_truth, all_sites = [], [], set()
    judged = {"asked": 0, "same": 0, "no key": 0}
    for town in load_towns(args.towns):
        osm, sites = osm_table(town), site_table(town)
        pairs = candidate_pairs(town, osm, sites, records, vectors)
        preds, unclear = predict(osm, sites, pairs)

        final = preds["text_plus_location"].copy()
        method = final.notna().map({True: "auto", False: None})
        osm_by_id, site_by_loc = osm.set_index("record_id"), sites.set_index("loc_id")
        for rid, row in unclear.iterrows():
            decision = judge({**osm_by_id.loc[rid], "dist_m": row["dist_m"]}, site_by_loc.loc[row["loc_id"]])
            judged["asked"] += 1
            if decision is None:
                judged["no key"] += 1
            elif decision["same_place"]:
                judged["same"] += 1
                final[rid], method[rid] = row["loc_id"], "llm_judge"
        preds["final"] = final

        score_cols = ["loc_id", "cos", "addr_ratio", "addr_score", "name_ratio", "dist_m", "text_score"]
        chosen = pairs.merge(final.dropna().rename("loc_id").rename_axis("record_id").reset_index(), on=["record_id", "loc_id"])
        top = pairs.sort_values("text_score", ascending=False).drop_duplicates("record_id")
        shown = pd.concat([chosen, top[~top["record_id"].isin(chosen["record_id"])]]).set_index("record_id")
        links = osm.set_index("record_id")[["name", "addr"]].join(shown[score_cols].rename(columns={"loc_id": "candidate_loc_id"}))
        links["building_id"], links["method"] = final, method
        links.to_csv(DATA_PROCESSED / town["id"] / "links.csv")

        all_preds.append(preds)
        all_truth.append(osm.set_index("record_id")["true_loc_id"])
        all_sites |= set(sites["loc_id"])
        print(f"{town['name']:12s} osm named {len(osm):4d}  linked {int(final.notna().sum()):4d}  unclear {len(unclear):3d}")

    preds, truth = pd.concat(all_preds), pd.concat(all_truth)
    report = {name: evaluate(preds[name], truth, all_sites) for name in preds.columns}
    report["truth_positives"] = int(truth.isin(all_sites).sum())
    report["llm_judge"] = judged
    (DATA_PROCESSED / "match_eval.json").write_text(json.dumps(report, indent=2))
    print(f"\nOSM records whose true parcel is a candidate site: {report['truth_positives']} of {len(truth)}")
    print(f"LLM judge: {judged}")
    print(f"{'method':22s} predicted precision recall")
    for name in preds.columns:
        r = report[name]
        print(f"{name:22s} {r['predicted']:9d} {r['precision']:9.3f} {r['recall']:6.3f}")
