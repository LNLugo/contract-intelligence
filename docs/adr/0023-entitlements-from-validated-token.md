# ADR-0023: Entitlements come only from the validated token, and leakage is a regression test

- **Status:** Accepted (test in place now; token validation lands with the API in Container Apps)
- **Date:** 2026-11-11
- **Phase:** Hardening, before the orchestrator and API
- **Builds on:** ADR-0013 (security trimming at query time, fail closed)

## Context
Security trimming works today: every chunk carries `allowed_groups`, every search applies a filter built from the caller's groups, and an empty or malformed group list is refused (ADR-0013). But in this build **the caller says which groups it has** (`python -m agents.ask --groups grp-legal`). The filter is only as trustworthy as the place the groups come from. A user who can choose their own groups can see everything.

Other ways a user can see what they are not entitled to, even with a correct filter:
1. **Wrong tags at ingestion.** The filter enforces the tags; it cannot know they are wrong. Here the tags are synthetic (`batch_ingest.access_for`), not copied from the source system.
2. **Stale tags.** Access changes in the source (a contract moves to a restricted matter) but the index keeps the old groups.
3. **Confused deputy.** Tools run as the agent's managed identity, which can read more than the user (the vendor tool can look up any vendor).
4. **Side channels.** Review history, logs and telemetry, cached retrieval results and evaluation artifacts can contain contract text outside the index's filter.
5. **Token limits.** Entra ID omits the `groups` claim when a user is in more than about 200 groups (overage), and a membership change takes up to about an hour to appear in new tokens.
6. **People with platform access.** Anyone with a data-plane role on Search, Storage or PostgreSQL bypasses the application.

## Decision
1. **Groups come from the validated token, never from the request.** The API (Container Apps) validates the Entra ID access token (signature, issuer, audience, expiry) and reads the groups from it. No request field, header, query string or prompt can set or widen them. The CLI's `--groups` stays only as a development and test harness.
2. **Use app roles or a small set of security groups**, not "all groups", to stay under the token overage limit. If overage occurs, resolve membership server-side through Microsoft Graph with the application's identity; if that fails, **refuse** (fail closed), never fall back to "no filter".
3. **Tags mirror the source system's access list.** Production ingestion copies access from the source (document library permissions or matter security). A scheduled re-tag job updates `allowed_groups` with a metadata-only merge (no re-extraction, no re-embedding) and records the time of the last sync, which is the staleness window we accept.
4. **Tools check entitlement for the user before acting.** A tool called on behalf of a user only returns data about contracts the user can already see (the vendor ID must come from a document the user's search returned). When a backend can enforce per-user access itself, call it with the user's identity (on-behalf-of flow) instead of the agent's.
5. **Side channels inherit the strictest tag.** Review history and stored answers carry the `allowed_groups` of every document they cite and are filtered the same way. Logs and telemetry hold IDs and scores, never clause text. Evaluation artifacts stay in the repo only because the corpus is public (CUAD); with private contracts they would stay inside the tenant.
6. **Platform access is separate from application access.** Data-plane roles are granted to identities that run the system and to a short list of administrators, reviewed like any privileged access; users get access only through the API.
7. **Leakage is a regression test with a pass mark of zero.** `eval/leakage_test.py` runs four kinds of probes against the live index and fails (exit code 1) on any leak:
   - enumerate everything each group can see and compare it with what it is entitled to
   - ask for each forbidden document by ID and by name
   - adversarial question text (asks to ignore filters, OData fragments, other groups' names)
   - crafted group values that try to break out of the filter; they must be rejected before a query runs

   It uses no semantic ranker and no chat model, so it is cheap enough to run after every ingestion, filter or prompt change, and later as a deployment gate.

## Consequences
- The question "how do you know a user only sees what they are entitled to?" has two answers: the design (groups from the token, filter at query time, fail closed) and the evidence (a zero-leak test run after each change).
- The filter is only as good as the tags: tag sync becomes a first-class pipeline with its own monitoring, not a one-time step.
- Groups in the token can be up to about an hour stale; for urgent revocations the API must also check a deny list or re-resolve membership through Graph.
- Answers and review history cost more to store and query because each carries access tags.

## Alternatives considered
- **Separate index per group:** simple isolation, but documents shared by several groups are duplicated and every new group needs a new index. Rejected at this scale; reconsider for hard tenant isolation.
- **Filter after retrieval in application code:** easy to forget on one path, and top-k results fill up with documents the user cannot see. Rejected: filter inside the search query.
- **Trust the client's groups because the client is ours:** any client can be modified or replayed. Rejected.
- **Microsoft Purview or SharePoint permission sync instead of our own tags:** the right production answer when the source is SharePoint; not available for a public corpus in a student subscription. Tags are written in the same shape so the source can change later.

## How it is verified
- `python eval/leakage_test.py --cuad-root <cuad>` → `PASS: 0 leaks`, results in `eval/results/leakage-<timestamp>.json`.
- Unit tests for `access_filter` (empty groups, malformed groups, malformed document IDs) in `agents/tests/test_slice1.py`.
- When the API exists: tests that a request with forged `groups` in the body or headers changes nothing, and that a token without the groups claim is refused.
