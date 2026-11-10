# ADR-0011: Where the governed clause taxonomy lives

- **Status:** Accepted (PostgreSQL Flexible Server)
- **Date:** 2026-11-07
- **Phase:** 6

## Context
The same legal concept appears under different names ("limitation of liability", "cap on damages"). A taxonomy maps terms to categories and is used in three places: at ingestion (classify chunks), in the prompt (constrain the model's categories) and at query time (normalize the user's wording). Legal must own and approve it.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| YAML in this repo, changed by pull request | Free; version control and approval built in through PR review | Legal will not use git; needs a redeploy to change |
| AI Search synonym maps | Native query expansion | Only covers query time, not ingestion or prompt; weak governance |
| Azure Database for PostgreSQL (Burstable) | Governed, queryable, an admin UI is possible, reusable as the LangGraph checkpoint store | Monthly cost; another service to secure |

## Decision
Azure Database for PostgreSQL Flexible Server, Burstable B1ms, PostgreSQL 16 (`infra/06-postgres.ps1`):
- **Entra ID authentication only; password login disabled.** Clients present an Entra access token as the password; nothing to store or rotate (ADR-0013).
- **Firewall open to one client IP** until private networking in the hardening phase.
- **Governed schema** (`taxonomy/schema.sql`): versions move draft → approved → retired, with at most one approved version (enforced by a unique partial index); each category has a definition, `includes` and `excludes` lists and an owner (Legal); `category_term` maps terms for query normalization; `unmapped_term` logs what could not be mapped instead of forcing a category.
- **Seeded as a draft** from CUAD's 41 published category descriptions, not from evaluation misses, so the evaluation set stays a test set. A draft is never used at runtime.
- The same server later holds the LangGraph checkpoints (ADR-0007): one service, two jobs.

## Cost
The first resource billed by the hour whether used or not. Stopped with `infra/06b-postgres-stop-start.ps1` between sessions (a stopped server bills storage only; Azure restarts it after 7 days).

## Consequences
- Terms the system cannot map are logged as exceptions for review rather than forced into a category.

## Interview angle
"The taxonomy is a governance artifact, not a prompt detail, so it lives in a store Legal owns, and it is applied in three places: ingestion, prompt and query. I put it in Postgres because the same instance holds the agent checkpoints, and a git-managed YAML would be equally defensible for a smaller team."
