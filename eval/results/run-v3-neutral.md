# Run: determination field, strictness rule removed (prompt `v3-neutral`), 2026-11-09

Same 200 questions, retrieval cached (identical chunks for every run).

| category | present | absent | found | missed | grounded | absent ok | false claims | abstain |
|---|---|---|---|---|---|---|---|---|
| Governing Law | 19 | 1 | 100% | 0 | 100% | 100% | 0 | 0 |
| Termination For Convenience | 7 | 13 | 100% | 0 | 100% | 85% | 2 | 0 |
| Cap On Liability | 13 | 7 | 85% | 2 | 91% | 57% | 3 | 0 |
| Anti-Assignment | 18 | 2 | 94% | 1 | 100% | 100% | 0 | 0 |
| Exclusivity | 9 | 11 | 56% | 4 | 100% | 91% | 1 | 0 |
| Non-Compete | 8 | 12 | 88% | 1 | 71% | 64% | 4 | 1 |
| Audit Rights | 14 | 6 | 93% | 1 | 100% | 100% | 0 | 1 |
| Insurance | 8 | 12 | 88% | 1 | 100% | 100% | 0 | 1 |
| Renewal Term | 7 | 13 | 100% | 0 | 100% | 71% | 2 | 6 |
| License Grant | 14 | 6 | 100% | 0 | 93% | 50% | 3 | 0 |
| **ALL** | **117** | **83** | **91%** | **10** | **96%** | **80%** | **15** | **9** |

p50 2.4 s, p95 33.1 s; 4,225 tokens per question; 5 findings dropped by the citation check; 0 errors.

## Three runs compared
| | baseline (`found` field, lenient "address") | v2-strict | v3-neutral |
|---|---|---|---|
| Found | 97% | 90% | 91% |
| **Missed** | **3** | 12 | 10 |
| False claims | 23 | 16 | 15 |
| Absent reported correctly | 70% | 79% | 80% |

## What the 10 v3 misses said in the baseline
- 2 were missed by the baseline too (Audit Rights, Cap On Liability).
- **8 were answered "Yes." by the baseline, correctly**: limited exclusivity, "exclusivity-style restrictions", a "non-compete-style restriction", territory-based exclusivity, an absolute anti-assignment, insurance maintenance, a time limit for breach claims as a cap.

## Hypotheses tested
1. *The strictness rule caused the misses* (after v2-strict): **rejected**. Removing it changed missed 12 → 10, false claims 16 → 15, within noise.
2. *The baseline's 97% was inflated by the routing bug*: **rejected**. 8 of the 10 lost detections were genuine, correct "Yes" answers in the baseline.

## Conclusion
The baseline asked whether the clauses "address" the question (lenient); the determination field asks whether the contract "contains" it (strict). Strictness fixed narrow categories (Termination For Convenience false claims 8 → 2) and broke broad ones (8 partial or limited forms that CUAD counts as present). **No single global wording serves both; each category needs its own definition of what counts.** Next component: per-category definitions (ADR-0011), built from CUAD's published descriptions and labelled examples from the 460 contracts outside the evaluation set, never from these misses.

Open question before comparing further: run-to-run variance of the same prompt (noise floor). Measured next with an identical repeat run.
