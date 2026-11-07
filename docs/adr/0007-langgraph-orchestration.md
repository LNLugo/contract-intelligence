# ADR-0007: LangGraph for orchestration instead of a managed agent service

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 8

## Context
The answer path has a parallel fan-out (intent, memory, policy), a join (execution plan), a single retrieval point, a sequential validation chain, and a deterministic routing step with three exits (final, legal review, abstain). Control flow has to be explicit and auditable, because a reviewer will ask why a finding went where it went.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Foundry Agent Service | Managed threads, tools and hosting; Azure-native | Less explicit control over branching and parallelism; flow lives partly in the service |
| Semantic Kernel | Microsoft-supported; strong .NET story | Graph-style orchestration less mature for this shape |
| LangGraph | Explicit state graph, parallel branches, conditional edges, checkpointing, interrupts for human review | I host it; I choose and operate the checkpoint store |

## Decision
I will use LangGraph, with routing implemented as plain Python conditional edges and not as LLM decisions.

## Consequences
- The graph diagram generated from code becomes living architecture documentation.
- Human review maps to a LangGraph interrupt, resumed when legal responds.
- Checkpoints need a store; reuse Postgres from ADR-0011 rather than adding a service.
- Accepted risk: not the Microsoft-first answer, so the reason must be stated clearly.

## Interview angle
"I chose LangGraph because the control flow is the compliance story: parallel fan-out, one retrieval point, and a router that is ordinary code, not a model decision. A managed agent service hides too much of that flow for a reviewer to audit."
