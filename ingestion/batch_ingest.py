"""Ingest the fixed evaluation set (eval/eval_set.csv) through the pipeline library.

Usage (from the repo root):
    python ingestion/batch_ingest.py --cuad-root <folder containing CUAD_v1> --limit 1
    python ingestion/batch_ingest.py --cuad-root <folder containing CUAD_v1>

Start with --limit 1: one contract, a few cents, proves the whole path end to end.
Re-running is safe: extraction is cached in ADLS and chunks are replaced per document.
"""
import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline.process import as_dict, process  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PRICE_PER_1000_PAGES = 10.0

# Synthetic access model for the security-trimming tests (ADR-0013): every contract is
# visible to legal; supply-chain contract types are also visible to procurement.
PROCUREMENT_TYPES = {"Supply", "Distributor", "Manufacturing", "Outsourcing",
                     "Maintenance", "Transportation", "Service"}


def access_for(contract_type: str) -> tuple[str, list[str]]:
    if contract_type in PROCUREMENT_TYPES:
        return "procurement", ["grp-legal", "grp-procurement"]
    return "legal", ["grp-legal"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuad-root", required=True, type=Path)
    ap.add_argument("--eval-set", default=REPO / "eval" / "eval_set.csv", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--skip-indexed", action="store_true",
                    help="skip contracts that already have chunks in the index (no re-embedding)")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.eval_set.open()))
    if args.limit:
        rows = rows[:args.limit]
    if args.skip_indexed:
        from pipeline.index import existing_ids
        from pipeline.process import document_id
        before = len(rows)
        rows = [r for r in rows
                if not existing_ids(document_id((args.cuad_root / r["path"]).read_bytes()))]
        print(f"Skipping {before - len(rows)} contracts already in the index")
    print(f"Ingesting {len(rows)} contracts with {args.workers} workers\n")

    def run(row):
        pdf = (args.cuad_root / row["path"]).read_bytes()
        unit, groups = access_for(row["type"])
        return row, process(pdf, row["file"], {"contract_type": row["type"],
                                               "business_unit": unit, "allowed_groups": groups})

    results, failures, t0 = [], [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, r): r for r in rows}
        for f in as_completed(futures):
            row = futures[f]
            try:
                _, r = f.result()
                results.append(as_dict(r))
                tag = "cached" if r.extraction_cached else "extracted"
                print(f"  OK   {r.pages:4d} p  {r.chunks:4d} chunks  {r.seconds:6.1f} s  {tag:9s}  {r.file_name[:60]}")
            except Exception as exc:
                failures.append({"file": row["file"], "error": str(exc)[:500]})
                print(f"  FAIL {row['file'][:60]}: {str(exc)[:200]}")

    paid_pages = sum(r["pages"] for r in results if not r["extraction_cached"])
    summary = {
        "contracts_ok": len(results), "contracts_failed": len(failures),
        "pages_total": sum(r["pages"] for r in results), "pages_extracted_now": paid_pages,
        "extraction_cost_usd": round(paid_pages / 1000 * PRICE_PER_1000_PAGES, 2),
        "chunks_total": sum(r["chunks"] for r in results),
        "embed_tokens_total": sum(r["embed_tokens"] for r in results),
        "max_chunk_tokens": max((r["max_chunk_tokens"] for r in results), default=0),
        "wall_seconds": round(time.time() - t0, 1),
    }
    print("\n" + "\n".join(f"{k:22s} {v}" for k, v in summary.items()))

    out_dir = REPO / "eval" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ingest-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"summary": summary, "results": results, "failures": failures}, indent=2))
    print(f"\nRun log: {out}")


if __name__ == "__main__":
    main()
