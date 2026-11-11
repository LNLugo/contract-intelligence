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

## Implementation (2026-11-11, `infra/07-sap-apim.ps1`)
| Hop | Mechanism |
|---|---|
| Agent → API Management | APIM subscription key scoped to this one API, stored in Key Vault, read by the agent with its Entra identity (`agents/tools/vendor.py`) |
| API Management → mock SAP | `x-sap-api-key` injected by policy from a **Key Vault-backed named value**, resolved by APIM's system-assigned managed identity (Key Vault Secrets User) |
| Mock SAP (`sap-mock/`, separate Function app) | Reads the same credential through a **Key Vault reference** in its app settings; compares in constant time; 401 otherwise |
| Gateway policy | `rate-limit` 60 calls/min, `forward-request` timeout 10 s, `x-powered-by` removed |
| Tool contract | Vendor ID validated (`V` + 6 hex) before any call; fixed fields out; 404 → `VendorNotFound` (a fact); any other failure or timeout → `VendorUnavailable` (dependent finding abstains) |

Secrets are generated in memory, written to Key Vault through a temporary file, and never printed, stored in config or committed.

## Enterprise vs this build
- **Caller authentication:** a subscription key (kept in Key Vault) here; in production, Entra token validation at the gateway (`validate-azure-ad-token`) against an app registration, so no shared key exists at all.
- **Backend authentication:** a shared secret header here; SAP BTP in the reference design uses OAuth 2.0 client credentials, with APIM's managed identity fetching them from Key Vault and caching the token.
- **Network:** the Consumption tier has no VNet integration or static outbound IP, so the mock SAP Function is internet-reachable and protected only by the secret. Production uses a VNet-integrated APIM tier and a private backend, so the system of record is unreachable except through the gateway.

## Interview angle
"The agent never touches the system of record directly. It calls one typed, read-only tool through API Management with a least-privilege identity, and if the call fails, the finding abstains instead of guessing. I kept it as a native tool in v1 and left MCP for when a second consumer appears."
