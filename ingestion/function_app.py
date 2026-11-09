"""Azure Function: queue-triggered ingestion (ADR-0017, ADR-0018).

Event Grid writes each BlobCreated event as plain JSON to the `ingest` queue.
This function reads the event, loads the PDF and its access metadata from the
data lake, and calls the same pipeline the batch script uses. No pipeline logic here.
"""
import json
import logging
from urllib.parse import unquote

import azure.functions as func

from pipeline import http
from pipeline.config import SETTINGS as S
from pipeline.events import decode_event
from pipeline.process import as_dict, process

app = func.FunctionApp()


class MissingAccessMetadata(ValueError):
    """Raised when an upload has no allowed_groups: fail closed, park in poison (ADR-0013)."""


def read_upload(blob_url: str) -> tuple[bytes, str, dict]:
    from azure.storage.filedatalake import DataLakeServiceClient
    lake = DataLakeServiceClient(S.dfs_endpoint, credential=http._credential)
    path = unquote(blob_url.split(f"/{S.raw_fs}/", 1)[1])
    f = lake.get_file_client(S.raw_fs, path)
    metadata = f.get_file_properties().metadata or {}
    groups = [g.strip() for g in metadata.get("allowed_groups", "").split(",") if g.strip()]
    if not groups:
        raise MissingAccessMetadata(f"{path} has no allowed_groups metadata; refusing to index")
    meta = {
        "contract_type": metadata.get("contract_type", "Unknown"),
        "business_unit": metadata.get("business_unit", "unassigned"),
        "allowed_groups": groups,
    }
    if metadata.get("vendor_id"):
        meta["vendor_id"] = metadata["vendor_id"]
    file_name = metadata.get("original_name") or path.rsplit("/", 1)[-1]
    return f.download_file().readall(), file_name, meta


@app.queue_trigger(arg_name="msg", queue_name="ingest", connection="IngestQueue")
def ingest(msg: func.QueueMessage) -> None:
    body = msg.get_body()
    logging.info("message received: %d bytes, starts with %r", len(body), body[:16])
    event = decode_event(body)
    url = event["data"]["url"]
    logging.info("ingest start: %s (dequeue count %s, event %s)", url, msg.dequeue_count, event.get("id"))
    pdf, file_name, meta = read_upload(url)
    result = process(pdf, file_name, meta, store_raw=False)
    logging.info("ingest done: %s", json.dumps(as_dict(result)))
