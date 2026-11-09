"""Slice 1 answering: generate a determination with cited evidence, validate citations
in code, and route the result in code (ADR-0009, ADR-0020, ADR-0021).

The model returns a `determination` (present / absent / unclear) separately from the
evidence it cites. Routing is decided by code from both:
  ANSWERED   determination present, and at least one finding survived citation validation
  NOT_FOUND  determination absent (evidence may still be cited to explain why)
  ABSTAIN    determination unclear, weak retrieval, or a "present" whose citations all failed
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
MIN_RERANKER_SCORE = 1.5        # floor against irrelevant retrieval only (ADR-0009 revision)

SYSTEM = """You review commercial contracts. Use ONLY the numbered clauses provided.
Return JSON with exactly these keys:
{"determination": "present" | "absent" | "unclear",
 "answer": "one or two sentence answer",
 "findings": [{"statement": "what the contract says",
               "citations": [{"clause": "C1", "quote": "words copied exactly from that clause"}]}]}

determination answers ONE thing: does the contract contain what the question asks about, as the
question defines it?
- "present": the clauses contain it. Cite the clauses that establish it.
- "absent": the clauses do not contain it. Related provisions that do not meet the question's
  definition (for example, termination for cause when the question asks about termination without
  cause) mean "absent". You may cite them in findings to explain the answer.
- "unclear": the clauses are ambiguous or you cannot tell from them.
Every statement needs at least one citation; quotes must be copied verbatim, 8 to 40 words."""


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
    determination: str
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


def validate(raw: dict, hits: list[Hit]) -> tuple[list[Finding], int]:
    """Keep findings with at least one citation whose quote is really in the cited clause."""
    findings, dropped = [], 0
    for f in raw.get("findings", []) or []:
        cites = []
        for c in f.get("citations", []) or []:
            idx = str(c.get("clause", "")).lstrip("Cc")
            hit = hits[int(idx) - 1] if idx.isdigit() and 1 <= int(idx) <= len(hits) else None
            cites.append(Citation(str(c.get("clause", "")), c.get("quote", ""),
                                  bool(hit) and quote_in_clause(c.get("quote", ""), hit.content),
                                  hit.file_name if hit else "", f"{hit.page_start}-{hit.page_end}" if hit else ""))
        finding = Finding(f.get("statement", ""), cites)
        if finding.supported:
            findings.append(finding)
        else:
            dropped += 1
    return findings, dropped


def route(determination: str, findings: list[Finding], dropped: int) -> tuple[str, str]:
    """Code decides the outcome (ADR-0009, ADR-0021). Returns (status, reason)."""
    if determination == "present":
        if findings:
            return "ANSWERED", ""
        return "ABSTAIN", f"determination present but all {dropped} finding(s) failed citation validation"
    if determination == "absent":
        return "NOT_FOUND", "determination absent"
    return "ABSTAIN", "model could not determine from the evidence (unclear): route to a reviewer"


def answer(question: str, groups: list[str], doc_id: str | None = None,
           hits: list[Hit] | None = None) -> Answer:
    """hits: pass pre-retrieved chunks to hold retrieval fixed (evaluation experiments)."""
    t0 = time.time()
    if hits is None:
        hits = search(question, groups, doc_id=doc_id, k=20, rerank=True)
    hits = hits[:TOP_N]
    top = hits[0].reranker_score if hits else None
    if not hits:
        return Answer("ABSTAIN", "", "", [], "no evidence retrieved", None, 0, 0, round(time.time() - t0, 1))
    if top is not None and top < MIN_RERANKER_SCORE:
        return Answer("ABSTAIN", "", "", [], f"irrelevant retrieval (top reranker score {top:.2f} < {MIN_RERANKER_SCORE})",
                      top, 0, 0, round(time.time() - t0, 1))

    raw, tokens = generate(question, hits)
    determination = str(raw.get("determination", "unclear")).lower()
    findings, dropped = validate(raw, hits)
    status, reason = route(determination, findings, dropped)
    return Answer(status, determination, raw.get("answer", ""), findings, reason, top, dropped, tokens,
                  round(time.time() - t0, 1))


def as_dict(a: Answer) -> dict:
    return asdict(a)
