"""Retrieval Agent: the only component that reads the index (reference architecture).

Every query goes through `access_filter`, which refuses to run without the caller's
groups (ADR-0013). Group names and document IDs are validated before they are placed
in the OData filter, so a crafted value cannot widen the filter (filter injection)."""
import re
from dataclasses import dataclass

from . import _ingestion  # noqa: F401  (sets the import path)
from pipeline import http
from pipeline.config import SETTINGS as S
from pipeline.embed import embed

SELECT = "id,doc_id,file_name,section_heading,page_start,page_end,content"
_SAFE_GROUP = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_DOC = re.compile(r"^[0-9a-f]{16}$")


class AccessError(PermissionError):
    pass


def access_filter(groups: list[str], doc_id: str | None = None) -> str:
    if not groups:
        raise AccessError("No groups supplied: retrieval refuses to run without the caller's groups")
    bad = [g for g in groups if not _SAFE_GROUP.match(g)]
    if bad:
        raise AccessError(f"Invalid group name(s): {bad}")
    f = f"allowed_groups/any(g: search.in(g, '{','.join(groups)}', ','))"
    if doc_id is not None:
        if not _SAFE_DOC.match(doc_id):
            raise AccessError(f"Invalid document id: {doc_id!r}")
        f += f" and doc_id eq '{doc_id}'"
    return f


@dataclass
class Hit:
    id: str
    doc_id: str
    file_name: str
    section_heading: str
    page_start: int
    page_end: int
    content: str
    score: float
    reranker_score: float | None


def query_vector(text: str) -> list[float]:
    return embed([text])[0][0]


def search(query: str, groups: list[str], *, doc_id: str | None = None, k: int = 20,
           rerank: bool = True, vector: list[float] | None = None) -> list[Hit]:
    """Hybrid search (BM25 + vector, fused with RRF), optionally reranked by the semantic
    ranker. Returns up to k hits, best first."""
    body = {
        "search": query,
        "filter": access_filter(groups, doc_id),
        "vectorQueries": [{"kind": "vector", "vector": vector or query_vector(query),
                           "fields": "content_vector", "k": k}],
        "select": SELECT,
        "top": k,
    }
    if rerank:
        body.update({"queryType": "semantic", "semanticConfiguration": "default"})
    url = f"{S.search_endpoint}/indexes/{S.index}/docs/search?api-version={S.search_api}"
    resp = http.request("POST", url, http.SEARCH_SCOPE, json=body, retry_404=False).json()
    hits = [Hit(d["id"], d["doc_id"], d["file_name"], d.get("section_heading") or "",
                d["page_start"], d["page_end"], d["content"], d["@search.score"],
                d.get("@search.rerankerScore")) for d in resp.get("value", [])]
    if rerank:
        hits.sort(key=lambda h: h.reranker_score or 0, reverse=True)
    return hits


def document_vendor(doc_id: str, groups: list[str]) -> str | None:
    """Vendor ID of a contract, ONLY if the caller's groups can see that contract (ADR-0023:
    tools act for the user, never beyond the user). Returns None both when the contract does not
    exist and when the caller may not see it, so the answer does not reveal which."""
    body = {"search": "*", "filter": access_filter(groups, doc_id), "select": "vendor_id", "top": 1}
    url = f"{S.search_endpoint}/indexes/{S.index}/docs/search?api-version={S.search_api}"
    rows = http.request("POST", url, http.SEARCH_SCOPE, json=body, retry_404=False).json().get("value", [])
    return (rows[0].get("vendor_id") or None) if rows else None

