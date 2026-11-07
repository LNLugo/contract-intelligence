# ADR-0001: Build on public endpoints with Entra auth, harden in a dedicated phase

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0

## Context
The target architecture puts storage, search and the model behind private endpoints with public access disabled. Building that way from the start means every early failure could be a code bug or a DNS and network problem, and telling the two apart costs hours. Private endpoints also need paid tiers of AI Search, and those drain a $100 credit quickly.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Private from day one | Matches production at every step | Network problems hide logic bugs; paid tiers billed for the whole build |
| Public with keys, harden later | Fastest start | Builds a habit and a code path (key auth) that has to be ripped out |
| Public with Entra auth, harden later | Code is already identity-based; hardening becomes a network-only change | Not representative of production networking until phase 13 |

## Decision
I will build on public endpoints, but authenticate with Entra ID and managed identities from the first line of code, and do all network isolation in phase 13.

## Consequences
- Moving to private endpoints in phase 13 changes networking and DNS only, not application code.
- `DefaultAzureCredential` is used everywhere, so local development (my identity) and cloud (managed identity) share one code path.
- Accepted risk: until phase 13 the data plane is reachable from the internet. Mitigated by using only public CUAD contracts and disabling local key auth wherever the service allows it.

## Enterprise vs this build
In production, private endpoints come first, because the security review blocks anything else. The order differs; the end state is the same.

## Evidence
Phase 13 build log: before and after test showing public access denied and private resolution working.

## Revisit when
If any phase needs real or sensitive documents, harden that resource immediately.

## Interview angle
"I separated identity from network. Identity was right from day one, managed identities and no keys, so locking down the network at the end was a DNS and endpoint change with zero code changes. In a regulated client you would do the network first, but the code path is identical."
