# ADR-0005: Fixed-size overlapping chunks in v1; clause-aware chunking as a measured experiment

- **Status:** Accepted for v1
- **Date:** 2026-11-07
- **Phase:** 5 and 12

## Context
Clauses vary from one line to several pages. Fixed-size chunks can split a clause across two chunks or merge unrelated clauses. Clause-aware chunking uses the layout model's headings and section numbering, but contracts are inconsistently formatted, so the parser can fail silently.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Fixed size with overlap | Predictable, simple, robust to bad formatting | Clauses split across boundaries; overlap inflates index size |
| Clause-aware (layout sections) | Chunks align with what the reviewer reasons about | Fragile on badly formatted contracts; very uneven chunk sizes |
| Hybrid: section-aware with a size cap and fixed-size fallback | Best of both in theory | Most code; hardest to debug |

## Decision
I will ship fixed-size overlapping chunks in v1 (starting point: about 800 tokens with 15% overlap), keep the page and section reference on each chunk for citation, and test clause-aware chunking in phase 12 as a controlled experiment.

## Consequences
- Citations still point to a page and section because the metadata travels with each chunk.
- Missed clauses are the expected failure mode, and the eval will count them.

## Evidence
Phase 12: clause-level recall for fixed-size vs clause-aware chunking on the same CUAD subset, with everything else held constant.

## Revisit when
If missed clauses dominate the errors in the eval.

## Interview angle
"I started with fixed-size chunks on purpose because they never fail silently, then ran clause-aware chunking as a controlled experiment against CUAD labels, changing one variable at a time. Missed clauses were the error I was measuring."
