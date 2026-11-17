"""Read the judgment errors side by side (ADR-0027): what the lawyers labelled vs what the model decided.

Takes a results file from eval/agent_eval.py, re-asks only the questions that went wrong for the
chosen buckets, and prints the label text, the model's determination, answer and validated quotes.
Re-asking is needed because results files hold outcomes, not text (and runs vary ~11%), so each
case also says whether the error reproduced.

    python eval/review_errors.py --cuad-root "$HOME/Documents/cuad" --results eval\\results\\agent-agent-aa-first10-....json
    python eval/review_errors.py ... --buckets reasoning false --arm agent --out eval/results/errors-review.md

For each case decide: model wrong (a boundary to write down), label wrong or debatable (leave the
model alone), or unclear. Boundaries ("includes" / "excludes") are written from the PATTERN, then
checked on CUAD contracts outside the evaluation set, never fitted to these cases.
"""
import argparse
import csv
import json
import os
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "ingestion"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--arm", default="agent")
    ap.add_argument("--buckets", nargs="+", default=["reasoning", "false"])
    ap.add_argument("--out", type=Path, default=None, help="also write the review as markdown")
    args = ap.parse_args()
    data = json.loads(args.results.read_text(encoding="utf-8"))
    os.environ["RERANK"] = data.get("rerank", "false")

    from agents import agent as agent_mod
    from agents.answer import answer
    from pipeline.process import document_id
    from retrieval_eval import key, load_labels

    labels = load_labels(args.cuad_root)
    paths = {r["file"]: r["path"] for r in csv.DictReader((REPO / "eval" / "eval_set.csv").open(encoding="utf-8", newline=""))}
    cases = [x for x in data["results"] if x.get(args.arm, {}).get("bucket") in args.buckets]
    print(f"{len(cases)} cases in buckets {args.buckets} for arm {args.arm}\n")
    lines = [f"# Error review: {args.results.name}, arm {args.arm}, buckets {', '.join(args.buckets)}\n"]

    for i, x in enumerate(cases, 1):
        lab = labels[key(x["file"])][x["category"]]
        doc = document_id((args.cuad_root / paths[x["file"]]).read_bytes())
        if args.arm.startswith("agent"):
            r = agent_mod.run(("grp-legal",), lab["question"], doc)
            status, det, ans, reason = r["clause"]["status"], r["clause"]["determination"], r["clause"]["answer"], r["clause"]["reason"]
            quotes = [c["quote"] for f in r["clause"]["findings"] for c in f["citations"] if c["valid"]]
        else:
            a = answer(lab["question"], ["grp-legal"], doc)
            status, det, ans, reason = a.status, a.determination, a.answer, a.reason
            quotes = [c.quote for f in a.findings for c in f.citations if c.valid]
        expected = "ANSWERED" if x["present"] else "NOT_FOUND"
        block = [
            f"## {i}. {x['category']}: {x[args.arm]['bucket']}  ({x['file'][:60]})",
            f"- Lawyers labelled: **{'present' if x['present'] else 'absent'}**",
            *[f"  > {textwrap.shorten(t, 400)}" for t in lab["answers"][:3]],
            f"- Model now: **{status}** (determination {det or '-'}); error {'reproduced' if status != expected else 'did NOT reproduce'}",
            f"- Model answer: {textwrap.shorten(ans or reason or '-', 400)}",
            *[f"  > quoted: {textwrap.shorten(q, 300)}" for q in quotes[:3]],
            "- Verdict (fill in): model wrong / label wrong or debatable / unclear. Boundary it suggests:",
            "",
        ]
        print("\n".join(block))
        lines += block
    if args.out:
        args.out.write_text("\n".join(lines), encoding="utf-8")
        print(f"Written: {args.out}")


if __name__ == "__main__":
    main()
