"""Fail-closed behaviour of the system-of-record tool, without network calls."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
pytest.importorskip("azure.identity")
from agents.tools.vendor import VendorNotFound, VendorUnavailable, classify, get_vendor  # noqa: E402


def test_invalid_id_is_rejected_before_any_call():
    with pytest.raises(ValueError):
        get_vendor("12345; DROP TABLE vendors")


@pytest.mark.parametrize("code", [401, 403, 429, 500, 502, 503, 504])
def test_outages_and_auth_failures_fail_closed(code):
    with pytest.raises(VendorUnavailable):
        classify(code, "V1A2B3C")


def test_only_404_means_not_found():
    with pytest.raises(VendorNotFound):
        classify(404, "V1A2B3C")
