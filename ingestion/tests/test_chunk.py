"""Unit tests for cleaning and chunking. No Azure calls; run with: pytest ingestion/tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.chunk import chunk, clean, count_tokens, embedding_text, paragraphs  # noqa: E402


def para(text, page=1, role=None):
    return {"content": text, "role": role, "boundingRegions": [{"pageNumber": page}]}


def layout(*paras):
    return {"paragraphs": list(paras), "pages": [{}] * max(p["boundingRegions"][0]["pageNumber"] for p in paras)}


def test_clean_strips_selection_marks():
    assert clean("☒ :selected: QUARTERLY REPORT :unselected: ☐ OR") == "QUARTERLY REPORT OR"


def test_page_furniture_is_dropped():
    lay = layout(para("ACME CORP CONFIDENTIAL", role="pageHeader"), para("Real clause text."),
                 para("Page 3", role="pageNumber"))
    assert [p.text for p in paragraphs(lay)] == ["Real clause text."]


def test_chunks_respect_budget_and_track_pages():
    body = " ".join(["The Supplier shall deliver the goods on time."] * 20)
    lay = layout(*[para(body, page=1 + i // 3) for i in range(12)])
    chunks = chunk(lay, budget=400, overlap=60)
    assert len(chunks) > 1
    assert all(c.tokens <= 400 for c in chunks)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 4


def test_overlap_repeats_tail_paragraph():
    paras = [para(f"Clause {i}. " + "word " * 80) for i in range(10)]
    chunks = chunk(layout(*paras), budget=300, overlap=120)
    for a, b in zip(chunks, chunks[1:]):
        assert set(a.paragraphs) & set(b.paragraphs), "consecutive chunks should share a paragraph"


def test_every_paragraph_is_covered_and_order_is_kept():
    paras = [para(f"Clause {i}. " + "word " * 50) for i in range(25)]
    chunks = chunk(layout(*paras), budget=250, overlap=60)
    covered = sorted({i for c in chunks for i in c.paragraphs})
    assert covered == list(range(25))
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_oversized_paragraph_is_split():
    long_para = " ".join(f"Sentence number {i} about indemnification." for i in range(300))
    chunks = chunk(layout(para(long_para)), budget=200, overlap=30)
    assert len(chunks) > 1 and all(c.tokens <= 200 for c in chunks)


def test_section_heading_carries_forward():
    lay = layout(para("12. LIMITATION OF LIABILITY", role="sectionHeading"),
                 para("Neither party's aggregate liability shall exceed the fees paid."),
                 para("13. TERMINATION", role="sectionHeading"),
                 para("Either party may terminate on ninety days notice."))
    chunks = chunk(lay, budget=20, overlap=0)
    headings = {c.content.splitlines()[0]: c.section_heading for c in chunks}
    assert any(h == "13. TERMINATION" for h in headings.values())
    text = embedding_text(chunks[-1], "Acme Supply Agreement.pdf")
    assert text.startswith("Acme Supply Agreement")


def test_empty_layout_gives_no_chunks():
    assert chunk({"paragraphs": []}) == []
    assert count_tokens("abcd") >= 1
