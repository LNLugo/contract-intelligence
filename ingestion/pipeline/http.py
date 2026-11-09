"""Authenticated HTTP with retries. One credential for everything (ADR-0013):
on a laptop DefaultAzureCredential uses `az login`; in Azure it uses the managed identity."""
import random
import time

import httpx
from azure.identity import DefaultAzureCredential

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
SEARCH_SCOPE = "https://search.azure.com/.default"

# 404 is included on purpose: model endpoints return short-lived DeploymentNotFound
# for deployments that exist (observed 2026-11-08, see build log).
RETRYABLE = {404, 408, 429, 500, 502, 503, 504}

_credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
_tokens: dict[str, tuple[str, float]] = {}
_client = httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))


def token(scope: str) -> str:
    cached = _tokens.get(scope)
    if cached and cached[1] - time.time() > 300:
        return cached[0]
    t = _credential.get_token(scope)
    _tokens[scope] = (t.token, t.expires_on)
    return t.token


def request(method: str, url: str, scope: str, *, json=None, retry_404: bool = True,
            max_attempts: int = 6, max_attempts_429: int = 12) -> httpx.Response:
    """Send a request with a bearer token; retry transient failures with backoff.
    Rate limits (429) get more attempts than other errors: they mean "later", not "broken".
    Honors Retry-After. Raises on the final failure or on a non-retryable status."""
    for attempt in range(1, max_attempts_429 + 1):
        resp = _client.request(method, url, json=json,
                               headers={"Authorization": f"Bearer {token(scope)}"})
        retryable = resp.status_code in RETRYABLE and (retry_404 or resp.status_code != 404)
        limit = max_attempts_429 if resp.status_code == 429 else max_attempts
        if resp.is_success or not retryable or attempt >= limit:
            if not resp.is_success:
                raise RuntimeError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:500]}")
            return resp
        wait = float(resp.headers.get("Retry-After", 0)) or min(60, 2 ** attempt) + random.random()
        time.sleep(wait)
    raise AssertionError("unreachable")
