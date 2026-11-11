# ADR-0024: A separate identity tenant, app roles, and two gates on every request

- **Status:** Accepted
- **Date:** 2026-11-11
- **Phase:** Identity first (before the orchestrator)
- **Implements:** ADR-0023, decision 1 and 2 (groups only from a validated token; avoid group overage)

## Context
ADR-0023 decided that a caller's search groups come only from a validated Entra ID token. Building that needs an app registration, roles and test identities. The tenant that holds the Azure subscription (Stevens) does not allow students to create app registrations or security groups (`allowedToCreateApps: false`, `allowedToCreateSecurityGroups: false`, no directory roles), but does allow creating a tenant (`allowedToCreateTenants: true`).

A bank is in the same position: application teams do not create identities in the corporate directory on their own; the directory is a separately governed trust boundary.

## Decision
1. **Identity lives in its own tenant** (`ciidentitydev2416.onmicrosoft.com`, Entra ID Free), where I am Global Administrator. Workloads stay in the resource tenant. The API trusts exactly one issuer (`https://login.microsoftonline.com/<identity-tenant>/v2.0`) and one audience (the API's application ID).
2. **App roles, not security groups.** The API app defines `Contracts.Legal` and `Contracts.Procurement`. Roles appear in the token's `roles` claim, are scoped to this one application, and do not hit the group overage limit (ADR-0023). The API maps roles to search groups through a fixed table in code; an unknown role grants nothing.
3. **Two independent gates:**
   - **Entra:** the API's service principal requires role assignment. A caller with no role is refused a token (`AADSTS501051`), so the API never sees it.
   - **API:** validates the token itself (RS256 only, signature against the tenant's published keys, issuer, audience, tenant, expiry, required claims) and refuses a token with no contract role (403). If someone turns off assignment in Entra by mistake, the API still refuses.
4. **Request models reject unknown fields.** A body with `groups`, `allowed_groups`, `filter` or `roles` gets 422, not silent ignoring: a client trying to choose its own entitlements is an error worth seeing. Headers are never read for entitlements.
5. **Two kinds of test identities:**
   - three client apps (legal, procurement, no role) with the client credentials flow for automated tests: no MFA prompt, same `roles` claim
   - three users (legal, procurement, no role) for interactive sign-in with MFA in the review app
6. **Secrets go straight to Key Vault.** Client secrets (90 days, rotated on every run of `infra/08-identity.ps1`) and initial user passwords (change at first sign-in) are generated in memory and written to Key Vault in the resource tenant. Never printed, stored in files or committed. Non-secret settings (tenant, audience, client IDs) are also kept in Key Vault so they stay out of the public repo.
7. **The audit log records who, not what:** caller object ID, client app, groups, document IDs returned. Never query results' text.

## Consequences
- The API can be tested end to end with real Entra tokens, and the token check is unit-tested with locally signed tokens (22 tests: forged body fields, forged headers, wrong key, expired, wrong audience, issuer or tenant, `alg: none`, HS256 algorithm confusion, missing claims, no contract role).
- Two tenants to sign in to during setup; scripts check which tenant they run in and stop before creating anything if they are in the wrong one (that check caught a wrong tenant ID on the first run).
- Client secrets expire in 90 days. Production would use certificates or workload identity federation instead of secrets.
- Role changes take effect on the next token (up to about an hour). Urgent revocation needs a deny check in the API (ADR-0023).

## Alternatives considered
- **Security groups in the token:** overage above about 200 groups, groups are tenant-wide rather than per application, and creating them was not permitted here. Rejected.
- **Tests sign their own tokens only:** proves the validation code but not the Entra configuration. Kept for unit tests; real tokens for the end-to-end check.
- **Ask university IT for an app registration:** slow, and the identity would not be under my control for testing.
- **Built-in Container Apps authentication (Easy Auth) only:** convenient, but it passes identity to the app in headers, and this API must not trust headers. May be added later as an extra layer in front of the API's own validation.

## In an interview (20 seconds)
"Entitlements come only from a validated token. Entra is the first gate: no role, no token. The API is the second: it checks signature, issuer, audience, tenant and expiry itself, maps app roles to search groups through a fixed table, and rejects any request that tries to send its own groups. Neither gate assumes the other is configured correctly."
