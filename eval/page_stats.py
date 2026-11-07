"""Measure CUAD page counts to decide the Document Intelligence tier (ADR-0015).

Usage:
    pip install --user pypdf
    python3 eval/page_stats.py <path-to-CUAD_v1-folder> [price_per_1000_pages]

Prints the page distribution, how much of the corpus the free tier (first 2 pages
only) would actually read, and what full extraction would cost at the given price.
"""
import sys
import statistics
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    price = float(sys.argv[2]) if len(sys.argv) > 2 else None

    pdfs = sorted(root.rglob("*.pdf")) + sorted(root.rglob("*.PDF"))
    if not pdfs:
        sys.exit(f"No PDFs found under {root}")

    counts, failed = [], []
    for p in pdfs:
        try:
            counts.append((p.name, len(PdfReader(p).pages)))
        except Exception as exc:  # corrupt or encrypted PDFs are a finding, not a crash
            failed.append((p.name, type(exc).__name__))

    pages = [c for _, c in counts]
    total = sum(pages)
    pages_sorted = sorted(pages)

    def pct(q: float) -> int:
        return pages_sorted[min(len(pages_sorted) - 1, int(q * len(pages_sorted)))]

    free_read = sum(min(c, 2) for c in pages)
    short = [n for n, c in counts if c <= 2]

    print(f"Contracts read:          {len(pages)}   (failed to open: {len(failed)})")
    print(f"Total pages:             {total}")
    print(f"Pages per contract:      min {min(pages)}, median {statistics.median(pages):.0f}, "
          f"p90 {pct(0.90)}, p99 {pct(0.99)}, max {max(pages)}")
    print(f"Contracts of 2 pages or fewer: {len(short)} ({len(short) / len(pages):.0%})")
    print(f"Free tier would read:    {free_read} of {total} pages ({free_read / total:.0%})")
    if price is not None:
        print(f"Full extraction cost:    ${total / 1000 * price:,.2f} at ${price}/1,000 pages")
        sample = sorted(counts, key=lambda x: x[1])[len(counts) // 2 - 25: len(counts) // 2 + 25]
        sample_pages = sum(c for _, c in sample)
        print(f"50 median-length contracts: {sample_pages} pages, ${sample_pages / 1000 * price:,.2f}")
    print("\nLongest 5:")
    for name, c in sorted(counts, key=lambda x: -x[1])[:5]:
        print(f"  {c:4d}  {name}")
    if failed:
        print("\nCould not open:")
        for name, err in failed:
            print(f"  {err}: {name}")


if __name__ == "__main__":
    main()
