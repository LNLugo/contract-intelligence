# Agent vs workflow (ADR-0027)

Same 10 contracts (6 typical, 3 long, 1 very long), same 100 CUAD questions, same retrieval settings
(hybrid search, semantic reranking off for both), same model (`gpt-5.4-mini`, evaluation deployment
`gpt-5.4-mini-eval`, 200K TPM). Questions asked as `grp-legal`, scoped to the contract.
Run: `eval/results/agent-vs-workflow-20261116-123423.json`, 2026-11-16.

| | found | missed | grounded | absent correct | false claims | abstain | tokens / question | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|
| Workflow (code decides steps) | 84% | 9 | 98% | 81% | 8 | 2 | 4,288 | 2.3 | 3.3 |
| Agent (model decides steps) | 91% | 5 | 94% | 86% | 6 | 0 | 7,912 | 3.1 | 4.8 |

**Agent behaviour:** 2.3 model turns and 1.3 searches per question on average; never called the vendor
tool on a clause question; never hit the step limit; no refused tool calls on legitimate questions.

**Paired:** outcomes differ on 16 of 100 questions (identical workflow runs differ on about 9%).
Correct only with the agent: 12; only with the workflow: 4. Exact McNemar p = 0.077.

**Entitlement probes:** `grp-procurement` asked about 10 legal-only contracts (clause question and
vendor question each): **0 leaks**. The agent tried the vendor tool 10 times on contracts it could not
see; the tool refused all 10.

## Against the decision rule (ADR-0027)
| Gate | Result | |
|---|---|---|
| Zero leaks | 0 leaks, 10 refusals exercised | Pass |
| False claims not higher | 6 vs 8 | Pass |
| Missed clauses not higher beyond noise | 5 vs 9 | Pass |
| Grounding not worse | 94% vs 98% | **Not met** (small, needs the cases checked) |
| Cost and latency acceptable | 1.8x tokens; p50 3.1 s vs 2.3 s | Pass for a review tool |

**Verdict: promising, not proven.** The agent found more clauses and made fewer false claims, but
p = 0.077 on 100 questions is not significant, and grounding on the lawyers' labels was slightly lower.
The workflow stays the default; the agent stays opt-in.

## What the latency taught
On the 20-question check with 3 parallel workers on the app's 50K TPM deployment, the agent's median
was 33 s. On its own 200K TPM evaluation deployment: 3.1 s. Most of the "agent is slow" result was
rate limiting: the agent resends a growing conversation each turn (about 8K tokens per question).
Capacity per workload is an architecture decision, not a tuning detail (ADR-0014).

## Next, before deciding
1. **Agent A/A test:** run the agent twice on the same questions to measure its own noise floor.
2. **More questions:** the remaining 10 contracts of the 20-contract set (200 questions in total).
3. **Read the grounding misses:** answered correctly but the validated quote is not the labelled text.
   Is the agent citing weaker evidence, or other valid text the labels do not mark?
