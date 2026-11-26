# Old vs new citation check on the same answers (ADR-0029)

- **Date:** 2026-11-26 · **Script:** `eval/citation_ab.py` · **Raw:** `citation-ab-first10-20261126-130955.json`
- **Set:** first10 development contracts, 100 questions, evaluation deployment `gpt-5.4-mini-eval`, rerank off
- **Design:** one retrieval and one model answer per question; every citation judged by both rules. Paired, so run-to-run noise (about 9%) cannot affect the comparison.

## Result
| | Old rule (ADR-0020) | New rule (ADR-0029) |
|---|---|---|
| Citations passed (of 330) | 324 | 315 |
| Correct | 84 | 84 |
| Missed | 6 | 6 |
| False claims | 6 | 6 |
| Abstained | 4 | 4 |

**No outcome changed.** Every finding that lost a citation still had another valid one.

New rule, by kind: exact 308, fuzzy 7 (PDF noise, all also passed by the old rule), not_in_clause 11, too_short 4.

## The 9 citations only the old rule passed: all correct rejections
| Kind | Count | What the model did |
|---|---|---|
| Elided | 5 | Joined the start and end of a clause with "...". The omitted text is where an "unless" or "subject to" would hide. |
| Heading | 2 | Cited a section title ("§ 6 Limitation of liability", "The supplier declares herewith:") as evidence. |
| Spliced | 1 | Ended a real sentence with words from elsewhere: the clause says the shares "will be given to PSS's transfer agent", the quote says they "can only be sold by the undersigned". |
| Qualifier dropped | 1 | Quoted "The Company and the ValueAct Group shall work together"; the clause says "the ValueAct Group and the Company (acting through the Board) shall work together". |

No false rejections were found. Elided quotes now fail with their own reason, `elided`, so the audit log shows the model shortening quotes separately from misquoting them.

## What this does not show
- Whether a valid quote supports its statement. The 6 false claims passed both rules with genuine quotes: that is the support check's job.
- Behaviour on scanned or poor-quality PDFs: only 7 fuzzy matches occurred here.
