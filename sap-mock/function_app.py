"""Mock SAP vendor master (ADR-0010). Stands in for SAP OData behind BTP.

Requires the x-sap-api-key header to match SAP_API_KEY, which the Function reads from
Key Vault through a Key Vault reference in its app settings. Only API Management holds
that value (as a Key Vault-backed named value), so callers cannot reach this directly.

Data is deterministic per vendor id ("V" + 6 hex characters, as assigned at ingestion),
so the same vendor always returns the same record.
"""
import hashlib
import hmac
import json
import os
import re
from datetime import date, timedelta

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
VENDOR_ID = re.compile(r"^V[0-9A-F]{6}$")
TERMS = ["Net 30", "Net 45", "Net 60", "Net 90"]
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE"]


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


@app.route(route="vendors/{vendor_id}", methods=["GET"])
def vendor(req: func.HttpRequest) -> func.HttpResponse:
    expected = os.environ.get("SAP_API_KEY", "")
    supplied = req.headers.get("x-sap-api-key", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return _json({"error": "unauthorized"}, 401)

    vid = req.route_params.get("vendor_id", "").upper()
    if not VENDOR_ID.match(vid):
        return _json({"error": "invalid vendor id", "expected": "V followed by 6 hex characters"}, 400)

    h = int(hashlib.sha256(vid.encode()).hexdigest(), 16)
    if h % 17 == 0:                                   # some ids genuinely do not exist
        return _json({"error": "vendor not found", "vendor_id": vid}, 404)
    return _json({
        "vendor_id": vid,
        "name": f"Vendor {vid[1:]}",
        "status": "blocked" if h % 11 == 0 else "active",
        "payment_terms": TERMS[h % len(TERMS)],
        "currency": "USD",
        "country": COUNTRIES[h % len(COUNTRIES)],
        "last_updated": (date(2026, 1, 1) + timedelta(days=h % 300)).isoformat(),
        "source": "mock-sap-vendor-master",
    })
