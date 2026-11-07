# ADR-0012: Clause-level evaluation against labeled ground truth, with a calibrated LLM judge

- **Status:** Proposed
- **Date:** 2026-11-07
- **Phase:** 12

## Context
Every other ADR waits on a measurement, so the evaluation method decides whether those decisions are evidence-based. An LLM judge is cheap and scalable, but an uncalibrated judge just adds a second unverified model.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Manual spot checks | Easy | Not repeatable; no numbers |
| CUAD labels only | Objective for clause detection | Does not judge whether a cited chunk supports the finding |
| CUAD labels + LLM judge for citation support, calibrated on a hand-labeled sample | Covers detection and support; repeatable | Calibration takes manual effort |

## Decision (proposed)
- Fixed, held-out evaluation set of CUAD contracts, never used for tuning.
- Metrics: clause recall and precision per category; retrieval recall@20 and precision@5; citation support rate; abstention rate; accuracy on non-abstained findings; p95 latency; token cost per contract.
- The LLM judge is calibrated against about 50 findings I label by hand; agreement rate reported next to every judge-based number.
- One variable changed per experiment, with results logged in `eval/results/`.

## Interview angle
"Every design choice in the repo points to a number from one held-out set, and I report how often the LLM judge agreed with my hand labels, so the judge itself has evidence behind it."
