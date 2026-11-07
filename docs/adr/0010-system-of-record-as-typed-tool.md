# ADR-0010: Vendor system of record reached through APIM as a typed, read-only tool

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 7

## Context
Findings like "payment terms differ from the vendor master" need live vendor and purchase-order data. In the enterprise version that is SAP (OData through SAP BTP with OAuth). This build has no SAP, so it needs a stand-in that keeps the same integration shape and the same failure modes.

## Options considered
| Option | Gains | Costs |
|---|---|---|
| Static JSON file loaded by the agent | Zero cost | No auth, no network failures, nothing learned about integration |
| Mock vendor API behind APIM Consumption, OAuth secret in Key Vault | Same shape as production: gateway, auth, rate limits, failures | Small cost; more setup |
| SAP API Business Hub sandbox behind APIM | Real SAP OData payloads | API-key sandbox, not OAuth via BTP; external dependency |

Tool packaging:
| Option | Gains | Costs |
|---|---|---|
| Native LangGraph tool via function calling | Simple, typed, one process | Tied to this agent framework |
| MCP server | Reusable by other agents and clients | Another service to run and secure |

## Decision
I will build a mock vendor-master Function behind APIM Consumption, called by a typed, read-only tool (vendor ID in, fixed fields out) through function calling. MCP is a v2 step.

## Consequences
- Failure handling is real: timeouts and auth failures fail closed, and the dependent finding abstains (ADR-0009).
- Vendor ID mismatches between upload metadata and extraction are resolved by code against the vendor record, never by the LLM.
- Optional stretch: point APIM at the SAP sandbox to handle real OData payloads.

## Interview angle
"The agent never touches the system of record directly. It calls one typed, read-only tool through API Management with a least-privilege identity, and if the call fails, the finding abstains instead of guessing. I kept it as a native tool in v1 and left MCP for when a second consumer appears."
