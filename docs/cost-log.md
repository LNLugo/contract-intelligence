# Cost log

Budget: $100 Azure for Students credit (hard cap). Check actual spend on the subscription's **Overview** page in the portal ("Spending rate and forecast", "Costs by resource"). The CLI's usage API returns usage without prices on this subscription (0 of 292 records priced), and Azure for Students is not shown on the Sponsorships portal.

## Rules
1. Anything billed hourly whether used or not (AI Search paid tiers, APIM Developer, Postgres) is created only in the step that needs it and deleted or stopped when the session ends.
2. Free tiers first: AI Search Free, semantic ranker free plan, Functions and Event Grid free grants.
3. Record actual spend, not estimates, at the end of each step.

## Spend to date (2026-11-25): $30.59, actual (portal)

Forecast for the month: $37.68. Remaining credit: about $69.

| Resource | Cost | Mostly from |
|---|---|---|
| Azure OpenAI `aoai-ci-dev-2416` | **$18.11** | Evaluation runs on 2026-11-16: agent vs workflow, A/A, error review, held-out and final test sets (over 1,500 answered questions; the agent uses about 8K tokens a question, the workflow about 4.4K) |
| Document Intelligence `di-ci-dev-2416` | **$10.30** | One-time extraction of the evaluation set (1,530 pages), cached, never re-extracted. The first 500 pages a month are free on this subscription, so 1,030 pages were billed at $0.01: $10.30, against $15.26 projected without the free pages. The only free limit exceeded (on 2026-11-08, the batch run), by design |
| Container Registry `acrcidev2416` | **$2.09** | The only fixed cost (Basic tier, billed daily) |
| Everything else | $0.10 | Search Free tier, Functions, Event Grid, API Management Consumption, Container Apps scaled to zero, Key Vault, storage, logs |
| PostgreSQL `pg-ci-dev-2416` | $0 | Within the free allowance: 61 of 750 Burstable B1ms hours, 16 of 32 GB-months of storage this month. 750 hours covers a server running all month, so stopping it saved free hours, not money; it matters once the free year ends (2027-09-28) |

Free allowances for 12 months, until 2027-09-28 (subscription Overview, "View all free services"): only Document Intelligence went over.

**Decision (2026-11-25): PostgreSQL stays running.** Azure restarts a stopped Flexible Server after 7 days, and 750 free hours cover a full month, so stopping it saved nothing. Decide by 2027-08-28, a month before the free year ends: back up with `pg_dump` and delete it (the API reads the exported taxonomy snapshot, not the database), or pay for it.

**Lesson:** the most expensive thing in this project is evaluation, not serving or infrastructure. A model that takes several turns (the agent) roughly doubles evaluation cost, which is one more reason the cheaper workflow stays default.

## Spend at 2026-11-09 (estimate): about $16

| Item | Basis | Cost |
|---|---|---|
| Document Intelligence (S0, prebuilt-layout) | 1,526 pages for the evaluation set + 37-page test + 2 small live uploads | **$15.26** for the evaluation set, matching the projection; tests a few cents |
| Embeddings (`text-embedding-3-large`) | ~950K tokens for ingestion, plus re-embeds and query embeddings | under $0.20 |
| Chat (`gpt-5.4-mini`) | ~0.85M tokens for the answer evaluation and test questions | under $1 |
| AI Search | Free tier; semantic ranker free plan (about 730 of 1,000 queries used this month) | $0 |
| Functions, Event Grid, queues | Flex Consumption and Event Grid free grants | ~$0 |
| Storage (data lake + plumbing) | Low MB | cents |
| Application Insights | Ingestion well under the free allowance | ~$0 |

## Services

| Service | Tier | Billing shape | Created | Status |
|---|---|---|---|---|
| Storage `stcidev2416` (ADLS Gen2) | Standard LRS | Per GB and per operation | 2026-11-07 | Running |
| Storage `stfncidev2416` (Function plumbing) | Standard LRS | Per GB and per operation | 2026-11-09 | Running |
| Document Intelligence `di-ci-dev-2416` | S0 | Per page analyzed | 2026-11-07 (F0), S0 2026-11-07 | Running, idle cost $0 |
| Azure OpenAI `aoai-ci-dev-2416` | GlobalStandard | Per token | 2026-11-07 | Running, idle cost $0 |
| AI Search `srch-ci-dev-2416` | Free | Free (deleted after long inactivity) | 2026-11-08 | Running |
| Function `fn-ci-dev-2416` | Flex Consumption | Per execution, free grant | 2026-11-09 | Running, scales to zero |
| Event Grid `egst-ci-dev-2416` | System topic | Per operation, free grant | 2026-11-09 | Running |
| Application Insights `fn-ci-dev-2416` | Pay as you go | Per GB ingested | 2026-11-09 | Running |
| PostgreSQL `pg-ci-dev-2416` | Burstable B1ms, 32 GB | **Hourly compute while running**, storage always | 2026-11-09 | Stop between sessions (`infra/06b`) |
| Key Vault `kv-ci-dev-2416` | Standard, RBAC mode | Per 10K operations | 2026-11-11 | Running, cents |
| API Management `apim-ci-dev-2416` | Consumption | Per call; first 1M calls/month free | 2026-11-11 | Running, scales to zero |
| Mock SAP `fn-sapmock-2416` | Flex Consumption | Per execution, free grant | 2026-11-11 | Running, scales to zero |
| Chat deployment `gpt-5.4-mini-eval` | GlobalStandard 200K TPM | Per token (evaluation only) | 2026-11-16 | Running, no cost when unused |
| Container Registry `acrcidev2416` | Basic | **Fixed, billed daily** (about $5 a month) | 2026-11-12 | Running; the only fixed cost |
| Container Apps `ca-ci-api-2416` | Consumption (Express environment) | Per vCPU-second and request; scales to zero | 2026-11-12 | Running, scales to zero |
| Log Analytics `law-ci-dev-2416` | Pay as you go, 30-day retention | Per GB ingested | 2026-11-12 | Running, well under free allowance |
| Managed identities (3) | User-assigned | Free | 2026-11-12 | Pull, runtime, GitHub OIDC |

## Unit economics (from the answer baseline)

| Item | Per unit |
|---|---|
| Extraction | $0.01 per page; median contract (11 pages) $0.11 |
| Answering | ~4,100 tokens per question; 10 questions per contract ≈ 41K tokens |
| Ingestion latency | 23 s upload to searchable (short contract) |
