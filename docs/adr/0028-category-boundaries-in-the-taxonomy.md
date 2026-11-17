# ADR-0028: Fix judgment errors with category boundaries in the governed taxonomy, measured on held-out contracts

- **Status:** Proposed (approved only if the held-out measurement improves without new false claims)
- **Date:** 2026-11-16
- **Builds on:** ADR-0011 (governed taxonomy), ADR-0026 (snapshot), ADR-0027 (agent and error buckets)

## Context
The agent A/A run showed that about 11 of 13 errors happen after the labelled text was retrieved: the model misjudges evidence it has. Adding the category definition to the prompt would change nothing, because the evaluation questions already are the CUAD descriptions the taxonomy was seeded from. The empty `includes` / `excludes` fields are what is missing.

The review of all 11 judgment errors ([errors-review-first10](../../eval/results/errors-review-first10.md)):
| Verdict | Cases | Pattern |
|---|---|---|
| Model wrong, error reproduced | 6 | All boundary errors in 4 categories: Renewal Term (indefinite term; extension only by mutual agreement), Anti-Assignment (outright prohibition read as "no consent requirement", twice), Cap On Liability (exclusion of consequential damages not counted), Non-Compete (exclusivity commitment counted as non-compete) |
| Noise, correct on re-run | 4 | Two near the same boundaries (territory vs non-compete, trademark display vs license) |
| Label debatable | 1 | Audit Rights: quarterly information meetings labelled as an audit right |

The model is too literal on two categories and too broad on two. A reviewer model would face the same unwritten conventions, so boundaries come first.

## Decision
1. **Boundaries live in the governed taxonomy**, not in the prompt text: a new version `cuad-v2` adds `includes` / `excludes` (and matching terms) for the four categories, reviewed as a file (`taxonomy/boundaries/cuad-v2.json`) and stored as a draft (`taxonomy/create_version.py`).
2. **The prompt shows the approved boundaries for the question's category** (both workflow and agent), with the taxonomy version. Categories without boundaries are unchanged. `BOUNDARIES=false` turns it off for A/B runs.
3. **Development and held-out sets are kept apart.** The 10 contracts whose errors were read (`first10`) are the development set. The decision is made on the other 10 (`next10`), measured before and after, with the draft exported as a candidate snapshot; only then is `cuad-v2` approved and exported to `approved.json`.
4. **Approval rule:** on `next10`, fewer missed clauses plus false claims than without boundaries, no new false claims in the four categories, no category made worse beyond noise (agent A/A: ~11%).

## First held-out measurement (next10, 2026-11-16): not approved
Before vs after the cuad-v2 draft: workflow 17 → 18 errors, agent 11 → 13. Not an improvement. Two causes found:
1. **Classifier bug:** only 4 of 10 evaluated categories were recognised from their CUAD questions; Non-Compete (the agent's most false claims) never received its boundaries, and Exclusivity was classified as "Parties" through the one-word term "parties". Also wrong in production `/ask` responses. Fix: one-word terms never pick a category; question-phrase terms for all evaluated categories.
2. **A boundary fitted to one example:** Cap On Liability false claims went from 2 to 4 in both modes after adding "exclusions of damage types count". The first10 labels counted such an exclusion as a cap; the next10 labels did not. A CUAD labelling inconsistency, not a model error: the include is removed.

`next10` has now shaped the draft, so it is no longer held out. Revision 2 is decided on `rest30`, the 30 contracts of the evaluation set never used for development.

## Consequences
- Legal's conventions become explicit, versioned and reviewable, and every answer reports the taxonomy version it used.
- Each boundary is a small rule that must stay consistent with the CUAD labels; a boundary that disagrees with how the lawyers labelled would show up as a regression on held-out contracts.
- The 4 noise cases point to consistency, not definitions: the three-sample agreement (ADR-0022) remains the tool for those.

## Alternatives considered
- **Reviewer model now:** doubles cost per question and would need the same boundaries to judge correctly.
- **Prompt rules written directly into the system prompt:** works, but bypasses governance and cannot be approved, versioned or audited per answer.
- **Measure on the same contracts the errors came from:** guaranteed to look better; rejected as fitting to the test.
