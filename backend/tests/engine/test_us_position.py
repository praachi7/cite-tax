"""Unit tests for steps 6 to 9: substantial presence, source rule, Article 15 and relief routing."""
from decimal import Decimal

import pytest

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.params import ParamSet
from engine.pipeline import run


def make(tax_year=2026, electronic=4000000, engagements=(), days=None, **kw):
    return TaxpayerInput(tax_year=tax_year, receipts=dict(electronic=electronic), engagements=list(engagements),
                         us_days_by_year=days or {}, **kw)


def eng(country="US", amount=800000, withheld=0, **kw):
    return dict(label=kw.pop("label", country), country_of_performance=country, amount_inr=amount,
                us_tax_withheld_inr=withheld, **kw)


def codes(r):
    return [f.code for f in r.flags]


# ---- step 6: substantial presence test (Pub. 519) ----

@pytest.mark.parametrize("days, expected", [
    ({2026: 120, 2025: 150, 2024: 180}, True),    # 120 + 50 + 30 = 200
    ({2026: 183}, True),                          # exactly 183 current-year days
    ({2026: 182}, False),
    ({2026: 100, 2025: 150, 2024: 198}, True),    # 100 + 50 + 33 = exactly 183
    ({2026: 100, 2025: 150, 2024: 197}, False),   # one day short
    ({2026: 31, 2025: 300, 2024: 300}, False),    # 31 + 100 + 50 = 181
])
def test_substantial_presence_weighting(days, expected):
    assert run(make(days=days)).us_presence.substantial_presence is expected


def test_fewer_than_31_current_days_never_meets_the_test():
    r = run(make(days={2026: 30, 2025: 365, 2024: 365}))   # weighted 30 + 121.67 + 60.83 is above 183
    assert r.us_presence.met_weighted and not r.us_presence.met_current_minimum
    assert not r.us_presence.substantial_presence


def test_spt_met_sends_relief_to_manual_review():
    r = run(make(engagements=[eng(withheld=240000)], days={2026: 200}))
    assert r.relief.route == "manual_review" and r.relief.ftc is None
    assert "US_SUBSTANTIAL_PRESENCE" in codes(r)


def test_us_calendar_year_defaults_to_the_first_year_and_can_be_overridden():
    days = {2026: 10, 2027: 95}
    assert run(make(days=days)).us_presence.days_current == 10
    assert run(make(days=days, us_calendar_year=2027)).us_presence.days_current == 95


# ---- step 7: source rule ----

def test_work_done_in_india_is_not_us_source_even_for_a_us_client():
    r = run(make(engagements=[eng("IN", 4000000)], days={2026: 120}))
    assert not r.us_source.any_us_source and r.us_source.engagements[0].reason == "PERFORMED_OUTSIDE_US"


def test_work_done_in_the_us_is_us_source():
    r = run(make(engagements=[eng("US"), eng("IN", 3000000)]))
    assert r.us_source.us_source_inr == 800000


@pytest.mark.parametrize("days, usd, us_client, expected_us_source", [
    (60, 2500, False, False),     # de minimis applies
    (60, 3000, False, False),     # exactly $3,000
    (60, 3001, False, True),      # over $3,000
    (90, 2500, False, False),     # exactly 90 days
    (91, 2500, False, True),      # over 90 days
    (60, 2500, True, True),       # a US-person client defeats the exception
    (60, None, False, True),      # unknown dollar amount: treated as US-source
])
def test_de_minimis_exception(days, usd, us_client, expected_us_source):
    e = eng("US", 200000, amount_usd=usd, client_is_us_person=us_client)
    r = run(make(engagements=[e], days={2026: days}))
    assert r.us_source.engagements[0].us_source is expected_us_source


# ---- step 8: Article 15 ----

def test_threshold_matches_the_irs_89_day_figure():
    c = ParamSet.for_tax_year(2026)
    assert c.get("treaty.art15.stay_days_threshold") - 1 == c.get("treaty.art15.us_exemption_max_days")


@pytest.mark.parametrize("days, may_tax, basis", [(89, False, "exempt"), (90, True, "days_threshold"), (95, True, "days_threshold")])
def test_ninety_days_is_the_trigger(days, may_tax, basis):
    r = run(make(engagements=[eng()], days={2026: days}))
    assert (r.treaty.us_may_tax, r.treaty.basis) == (may_tax, basis)


def test_fixed_base_triggers_with_few_days():
    r = run(make(engagements=[eng()], days={2026: 10}, us_fixed_base=True))
    assert r.treaty.basis == "fixed_base" and "US_FIXED_BASE" in codes(r)


def test_treaty_is_not_reached_without_us_source_income():
    r = run(make(engagements=[eng("IN", 4000000)], days={2026: 120}))
    assert not r.treaty.reached and r.treaty.basis == "not_reached"


@pytest.mark.parametrize("days, present, trigger", [(79, False, False), (80, True, False), (89, True, False), (90, False, True)])
def test_us_days_warning_and_trigger_flags(days, present, trigger):
    c = codes(run(make(engagements=[eng()], days={2026: days})))
    assert ("US_DAYS_WARNING" in c) is present and ("ARTICLE_15_TRIGGERED" in c) is trigger


# ---- step 9: relief routing ----

def p5_like(**kw):
    return make(engagements=[eng("US", 800000, 240000), eng("IN", 3200000)], days={2026: 95}, **kw)


def test_credit_is_capped_at_indian_tax_attributable_to_the_us_income():
    # income 20,00,000: tax 2,00,000 + cess 8,000 = 2,08,000; US receipts are 8L of 40L, so cap = 41,600 (A-5 reading a)
    f = run(p5_like()).relief.ftc
    assert (f.foreign_tax_inr, f.cap_inr, f.credit_inr, f.unrelieved_inr) == (240000, Decimal("41600"), Decimal("41600"), Decimal("198400"))
    assert (f.form, f.rule, f.cap_basis) == ("Form 44", "Rule 76", "deemed_income")
    assert run(p5_like()).relief.route == "credit"


def test_assumption_a5_gross_receipts_reading_raises_the_cap():
    f = run(p5_like(), EngineConfig.defaults(ftc_cap_basis="gross_receipts")).relief.ftc
    assert f.cap_inr == Decimal("83200") and f.cap_basis == "gross_receipts"   # 2,08,000 x 8L / 20L


def test_credit_is_the_foreign_tax_when_that_is_lower_than_the_cap():
    r = run(make(engagements=[eng("US", 2000000, 10000), eng("IN", 2000000)], days={2026: 95}))
    f = r.relief.ftc    # cap = 2,08,000 x 20L / 40L = 1,04,000; foreign tax 10,000 is lower
    assert f.cap_inr == Decimal("104000") and f.credit_inr == 10000 and f.unrelieved_inr == 0


def test_no_credit_when_indian_tax_is_nil():
    r = run(make(electronic=2400000, engagements=[eng("US", 800000, 240000), eng("IN", 1600000)], days={2026: 95}))
    assert r.relief.ftc.cap_inr == 0 and r.relief.ftc.credit_inr == 0 and r.relief.ftc.unrelieved_inr == 240000


def test_1961_year_uses_form_67_and_its_own_deadline():
    f = run(p5_like_year(2025)).relief.ftc
    assert (f.form, f.rule, f.statement_due, f.accountant_verification) == ("Form 67", "Rule 128", "2027-03-31", False)
    assert run(p5_like()).relief.ftc.statement_due == "2028-03-31"


def p5_like_year(y):
    return make(y, engagements=[eng("US", 800000, 240000), eng("IN", 3200000)], days={y: 95})


def test_2025_act_needs_accountant_verification_from_one_lakh_of_foreign_tax():
    r = run(p5_like())
    assert r.relief.ftc.accountant_verification and "FTC_ACCOUNTANT_VERIFICATION" in codes(r)
    small = run(make(engagements=[eng("US", 800000, 99999), eng("IN", 3200000)], days={2026: 95}))
    assert not small.relief.ftc.accountant_verification


def test_remote_work_withholding_is_a_refund_not_a_credit():
    e = eng("IN", 4000000, 1200000, w8ben_on_file=False)      # 30% withheld, no W-8BEN
    r = run(make(engagements=[e], days={2026: 0}))
    assert r.relief.route == "refund" and r.relief.ftc is None
    assert r.relief.refunds[0].reason == "NOT_US_SOURCE" and r.relief.refunds[0].amount_inr == 1200000
    assert r.relief.refunds[0].forms == ["Form 1040-NR", "Form W-8BEN"]
    assert "W8BEN_MISSING" in codes(r)


def test_treaty_exempt_us_work_withholding_is_refundable():
    r = run(make(engagements=[eng("US", 800000, 240000)], days={2026: 85}))
    assert r.relief.route == "refund" and r.relief.refunds[0].reason == "TREATY_EXEMPT"
    assert r.relief.refunds[0].forms == ["Form 1040-NR", "Form 8233"] and "US_DAYS_WARNING" in codes(r)


def test_credit_and_refund_can_both_apply():
    r = run(make(engagements=[eng("US", 800000, 240000), eng("IN", 3200000, 50000)], days={2026: 95}))
    assert r.relief.route == "credit_and_refund"
    assert r.relief.refunds[0].reason == "NOT_US_SOURCE" and r.relief.ftc.credit_inr > 0


def test_nothing_withheld_means_no_relief_route():
    r = run(make(engagements=[eng("US", 800000, 0)], days={2026: 95}))
    assert r.relief.route == "none" and r.relief.ftc is None and "US_RETURN_REQUIRED" in codes(r)


def test_no_us_facts_at_all_gives_none():
    r = run(make())
    assert r.relief.route == "none" and not r.treaty.reached and not r.us_presence.substantial_presence


def test_engagements_cannot_exceed_total_receipts():
    with pytest.raises(ValueError):
        make(electronic=100, engagements=[eng(amount=200)])


def test_every_us_step_logs_a_rule_id_and_citations():
    r = run(p5_like())
    ids = [t.rule_id for t in r.trace]
    for rid in ("ENG.06.substantial_presence", "ENG.07.source_rule", "ENG.08.article_15", "ENG.09.relief"):
        assert rid in ids
    assert all(t.citations for t in r.trace if t.step in (6, 8, 9))
