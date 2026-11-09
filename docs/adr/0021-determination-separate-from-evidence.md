# ADR-0021: The model returns its determination separately from the evidence it cites

- **Status:** Accepted (effect to be measured against the slice 1 answer baseline)
- **Date:** 2026-11-09
- **Phase:** Slice 1

## Context
Slice 1's output format was `found: true|false` plus `findings` with citations, and code routed "has valid findings" to ANSWERED. The answer baseline (`eval/results/baseline-slice1-answers.md`) reported 23 false claims out of 83 absent clauses, 8 of them for Termination For Convenience.

Reading those answers showed most were not wrong conclusions. Several began "No." or stated that the contract "does not provide a general no-cause termination right". The model cited the termination-for-cause clauses **as evidence for its "no"**, and the routing code read the presence of valid findings as "the clause exists". The format conflated two things: the yes/no determination and the evidence behind it. The metric inherited the same conflation.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Keep the format; tell the model not to cite anything when the answer is "no" | No schema change | Removes the explanation a reviewer needs to trust a "no" |
| Route on keywords in the answer text ("No.") | Quick | Fragile; free text is not a contract |
| **Explicit `determination: present / absent / unclear`, separate from findings; code routes on it** | A "no" can still cite its evidence; "unclear" gets its own route to a reviewer; routing is testable | One more field to keep consistent with the findings |

## Decision
Code routes: `present` + at least one valid citation → ANSWERED; `present` with every citation failing → ABSTAIN; `absent` → NOT_FOUND (explanatory evidence kept); `unclear` → ABSTAIN, routed to a reviewer. The prompt defines "absent" to include related provisions that do not meet the question's definition (for cause versus without cause). Unit tests cover all four routes, including the baseline bug.

## Evaluation discipline
Retrieval is cached from the first run and reused, so this change is measured with retrieval held fixed: one variable at a time, and no further semantic-ranker quota spent.

## Interview angle
"My first evaluation showed 23 false claims. Reading them, most weren't hallucinations: the model said 'No' and cited the for-cause clauses to explain why, and my routing treated any valid citation as 'the clause exists'. The bug was in the output contract, not the model. I separated the determination from the evidence, routed on the determination in code, and re-measured with retrieval frozen so the change was the only variable."
