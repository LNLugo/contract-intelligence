"""Read the governed clause taxonomy (ADR-0011). Runtime reads ONLY the approved version.

    python -m agents.taxonomy "Cap On Liability"
    python -m agents.taxonomy "cap on liability"    # names, codes and mapped terms all resolve
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "taxonomy"))
from db import connect  # noqa: E402


class NoApprovedTaxonomy(RuntimeError):
    pass


def _code(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@lru_cache(maxsize=1)
def approved_version() -> str:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT version FROM taxonomy_version WHERE status = 'approved'")
        row = cur.fetchone()
    if not row:
        raise NoApprovedTaxonomy("No approved taxonomy version: approve one with taxonomy/approve.py")
    return row[0]


def category(name_or_term: str) -> dict | None:
    """Resolve a category by code, name or mapped term in the approved version.
    Unresolved terms are logged to unmapped_term for Legal review, never guessed."""
    version = approved_version()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.code, c.name, c.definition, c.includes, c.excludes, c.owner
            FROM clause_category c
            LEFT JOIN category_term t ON t.version = c.version AND t.code = c.code
            WHERE c.version = %s AND (c.code = %s OR lower(c.name) = lower(%s) OR t.term = lower(%s))
            LIMIT 1""", (version, _code(name_or_term), name_or_term, name_or_term))
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO unmapped_term (term, seen_in) VALUES (%s, %s)", (name_or_term, "agents.taxonomy"))
            return None
    code, name, definition, includes, excludes, owner = row
    return {"version": version, "code": code, "name": name, "definition": definition,
            "includes": includes, "excludes": excludes, "owner": owner}


if __name__ == "__main__":
    term = " ".join(sys.argv[1:]) or "Cap On Liability"
    c = category(term)
    if c is None:
        print(f"'{term}' is not in the approved taxonomy; logged to unmapped_term for Legal review")
    else:
        print(f"[{c['version']}] {c['name']} ({c['code']}), owner {c['owner']}")
        print(f"  definition: {c['definition']}")
        print(f"  includes:   {c['includes'] or '(none yet)'}")
        print(f"  excludes:   {c['excludes'] or '(none yet)'}")
