"""Token validation and entitlements (ADR-0023, ADR-0024).

The ONLY source of a caller's search groups is a validated Entra ID access token:
signature (RS256, key from the tenant's published keys), issuer, audience, tenant, expiry.
Roles in the token map to search groups through a fixed table. Nothing in the request body,
headers or query string can set or widen them. Anything unexpected is refused (fail closed).
"""
import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

ROLE_TO_GROUP = {"Contracts.Legal": "grp-legal", "Contracts.Procurement": "grp-procurement"}
ALGORITHMS = ["RS256"]          # never "none", never HS256: a public key must not work as a shared secret
LEEWAY_SECONDS = 60             # clock skew tolerance


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    audience: str
    issuer: str

    @property
    def jwks_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"


@lru_cache(maxsize=1)
def settings() -> Settings:
    """From environment variables (set at deployment). For local runs, fall back to the
    non-secret identity settings in Key Vault (written by infra/08-identity.ps1)."""
    if os.environ.get("ID_TENANT_ID"):
        return Settings(os.environ["ID_TENANT_ID"], os.environ["ID_AUDIENCE"], os.environ["ID_ISSUER"])
    from identity.tokens import settings as kv_settings
    s = kv_settings()
    return Settings(s["tenantId"], s["audience"], s["issuer"])


@lru_cache(maxsize=1)
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(settings().jwks_url, cache_keys=True, lifespan=3600)


def signing_key(token: str):
    """Key that signed this token, from the tenant's published keys. Tests replace this."""
    return _jwks().get_signing_key_from_jwt(token).key


@dataclass(frozen=True)
class Caller:
    subject: str                # oid of the user or service principal: who, for the audit log
    client_app: str             # azp: which application called
    roles: tuple[str, ...]
    groups: tuple[str, ...]     # derived from roles; what the search filter uses


def _unauthorized(reason: str) -> HTTPException:
    # The reason goes to our log; the caller only learns that the token was not accepted
    return HTTPException(status_code=401, detail="invalid token",
                         headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{reason}"'})


def validate(token: str) -> Caller:
    s = settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise _unauthorized("malformed")
    if header.get("alg") not in ALGORITHMS:
        raise _unauthorized("algorithm not allowed")
    try:
        claims = jwt.decode(
            token, signing_key(token), algorithms=ALGORITHMS, audience=s.audience, issuer=s.issuer,
            leeway=LEEWAY_SECONDS, options={"require": ["exp", "iat", "iss", "aud", "tid", "oid"]})
    except jwt.PyJWTError as e:
        raise _unauthorized(type(e).__name__)
    if claims.get("tid") != s.tenant_id:
        raise _unauthorized("wrong tenant")
    roles = tuple(r for r in claims.get("roles", []) if isinstance(r, str))
    groups = tuple(sorted({ROLE_TO_GROUP[r] for r in roles if r in ROLE_TO_GROUP}))
    if not groups:
        raise HTTPException(status_code=403, detail="no contract entitlements in token")
    return Caller(claims["oid"], claims.get("azp", ""), roles, groups)


def current_caller(authorization: str | None = Header(default=None)) -> Caller:
    """FastAPI dependency: the only place a Caller is created."""
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized("missing bearer token")
    return validate(authorization.removeprefix("Bearer ").strip())
