"""Runtime taxonomy from the approved snapshot (ADR-0026). No database at request time.

Maps a question to at most one clause category by its name, code or mapped terms (longest match
wins). No match means no category: the answer still runs, and the category is reported as none,
never guessed.
"""
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "taxonomy" / "snapshots" / "approved.json"


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    definition: str
    version: str


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


@lru_cache(maxsize=1)
def snapshot() -> dict:
    path = Path(os.environ.get("TAXONOMY_SNAPSHOT", DEFAULT))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("version") or not data.get("categories"):
        raise RuntimeError(f"Taxonomy snapshot {path} is empty or has no version")
    return data


@lru_cache(maxsize=1)
def _phrases() -> list[tuple[str, dict]]:
    out = []
    for c in snapshot()["categories"]:
        # Names and codes always match; mapped terms only when they are phrases of 2+ words.
        # A one-word term ("parties", "assign") matches almost any question and picks the wrong
        # category (build log 2026-11-16: Exclusivity questions were classified as Parties).
        names = {c["name"], c["code"].replace("_", " ")}
        terms = {t for t in c.get("terms", []) if len(_norm(t).split()) >= 2}
        for p in names | terms:
            if p and len(p.strip()) >= 3:
                out.append((_norm(p), c))
    return sorted(out, key=lambda x: len(x[0]), reverse=True)     # longest phrase first


def version() -> str:
    return snapshot()["version"]


def boundaries_text(question: str) -> str:
    """The approved boundaries (includes / excludes) for the question's category, for the prompt
    (ADR-0028). Empty when the category is unknown, has no boundaries, or BOUNDARIES=false."""
    if os.environ.get("BOUNDARIES", "true").lower() != "true":
        return ""
    cat = classify(question)
    if cat is None:
        return ""
    c = next(x for x in snapshot()["categories"] if x["code"] == cat.code)
    if not (c.get("includes") or c.get("excludes")):
        return ""
    lines = [f"Category boundaries for {c['name']} (approved taxonomy {version()}):"]
    lines += [f"- Counts: {x}" for x in c.get("includes", [])]
    lines += [f"- Does not count: {x}" for x in c.get("excludes", [])]
    return "\n".join(lines)


def classify(question: str) -> Category | None:
    q = _norm(question)
    for phrase, c in _phrases():
        if phrase in q:
            return Category(c["code"], c["name"], c["definition"], version())
    return None
