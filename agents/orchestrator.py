"""Orchestrator (ADR-0026): a LangGraph state graph behind the API.

    plan ──> answer ──> needs vendor? ──yes──> vendor ──> compose
                              └──────no──────────────────> compose

Entitlements (ADR-0023, ADR-0024):
- The graph never sees groups. Tools are built per request from the validated Caller and close
  over the caller's groups; the graph state has no field a request could use to set them.
- The vendor tool takes a contract ID, not a vendor ID. It looks up the vendor ID through search
  WITH the caller's groups, so it can only act on contracts the caller can already see.
  "Not visible" and "does not exist" give the same answer, so the tool does not reveal either.

Failure (ADR-0009, ADR-0010): if the vendor system is unavailable, the vendor part ABSTAINS with
the reason; the clause answer is still returned. Nothing is guessed.

Routing is code, not the model: which steps run is decided by deterministic rules, and the model
is used only to write the cited answer (ADR-0019, ADR-0021). That keeps every path testable.
"""
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from . import _ingestion  # noqa: F401
from .answer import Answer, answer as run_answer
from .retrieve import document_vendor
from .taxonomy_snapshot import Category, classify, version as taxonomy_version
from .tools.vendor import Vendor, VendorNotFound, VendorUnavailable, get_vendor

_VENDOR_INTENT = re.compile(
    r"\b(vendor|supplier|payment terms?|vendor master|blocked|sap|counterparty status)\b", re.I)


@dataclass(frozen=True)
class CallerTools:
    """Every capability the graph has, bound to one caller's entitlements. Built only from a
    validated token (api.auth.Caller); nothing in the request can widen it."""
    answer: Callable[[str, str | None], Answer]
    vendor_for_contract: Callable[[str], Vendor]      # raises NotEntitled, VendorNotFound, VendorUnavailable


class NotEntitled(PermissionError):
    pass


def tools_for(groups: tuple[str, ...]) -> CallerTools:
    g = list(groups)

    def _answer(question: str, doc_id: str | None) -> Answer:
        return run_answer(question, g, doc_id=doc_id)

    def _vendor(doc_id: str) -> Vendor:
        vid = document_vendor(doc_id, g)
        if not vid:
            raise NotEntitled("contract not available to this caller")
        return get_vendor(vid)

    return CallerTools(_answer, _vendor)


class State(TypedDict, total=False):
    question: str
    doc_id: str | None
    category: dict | None
    needs_vendor: bool
    answer: dict
    vendor: dict
    result: dict


def build_graph(tools: CallerTools):
    def plan(s: State) -> State:
        cat: Category | None = classify(s["question"])
        return {"category": asdict(cat) if cat else None,
                "needs_vendor": bool(_VENDOR_INTENT.search(s["question"]))}

    def answer_node(s: State) -> State:
        a = tools.answer(s["question"], s.get("doc_id"))
        return {"answer": asdict(a)}

    def vendor_node(s: State) -> State:
        doc_id = s.get("doc_id")
        if not doc_id:
            return {"vendor": {"status": "NEEDS_CONTRACT",
                               "reason": "vendor data is checked for one contract: ask with doc_id"}}
        try:
            v = tools.vendor_for_contract(doc_id)
            return {"vendor": {"status": "OK", "record": asdict(v)}}
        except NotEntitled:
            return {"vendor": {"status": "NOT_AVAILABLE", "reason": "contract not available to you"}}
        except VendorNotFound:
            return {"vendor": {"status": "NOT_FOUND", "reason": "no record in the vendor master"}}
        except VendorUnavailable as e:
            return {"vendor": {"status": "ABSTAIN",
                               "reason": f"vendor system unavailable ({e}); vendor-dependent findings withheld"}}

    def compose(s: State) -> State:
        a = s["answer"]
        vendor = s.get("vendor", {"status": "NOT_REQUESTED"})
        overall = a["status"]
        if s.get("needs_vendor") and vendor["status"] in ("ABSTAIN", "NOT_AVAILABLE", "NEEDS_CONTRACT"):
            overall = "PARTIAL" if a["status"] == "ANSWERED" else a["status"]
        return {"result": {
            "status": overall,
            "clause": {k: a[k] for k in ("status", "determination", "answer", "findings", "reason")},
            "vendor": vendor,
            "category": s.get("category"),
            "taxonomy_version": taxonomy_version(),
        }}

    g = StateGraph(State)
    g.add_node("plan", plan)
    g.add_node("answer", answer_node)
    g.add_node("vendor", vendor_node)
    g.add_node("compose", compose)
    g.add_edge(START, "plan")
    g.add_edge("plan", "answer")
    g.add_conditional_edges("answer", lambda s: "vendor" if s.get("needs_vendor") else "compose",
                            {"vendor": "vendor", "compose": "compose"})
    g.add_edge("vendor", "compose")
    g.add_edge("compose", END)
    return g.compile()


def run(groups: tuple[str, ...], question: str, doc_id: str | None = None,
        tools: CallerTools | None = None) -> dict[str, Any]:
    """groups must come from a validated token (api.auth.Caller.groups). tools: tests only."""
    graph = build_graph(tools or tools_for(groups))
    return graph.invoke({"question": question, "doc_id": doc_id})["result"]
