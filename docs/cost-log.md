# Cost log

Budget: $100 Azure for Students credit (hard cap). Check the balance on the Microsoft Azure Sponsorships portal after each phase.

## Rules
1. Anything billed hourly whether used or not (AI Search paid tiers, APIM Developer, Postgres) is created only in the step that needs it and deleted or stopped when the session ends.
2. Free tiers first: AI Search Free, semantic ranker free plan, Functions and Event Grid free grants.
3. Record actual spend, not estimates, at the end of each step.

## Spend to date (2026-11-09): about $16

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
| Chat deployment `gpt-5.4-mini-eval` | GlobalStandard 200K TPM | Per token (evaluation only) | script ready (`infra/03c`) | Not yet created |

## Unit economics (from the answer baseline)

| Item | Per unit |
|---|---|
| Extraction | $0.01 per page; median contract (11 pages) $0.11 |
| Answering | ~4,100 tokens per question; 10 questions per contract ≈ 41K tokens |
| Ingestion latency | 23 s upload to searchable (short contract) |
