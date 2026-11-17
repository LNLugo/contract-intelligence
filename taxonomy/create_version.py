"""Create a new DRAFT taxonomy version from an existing one plus reviewed boundaries (ADR-0011, ADR-0028).

Copies every category and term of --from, applies the includes / excludes / extra terms in the
boundaries file, and stores the result as a draft. Nothing changes at runtime until the draft is
approved (taxonomy/approve.py) and exported (taxonomy/export_snapshot.py).

    python taxonomy/create_version.py taxonomy/boundaries/cuad-v2.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    src, dst, cats = spec["from_version"], spec["to_version"], spec["categories"]
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM taxonomy_version WHERE version = %s", (dst,))
        row = cur.fetchone()
        if row and row[0] != "draft":
            sys.exit(f"{dst} is {row[0]}; approved or retired versions are never edited. Use a new version name.")
        cur.execute("SELECT 1 FROM taxonomy_version WHERE version = %s", (src,))
        if not cur.fetchone():
            sys.exit(f"No taxonomy version {src!r}")
        cur.execute("INSERT INTO taxonomy_version (version, status, source) VALUES (%s, 'draft', %s) "
                    "ON CONFLICT (version) DO UPDATE SET source = EXCLUDED.source", (dst, spec["source"][:500]))
        cur.execute("""INSERT INTO clause_category (version, code, name, definition, includes, excludes, owner)
                       SELECT %s, code, name, definition, includes, excludes, owner FROM clause_category WHERE version = %s
                       ON CONFLICT (version, code) DO NOTHING""", (dst, src))
        cur.execute("""INSERT INTO category_term (version, code, term)
                       SELECT %s, code, term FROM category_term WHERE version = %s ON CONFLICT DO NOTHING""", (dst, src))
        for code, b in cats.items():
            cur.execute("SELECT 1 FROM clause_category WHERE version = %s AND code = %s", (dst, code))
            if not cur.fetchone():
                sys.exit(f"Unknown category {code!r} in {src}")
            if "includes" in b or "excludes" in b:
                cur.execute("UPDATE clause_category SET includes = %s, excludes = %s WHERE version = %s AND code = %s",
                            (b.get("includes", []), b.get("excludes", []), dst, code))
            for term in b.get("terms", []):
                cur.execute("INSERT INTO category_term (version, code, term) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                            (dst, code, term.lower()))
        cur.execute("SELECT count(*), count(*) FILTER (WHERE cardinality(includes) + cardinality(excludes) > 0) "
                    "FROM clause_category WHERE version = %s", (dst,))
        n, with_b = cur.fetchone()
    print(f"{dst} (draft): {n} categories, {with_b} with boundaries. Next: measure, then approve.py --version {dst}")


if __name__ == "__main__":
    main()
