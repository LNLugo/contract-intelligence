# ADR-0014: GlobalStandard deployments, with a model chosen per role

- **Status:** Accepted for deployment type; model roles to be confirmed by phase 12 measurements
- **Date:** 2026-11-07
- **Phase:** 3

## Context
Azure OpenAI deployment types differ in where prompts are processed. Standard processes in the resource's region; DataZoneStandard within a geographic zone; GlobalStandard in any Azure region (data at rest stays in the resource's region). For a contract system in a regulated client, processing location is usually the first security-review question.

Separately, the system makes several kinds of model calls with very different needs: classifying intent, generating cited findings, and judging whether a citation supports a finding.

## Evidence (2026-11-07)
`az cognitiveservices model list -l canadacentral`: `text-embedding-3-large` is offered as **GlobalStandard only**. The gpt-5.x chat models are GlobalStandard or provisioned; no regional Standard and no DataZoneStandard offered in this region.

## Options considered: deployment type
| Option | Gains | Costs |
|---|---|---|
| Regional Standard | Processing stays in Canada Central | Not offered for these models in this region |
| Provisioned (PTU) | Reserved throughput, predictable latency | Priced for production workloads; far beyond the credit |
| GlobalStandard | Available, large quota, pay per token | Prompts may be processed outside Canada |

## Decision: deployment type
GlobalStandard for every deployment, with low capacity settings (TPM) on purpose as a guardrail: a runaway agent loop hits a rate limit before it burns the credit.

Acceptable here because the corpus is public CUAD contracts.

## Decision: model per role (proposed)
| Role | Model | Why |
|---|---|---|
| Embeddings | `text-embedding-3-large` | Strongest retrieval; dimensions reduced if index size requires (see ADR-0006 and phase 4) |
| Intent classification | `gpt-5.4-nano` | High-volume, simple task; cheapest and fastest |
| Generation (cited findings) | `gpt-5.4-mini` | The quality-critical call; mid-tier cost |
| Citation judge | `gpt-4.1` | Different model family from the generator, so the judge does not share the generator's blind spots |

## Revision 2026-11-09: capacity per workload, not one guardrail for all
**Evidence:** the 50-contract batch (911,551 embedding tokens, 3 workers, 16 chunks per request) failed 2 of 50 contracts with HTTP 429 after 6 retries, and took 7.1 hours of wall time. A single request was about 13K tokens; three in flight exceed a 50K-per-minute cap in one burst.

**Decision:** the 50K TPM guardrail was right for the wrong deployment. It protects against a runaway agent loop, which is a risk for the chat model, not for a bounded batch job.
- `gpt-5.4-mini` stays at 50K TPM (runaway guardrail).
- `text-embedding-3-large` raised to 200K TPM (`infra/03b-embedding-capacity.ps1`). Capacity on GlobalStandard is a rate limit, not a reservation, so this costs nothing by itself.
- The client paces itself under the limit: a shared one-minute token budget at 180K (`EMBED_TPM`), so parallel workers slow down together instead of all hitting 429 and backing off at random.
- 429 gets 12 attempts; other transient errors keep 6. A rate limit means "later", not "broken".

**Interview angle:** "My first guardrail was one number for every deployment, and it broke my batch: two contracts failed on 429s. The fix was to set limits per workload: keep the tight cap on the chat model, where a runaway loop is the risk, raise it on embeddings, and pace the client under the limit instead of retrying into it."

## Enterprise vs this build
In a regulated client with residency requirements, GlobalStandard would be rejected. The choices would be a region that offers regional Standard or DataZoneStandard for the needed models, or provisioned throughput. Model availability per deployment type then becomes a region selection criterion, which is the same test run here.

## Revisit when
- Real or sensitive documents enter the corpus.
- Phase 12 shows `gpt-5.4-mini` findings are not good enough, or `gpt-5.4-nano` misclassifies intent.
- Judge agreement with hand labels is low (ADR-0012).

## Interview angle
"In my region the embedding model was only offered as GlobalStandard, which means prompts can be processed outside the region. That was fine for public contracts, but for a regulated client I'd select the region by which deployment types it offers. I also split models by role, a nano model for intent, a mini for generation and a different family as the judge, so the judge doesn't share the generator's blind spots."
