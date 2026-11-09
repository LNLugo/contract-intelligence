"""Measure retrieval against CUAD's lawyer labels before any generation (ADR-0012, ADR-0019).

For each evaluation contract and each clause category below, ask the category's CUAD
question scoped to that contract, and record the rank of the first chunk that contains
the labelled clause text:
  * hybrid ranking (BM25 + vector, RRF), no reranker
  * the same candidates reranked by the semantic ranker
Also records the top reranker score for categories that are present and absent in the
contract: the data needed to calibrate the abstention threshold (ADR-0009).

Usage (repo root, venv active):
    python eval/retrieval_eval.py --cuad-root "$HOME/Documents/cuad"
    python eval/retrieval_eval.py --cuad-root ... --limit 5         # quick check first

Cost: one embedding and two searches per (contract, category); the semantic ranker's free
plan allows 1,000 queries per month, and a full run uses about 500.
"""
import argparse
import csv
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from agents.retrieve import query_vector, search  # noqa: E402
from pipeline.process import document_id  # noqa: E402

CATEGORIES = [
    "Governing Law", "Termination For Convenience", "Cap On Liability", "Anti-Assignment",
    "Exclusivity", "Non-Compete", "Audit Rights", "Insurance", "Renewal Term", "License Grant",
]


def norm(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def contains(chunk: str, answer: str, window: int = 8) -> bool:
    """True if the chunk holds the labelled clause: the whole answer if short, otherwise any
    8-word run of it (tolerates PDF extraction differences and clauses split across chunks)."""
    a, c = norm(answer), " " + " ".join(norm(chunk)) + " "
    if not a:
        return False
    if len(a) <= window:
        return f" {' '.join(a)} " in c
    return any(f" {' '.join(a[i:i + window])} " in c for i in range(0, len(a) - window + 1))


def load_labels(cuad_root: Path) -> dict:
    """{normalized contract title: {category: {"question": str, "answers": [str]}}}"""
    path = next(cuad_root.rglob("CUAD_v1.json"))
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    labels = {}
    for doc in data:
        cats = {}
        for para in doc["paragraphs"]:
            for qa in para["qas"]:
                cat = qa["id"].split("__")[-1]
                details = qa["question"].split("Details:")[-1].strip()
                cats[cat] = {"question": details, "answers": [a["text"] for a in qa["answers"]]}
        labels[key(doc["title"])] = cats
    return labels


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\.pdf$", "", name, flags=re.I).lower())


def first_rank(hits, answers) -> int | None:
    for rank, h in enumerate(hits, 1):
        if any(contains(h.content, a) for a in answers):
            return rank
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    labels = load_labels(args.cuad_root)
    rows = list(csv.DictReader((REPO / "eval" / "eval_set.csv").open()))
    if args.limit:
        rows = rows[:args.limit]

    tasks, unmatched = [], []
    for r in rows:
        lab = labels.get(key(r["file"]))
        if lab is None:
            unmatched.append(r["file"])
            continue
        doc = document_id((args.cuad_root / r["path"]).read_bytes())
        for cat in CATEGORIES:
            if cat in lab:
                tasks.append((r, doc, cat, lab[cat]))
    print(f"{len(rows)} contracts, {len(tasks)} (contract, category) queries, {len(unmatched)} without labels")

    def run(t):
        r, doc, cat, lab = t
        vec = query_vector(lab["question"])
        hybrid = search(lab["question"], ["grp-legal"], doc_id=doc, k=20, rerank=False, vector=vec)
        reranked = search(lab["question"], ["grp-legal"], doc_id=doc, k=20, rerank=True, vector=vec)
        present = bool(lab["answers"])
        return {
            "file": r["file"], "group": r["group"], "category": cat, "present": present,
            "doc_chunks_seen": len(hybrid),
            "hybrid_rank": first_rank(hybrid, lab["answers"]) if present else None,
            "rerank_rank": first_rank(reranked, lab["answers"]) if present else None,
            "top_reranker_score": reranked[0].reranker_score if reranked else None,
        }

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, tasks))

    def recall(rs, field, k):
        rs = [x for x in rs if x["present"]]
        return sum(1 for x in rs if x[field] and x[field] <= k) / len(rs) if rs else float("nan")

    def mrr(rs, field):
        rs = [x for x in rs if x["present"]]
        return statistics.mean(1 / x[field] if x[field] else 0 for x in rs) if rs else float("nan")

    print(f"\n{'category':28s} {'n':>3s}  {'hyb@1':>6s} {'hyb@5':>6s} {'hyb@20':>6s}  {'rr@1':>6s} {'rr@5':>6s}  {'MRR hyb':>7s} {'MRR rr':>7s}")
    for cat in CATEGORIES + ["ALL"]:
        rs = results if cat == "ALL" else [x for x in results if x["category"] == cat]
        n = sum(1 for x in rs if x["present"])
        if not n:
            continue
        print(f"{cat:28s} {n:3d}  {recall(rs,'hybrid_rank',1):6.0%} {recall(rs,'hybrid_rank',5):6.0%} "
              f"{recall(rs,'hybrid_rank',20):6.0%}  {recall(rs,'rerank_rank',1):6.0%} {recall(rs,'rerank_rank',5):6.0%}  "
              f"{mrr(rs,'hybrid_rank'):7.2f} {mrr(rs,'rerank_rank'):7.2f}")

    print("\nRecall@5 by contract length (what the model actually sees):")
    for g in ("typical", "long", "very_long"):
        rs = [x for x in results if x["group"] == g]
        if rs:
            print(f"  {g:10s} hybrid {recall(rs,'hybrid_rank',5):5.0%}   reranked {recall(rs,'rerank_rank',5):5.0%}   "
                  f"(avg chunks per contract {statistics.mean(x['doc_chunks_seen'] for x in rs):.0f}, capped at 20)")

    pres = [x["top_reranker_score"] for x in results if x["present"] and x["top_reranker_score"] is not None]
    absn = [x["top_reranker_score"] for x in results if not x["present"] and x["top_reranker_score"] is not None]
    if pres and absn:
        print("\nTop reranker score (abstention calibration, ADR-0009):")
        print(f"  clause present: median {statistics.median(pres):.2f}, p10 {sorted(pres)[len(pres)//10]:.2f}  (n={len(pres)})")
        print(f"  clause absent:  median {statistics.median(absn):.2f}, p90 {sorted(absn)[int(len(absn)*0.9)]:.2f}  (n={len(absn)})")

    out = REPO / "eval" / "results" / f"retrieval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"categories": CATEGORIES, "seconds": round(time.time() - t0, 1),
                               "unmatched": unmatched, "results": results}, indent=2))
    print(f"\n{len(results)} queries in {time.time() - t0:.0f} s. Results: {out}")


if __name__ == "__main__":
    main()
