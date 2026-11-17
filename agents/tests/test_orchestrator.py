"""Orchestrator (ADR-0026): entitlements and failure handling, with fake tools and no network."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
pytest.importorskip("azure.identity")
pytest.importorskip("langgraph")

from agents import orchestrator as orch  # noqa: E402
from agents import taxonomy_snapshot as tax  # noqa: E402
from agents.answer import Answer, Citation, Finding  # noqa: E402
from agents.tools.vendor import Vendor, VendorNotFound, VendorUnavailable  # noqa: E402

VISIBLE, HIDDEN = "a" * 16, "b" * 16


@pytest.fixture(autouse=True)
def snapshot(tmp_path, monkeypatch):
    snap = {"version": "test-v1", "categories": [
        {"code": "cap_on_liability", "name": "Cap On Liability", "definition": "d", "terms": ["cap on damages"]},
        {"code": "termination_for_convenience", "name": "Termination For Convenience", "definition": "d", "terms": []}]}
    f = tmp_path / "s.json"; f.write_text(json.dumps(snap))
    monkeypatch.setenv("TAXONOMY_SNAPSHOT", str(f))
    tax.snapshot.cache_clear(); tax._phrases.cache_clear()
    yield
    tax.snapshot.cache_clear(); tax._phrases.cache_clear()


def answered(*_):
    return Answer("ANSWERED", "present", "Yes.", [Finding("s", [Citation("C1", "q q q q", True, "x.pdf", "1-1")])],
                  "", 2.5, 0, 10, 0.1)


def fake_tools(vendor_behaviour, calls):
    def vendor_for(doc_id):
        calls.append(doc_id)
        if doc_id != VISIBLE:
            raise orch.NotEntitled("no")
        return vendor_behaviour()
    return orch.CallerTools(answered, vendor_for)


def vendor_ok():
    return Vendor("V1A2B3C", "Vendor 1A2B3C", "active", "Net 90", "USD", "DE", "2026-03-01")


def test_vendor_for_visible_contract():
    r = orch.run(("grp-legal",), "What are the payment terms for this vendor?", VISIBLE, fake_tools(vendor_ok, []))
    assert r["vendor"]["status"] == "OK" and r["vendor"]["record"]["payment_terms"] == "Net 90"
    assert r["status"] == "ANSWERED"


def test_vendor_for_contract_the_caller_cannot_see_is_refused_without_saying_why():
    r = orch.run(("grp-procurement",), "Is the vendor blocked?", HIDDEN, fake_tools(vendor_ok, []))
    assert r["vendor"] == {"status": "NOT_AVAILABLE", "reason": "contract not available to you"}
    assert r["status"] == "PARTIAL"


def test_vendor_system_down_abstains_and_keeps_the_clause_answer():
    def down():
        raise VendorUnavailable("system of record returned HTTP 503 for V1A2B3C")
    r = orch.run(("grp-legal",), "Check the supplier payment terms", VISIBLE, fake_tools(down, []))
    assert r["vendor"]["status"] == "ABSTAIN" and "withheld" in r["vendor"]["reason"]
    assert r["clause"]["status"] == "ANSWERED" and r["status"] == "PARTIAL"


def test_vendor_not_found_is_a_fact_not_an_abstention():
    def missing():
        raise VendorNotFound("V000000")
    r = orch.run(("grp-legal",), "vendor status?", VISIBLE, fake_tools(missing, []))
    assert r["vendor"]["status"] == "NOT_FOUND" and r["status"] == "ANSWERED"


def test_no_vendor_intent_means_no_vendor_call():
    calls = []
    r = orch.run(("grp-legal",), "Is there a cap on damages?", VISIBLE, fake_tools(vendor_ok, calls))
    assert calls == [] and r["vendor"]["status"] == "NOT_REQUESTED"


def test_vendor_needs_a_contract():
    calls = []
    r = orch.run(("grp-legal",), "What are the vendor payment terms?", None, fake_tools(vendor_ok, calls))
    assert calls == [] and r["vendor"]["status"] == "NEEDS_CONTRACT"


def test_taxonomy_category_and_version_reported():
    r = orch.run(("grp-legal",), "Is there a cap on damages?", None, fake_tools(vendor_ok, []))
    assert r["category"]["code"] == "cap_on_liability" and r["taxonomy_version"] == "test-v1"


def test_unknown_topic_has_no_category():
    r = orch.run(("grp-legal",), "Who signed it?", None, fake_tools(vendor_ok, []))
    assert r["category"] is None


def test_graph_state_has_no_place_for_groups():
    assert not any("group" in k or "role" in k for k in orch.State.__annotations__)


def test_real_tools_pass_the_callers_groups(monkeypatch):
    seen = {}
    monkeypatch.setattr(orch, "document_vendor", lambda doc_id, groups: seen.setdefault("groups", groups) and None)
    with pytest.raises(orch.NotEntitled):
        orch.tools_for(("grp-procurement",)).vendor_for_contract(VISIBLE)
    assert seen["groups"] == ["grp-procurement"]


def test_boundaries_reach_the_prompt_only_when_approved_and_enabled(tmp_path, monkeypatch):
    snap = {"version": "cuad-v2", "categories": [
        {"code": "anti_assignment", "name": "Anti-Assignment", "definition": "d",
         "includes": ["an outright prohibition on assignment"], "excludes": [], "terms": ["assigned to a third party"]},
        {"code": "audit_rights", "name": "Audit Rights", "definition": "d", "includes": [], "excludes": [], "terms": []}]}
    f = tmp_path / "v2.json"; f.write_text(json.dumps(snap))
    monkeypatch.setenv("TAXONOMY_SNAPSHOT", str(f))
    tax.snapshot.cache_clear(); tax._phrases.cache_clear()
    q = "Is consent or notice required of a party if the contract is assigned to a third party?"
    text = tax.boundaries_text(q)
    assert "Counts: an outright prohibition on assignment" in text and "cuad-v2" in text
    assert tax.boundaries_text("Does a party have audit rights?") == ""      # category without boundaries
    assert tax.boundaries_text("Who signed it?") == ""                        # no category
    monkeypatch.setenv("BOUNDARIES", "false")
    assert tax.boundaries_text(q) == ""                                       # switched off for A/B runs


def test_one_word_terms_never_pick_a_category(tmp_path, monkeypatch):
    snap = {"version": "t", "categories": [
        {"code": "parties", "name": "Parties", "definition": "d", "terms": ["parties", "party"]},
        {"code": "exclusivity", "name": "Exclusivity", "definition": "d", "terms": ["exclusive dealing commitment"]}]}
    f = tmp_path / "s.json"; f.write_text(json.dumps(snap))
    monkeypatch.setenv("TAXONOMY_SNAPSHOT", str(f))
    tax.snapshot.cache_clear(); tax._phrases.cache_clear()
    q = "Is there an exclusive dealing commitment with the counterparty, or a ban on working with other parties?"
    assert tax.classify(q).code == "exclusivity"
    assert tax.classify("Which party pays?") is None
