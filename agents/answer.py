"""Slice 1 answering: generate a determination with cited evidence, validate citations
in code, and route the result in code (ADR-0009, ADR-0020, ADR-0021).

The model returns a `determination` (present / absent / unclear) separately from the
evidence it cites. Routing is decided by code from both:
  ANSWERED   determination present, and at least one finding survived citation validation
  NOT_FOUND  determination absent (evidence may still be cited to explain why)
  ABSTAIN    determination unclear, weak retrieval, or a "present" whose citations all failed
"""
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import _ingestion  # noqa: F401
from .citations import check_quote
from .retrieve import Hit, search
from pipeline import http
from pipeline.config import SETTINGS as S

# Deployment name, not just model: evaluation runs use their own deployment with its own
# rate limit (infra/03c), so they never compete with interactive traffic (ADR-0014).
CHAT_MODEL = os.environ.get("CHAT_DEPLOYMENT", "gpt-5.4-mini")
TOP_N = 5                       # chunks the model sees (ADR-0006: top 20 -> top 5)
MIN_RERANKER_SCORE = 1.5        # floor against irrelevant retrieval only (ADR-0009 revision)
# Semantic reranking has a monthly quota on the Free search tier; RERANK=false turns it off
# (the irrelevance floor then cannot apply, and abstention relies on the model's determination)
RERANK = os.environ.get("RERANK", "true").lower() == "true"

from .prompts import DEFAULT as DEFAULT_PROMPT, PROMPTS


@dataclass
class Citation:
    clause: str
    quote: str
    valid: bool
    file_name: str = ""
    pages: str = ""
    match: str = ""        # exact | fuzzy | "" (ADR-0029)
    reason: str = ""       # why it failed: too_short | not_in_clause | fuzzy_changed_meaning | no_clause
    start: int = -1        # character offsets into the cited clause's text, for highlighting
    end: int = -1


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
    samples: list[str] = field(default_factory=list)   # status of each sample (ADR-0022)
    citation_checks: dict = field(default_factory=dict) # counts of exact / fuzzy / each failure reason (ADR-0029)


def quote_in_clause(quote: str, clause: str) -> bool:
    """Kept for callers and tests that only need yes or no. The rule lives in citations.py."""
    return check_quote(quote, clause).valid


def _context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[C{i}] ({h.file_name}, pages {h.page_start}-{h.page_end}, section: {h.section_heading})\n{h.content}"
                       for i, h in enumerate(hits, 1))


def _boundaries(question: str) -> str:
    from .taxonomy_snapshot import boundaries_text
    b = boundaries_text(question)
    return f"{b}\n\n" if b else ""


def generate(question: str, hits: list[Hit], prompt: str = DEFAULT_PROMPT) -> tuple[dict, int]:
    body = {"model": CHAT_MODEL, "response_format": {"type": "json_object"},
            "max_completion_tokens": 2000,
            "messages": [{"role": "system", "content": PROMPTS[prompt]},
                         {"role": "user", "content": f"Question: {question}\n\n{_boundaries(question)}Clauses:\n{_context(hits)}"}]}
    resp = http.request("POST", f"{S.aoai_endpoint}/chat/completions", http.COGNITIVE_SCOPE, json=body).json()
    text = resp["choices"][0]["message"]["content"] or "{}"
    return json.loads(text), resp.get("usage", {}).get("total_tokens", 0)


def validate_with(raw: dict, lookup) -> tuple[list[Finding], int, dict]:
    """Keep findings with at least one citation whose quote is really in the clause it cites
    (ADR-0020, ADR-0029). lookup(clause_id) returns the cited Hit or None. Same rule for the
    workflow and the agent. Returns (findings kept, findings dropped, citation check counts)."""
    findings, dropped, checks = [], 0, Counter()
    for f in raw.get("findings", []) or []:
        cites = []
        for c in f.get("citations", []) or []:
            cid = str(c.get("clause", "")).upper().strip()
            hit = lookup(cid)
            quote = str(c.get("quote", ""))
            r = check_quote(quote, hit.content if hit else None)
            checks[r.match or r.reason] += 1
            cites.append(Citation(cid, quote, r.valid, hit.file_name if hit else "",
                                  f"{hit.page_start}-{hit.page_end}" if hit else "", r.match, r.reason, r.start, r.end))
        finding = Finding(f.get("statement", ""), cites)
        if finding.supported:
            findings.append(finding)
        else:
            dropped += 1
    return findings, dropped, dict(checks)


def validate(raw: dict, hits: list[Hit]) -> tuple[list[Finding], int, dict]:
    def lookup(cid: str):
        idx = cid.lstrip("C")
        return hits[int(idx) - 1] if idx.isdigit() and 1 <= int(idx) <= len(hits) else None
    return validate_with(raw, lookup)


def route(determination: str, findings: list[Finding], dropped: int) -> tuple[str, str]:
    """Code decides the outcome (ADR-0009, ADR-0021). Returns (status, reason)."""
    if determination == "present":
        if findings:
            return "ANSWERED", ""
        return "ABSTAIN", f"determination present but all {dropped} finding(s) failed citation validation"
    if determination == "absent":
        return "NOT_FOUND", "determination absent"
    return "ABSTAIN", "model could not determine from the evidence (unclear): route to a reviewer"


def _one_sample(question: str, hits: list[Hit], prompt: str):
    raw, tokens = generate(question, hits, prompt)
    determination = str(raw.get("determination", "unclear")).lower()
    findings, dropped, checks = validate(raw, hits)
    status, reason = route(determination, findings, dropped)
    return status, determination, raw.get("answer", ""), findings, reason, dropped, tokens, checks


def agree(statuses: list[str]) -> tuple[bool, str]:
    """ADR-0022: act only when every sample reached the same outcome."""
    counts = Counter(statuses)
    if len(counts) == 1:
        return True, ""
    return False, "samples disagree (" + ", ".join(f"{k} x{v}" for k, v in counts.most_common()) + "): route to a reviewer"


def answer(question: str, groups: list[str], doc_id: str | None = None,
           hits: list[Hit] | None = None, prompt: str = DEFAULT_PROMPT, samples: int = 1) -> Answer:
    """hits: pass pre-retrieved chunks to hold retrieval fixed (evaluation experiments).
    samples: independent answers to draw; with more than one, disagreement abstains (ADR-0022)."""
    t0 = time.time()
    if hits is None:
        hits = search(question, groups, doc_id=doc_id, k=20, rerank=RERANK)
    hits = hits[:TOP_N]
    top = hits[0].reranker_score if hits else None
    if not hits:
        return Answer("ABSTAIN", "", "", [], "no evidence retrieved", None, 0, 0, round(time.time() - t0, 1))
    if top is not None and top < MIN_RERANKER_SCORE:
        return Answer("ABSTAIN", "", "", [], f"irrelevant retrieval (top reranker score {top:.2f} < {MIN_RERANKER_SCORE})",
                      top, 0, 0, round(time.time() - t0, 1))

    if samples == 1:
        runs = [_one_sample(question, hits, prompt)]
    else:
        with ThreadPoolExecutor(max_workers=samples) as pool:
            runs = list(pool.map(lambda _: _one_sample(question, hits, prompt), range(samples)))
    tokens = sum(r[6] for r in runs)
    statuses = [r[0] for r in runs]
    ok, why = agree(statuses)
    status, determination, text, findings, reason, dropped, _, checks = runs[0]
    if not ok:
        return Answer("ABSTAIN", determination, text, [], why, top, dropped, tokens,
                      round(time.time() - t0, 1), statuses, checks)
    return Answer(status, determination, text, findings, reason, top, dropped, tokens,
                  round(time.time() - t0, 1), statuses, checks)


def as_dict(a: Answer) -> dict:
    return asdict(a)
