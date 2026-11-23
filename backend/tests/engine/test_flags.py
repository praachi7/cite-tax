"""Phase F: the compliance and audit-risk flags of SRS/SDS Table 3.1, the deadline tracker and the
Form 44 / Form 67 readiness checklist.

Done-when (Implementation Plan, Phase F): each flag fires on its trigger persona and on no other, and
every flag shows severity, reason and citation.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.flag_rules import RULES, TABLE_3_1_CODES
from engine.models import TaxpayerInput
from engine.pipeline import run
from lawdata.loader import load_registry
from lawdata.models import CITATION_RE

PERSONAS = Path(__file__).parent / "personas"
PREFIXES = {s.cite_prefix for s in load_registry()}

# Flag -> the persona(s) built to trigger it. A persona may trigger several flags.
TRIGGER = {
    "W8BEN_INVALID": {"P6"},
    "US_TAX_ON_INDIA_WORK": {"P6"},
    "US_DAYS_WARNING": {"P9"},
    "US_DAYS_TRIGGER": {"P5"},
    "RECEIPTS_NEAR_LIMIT": {"P3"},
    "CASH_SHARE_ABOVE_5": {"P4"},
    "PROFIT_BELOW_50": {"P10"},
    "FOREIGN_ACCOUNT_HELD": {"P7"},
    "FTC_DOCS_INCOMPLETE": {"P5"},
    "FIRA_MISSING": {"P7"},
    "GST_LUT_MISSING": {"P8"},
    "ADVANCE_TAX_DUE": {"P3"},
    "RETURN_DUE": {"P2"},
    "LOW_CLASSIFICATION_CONFIDENCE": {"P10"},
}

# SRS/SDS Table 3.1 severities.
TABLE_SEVERITY = {
    "W8BEN_INVALID": "high", "US_TAX_ON_INDIA_WORK": "high", "US_DAYS_WARNING": "medium", "US_DAYS_TRIGGER": "high",
    "RECEIPTS_NEAR_LIMIT": "medium", "CASH_SHARE_ABOVE_5": "medium", "PROFIT_BELOW_50": "high",
    "FOREIGN_ACCOUNT_HELD": "high", "FTC_DOCS_INCOMPLETE": "high", "FIRA_MISSING": "medium",
    "GST_LUT_MISSING": "medium", "ADVANCE_TAX_DUE": "medium", "RETURN_DUE": "info",
    "LOW_CLASSIFICATION_CONFIDENCE": "low",
}


def persona_input(pid, **overrides):
    data = yaml.safe_load((PERSONAS / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]
    data.update(overrides)
    return TaxpayerInput(**data)


@pytest.fixture(scope="module")
def persona_results():
    return {f"P{n}": run(persona_input(f"P{n}")) for n in range(1, 11)}


def make(tax_year=2026, electronic=2400000, **kw):
    receipts = kw.pop("receipts", dict(electronic=electronic))
    return TaxpayerInput(tax_year=tax_year, receipts=receipts, **kw)


def codes(r):
    return [f.code for f in r.flags]


def flag(r, code):
    return next(f for f in r.flags if f.code == code)


# ---- the rule table matches SRS/SDS Table 3.1 ----

def test_every_table_3_1_flag_has_a_rule_and_a_trigger_persona():
    assert set(TABLE_3_1_CODES) == set(TRIGGER) == set(TABLE_SEVERITY)
    assert len(TABLE_3_1_CODES) == 14          # 13 rows; US_DAYS_WARNING / US_DAYS_TRIGGER share one


def test_rule_severities_match_table_3_1():
    assert {r.code: r.severity for r in RULES} == TABLE_SEVERITY


def test_every_rule_has_a_citation_or_a_source_note():
    for r in RULES:
        assert r.cite_keys or r.case_cite_keys or r.extra_cites or r.source_note, r.code
        assert r.trigger.strip(), r.code


# ---- done-when: each flag fires on its trigger persona and on no other ----

@pytest.mark.parametrize("code", sorted(TRIGGER))
def test_flag_fires_on_its_trigger_persona_and_on_no_other(code, persona_results):
    fired = {pid for pid, r in persona_results.items() if code in codes(r)}
    assert fired == TRIGGER[code]


def test_p1_baseline_raises_no_flag(persona_results):
    assert codes(persona_results["P1"]) == []


@pytest.mark.parametrize("code", sorted(TRIGGER))
def test_flag_shows_severity_reason_and_citation(code, persona_results):
    pid = next(iter(TRIGGER[code]))
    f = flag(persona_results[pid], code)
    assert f.severity == TABLE_SEVERITY[code]
    assert f.message.strip() and f.rule_id == f"ENG.10.flag.{code}"
    assert f.citations or f.source_note, f"{code} has neither a citation nor a source note"
    for c in f.citations:
        assert CITATION_RE.match(c) and c.split(":")[0] in PREFIXES, c


def test_flags_without_a_registered_source_say_so():
    for code in ("FIRA_MISSING", "LOW_CLASSIFICATION_CONFIDENCE"):
        rule = next(r for r in RULES if r.code == code)
        assert not rule.cite_keys and rule.source_note
    gst = next(r for r in RULES if r.code == "GST_LUT_MISSING")
    assert "registry" in gst.source_note


def test_foreign_account_flag_names_the_contested_assumption(persona_results):
    assert flag(persona_results["P7"], "FOREIGN_ACCOUNT_HELD").assumptions == ["A-12"]
    r = run(persona_input("P7", foreign_assets_held=True))
    assert flag(r, "FOREIGN_ACCOUNT_HELD").assumptions == []


def test_flag_citations_follow_the_act_for_the_year():
    receipts = dict(electronic=4600000, cash=400000)                      # 8% cash
    new = flag(run(make(2026, receipts=receipts, declared_profit=3000000)), "CASH_SHARE_ABOVE_5").citations
    old = flag(run(make(2025, receipts=receipts, declared_profit=3000000)), "CASH_SHARE_ABOVE_5").citations
    assert any(c.startswith("IT2025:s58") for c in new) and not any(c.startswith("IT1961") for c in new)
    assert any(c.startswith("IT1961:s44ADA") for c in old) and not any(c.startswith("IT2025") for c in old)


# ---- boundaries, one rule at a time ----

def test_w8ben_expires_at_the_end_of_the_third_calendar_year_after_signing():
    def r(signed, as_of=None):
        e = dict(label="Acme", country_of_performance="IN", amount_inr=1000000, w8ben_signed=signed)
        return run(make(engagements=[e], as_of=as_of))
    assert "W8BEN_INVALID" not in codes(r(date(2023, 5, 1), date(2026, 12, 31)))     # last valid day
    assert "W8BEN_INVALID" in codes(r(date(2023, 5, 1), date(2027, 1, 1)))
    assert "W8BEN_INVALID" in codes(r(date(2023, 5, 1)))         # undated: must cover the year to 31 Mar 2027
    assert "W8BEN_INVALID" not in codes(r(date(2024, 1, 2)))     # valid to 31 Dec 2027


def test_w8ben_is_not_checked_for_a_client_who_is_not_a_us_person():
    e = dict(country_of_performance="IN", amount_inr=1000000, client_is_us_person=False, w8ben_on_file=False)
    assert "W8BEN_INVALID" not in codes(run(make(engagements=[e])))


def test_us_tax_on_us_performed_work_is_not_us_tax_on_india_work():
    e = dict(country_of_performance="US", amount_inr=800000, us_tax_withheld_inr=240000)
    assert "US_TAX_ON_INDIA_WORK" not in codes(run(make(engagements=[e], us_days_by_year={2026: 95})))


@pytest.mark.parametrize("cash, cheque, fires", [
    (125000, 0, False),        # exactly 5% of 25L
    (125100, 0, True),
    (0, 125100, True),         # a non-account-payee cheque counts as cash
])
def test_cash_share_boundary(cash, cheque, fires):
    receipts = dict(electronic=2500000 - cash - cheque, cash=cash, non_account_payee_cheque=cheque)
    assert ("CASH_SHARE_ABOVE_5" in codes(run(make(receipts=receipts)))) is fires


def test_profit_below_50_needs_income_above_the_exemption_limit():
    assert "PROFIT_BELOW_50" not in codes(run(make(electronic=1000000, declared_profit=400000)))   # 4L = limit
    assert "PROFIT_BELOW_50" in codes(run(make(electronic=1000000, declared_profit=400010)))


@pytest.mark.parametrize("as_of, filed, fires", [
    (date(2027, 8, 1), False, True),     # 30 days before 31 August
    (date(2027, 7, 31), False, False),   # 31 days before
    (date(2027, 9, 5), False, True),     # past due
    (date(2027, 8, 20), True, False),    # already filed
])
def test_return_due_window(as_of, filed, fires):
    r = run(make(as_of=as_of, return_filed=filed))
    assert ("RETURN_DUE" in codes(r)) is fires


def test_return_due_uses_the_audit_date_for_an_audit_case():
    r = run(make(electronic=3000000, declared_profit=1200000, as_of=date(2027, 10, 10)))
    f = flag(r, "RETURN_DUE")
    assert "2027-10-31" in f.message and "IT2025:s263(1)" in f.citations


def test_advance_tax_single_instalment():
    base = dict(electronic=7000000)                  # payable 6,55,200 as in P3
    assert "ADVANCE_TAX_DUE" not in codes(run(make(**base, as_of=date(2027, 2, 12))))       # 31 days before
    r = run(make(**base, as_of=date(2027, 2, 13)))
    assert "ADVANCE_TAX_DUE" in codes(r) and "IT2025:s408(2)" in flag(r, "ADVANCE_TAX_DUE").citations
    assert "ADVANCE_TAX_DUE" not in codes(run(make(**base, as_of=date(2027, 3, 10), advance_tax_paid_inr=655200)))
    assert "ADVANCE_TAX_DUE" in codes(run(make(**base, as_of=date(2027, 3, 20), advance_tax_paid_inr=600000)))


def test_advance_tax_four_instalments_checks_the_instalment_that_is_due():
    base = dict(electronic=8000000, declared_profit=3000000)    # books profit: four instalments
    r = run(make(**base, as_of=date(2026, 6, 1)))
    first = r.compliance.advance_tax.instalments[0]
    assert "ADVANCE_TAX_DUE" in codes(r) and first.due in flag(r, "ADVANCE_TAX_DUE").message
    assert "IT2025:s408(1)" in flag(r, "ADVANCE_TAX_DUE").citations
    paid = run(make(**base, as_of=date(2026, 6, 1), advance_tax_paid_inr=first.cumulative_amount_inr))
    assert "ADVANCE_TAX_DUE" not in codes(paid)


def test_advance_tax_and_return_flags_need_a_date():
    assert not {"ADVANCE_TAX_DUE", "RETURN_DUE"} & set(codes(run(make(electronic=7000000))))


ALL_DOCS = dict(foreign_tin=True, foreign_tax_certificate=True, dtaa_article_and_rate=True,
                accountant_verification=True)


def test_ftc_docs_complete_clears_the_flag_and_the_window_brings_it_back():
    assert "FTC_DOCS_INCOMPLETE" not in codes(run(persona_input("P5", ftc_documents=ALL_DOCS)))
    r = run(persona_input("P5", ftc_documents=ALL_DOCS, as_of=date(2028, 3, 10), return_filed=True))
    assert "FTC_DOCS_INCOMPLETE" in codes(r) and "closes on 2028-03-31" in flag(r, "FTC_DOCS_INCOMPLETE").message
    done = run(persona_input("P5", ftc_documents=dict(ALL_DOCS, statement_filed=True), as_of=date(2028, 3, 10),
                             return_filed=True))
    assert "FTC_DOCS_INCOMPLETE" not in codes(done) and done.compliance.ftc_readiness.ready


def test_ftc_readiness_lists_what_is_missing():
    rd = run(persona_input("P5")).compliance.ftc_readiness
    status = {i.key: i.status for i in rd.items}
    assert status == {"foreign_tin": "missing", "foreign_tax_certificate": "missing",
                      "dtaa_article_and_rate": "missing", "accountant_verification": "missing",
                      "timely_return": "pending", "statement_filed": "pending"}
    assert all(i.citations for i in rd.items)


def test_a_late_return_makes_the_statement_unready():
    r = run(persona_input("P5", ftc_documents=ALL_DOCS, as_of=date(2027, 9, 15)))
    status = {i.key: i.status for i in r.compliance.ftc_readiness.items}
    assert status["timely_return"] == "missing" and "FTC_DOCS_INCOMPLETE" in codes(r)


def test_disputed_tax_adds_the_form_45_follow_up():
    r = run(persona_input("P5", ftc_documents=dict(ALL_DOCS, foreign_tax_disputed=True)))
    item = next(i for i in r.compliance.ftc_readiness.items if i.key == "disputed_tax")
    assert item.status == "pending" and "Form 45" in item.note and "RULES2026:r76(15)" in item.citations


def test_1961_year_uses_form_67_and_has_no_accountant_verification():
    eng = [dict(country_of_performance="US", amount_inr=800000, us_tax_withheld_inr=240000),
           dict(country_of_performance="IN", amount_inr=3200000)]
    r = run(make(2025, electronic=4000000, engagements=eng, us_days_by_year={2025: 95}))
    rd = r.compliance.ftc_readiness
    assert (rd.form, rd.rule, rd.statement_due) == ("Form 67", "Rule 128", "2027-03-31")
    verify = next(i for i in rd.items if i.key == "accountant_verification")
    assert verify.status == "not_required" and any(c.startswith("RULES1962:r128") for c in verify.citations)
    assert "FTC_DOCS_INCOMPLETE" in codes(r)


def test_fira_needs_both_the_reference_and_the_purpose_code():
    ok = [dict(amount_inr=100000, fira_ref="E1", purpose_code="P0802")]
    assert "FIRA_MISSING" not in codes(run(make(remittances=ok)))
    assert "FIRA_MISSING" in codes(run(make(remittances=[dict(amount_inr=100000, fira_ref="E1")])))
    assert "FIRA_MISSING" in codes(run(make(remittances=[dict(amount_inr=100000, purpose_code="P0802")])))


@pytest.mark.parametrize("electronic, lut, foreign, fires", [
    (2000000, False, True, True),      # exactly Rs 20 lakh
    (1999999, False, True, False),
    (4000000, None, True, False),      # LUT status unknown: not checked
    (4000000, True, True, False),
    (4000000, False, False, False),    # no exports
])
def test_gst_lut_boundary(electronic, lut, foreign, fires):
    r = run(make(electronic=electronic, lut_current=lut, foreign_clients=foreign))
    assert ("GST_LUT_MISSING" in codes(r)) is fires


@pytest.mark.parametrize("label, confidence, fires", [
    ("travel", "0.8", False),          # exactly the floor
    ("travel", "0.79", True),
    ("uncertain", "1.0", True),        # the abstain label always fires
])
def test_classification_confidence_boundary(label, confidence, fires):
    items = [dict(label=label, confidence=confidence, amount_inr=1000)]
    assert ("LOW_CLASSIFICATION_CONFIDENCE" in codes(run(make(expense_classifications=items)))) is fires


def test_classification_never_changes_income_or_tax():
    with_items = run(persona_input("P10"))
    without = run(persona_input("P10", expense_classifications=[]))
    assert with_items.income == without.income and with_items.india_tax == without.india_tax


# ---- deadline tracker (SRS/SDS FR-21) ----

def test_deadlines_are_scheduled_without_a_date_and_sorted():
    d = run(persona_input("P5")).compliance.deadlines
    keys = [x.key for x in d]
    assert keys == ["gst_lut", "advance_tax_1", "return", "ftc_statement"]
    assert [x.due for x in d] == sorted(x.due for x in d)
    assert all(x.status == "scheduled" and x.days_left is None for x in d)
    assert all(x.citations or x.source_note for x in d)


def test_deadline_statuses_from_the_as_of_date():
    r = run(persona_input("P5", as_of=date(2027, 3, 1), advance_tax_paid_inr=166400, lut_current=True))
    s = {x.key: (x.status, x.days_left) for x in r.compliance.deadlines}
    assert s["advance_tax_1"] == ("done", 14)
    assert s["gst_lut"][0] == "done"
    assert s["return"] == ("upcoming", 183)
    assert s["ftc_statement"][0] == "upcoming"


def test_four_instalments_and_w8ben_expiry_are_tracked():
    eng = [dict(label="Acme", country_of_performance="IN", amount_inr=1000000, w8ben_signed=date(2025, 2, 1))]
    r = run(make(electronic=8000000, declared_profit=3000000, engagements=eng, as_of=date(2026, 9, 1),
                 advance_tax_paid_inr=Decimal(200000)))
    s = {x.key: x for x in r.compliance.deadlines}
    assert [k for k in s if k.startswith("advance_tax_")] == ["advance_tax_1", "advance_tax_2", "advance_tax_3",
                                                               "advance_tax_4"]
    assert s["advance_tax_1"].status == "done" and s["advance_tax_2"].status == "due_soon"
    assert s["w8ben:Acme"].due == "2028-12-31" and "IRS_W8BEN:validity" in s["w8ben:Acme"].citations


def test_engine_never_reads_the_clock():
    engine = Path(__file__).resolve().parents[2] / "engine"
    for f in engine.rglob("*.py"):
        text = f.read_text(encoding="utf8")
        assert "today(" not in text and "now(" not in text, f.name
