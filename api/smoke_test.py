"""End-to-end check of the API with REAL Entra tokens (ADR-0024).

    uvicorn api.main:app --port 8000          # terminal 1
    python -m api.smoke_test                  # terminal 2 (add --base-url for a deployed API)

Exit code 1 on any failure. Tokens are never printed.
"""
import argparse
import sys

import httpx

from identity.tokens import TokenRefused, get_token

QUERY = "limitation of liability"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    base = ap.parse_args().base_url.rstrip("/")
    c = httpx.Client(base_url=base, timeout=60)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'OK  ' if ok else 'FAIL'} {name}  {detail}")

    tok = {n: get_token(n) for n in ("legal", "procurement")}
    auth = {n: {"Authorization": f"Bearer {t}"} for n, t in tok.items()}

    r = c.get("/health"); check("health without token", r.status_code == 200)
    r = c.post("/search", json={"query": QUERY}); check("search without token refused", r.status_code == 401, r.status_code)
    r = c.post("/search", json={"query": QUERY}, headers={"Authorization": "Bearer not-a-jwt"})
    check("malformed token refused", r.status_code == 401, r.status_code)

    for n, expect in (("legal", ["grp-legal"]), ("procurement", ["grp-procurement"])):
        r = c.get("/me", headers=auth[n]); groups = r.json().get("groups") if r.status_code == 200 else None
        check(f"{n}: groups from token", groups == expect, groups)

    r = c.post("/search", json={"query": QUERY, "groups": ["grp-legal"]}, headers=auth["procurement"])
    check("procurement: forged groups in body refused", r.status_code == 422, r.status_code)
    r = c.post("/search", json={"query": QUERY}, headers={**auth["procurement"], "X-Groups": "grp-legal"})
    check("procurement: forged header ignored", r.status_code == 200, r.status_code)

    docs = {}
    for n in ("legal", "procurement"):
        r = c.post("/search", json={"query": QUERY, "k": 20}, headers=auth[n])
        docs[n] = {h["doc_id"] for h in r.json()} if r.status_code == 200 else None
        check(f"{n}: search", r.status_code == 200, f"{len(docs[n] or [])} documents")
    try:
        get_token("norole"); check("norole refused a token by Entra", False)
    except TokenRefused:
        check("norole refused a token by Entra", True)

    print("PASS" if all(results) else "FAIL")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
