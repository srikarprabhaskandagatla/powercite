import hashlib
import re
from datetime import datetime, timezone
import pymupdf
import requests
import trafilatura

HEADERS = {"User-Agent": "Mozilla/5.0 (powercite research prototype)"}


def download(url):
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "")


def is_pdf(raw, content_type):
    return "pdf" in content_type.lower() or raw[:4] == b"%PDF"


def pdf_to_text(raw):
    with pymupdf.open(stream=raw, filetype="pdf") as doc:
        pages = [f"[page {i + 1}]\n{page.get_text()}" for i, page in enumerate(doc)]
    return "\n".join(pages)


def html_to_text(raw, url):
    html = raw.decode("utf-8", errors="replace")
    return trafilatura.extract(html, url=url, include_tables=True, include_links=False) or ""


def tidy_text(text):
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def page_record(source, raw, content_type, text):
    return {
        **source,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content_type": "pdf" if is_pdf(raw, content_type) else "html",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "n_chars": len(text),
        "text": text,
    }


def fetch_and_clean(source):
    raw, content_type = download(source["url"])
    text = pdf_to_text(raw) if is_pdf(raw, content_type) else html_to_text(raw, source["url"])
    return raw, page_record(source, raw, content_type, tidy_text(text))
