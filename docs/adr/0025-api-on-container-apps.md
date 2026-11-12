# ADR-0025: Run the API on Container Apps with a managed identity and least-privilege roles

- **Status:** Accepted
- **Date:** 2026-11-12
- **Phase:** Identity first (deployment)
- **Builds on:** ADR-0023 (entitlements from the token), ADR-0024 (identity tenant, app roles, two gates)

## Context
The API validates Entra tokens and passes tested end to end on the laptop. To be the only way users reach the index it must run in Azure, with its own identity, and hold no secret. Budget: $100 student credit, about $16 used.

## Decision
1. **Azure Container Apps, Consumption plan, scale to zero** (min 0, max 1 replica, 0.5 vCPU, 1 GiB). No cost while idle; first request after idle takes about 20 seconds.
2. **Image built in GitHub Actions, pushed with no stored secret.** ACR Tasks (cloud build) are not permitted on this subscription (`TasksOperationsNotAllowed`). The workflow signs in to Azure with workload identity federation: a user-assigned managed identity trusts only GitHub OIDC tokens for pushes to `main` of this repository, and holds only `AcrPush` on this registry. The 22 API security tests must pass before the image is built. Images are tagged with the commit, so the tag names exactly the code that runs; the deploy script refuses a commit with no image.
3. **No registry password.** Azure Container Registry Basic with the admin user disabled; the app's system-assigned managed identity pulls with `AcrPull`.
4. **Least privilege at runtime.** The API's identity gets `Search Index Data Reader` (read, not write) and `Cognitive Services OpenAI User` (embeddings for the query). Nothing on Key Vault, storage or PostgreSQL: the API does not use them yet, so it cannot be used to reach them.
5. **Configuration is not secret.** Issuer, audience and tenant are read from Key Vault at deploy time and set as environment variables. The API holds no secret at all.
6. **Small image, small attack surface.** Only the API's runtime packages and code are in the image (default-deny `.dockerignore`: no evaluation data, results, infra scripts or tests); runs as a non-root user; `--no-server-header`; no OpenAPI docs endpoint.
7. **Two tenants, checked every time.** Every resource script starts with `Assert-ResourceSubscription` and stops if the CLI is pointed at the identity tenant (build log, 2026-11-11).

## Consequences
- Cost: Container Registry Basic is the main fixed cost (about $5 a month); Container Apps and Log Analytics stay near zero at this volume.
- The API endpoint is public (HTTPS). Entitlements are enforced by the token check, not by the network; private networking comes with the hardening phase (ADR-0011).
- Cold starts after idle; acceptable for a review tool, not for an interactive chat SLA (set min replicas to 1 then).

## Alternatives considered
- **App Service:** always-on plan costs more at zero traffic; no scale to zero.
- **Azure Functions (already used for ingestion):** possible, but the API is a long-lived web service with its own dependencies and will host the orchestrator; a container keeps it portable.
- **ACR Tasks (`az acr build`):** first choice, simplest; blocked on this subscription.
- **GitHub Container Registry with a public image:** free (saves the registry's ~$5 a month), but the image would be public and pulled from outside Azure. Rejected for a financial-services pattern; a private registry with identity-based pull and push is the norm.
- **A service principal secret stored in GitHub:** a long-lived credential that can leak and must be rotated. Rejected: federation needs no secret at all.
- **Easy Auth (built-in authentication) in front of the API:** passes identity in headers; this API trusts only tokens it validates itself (ADR-0024).

## In an interview (20 seconds)
"The API runs on Container Apps and holds no secret: it pulls its image with its managed identity, reads the index with a read-only role, and gets issuer and audience from configuration. It can only reach what it needs, and the image is tagged with the commit, so I can say exactly what code is serving a request."
