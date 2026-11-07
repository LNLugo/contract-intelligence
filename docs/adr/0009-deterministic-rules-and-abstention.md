# ADR-0009: Business rules and risk routing run outside the LLM; abstain when evidence fails

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 9

## Context
Some checks have exact answers: do the contract's payment terms match the vendor master? Is the liability cap above a threshold? An LLM can produce the wrong answer to these with full confidence. And the cost of a wrong finding (approving a bad contract) is far higher than the cost of a flagged one (a human looks at it).

## Options considered
| Option | Gains | Costs |
|---|---|---|
| LLM decides findings and routing | Flexible | Not reproducible; hard to audit; confident errors |
| LLM extracts, code compares and routes | Reproducible, testable, auditable | Rules must be written and maintained |
| Always route to a human | Safe | Removes the time savings |

## Decision
The LLM extracts and cites; code compares, scores and routes. The router has three exits: low risk → final response; high risk → legal review; missing, contradictory or system-of-record unavailable → abstain and flag.

## Consequences
- Every routing decision is unit-testable with fixed inputs.
- Abstain is a first-class outcome, counted in the eval: abstaining on a correct answer is measured as a cost, not hidden.

## Evidence
Phase 9: unit tests for each router branch. Phase 12: abstention rate and accuracy on non-abstained findings.

## Interview angle
"The model reads and cites; it never decides. Comparisons and routing are plain code with unit tests, and abstaining is a valid output that I measure, because a flagged finding costs a reviewer five minutes and a wrong one costs a bad contract."
