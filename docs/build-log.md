# Build log

One entry per working session. The entries where something broke are the most valuable ones: they become interview stories.

## Entry format

```
### YYYY-MM-DD · Phase N · Short title
**Goal:**
**Did:**
**Broke:** exact error, what I first thought it was, what it actually was
**Learned:**
**Decision impact:** ADR touched, if any
**Spend so far:** $
```

---

### 2026-11-07 · Phase 0 · Scope and constraints
**Goal:** Turn the reference architecture into a build plan that fits an Azure for Students subscription.
**Did:** Wrote ADRs 0001 to 0013. Identified the subscription constraints: $100 credit, hard cap, allowed-regions policy, uncertain Azure OpenAI access.
**Broke:** Nothing yet.
**Learned:** The subscription constrains the region before any architecture choice does; region is now an input to the design, not a default.
**Decision impact:** ADR-0003 opened as Proposed.
**Spend so far:** $0

### 2026-11-07 · Phase 0 · Region and model quota test
**Goal:** Prove the subscription can host the models before designing around them.
**Did:** Read the allowed-regions policy (5 regions), intersected with Azure OpenAI regions (Canada Central, France Central), created `rg-ci-dev` and `aoai-ci-dev-2416` in Canada Central, listed quota and models.
**Broke:** Nothing, but found two constraints: one OpenAI account per region on this subscription, and models offered as GlobalStandard only in this region.
**Learned:** A cloud service list is not one list. The policy, the service and the deployment type each narrow the region choice separately.
**Decision impact:** ADR-0003 Accepted. ADR-0014 created.
**Spend so far:** $0

### 2026-11-07 · Phase 3 · Model deployments, keyless
**Goal:** Deploy the embedding and generation models and call them with an Entra token, with API keys disabled.
**Did:** Deployed `text-embedding-3-large` and `gpt-5.4-mini` (GlobalStandard, 50K TPM each), set the custom subdomain, assigned `Cognitive Services OpenAI User` to myself, disabled local auth, ran `infra/03-models.ps1` from a fresh clone in Cloud Shell.
**Result:** Embedding returned 3072 dimensions. Chat answered in 49 tokens. Both calls used a bearer token; keys are off.
**Broke:** Cloud Shell was in bash, which cannot execute a `.ps1` directly ("Permission denied"). Fixed by running `pwsh ./infra/03-models.ps1`. A stale folder from an earlier session blocked `git clone`; deleted and re-cloned.
**Learned:** Entra token auth on Azure OpenAI needs a custom subdomain; key auth works without one, which is why teams drift back to keys. Script re-runs confirmed state without duplicating anything.
**Decision impact:** ADR-0013 and ADR-0014 now have working evidence. The 3072-dimension vector size feeds the phase 4 index-size decision.
**Spend so far:** $0 (49 tokens)

### 2026-11-07 · Phases 1 and 2 · Data lake and Document Intelligence, keyless
**Goal:** Storage that only accepts Entra identities, and a working extraction call using the async pattern the Function will use.
**Did:** Ran `infra/01-storage.ps1` (account already existed from an earlier manual run; script verified settings) and `infra/02-document-intelligence.ps1` (created `di-ci-dev-2416` on F0, assigned `Cognitive Services User`, disabled keys).
**Result:** Storage: shared key access false, hierarchical namespace true, write/list/delete with my identity OK. Document Intelligence: submit returned HTTP 202 with an operation URL; polling succeeded in 3 s; 1 page, 38 paragraphs, 2 tables, roles `title` and `sectionHeading` detected.
**Broke:** Cloud Shell home directory was empty in the new session (no storage mounted), so the repo had to be cloned again. Not a bug: it confirms nothing in Cloud Shell is durable and the repo is the only source of truth.
**Learned:** (1) `sectionHeading` roles mean clause-aware chunking has structure to split on (ADR-0005). (2) Selection marks come through as `:selected:` / `:unselected:` tokens; the chunker must strip them before embedding. (3) The free tier reads only 2 pages per document, which would silently drop most contract clauses.
**Decision impact:** ADR-0015 opened (Document Intelligence tier).
**Spend so far:** $0

### 2026-11-07 · Phase 2 · Measuring the corpus before choosing a tier
**Goal:** Replace a guess about contract length with a measurement, and use it to choose the Document Intelligence tier.
**Did:** Downloaded CUAD v1 (510 PDFs) into Cloud Shell, ran `eval/page_stats.py`.
**Result:** 9,348 pages; median 11 per contract, p90 46, max 154. The free tier would read 11% of pages. Full extraction $93.48; 50 median-length contracts $5.40.
**Broke:** First run failed with "No such file" because the script had not been pushed and pulled yet. Same root cause as before: the repo is the only path from laptop to Cloud Shell.
**Learned:** My own first proposal (50 median-length contracts) was the wrong sample: it would have excluded the long contracts where context overflow and missed clauses occur, making the evaluation look better than reality. A cheap sample is not a valid sample.
**Decision impact:** ADR-0015 Accepted: S0, stratified 50-contract evaluation set, about $15.50, extracted once.
**Spend so far:** $0
