"""Tests for the code-enforced parts of slice 1: the access filter and the citation check.
No Azure calls. Run: pytest agents/tests"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
pytest.importorskip("azure.identity")
from agents.answer import quote_in_clause  # noqa: E402
from agents.retrieve import AccessError, access_filter  # noqa: E402

CLAUSE = ("12.1 Neither party's aggregate liability under this Agreement shall exceed the total "
          "fees paid by Customer in the twelve (12) months preceding the claim.")


def test_filter_requires_groups():
    with pytest.raises(AccessError):
        access_filter([])


def test_filter_rejects_injection_in_group_name():
    with pytest.raises(AccessError):
        access_filter(["grp-legal') or true or ('"])


def test_filter_rejects_bad_doc_id():
    with pytest.raises(AccessError):
        access_filter(["grp-legal"], "x' or doc_id ne '")


def test_filter_shape():
    f = access_filter(["grp-legal", "grp-procurement"], "bdb7d1532a642920")
    assert "search.in(g, 'grp-legal,grp-procurement', ',')" in f
    assert f.endswith("doc_id eq 'bdb7d1532a642920'")


def test_exact_quote_is_valid():
    assert quote_in_clause("aggregate liability under this Agreement shall exceed the total fees paid", CLAUSE)


def test_quote_with_typography_differences_is_valid():
    assert quote_in_clause("Neither party’s aggregate liability under this Agreement shall exceed", CLAUSE)


def test_invented_quote_is_invalid():
    assert not quote_in_clause("liability is unlimited for gross negligence and wilful misconduct", CLAUSE)


def test_very_short_quote_is_invalid():
    assert not quote_in_clause("twelve months", CLAUSE)
