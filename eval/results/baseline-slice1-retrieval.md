# Baseline: slice 1 retrieval (2026-11-09)

Run: `eval/retrieval_eval.py` over the 50-contract evaluation set, 10 CUAD categories, 500 queries
(279 with the clause present, 221 absent). Index: 1,238 chunks, 800-token paragraph-filled chunks,
1,024-dimension `text-embedding-3-large`, hybrid BM25 + vector with RRF, semantic ranker on Free.
A hit = a retrieved chunk contains any 8-word run of the CUAD-labelled clause text.
(The JSON results file was not written because of a missing-folder bug, since fixed; figures below are from the printed output.)

| category | n | hyb@1 | hyb@5 | hyb@20 | rr@1 | rr@5 | MRR hyb | MRR rr |
|---|---|---|---|---|---|---|---|---|
| Governing Law | 46 | 74% | 98% | 98% | 91% | 98% | 0.83 | 0.95 |
| Termination For Convenience | 21 | 71% | 95% | 100% | 81% | 95% | 0.83 | 0.87 |
| Cap On Liability | 36 | 72% | 92% | 97% | 72% | **86%** | 0.82 | 0.78 |
| Anti-Assignment | 45 | 73% | 98% | 100% | 87% | 100% | 0.83 | 0.92 |
| Exclusivity | 14 | 36% | 64% | 93% | 36% | 79% | 0.52 | 0.54 |
| Non-Compete | 15 | 40% | 60% | 93% | **27%** | 80% | 0.53 | 0.50 |
| Audit Rights | 33 | 70% | 91% | 100% | 73% | 97% | 0.79 | 0.81 |
| Insurance | 22 | 59% | 100% | 100% | 82% | 100% | 0.74 | 0.90 |
| Renewal Term | 20 | 60% | 95% | 95% | 95% | 100% | 0.73 | 0.97 |
| License Grant | 27 | 59% | 96% | 100% | 59% | 96% | 0.75 | 0.77 |
| **ALL** | **279** | **66%** | **92%** | **98%** | **75%** | **95%** | **0.77** | **0.84** |

Recall@5 by contract length: typical 97% hybrid / 99% reranked (avg 10 chunks per contract); long 88% / 91%; very long 84% / 84% (20+ chunks, capped).

Top semantic reranker score: clause present median 2.30, p10 1.96 (n=279); clause absent median 1.96, p90 2.35 (n=221).

## Findings
1. Recall falls with contract length (99% → 91% → 84% at top 5). A median-length-only sample would have reported about 99% (validates ADR-0015).
2. The reranker improves rank 1 overall (+9 points) but lowers top-5 recall for Cap On Liability (92% → 86%) and rank-1 recall for Non-Compete (40% → 27%). Not uniformly better (ADR-0006).
3. Reranker scores for present and absent clauses overlap almost completely, so a score threshold cannot decide whether a clause exists. Absence must be judged by the model reading the evidence (NOT_FOUND); the threshold remains only a guard against irrelevant retrieval (ADR-0009 revision).
4. Caveat: for typical contracts (about 10 chunks) top 5 is half the document, which inflates recall; long contracts are the meaningful test.
