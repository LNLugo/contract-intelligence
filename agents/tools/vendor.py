"""Typed, read-only system-of-record tool (ADR-0010): vendor ID in, fixed fields out.

Path: this tool -> API Management (subscription key read from Key Vault with my Entra identity)
-> mock SAP (credential injected by APIM from Key Vault). The tool never holds the SAP credential.

Fails closed (ADR-0009): a timeout, rate limit, auth failure or server error raises
VendorUnavailable, and the finding that depends on vendor data must abstain. A vendor that
does not exist raises VendorNotFound, which is a fact, not an outage.

    python -m agents.tools.vendor V1A2B3C
"""
import os
import re
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache

import httpx

from .. import _ingestion  # noqa: F401
from pipeline import http

APIM = os.environ.get("APIM", "apim-ci-dev-2416")
KV = os.environ.get("KV", "kv-ci-dev-2416")
GATEWAY = f"https://{APIM}.azure-api.net/sap/vendors"
VAULT_SCOPE = "https://vault.azure.net/.default"
_VENDOR_ID = re.compile(r"^V[0-9A-F]{6}$")


@dataclass(frozen=True)
class Vendor:
    vendor_id: str
    name: str
    status: str
    payment_terms: str
    currency: str
    country: str
    last_updated: str


class VendorNotFound(LookupError):
    pass


class VendorUnavailable(RuntimeError):
    """The system of record could not answer. Dependent findings must abstain, never guess."""


@lru_cache(maxsize=1)
def _subscription_key() -> str:
    url = f"https://{KV}.vault.azure.net/secrets/apim-subscription-key?api-version=7.4"
    return http.request("GET", url, VAULT_SCOPE, retry_404=False).json()["value"]


def classify(status_code: int, vendor_id: str) -> None:
    """Map a non-200 response to the right failure. Only 404 means 'no such vendor'."""
    if status_code == 404:
        raise VendorNotFound(vendor_id)
    raise VendorUnavailable(f"system of record returned HTTP {status_code} for {vendor_id}")


def get_vendor(vendor_id: str, timeout: float = 10.0) -> Vendor:
    vendor_id = vendor_id.strip().upper()
    if not _VENDOR_ID.match(vendor_id):
        raise ValueError(f"Invalid vendor id {vendor_id!r}: expected V followed by 6 hex characters")
    try:
        resp = httpx.get(f"{GATEWAY}/{vendor_id}", timeout=timeout,
                         headers={"Ocp-Apim-Subscription-Key": _subscription_key()})
    except httpx.HTTPError as exc:
        raise VendorUnavailable(f"system of record unreachable: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        classify(resp.status_code, vendor_id)
    data = resp.json()
    return Vendor(**{f: str(data.get(f, "")) for f in Vendor.__dataclass_fields__})   # fixed fields only


if __name__ == "__main__":
    vid = sys.argv[1] if len(sys.argv) > 1 else "V1A2B3C"
    try:
        v = get_vendor(vid)
        for k, val in asdict(v).items():
            print(f"  {k:14s} {val}")
    except VendorNotFound:
        print(f"{vid}: not found in the vendor master (a fact: the finding can say so)")
    except VendorUnavailable as exc:
        print(f"{vid}: UNAVAILABLE ({exc}). Dependent findings abstain.")
