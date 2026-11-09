import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.events import decode_event  # noqa: E402

EVENT = {"id": "1", "eventType": "Microsoft.Storage.BlobCreated",
         "data": {"api": "FlushWithClose",
                  "url": "https://stcidev2416.blob.core.windows.net/contracts-raw/inbox/abc.pdf"}}


def test_plain_json():
    assert decode_event(json.dumps(EVENT).encode())["data"]["url"].endswith("abc.pdf")


def test_base64_json():
    body = base64.b64encode(json.dumps(EVENT).encode())
    assert decode_event(body)["id"] == "1"


def test_array_of_one_event():
    assert decode_event(json.dumps([EVENT]))["id"] == "1"


def test_garbage_is_rejected_with_a_readable_error():
    with pytest.raises(ValueError, match="neither JSON nor Base64"):
        decode_event(b"not an event at all!!")


def test_non_blob_event_is_rejected():
    with pytest.raises(ValueError, match="Not a BlobCreated event"):
        decode_event(json.dumps({"id": "x", "data": {}}))
