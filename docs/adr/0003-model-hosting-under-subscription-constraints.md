# ADR-0003: Host the models on the student subscription, in Canada Central

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0 and 3

## Context
The build runs on an Azure for Students subscription: $100 credit, a hard spending cap, and an "Allowed resource deployment regions" policy. Azure OpenAI / Foundry access on these subscriptions is inconsistent: some are blocked by policy, others have zero model quota. Every downstream component needs an embedding model and a chat model, and every other service should sit in the same region to avoid cross-region latency and egress.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| A: Everything on the student subscription | One subscription, one bill, simplest identity setup | Only possible if an allowed region also offers the models and quota |
| B: Separate pay-as-you-go subscription for the model resource only | Unblocks models; token cost stays small | Cross-subscription role assignments; no hard spending cap |
| C: Call a model provider's API directly, outside Azure | No Azure quota dependency | Loses managed identity, Azure networking and content filtering; defeats the purpose |

## Decision
Option A. All resources go in **Canada Central**, in resource group `rg-ci-dev`.

## Evidence (2026-11-07, Cloud Shell)
- Allowed regions policy: `canadacentral`, `denmarkeast`, `francecentral`, `mexicocentral`, `belgiumcentral`.
- Regions offering Azure OpenAI that are also allowed: Canada Central and France Central. Canada Central chosen for lower latency from the US East Coast.
- `az cognitiveservices account create --kind OpenAI --sku S0` in Canada Central: **Succeeded** (`aoai-ci-dev-2416`).
- Quota is non-zero: `text-embedding-3-large` GlobalStandard 1000, `gpt-5.4-mini` GlobalStandard 1000, `gpt-5.4-nano` GlobalStandard 5000, `gpt-4.1` available.
- `OpenAI.S0.AccountCount` is 1 of 1: **only one OpenAI account per region on this subscription.** Every model deployment for this project goes in this one resource; deleting and recreating it is the only way to replace it.

## Consequences
- No cross-subscription identity work needed.
- Deployment type is constrained by what the region offers; see ADR-0014.
- Option B remains the fallback if the student subscription expires mid-build.

## Revisit when
The student subscription renews (allowed regions can change) or the credit runs low.

## Interview angle
"Before designing anything, I tested the platform constraints: the subscription policy allowed five regions, only two of them offered the models, and the subscription allowed one OpenAI account per region. Region became a design input, not a default."
