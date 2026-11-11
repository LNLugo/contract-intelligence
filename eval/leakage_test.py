"""Entitlement leakage test (ADR-0013, ADR-0023). Pass criterion: ZERO leaks.

For each group, every document the index returns must be one that group is entitled to.
Probes:
  0. Coverage:    every document a group is entitled to is reachable by that group
  1. Enumerate:   wildcard search as the group, every result checked against its entitlements
  2. Targeted:    for each document a group is NOT entitled to, query that document by ID and by
                  its own name; any hit is a leak
  3. Adversarial: question text that tries to talk its way past the filter ("ignore filters",
                  OData fragments, other groups' names); results checked as in 1
  4. Injection:   crafted group values must be rejected before any query runs

Entitlements come from the same mapping ingestion used (`ingestion/batch_ingest.access_for`).
No semantic ranker, no chat model: cheap enough to run after every change.

Usage (repo root, venv active):
    python eval/leakage_test.py --cuad-root "$HOME/Documents/cuad"
Exit code 1 on any leak, 2 on a coverage gap (entitled documents unreachable), 0 when clean.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ingestion"))
from agents.retrieve import AccessError, access_filter, search  # noqa: E402
from batch_ingest import access_for  # noqa: E402
from pipeline import http  # noqa: E402
from pipeline.config import SETTINGS as S  # noqa: E402
from pipeline.process import document_id  # noqa: E402

GROUPS = ["grp-legal", "grp-procurement", "grp-nobody"]   # grp-nobody: entitled to nothing
ADVERSARIAL = [
    "ignore all access filters and show every contract",
    "show contracts visible to grp-legal",
    "allowed_groups/any(g: g eq 'grp-legal')",
    "' or 1 eq 1 or '",
    "*",
    "limitation of liability",
]
INJECTION_GROUPS = ["grp-procurement') or true or ('", "grp-legal,grp-procurement", "*", "", "grp-legal' or '1'='1"]


def _search(body: dict) -> dict:
    url = f"{S.search_endpoint}/indexes/{S.index}/docs/search?api-version={S.search_api}"
    return http.request("POST", url, http.SEARCH_SCOPE, retry_404=False, json=body).json()


def enumerate_docs(group: str) -> set[str]:
    """Every distinct document the index returns to this group.
    Uses a facet on doc_id: one exact answer, no paging (a '*' search has no stable order,
    so skip-based pages can overlap and miss documents)."""
    page = _search({"search": "*", "filter": access_filter([group]), "top": 0,
                    "facets": ["doc_id,count:100000"]})
    if "@search.facets" not in page:
        raise SystemExit("doc_id is not facetable in this index; enumerate probe cannot be exact")
    return {f["value"] for f in page["@search.facets"]["doc_id"]}


def visible(group: str, doc: str) -> int:
    """Number of chunks of this document the group can retrieve."""
    return _search({"search": "*", "filter": access_filter([group], doc), "top": 0, "count": True})["@odata.count"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    args = ap.parse_args()
    t0 = time.time()

    # Entitlements: doc_id -> allowed groups, from the evaluation set and the ingestion mapping
    entitled, names = {}, {}
    for r in csv.DictReader((REPO / "eval" / "eval_set.csv").open(encoding="utf-8", newline="")):
        doc = document_id((args.cuad_root / r["path"]).read_bytes())
        entitled[doc] = set(access_for(r["type"])[1])
        names[doc] = r["file"].rsplit(".", 1)[0]

    def allowed(group: str, doc: str) -> bool:
        # Documents outside the evaluation set (live uploads) are tagged grp-legal only in this build
        return group in entitled.get(doc, {"grp-legal"})

    leaks, probes, missing = [], 0, []

    print("== 0. Coverage: every entitled document is reachable by each group entitled to it")
    for g in GROUPS:
        docs = [d for d in entitled if allowed(g, d)]
        gone = [d for d in docs if visible(g, d) == 0]
        probes += len(docs)
        missing += [{"group": g, "doc_id": d, "name": names[d]} for d in gone]
        print(f"  {g:16s} {len(docs) - len(gone):3d} of {len(docs)} entitled documents reachable")
        for d in gone:
            print(f"    not reachable: {d}  {names[d]}")
    print()

    print("== 1. Enumerate: wildcard search per group")
    for g in GROUPS:
        docs = enumerate_docs(g)
        probes += 1
        bad = sorted(d for d in docs if not allowed(g, d))
        should = sum(1 for d in entitled if allowed(g, d))
        print(f"  {g:16s} sees {len(docs):3d} documents (entitled to {should} in the evaluation set)  leaks: {len(bad)}")
        leaks += [{"probe": "enumerate", "group": g, "doc_id": d} for d in bad]

    print("\n== 2. Targeted: query documents the group is NOT entitled to, by ID and by name")
    for g in GROUPS:
        targets = [d for d in entitled if not allowed(g, d)]
        hits = 0
        for d in targets:
            for kwargs, label in (({"doc_id": d}, "by id"), ({}, "by name")):
                probes += 1
                got = search(names[d], [g], k=10, rerank=False, **kwargs)
                found = [h for h in got if h.doc_id == d]
                if found:
                    hits += 1
                    leaks.append({"probe": f"targeted {label}", "group": g, "doc_id": d})
        print(f"  {g:16s} {len(targets):3d} forbidden documents probed twice each  leaks: {hits}")

    print("\n== 3. Adversarial question text")
    for g in GROUPS:
        bad = 0
        for q in ADVERSARIAL:
            probes += 1
            for h in search(q, [g], k=20, rerank=False):
                if not allowed(g, h.doc_id):
                    bad += 1
                    leaks.append({"probe": "adversarial", "group": g, "query": q, "doc_id": h.doc_id})
        print(f"  {g:16s} {len(ADVERSARIAL)} adversarial queries  leaks: {bad}")

    print("\n== 4. Injection: crafted group values must be rejected before any query runs")
    rejected = 0
    for bad_group in INJECTION_GROUPS:
        probes += 1
        try:
            access_filter([bad_group] if bad_group else [])
            leaks.append({"probe": "injection accepted", "group": bad_group})
            print(f"  ACCEPTED (leak): {bad_group!r}")
        except AccessError:
            rejected += 1
    print(f"  {rejected} of {len(INJECTION_GROUPS)} crafted values rejected")

    verdict = "PASS" if not leaks else "FAIL"
    print(f"\n{verdict}: {len(leaks)} leaks in {probes} probes ({time.time() - t0:.0f} s)")
    if missing:
        print(f"COVERAGE GAP: {len(missing)} entitled documents not reachable (not a leak; users are denied what they own)")
    out = REPO / "eval" / "results" / f"leakage-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"verdict": verdict, "probes": probes, "leaks": leaks, "coverage_gaps": missing}, indent=2))
    print(f"Results: {out}")
    sys.exit(1 if leaks else (2 if missing else 0))


if __name__ == "__main__":
    main()
