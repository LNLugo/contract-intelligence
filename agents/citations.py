"""Citation check (ADR-0020, revised by ADR-0029): is the quote really in the clause it cites?

Rules, applied identically to the workflow and the agent:
  1. Quote and clause are cleaned the same way: Unicode NFKC (ligatures, full-width forms),
     typographic quotes and dashes mapped to plain ones (NFKC leaves those alone), and runs of
     whitespace collapsed to one space.
  2. The cleaned quote must be at least MIN_CHARS long. Shorter quotes match almost anywhere.
  3. EXACT: the cleaned quote appears in the cleaned clause, character for character.
  4. FUZZY, only for PDF and OCR noise (hyphenation at line breaks, stray characters): rapidfuzz
     partial_ratio >= FUZZY_MIN against the clause, AND the quote and the matched span contain
     the same negations and the same numbers. A fuzzy match may never add, drop or change
     "not", "no", "unless", a number or an amount: those are the words that change a contract's meaning.
  5. A quote with "..." that is not an exact match fails as "elided": the omitted text is where an
     "unless" or "subject to" would hide, so a citation must show the full text it relies on.
  6. Anything else fails, with a reason. Passing citations carry character offsets into the
     ORIGINAL clause text, so a reviewer can highlight the exact span.

No model call, no cost, deterministic.
"""
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

MIN_CHARS = 40          # 15 lets "the Agreement shall" match almost anywhere
FUZZY_MIN = 95.0        # rapidfuzz partial_ratio, 0-100

# Words whose presence or absence reverses or conditions an obligation.
MEANING_WORDS = {"not", "no", "never", "neither", "nor", "none", "without", "unless", "except",
                 "notwithstanding", "shall", "may", "must", "only"}
_TYPO = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                       "“": '"', "”": '"', "„": '"', "‟": '"',
                       "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                       " ": " ", "­": ""})   # soft hyphen removed
_WORD = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")


@dataclass
class QuoteCheck:
    valid: bool
    match: str          # "exact" | "fuzzy" | ""
    reason: str         # "" when valid; else too_short | elided | not_in_clause | fuzzy_changed_meaning | no_clause
    start: int = -1     # offsets into the ORIGINAL clause text (end exclusive)
    end: int = -1
    score: float = 0.0


def norm(text: str) -> str:
    return normalize_with_map(text)[0]


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Clean text and keep, for every output character, the index of the original character it
    came from, so a match in cleaned text can be mapped back to the source."""
    out, idx = [], []
    prev_space = True                      # drops leading whitespace
    for i, ch in enumerate(text or ""):
        for c in unicodedata.normalize("NFKC", ch).translate(_TYPO):
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = " ", True
            else:
                prev_space = False
            out.append(c)
            idx.append(i)
    if out and out[-1] == " ":
        out.pop(); idx.pop()
    return "".join(out), idx


def _meaning(text: str) -> list[str]:
    """Negations, modal verbs and numbers, in order."""
    return [w for w in _WORD.findall(text.lower()) if w in MEANING_WORDS or w[0].isdigit()]


def is_verbatim(source: str, quote: str, min_chars: int = MIN_CHARS) -> bool:
    q = norm(quote)
    return len(q) >= min_chars and q in norm(source)


def check_quote(quote: str, clause: str | None) -> QuoteCheck:
    if clause is None:
        return QuoteCheck(False, "", "no_clause")
    q = norm(quote)
    if len(q) < MIN_CHARS:
        return QuoteCheck(False, "", "too_short")
    c, cmap = normalize_with_map(clause)
    if not c:
        return QuoteCheck(False, "", "not_in_clause")
    pos = c.find(q)
    if pos >= 0:
        return QuoteCheck(True, "exact", "", cmap[pos], cmap[pos + len(q) - 1] + 1, 100.0)
    if "..." in q or "\u2026" in quote:
        return QuoteCheck(False, "", "elided")
    al = fuzz.partial_ratio_alignment(q, c)
    if al is None or al.score < FUZZY_MIN:
        return QuoteCheck(False, "", "not_in_clause", score=al.score if al else 0.0)
    span = c[al.dest_start:al.dest_end]
    if _meaning(q) != _meaning(span):
        return QuoteCheck(False, "", "fuzzy_changed_meaning", score=al.score)
    return QuoteCheck(True, "fuzzy", "", cmap[al.dest_start], cmap[al.dest_end - 1] + 1, al.score)
