# ADR-0015: Paid Document Intelligence tier, extracting a stratified 50-contract evaluation set once

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 2 and 5

## Context
Document Intelligence F0 (free) analyzes only the first 2 pages of each document. Contracts put critical clauses (liability caps, termination, indemnification, governing law) anywhere, often deep in the body. Extracting only pages 1 and 2 would silently drop most clauses, and the evaluation would blame retrieval or the model for an extraction gap. The paid tier charges per page (prebuilt-layout about $10 per 1,000 pages), and the corpus is fixed, so the cost is measurable.

## Evidence (2026-11-07, `eval/page_stats.py` over CUAD v1)
| Measure | Value |
|---|---|
| Contracts | 510 (0 failed to open) |
| Total pages | 9,348 |
| Pages per contract | min 1, median 11, p90 46, p99 106, max 154 |
| Contracts of 2 pages or fewer | 38 (7%) |
| Pages the free tier would read | 1,000 of 9,348 (11%) |
| Full corpus extraction | $93.48 |
| 50 median-length contracts | 540 pages, $5.40 |

## Options considered
| Option | Gains | Costs |
|---|---|---|
| F0, full corpus | Free | Reads 11% of pages; most clauses never reach the index |
| F0, only contracts of 2 pages or fewer | Free; full extraction for those | 7% of the corpus, and short contracts lack the clauses that matter |
| S0, 50 median-length contracts | $5.40 | Excludes long contracts, the exact case where context overflow (ADR-0008) and missed clauses appear; the evaluation would look better than reality |
| **S0, stratified 50-contract set** | **Covers typical, long and very long contracts; about $15.50, extracted once** | **Per-page spend; development smoke tests also cost (about $0.01 per page)** |
| S0, full corpus | Everything indexed | $93.48, almost the whole credit, for little extra learning |
| Skip extraction, use CUAD's TXT files | Free, complete text | Loses layout, headings, tables and page numbers needed for citations |

## Decision
Upgrade `di-ci-dev-2416` to S0. Extract a fixed evaluation set of 50 contracts once, stratified by length: 30 typical (8 to 15 pages), 15 long (30 to 60 pages), 5 very long (over 100 pages), spread across contract types. The selection is written to `eval/eval_set.csv` and never changes, so every experiment runs on the same documents (ADR-0012).

## Consequences
- Extraction JSON stored in ADLS is the asset; re-chunking experiments never re-extract. ADR-0004's design choice now has a dollar figure: each avoided re-extraction of the set saves about $15.50.
- The Function must check for an existing extraction before calling Document Intelligence.
- Development smoke tests use 1 to 2 page documents.
- Accepted risk: results describe a 50-contract sample, not the full corpus; the stratification is reported alongside every metric.

## Enterprise vs this build
At enterprise volume (thousands of contracts per year), the same per-page model applies; commitment tiers lower the unit price, and the cost per contract belongs in the unit-economics line (cost log).

## Interview angle
"The free tier would have read 11% of the pages, so 89% of the clauses would never reach the index, and the evaluation would have blamed the model. Extracting everything would have spent almost the whole budget. I measured the corpus, saw 10% of contracts run past 46 pages, and extracted a 50-contract set stratified by length for about fifteen dollars, because a median-only sample would have hidden the long-contract failure I was testing for."
