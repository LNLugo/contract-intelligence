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
        for p in {c["name"], c["code"].replace("_", " "), *c.get("terms", [])}:
            if p and len(p.strip()) >= 3:
                out.append((_norm(p), c))
    return sorted(out, key=lambda x: len(x[0]), reverse=True)     # longest phrase first


def version() -> str:
    return snapshot()["version"]


def classify(question: str) -> Category | None:
    q = _norm(question)
    for phrase, c in _phrases():
        if phrase in q:
            return Category(c["code"], c["name"], c["definition"], version())
    return None
