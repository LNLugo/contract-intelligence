# ADR-0021: The model returns its determination separately from the evidence it cites

- **Status:** Format accepted; prompt wording under experiment (see revision)
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

## Revision 2026-11-09: measured, and a bundled-variable mistake
**Evidence** (`eval/results/run-v2-strict.md`, same 200 questions, retrieval cached): false claims 23 → 16 (Termination For Convenience 8 → 2), absent reported correctly 70% → 79%, but **missed clauses 3 → 12** and detection 97% → 90%, concentrated in categories CUAD defines broadly (Cap On Liability, Exclusivity, Anti-Assignment, Audit Rights).

**Mistake:** this change bundled two variables: the output format and a prompt rule that related-but-not-matching provisions mean "absent". The rule generalized into strictness everywhere, including where the labels are broad. The run cannot separate their effects.

**Decision:** keep the format and code routing (they are correct regardless, and unit-tested). Treat the prompt wording as its own experiment: prompts are now named and versioned (`agents/prompts.py`), every result records which prompt produced it, and the next run (`v3-neutral`) removes only the rule.

**Weighting rule for this domain:** a missed clause costs more than a false claim. A false claim arrives with a citation a reviewer can reject in seconds; a missed clause is silent. Detection recall is the primary metric; false claims are secondary.

## Revision 2 (2026-11-09): the trade is in the definition, not the format
`v3-neutral` (format kept, rule removed): missed 10, false claims 15, found 91% (`eval/results/run-v3-neutral.md`). Removing the rule barely moved the numbers, so the rule was not the cause. Comparing each v3 miss with the baseline answer showed 8 of 10 were correct "Yes" answers in the baseline: partial or limited forms (limited exclusivity, non-compete-style restrictions, a time limit as a cap) that CUAD counts as present. The baseline prompt asked whether clauses "address" the question; the determination asks whether the contract "contains" it.

**Conclusion:** narrow categories need strict reading, broad categories need broad reading; one global wording cannot do both. The format and routing stay. Category definitions move to the clause taxonomy (ADR-0011), derived from CUAD's descriptions and from labelled examples outside the evaluation set, so the evaluation stays a test set. `v3-neutral` is the interim default.

## Interview angle
"My first evaluation showed 23 false claims. Reading them, most weren't hallucinations: the model said 'No' and cited the for-cause clauses to explain why, and my routing treated any valid citation as 'the clause exists'. The bug was in the output contract, not the model. I separated the determination from the evidence, routed on the determination in code, and re-measured with retrieval frozen. The first re-measurement taught me something too: I had also tightened the prompt in the same change, missed clauses went from 3 to 12, and I couldn't tell which change did what. Since then prompts are versioned and every experiment changes exactly one thing, and I weight a missed clause above a false claim because only one of them comes with a citation a reviewer can check."
