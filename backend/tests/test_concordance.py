from lawdata import validate
from lawdata.loader import load_concordance


def test_concordance_is_consistent():
    assert validate.check_concordance() == []


def test_44ada_resolves_to_the_2025_provision():
    new = {c.new_ref for c in load_concordance() if c.old_ref == "IT1961:s44ADA"}
    assert new == {"IT2025:s58(2)/T3"}


def test_both_interest_sections_map_to_s425():
    targets = {c.old_ref: c.new_ref for c in load_concordance()
               if c.old_ref in ("IT1961:s234B", "IT1961:s234C")}
    assert targets == {"IT1961:s234B": "IT2025:s425", "IT1961:s234C": "IT2025:s425"}


def test_form_67_is_replaced_by_form_44():
    assert [(c.old_ref, c.new_ref) for c in load_concordance() if c.kind.value == "form"] == [("FORM67:all", "FORM44:all")]


def test_the_only_unverified_row_is_rule_6f():
    unverified = [c.old_ref for c in load_concordance() if c.status.value != "verified"]
    assert unverified == ["RULES1962:r6F"]
