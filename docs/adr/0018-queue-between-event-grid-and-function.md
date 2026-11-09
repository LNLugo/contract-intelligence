# ADR-0018: A storage queue between Event Grid and the ingestion Function

- **Status:** Accepted
- **Date:** 2026-11-09
- **Phase:** 5c

## Context
The reference architecture shows Event Grid delivering `BlobCreated` directly to the ingestion Function. Event Grid waits 30 seconds for a response; after that it queues the event for retry. Delivery is at least once, so handlers can see duplicates.

## Evidence (2026-11-09)
Per-contract processing times from the evaluation-set run: **31 of 48 contracts took longer than 30 seconds** (times include some rate-limit waits from that run, so they overstate the steady state; the long-contract pattern holds regardless). The first test contract (37 pages) took 18.5 s with no throttling, and the set includes 5 contracts over 100 pages.

**Consequence of a direct subscription:** a contract that takes more than 30 s is redelivered while the first invocation is still running. The extraction result is not yet cached, so the second invocation pays Document Intelligence again for the same document. Content-hash chunk IDs stop duplicate chunks, not duplicate spend.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Event Grid → Function directly (as drawn) | Simplest; matches the diagram | Redelivery of most real contracts; double extraction spend; overlapping runs on one document |
| Event Grid → Function that acknowledges, then processes in the background | Fast acknowledgement | Work in flight is lost if the instance recycles; no built-in retry or poison handling |
| **Event Grid → Storage Queue → queue-triggered Function** | Event Grid's delivery completes when the message is queued; the message stays invisible while a worker processes it; after 5 failed attempts it moves to `ingest-poison` (built-in dead letter); load is smoothed | One more hop; a queue, its identities and roles to configure |

## Decision
Event Grid system topic on the data lake → subscription filtered to `BlobCreated`, `.pdf`, prefix `contracts-raw/inbox/`, and blob write APIs only (`PutBlob`, `PutBlockList`, `FlushWithClose`) → storage queue `ingest` → Flex Consumption Function (queue trigger) → `pipeline.process` (ADR-0017).

Failure handling in two layers:
- Event Grid cannot reach the queue → retries, then dead-letters to `contracts-raw`'s sibling container `deadletter`.
- The Function fails on a message → the queue retries up to 5 times, then moves it to `ingest-poison`.

Identity everywhere: Event Grid delivers and dead-letters with its system-assigned identity; the Function uses its managed identity for the queue, the lake, Document Intelligence, the model and search. No connection strings.

## Consequences
- Batch uploads under `contracts-raw/eval/` never trigger the Function (prefix filter).
- A document uploaded without its access metadata (`allowed_groups`) is refused, not indexed with empty groups: it lands in `ingest-poison` for a person to fix. Fail closed (ADR-0013).
- The queue trigger must read Event Grid's plain-JSON messages (`messageEncoding: none` in `host.json`); the Functions default expects base64.
- The Function's storage account is separate from the data lake: application plumbing (deployment package, queue, host state) is kept apart from business data.

## Enterprise vs this build
The diagram's direct arrow is fine when handlers finish in seconds. Contracts do not. At higher volume the same queue gives backpressure, and a Service Bus queue would add sessions, scheduled retries and duplicate detection if needed.

## Interview angle
"Event Grid waits 30 seconds for a response. I measured my contracts and most took longer, so a direct subscription would have redelivered them mid-run and paid for extraction twice. I put a storage queue between Event Grid and the Function: Event Grid's job ends at the queue, the message stays invisible while it's processed, and after five failures it parks in a poison queue. Documents without access metadata go to poison too, because indexing them with no groups would fail open."
