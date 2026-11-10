"""Create the taxonomy schema and seed a DRAFT version from CUAD's 41 category descriptions.

Definitions come from CUAD's published category descriptions only (not from evaluation
misses), so the evaluation set stays a test set. `includes` and `excludes` start empty:
filling them is Legal's job, and a draft is never used at runtime until approved.

Usage (repo root, venv active, az login as the Entra admin):
    pip install "psycopg[binary]"
    python taxonomy/seed_from_cuad.py --cuad-root "$HOME/Documents/cuad"
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402

VERSION = "cuad-v1-draft"


def code_for(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    args = ap.parse_args()

    data = json.loads(next(args.cuad_root.rglob("CUAD_v1.json")).read_text(encoding="utf-8"))["data"]
    categories = {}
    for qa in data[0]["paragraphs"][0]["qas"]:          # every contract carries all 41 questions
        name = qa["id"].split("__")[-1]
        definition = qa["question"].split("Details:")[-1].strip()
        categories[code_for(name)] = (name, definition)

    schema = (Path(__file__).resolve().parent / "schema.sql").read_text()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(schema)
        cur.execute("INSERT INTO taxonomy_version (version, status, source) VALUES (%s, 'draft', %s) "
                    "ON CONFLICT (version) DO NOTHING", (VERSION, "CUAD v1 category descriptions"))
        for code, (name, definition) in categories.items():
            cur.execute("INSERT INTO clause_category (version, code, name, definition) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (version, code) DO UPDATE SET name = EXCLUDED.name, definition = EXCLUDED.definition",
                        (VERSION, code, name, definition))
            cur.execute("INSERT INTO category_term (version, code, term) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (VERSION, code, name.lower()))
        cur.execute("SELECT count(*) FROM clause_category WHERE version = %s", (VERSION,))
        n = cur.fetchone()[0]
        cur.execute("SELECT name, left(definition, 90) FROM clause_category WHERE version = %s "
                    "AND code IN ('cap_on_liability', 'exclusivity', 'termination_for_convenience') ORDER BY name",
                    (VERSION,))
        sample = cur.fetchall()

    print(f"Taxonomy version {VERSION} (draft): {n} categories")
    for name, d in sample:
        print(f"  {name:28s} {d}...")
    print("\nincludes / excludes are empty by design: Legal fills them, then approves the version.")


if __name__ == "__main__":
    main()
