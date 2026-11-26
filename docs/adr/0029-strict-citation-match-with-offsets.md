# ADR-0029: Strict citation match, with offsets, a meaning guard and logged drops

- **Status:** Accepted
- **Date:** 2026-11-26
- **Phase:** Hardening
- **Supersedes:** the matching rule in ADR-0020 (the rest of ADR-0020 stands)

## Context
ADR-0020's check accepted a quote that matched exactly after lower-casing and stripping punctuation, or, failing that, when 90% of its words appeared in order in the clause. The fallback was meant for PDF noise, but it also accepts a quote with one word added in ten. In a contract the word that slips through is often the one that matters: a quote of "shall exceed" with "not" inserted still scored 9 of 10. In a regulated domain a citation that reverses the clause is worse than no citation.

Three things were also missing: the citation could not be highlighted in the source, failures were counted but not explained, and nothing showed whether failures were rising.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Keep the 90%-of-words rule | No change | Accepts meaning-changing edits |
| Exact match only | Simplest, strongest | Rejects real quotes broken by hyphenation, stray characters or OCR noise |
| **Exact after cleaning; fuzzy only above 95, and only when negations, modal verbs and numbers are identical** | Tolerates PDF noise, never a change of meaning | A few lines more; one dependency (rapidfuzz) |

## Decision
`agents/citations.py`, used by both the workflow and the agent:
1. Quote and clause cleaned the same way: Unicode NFKC, typographic quotes and dashes mapped to plain ones (NFKC does not convert curly quotes), soft hyphens removed, whitespace runs collapsed to one space. Case is kept.
2. The cleaned quote must be at least 40 characters (15 lets short phrases match almost anywhere).
3. **Exact:** the cleaned quote appears in the cleaned clause.
4. **Fuzzy:** rapidfuzz `partial_ratio` of 95 or more, **and** the quote and the matched span contain the same negations (not, no, never, neither, nor, none, without, unless, except, notwithstanding), modal verbs (shall, may, must, only) and numbers, in the same order. Otherwise rejected as `fuzzy_changed_meaning`.
5. Each citation records `match` (exact or fuzzy), the failure `reason`, and `start`/`end` character offsets into the original clause text, so a reviewer can highlight the exact span.
6. Each answer carries `citation_checks` (counts of exact, fuzzy and each failure reason). The audit log records these counts, never the quote text.

## Measured (eval/results/citation-ab-first10.md)
Paired test on 100 development questions, both rules judging the same answers: the new rule rejected 9 citations the old rule passed (5 elided with "...", 2 section headings, 1 spliced from two passages, 1 with a qualifier dropped). All 9 were correct rejections; **no outcome changed**. Elided quotes now fail with their own reason, `elided`.

## Consequences
- Measured on the inserted-"not" case: partial_ratio scored it **97**. A fuzzy threshold alone would have accepted it; the meaning guard rejects it. Unit test `test_inserted_not_fails_even_if_almost_identical`.
- Matching is now case-sensitive and stricter, so some quotes that passed before will fail and their findings will be dropped. Expect a small rise in abstentions; confirm on the next evaluation run before comparing against earlier results.
- The prompts are unchanged (they still ask for 8 to 40 word verbatim quotes under the key `quote`), so evaluation results stay traceable to their prompt names.
- Offsets are relative to the cited chunk. Highlighting in the full PDF needs each chunk's character offset in the document, stored at ingestion: open item.
- A rise in `not_in_clause` or `too_short` counts usually means a parsing bug or a prompt change, not the model: the counts are in the audit log for an alert to watch (open item, with the audit-store ADR).
- This check still proves only that the quote is real. Whether it supports the statement is the support check's job (ADR-0020, still to build).

## Interview angle
"My citation check is deterministic: exact match after Unicode cleaning, and a fuzzy fallback only for PDF noise. The fuzzy path is guarded: if the quote and the source differ in a negation, a modal verb or a number, it fails. I found this by testing: a quote with 'not' inserted scored 97 on partial_ratio, so a plain threshold would have passed a citation that reverses the clause. Each citation stores character offsets so a lawyer can see the exact span, and the drop counts go to the audit log as a health signal."
