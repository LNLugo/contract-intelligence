# Contract Intelligence on Azure

A contract review system on Azure, measured against lawyer-labelled ground truth. It runs end to end on Azure today: it reads contracts, finds the clauses that matter, answers with verbatim citations checked in code, and says "not found" or abstains instead of guessing. Every request goes through an API that takes the user's groups only from a validated Entra ID token, and a LangGraph orchestrator (workflow by default, agent opt-in) works behind that API, so nothing runs without a verified user.

This is my own reconstruction of an enterprise architecture pattern, built on a $100 student subscription. Every tradeoff is an [architecture decision record](docs/adr/), every failure is in the [build log](docs/build-log.md), and every claim below is a measurement.

## Results so far

| | Measured | How |
|---|---|---|
| **Corpus** | 50 contracts, 1,526 pages, 1,238 chunks, 27 contract types | [CUAD](docs/adr/0002-cuad-as-corpus-and-ground-truth.md), stratified by length ([ADR-0015](docs/adr/0015-document-intelligence-tier.md)) |
| **Extraction cost** | $15.26, matching the projection to the cent | Corpus measured before choosing a tier |
| **Upload to searchable** | 23 s (short contract) | Event Grid → queue → Function ([ADR-0018](docs/adr/0018-queue-between-event-grid-and-function.md)) |
| **Access control** | Upload without access groups refused and parked; search refuses to run without the caller's groups; leakage test (enumerate, targeted, adversarial, injection probes) must find 0 leaks | Tested live and in unit tests ([ADR-0013](docs/adr/0013-identity-and-security-trimming.md), [ADR-0023](docs/adr/0023-entitlements-from-validated-token.md), `eval/leakage_test.py`) |
| **System of record** | Reachable only through API Management; credentials resolved from Key Vault by managed identities; no secret in code or config | Live access tests ([ADR-0010](docs/adr/0010-system-of-record-as-typed-tool.md)) |
| **Retrieval** | Labelled clause in the top 5: **95%** (typical 99%, long 91%, very long 84%) | 500 queries vs CUAD labels ([baseline](eval/results/baseline-slice1-retrieval.md)) |
| **Answers** (current configuration: workflow) | On the final test set, 300 questions never used for development: clauses found **94%**; quote matches the lawyers' text **93%**; absent clauses reported correctly **80%**; fabricated quotes reaching a reviewer: **0** in every run. Strict quote check (exact, or fuzzy only for PDF noise with negations, modal verbs and numbers identical): on 100 questions it rejected 9 citations the old rule passed (elided, spliced, headings, a dropped qualifier) and changed **no** outcome | [Final test](eval/results/final-rest30.md); earlier 200-question runs: found 90 to 91% ([run](eval/results/run-v3-neutral.md)); [citation check](eval/results/citation-ab-first10.md) ([ADR-0029](docs/adr/0029-strict-citation-match-with-offsets.md)) |
| **Known weakness** | **False claims:** a clause the lawyers marked absent is reported as present on about 1 question in 11 (27 of 300 on the final test, about the same for the agent). Every quote is real; the conclusion drawn from it is wrong, so the citation check cannot catch it. Consistency is the second weakness: 9% of outcomes change between identical runs. Next: a support check (does the quote support the claim?), after reading a sample of false claims for label errors | [Final test](eval/results/final-rest30.md), [A/A tests](eval/results/noise-floor-v3.md), [ADR-0028](docs/adr/0028-category-boundaries-in-the-taxonomy.md) |
| **Spend to date** | **$30.59 of $100** (actual, 2026-11-25): Azure OpenAI $18.11, mostly evaluation runs; Document Intelligence $10.30, one-time extraction; Container Registry $2.09, the only fixed cost; everything else $0.10 | [Cost log](docs/cost-log.md) |

![Reference architecture](docs/architecture/reference-architecture.png)

## Architecture as built

The reference design above is what I set out to build. This is what exists and was measured, stage by stage: green is built and measured, amber is built differently or only in part, grey is not built. Each stage carries the number behind it and the decision it led to.

![Production RAG as built](docs/architecture/as-built.png)

Two places where the build deliberately differs from common reference designs: **authorization is enforced inside the search query, never after retrieval** ([ADR-0013](docs/adr/0013-identity-and-security-trimming.md), [ADR-0023](docs/adr/0023-entitlements-from-validated-token.md)), and **the default path is a workflow, not an agent**, because the agent tied it on the final test set at twice the cost ([ADR-0027](docs/adr/0027-first-agent-model-chooses-tools.md)).

## How it is secured

Nine layers, placed on the request path. For each one the drawing shows the controls in place, the test that proves it works, and what is still open. The rule behind all of them: **security is enforced by code at the edges, never by the prompt.** The model can be fooled; the token check, the search filter and the tools cannot, and every layer fails closed.

![How the system is secured](docs/architecture/security.png)

The open items are deliberate for a student subscription, not oversights. In a regulated tenant the first three to close would be private endpoints with a web application firewall, an immutable audit store with alerts on refusals, and permissions copied from the source document system instead of derived from contract type.

## What runs today

**Ingestion.** A PDF uploaded to the data lake's `inbox/` raises an Event Grid event, which is written to a storage queue and processed by a Flex Consumption Function: Document Intelligence layout extraction (cached), cleaning, paragraph-filled 800-token chunks with page numbers, 1,024-dimension embeddings, and a push to AI Search with access groups on every chunk. Failures retry, then park in a poison queue. No keys anywhere: every hop uses a managed identity.

**Answering (slice 1, [ADR-0019](docs/adr/0019-vertical-slice-before-components.md)).** Hybrid search (BM25 + vector, RRF) reranked by the semantic ranker, filtered by the caller's groups. The model returns a determination and verbatim quotes; code drops any finding whose quote is not in the clause it cites ([ADR-0020](docs/adr/0020-deterministic-citation-check-first.md)) and routes the result: answered, not found, or abstain. The check is exact after Unicode cleaning; a fuzzy match is allowed only for PDF noise and never when a negation, modal verb or number differs. Each citation carries character offsets into the clause for highlighting, and drop counts by reason go to the audit log ([ADR-0029](docs/adr/0029-strict-citation-match-with-offsets.md)).

```powershell
python -m agents.ask "What law governs this agreement?" --doc bdb7d1532a642920
# [ANSWERED]  Delaware ... [C1 valid] DigitalCinemaDestinations... p.30-31: "governed by the internal laws of the State of Delaware..."
```

## Lessons the measurements taught

- **A retrieval score cannot tell you a clause is missing.** Reranker scores for present and absent clauses overlap almost completely, so absence is judged by the model reading the evidence, not by a threshold ([ADR-0009](docs/adr/0009-deterministic-rules-and-abstention.md)).
- **Run the same thing twice before believing a difference.** Two identical runs changed 9% of answers, and one identical comparison even came out "statistically significant". That overturned two of my own earlier conclusions and exposed the real weakness: consistency ([A/A tests](eval/results/noise-floor-v3.md)).
- **Test your own hypotheses, including the flattering ones.** I suspected the first configuration's 97% was inflated by a bug; checking each answer showed it was real, and that strict wording had cost 8 correct detections ([analysis](eval/results/run-v3-neutral.md)).
- **Change one variable at a time, and weight errors by their cost.** Bundling a format fix with a prompt tweak cut false claims but quadrupled missed clauses, and the run could not say which change did which. A missed clause is silent; a false claim comes with a citation a reviewer can reject ([run](eval/results/run-v2-strict.md)).
- **Test the checker on the same answers, not on a new run.** Run-to-run noise (9%) would hide any checker effect. Judging the same 330 citations with both rules showed the old 90%-of-words fallback was mostly passing quotes the model had shortened or stitched together, not PDF noise ([result](eval/results/citation-ab-first10.md)).
- **Read the errors before fixing them.** The 23 "false claims" were mostly the model saying "No" and citing evidence for it, which my routing counted as "yes". The fix was the output contract, not an extra model call ([ADR-0021](docs/adr/0021-determination-separate-from-evidence.md)).
- **A cheap sample is not a valid sample.** A median-length evaluation set would have reported 99% retrieval and hidden the drop to 84% on very long contracts ([ADR-0015](docs/adr/0015-document-intelligence-tier.md)).
- **Pace under rate limits, do not retry into them.** One guardrail for every deployment broke the batch; limits are now set per workload ([ADR-0014](docs/adr/0014-model-deployment-type-and-model-roles.md)).
- **Measure the platform's limits before designing around them.** Event Grid waits 30 seconds; 31 of 48 contracts took longer, so a queue sits between them ([ADR-0018](docs/adr/0018-queue-between-event-grid-and-function.md)).

## Roadmap

| Step | Scope | Status |
|---|---|---|
| Foundation | Subscription constraints, data lake, Document Intelligence, models, search index | Done |
| Ingestion | Pipeline library, batch over evaluation set, event-driven Function, health check | Done |
| Slice 1 | Retrieval agent, cited answers, citation check, routing, retrieval and answer evaluation | Done |
| Azure services | PostgreSQL taxonomy (Entra-only auth, approval, managed-identity DB role); Key Vault + API Management + mock SAP with a typed, fail-closed vendor tool | Done |
| Entitlements | Leakage test with a zero-leak pass mark; rule that groups come only from the validated token ([ADR-0023](docs/adr/0023-entitlements-from-validated-token.md)) | Leakage test PASS (0 leaks, 260 probes); token check built ([ADR-0024](docs/adr/0024-identity-tenant-and-app-roles.md)) |
| **Identity first** | Separate identity tenant, app roles, test clients and users (`infra/08-identity.ps1`); API that validates the Entra ID token and maps roles to groups (`api/`); 22 unit tests; image built in GitHub Actions with OIDC (no stored secret), tests gate the build; deployed to Container Apps with separate pull and runtime identities ([ADR-0025](docs/adr/0025-api-on-container-apps.md)); smoke test with real tokens PASS against the deployed API | Done |
| **Orchestration** | LangGraph graph behind `/ask`: cited clause answer, taxonomy category from the approved snapshot, vendor check only for contracts the caller can see, abstain when the vendor system is down ([ADR-0026](docs/adr/0026-orchestrator-behind-the-api.md)); end-to-end check with real tokens PASS, including a live outage | Done |
| **Agent** | Model chooses its tools in a LangGraph loop; code keeps entitlements, search scope, citation checks and step limits; 0 leaks on every run. Led on the first 200 questions (p = 0.024), **tied on the final 300 (p = 0.88)** at 2x cost: opt-in, workflow stays default ([ADR-0027](docs/adr/0027-first-agent-model-chooses-tools.md), [final results](eval/results/final-rest30.md)) | Done |
| **Hardening** | Security drawing (nine layers, evidence, open items); database firewall closed; infra scripts refuse to run outside Cloud Shell; strict citation check with offsets and logged drops, measured on paired answers ([ADR-0029](docs/adr/0029-strict-citation-match-with-offsets.md)) | Done |
| **Next: false claims** | The largest error in both modes (~10% of questions). Category boundaries did not help ([ADR-0028](docs/adr/0028-category-boundaries-in-the-taxonomy.md), rejected). The strict citation check cannot catch them: every quote is real. Next: read a sample of final-set false claims for label errors, then a support check (does the quote support the claim?) | ⏭ Now |
| Then | **Monitoring:** alerts on abstain rate, citation drops, refused tool calls and tokens per question from the audit log (Application Insights); human corrections from the review app become new labelled examples | |
| Then | Second model (reviewer) only if the error analysis shows false claims or wrong passages; leakage test through the deployed API as a release gate in CI | |
| Then | Review app with Entra sign-in; review history carrying the source documents' access tags; private endpoints; Terraform for all infrastructure | |
| Parked, ready to run | Three-sample agreement ([ADR-0022](docs/adr/0022-agreement-across-samples.md)), definitions in prompts, LLM judge, reranker comparison | |

## How to read this repo

| If you want | Go to |
|---|---|
| Why each part is built the way it is | [`docs/adr/`](docs/adr/): one decision record per tradeoff, with the evidence |
| What broke and how it was diagnosed | [`docs/build-log.md`](docs/build-log.md) |
| The measured baselines | [`eval/results/`](eval/results/) |
| How the pieces connect | [`docs/architecture/overview.md`](docs/architecture/overview.md) |
| What it costs | [`docs/cost-log.md`](docs/cost-log.md) |

## Decision index

| ADR | Decision | Status |
|---|---|---|
| [0001](docs/adr/0001-public-first-harden-later.md) | Build on public endpoints with Entra auth, harden in a dedicated phase | Accepted |
| [0002](docs/adr/0002-cuad-as-corpus-and-ground-truth.md) | Use CUAD as the contract corpus and evaluation ground truth | Accepted |
| [0003](docs/adr/0003-model-hosting-under-subscription-constraints.md) | Host the models on the student subscription, in Canada Central | Accepted |
| [0004](docs/adr/0004-push-ingestion-over-indexer.md) | Event-driven push ingestion instead of an AI Search indexer | Accepted |
| [0005](docs/adr/0005-fixed-size-chunking-v1.md) | Paragraph-filled 800-token chunks in v1; clause-aware chunking as a measured experiment | Accepted |
| [0006](docs/adr/0006-hybrid-retrieval-and-reranking.md) | Hybrid retrieval with RRF, then rerank from top 20 to top 5 | First stage Accepted; reranker comparison pending |
| [0007](docs/adr/0007-langgraph-orchestration.md) | LangGraph for orchestration instead of a managed agent service | Accepted |
| [0008](docs/adr/0008-review-history-as-retrieval.md) | Review history retrieved from its own index, not appended to the prompt | Proposed |
| [0009](docs/adr/0009-deterministic-rules-and-abstention.md) | Rules and routing in code; a retrieval score cannot decide absence | Accepted, revised |
| [0010](docs/adr/0010-system-of-record-as-typed-tool.md) | Vendor system of record reached through APIM as a typed, read-only tool | Accepted |
| [0011](docs/adr/0011-clause-taxonomy-store.md) | Governed clause taxonomy in PostgreSQL, Entra-only auth, versioned draft → approved | Accepted |
| [0012](docs/adr/0012-evaluation-method.md) | Clause-level evaluation against labelled ground truth, with a calibrated LLM judge | Proposed |
| [0013](docs/adr/0013-identity-and-security-trimming.md) | Entra identities everywhere, no keys, results filtered by the user's groups | Accepted |
| [0014](docs/adr/0014-model-deployment-type-and-model-roles.md) | GlobalStandard deployments; capacity set per workload | Accepted, revised |
| [0015](docs/adr/0015-document-intelligence-tier.md) | Paid extraction tier, stratified 50-contract evaluation set extracted once | Accepted |
| [0016](docs/adr/0016-search-tier-and-vector-size.md) | AI Search Free tier, 1,024-dimension vectors, vectors not stored | Accepted |
| [0017](docs/adr/0017-pipeline-as-library.md) | Ingestion pipeline as a library with two thin callers | Accepted |
| [0018](docs/adr/0018-queue-between-event-grid-and-function.md) | Storage queue between Event Grid and the Function | Accepted, revised |
| [0019](docs/adr/0019-vertical-slice-before-components.md) | Thin answering slice end to end before the remaining components | Accepted |
| [0020](docs/adr/0020-deterministic-citation-check-first.md) | Deterministic citation check first; LLM judge only for entailment | Accepted; matching rule superseded by 0029 |
| [0021](docs/adr/0021-determination-separate-from-evidence.md) | Determination separate from cited evidence; code routes on it | Accepted (format); wording effects not established |
| [0022](docs/adr/0022-agreement-across-samples.md) | Three samples per question; answer only on agreement, otherwise route to a reviewer | Proposed |
| [0023](docs/adr/0023-entitlements-from-validated-token.md) | Entitlements come only from the validated token; leakage is a zero-tolerance regression test | Accepted |
| [0024](docs/adr/0024-identity-tenant-and-app-roles.md) | Separate identity tenant; app roles mapped to search groups; two gates (Entra, then the API) | Accepted |
| [0025](docs/adr/0025-api-on-container-apps.md) | API on Container Apps: managed identity, no registry password, read-only roles, scale to zero | Accepted |
| [0026](docs/adr/0026-orchestrator-behind-the-api.md) | LangGraph orchestrator behind the API; tools bound to the caller; vendor tool takes a contract ID; taxonomy from an approved snapshot | Accepted |
| [0027](docs/adr/0027-first-agent-model-chooses-tools.md) | First real agent: the model chooses tools; code keeps access, citations and limits. Tied with the workflow on the final test set at 2x cost: kept opt-in, workflow stays default | Not adopted as default |
| [0028](docs/adr/0028-category-boundaries-in-the-taxonomy.md) | Fix judgment errors with includes/excludes in the governed taxonomy; decided on held-out contracts. No improvement on the final test set; classifier fix kept | Rejected |
| [0029](docs/adr/0029-strict-citation-match-with-offsets.md) | Strict citation match: exact after cleaning, fuzzy only with negations, modals and numbers identical; offsets; drops logged by reason | Accepted |

**Proposed** means the decision waits for evidence from the step where it applies. An ADR moves to Accepted only with a measurement or a test result behind it.

## Repo layout

```
infra/       az CLI and ARM scripts, one per phase (Bicep in a later step)
ingestion/   pipeline library, batch script, queue-triggered Function, unit tests
agents/      retrieval agent, answering and routing, ask CLI, taxonomy lookup, typed system-of-record tool, unit tests
eval/        evaluation set, retrieval and answer evaluations, baselines in eval/results/
taxonomy/    governed clause taxonomy: schema, Entra-token connection, CUAD seed, approval, identity grants
sap-mock/    mock SAP vendor master (separate Function app behind API Management)
docs/        ADRs, architecture overview, build log, cost log, interview notes
```

## Run it

Requires Python 3.12, the Azure CLI signed in (`az login`), and the resources from `infra/`. Contracts are not in the repo: download [CUAD v1](https://zenodo.org/records/4595826) separately.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r ingestion\requirements-dev.txt
python -m pytest -q agents\tests ingestion\tests
python ingestion\batch_ingest.py --cuad-root <folder containing CUAD_v1> --limit 1
python -m agents.ask "What law governs this agreement?" --doc <doc_id>
python eval\answer_eval.py --cuad-root <folder containing CUAD_v1>
```
