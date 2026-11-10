# Noise floor: the same prompt run twice (2026-11-09)

`v3-neutral` run twice on the same 200 questions with identical cached retrieval. Any difference is the model's own run-to-run variance.

| | run 1 | run 2 (repeat) | difference |
|---|---|---|---|
| Missed | 10 | 11 | 1 |
| False claims | 15 | 14 | 1 |
| Found | 91% | 90% | 1 point |
| Absent reported correctly | 80% | 81% | 1 point |
| Grounded | 96% | 98% | 2 points |
| Abstain | 9 | 13 | 4 |

Per category, identical runs differ by 1 to 2 (Cap On Liability missed 2 → 3; License Grant false claims 3 → 4; Termination For Convenience false claims 2 → 3).

## How earlier comparisons hold up
- Baseline → v3, missed 3 → 10 (+7) and false claims 23 → 15 (−8): far beyond a ±1 noise floor. Real.
- v2-strict → v3, missed 12 → 10: within noise. The strictness rule had no measurable effect.
- Single-category differences of 1 to 2 are not evidence. Abstention counts move by 4 between identical runs and are not comparable on their own.

## Method change
From here, runs are compared question by question with `eval/compare_runs.py`: flip rate, detections gained and lost, false claims fixed and introduced, each with an exact McNemar test on the paired outcomes, and the list of flipped questions to read.
