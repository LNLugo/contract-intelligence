# ADR-0019: Build a thin answering slice end to end before the remaining components

- **Status:** Accepted
- **Date:** 2026-11-09
- **Phase:** 6 onward (re-sequencing of the original phases 6 to 12)

## Context
After ingestion (phase 5), the original plan built the clause taxonomy (6) and the system-of-record tool (7) before any agent (8). That defers the first answered question, and every component would be built without a way to measure whether it improves answers.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Components in order: taxonomy, SAP tool, full agent graph | Every part exists before integration | First answer arrives late; no baseline to measure each component against |
| **Vertical slice first: retrieval → generation → citation check → routing, measured on the evaluation set; then add components one at a time** | A cited answer within one phase; each later component is judged by the change it makes to measured quality | The slice is deliberately incomplete (no intent, memory or policy agents yet; no SAP enrichment) |

## Decision
Slice 1: `agents/retrieve.py` (the only reader of the index, access filter enforced), `agents/answer.py` (generation with verbatim quotes, deterministic citation validation, code-based routing), `agents/ask.py` (CLI), and `eval/retrieval_eval.py` (retrieval measured against CUAD lawyer labels before any generation). Then add, one at a time, each with a before and after measurement: abstention calibration, taxonomy normalization, definitions lookup, SAP tool, the LangGraph orchestrator with intent, memory and policy, review history.

## Consequences
- The evaluation harness (originally phase 12) starts now, in a minimal form, and grows with each component.
- Retrieval is measured on its own first, so a later answer-quality problem can be attributed to retrieval or to generation instead of guessed.

## Interview angle
"I built a thin slice end to end first, retrieval to cited answer, and measured retrieval against lawyer labels before adding any generation. Every component after that had to earn its place with a before and after number."
