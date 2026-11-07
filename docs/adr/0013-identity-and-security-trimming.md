# ADR-0013: Entra identities everywhere, no keys, results filtered by the user's groups

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 1 onward, completed in 11

## Context
Contracts are restricted by business unit, vendor and contract type. A RAG system that retrieves across the whole index can leak a clause to a user who could never open the source PDF. Separately, keys in config are the most common path to credential leaks.

## Options considered: service authentication
| Option | Gains | Costs |
|---|---|---|
| Keys and connection strings in config | Quick | Leak risk; rotation burden |
| Keys in Key Vault | Better | Still keys |
| Managed identities + data-plane RBAC, local key auth disabled | No secrets for Azure services | Role assignment propagation delays; more setup |

## Options considered: document-level security
| Option | Gains | Costs |
|---|---|---|
| Separate index per business unit | Hard isolation | Index sprawl; cross-unit users break it |
| Group IDs stored on each chunk, filtered on every query | One index; enforced at retrieval time | Filter must never be skipped; group changes need reindex or a lookup |
| AI Search native document-level permissions | Managed | Check feature maturity and tier support before relying on it |

## Decision
Managed identities for every service-to-service call; the only secret in the system is the vendor API's OAuth client secret, held in Key Vault. Each chunk stores allowed group IDs, and the retrieval agent always applies the filter from the signed-in user's token. The filter lives in one function that every query path calls, with a test that fails if a query runs without it.

## Interview angle
"Security trimming happens at retrieval, not generation: if the user cannot open the PDF, its chunks never reach the prompt. The group filter is applied in one function that a test forces every query through, and there are no Azure keys anywhere; the only secret is the system-of-record OAuth credential in Key Vault."
