# ADR-0006: Hybrid retrieval with RRF, then a cross-encoder rerank from top 20 to top 5

- **Status:** First stage Accepted; reranker choice waits for the phase 12 measurement
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
- 2026-11-08, phase 4 smoke test: hybrid query "cap on damages" returned the liability clause first although neither word appears in it (vector side matching on meaning), with the group filter applied.
- 2026-11-08: semantic ranker **is available on the Free tier** (first 1,000 requests per month free). Both reranker options can therefore be compared at no cost; the comparison is no longer limited by tier.
- Observed fused scores were 0.0167 and 0.0164. RRF scores reflect rank positions, not relevance, so **they cannot be used as a confidence threshold for abstention** (ADR-0009). Abstention must use the reranker's score or the Evaluation Agent's confidence.
- Phase 12: recall@20, and precision@5 per reranker (semantic ranker vs self-hosted cross-encoder), with p95 latency for each.

## Revisit when
If recall@20 is low, fix retrieval (k, chunking) before touching the reranker.

## Interview angle
"Hybrid with RRF because contracts need both exact defined terms and paraphrase. I chose a cross-encoder over an LLM reranker for latency and cost, and I measured recall at 20 separately from precision at 5, because a reranker cannot recover what retrieval missed."
