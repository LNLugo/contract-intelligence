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

### 2026-11-07 · Phase 2 · Tier upgrade and evaluation set selected
**Did:** Moved `di-ci-dev-2416` from F0 to S0 (`infra/02b-document-intelligence-s0.ps1`); keys still disabled after the change. Ran `eval/select_eval_set.py` to pick the fixed evaluation set.
**Result:** 50 contracts, 1,526 pages, $15.26 projected extraction cost, 27 contract types. Typical 30 (335 pages, 26 types), long 15 (607 pages), very long 5 (584 pages). Written to `eval/eval_set.csv`.
**Learned:** A tier change on Cognitive Services keeps the identity settings (custom subdomain, keys disabled); worth verifying after every change rather than assuming.
**Decision impact:** ADR-0015 evidence complete. Opened ADR-0016 (search tier and vector size).
**Spend so far:** $0 (no pages analyzed yet)

### 2026-11-08 · Phase 4 · Index creation failed on a valid name
**Broke:** `PUT /indexes/...` returned `InvalidName` although the configured name `contracts-v1` is valid.
**First thought:** a naming rule I had missed.
**Actual cause:** PowerShell variable names are case-insensitive. `config.ps1` defines `$INDEX` (the name); the script then built the index definition in `$index`, which overwrote the name with a hashtable. The URL was sent as `/indexes/System.Collections.Hashtable`.
**Fix:** renamed the definition to `$indexDef`; checked every script for other names that collide with `config.ps1` ignoring case.
**Learned:** In PowerShell, shared config variables and local variables live in one case-insensitive namespace. Read the request actually sent, not the variable you think you sent.

### 2026-11-08 · Phase 4 · Search index live, security trimming proven
**Did:** Ran `infra/04-search.ps1` after the variable fix: index `contracts-v1` created, 3 synthetic chunks embedded at 1,024 dimensions, uploaded with two security groups, queried, deleted.
**Result:** Query "cap on damages" as `grp-legal` returned the liability clause first (neither word is in it). The same query as `grp-procurement` returned only the procurement chunk: the legal chunks never came back. Semantic ranker available on Free. 1 of 3 indexes used.
**Broke:** One run failed with `DeploymentNotFound` on the embedding call although both deployments were `Succeeded`. An isolated test of the same call (single, 1,024 dimensions, batch) passed three times, and the re-run passed. Transient.
**Learned:** (1) Model endpoints return short-lived 404s, not only 429s; the phase 5 Function needs retry with backoff on 404, 429 and 5xx from the start. (2) RRF fused scores are rank-based and tiny (0.0167 vs 0.0164), so they are not a confidence signal; abstention needs reranker or evaluator scores. (3) `servicestats` reported the vector index quota as 0 MB on Free; to verify against real usage in phase 5.
**Decision impact:** ADR-0006 first stage Accepted; semantic ranker added as a no-cost comparison option. ADR-0013 trimming has its first evidence.
**Spend so far:** $0

### 2026-11-08 · Phase 5a · Pipeline library, first contract end to end
**Goal:** One code path for ingestion (ADR-0017), proven on a single contract before paying for 49 more.
**Did:** Built `ingestion/pipeline` (extract with cache, clean, chunk, embed, push), `batch_ingest.py`, 8 unit tests for cleaning and chunking. Regenerated `eval/eval_set.csv` on the laptop after the Cloud Shell copy was lost with the session.
**Result:** First contract (37 pages): 30 chunks, 23,410 embedding tokens, largest chunk 798 tokens against an 800 budget, 18.5 s, $0.37 extraction. Re-run: `cached`, $0.00, still 30 chunks (idempotent). Index 0.3 MB, which projects to about 12 MB for the full set (ADR-0016 estimated 17 MB). Chunk review: pages increase with overlap (1-2, 2-3, 3-5), real section headings, no page furniture or selection marks.
**Broke:** (1) `eval_set.csv` existed only in Cloud Shell and was lost; anything produced there must be brought back to the repo immediately. (2) The selector sorted paths differently on Windows (case-insensitive) and Linux, so the "deterministic" set was only deterministic per OS; fixed by sorting on relative POSIX paths. (3) A `<doc_id>` placeholder in my instructions was parsed by PowerShell as a redirection operator.
**Learned:** (1) Layout dropped a space in a heading (`ARTICLEI DEFINITIONS`); exact keyword match on "Article I" fails, which argues for query-time normalization (ADR-0011). (2) Contracts are self-referential: definitions live in one chunk, the clauses using them in others; top-5 retrieval can miss the definition a clause depends on. Candidate ADR for phase 8. (3) Cached runs still re-embed every chunk; negligible here, but at volume embeddings should be cached by chunk content hash.
**Decision impact:** ADR-0004 and ADR-0005 have working evidence. ADR-0017 accepted.
**Spend so far:** about $0.37 extraction, under $0.01 embeddings

### 2026-11-09 · Phase 5b · Evaluation set ingested; rate limits broke two contracts
**Did:** Ran `batch_ingest.py` over the 50-contract evaluation set with 3 workers.
**Result:** 48 OK, 2 failed. 1,460 pages (1,423 extracted in this run, 37 cached), $14.23 extraction ($14.60 total with the first test), 1,183 chunks, 911,551 embedding tokens (~770 per chunk), largest chunk 800. Wall time 25,735 s (7.1 hours) against an expected 10 to 15 minutes.
**Broke:** Both failures were HTTP 429 `RateLimitReached` on `text-embedding-3-large` after 6 retries. Each request carried 16 chunks (~13K tokens); 3 workers in flight exceeded the 50K TPM cap in one burst, and every worker backed off independently.
**First thought:** add more retries.
**Actual fix:** a design change. Capacity is now set per workload (ADR-0014 revision): chat stays at 50K TPM as the runaway guardrail, embeddings go to 200K TPM, and the client paces itself under the limit with a shared one-minute token budget. 429 gets 12 attempts.
**Learned:** (1) Retrying into a rate limit is not a strategy; pacing under it is. (2) Extraction ran before embedding, so the two failed contracts were already extracted and cached; their retry costs no extraction. Ordering the expensive, cacheable step first made the failure cheap. (3) Added `--skip-indexed` so retrying failures does not re-embed the 48 finished contracts.
**Decision impact:** ADR-0014 revised.
**Spend so far:** $14.60 extraction, about $0.12 embeddings

### 2026-11-09 · Phase 5b · Evaluation set complete
**Did:** Retried the 2 failed contracts with `--skip-indexed`.
**Result:** Both `cached` (no extraction), 55 chunks, 5.4 s. Index: **50 documents, 1,238 chunks, 14.1 MB of 50 MB.** Total extraction for the set: 1,526 pages, **$15.26**, matching the selector's projection to the cent.
**Learned:** The retry cost nothing because the expensive step (extraction) was cached before the step that failed (embedding). Order pipeline stages so the costly, cacheable work completes and persists first.
**Decision impact:** ADR-0016 size estimate replaced with the measurement. ADR-0015 cost projection confirmed.
**Spend so far:** $15.26 extraction, about $0.13 embeddings

### 2026-11-09 · Phase 5c · Function deployed; Event Grid wiring failed on CLI gaps
**Did:** Ran `infra/05c-function.ps1`: plumbing storage account, `ingest` and `ingest-poison` queues, Flex Consumption Function (Python 3.12) with Application Insights, managed identity roles, identity-based app settings, code deployed with remote build, shared keys disabled.
**Result:** `fn-ci-dev-2416/ingest` deployed. Event Grid topic created but without an identity; subscription not created.
**Broke:**
1. `Cannot find user or service principal in graph database` when checking roles for the new Function identity. A new managed identity takes time to replicate in Entra ID. The check failed; creating by object ID does not need the directory lookup.
2. My role helper printed `+ <role>` even when the assignment failed (empty principal ID for the topic). Misleading output is worse than none.
3. `az eventgrid system-topic event-subscription create` in Cloud Shell's CLI does not accept the identity-delivery options (`--delivery-identity`, `--deadletter-identity`), and the topic identity flags also failed.
**Fix:** The helper now refuses an empty principal and checks every result. The topic identity and the subscription are created through the Resource Manager API (`az rest`, Event Grid API 2022-06-15), and the script ends by reading every role assignment back from Azure. Added `-SkipDeploy` so a re-run does not redeploy unchanged code.
**Learned:** The CLI lags the platform; the ARM API is the source of truth and is what Bicep (phase 14) will declare. Verify by reading state back, not by trusting your own log lines.

### 2026-11-09 · Phase 5c · First live upload: wiring fine, message format wrong
**Did:** Uploaded a contract outside the evaluation set to `contracts-raw/inbox/`; it was not indexed within 10 minutes. Traced each hop: Event Grid metrics (3 published, 1 matched, 1 delivered, 0 failed), queues (`ingest` 0, `ingest-poison` 1), dead-letter container empty, then Function exceptions in Application Insights.
**Broke:** `json.loads(msg.get_body())` raised `JSONDecodeError` at character 0 on all 5 attempts; the message moved to `ingest-poison`.
**First thought:** I assumed Event Grid writes plain JSON to the queue and set `messageEncoding: none`.
**Actual cause:** the body arrived encoded (consistent with Base64), and the host passed it through as-is.
**Fix:** `pipeline/events.py` decodes either form, logs what arrived, unit-tested.
**Learned:** (1) Hop-by-hop observability (topic metrics, queue depth, dead letter, function exceptions) found the fault in one pass. (2) A permanent error retried 5 times is wasted work; classify permanent vs transient (ADR-0018 revision). (3) Cloud Shell's managed identity cannot get an Application Insights token; log queries run from the laptop.

### 2026-11-09 · Phase 5c · Event-driven ingestion live; fail-closed proven
**Test 1 (normal upload):** a contract outside the evaluation set uploaded to `contracts-raw/inbox/` with `allowed_groups=grp-legal` was **searchable 23 s after upload** (3 chunks; upper bound, polled every 10 s; includes a cold start after redeploy). Target in the architecture overview: 2 minutes.
**Test 2 (no access metadata):** the Function refused the upload on every attempt with `MissingAccessMetadata: ... has no allowed_groups metadata; refusing to index`; the message moved to `ingest-poison`; no chunks were indexed. Fail closed, as designed (ADR-0013, ADR-0018).
**Observed:** `ingest-poison` held 2 messages afterwards; to be traced (leftover from the decoding failure, or an at-least-once duplicate delivery).
**Added:** `eval/check_ingestion.ps1`, a one-command hop-by-hop health check: Event Grid metrics, queue contents with the file each message refers to, dead letter, function run counts with p50 and p95 duration, and distinct failure reasons.
**Decision impact:** ADR-0013 (trimming at ingestion), ADR-0017 (one code path) and ADR-0018 (queue) all have live evidence. Phase 5 complete.
**Spend so far:** about $15.30 extraction, under $0.20 embeddings; Function and Event Grid within free grants.

### 2026-11-09 · Slice 1 · First cited answers; retrieval baseline against lawyer labels
**Did:** Built the answering slice (ADR-0019): retrieval agent with an enforced, injection-checked access filter; generation with verbatim quotes; deterministic citation check (ADR-0020); code-based routing. Ran `eval/retrieval_eval.py`: 50 contracts × 10 CUAD categories, 500 queries.
**First answers:** "What law governs this agreement?" → ANSWERED, Delaware, 2 valid citations (pp. 30-31), 5.3 s, 4,248 tokens. "Can either party terminate for convenience?" → NOT_FOUND: the model read strong evidence and reported only termination for cause, which is the intended distinction between an absent clause and an abstention.
**Retrieval baseline** (`eval/results/baseline-slice1-retrieval.md`): reranked recall@5 95%, @1 75% (hybrid alone: 92%, 66%). By length @5: typical 99%, long 91%, very long 84%. Weakest: Exclusivity 79%, Non-Compete 80%. The reranker lowered Cap On Liability @5 from 92% to 86%.
**Broke:** the results JSON was not written (`eval/results` did not exist); fixed with `mkdir`. Printed figures saved by hand as the baseline, to avoid spending another 500 semantic-ranker queries from the free monthly 1,000.
**Learned:** (1) Recall drops with contract length; the stratified sample (ADR-0015) is what exposed it. (2) The reranker is not uniformly better. (3) Reranker scores for present and absent clauses overlap almost completely (present median 2.30, absent 1.96, absent p90 2.35), so a score threshold cannot decide whether a clause exists; absence is decided by the model reading evidence (ADR-0009 revision).
**Next:** `eval/answer_eval.py` measures the answers themselves on 20 contracts: missed clauses, false claims, grounding against the labelled text.
**Spend so far:** about $15.30 extraction; tokens under $0.30; semantic ranker about 530 of 1,000 free queries this month.

### 2026-11-09 · Slice 1 · Answer baseline; the "false claims" were my output format
**Did:** Ran `eval/answer_eval.py`: 20 contracts × 10 categories, 200 questions (`eval/results/baseline-slice1-answers.md`).
**Result:** found 97% of present clauses (3 missed), 95% grounded on the lawyers' labelled text, 2 bad quotes dropped by the citation check, but only 70% of absent clauses reported correctly: 23 false claims, 8 in Termination For Convenience.
**First thought:** the model reads clauses too generously and needs an LLM judge.
**Actual cause (after reading the answers):** several "false claims" began "No." The model cited for-cause termination clauses to explain why the answer was no, and my routing read any valid citation as "the clause exists". The defect was the output contract, and the metric inherited it.
**Fix:** ADR-0021: explicit `determination` (present, absent, unclear) separate from evidence; code routes on it; four routing unit tests including this bug. Evaluation now caches retrieval and reuses it, so the fix is measured with retrieval held fixed and without spending more semantic-ranker quota.
**Learned:** read the errors before fixing them. The obvious fix (add an LLM judge) would have spent a model call per finding to patch a schema bug.
