# ADR-0026: LangGraph orchestrator behind the API, with tools bound to the caller

- **Status:** Accepted
- **Date:** 2026-11-13
- **Phase:** Orchestration
- **Builds on:** ADR-0007 (LangGraph), ADR-0010 (typed system-of-record tool), ADR-0011 (governed taxonomy), ADR-0023/0024 (entitlements from the token)

## Context
The pieces exist separately: cited answers (Slice 1), the approved taxonomy in PostgreSQL, and the vendor tool behind API Management. They now run behind the deployed API for a signed-in user. Two risks matter most in a bank:
- **Confused deputy:** a tool runs with the application's identity, which can see more than the user. The vendor tool can look up any vendor; a user must not get vendor data for a contract they cannot see.
- **Silent degradation:** if the vendor system is down, the answer must say so, not guess.

## Decision
1. **A small LangGraph state graph:** `plan → answer → (vendor if needed) → compose`. Which steps run is decided by code (intent rules, presence of a contract ID), not by the model. The model only writes the cited clause answer. Every path is unit-testable.
2. **Tools are built per request from the validated caller** (`tools_for(caller.groups)`) and close over the caller's groups. The graph state has no field for groups or roles, so nothing in the request can reach them (unit test checks the state schema).
3. **The vendor tool takes a contract ID, never a vendor ID.** It reads the contract's vendor ID from the index **with the caller's search filter**. If the caller cannot see the contract, there is no vendor ID to look up. "Not visible" and "does not exist" return the same `NOT_AVAILABLE`, so the response reveals neither.
4. **Vendor outcomes are explicit:** `OK`, `NOT_FOUND` (a fact), `NOT_AVAILABLE` (not your contract), `NEEDS_CONTRACT` (vendor checks are per contract), `ABSTAIN` (system of record unavailable: vendor-dependent findings withheld, clause answer still returned, overall status `PARTIAL`).
5. **Taxonomy from an approved snapshot, not a live database connection.** Approval stays in PostgreSQL (ADR-0011). `taxonomy/export_snapshot.py` publishes the approved version as a committed JSON file with a content hash; the image includes it; every answer reports the taxonomy version it used. The deployed API has no database credentials or network path to PostgreSQL. Updating the taxonomy is approve → export → commit → build: reviewed and auditable like code.
6. **Least privilege for the vendor tool:** the API's runtime identity can read **one** Key Vault secret (the API Management subscription key), scoped at the secret, not the vault.
7. **Audit log:** caller, groups, contract filter, clause status, vendor status, category, taxonomy version, number of cited files. No question or answer text.

## Consequences
- The API stays stateless and has no database dependency at request time; taxonomy changes need a rebuild (minutes), which suits a governed list that changes rarely.
- Deterministic routing means the graph cannot decide on its own to call a new tool. Adding a tool is a code change with a test, which is what a model risk reviewer wants to see.
- Vendor checks need a contract ID. Portfolio-wide vendor questions ("which vendors are blocked?") are out of scope until there is an entitlement-aware way to enumerate them.
- Semantic reranking has a monthly quota on the Free search tier. `RERANK=false` turns it off; then the retrieval-relevance floor does not apply and abstention relies on the model's determination.

## Alternatives considered
- **Let the model choose tools (function calling):** flexible, but the model could call the vendor tool with any ID it reads or invents; entitlement would depend on the prompt. Rejected for now; when added, tools stay bound to the caller and validate their inputs exactly as here.
- **Pass groups through the graph state:** simplest, but any node or future tool could change them. Rejected.
- **Connect the API to PostgreSQL:** needs the firewall opened to Azure-wide IPs (rejected in ADR-0011) or private networking (later phase).
- **Store the taxonomy in Key Vault or Blob Storage:** another runtime dependency and another role, with no review step. The committed snapshot is reviewed in a pull request and pinned to the image.

## In an interview (20 seconds)
"Tools are built per request from the validated token and close over the user's groups; the graph state has nowhere to put groups. The vendor tool takes a contract ID and looks up the vendor through search with the user's filter, so it can't act on a contract the user can't see. If the system of record is down, the vendor part abstains and says why, and the clause answer still comes back."
