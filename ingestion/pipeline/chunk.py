"""Clean and chunk a layout result (ADR-0005).

v1 strategy: a fixed token budget per chunk with overlap, filled with whole
paragraphs. Paragraph boundaries are kept because every paragraph carries its
page number, which citations need. A paragraph longer than the budget is split
on sentence and then word boundaries.
"""
import re
from dataclasses import dataclass, field

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")   # text-embedding-3 tokenizer

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:  # offline fallback, used in unit tests without the tokenizer download
    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

# Layout roles that are page furniture, not contract content
SKIP_ROLES = {"pageHeader", "pageFooter", "pageNumber"}
HEADING_ROLES = {"title", "sectionHeading"}

_SELECTION = re.compile(r":(un)?selected:|[☐☑☒]")
_SPACES = re.compile(r"[ \t ]+")
_SENTENCE = re.compile(r"(?<=[.;:])\s+")


def clean(text: str) -> str:
    """Strip selection-mark tokens and normalize whitespace (build log, 2026-11-07)."""
    text = _SELECTION.sub(" ", text)
    text = _SPACES.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


@dataclass
class Para:
    text: str
    page: int
    role: str | None
    tokens: int = 0


@dataclass
class Chunk:
    index: int
    content: str
    section_heading: str
    page_start: int
    page_end: int
    tokens: int
    paragraphs: list[int] = field(default_factory=list)


def paragraphs(layout: dict) -> list[Para]:
    out = []
    for p in layout.get("paragraphs", []):
        role = p.get("role")
        if role in SKIP_ROLES:
            continue
        text = clean(p.get("content", ""))
        if not text:
            continue
        regions = p.get("boundingRegions") or [{"pageNumber": 1}]
        out.append(Para(text, regions[0]["pageNumber"], role, count_tokens(text)))
    return out


def _split_long(p: Para, budget: int) -> list[Para]:
    if p.tokens <= budget:
        return [p]
    pieces, current = [], ""
    units = _SENTENCE.split(p.text)
    if any(count_tokens(u) > budget for u in units):
        units = p.text.split(" ")
    for u in units:
        candidate = f"{current} {u}".strip()
        if current and count_tokens(candidate) > budget:
            pieces.append(current)
            current = u
        else:
            current = candidate
    if current:
        pieces.append(current)
    return [Para(t, p.page, p.role, count_tokens(t)) for t in pieces]


def chunk(layout: dict, budget: int = 800, overlap: int = 120) -> list[Chunk]:
    paras: list[Para] = []
    for p in paragraphs(layout):
        paras.extend(_split_long(p, budget))
    if not paras:
        return []

    heading_at, current = [], ""
    for p in paras:
        if p.role in HEADING_ROLES:
            current = p.text
        heading_at.append(current)

    chunks, i, n = [], 0, len(paras)
    while i < n:
        j, total = i, 0
        while j < n and (j == i or total + paras[j].tokens <= budget):
            total += paras[j].tokens
            j += 1
        members = paras[i:j]
        chunks.append(Chunk(
            index=len(chunks),
            content="\n\n".join(p.text for p in members),
            section_heading=heading_at[i],
            page_start=min(p.page for p in members),
            page_end=max(p.page for p in members),
            tokens=total,
            paragraphs=list(range(i, j)),
        ))
        if j >= n:
            break
        k, carried = j, 0                      # step back to create the overlap
        while k - 1 > i and carried + paras[k - 1].tokens <= overlap:
            carried += paras[k - 1].tokens
            k -= 1
        i = k
    return chunks


def embedding_text(c: Chunk, file_name: str) -> str:
    """Text sent to the embedding model: the chunk plus its document and section,
    so a clause like 'Either party may terminate...' is embedded with its context."""
    header = file_name.rsplit(".", 1)[0]
    if c.section_heading and c.section_heading not in c.content[:200]:
        header += f"\n{c.section_heading}"
    return f"{header}\n\n{c.content}"
