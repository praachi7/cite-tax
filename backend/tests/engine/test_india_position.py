"""Unit tests for steps 1 to 5, including the boundary values the personas do not reach."""
from decimal import Decimal

import pytest

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.money import D, round_to_multiple
from engine.params import ParamSet, UnsupportedTaxYear
from engine.pipeline import run

LAKH = 100000


def make(tax_year=2026, electronic=0, cash=0, cheque=0, **kw):
    return TaxpayerInput(tax_year=tax_year, receipts=dict(electronic=electronic, cash=cash, non_account_payee_cheque=cheque), **kw)


# ---- rounding: s.288A and s.288B (1961), s.516 (2025) ----

@pytest.mark.parametrize("amount, want", [
    ("1200004.99", 1200000), ("1200005", 1200010), ("1200005.99", 1200010), ("1200009", 1200010),
    ("1200000", 1200000), ("14", 10), ("15", 20), ("0", 0)])
def test_rounding_to_nearest_ten_ignores_paise_first(amount, want):
    assert round_to_multiple(D(amount), 10) == want


def test_money_refuses_floats():
    with pytest.raises(TypeError):
        D(1.5)


def test_total_income_is_rounded_before_the_slabs_are_applied():
    # 12,00,004 rounds down to 12,00,000: still within the rebate limit, so nil tax
    r = run(make(electronic=2400009, declared_profit=1200004))
    assert r.india_tax.in_force.total_income == 1200000
    assert r.india_tax.in_force.payable == 0


# ---- marginal relief above the rebate limit (s.156(2)(b), s.87A) ----

def test_marginal_relief_just_above_twelve_lakh():
    # income 12,10,000: slab tax 60,000 + 1,500 = 61,500; capped at 10,000 (the excess over 12L); cess 400
    r = run(make(electronic=2420000))
    t = r.india_tax.in_force
    assert (t.total_income, t.slab_tax, t.tax_after_rebate, t.rebate, t.cess, t.payable) == (
        1210000, Decimal("61500"), 10000, Decimal("51500"), 400, 10400)


def test_marginal_relief_stops_where_slab_tax_is_lower_than_the_excess():
    # income 13,00,000: slab tax 60,000 + 15,000 = 75,000; the excess over 12L is 1,00,000, so no relief
    t = run(make(electronic=2600000)).india_tax.in_force
    assert (t.slab_tax, t.rebate, t.payable) == (75000, 0, 78000)


def test_old_regime_rebate_applies_to_income_up_to_five_lakh():
    r = run(make(electronic=1000000, regime_choice="old"))   # income 5,00,000: tax 12,500, rebate 12,500
    assert (r.india_tax.in_force.slab_tax, r.india_tax.in_force.rebate, r.india_tax.in_force.payable) == (12500, 12500, 0)


def test_surcharge_guard_fires_only_above_fifty_lakh():
    r = run(make(electronic=15000000, declared_profit=6000000))   # not presumptive-eligible; books profit 60L
    assert r.india_tax.in_force.surcharge > 0
    assert "SURCHARGE_APPROXIMATE" in [f.code for f in r.flags]
    assert run(make(electronic=7000000)).india_tax.in_force.surcharge == 0


# ---- step 3: receipts limit boundaries (s.58(2) Sl.3, s.44ADA(1) provisos) ----

def test_exactly_fifty_lakh_is_within_the_limit():
    r = run(make(electronic=4700000, cash=300000))   # 6% cash: limit Rs 50 lakh, receipts exactly 50 lakh
    assert r.receipts_test.applicable_limit == 5000000 and r.receipts_test.within_limit
    assert r.income.scheme_available


def test_one_rupee_over_fifty_lakh_with_high_cash_is_outside():
    r = run(make(electronic=4700001, cash=300000, declared_profit=2000000))
    assert not r.receipts_test.within_limit and not r.income.scheme_available


def test_cash_of_exactly_five_percent_keeps_the_seventy_five_lakh_limit():
    r = run(make(electronic=6650000, cash=350000))   # exactly 5%
    assert r.receipts_test.low_cash and r.receipts_test.applicable_limit == 7500000


def test_cash_just_over_five_percent_drops_the_limit():
    r = run(make(electronic=6649999, cash=350001, declared_profit=3000000))
    assert not r.receipts_test.low_cash and r.receipts_test.applicable_limit == 5000000


def test_non_account_payee_cheques_count_as_cash():
    r = run(make(electronic=6000000, cheque=1000000, declared_profit=3000000))   # 1/7 = 14.3% "cash"
    assert r.receipts_test.cash_like == 1000000 and not r.receipts_test.low_cash


def test_exactly_seventy_five_lakh_is_within_and_over_is_not():
    assert run(make(electronic=7500000)).income.scheme_available
    assert not run(make(electronic=7500001, declared_profit=3000000)).income.scheme_available


def test_receipts_near_limit_flag_boundary():
    flags = lambda e: [f.code for f in run(make(electronic=e)).flags]
    assert "RECEIPTS_NEAR_LIMIT" in flags(6750000)      # exactly 90% of 75 lakh
    assert "RECEIPTS_NEAR_LIMIT" not in flags(6749999)


# ---- step 2: eligibility ----

@pytest.mark.parametrize("kw, code", [
    (dict(entity_type="huf"), "ENTITY_NOT_ELIGIBLE"),
    (dict(entity_type="llp"), "ENTITY_NOT_ELIGIBLE"),
    (dict(entity_type="company"), "ENTITY_NOT_ELIGIBLE"),
    (dict(residential_status="non_resident"), "NOT_RESIDENT"),
    (dict(profession="not_specified"), "PROFESSION_NOT_SPECIFIED"),
])
def test_ineligible_taxpayers_are_refused_with_the_reason(kw, code):
    r = run(make(electronic=2400000, declared_profit=1200000, **kw))
    assert not r.eligibility.eligible and code in r.eligibility.failed
    assert not r.income.scheme_available and r.income.basis == "books_profit"


def test_non_llp_firm_and_rnor_are_eligible():
    assert run(make(electronic=2400000, entity_type="non_llp_firm")).eligibility.eligible
    assert run(make(electronic=2400000, residential_status="rnor")).eligibility.eligible


def test_other_specified_profession_is_eligible():
    assert run(make(electronic=2400000, profession="other_specified")).eligibility.eligible


def test_ineligible_without_profit_gives_a_blocker_and_no_tax():
    r = run(make(electronic=2400000, entity_type="huf"))
    assert r.income.income is None and r.india_tax is None
    assert "PROFIT_REQUIRED" in [f.code for f in r.flags]


def test_assumption_a3_switches_it_eligibility_for_1961_only():
    off = EngineConfig.defaults(it_specified_profession_1961=False)
    assert not run(make(2025, electronic=2400000, declared_profit=1200000), off).eligibility.eligible
    assert run(make(2026, electronic=2400000), off).eligibility.eligible   # the 2025 Act names IT in s.62(4)


# ---- step 4: declared profit ----

def test_higher_declared_profit_is_taxed_as_declared():
    r = run(make(electronic=2400000, declared_profit=1500000))
    assert r.income.basis == "declared_higher" and r.income.income == 1500000 and not r.income.books_audit_required


def test_declared_lower_but_within_exemption_limit_needs_no_audit():
    r = run(make(electronic=600000, declared_profit=250000))   # 50% would be 3,00,000; declared 2,50,000 < 4,00,000
    assert r.income.basis == "declared_lower" and not r.income.books_audit_required


def test_exemption_limit_depends_on_the_regime_in_force():
    # declared 3,00,000: above the old-regime limit 2,50,000, below the new-regime limit 4,00,000
    new = run(make(electronic=1000000, declared_profit=300000, regime_choice="new"))
    old = run(make(electronic=1000000, declared_profit=300000, regime_choice="old"))
    assert not new.income.books_audit_required and old.income.books_audit_required


def test_high_receipts_do_not_trigger_audit_for_a_presumptive_declarant():
    r = run(make(electronic=7000000))
    assert not r.income.tax_audit_required and r.income.audit_note


# ---- step 1: Act selection and regime history ----

def test_act_follows_the_tax_year():
    assert run(make(2025, electronic=100000)).act.act_id == "IT1961"
    assert run(make(2026, electronic=100000)).act.act_id == "IT2025"


def test_unsupported_tax_year_is_refused():
    with pytest.raises(UnsupportedTaxYear):
        run(make(2024, electronic=100000))


def test_first_opt_out_under_1961_needs_form_10iea():
    r = run(make(2025, electronic=2400000, regime_choice="old"))
    assert r.regime.regime_in_force.value == "old" and r.regime.filing == "Form 10-IEA"
    assert not r.regime.opt_out_barred_after


def test_first_opt_out_under_2025_is_made_in_the_return():
    assert run(make(2026, electronic=2400000, regime_choice="old")).regime.filing == "return_of_income"


def test_continuing_in_the_old_regime_needs_no_new_filing():
    r = run(make(2026, electronic=2400000, regime_choice="old",
                 election_history=[dict(tax_year=2025, regime="old")]))
    assert r.regime.regime_in_force.value == "old" and r.regime.filing is None


def test_second_opt_out_after_withdrawal_is_refused_and_new_regime_applied():
    hist = [dict(tax_year=2023, regime="old"), dict(tax_year=2024, regime="new"), dict(tax_year=2025, regime="new")]
    r = run(make(2026, electronic=2400000, regime_choice="old", election_history=hist))
    assert r.regime.overridden and r.regime.regime_in_force.value == "new"
    assert "REGIME_OPT_OUT_BARRED" in [f.code for f in r.flags]
    assert r.india_tax.in_force.regime.value == "new"


def test_history_with_an_opt_out_after_withdrawal_is_reported():
    hist = [dict(tax_year=2022, regime="old"), dict(tax_year=2023, regime="new"), dict(tax_year=2024, regime="old")]
    r = run(make(2026, electronic=2400000, election_history=hist))
    assert "REGIME_HISTORY_INCONSISTENT" in [f.code for f in r.flags]


def test_history_must_hold_earlier_years_only_and_no_duplicates():
    with pytest.raises(ValueError):
        make(2026, electronic=1, election_history=[dict(tax_year=2026, regime="old")])
    with pytest.raises(ValueError):
        make(2026, electronic=1, election_history=[dict(tax_year=2025, regime="old"), dict(tax_year=2025, regime="new")])


# ---- parameters and traceability ----

def test_every_parameter_key_the_steps_read_exists_in_both_act_files():
    # run() reads keys through ParamSet.get, which raises KeyError on an unknown key
    for year in (2025, 2026):
        run(make(year, electronic=2400000, declared_profit=1500000))
        run(make(year, electronic=2400000, regime_choice="old"))
        run(make(year, electronic=8000000, declared_profit=2000000))


def test_unknown_parameter_key_is_an_error():
    with pytest.raises(KeyError):
        ParamSet.for_tax_year(2026).get("no.such.key")


def test_result_records_which_assumptions_were_applied():
    r = run(make(electronic=2400000))
    a16 = next(a for a in r.assumptions_applied if a["id"] == "A-16")
    assert a16["is_default"] and a16["reading"] == "b" and a16["status"] == "contested"
    off = run(make(electronic=2400000), EngineConfig.defaults(itr4_foreign_client_income_is_indian_source=True))
    assert next(a for a in off.assumptions_applied if a["id"] == "A-16")["reading"] == "a"


def test_config_defaults_equal_the_assumptions_register():
    from lawdata.loader import load_assumptions
    cfg = EngineConfig.defaults()
    for a in load_assumptions():
        assert getattr(cfg, a.config_flag) == a.config_default


def test_regime_comparison_picks_the_cheaper_and_reports_the_saving():
    r = run(make(2026, electronic=4000000, regime_choice="old"))   # income 20L: old 4,29,000 vs new 2,08,000
    assert r.india_tax.cheaper.value == "new" and r.india_tax.saving_inr == 429000 - 208000
