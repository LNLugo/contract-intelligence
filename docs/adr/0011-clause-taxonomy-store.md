# ADR-0011: Where the governed clause taxonomy lives

- **Status:** Proposed
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
Pending the phase 6 cost check. Leaning toward Postgres because it also serves as the LangGraph checkpoint store (ADR-0007), so one service carries two jobs. The YAML file is the fallback, and it is a defensible choice in its own right.

## Consequences
- Terms the system cannot map are logged as exceptions for review rather than forced into a category.

## Interview angle
"The taxonomy is a governance artifact, not a prompt detail, so it lives in a store Legal owns, and it is applied in three places: ingestion, prompt and query. I put it in Postgres because the same instance holds the agent checkpoints, and a git-managed YAML would be equally defensible for a smaller team."
