"""Ask the contract corpus a question from the command line (slice 1).

Usage (repo root, venv active):
    python -m agents.ask "What law governs this agreement?" --doc bdb7d1532a642920
    python -m agents.ask "Which contracts cap liability at fees paid?" --groups grp-procurement
"""
import argparse
import json

from .answer import answer, as_dict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--groups", default="grp-legal", help="comma-separated groups of the caller")
    ap.add_argument("--doc", default=None, help="restrict to one document id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    a = answer(args.question, [g.strip() for g in args.groups.split(",") if g.strip()], args.doc)
    if args.json:
        print(json.dumps(as_dict(a), indent=2))
        return
    top = f"{a.top_reranker_score:.2f}" if a.top_reranker_score is not None else "n/a"
    print(f"\n[{a.status}]  top reranker score {top}  |  {a.tokens} tokens  |  {a.seconds} s")
    if a.reason:
        print(f"Reason: {a.reason}")
    if a.answer:
        print(f"\n{a.answer}")
    for i, f in enumerate(a.findings, 1):
        print(f"\n{i}. {f.statement}")
        for c in f.citations:
            mark = "valid" if c.valid else "INVALID"
            print(f"   [{c.clause} {mark}] {c.file_name[:60]} p.{c.pages}: \"{c.quote[:160]}\"")
    if a.dropped_findings:
        print(f"\n({a.dropped_findings} finding(s) dropped: citations did not match the clause text)")


if __name__ == "__main__":
    main()
