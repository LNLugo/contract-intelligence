# Contract Intelligence on Azure

A reference build of a multi-agent contract review system on Azure. It reads a contract, finds the clauses that matter, checks them against a vendor system of record, and returns findings that each cite their source clause. When the evidence is missing, contradictory or unavailable, it abstains and flags the finding instead of guessing.

This is a personal learning build on my own Azure subscription. It reconstructs an enterprise architecture pattern on a constrained budget, and it records every place where the constraints forced a different choice from the enterprise version.

![Reference architecture](docs/architecture/reference-architecture.png)

## How to read this repo

| If you want | Go to |
|---|---|
| Why each part is built the way it is | [`docs/adr/`](docs/adr/) — one architecture decision record per tradeoff |
| How the pieces connect | [`docs/architecture/overview.md`](docs/architecture/overview.md) |
| What broke and what I learned | [`docs/build-log.md`](docs/build-log.md) |
| What it costs to run | [`docs/cost-log.md`](docs/cost-log.md) |
| How decisions map to interview questions | [`docs/interview/talking-points.md`](docs/interview/talking-points.md) |

## Decision index

| ADR | Decision | Status |
|---|---|---|
| [0001](docs/adr/0001-public-first-harden-later.md) | Build on public endpoints with Entra auth, harden in a dedicated phase | Accepted |
| [0002](docs/adr/0002-cuad-as-corpus-and-ground-truth.md) | Use CUAD as the contract corpus and evaluation ground truth | Accepted |
| [0003](docs/adr/0003-model-hosting-under-subscription-constraints.md) | Host the models on the student subscription, in Canada Central | Accepted |
| [0004](docs/adr/0004-push-ingestion-over-indexer.md) | Event-driven push ingestion instead of an AI Search indexer | Accepted |
| [0005](docs/adr/0005-fixed-size-chunking-v1.md) | Fixed-size overlapping chunks in v1; clause-aware chunking as a measured experiment | Accepted |
| [0006](docs/adr/0006-hybrid-retrieval-and-reranking.md) | Hybrid retrieval with RRF, then a cross-encoder rerank from top 20 to top 5 | First stage Accepted; reranker pending |
| [0007](docs/adr/0007-langgraph-orchestration.md) | LangGraph for orchestration instead of a managed agent service | Accepted |
| [0008](docs/adr/0008-review-history-as-retrieval.md) | Review history retrieved from its own index, not appended to the prompt | Proposed |
| [0009](docs/adr/0009-deterministic-rules-and-abstention.md) | Business rules and risk routing run outside the LLM; abstain when evidence fails | Accepted |
| [0010](docs/adr/0010-system-of-record-as-typed-tool.md) | Vendor system of record reached through APIM as a typed, read-only tool | Accepted |
| [0011](docs/adr/0011-clause-taxonomy-store.md) | Where the governed clause taxonomy lives | Proposed |
| [0012](docs/adr/0012-evaluation-method.md) | Clause-level evaluation against labeled ground truth, with a calibrated LLM judge | Proposed |
| [0013](docs/adr/0013-identity-and-security-trimming.md) | Entra identities everywhere, no keys, results filtered by the user's groups | Accepted |
| [0014](docs/adr/0014-model-deployment-type-and-model-roles.md) | GlobalStandard deployments, with a model chosen per role | Accepted (roles pending measurement) |
| [0015](docs/adr/0015-document-intelligence-tier.md) | Paid Document Intelligence tier, stratified 50-contract evaluation set extracted once | Accepted |
| [0016](docs/adr/0016-search-tier-and-vector-size.md) | AI Search Free tier, 1024-dimension vectors, vectors not stored | Accepted |
| [0017](docs/adr/0017-pipeline-as-library.md) | Ingestion pipeline as a library with two thin callers (batch, Function) | Accepted |
| [0018](docs/adr/0018-queue-between-event-grid-and-function.md) | Storage queue between Event Grid and the Function (30-second delivery window) | Accepted |

**Proposed** means the decision waits for evidence from the phase where it applies. An ADR moves to Accepted only once there is a measurement or a test result behind it.

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Subscription constraints, resource group, tooling | Done |
| 1 | ADLS Gen2 storage | Done |
| 2 | Document Intelligence extraction | Done |
| 3 | Embedding and chat model deployments | Done |
| 4 | AI Search index | Done |
| 5 | Ingestion: 5a library ✅, 5b batch over eval set ✅ (50 contracts, 1,238 chunks), 5c Event Grid Function | In progress |
| 6 | Clause taxonomy | |
| 7 | Vendor system of record behind APIM | |
| 8 | Agents: orchestrator, intent, memory, policy, plan, retrieval | |
| 9 | Agents: generation, citation validator, evaluation, risk router | |
| 10 | Review history index | |
| 11 | API and review app on Container Apps, Entra sign-in | |
| 12 | Evaluation harness | |
| 13 | Hardening: private endpoints, Defender, diagnostics, delete sweep | |
| 14 | Infrastructure as code (Bicep) | |

## Repo layout

```
infra/       Bicep and az CLI scripts, one file per phase
ingestion/   Azure Function: Event Grid trigger, extraction, chunking, embedding, index push
agents/      LangGraph graph and agent nodes
api/         FastAPI service and review app
eval/        Evaluation harness and results
data/        Local contracts (git ignored)
docs/        ADRs, architecture, build log, cost log, interview notes
```
