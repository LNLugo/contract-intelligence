# ADR-0016: AI Search Free tier, 1024-dimension vectors, vectors not stored for retrieval

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 4

## Context
The Free tier of AI Search allows one service per subscription, 50 MB of storage and 3 indexes, has no SLA, and a free service can be deleted after a long period of inactivity. Basic and above bill every hour the service exists, which would consume most of the $100 credit over the build. The index has to hold the 50-contract evaluation set and leave room for a second chunking variant (ADR-0005 experiment) and the review history index (ADR-0008), within the 3-index cap.

## Estimate (to be replaced by `servicestats` after phase 5)
| Item | Basis | Estimate |
|---|---|---|
| Tokens in evaluation set | 1,526 pages × ~600 tokens | ~900K |
| Chunks | 800 tokens, 15% overlap | ~1,350 |
| Vectors at 3,072 dimensions | 1,350 × 12 KB | ~17 MB |
| Vectors at 1,024 dimensions | 1,350 × 4 KB | ~5.5 MB |
| Text, inverted index, graph overhead | | ~10 to 13 MB |
| **Index total at 3,072 / 1,024** | | **~30 MB / ~17 MB** |

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Basic tier, 3,072 dimensions | Room for everything; SLA; private endpoints | Hourly billing for the life of the service |
| Free tier, 3,072 dimensions | Full embedding fidelity | ~30 MB: one index fits, a second variant does not |
| **Free tier, 1,024 dimensions** (embedding API `dimensions` parameter) | ~17 MB; room for two variants or a variant plus history | Some retrieval quality loss, to be measured |
| Free tier, 3,072 dimensions with scalar quantization | Keeps full dimensions, compresses vectors | Full-precision originals kept for rescoring still count against storage; more settings to tune |
| Smaller model (`text-embedding-3-small`) | Smaller vectors | Weaker retrieval on legal language; changes two variables at once |

## Decision
Free tier. Embeddings requested at 1,024 dimensions from `text-embedding-3-large`. Vector field set to `stored: false` (vectors are searchable but not returned in results, which saves storage; nothing in the application needs to read a vector back). HNSW with cosine distance.

## Consequences
- Index fits with headroom for one more index; the 3-index cap is the binding limit, not storage.
- The free service can be deleted after inactivity. Mitigation: the index is fully rebuildable from extraction JSON in ADLS (ADR-0004) without re-paying for extraction. A rebuild script is part of phase 5.
- Private endpoints are not available on Free; phase 13 hardening needs a short-lived Basic service.
- Search authentication: Entra ID only, local keys disabled (ADR-0013). Role-based access works on every tier including Free; search role assignments can take 5 to 10 minutes to apply, so scripts retry instead of failing.
- The Free tier has no managed identity, so the search service cannot pull from storage or call the embedding model itself. The push model (ADR-0004) does not need it: the Function holds the identity and pushes finished chunks. This is a second, independent reason for push over pull on this budget.
- A Free service cannot be upgraded in place; moving to Basic means a new service and a reindex from ADLS.

## Evidence
- **Measured 2026-11-09:** 50 contracts, 1,526 pages, 1,238 chunks at 1,024 dimensions = **14.1 MB of 50 MB** (estimate was ~17 MB). Room remains for a second chunking variant and the review history index.
- Phase 4: index created, smoke test passes, `servicestats` storage reported.
- Phase 5: measured index size for the full evaluation set replaces the estimate above.
- Phase 12: recall@20 at 1,024 vs 3,072 dimensions on a subset of the evaluation set, to put a number on what the dimension cut costs.

## Revisit when
Measured index size exceeds 35 MB, or the phase 12 comparison shows a recall loss larger than a few points.

## Interview angle
"The free search tier gives 50 MB and three indexes. At full dimensions the evaluation set alone would take most of that, leaving no room for a second chunking variant or the history index. I cut embeddings to 1,024 dimensions with the model's own dimensions parameter, stopped storing the vectors for retrieval, and scheduled a measurement of what the cut costs in recall instead of assuming it was free."
