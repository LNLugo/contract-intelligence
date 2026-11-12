"""Get test access tokens for the API from the identity tenant (client credentials flow).

Settings and client secrets come from Key Vault (written by infra/08-identity.ps1), read with my
own Entra identity. Tokens and secrets are never printed or written to disk.

    python -m identity.tokens          # checks all three test clients
"""
import base64
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from pipeline import http  # noqa: E402

KV = os.environ.get("KV", "kv-ci-dev-2416")
VAULT_SCOPE = "https://vault.azure.net/.default"


class TokenRefused(PermissionError):
    """Entra refused to issue a token (for example, no role assigned)."""


def _secret(name: str) -> str:
    url = f"https://{KV}.vault.azure.net/secrets/{name}?api-version=7.4"
    return http.request("GET", url, VAULT_SCOPE, retry_404=False).json()["value"]


@lru_cache(maxsize=1)
def settings() -> dict:
    return json.loads(_secret("ci-identity-config"))


def get_token(client: str) -> str:
    """Access token for the API as test client 'legal', 'procurement' or 'norole'."""
    s = settings()
    resp = httpx.post(
        f"https://login.microsoftonline.com/{s['tenantId']}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": s["clients"][client],
              "client_secret": _secret(f"ci-test-{client}-secret"), "scope": s["scope"]},
        timeout=30)
    body = resp.json()
    if resp.status_code != 200:
        code = (body.get("error_description") or "").split(":")[0]
        raise TokenRefused(f"{client}: {body.get('error')} {code}")
    return body["access_token"]


def claims(token: str) -> dict:
    """Decode the payload WITHOUT verifying it. For display only; the API verifies."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def main() -> None:
    s = settings()
    ok = True
    for client, expect in (("legal", ["Contracts.Legal"]), ("procurement", ["Contracts.Procurement"]), ("norole", None)):
        try:
            c = claims(get_token(client))
            roles = c.get("roles", [])
            good = expect is not None and roles == expect and c["aud"] == s["audience"] and c["iss"] == s["issuer"]
            print(f"  {client:12s} token issued   roles={roles}  aud ok={c['aud'] == s['audience']}  "
                  f"iss ok={c['iss'] == s['issuer']}  ver={c.get('ver')}  {'OK' if good else 'UNEXPECTED'}")
        except TokenRefused as e:
            good = expect is None
            print(f"  {client:12s} token REFUSED  {e}  {'OK (no role, no token)' if good else 'UNEXPECTED'}")
        ok &= good
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
