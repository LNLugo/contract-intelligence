"""Citation check (ADR-0020, ADR-0029): exact after cleaning; fuzzy only for PDF noise and never
when a negation, modal verb or number differs; offsets point at the source text."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents.citations import MIN_CHARS, check_quote, is_verbatim, norm  # noqa: E402

CLAUSE = ("12.1 Neither party’s aggregate liability under this Agreement shall exceed the total "
          "fees paid by Customer in the twelve (12) months preceding the claim.")


def test_norm_maps_ligatures_curly_quotes_and_whitespace():
    assert norm("  the ﬁrst party’s\n\n  “fees”  ") == "the first party's \"fees\""


def test_exact_quote_passes_with_offsets_into_original_text():
    q = "aggregate liability under this Agreement shall exceed the total fees"
    r = check_quote(q, CLAUSE)
    assert r.valid and r.match == "exact"
    assert CLAUSE[r.start:r.end] == q


def test_offsets_survive_whitespace_and_ligatures_in_the_source():
    clause = "The  Supplier shall\n  not  be liable for any ﬁnancial loss arising from delay."
    r = check_quote("Supplier shall not be liable for any financial loss", clause)
    assert r.valid and r.match == "exact"
    assert clause[r.start:r.end] == "Supplier shall\n  not  be liable for any ﬁnancial loss"


def test_straight_apostrophe_matches_curly_in_source():
    assert check_quote("Neither party's aggregate liability under this Agreement shall exceed", CLAUSE).valid


def test_short_quote_fails():
    r = check_quote("the twelve (12) months", CLAUSE)
    assert not r.valid and r.reason == "too_short"
    assert MIN_CHARS >= 40


def test_invented_quote_fails():
    r = check_quote("liability is unlimited for gross negligence and wilful misconduct", CLAUSE)
    assert not r.valid and r.reason == "not_in_clause"


def test_inserted_not_fails_even_if_almost_identical():
    long_clause = CLAUSE + " This limitation applies to all claims under this Agreement and its schedules."
    r = check_quote("aggregate liability under this Agreement shall not exceed the total fees paid by Customer "
                    "in the twelve (12) months preceding the claim", long_clause)
    assert not r.valid and r.reason in ("fuzzy_changed_meaning", "not_in_clause")


def test_changed_number_fails():
    r = check_quote("fees paid by Customer in the twenty-four (24) months preceding the claim", CLAUSE)
    assert not r.valid


def test_hyphenation_at_line_break_passes_as_fuzzy():
    clause = ("Either party may terminate this Agreement upon thirty (30) days written notice if the other "
              "party materially breaches any obli-\ngation and fails to cure it.")
    r = check_quote("terminate this Agreement upon thirty (30) days written notice if the other party "
                    "materially breaches any obligation and fails to cure it", clause)
    assert r.valid and r.match == "fuzzy"
    assert "obli-" in clause[r.start:r.end]


def test_wrong_clause_fails():
    other = "This Agreement is governed by the laws of the State of New York, without regard to conflicts rules."
    assert check_quote("aggregate liability under this Agreement shall exceed the total fees", other).valid is False


def test_missing_clause_fails():
    assert check_quote("aggregate liability under this Agreement shall exceed the total fees", None).reason == "no_clause"


def test_is_verbatim_helper():
    assert is_verbatim(CLAUSE, "aggregate liability under this Agreement shall exceed")
    assert not is_verbatim(CLAUSE, "aggregate liability under this Agreement shall not exceed")
