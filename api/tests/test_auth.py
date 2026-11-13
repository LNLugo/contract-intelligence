"""The API takes groups only from a validated token (ADR-0023, ADR-0024). No network calls:
tokens are signed here with a test key, and search is replaced by a recorder."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
pytest.importorskip("azure.identity")
jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import auth, main  # noqa: E402

TENANT, AUD = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def wiring(monkeypatch):
    monkeypatch.setattr(auth, "settings", lambda: auth.Settings(TENANT, AUD, ISS))
    monkeypatch.setattr(auth, "signing_key", lambda token: KEY.public_key())
    calls = []

    def fake_search(query, groups, **kw):
        calls.append({"query": query, "groups": groups, **kw})
        return []
    monkeypatch.setattr(main.retrieve, "search", fake_search)
    return calls


def token(roles=("Contracts.Legal",), key=KEY, alg="RS256", **override):
    now = int(time.time())
    claims = {"iss": ISS, "aud": AUD, "tid": TENANT, "oid": "caller-oid", "azp": "client-app",
              "iat": now, "nbf": now, "exp": now + 600, "roles": list(roles), **override}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg)


client = TestClient(main.app)


def post(tok, body=None, headers=None):
    h = {"Authorization": f"Bearer {tok}"} if tok else {}
    return client.post("/search", json=body or {"query": "termination"}, headers={**h, **(headers or {})})


def test_groups_come_from_the_token(wiring):
    assert post(token(("Contracts.Procurement",))).status_code == 200
    assert wiring[-1]["groups"] == ["grp-procurement"]


def test_both_roles_give_both_groups(wiring):
    post(token(("Contracts.Legal", "Contracts.Procurement")))
    assert wiring[-1]["groups"] == ["grp-legal", "grp-procurement"]


@pytest.mark.parametrize("field", ["groups", "allowed_groups", "filter", "roles"])
def test_forged_entitlements_in_body_are_refused(wiring, field):
    r = post(token(), {"query": "termination", field: ["grp-procurement"]})
    assert r.status_code == 422 and not wiring


def test_forged_headers_change_nothing(wiring):
    post(token(), headers={"X-Groups": "grp-procurement", "X-MS-CLIENT-PRINCIPAL-ROLES": "Contracts.Procurement"})
    assert wiring[-1]["groups"] == ["grp-legal"]


@pytest.mark.parametrize("tok", [
    None,                                               # no token
    "not-a-jwt",                                        # malformed
    "PLACEHOLDER_WRONG_KEY",                            # signed by someone else
    "PLACEHOLDER_EXPIRED",
    "PLACEHOLDER_WRONG_AUD",
    "PLACEHOLDER_WRONG_ISS",
    "PLACEHOLDER_WRONG_TENANT",
    "PLACEHOLDER_NO_OID",
])
def test_invalid_tokens_are_refused(wiring, tok):
    now = int(time.time())
    tok = {
        "PLACEHOLDER_WRONG_KEY": lambda: token(key=OTHER_KEY),
        "PLACEHOLDER_EXPIRED": lambda: token(iat=now - 7200, nbf=now - 7200, exp=now - 3600),
        "PLACEHOLDER_WRONG_AUD": lambda: token(aud="api://someone-else"),
        "PLACEHOLDER_WRONG_ISS": lambda: token(iss="https://login.microsoftonline.com/evil/v2.0"),
        "PLACEHOLDER_WRONG_TENANT": lambda: token(tid="33333333-3333-3333-3333-333333333333"),
        "PLACEHOLDER_NO_OID": lambda: token(oid=None),
    }.get(tok, lambda: tok)()
    assert post(tok).status_code == 401 and not wiring


def test_alg_none_is_refused(wiring):
    unsigned = jwt.encode({"iss": ISS, "aud": AUD, "tid": TENANT, "oid": "x", "roles": ["Contracts.Legal"],
                           "exp": int(time.time()) + 600, "iat": int(time.time())}, None, algorithm="none")
    assert post(unsigned).status_code == 401 and not wiring


@pytest.mark.parametrize("roles", [(), ("Contracts.Admin",), ("grp-legal",)])
def test_no_contract_role_means_forbidden(wiring, roles):
    assert post(token(roles)).status_code == 403 and not wiring


def test_doc_id_is_validated_before_search(wiring):
    r = post(token(), {"query": "x", "doc_id": "' or 1 eq 1 or '"})
    assert r.status_code == 422 and not wiring


def test_health_needs_no_token():
    assert client.get("/health").json() == {"status": "ok"}


def test_hs256_signed_with_a_guessable_secret_is_refused(wiring):
    # Algorithm confusion: an attacker signs with HMAC; only RS256 is accepted
    forged = jwt.encode({"iss": ISS, "aud": AUD, "tid": TENANT, "oid": "x", "roles": ["Contracts.Legal"],
                         "exp": int(time.time()) + 600, "iat": int(time.time())}, "a" * 32, algorithm="HS256")
    assert post(forged).status_code == 401 and not wiring


def test_ask_uses_groups_from_token_and_refuses_forged_fields(monkeypatch):
    seen = {}

    def fake_run(groups, question, doc_id=None):
        seen["groups"] = groups
        return {"status": "ANSWERED", "clause": {"status": "ANSWERED", "findings": []}, "vendor": {"status": "NOT_REQUESTED"},
                "category": None, "taxonomy_version": "t"}
    monkeypatch.setattr(main.orchestrator, "run", fake_run)
    h = {"Authorization": f"Bearer {token(('Contracts.Procurement',))}"}
    assert client.post("/ask", json={"question": "q"}, headers=h).status_code == 200
    assert seen["groups"] == ("grp-procurement",)
    assert client.post("/ask", json={"question": "q", "groups": ["grp-legal"]}, headers=h).status_code == 422
    assert client.post("/ask", json={"question": "q"}).status_code == 401
