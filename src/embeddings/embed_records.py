import argparse
import json
import os
import faiss
import numpy as np
import pandas as pd
import pyogrio
from sentence_transformers import SentenceTransformer
from config.towns import DATA_PROCESSED, DATA_RAW, load_towns, raw_dir

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMB_DIR = DATA_RAW / "embeddings"
OSM_COLS = ["osm_id", "name", "addr:housenumber", "addr:street", "building", "shop", "amenity", "office", "loc_id"]
DEMO_QUERIES = ["supermarket grocery store", "Home Depot", "cold storage warehouse", "hospital medical center"]


def clean(value):
    return "" if pd.isna(value) else str(value).strip()


def site_records(town):
    sites = pd.read_csv(DATA_PROCESSED / town["id"] / "sites.csv")
    text = [
        "; ".join(p for p in [clean(r.owner1), f"{clean(r.site_addr)}, {town['name']}", clean(r.use_desc)] if p)
        for r in sites.itertuples()
    ]
    return pd.DataFrame({
        "record_id": "site:" + sites["loc_id"], "source": "parcel_site", "town": town["id"],
        "loc_id": sites["loc_id"], "text": text,
    })


def osm_records(town):
    osm = pyogrio.read_dataframe(raw_dir(town["id"]) / "buildings_parcels.gpkg", read_geometry=False, columns=OSM_COLS)
    osm = osm[osm["name"].notna()]
    kind = osm[["shop", "amenity", "office", "building"]].bfill(axis=1).iloc[:, 0]
    address = (osm["addr:housenumber"].fillna("") + " " + osm["addr:street"].fillna("")).str.strip()
    text = [
        "; ".join(p for p in [clean(n), f"{a}, {town['name']}" if a else town["name"], clean(k)] if p)
        for n, a, k in zip(osm["name"], address, kind)
    ]
    return pd.DataFrame({
        "record_id": "osm:" + osm["osm_id"], "source": "osm", "town": town["id"],
        "loc_id": osm["loc_id"].values, "text": text,
    })


def embed(texts, model):
    vectors = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype="float32")


def load_store():
    records = pd.read_csv(EMB_DIR / "records.csv")
    vectors = np.load(EMB_DIR / "vectors.npy")
    index = faiss.read_index(str(EMB_DIR / "records.faiss"))
    return records, vectors, index


def demo(model, records, index):
    for query in DEMO_QUERIES:
        scores, ids = index.search(embed([query], model), 3)
        hits = [f"{records.text[i][:60]} ({s:.2f})" for s, i in zip(scores[0], ids[0])]
        print(f"\nquery: {query}")
        for hit in hits:
            print(f"  {hit}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--towns", nargs="*")
    args = parser.parse_args()

    threads = int(os.getenv("SLURM_CPUS_PER_TASK", "1"))
    faiss.omp_set_num_threads(threads)
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    towns = load_towns(args.towns)
    records = pd.concat([f(t) for t in towns for f in (site_records, osm_records)], ignore_index=True)
    vectors = embed(records["text"].tolist(), model)

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    EMB_DIR.mkdir(parents=True, exist_ok=True)
    records.to_csv(EMB_DIR / "records.csv", index=False)
    np.save(EMB_DIR / "vectors.npy", vectors)
    faiss.write_index(index, str(EMB_DIR / "records.faiss"))
    (EMB_DIR / "meta.json").write_text(json.dumps({"model": MODEL_NAME, "dim": int(vectors.shape[1]), "n": len(records)}))

    print(f"records {len(records)}  dim {vectors.shape[1]}  by source {records['source'].value_counts().to_dict()}")
    print(f"vector norm check {np.linalg.norm(vectors[:5], axis=1).round(3).tolist()}")
    demo(model, records, index)
