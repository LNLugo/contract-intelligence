# Baseline: slice 1 answers (2026-11-09)

Run: `eval/answer_eval.py`, 20 contracts (12 typical, 6 long, 2 very long) × 10 CUAD categories = 200 questions
(117 clauses present, 83 absent). Model `gpt-5.4-mini`, top 5 reranked chunks, deterministic citation check.
Output format: `found` + findings; routing "has valid findings → ANSWERED" (superseded by ADR-0021).

| category | present | absent | found | missed | grounded | absent ok | false claims | abstain |
|---|---|---|---|---|---|---|---|---|
| Governing Law | 19 | 1 | 100% | 0 | 100% | 100% | 0 | 1 |
| Termination For Convenience | 7 | 13 | 100% | 0 | 100% | 38% | 8 | 0 |
| Cap On Liability | 13 | 7 | 92% | 1 | 83% | 71% | 2 | 0 |
| Anti-Assignment | 18 | 2 | 100% | 0 | 100% | 100% | 0 | 0 |
| Exclusivity | 9 | 11 | 89% | 1 | 88% | 73% | 3 | 0 |
| Non-Compete | 8 | 12 | 100% | 0 | 75% | 64% | 4 | 1 |
| Audit Rights | 14 | 6 | 93% | 1 | 100% | 100% | 0 | 1 |
| Insurance | 8 | 12 | 100% | 0 | 100% | 91% | 1 | 1 |
| Renewal Term | 7 | 13 | 100% | 0 | 100% | 70% | 3 | 3 |
| License Grant | 14 | 6 | 100% | 0 | 93% | 67% | 2 | 0 |
| **ALL** | **117** | **83** | **97%** | **3** | **95%** | **70%** | **23** | **7** |

Latency p50 2.5 s, p95 32.8 s (chat deployment 50K TPM guardrail pacing three parallel workers). Mean 4,089 tokens per question. 2 findings dropped by the citation check. 0 errors. Detection by length: typical 95% (3 missed), long 100%, very long 100%.

## Error analysis
- **False claims (23):** mostly an output-format defect, not wrong conclusions. In Termination For Convenience, answers began "No." or said there was no general no-cause right, but cited the for-cause clauses as explanation; routing treated valid citations as presence. Fixed by ADR-0021.
- **Missed (3):** definition boundaries. Exclusivity: the model did not count an exclusive license as exclusivity. Cap On Liability: a damages exclusion was not counted as a cap. Audit Rights: to be checked (retrieval or definition). Target of the category-definitions step (ADR-0011).
- **Abstained on a present clause (1):** Governing Law, every citation failed validation. A safe failure: no unverified claim reached the reviewer.
- **Caveat:** CUAD labels contain some errors; a share of "false claims" may be label noise. Report both the metric and the reviewed cases.
