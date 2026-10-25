import json
import re
import faiss
import numpy as np
import pandas as pd
from config.towns import DATA_RAW, ROOT
from embeddings.embed_records import embed
from research.fetch_pages import load_page, load_sources

RAG_DIR = DATA_RAW / "rag"
CHUNK_SIZES = [400, 1200]
OVERLAP = 150
TOP_K = 3
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def chunk_page(page, size, title=None):
    parts = re.split(r"\[page (\d+)\]", page["text"]) if page["content_type"] == "pdf" else ["", "1", page["text"]]
    chunks = []
    for page_no, body in zip(parts[1::2], parts[2::2]):
        body = squash(body)
        start = 0
        while start < len(body):
            end = min(start + size, len(body))
            if end < len(body):
                cut = body.rfind(" ", start + size // 2, end)
                end = cut if cut > 0 else end
            header = f"{title or page['id']}, page {page_no}"
            chunks.append({"page_id": page["id"], "url": page["url"], "page_no": int(page_no), "header": header, "text": body[start:end]})
            if end == len(body):
                break
            start = max(end - OVERLAP, start + 1)
    return chunks


def build(size, model, use_header=True):
    chunks = pd.DataFrame([c for s in load_sources() for c in chunk_page(load_page(s["id"]), size, s.get("title"))])
    chunks.insert(0, "chunk_id", [f"c{size}_{i:04d}" for i in range(len(chunks))])
    texts = (chunks["header"] + ": " + chunks["text"]) if use_header else chunks["text"]
    vectors = embed(texts.tolist(), model)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return chunks, index


def retrieve(question, chunks, index, model, k=TOP_K):
    scores, ids = index.search(embed([QUERY_PREFIX + question], model), k)
    hits = chunks.iloc[ids[0]].copy()
    hits["score"] = scores[0].round(3)
    return hits


def load_questions():
    return json.loads((ROOT / "questions.json").read_text())


def hit(question, hits):
    text = " ".join(hits["text"])
    return question["expect_page"] in set(hits["page_id"]) and all(squash(t) in text for t in question["expect_text"])


def save(chunks, index):
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    chunks.to_csv(RAG_DIR / "chunks.csv", index=False)
    faiss.write_index(index, str(RAG_DIR / "chunks.faiss"))


def load():
    return pd.read_csv(RAG_DIR / "chunks.csv"), faiss.read_index(str(RAG_DIR / "chunks.faiss"))


def compare_sizes(model):
    questions = load_questions()
    built = {}
    for size in CHUNK_SIZES:
        for use_header in (False, True):
            chunks, index = build(size, model, use_header)
            hits = [hit(q, retrieve(q["question"], chunks, index, model)) for q in questions]
            built[(size, use_header)] = (chunks, index, float(np.mean(hits)))
            missed = [q["id"] for q, h in zip(questions, hits) if not h]
            label = "with header" if use_header else "no header"
            print(f"chunk size {size:5d}  {label:11s}  chunks {len(chunks):4d}  hit@{TOP_K} {np.mean(hits):.0%}  missed {missed}")
    best = max(built, key=lambda k: (built[k][2], k[1]))
    save(*built[best][:2])
    print(f"saved chunk size {best[0]} {'with' if best[1] else 'without'} header")
    return best
