import os
import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from config.towns import DATA_PROCESSED, load_towns
from embeddings.embed_records import MODEL_NAME, embed

TOP_N = 5
TEXT_WEIGHT = 0.5
NUMERIC = ["floor_area_m2", "peak_kw_est", "open_lot_m2", "dist_substation_m", "n_buildings"]
WEIGHTINGS = {"text_only": 1.0, "numbers_only": 0.0, "hybrid": TEXT_WEIGHT}
DEMO_ADDRESSES = ["540 WESTGATE DR", "651 BELMONT ST", "1001 N MONTELLO ST"]


def load_sites():
    frames = []
    for town in load_towns():
        sites = pd.read_csv(DATA_PROCESSED / town["id"] / "sites.csv")
        links = pd.read_csv(DATA_PROCESSED / town["id"] / "links.csv").dropna(subset=["building_id"])
        names = links.groupby("building_id")["name"].apply(lambda s: ", ".join(sorted(set(s))[:3]))
        sites["linked_names"] = sites["loc_id"].map(names).fillna("")
        frames.append(sites)
    return pd.concat(frames, ignore_index=True)


def site_text(sites):
    return [
        "; ".join(p for p in [str(d), str(l).replace("_", " "), n] if p and p != "nan")
        for d, l, n in zip(sites["use_desc"], sites["load_profile"], sites["linked_names"])
    ]


def numeric_vectors(sites):
    values = np.log1p(sites[NUMERIC].fillna(0).clip(lower=0).to_numpy(dtype="float64"))
    z = (values - values.mean(axis=0)) / values.std(axis=0)
    return (z / np.linalg.norm(z, axis=1, keepdims=True)).astype("float32")


def combine(text_vecs, num_vecs, text_weight):
    return np.hstack([text_vecs * np.sqrt(text_weight), num_vecs * np.sqrt(1 - text_weight)]).astype("float32")


def neighbors(vectors):
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    scores, ids = index.search(vectors, TOP_N + 1)
    return scores[:, 1:], ids[:, 1:]


def quality(sites, ids):
    same_profile = (sites["load_profile"].to_numpy()[ids] == sites["load_profile"].to_numpy()[:, None]).mean()
    area = np.log(sites["floor_area_m2"].to_numpy())
    size_gap = np.median(np.abs(area[ids] - area[:, None]))
    other_town = (sites["town"].to_numpy()[ids] != sites["town"].to_numpy()[:, None]).mean()
    return same_profile, float(np.exp(size_gap)), other_town


if __name__ == "__main__":
    faiss.omp_set_num_threads(int(os.getenv("SLURM_CPUS_PER_TASK", "1")))
    sites = load_sites()
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    text_vecs = embed(site_text(sites), model)
    num_vecs = numeric_vectors(sites)

    print(f"sites {len(sites)}  with linked OSM names {int((sites['linked_names'] != '').sum())}")
    print(f"{'weighting':14s} same load type  typical size gap  from another town")
    results = {}
    for name, weight in WEIGHTINGS.items():
        scores, ids = neighbors(combine(text_vecs, num_vecs, weight))
        results[name] = (scores, ids)
        same, gap, other = quality(sites, ids)
        print(f"{name:14s} {same:14.0%}  {gap:15.2f}x  {other:17.0%}")

    scores, ids = results["hybrid"]
    text_cos = (text_vecs[:, None, :] * text_vecs[ids]).sum(axis=2)
    num_cos = (num_vecs[:, None, :] * num_vecs[ids]).sum(axis=2)
    out = pd.DataFrame({
        "loc_id": np.repeat(sites["loc_id"].to_numpy(), TOP_N),
        "town": np.repeat(sites["town"].to_numpy(), TOP_N),
        "rank": np.tile(np.arange(1, TOP_N + 1), len(sites)),
        "match_loc_id": sites["loc_id"].to_numpy()[ids].ravel(),
        "match_town": sites["town"].to_numpy()[ids].ravel(),
        "score": scores.ravel().round(3),
        "text_cos": text_cos.ravel().round(3),
        "numbers_cos": num_cos.ravel().round(3),
    })
    out.to_csv(DATA_PROCESSED / "lookalikes.csv", index=False)

    label = sites.set_index("loc_id")
    for address in DEMO_ADDRESSES:
        row = sites[sites["site_addr"] == address].iloc[0]
        print(f"\n{row['site_addr']}, {row['town']}: {row['use_desc'][:45]}, {row['floor_area_m2']:.0f} m2")
        for _, m in out[out["loc_id"] == row["loc_id"]].iterrows():
            t = label.loc[m["match_loc_id"]]
            print(f"  {m['score']:.2f}  {t['site_addr'][:24]:24s} {t['town']:11s} {str(t['use_desc'])[:40]:40s} {t['floor_area_m2']:7.0f} m2")
