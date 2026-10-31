"""Unit tests for step 10: ITR form, advance tax and return due dates."""
import pytest

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.pipeline import run

A16_OFF = EngineConfig.defaults(itr4_foreign_client_income_is_indian_source=True)   # no contested bar


def make(tax_year=2026, electronic=2400000, **kw):
    return TaxpayerInput(tax_year=tax_year, receipts=dict(electronic=electronic), **kw)


# ---- advance tax threshold (s.208 / s.404: Rs 10,000), applied after rounding to Rs 10 ----

def test_advance_tax_just_below_the_threshold_is_not_required():
    # income 12,09,600: tax capped at 9,600 (marginal relief), cess 384, 9,984 rounds to 9,980
    r = run(make(electronic=2419200))
    assert r.india_tax.in_force.payable == 9980
    assert not r.compliance.advance_tax.required and r.compliance.advance_tax.schedule == "none"


def test_advance_tax_at_the_threshold_after_rounding_is_required():
    # income 12,09,620: tax 9,620, cess 384.80, 10,004.80 rounds to 10,000
    r = run(make(electronic=2419240))
    assert r.india_tax.in_force.payable == 10000
    assert r.compliance.advance_tax.required and r.compliance.advance_tax.schedule == "single_instalment"


def test_foreign_tax_credit_reduces_advance_tax_and_can_remove_it():
    eng = [dict(country_of_performance="US", amount_inr=2000000, us_tax_withheld_inr=500000),
           dict(country_of_performance="IN", amount_inr=2000000)]
    r = run(make(electronic=4000000, engagements=eng, us_days_by_year={2026: 95}))
    # payable 2,08,000, credit = cap 1,04,000, so advance tax 1,04,000
    assert r.compliance.advance_tax.net_tax_inr == 104000


def test_single_instalment_carries_the_one_percent_shortfall_rate():
    a = run(make(electronic=7000000)).compliance.advance_tax
    assert a.shortfall_interest_percent == 1 and len(a.instalments) == 1
    assert a.instalments[0].due == "2027-03-15" and a.instalments[0].cumulative_percent == 100


def test_1961_year_dates_fall_in_the_right_calendar_years():
    a = run(make(2025, electronic=7000000)).compliance.advance_tax
    assert a.instalments[0].due == "2026-03-15"
    books = run(make(2025, electronic=8000000, declared_profit=3000000)).compliance.advance_tax
    assert [i.due for i in books.instalments] == ["2025-06-15", "2025-09-15", "2025-12-15", "2026-03-15"]
    assert [i.cumulative_percent for i in books.instalments] == [15, 45, 75, 100]


# ---- return due date ----

def test_audit_case_return_is_due_on_31_october_and_other_cases_on_31_august():
    assert run(make()).compliance.return_due_date == "2027-08-31"
    audit = run(make(electronic=8000000, declared_profit=3000000))
    assert audit.compliance.return_due_date == "2027-10-31" and audit.compliance.return_due_basis == "audit_case"
    assert run(make(2025)).compliance.return_due_date == "2026-08-31"
    assert run(make(2025, electronic=8000000, declared_profit=3000000)).compliance.return_due_date == "2026-10-31"


# ---- ITR form ----

def test_itr4_is_chosen_when_no_bar_applies():
    r = run(make(foreign_clients=False))
    assert r.compliance.itr_form == "ITR-4" and r.compliance.itr4_bars == []


def test_total_income_over_fifty_lakh_bars_itr4():
    r = run(make(electronic=7000000, declared_profit=5100000, foreign_clients=False))
    assert r.compliance.itr_form == "ITR-3" and r.compliance.itr_form_reasons == ["total_income_over_limit"]
    assert not r.compliance.itr4_possible_under_other_reading


def test_total_income_of_exactly_fifty_lakh_does_not_bar_itr4():
    r = run(make(electronic=7000000, declared_profit=5000000, foreign_clients=False))
    assert r.compliance.itr_form == "ITR-4"


def test_a_client_who_is_a_us_person_counts_as_a_foreign_client_even_if_the_flag_is_off():
    eng = [dict(country_of_performance="IN", amount_inr=1000000, client_is_us_person=True)]
    r = run(make(foreign_clients=False, engagements=eng))
    assert [b.bar for b in r.compliance.itr4_bars] == ["foreign_source_income"]


def test_other_bars_come_from_the_input_and_must_be_known_to_the_act():
    r = run(make(foreign_clients=False, other_itr4_bars=["company_director"]))
    assert r.compliance.itr_form == "ITR-3" and r.compliance.itr_form_reasons == ["company_director"]
    with pytest.raises(ValueError):
        run(make(foreign_clients=False, other_itr4_bars=["no_such_bar"]))
    # the 2025-Act rule has a Section 93 bar that the 1961 rule does not
    assert run(make(foreign_clients=False, other_itr4_bars=["deduction_s93_claimed"])).compliance.itr_form == "ITR-3"
    with pytest.raises(ValueError):
        run(make(2025, foreign_clients=False, other_itr4_bars=["deduction_s93_claimed"]))


def test_the_form_choice_names_the_act_specific_form_rules():
    r = run(make())
    cites = {c for t in r.trace if t.rule_id == "ENG.10.itr_form" for c in t.citations}
    assert any(c.startswith("RULES2026:r164") for c in cites)
    cites61 = {c for t in run(make(2025)).trace if t.rule_id == "ENG.10.itr_form" for c in t.citations}
    assert any(c.startswith("RULES1962:r12") for c in cites61)
