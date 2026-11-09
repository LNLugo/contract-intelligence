"""Push chunks to AI Search (ADR-0004). Idempotent per document: existing chunks
for the doc_id are deleted first, so a re-chunk that yields fewer chunks leaves
no stale ones behind."""
from datetime import datetime, timezone

from . import http
from .config import SETTINGS as S

BATCH = 100


def _docs_url() -> str:
    return f"{S.search_endpoint}/indexes/{S.index}/docs"


def existing_ids(doc_id: str) -> list[str]:
    body = {"search": "*", "filter": f"doc_id eq '{doc_id}'", "select": "id", "top": 1000}
    resp = http.request("POST", f"{_docs_url()}/search?api-version={S.search_api}",
                        http.SEARCH_SCOPE, json=body, retry_404=False).json()
    return [d["id"] for d in resp.get("value", [])]


def _post(actions: list[dict]) -> None:
    for start in range(0, len(actions), BATCH):
        resp = http.request("POST", f"{_docs_url()}/index?api-version={S.search_api}",
                            http.SEARCH_SCOPE, json={"value": actions[start:start + BATCH]},
                            retry_404=False).json()
        failed = [r for r in resp.get("value", []) if not r.get("status")]
        if failed:
            raise RuntimeError(f"{len(failed)} index actions failed, first: {failed[0]}")


def replace_document(doc_id: str, chunks, vectors, meta: dict) -> int:
    """Delete this document's old chunks, upload the new ones. Returns chunk count."""
    old = existing_ids(doc_id)
    if old:
        _post([{"@search.action": "delete", "id": i} for i in old])
    now = datetime.now(timezone.utc).isoformat()
    actions = [{
        "@search.action": "mergeOrUpload",
        "id": f"{doc_id}-{c.index:04d}",          # deterministic: reprocessing overwrites
        "doc_id": doc_id,
        "chunk_index": c.index,
        "file_name": meta["file_name"],
        "section_heading": c.section_heading,
        "content": c.content,
        "content_vector": v,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "contract_type": meta["contract_type"],
        "vendor_id": meta["vendor_id"],
        "business_unit": meta["business_unit"],
        "allowed_groups": meta["allowed_groups"],
        "clause_categories": [],                  # filled by the taxonomy step (ADR-0011)
        "extraction_version": S.extraction_version,
        "ingested_at": now,
    } for c, v in zip(chunks, vectors)]
    _post(actions)
    return len(actions)
