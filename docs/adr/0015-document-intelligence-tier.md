# ADR-0015: Document Intelligence tier for a corpus of long contracts

- **Status:** Proposed (waiting for CUAD page measurements)
- **Date:** 2026-11-07
- **Phase:** 2 and 5

## Context
Document Intelligence F0 (free) analyzes only the first 2 pages of each document. Contracts put critical clauses (liability caps, termination, indemnification, governing law) anywhere, often deep in the body. Extracting only page 1 and 2 would silently drop most clauses, and the evaluation would blame retrieval or the model for an extraction gap. The paid tier charges per page; the corpus is fixed, so the cost is calculable rather than estimated.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| F0, full corpus | Free | Reads only 2 pages per contract; most clauses never reach the index |
| F0, only contracts of 2 pages or fewer | Free; full extraction for those | Unrepresentative sample; short contracts lack the clauses that matter |
| S0, a fixed 50-contract evaluation set | Full extraction where it is measured; bounded cost | Per-page spend; a second resource (or tier change) |
| S0, full corpus | Everything indexed | Highest spend for little extra learning |
| Skip extraction, use CUAD's TXT files | Free, complete text | Loses layout, headings, tables and page numbers needed for citations; skips the service being learned |

## Decision
Pending. Expected: S0 for a fixed evaluation set of about 50 median-length contracts, chosen once and reused for every experiment (ADR-0012). F0 stays for development smoke tests.

## Evidence needed
Output of `eval/page_stats.py`: page distribution, share of pages the free tier would read, cost of full extraction and of the 50-contract set at the current price per 1,000 pages.

## Interview angle
"The free tier only reads two pages, which for contracts means silently losing the clauses that matter, and the evaluation would have blamed the model. I measured the corpus page distribution and paid for full extraction on a fixed evaluation set only, so the cost was a calculated number, not a guess."
