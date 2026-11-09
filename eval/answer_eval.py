"""Measure slice 1 answers against CUAD labels (ADR-0012, ADR-0019).

For each (contract, category): ask the CUAD question scoped to the contract and compare
the routed outcome with the label.

  clause present + ANSWERED   -> correct detection; then: does a valid citation quote the labelled clause?
  clause present + NOT_FOUND  -> MISSED CLAUSE (the dangerous error in contract review)
  clause absent  + NOT_FOUND  -> correct
  clause absent  + ANSWERED   -> FALSE CLAIM (asserted a clause that the lawyers did not label)
  any            + ABSTAIN    -> abstained (counted, not hidden)

Usage (repo root, venv active):
    python eval/answer_eval.py --cuad-root "$HOME/Documents/cuad" --limit 2     # quick check
    python eval/answer_eval.py --cuad-root "$HOME/Documents/cuad"               # 20 contracts, 200 questions

Budget: 20 contracts (12 typical, 6 long, 2 very long) x 10 categories = 200 questions,
about 200 semantic-ranker queries (free plan: 1,000 per month) and roughly 0.8M chat tokens.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "eval"))
from agents.answer import answer  # noqa: E402
from agents.retrieve import Hit, search  # noqa: E402
from pipeline.process import document_id  # noqa: E402
from retrieval_eval import CATEGORIES, contains, key, load_labels  # noqa: E402

PER_GROUP = {"typical": 12, "long": 6, "very_long": 2}


def pick(rows: list[dict]) -> list[dict]:
    chosen = []
    for g, n in PER_GROUP.items():
        chosen += [r for r in rows if r["group"] == g][:n]
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="contracts to use (default: the 20-contract subset)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tag", default="", help="label for this run, e.g. baseline or determination-field")
    args = ap.parse_args()

    # Retrieval cache: generation experiments hold retrieval fixed (one variable at a time)
    # and do not spend semantic-ranker quota again. Delete the file to re-retrieve.
    cache_path = REPO / "eval" / "runs" / "retrieval-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    cache_hits = sum(1 for _ in cache)
    print(f"Retrieval cache: {cache_hits} entries ({'reusing' if cache_hits else 'will be created'})")

    labels = load_labels(args.cuad_root)
    rows = pick(list(csv.DictReader((REPO / "eval" / "eval_set.csv").open())))
    if args.limit:
        rows = rows[:args.limit]
    tasks = []
    for r in rows:
        lab = labels.get(key(r["file"]))
        if not lab:
            continue
        doc = document_id((args.cuad_root / r["path"]).read_bytes())
        tasks += [(r, doc, c, lab[c]) for c in CATEGORIES if c in lab]
    print(f"{len(rows)} contracts, {len(tasks)} questions\n")

    def run(t):
        r, doc, cat, lab = t
        ck = f"{doc}|{cat}"
        try:
            if ck not in cache:
                cache[ck] = [vars(h) for h in search(lab["question"], ["grp-legal"], doc_id=doc, k=20, rerank=True)[:5]]
            hits = [Hit(**h) for h in cache[ck]]
            a = answer(lab["question"], ["grp-legal"], doc, hits=hits)
        except Exception as exc:  # one failed call should not lose the run
            return {"file": r["file"], "group": r["group"], "category": cat, "present": bool(lab["answers"]),
                    "status": "ERROR", "error": str(exc)[:300]}
        present = bool(lab["answers"])
        quotes = [c.quote for f in a.findings for c in f.citations if c.valid]
        grounded = present and a.status == "ANSWERED" and any(contains(q, ans, window=6) or contains(ans, q, window=6)
                                   for q in quotes for ans in lab["answers"])
        return {"file": r["file"], "group": r["group"], "category": cat, "present": present,
                "status": a.status, "determination": a.determination, "grounded_on_label": grounded, "dropped_findings": a.dropped_findings,
                "top_reranker_score": a.top_reranker_score, "tokens": a.tokens, "seconds": a.seconds,
                "answer": a.answer[:300], "reason": a.reason}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(run, tasks))

    errors = [x for x in res if x["status"] == "ERROR"]
    if len(errors) > 0.05 * len(res):
        print(f"RUN INVALID: {len(errors)} of {len(res)} questions errored (more than 5%). No metrics reported.")
        reasons = {}
        for x in errors:
            reasons[x["error"][:120]] = reasons.get(x["error"][:120], 0) + 1
        for msg, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:3]:
            print(f"  {n:4d} x {msg}")
        print("Successful retrievals are cached; re-run the same command to continue.")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))
        return

    def outcome(x):
        if x["status"] in ("ABSTAIN", "ERROR"):
            return x["status"]
        if x["present"]:
            return "correct" if x["status"] == "ANSWERED" else "MISSED"
        return "correct" if x["status"] == "NOT_FOUND" else "FALSE_CLAIM"

    print(f"{'category':28s} {'pres':>4s} {'abs':>4s}  {'found':>6s} {'missed':>6s} {'grounded':>8s}  {'abs ok':>6s} {'false':>5s}  {'abstain':>7s}")
    for cat in CATEGORIES + ["ALL"]:
        rs = res if cat == "ALL" else [x for x in res if x["category"] == cat]
        p = [x for x in rs if x["present"]]
        a = [x for x in rs if not x["present"]]
        pd = [x for x in p if outcome(x) in ("correct", "MISSED")]
        ad = [x for x in a if outcome(x) in ("correct", "FALSE_CLAIM")]
        found = sum(outcome(x) == "correct" for x in pd)
        print(f"{cat:28s} {len(p):4d} {len(a):4d}  "
              f"{found / len(pd) if pd else float('nan'):6.0%} {sum(outcome(x) == 'MISSED' for x in pd):6d} "
              f"{sum(x.get('grounded_on_label', False) for x in p) / found if found else float('nan'):8.0%}  "
              f"{sum(outcome(x) == 'correct' for x in ad) / len(ad) if ad else float('nan'):6.0%} "
              f"{sum(outcome(x) == 'FALSE_CLAIM' for x in ad):5d}  "
              f"{sum(outcome(x) == 'ABSTAIN' for x in rs):7d}")

    ok = [x for x in res if x["status"] != "ERROR"]
    print("\nfound    = clause present and the system answered with valid citations (detection recall)")
    print("missed   = clause present but the system said NOT_FOUND (the dangerous error)")
    print("grounded = of the found clauses, share where a validated quote matches the lawyers' labelled text")
    print("abs ok   = clause absent and the system said NOT_FOUND;  false = asserted a clause the lawyers did not label")
    if ok:
        secs = sorted(x["seconds"] for x in ok)
        print(f"\nLatency p50 {statistics.median(secs):.1f} s, p95 {secs[int(len(secs) * 0.95) - 1]:.1f} s.  "
              f"Tokens per question: mean {statistics.mean(x['tokens'] for x in ok):.0f}.  "
              f"Findings dropped by the citation check: {sum(x['dropped_findings'] for x in ok)}.  "
              f"Errors: {len(res) - len(ok)}")
    print("\nBy contract length (detection recall / missed):")
    for g in PER_GROUP:
        p = [x for x in res if x["group"] == g and x["present"] and outcome(x) in ("correct", "MISSED")]
        if p:
            print(f"  {g:10s} {sum(outcome(x) == 'correct' for x in p) / len(p):5.0%}  missed {sum(outcome(x) == 'MISSED' for x in p)}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    tag = f"-{args.tag}" if args.tag else ""
    out = REPO / "eval" / "results" / f"answers{tag}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tag": args.tag, "results": res, "seconds": round(time.time() - t0, 1)}, indent=2))
    print(f"\n{len(res)} questions in {time.time() - t0:.0f} s. Results: {out}")


if __name__ == "__main__":
    main()
