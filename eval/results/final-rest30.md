# Final test set: rest30 (2026-11-16)

30 contracts of the 50-contract evaluation set never used to develop anything; 300 questions (10 CUAD
categories x 30 contracts) asked as `grp-legal`, scoped to the contract. `gpt-5.4-mini-eval`, reranking off.

| Run | Arm | Found | Missed | Grounded | Absent correct | False claims | Abstain | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|
| Boundaries off | Workflow | 94% | 10 | 93% | 80% | 27 | 6 | 4,395 | 1.9 | 2.7 |
| Boundaries off | Agent | 96% | 7 | 95% | 79% | 29 | 5 | 8,603 | 3.0 | 6.3 |
| Boundaries on (cuad-v2) | Workflow | 94% | 9 | 93% | 78% | 29 | 7 | 4,415 | 1.9 | 2.7 |
| Boundaries on (cuad-v2) | Agent | 93% | 11 | 97% | 77% | 31 | 5 | 8,171 | 3.0 | 5.4 |

Paired workflow vs agent: 22 / 24 (boundaries off) and 24 / 22 (on); p = 0.88 both times.
Entitlement probes (boundaries off run): 0 leaks, 10 refusals exercised.

**Decisions:** the workflow stays the default (ADR-0027); `cuad-v2` rejected (ADR-0028).
**Largest remaining error in both modes:** false claims, ~27 to 31 of 300.

Files: `agent-compare-rest30-20261116-180632.json` (off), the following `agent-compare-rest30-*.json` (on).
