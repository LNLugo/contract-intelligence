# Run: determination field + strictness rule (prompt `v2-strict`), 2026-11-09

Same 200 questions and the same cached retrieval as the baseline; only the answering step changed.

| category | present | absent | found | missed | grounded | absent ok | false claims | abstain |
|---|---|---|---|---|---|---|---|---|
| Governing Law | 19 | 1 | 100% | 0 | 100% | n/a | 0 | 1 |
| Termination For Convenience | 7 | 13 | 100% | 0 | 100% | 85% | 2 | 0 |
| Cap On Liability | 13 | 7 | 69% | 4 | 89% | 86% | 1 | 0 |
| Anti-Assignment | 18 | 2 | 89% | 2 | 100% | 100% | 0 | 0 |
| Exclusivity | 9 | 11 | 67% | 3 | 100% | 91% | 1 | 0 |
| Non-Compete | 8 | 12 | 88% | 1 | 71% | 64% | 4 | 1 |
| Audit Rights | 14 | 6 | 86% | 2 | 100% | 100% | 0 | 1 |
| Insurance | 8 | 12 | 100% | 0 | 100% | 100% | 0 | 1 |
| Renewal Term | 7 | 13 | 100% | 0 | 100% | 70% | 3 | 3 |
| License Grant | 14 | 6 | 100% | 0 | 93% | 17% | 5 | 0 |
| **ALL** | **117** | **83** | **90%** | **12** | **96%** | **79%** | **16** | **7** |

p50 2.7 s, p95 32.9 s; 4,247 tokens per question; 4 findings dropped by the citation check; 0 errors.
Detection by length: typical 84% (10 missed), long 100%, very long 87% (2 missed).

## Against the baseline
| | baseline | v2-strict |
|---|---|---|
| False claims | 23 | 16 |
| Absent reported correctly | 70% | 79% |
| **Missed clauses** | **3** | **12** |
| Found | 97% | 90% |

## Reading
- Termination For Convenience false claims fell from 8 to 2, as intended.
- Missed clauses quadrupled, concentrated in categories CUAD defines broadly: Cap On Liability (1 → 4), Exclusivity (1 → 3), Anti-Assignment (0 → 2), Audit Rights (1 → 2).
- **Experiment design flaw:** this run changed two things at once, the output format (determination field, code routing) and a prompt rule defining related provisions as "absent". The run cannot attribute the gain to one and the loss to the other. Next run (`v3-neutral`) keeps the format and removes the rule.
- **Verdict:** in contract review a false claim carries a citation a reviewer can reject in seconds; a missed clause is silent. Trading 7 fewer false claims for 9 more missed clauses is the wrong trade. `v2-strict` is not adopted as is.
