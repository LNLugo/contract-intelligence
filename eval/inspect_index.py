"""Look inside the index: chunk counts per document, a sample of chunks, storage used.

Usage (repo root, venv active):
    python eval/inspect_index.py                 # summary for every document
    python eval/inspect_index.py <doc_id> 3      # first 3 chunks of one document
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from pipeline import http  # noqa: E402
from pipeline.config import SETTINGS as S  # noqa: E402

DOCS = f"{S.search_endpoint}/indexes/{S.index}/docs"


def search(body: dict) -> dict:
    return http.request("POST", f"{DOCS}/search?api-version={S.search_api}", http.SEARCH_SCOPE,
                        json=body, retry_404=False).json()


def summary() -> None:
    counts, files, skip = Counter(), {}, 0
    while True:
        page = search({"search": "*", "select": "doc_id,file_name", "top": 1000, "skip": skip,
                       "count": True, "orderby": "doc_id"})
        for d in page["value"]:
            counts[d["doc_id"]] += 1
            files[d["doc_id"]] = d["file_name"]
        skip += len(page["value"])
        if len(page["value"]) < 1000:
            break
    print(f"Documents: {len(counts)}   Chunks: {sum(counts.values())}\n")
    for doc_id, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {doc_id}  {n:4d} chunks  {files[doc_id][:70]}")
    stats = http.request("GET", f"{S.search_endpoint}/servicestats?api-version={S.search_api}",
                         http.SEARCH_SCOPE, retry_404=False).json()["counters"]
    print(f"\nStorage used: {stats['storageSize']['usage'] / 2**20:.1f} MB of "
          f"{stats['storageSize']['quota'] / 2**20:.0f} MB")


def sample(doc_id: str, n: int) -> None:
    res = search({"search": "*", "filter": f"doc_id eq '{doc_id}'", "orderby": "chunk_index",
                  "top": n, "select": "id,chunk_index,section_heading,page_start,page_end,content"})
    for d in res["value"]:
        print(f"--- {d['id']}  pages {d['page_start']}-{d['page_end']}  heading: {d['section_heading'][:60]!r}")
        print(d["content"][:400].replace("\n", " "), "...\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sample(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    else:
        summary()
