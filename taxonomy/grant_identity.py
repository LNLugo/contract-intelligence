"""Give a managed identity its own least-privilege PostgreSQL role (ADR-0011, ADR-0013).

The identity signs in with an Entra token, like a user; there is no password to store.
Privileges: read the taxonomy, and add rows to the unmapped-term log. Nothing else: no admin,
no updates, no deletes, no access to other tables.

Run as the Entra admin from the laptop:
    python taxonomy/grant_identity.py --identity fn-ci-dev-2416

The role name is the managed identity's display name (for a system-assigned identity, the
app's name). The network path from the Function to PostgreSQL is deliberately NOT opened
yet: see ADR-0011, "Network path".
"""
import argparse
import sys
from pathlib import Path

from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import DBNAME, connect  # noqa: E402

READ_TABLES = ["taxonomy_version", "clause_category", "category_term"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", required=True, help="managed identity display name, e.g. fn-ci-dev-2416")
    args = ap.parse_args()
    role = sql.Identifier(args.identity)

    # Entra principals are created from the postgres database (server-level role)
    with connect("postgres") as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (args.identity,))
        if cur.fetchone():
            print(f"Role {args.identity} already exists")
        else:
            cur.execute("SELECT * FROM pgaadauth_create_principal(%s, false, false)", (args.identity,))
            print(f"Created Entra role {args.identity} (not admin, no MFA requirement: it is a service identity)")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DBNAME), role))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        for t in READ_TABLES:
            cur.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(t), role))
        cur.execute(sql.SQL("GRANT INSERT ON unmapped_term TO {}").format(role))
        cur.execute(sql.SQL("GRANT USAGE ON SEQUENCE unmapped_term_id_seq TO {}").format(role))
        cur.execute("""
            SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
            FROM information_schema.role_table_grants
            WHERE grantee = %s GROUP BY table_name ORDER BY table_name""", (args.identity,))
        print(f"\nPrivileges held by {args.identity} in {DBNAME}:")
        for table, privs in cur.fetchall():
            print(f"  {table:18s} {privs}")


if __name__ == "__main__":
    main()
