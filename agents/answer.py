"""Slice 1 answering: generate cited findings, validate citations in code, route the result.

Routing (ADR-0009), decided by code, not the model:
  ANSWERED   findings survived citation validation
  NOT_FOUND  strong evidence was retrieved and the model reports the clause is absent
  ABSTAIN    weak retrieval, or every citation failed validation
"""
import json
import re
import time
from dataclasses import asdict, dataclass, field

from . import _ingestion  # noqa: F401
from .retrieve import Hit, search
from pipeline import http
from pipeline.config import SETTINGS as S

CHAT_MODEL = "gpt-5.4-mini"
TOP_N = 5                       # chunks the model sees (ADR-0006: top 20 -> top 5)
MIN_RERANKER_SCORE = 1.5        # semantic ranker scale 0-4; provisional, to be calibrated by eval

SYSTEM = """You review commercial contracts. Answer ONLY from the numbered clauses provided.
Return JSON with exactly these keys:
{"found": true|false,
 "answer": "one or two sentence answer",
 "findings": [{"statement": "what the contract says",
               "citations": [{"clause": "C1", "quote": "words copied exactly from that clause"}]}]}
Rules: every statement needs at least one citation; quotes must be copied verbatim, 8 to 40 words;
if the clauses do not address the question, return found=false and an empty findings list."""


@dataclass
class Citation:
    clause: str
    quote: str
    valid: bool
    file_name: str = ""
    pages: str = ""


@dataclass
class Finding:
    statement: str
    citations: list[Citation] = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return any(c.valid for c in self.citations)


@dataclass
class Answer:
    status: str
    answer: str
    findings: list[Finding]
    reason: str
    top_reranker_score: float | None
    dropped_findings: int
    tokens: int
    seconds: float


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def quote_in_clause(quote: str, clause: str) -> bool:
    """Deterministic citation check (ADR-0020): the quote must appear in the clause.
    Exact match after normalization, or 90% of the quote's words in order within the clause."""
    q, c = _norm(quote), _norm(clause)
    if len(q.split()) < 4:
        return False
    if q in c:
        return True
    words, pos, matched = q.split(), 0, 0
    c_words = c.split()
    for w in words:
        try:
            pos = c_words.index(w, pos) + 1
            matched += 1
        except ValueError:
            continue
    return matched / len(words) >= 0.9


def _context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[C{i}] ({h.file_name}, pages {h.page_start}-{h.page_end}, section: {h.section_heading})\n{h.content}"
                       for i, h in enumerate(hits, 1))


def generate(question: str, hits: list[Hit]) -> tuple[dict, int]:
    body = {"model": CHAT_MODEL, "response_format": {"type": "json_object"},
            "max_completion_tokens": 2000,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"Question: {question}\n\nClauses:\n{_context(hits)}"}]}
    resp = http.request("POST", f"{S.aoai_endpoint}/chat/completions", http.COGNITIVE_SCOPE, json=body).json()
    text = resp["choices"][0]["message"]["content"] or "{}"
    return json.loads(text), resp.get("usage", {}).get("total_tokens", 0)


def answer(question: str, groups: list[str], doc_id: str | None = None) -> Answer:
    t0 = time.time()
    hits = search(question, groups, doc_id=doc_id, k=20, rerank=True)[:TOP_N]
    top = hits[0].reranker_score if hits else None
    if not hits:
        return Answer("ABSTAIN", "", [], "no evidence retrieved", None, 0, 0, round(time.time() - t0, 1))
    if top is not None and top < MIN_RERANKER_SCORE:
        return Answer("ABSTAIN", "", [], f"weak evidence (top reranker score {top:.2f} < {MIN_RERANKER_SCORE})",
                      top, 0, 0, round(time.time() - t0, 1))

    raw, tokens = generate(question, hits)
    findings, dropped = [], 0
    for f in raw.get("findings", []):
        cites = []
        for c in f.get("citations", []):
            idx = c.get("clause", "").lstrip("Cc")
            hit = hits[int(idx) - 1] if idx.isdigit() and 1 <= int(idx) <= len(hits) else None
            cites.append(Citation(c.get("clause", ""), c.get("quote", ""),
                                  bool(hit) and quote_in_clause(c.get("quote", ""), hit.content),
                                  hit.file_name if hit else "", f"{hit.page_start}-{hit.page_end}" if hit else ""))
        finding = Finding(f.get("statement", ""), cites)
        if finding.supported:
            findings.append(finding)
        else:
            dropped += 1

    seconds = round(time.time() - t0, 1)
    if findings:
        return Answer("ANSWERED", raw.get("answer", ""), findings, "", top, dropped, tokens, seconds)
    if not raw.get("found", False) and dropped == 0:
        return Answer("NOT_FOUND", raw.get("answer", ""), [], "model reports the clause is not present", top, 0, tokens, seconds)
    return Answer("ABSTAIN", "", [], f"all {dropped} finding(s) failed citation validation", top, dropped, tokens, seconds)


def as_dict(a: Answer) -> dict:
    d = asdict(a)
    return d
