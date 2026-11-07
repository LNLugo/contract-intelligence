# ADR-0004: Event-driven push ingestion instead of an AI Search indexer

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 5

## Context
Uploaded PDFs need to be extracted, chunked, tagged with access metadata (business unit, vendor, contract type), embedded and indexed. AI Search can pull from blob storage with an indexer and integrated vectorization, or my own code can push documents through the index API.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| AI Search indexer + skillset (pull) | Little code; built-in change tracking and retries | Less control over chunk boundaries and per-chunk security tags; skillset debugging is opaque; extraction output not easily reused |
| Event Grid → Function → push to index API | Full control of chunking, tags and IDs; extraction JSON saved so re-chunking skips re-extraction | I own retries, idempotency, dead lettering and delete handling |
| Blob-polling trigger | Simple | Latency and scale limits; Flex Consumption uses Event Grid for blob triggers anyway |

## Decision
I will push: an Event Grid subscription filtered to `BlobCreated` and `.pdf` triggers a Function that submits to Document Intelligence, polls for the result, saves the extraction JSON to ADLS, chunks, embeds and pushes to the index.

## Consequences
- Chunk IDs are derived from document ID and chunk position, so reprocessing overwrites instead of duplicating (idempotent).
- Event Grid retries, then dead letters to a storage container I can replay from.
- Deletes are not event-driven; a nightly sweep removes index entries whose source blob is gone (phase 13).
- Accepted risk: more code to own and test than an indexer.

## Evidence
Phase 5: upload the same PDF twice, confirm the index count is unchanged. Force a Document Intelligence failure and confirm the event lands in dead letter.

## Revisit when
If chunking ever becomes standard (no custom tags), an indexer would remove the code I own.

## Interview angle
"I pushed rather than pulled because security trimming needs tags on every chunk, and I wanted extraction saved separately so I could re-chunk without paying for extraction again. The cost is owning idempotency, so chunk IDs are deterministic from the document ID."
