"""Upload a contract to contracts-raw/inbox/ with its access metadata, then wait until
the event-driven path (Event Grid -> queue -> Function) has indexed it. Prints the
end-to-end latency from upload to searchable.

Usage (repo root, venv active):
    python ingestion/upload_to_inbox.py <pdf> --type "License" --groups grp-legal
    python ingestion/upload_to_inbox.py <pdf> --no-groups      # fail-closed test: should land in ingest-poison
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from azure.storage.filedatalake import DataLakeServiceClient  # noqa: E402

from pipeline import http  # noqa: E402
from pipeline.config import SETTINGS as S  # noqa: E402
from pipeline.index import existing_ids  # noqa: E402
from pipeline.process import document_id  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--type", default="Unknown")
    ap.add_argument("--groups", default="grp-legal")
    ap.add_argument("--no-groups", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    pdf = args.pdf.read_bytes()
    doc_id = document_id(pdf)
    if existing_ids(doc_id):
        sys.exit(f"{args.pdf.name} is already indexed as {doc_id}; pick a contract outside the evaluation set")

    metadata = {"original_name": args.pdf.name.encode("ascii", "ignore").decode()[:250],
                "contract_type": args.type, "business_unit": "legal"}
    if not args.no_groups:
        metadata["allowed_groups"] = args.groups

    lake = DataLakeServiceClient(S.dfs_endpoint, credential=http._credential)
    f = lake.get_file_client(S.raw_fs, f"inbox/{doc_id}.pdf")
    t0 = time.time()
    f.upload_data(pdf, overwrite=True, metadata=metadata)
    print(f"Uploaded {args.pdf.name} -> {S.raw_fs}/inbox/{doc_id}.pdf  (doc_id {doc_id})")
    if args.no_groups:
        print("No access metadata: expect the message in the ingest-poison queue after 5 attempts, and no chunks.")

    while time.time() - t0 < args.timeout:
        n = len(existing_ids(doc_id))
        if n:
            print(f"Indexed: {n} chunks, {time.time() - t0:.0f} s from upload to searchable")
            return
        time.sleep(10)
        print(f"  waiting... {time.time() - t0:.0f} s")
    print(f"Not indexed after {args.timeout} s. Check the function logs and the ingest-poison queue.")


if __name__ == "__main__":
    main()
