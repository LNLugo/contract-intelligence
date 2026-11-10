"""Compare two answer-evaluation runs question by question (same 200 questions, same cached retrieval).

Totals hide movement in both directions; this pairs each question across runs and reports:
  * how many questions changed outcome at all (flip rate)
  * detection on present clauses: gained vs lost, with an exact McNemar test
  * absent clauses: false claims fixed vs introduced, with an exact McNemar test
  * the questions that flipped, so they can be read

Usage (repo root, venv active):
    python eval/compare_runs.py eval/results/<run A>.json eval/results/<run B>.json
"""
import json
import sys
from math import comb
from pathlib import Path


def outcome(x: dict) -> str:
    if x["status"] in ("ABSTAIN", "ERROR"):
        return x["status"]
    if x["present"]:
        return "correct" if x["status"] == "ANSWERED" else "MISSED"
    return "correct" if x["status"] == "NOT_FOUND" else "FALSE_CLAIM"


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value: b and c are the discordant pair counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def load(path: str) -> tuple[str, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    name = data.get("tag") or Path(path).stem
    return name, {f"{x['file']}|{x['category']}": x for x in data["results"]}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a_name, a = load(sys.argv[1])
    b_name, b = load(sys.argv[2])
    keys = sorted(set(a) & set(b))
    print(f"A = {a_name}   B = {b_name}   paired questions: {len(keys)}\n")

    flips = [k for k in keys if outcome(a[k]) != outcome(b[k])]
    print(f"Questions whose outcome changed: {len(flips)} of {len(keys)} ({len(flips) / len(keys):.0%})")

    def judged(x):
        return outcome(x) in ("correct", "MISSED", "FALSE_CLAIM")

    pres = [k for k in keys if a[k]["present"] and judged(a[k]) and judged(b[k])]
    gained = sum(outcome(a[k]) == "MISSED" and outcome(b[k]) == "correct" for k in pres)
    lost = sum(outcome(a[k]) == "correct" and outcome(b[k]) == "MISSED" for k in pres)
    absn = [k for k in keys if not a[k]["present"] and judged(a[k]) and judged(b[k])]
    fixed = sum(outcome(a[k]) == "FALSE_CLAIM" and outcome(b[k]) == "correct" for k in absn)
    broke = sum(outcome(a[k]) == "correct" and outcome(b[k]) == "FALSE_CLAIM" for k in absn)

    def verdict(p):
        return "real difference (p < 0.05)" if p < 0.05 else "within noise"

    p1, p2 = mcnemar_p(gained, lost), mcnemar_p(fixed, broke)
    print(f"\nPresent clauses ({len(pres)} judged in both runs):")
    print(f"  detections gained in B: {gained}   lost in B: {lost}   McNemar p = {p1:.3f}  -> {verdict(p1)}")
    print(f"Absent clauses ({len(absn)} judged in both runs):")
    print(f"  false claims fixed in B: {fixed}   introduced in B: {broke}   McNemar p = {p2:.3f}  -> {verdict(p2)}")
    abst = sum(outcome(a[k]) != "ABSTAIN" and outcome(b[k]) == "ABSTAIN" for k in keys)
    unab = sum(outcome(a[k]) == "ABSTAIN" and outcome(b[k]) != "ABSTAIN" for k in keys)
    print(f"Abstentions: {abst} new in B, {unab} resolved in B")

    if flips:
        print("\nFlipped questions (A -> B):")
        for k in flips:
            file, cat = k.split("|")
            print(f"  {cat:28s} {outcome(a[k]):12s} -> {outcome(b[k]):12s} {file[:45]}")


if __name__ == "__main__":
    main()
