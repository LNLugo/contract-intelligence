# ADR-0006: Hybrid retrieval with RRF, then a cross-encoder rerank from top 20 to top 5

- **Status:** Proposed (reranker choice waits for phase 4 tier check and phase 12 measurement)
- **Date:** 2026-11-07
- **Phase:** 4, 8 and 12

## Context
Contracts mix exact terms (defined terms, party names, section numbers) that keyword search handles well with paraphrased obligations that vector search handles well. The generation step should see few, high-quality chunks: more context costs tokens and dilutes attention.

## Options considered: first-stage retrieval
| Option | Gains | Costs |
|---|---|---|
| Vector only | Handles paraphrase | Misses exact defined terms and numbers |
| BM25 only | Exact matches | Misses paraphrase |
| Hybrid BM25 + vector with RRF | Both; RRF fuses ranks without score calibration | Two retrievals per query |

## Options considered: reranking
| Option | Gains | Costs |
|---|---|---|
| AI Search semantic ranker | Managed, no hosting | Tier-dependent and billed per query; a black box I cannot tune |
| Self-hosted cross-encoder (for example `BAAI/bge-reranker-base`) | Free per query, controllable, inspectable | I host it; adds latency and CPU in the API container |
| LLM rerank | Strongest relevance judgment | Highest latency and token cost per query |

## Decision
First stage: hybrid with RRF, top 20, filtered by the user's groups. Reranker: pending. The default is the self-hosted cross-encoder, compared against the semantic ranker if the tier allows it.

## Consequences
- Top 20 to top 5 means the generation prompt holds about 4K tokens of evidence.
- Recall at 20 caps what reranking can achieve, so it is measured separately from precision at 5.

## Evidence
Phase 12: recall@20, and precision@5 per reranker, with p95 latency for each.

## Revisit when
If recall@20 is low, fix retrieval (k, chunking) before touching the reranker.

## Interview angle
"Hybrid with RRF because contracts need both exact defined terms and paraphrase. I chose a cross-encoder over an LLM reranker for latency and cost, and I measured recall at 20 separately from precision at 5, because a reranker cannot recover what retrieval missed."
