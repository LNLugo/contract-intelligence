"""Agent evaluation (ADR-0027): agent vs workflow, agent vs itself, and why each error happened.

Same contracts, CUAD labels, retrieval settings and model deployment for every arm; the only
difference between arms is who decides the steps (or, for A/A, nothing at all).

    --arms compare    workflow vs agent (default)
    --arms agent-aa   agent vs agent: the agent's own noise floor
    --contracts first10 | next10 | all20   (the 20-contract set of answer_eval.py, split in two)
    --contracts rest30                      the other 30 contracts of the evaluation set: the final test set

Part 1: for each (contract, category), the CUAD question scoped to the contract, as grp-legal.
Part 2: entitlement probes: grp-procurement asks about legal-only contracts (skip with --no-probes).
Error buckets (what kind of fix each error needs):
    retrieval   clause present, missed, and the labelled text was never retrieved -> better search
    reasoning   clause present, missed, although the labelled text WAS retrieved  -> model or prompt
    false       clause absent, answered as present                               -> a reviewer could catch
    other_text  answered correctly but quoted text other than the labelled text   -> read case by case
    abstain     no answer                                                         -> by reason

Usage (repo root, venv active, evaluation deployment):
    $env:CHAT_DEPLOYMENT = "gpt-5.4-mini-eval"
    python eval/agent_eval.py --cuad-root "$HOME/Documents/cuad" --arms agent-aa --no-probes
    python eval/agent_eval.py --cuad-root "$HOME/Documents/cuad" --contracts next10
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "ingestion"))

FULL = {"typical": 12, "long": 6, "very_long": 2}       # answer_eval.py's 20-contract set


def mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def pick(rows, which):
    if which == "rest30":                      # never used to develop anything: the final test set
        used = {r["file"] for r in pick(rows, "all20")}
        return [r for r in rows if r["file"] not in used]
    out = []
    for g, n in FULL.items():
        grp = [r for r in rows if r["group"] == g][:n]
        half = n // 2
        out += {"first10": grp[:half], "next10": grp[half:], "all20": grp}[which]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--arms", choices=["compare", "agent-aa"], default="compare")
    ap.add_argument("--contracts", choices=["first10", "next10", "all20", "rest30"], default="first10")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--rerank", choices=["true", "false"], default="false")
    ap.add_argument("--probes", type=int, default=10)
    ap.add_argument("--no-probes", action="store_true")
    args = ap.parse_args()
    os.environ["RERANK"] = args.rerank          # read at import by agents.answer

    from agents import agent as agent_mod
    from agents.answer import RERANK, TOP_N, answer
    from agents.retrieve import search
    from agents.taxonomy_snapshot import version as taxonomy_version
    from batch_ingest import access_for
    from pipeline.process import document_id
    from retrieval_eval import CATEGORIES, contains, key, load_labels

    labels = load_labels(args.cuad_root)
    rows = list(csv.DictReader((REPO / "eval" / "eval_set.csv").open(encoding="utf-8", newline="")))
    chosen = pick(rows, args.contracts)
    if args.limit:
        chosen = chosen[:args.limit]
    unmatched = [c for c in CATEGORIES if not any(c in labels.get(key(r["file"]), {}) for r in chosen)]
    from agents.taxonomy_snapshot import boundaries_text, classify
    q_by_cat = {c: next(v[c]["question"] for v in labels.values() if c in v) for c in CATEGORIES}
    wrong = {c: (classify(q).code if classify(q) else None) for c, q in q_by_cat.items()}
    print("Category recognised from each CUAD question (taxonomy check):")
    for c, code in wrong.items():
        ok = code == c.lower().replace("-", "_").replace(" ", "_")
        print(f"  {'ok ' if ok else 'BAD'} {c:28s} -> {code}  boundaries={bool(boundaries_text(q_by_cat[c]))}")
    tasks = []
    for r in chosen:
        lab = labels.get(key(r["file"]))
        if lab:
            doc = document_id((args.cuad_root / r["path"]).read_bytes())
            tasks += [(r, doc, c, lab[c]) for c in CATEGORIES if c in lab]
    arms = ["workflow", "agent"] if args.arms == "compare" else ["agent", "agent#2"]
    print(f"{len(chosen)} contracts ({args.contracts}), {len(tasks)} questions, arms {arms}, rerank={args.rerank}, "
          f"deployment {os.environ.get('CHAT_DEPLOYMENT', 'gpt-5.4-mini')}, taxonomy {taxonomy_version()}, "
          f"boundaries {os.environ.get('BOUNDARIES', 'true')}\n")

    def label_seen(texts, answers):
        return any(contains(a, t, window=6) or contains(t, a, window=6) for t in texts for a in answers)

    def score(present, status, quotes, answers, retrieved, reason):
        grounded = present and status == "ANSWERED" and any(
            contains(q, a, window=6) or contains(a, q, window=6) for q in quotes for a in answers)
        if status in ("ABSTAIN", "ERROR"):
            outcome = status
        elif present:
            outcome = "correct" if status == "ANSWERED" else "MISSED"
        else:
            outcome = "correct" if status == "NOT_FOUND" else "FALSE_CLAIM"
        bucket = None
        if outcome == "MISSED":
            bucket = "reasoning" if label_seen(retrieved, answers) else "retrieval"
        elif outcome == "FALSE_CLAIM":
            bucket = "false"
        elif outcome == "correct" and present and not grounded:
            bucket = "other_text"
        elif outcome == "ABSTAIN":
            bucket = "abstain"
        return {"outcome": outcome, "grounded": grounded, "bucket": bucket, "reason": reason}

    def run_arm(arm, question, doc, present, answers):
        if arm == "workflow":
            hits = search(question, ["grp-legal"], doc_id=doc, k=20, rerank=RERANK)
            a = answer(question, ["grp-legal"], doc, hits=hits)
            q = [c.quote for f in a.findings for c in f.citations if c.valid]
            return {"status": a.status, **score(present, a.status, q, answers, [h.content for h in hits[:TOP_N]], a.reason),
                    "tokens": a.tokens, "seconds": a.seconds}
        res = agent_mod.run(("grp-legal",), question, doc, include_retrieved=True)
        q = [c["quote"] for f in res["clause"]["findings"] for c in f["citations"] if c["valid"]]
        st = res["clause"]["status"]
        return {"status": st, **score(present, st, q, answers, res["retrieved"], res["clause"]["reason"]),
                **res["usage"], "tools": [f"{s['tool']}:{s['outcome']}" for s in res["trace"]]}

    def one(t):
        r, doc, cat, lab = t
        present = bool(lab["answers"])
        out = {"file": r["file"], "group": r["group"], "category": cat, "present": present}
        for arm in arms:
            try:
                out[arm] = run_arm(arm, lab["question"], doc, present, lab["answers"])
            except Exception as e:
                out[arm] = {"status": "ERROR", "outcome": "ERROR", "bucket": None, "error": str(e)[:200]}
        return out

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(one, tasks))

    errors = sum(x[a]["status"] == "ERROR" for x in res for a in arms)
    if errors > 0.05 * len(res) * len(arms):
        print(f"RUN INVALID: {errors} errored answers (more than 5%). No metrics reported.")
        for msg, n in Counter(x[a].get("error", "")[:120] for x in res for a in arms if x[a]["status"] == "ERROR").most_common(3):
            print(f"  {n:4d} x {msg}")
        sys.exit(2)

    print(f"{'':10s} {'found':>6s} {'missed':>6s} {'grounded':>8s} {'abs ok':>6s} {'false':>5s} {'abstain':>7s} {'errors':>6s}"
          f" {'tokens':>7s} {'p50 s':>6s} {'p95 s':>6s}")
    summary = {}
    for arm in arms:
        xs = [x[arm] | {"present": x["present"]} for x in res]
        p = [x for x in xs if x["present"] and x["outcome"] in ("correct", "MISSED")]
        a = [x for x in xs if not x["present"] and x["outcome"] in ("correct", "FALSE_CLAIM")]
        found = sum(x["outcome"] == "correct" for x in p)
        ok = [x for x in xs if x["status"] != "ERROR"]
        secs = sorted(x["seconds"] for x in ok) or [0]
        s = {"found": found / len(p) if p else float("nan"), "missed": sum(x["outcome"] == "MISSED" for x in p),
             "grounded": sum(x.get("grounded", False) for x in xs) / found if found else float("nan"),
             "absent_ok": sum(x["outcome"] == "correct" for x in a) / len(a) if a else float("nan"),
             "false_claims": sum(x["outcome"] == "FALSE_CLAIM" for x in a),
             "abstain": sum(x["outcome"] == "ABSTAIN" for x in xs), "errors": len(xs) - len(ok),
             "tokens_mean": statistics.mean(x["tokens"] for x in ok) if ok else 0,
             "p50_s": statistics.median(secs), "p95_s": secs[max(0, int(len(secs) * 0.95) - 1)],
             "buckets": dict(Counter(x["bucket"] for x in xs if x.get("bucket")))}
        summary[arm] = s
        print(f"{arm:10s} {s['found']:6.0%} {s['missed']:6d} {s['grounded']:8.0%} {s['absent_ok']:6.0%} {s['false_claims']:5d}"
              f" {s['abstain']:7d} {s['errors']:6d} {s['tokens_mean']:7.0f} {s['p50_s']:6.1f} {s['p95_s']:6.1f}")

    print("\nWhy each error happened (what kind of fix it needs):")
    print(f"  {'':10s} {'retrieval':>9s} {'reasoning':>9s} {'false':>6s} {'other_text':>10s} {'abstain':>7s}")
    for arm in arms:
        b = summary[arm]["buckets"]
        print(f"  {arm:10s} {b.get('retrieval', 0):9d} {b.get('reasoning', 0):9d} {b.get('false', 0):6d} "
              f"{b.get('other_text', 0):10d} {b.get('abstain', 0):7d}")
    print("  retrieval = labelled text never retrieved (better search);  reasoning = retrieved but missed (model/prompt)")
    print("  false = claimed an absent clause (a reviewer could catch);  other_text = right answer, different quote (read)")

    ag = [x[a] for x in res for a in arms if a.startswith("agent") and x[a]["status"] != "ERROR"]
    if ag:
        print(f"\nAgent behaviour: model turns mean {statistics.mean(x['model_turns'] for x in ag):.1f}, "
              f"searches mean {statistics.mean(x['searches'] for x in ag):.1f}, "
              f"refused tool calls {sum(x['refused_tool_calls'] for x in ag)}, "
              f"no answer within step limit {sum('steps' in (x.get('reason') or '') for x in ag)}, "
              f"vendor tool on clause questions {sum(any(t.startswith('vendor_for_contract') for t in x['tools']) for x in ag)}")

    a0, a1 = arms
    both = [x for x in res if "ERROR" not in (x[a0]["outcome"], x[a1]["outcome"])]
    only0 = sum(x[a0]["outcome"] == "correct" and x[a1]["outcome"] != "correct" for x in both)
    only1 = sum(x[a1]["outcome"] == "correct" and x[a0]["outcome"] != "correct" for x in both)
    flips = sum(x[a0]["outcome"] != x[a1]["outcome"] for x in both)
    label = "noise floor of the agent itself" if args.arms == "agent-aa" else "workflow A/A noise floor ~9%"
    print(f"\nPaired {a0} vs {a1}: outcomes differ on {flips}/{len(both)} ({flips / max(1, len(both)):.0%}; {label}). "
          f"Correct only in {a0} {only0}, only in {a1} {only1}, McNemar p = {mcnemar_p(only0, only1):.3f}")

    probes = None
    if not args.no_probes:
        legal_only = [document_id((args.cuad_root / r["path"]).read_bytes()) for r in rows
                      if access_for(r["type"])[1] == ["grp-legal"]][:args.probes]
        leaks, refused = [], 0
        for d in legal_only:
            for q in ("Summarize the limitation of liability clause.", "What are the vendor payment terms for this contract?"):
                r = agent_mod.run(("grp-procurement",), q, d)
                found = [c for f in r["clause"]["findings"] for c in f["citations"] if c["valid"]]
                if found or r["vendor"]["status"] == "OK":
                    leaks.append({"doc_id": d, "question": q, "findings": len(found), "vendor": r["vendor"]["status"]})
                refused += r["usage"]["refused_tool_calls"]
        probes = {"contracts": len(legal_only), "leaks": leaks, "refused": refused}
        print(f"\nEntitlement probes (grp-procurement, {len(legal_only)} legal-only contracts, 2 questions each): "
              f"leaks {len(leaks)}  refused tool calls {refused}  -> {'PASS' if not leaks else 'FAIL'}")

    out = REPO / "eval" / "results" / f"agent-{args.arms}-{args.contracts}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"arms": arms, "contracts": args.contracts, "rerank": args.rerank,
                               "deployment": os.environ.get("CHAT_DEPLOYMENT", "gpt-5.4-mini"), "taxonomy": taxonomy_version(),
                               "boundaries": os.environ.get("BOUNDARIES", "true"), "summary": summary,
                               "paired": {"differ": flips, "n": len(both), f"only_{a0}": only0, f"only_{a1}": only1,
                                          "p": mcnemar_p(only0, only1)},
                               "probes": probes, "results": res, "seconds": round(time.time() - t0, 1)}, indent=2))
    print(f"\n{time.time() - t0:.0f} s. Results: {out}")
    sys.exit(1 if probes and probes["leaks"] else 0)


if __name__ == "__main__":
    main()
