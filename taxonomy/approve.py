"""Approve a taxonomy version for runtime use (ADR-0011 governance).

Only an approved version is read at runtime. Approving records who and when; any previously
approved version is retired in the same transaction (the database also enforces at most one
approved version). In this build "Legal" is me; in an enterprise this script runs only for the
Legal approver role.

Usage (repo root, venv active, az login as the Entra admin):
    python taxonomy/approve.py --version cuad-v1-draft
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import _user, connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    args = ap.parse_args()
    approver = _user()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM taxonomy_version WHERE version = %s", (args.version,))
        row = cur.fetchone()
        if not row:
            sys.exit(f"No taxonomy version {args.version!r}")
        if row[0] == "approved":
            print(f"{args.version} is already approved")
            return
        cur.execute("UPDATE taxonomy_version SET status = 'retired' WHERE status = 'approved'")
        cur.execute("UPDATE taxonomy_version SET status = 'approved', approved_by = %s, approved_at = now() "
                    "WHERE version = %s", (approver, args.version))
        cur.execute("SELECT version, status, approved_by, approved_at FROM taxonomy_version ORDER BY created_at")
        for v in cur.fetchall():
            print(f"  {v[0]:20s} {v[1]:9s} {v[2] or '':25s} {v[3] or ''}")


if __name__ == "__main__":
    main()
