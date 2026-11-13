"""Publish the APPROVED taxonomy version as a snapshot the API loads at startup (ADR-0026).

Approval stays in PostgreSQL (ADR-0011). The deployed API never connects to the database:
it reads this file, which is committed (reviewed like code) and baked into the image.
The snapshot records its version and a content hash; every answer reports the version it used.

Usage (laptop, repo root, venv active, PostgreSQL started):
    python taxonomy/export_snapshot.py
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402

OUT = Path(__file__).resolve().parent / "snapshots" / "approved.json"


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT version, approved_by, approved_at FROM taxonomy_version WHERE status = 'approved'")
        row = cur.fetchone()
        if not row:
            sys.exit("No approved taxonomy version. Approve one first: python taxonomy/approve.py --version cuad-v1-draft")
        version, approved_by, approved_at = row
        cur.execute("""SELECT code, name, definition, includes, excludes, owner FROM clause_category
                       WHERE version = %s ORDER BY code""", (version,))
        cats = {r[0]: {"code": r[0], "name": r[1], "definition": r[2], "includes": list(r[3]),
                       "excludes": list(r[4]), "owner": r[5], "terms": []} for r in cur.fetchall()}
        cur.execute("SELECT code, term FROM category_term WHERE version = %s ORDER BY code, term", (version,))
        for code, term in cur.fetchall():
            cats[code]["terms"].append(term)
    categories = list(cats.values())
    digest = hashlib.sha256(json.dumps(categories, sort_keys=True).encode()).hexdigest()[:16]
    snapshot = {"version": version, "approved_at": approved_at.isoformat() if approved_at else None,
                "approved_by_role": "Legal",       # the approver's account stays in the database, not the public repo
                "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "content_sha256_16": digest, "categories": categories}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported {version}: {len(categories)} categories, "
          f"{sum(len(c['terms']) for c in categories)} terms, hash {digest} -> {OUT}")


if __name__ == "__main__":
    main()
