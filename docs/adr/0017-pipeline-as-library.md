# ADR-0017: The ingestion pipeline is a library; the batch script and the Function are thin callers

- **Status:** Accepted
- **Date:** 2026-11-08
- **Phase:** 5

## Context
Ingestion has two triggers: a one-off batch over the 50-contract evaluation set, and the event-driven path (upload → Event Grid → Function) for every later document. If the logic lives inside the Function, every fix needs a deploy and an upload to test, failures surface only in cloud logs, and the batch run would need a second copy of the same logic that drifts from the first.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Logic inside the Function only; batch by uploading 50 files | One deployable | Debugging through deploy cycles and logs; batch progress and cost hard to see |
| Separate batch script and Function, each with its own logic | Each tuned for its job | Two code paths that drift; the evaluation measures code production does not run |
| **One library (`ingestion/pipeline`), two thin callers** | One code path; debuggable locally with breakpoints; unit tests without Azure | Package layout must work both locally and in the Functions runtime |

## Decision
`pipeline.process.process(pdf, file_name, meta)` is the only entry point for ingesting a document. `batch_ingest.py` and the phase 5c Function both call it and contain no pipeline logic. Identity comes from `DefaultAzureCredential`: `az login` on the laptop, managed identity in Azure.

## Consequences
- Bugs are reproduced and fixed on the laptop, then the Function picks up the fix unchanged.
- The evaluation set is indexed by exactly the code that will run in production.
- Chunking is pure Python with unit tests (`ingestion/tests`), no Azure needed.
- Batch uploads to `contracts-raw/eval/`. The phase 5c Event Grid subscription must filter on a different prefix (`inbox/`) so the batch files do not trigger a second ingestion.

## Interview angle
"I kept the pipeline as a library with two thin callers: a batch script for the evaluation set and the Event Grid Function for live uploads. Bugs were fixed with a debugger on my laptop instead of through deploy cycles, and the evaluation numbers come from the same code path production runs."
