# ADR-0020: Validate citations deterministically first; use an LLM judge only for what code cannot check

- **Status:** Accepted (LLM judge to be added later and measured against this baseline)
- **Date:** 2026-11-09
- **Phase:** Slice 1

## Context
The Citation Validator in the reference architecture checks that each finding is supported by the clause it cites. An LLM judge can assess support, but it adds a model call per finding, its own error rate, and its own cost. Part of the check needs no model at all: does the quoted text actually exist in the cited clause?

## Options considered
| Option | Gains | Costs |
|---|---|---|
| LLM judge for every citation | Can judge paraphrase and entailment | Extra call per finding; the judge can itself be wrong; harder to audit |
| **Require verbatim quotes, check them in code; add an LLM judge later for entailment only** | Free, instant, reproducible; catches fabricated or misattributed quotes with certainty | Does not check whether a real quote actually supports the statement drawn from it |
| No validation | Simplest | Unverifiable answers |

## Decision
The model must return 8 to 40 word verbatim quotes with a clause number. Code accepts a citation only if the quote appears in that clause (exact after normalization, or 90% of its words in order, tolerating typography). A finding with no valid citation is dropped; if every finding is dropped, the answer abstains. The LLM judge (different model family, ADR-0014) is added later to check entailment, and its value is measured against this baseline.

## Consequences
- A fabricated or misattributed quote can never reach the reviewer.
- Remaining risk, accepted for now: a real quote attached to an overstated statement. That is the judge's job.
- Unit tests cover exact, typographic and invented quotes.

## Interview angle
"I validate citations in code first: the model has to quote verbatim, and if the quote isn't in the clause it cites, the finding is dropped. That catches fabricated citations for free and with certainty. The LLM judge comes second, only for the question code can't answer: does a real quote actually support the claim."
