"""Select the fixed, stratified 50-contract evaluation set (ADR-0015, ADR-0012).

Usage:
    python3 eval/select_eval_set.py <path-to-CUAD_v1-folder> [price_per_1000_pages]

Writes eval/eval_set.csv. Deterministic: the same corpus always yields the same set,
so every experiment runs on identical documents. Contract type comes from the CUAD
folder the PDF sits in; within each length group, contracts are taken round-robin
across types so no single type dominates.
"""
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

GROUPS = [  # name, min pages, max pages, how many
    ("typical", 8, 15, 30),
    ("long", 30, 60, 15),
    ("very_long", 101, 10_000, 5),
]
SEED = 20261107
OUT = Path(__file__).resolve().parent / "eval_set.csv"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    price = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

    rows = []
    # Sort on the relative POSIX path so Windows and Linux pick the identical set
    found = set(root.rglob("*.pdf")) | set(root.rglob("*.PDF"))
    for p in sorted(found, key=lambda x: x.relative_to(root).as_posix()):
        try:
            rows.append({"file": p.name, "path": p.relative_to(root).as_posix(),
                         "type": p.parent.name, "pages": len(PdfReader(p).pages)})
        except Exception:
            continue

    rng = random.Random(SEED)
    selected = []
    for name, lo, hi, n in GROUPS:
        by_type = defaultdict(list)
        for r in rows:
            if lo <= r["pages"] <= hi:
                by_type[r["type"]].append(r)
        for items in by_type.values():
            rng.shuffle(items)
        types = sorted(by_type)
        rng.shuffle(types)
        picked = []
        while len(picked) < n and any(by_type[t] for t in types):
            for t in types:
                if by_type[t] and len(picked) < n:
                    picked.append(by_type[t].pop())
        for r in picked:
            r["group"] = name
        selected += picked
        print(f"{name:10s} wanted {n:2d}, got {len(picked):2d}, "
              f"pages {sum(r['pages'] for r in picked):5d}, types {len({r['type'] for r in picked})}")

    total = sum(r["pages"] for r in selected)
    print(f"\nTotal: {len(selected)} contracts, {total} pages, ${total / 1000 * price:,.2f} at ${price}/1,000 pages")
    print(f"Contract types covered: {len({r['type'] for r in selected})}")

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["group", "type", "pages", "file", "path"])
        w.writeheader()
        for r in sorted(selected, key=lambda r: (r["group"], r["type"], r["file"])):
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
