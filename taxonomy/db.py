"""PostgreSQL connection with an Entra ID access token as the password (no stored password).
On the laptop the token comes from `az login`; in Azure, from the managed identity."""
import os
import subprocess

import psycopg
from azure.identity import DefaultAzureCredential

PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
HOST = f"{os.environ.get('PG', 'pg-ci-dev-2416')}.postgres.database.azure.com"
DBNAME = os.environ.get("PGDB", "contracts")


def _user() -> str:
    if os.environ.get("PGUSER"):
        return os.environ["PGUSER"]
    # The signed-in Entra user principal name is the database role name for an Entra admin
    return subprocess.run(["az", "ad", "signed-in-user", "show", "--query", "userPrincipalName", "-o", "tsv"],
                          capture_output=True, text=True, check=True, shell=os.name == "nt").stdout.strip()


def connect() -> psycopg.Connection:
    token = DefaultAzureCredential(exclude_interactive_browser_credential=True).get_token(PG_SCOPE).token
    return psycopg.connect(host=HOST, dbname=DBNAME, user=_user(), password=token, sslmode="require",
                           connect_timeout=15)
