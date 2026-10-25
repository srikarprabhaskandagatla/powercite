import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from config.towns import DATA_CACHE, DATA_PROCESSED, ROOT
from embeddings.embed_records import MODEL_NAME
from rag.build_index import compare_sizes, hit, load, load_questions, retrieve

ANSWER_MODEL = "claude-haiku-5-5"
ANSWER_CACHE = DATA_CACHE / "rag"
SYSTEM_PROMPT = (
    "Answer questions about Massachusetts electric tariffs and battery incentives using only the documents given. "
    "Quote the exact numbers and units. If the documents do not answer the question, say so."
)

load_dotenv(ROOT / ".env")


def cache_path(question, hits):
    key = question + "|" + "|".join(hits["chunk_id"])
    return ANSWER_CACHE / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"


def ask_claude(question, hits):
    import anthropic
    documents = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": row["text"]},
            "title": row["header"],
            "citations": {"enabled": True},
        }
        for _, row in hits.iterrows()
    ]
    response = anthropic.Anthropic().messages.create(
        model=ANSWER_MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": documents + [{"type": "text", "text": question}]}],
    )
    if response.stop_reason == "refusal":
        return None, []
    answer, citations = "", []
    for block in response.content:
        if block.type != "text":
            continue
        answer += block.text
        for c in block.citations or []:
            citations.append({"cited_text": c.cited_text, "document_index": c.document_index, "document_title": c.document_title})
    return answer.strip(), citations


def numbers_grounded(answer, hits):
    evidence = " ".join(hits["text"])
    numbers = re.findall(r"\d+(?:\.\d+)?", answer or "")
    return all(n in evidence for n in numbers)


def answer(question, hits):
    path = cache_path(question["question"], hits)
    if path.exists():
        return json.loads(path.read_text()), "cached"
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"answer": None, "citations": [], "method": "evidence only"}, "no key"
    text, citations = ask_claude(question["question"], hits)
    record = {
        "answer": text, "citations": citations, "method": ANSWER_MODEL,
        "numbers_grounded": numbers_grounded(text, hits),
        "answered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    ANSWER_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record, "live"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    if not args.skip_build:
        compare_sizes(model)
    chunks, index = load()

    print(f"\nAnswer mode: {ANSWER_MODEL if os.getenv('ANTHROPIC_API_KEY') else 'evidence only (no ANTHROPIC_API_KEY)'}")
    results = []
    for q in load_questions():
        hits = retrieve(q["question"], chunks, index, model)
        record, status = answer(q, hits)
        evidence = [
            {"page_id": r.page_id, "page_no": int(r.page_no), "header": r.header, "url": r.url, "score": float(r.score), "text": r.text}
            for r in hits.itertuples()
        ]
        results.append({"id": q["id"], "question": q["question"], "retrieval_hit": hit(q, hits), **record, "evidence": evidence})
        print(f"{q['id']} {status:13s} hit {str(hit(q, hits)):5s} top page {hits.iloc[0]['page_id']:38s} {q['question'][:55]}")

    (DATA_PROCESSED / "rag_answers.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nretrieval hit@3 {sum(r['retrieval_hit'] for r in results)}/{len(results)}")
