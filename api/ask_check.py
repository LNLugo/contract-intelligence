"""End-to-end check of /ask with REAL Entra tokens (ADR-0026). All calls go through the API.

    python -m api.ask_check --base-url URL                       # vendor system up
    python -m api.ask_check --base-url URL --expect-vendor-down  # after stopping the mock SAP app

Finds, through the API itself, one contract both groups can see and one only legal can see.
Exit code 1 on any failure. Tokens are never printed.
"""
import argparse
import sys

import httpx

from identity.tokens import get_token


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--expect-vendor-down", action="store_true")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120)
    auth = {n: {"Authorization": f"Bearer {get_token(n)}"} for n in ("legal", "procurement")}
    ok = []

    def check(name, cond, detail=""):
        ok.append(bool(cond))
        print(f"  {'OK  ' if cond else 'FAIL'} {name}  {detail}")

    def ask(who, question, doc_id):
        r = c.post("/ask", json={"question": question, "doc_id": doc_id}, headers=auth[who])
        if r.status_code != 200:
            check(f"{who}: /ask HTTP", False, r.status_code)
            return None
        return r.json()

    # Pick contracts through the API: shared (both groups) and legal-only
    docs = [h["doc_id"] for h in c.post("/search", json={"query": "agreement", "k": 20}, headers=auth["legal"]).json()]
    docs = list(dict.fromkeys(docs))
    shared = legal_only = None
    for d in docs:
        seen = c.post("/search", json={"query": "agreement", "doc_id": d, "k": 1}, headers=auth["procurement"]).json()
        if seen and not shared:
            shared = d
        if not seen and not legal_only:
            legal_only = d
    check("found a shared and a legal-only contract", shared and legal_only, f"shared={shared} legal_only={legal_only}")
    if not (shared and legal_only):
        sys.exit(1)

    r = ask("legal", "Is there a cap on liability in this contract?", shared)
    if r:
        check("legal: clause answer with taxonomy", r["clause"]["status"] in ("ANSWERED", "NOT_FOUND", "ABSTAIN")
              and r["taxonomy_version"], f"clause={r['clause']['status']} category={(r['category'] or {}).get('code')} "
              f"taxonomy={r['taxonomy_version']}")
        check("legal: no vendor call without vendor intent", r["vendor"]["status"] == "NOT_REQUESTED", r["vendor"]["status"])

    r = ask("procurement", "What are the vendor payment terms for this contract?", shared)
    if r:
        want = ("ABSTAIN",) if args.expect_vendor_down else ("OK", "NOT_FOUND")
        check(f"procurement: vendor for a visible contract -> {'/'.join(want)}", r["vendor"]["status"] in want,
              f"{r['vendor']['status']} {r['vendor'].get('reason', '')}")
        if args.expect_vendor_down:
            check("procurement: clause answer still returned", r["clause"]["status"] in ("ANSWERED", "NOT_FOUND", "ABSTAIN"),
                  f"overall={r['status']} clause={r['clause']['status']}")

    r = ask("procurement", "Is the vendor blocked for this contract?", legal_only)
    if r:
        check("procurement: vendor for a legal-only contract refused", r["vendor"]["status"] == "NOT_AVAILABLE",
              r["vendor"]["status"])
        check("procurement: no clause evidence from the legal-only contract", not r["clause"]["findings"],
              f"clause={r['clause']['status']}")

    print("PASS" if all(ok) else "FAIL")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    main()
