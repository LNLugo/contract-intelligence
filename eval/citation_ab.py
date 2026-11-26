"""Old vs new citation check on the SAME model answers (ADR-0029). Paired: no run-to-run noise.

For each (contract, category) question: retrieve once, generate once, then judge every citation
with both rules and route the answer twice. Any difference in outcome is caused by the checker
alone, never by the model.

    old  ADR-0020: lower-case, punctuation stripped, exact or 90% of words in order
    new  ADR-0029: NFKC + whitespace, at least 40 characters, exact or fuzzy >= 95 with the
         negations, modal verbs and numbers identical

Usage (repo root, venv active, evaluation deployment; about 100 questions for first10):
    $env:CHAT_DEPLOYMENT = "gpt-5.4-mini-eval"
    python eval/citation_ab.py --cuad-root "$HOME/Documents/cuad" --contracts first10

Writes eval/results/citation-ab-<set>-<time>.json, including every citation the two rules
disagree on (CUAD is public data), so each disagreement can be read.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "ingestion"))


def old_quote_in_clause(quote: str, clause: str) -> bool:
    """ADR-0020 rule, frozen exactly as it ran until commit dcdfb88."""
    def n(t):
        t = t.lower().replace("’", "'").replace("“", '"').replace("”", '"')
        return re.sub(r"[^a-z0-9]+", " ", t).strip()
    q, c = n(quote), n(clause)
    if len(q.split()) < 4:
        return False
    if q in c:
        return True
    words, pos, matched = q.split(), 0, 0
    c_words = c.split()
    for w in words:
        try:
            pos = c_words.index(w, pos) + 1
            matched += 1
        except ValueError:
            continue
    return matched / len(words) >= 0.9


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--contracts", choices=["first10", "next10", "all20"], default="first10")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    os.environ["RERANK"] = "false"              # same setting as the agent evaluations

    from agents.answer import TOP_N, generate, route
    from agents.citations import check_quote
    from agents.retrieve import search
    from agent_eval import pick
    from pipeline.process import document_id
    from retrieval_eval import CATEGORIES, key, load_labels

    labels = load_labels(args.cuad_root)
    rows = list(csv.DictReader((REPO / "eval" / "eval_set.csv").open(encoding="utf-8", newline="")))
    tasks = []
    for r in pick(rows, args.contracts):
        lab = labels.get(key(r["file"]))
        if lab:
            doc = document_id((args.cuad_root / r["path"]).read_bytes())
            tasks += [(r, doc, c, lab[c]) for c in CATEGORIES if c in lab]
    if args.limit:
        tasks = tasks[:args.limit]
    print(f"{len(tasks)} questions ({args.contracts}), deployment {os.environ.get('CHAT_DEPLOYMENT', 'gpt-5.4-mini')}\n")

    def outcome(present, status):
        if status in ("ABSTAIN", "ERROR"):
            return status
        if present:
            return "correct" if status == "ANSWERED" else "MISSED"
        return "correct" if status == "NOT_FOUND" else "FALSE_CLAIM"

    def one(t):
        r, doc, cat, lab = t
        present = bool(lab["answers"])
        try:
            hits = search(lab["question"], ["grp-legal"], doc_id=doc, k=20, rerank=False)[:TOP_N]
            if not hits:
                return {"file": r["file"], "category": cat, "present": present, "old": "ABSTAIN", "new": "ABSTAIN",
                        "citations": [], "disagree": []}
            raw, tokens = generate(lab["question"], hits)
        except Exception as e:
            return {"file": r["file"], "category": cat, "present": present, "old": "ERROR", "new": "ERROR",
                    "error": str(e)[:200], "citations": [], "disagree": []}
        det = str(raw.get("determination", "unclear")).lower()
        kept = {"old": [], "new": []}
        dropped = {"old": 0, "new": 0}
        cites, disagree = [], []
        for f in raw.get("findings", []) or []:
            ok = {"old": False, "new": False}
            for c in f.get("citations", []) or []:
                cid = str(c.get("clause", "")).upper().strip().lstrip("C")
                hit = hits[int(cid) - 1] if cid.isdigit() and 1 <= int(cid) <= len(hits) else None
                quote = str(c.get("quote", ""))
                o = bool(hit) and old_quote_in_clause(quote, hit.content)
                n = check_quote(quote, hit.content if hit else None)
                ok["old"] |= o
                ok["new"] |= n.valid
                cites.append({"old": o, "new": n.valid, "kind": n.match or n.reason})
                if o != n.valid:
                    disagree.append({"old": o, "new": n.valid, "kind": n.match or n.reason, "score": round(n.score, 1),
                                     "quote": quote, "clause": hit.content if hit else None})
            for rule in ("old", "new"):
                if ok[rule]:
                    kept[rule].append(f)
                else:
                    dropped[rule] += 1
        st = {rule: route(det, kept[rule], dropped[rule])[0] for rule in ("old", "new")}
        return {"file": r["file"], "category": cat, "present": present, "determination": det, "tokens": tokens,
                "old": outcome(present, st["old"]), "new": outcome(present, st["new"]),
                "citations": cites, "disagree": disagree}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(one, tasks))

    cites = [c for x in res for c in x["citations"]]
    print(f"Citations judged: {len(cites)}   old passed {sum(c['old'] for c in cites)}   new passed {sum(c['new'] for c in cites)}")
    print("New rule, by kind:", dict(Counter(c["kind"] for c in cites).most_common()))
    print("\nOutcomes (same answers, two checkers):")
    for o in ("correct", "MISSED", "FALSE_CLAIM", "ABSTAIN", "ERROR"):
        print(f"  {o:12s} old {sum(x['old'] == o for x in res):4d}   new {sum(x['new'] == o for x in res):4d}")
    changed = [x for x in res if x["old"] != x["new"]]
    print(f"\nQuestions whose outcome changed: {len(changed)}")
    for x in changed:
        print(f"  {x['category']:28s} {x['old']:>12s} -> {x['new']:<12s} {x['file'][:50]}")
    dis = [d for x in res for d in x["disagree"]]
    print(f"\nCitations the rules disagree on: {len(dis)}   (old passed, new failed: {sum(d['old'] for d in dis)};"
          f" new passed, old failed: {sum(d['new'] for d in dis)})")
    for d in dis[:15]:
        print(f"  old={'pass' if d['old'] else 'fail'} new={'pass' if d['new'] else 'fail'} [{d['kind']} {d['score']}] \"{d['quote'][:110]}\"")

    out = REPO / "eval" / "results" / f"citation-ab-{args.contracts}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"contracts": args.contracts, "deployment": os.environ.get("CHAT_DEPLOYMENT", "gpt-5.4-mini"),
                               "seconds": round(time.time() - t0), "results": res}, indent=1), encoding="utf-8")
    print(f"\nSaved {out.relative_to(REPO)}  ({round(time.time() - t0)} s, {sum(x.get('tokens', 0) for x in res)} tokens)")


if __name__ == "__main__":
    main()
