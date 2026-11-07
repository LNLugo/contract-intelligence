# ADR-0002: Use CUAD as the contract corpus and evaluation ground truth

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0

## Context
A contract system needs real contracts to test extraction and chunking, and labeled answers to measure accuracy. Without labels, "it seems to work" is the only evidence, which does not survive an interview follow-up.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Synthetic contracts written by an LLM | Unlimited, any clause on demand | Too clean; no scanned pages, odd layouts or messy numbering |
| Public filings scraped ad hoc | Real documents | No labels, so no accuracy measurement |
| CUAD (Atticus Project, CC BY 4.0) | About 500 real commercial contracts, lawyer labels across 41 clause categories | Not raw materials procurement contracts; label set may not match every finding the system produces |

## Decision
I will use CUAD for both the corpus and the evaluation ground truth, and map my clause taxonomy onto its 41 categories.

## Consequences
- Clause-level precision and recall can be measured from day one.
- The taxonomy (ADR-0011) gets a realistic seed.
- Accepted risk: CUAD covers commercial agreements (licensing, distribution, supply), not procurement-specific terms. Findings outside CUAD's categories need a small hand-labeled set.

## Enterprise vs this build
In production, ground truth comes from held-out historical legal decisions judged by a human reviewer. CUAD is the public substitute for that.

## Evidence
Phase 12 results table.

## Revisit when
If more than a small share of findings fall outside CUAD categories, build a hand-labeled supplement.

## Interview angle
"I did not want to evaluate on vibes, so I used CUAD: 500 real contracts with lawyer labels across 41 clause types. That gave me clause-level recall to tune chunking and reranking against."
