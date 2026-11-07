# ADR-0008: Review history retrieved from its own index, not appended to the prompt

- **Status:** Proposed (to be decided by reproducing the failure first)
- **Date:** 2026-11-07
- **Phase:** 10

## Context
Reviewers ask follow-up questions across a session. The naive memory design appends the full history to every prompt. On long contracts with long sessions, the prompt overflows, truncation drops the earliest material, and the clauses discussed first silently disappear from the model's view.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Append full history | Trivial | Overflow and silent truncation on long sessions |
| Rolling summary | Bounded size | Summaries lose exact clause wording, which citations depend on |
| History in its own search index, retrieve relevant turns | Bounded and precise | Another index; retrieval can miss a relevant earlier turn |

## Decision
Pending, by experiment: build the naive version first, reproduce the overflow on a long CUAD contract with a scripted 15-turn session, then implement the index-based fix and measure again.

## Consequences
- The build log will contain a real failure and a real fix, not a described one.

## Evidence
Phase 10: number of earlier-clause references answered correctly at turn 15, naive vs index-based, and prompt token count per turn for each.

## Interview angle
"I reproduced the failure on purpose: append-everything memory silently dropped the clauses discussed first. Moving history into its own index kept the prompt bounded and brought back the earlier clauses, and I have the before and after token counts."
