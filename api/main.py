"""Contracts API (ADR-0023, ADR-0024). Run locally:  uvicorn api.main:app --port 8000

Every data endpoint takes the caller from a validated token. Request models reject unknown
fields, so a body that tries to send its own groups is refused (422), not silently ignored.
The audit log records who, which groups, which documents: never contract text.
"""
import logging
import sys
from pathlib import Path

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ingestion"))
from agents import orchestrator, retrieve  # noqa: E402
from api.auth import Caller, current_caller  # noqa: E402

log = logging.getLogger("contracts.audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="Contracts API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")       # "groups", "allowed_groups", "filter": all refused
    query: str = Field(min_length=1, max_length=500)
    doc_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    k: int = Field(default=10, ge=1, le=20)


class HitOut(BaseModel):
    doc_id: str
    file_name: str
    section_heading: str
    page_start: int
    page_end: int
    content: str
    score: float


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/me")
def me(caller: Caller = Depends(current_caller)) -> dict:
    return {"roles": list(caller.roles), "groups": list(caller.groups)}


@app.post("/search")
def search(req: SearchRequest, caller: Caller = Depends(current_caller)) -> list[HitOut]:
    # Semantic reranking off for now: the free tier allows 1,000 reranked queries a month
    hits = retrieve.search(req.query, list(caller.groups), doc_id=req.doc_id, k=req.k, rerank=False)
    log.info("search subject=%s app=%s groups=%s doc_filter=%s results=%d docs=%s",
             caller.subject, caller.client_app, ",".join(caller.groups), req.doc_id or "-",
             len(hits), ",".join(sorted({h.doc_id for h in hits})))
    return [HitOut(doc_id=h.doc_id, file_name=h.file_name, section_heading=h.section_heading,
                   page_start=h.page_start, page_end=h.page_end, content=h.content, score=h.score) for h in hits]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")       # no groups, roles or filters from the client
    question: str = Field(min_length=1, max_length=1000)
    doc_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


@app.post("/ask")
def ask(req: AskRequest, caller: Caller = Depends(current_caller)) -> dict:
    """Orchestrated answer (ADR-0026): cited clause answer, taxonomy category, and vendor check
    for a contract the caller can see. Groups come only from the validated token."""
    result = orchestrator.run(caller.groups, req.question, req.doc_id)
    cited = {c["file_name"] for f in result["clause"]["findings"] for c in f["citations"] if c["valid"]}
    log.info("ask subject=%s app=%s groups=%s doc_filter=%s status=%s clause=%s vendor=%s category=%s taxonomy=%s cited_files=%d",
             caller.subject, caller.client_app, ",".join(caller.groups), req.doc_id or "-", result["status"],
             result["clause"]["status"], result["vendor"]["status"],
             (result["category"] or {}).get("code", "-"), result["taxonomy_version"], len(cited))
    return result

