"""Decode an Event Grid event delivered through a storage queue.

Observed 2026-11-09: the queue message body was not plain JSON (json.loads failed at
char 0), consistent with Event Grid writing the event Base64-encoded. Accept both forms
so the Function does not depend on one encoding setting."""
import base64
import binascii
import json


def decode_event(body: bytes | str) -> dict:
    text = body.decode("utf-8-sig") if isinstance(body, bytes) else body
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        event = json.loads(text)
    else:
        try:
            event = json.loads(base64.b64decode(text, validate=True).decode("utf-8-sig"))
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"Queue message is neither JSON nor Base64 JSON; starts with {text[:40]!r}") from exc
    if isinstance(event, list):          # Event Grid can deliver a one-element array
        event = event[0]
    if "data" not in event or "url" not in event["data"]:
        raise ValueError(f"Not a BlobCreated event: keys {sorted(event)}")
    return event
