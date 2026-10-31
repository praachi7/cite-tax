"""Assumption-flag variants: an existing persona rerun with one flag switched.

These show that each contested point can be changed through config alone, with no code change,
and that the result then records the other reading.
"""
from pathlib import Path

import yaml

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.pipeline import run

PERSONAS = Path(__file__).parent / "personas"


def persona(pid, **overrides):
    data = yaml.safe_load((PERSONAS / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]
    data.update(overrides)
    return TaxpayerInput(**data)


def codes(r):
    return [f.code for f in r.flags]


def test_p1_with_a16_indian_source_reading_gives_itr4():
    # A-16 reading a: work done in India for a foreign client is Indian-source, so ITR-4 stays available.
    r = run(persona("P1"), EngineConfig.defaults(itr4_foreign_client_income_is_indian_source=True))
    assert r.compliance.itr_form == "ITR-4" and r.compliance.itr_form_reasons == []
    assert r.compliance.depends_on_contested == []
    assert next(a for a in r.assumptions_applied if a["id"] == "A-16")["reading"] == "a"


def test_p1_default_is_itr3_and_says_it_rests_on_a16():
    r = run(persona("P1"))
    assert r.compliance.itr_form == "ITR-3" and r.compliance.depends_on_contested == ["A-16"]
    assert r.compliance.itr4_possible_under_other_reading


def test_p7_with_a12_transit_wallet_reading_drops_the_a12_bar_only():
    r = run(persona("P7"), EngineConfig.defaults(platform_wallet_is_foreign_asset=False))
    assert r.compliance.itr_form == "ITR-3" and r.compliance.depends_on_contested == ["A-16"]
    assert "SCHEDULE_FA_REQUIRED" not in codes(r)


def test_p7_with_both_contested_points_resolved_the_other_way_gives_itr4():
    cfg = EngineConfig.defaults(platform_wallet_is_foreign_asset=False, itr4_foreign_client_income_is_indian_source=True)
    r = run(persona("P7"), cfg)
    assert r.compliance.itr_form == "ITR-4" and "SCHEDULE_FA_REQUIRED" not in codes(r)


def test_p7_stated_foreign_assets_are_a_firm_bar_whatever_the_flags():
    cfg = EngineConfig.defaults(platform_wallet_is_foreign_asset=False, itr4_foreign_client_income_is_indian_source=True)
    r = run(persona("P7", foreign_assets_held=True), cfg)
    assert r.compliance.itr_form == "ITR-3" and not r.compliance.itr4_possible_under_other_reading
    assert "SCHEDULE_FA_REQUIRED" in codes(r)


def test_p5_with_a5_gross_receipts_reading_raises_the_credit():
    # reading b: cap = 2,08,000 x 8,00,000 / 20,00,000 = 83,200; credit 83,200; unrelieved 1,56,800
    r = run(persona("P5"), EngineConfig.defaults(ftc_cap_basis="gross_receipts"))
    f = r.relief.ftc
    assert (f.cap_inr, f.credit_inr, f.unrelieved_inr, f.cap_basis) == (83200, 83200, 156800, "gross_receipts")
    assert r.compliance.advance_tax.net_tax_inr == 124800        # 2,08,000 - 83,200
    assert next(a for a in r.assumptions_applied if a["id"] == "A-5")["reading"] == "b"


def test_p2_with_a3_unclear_eligibility_reading_removes_presumptive_taxation():
    off = EngineConfig.defaults(it_specified_profession_1961=False)
    r = run(persona("P2"), off)
    assert r.eligibility.failed == ["PROFESSION_NOT_SPECIFIED"] and not r.income.scheme_available
    assert r.india_tax is None and "PROFIT_REQUIRED" in codes(r)
    # with books profit supplied, tax is worked out on it and the return is ITR-3
    r = run(persona("P2", declared_profit=1200000), off)
    assert r.income.basis == "books_profit" and r.compliance.itr_form_reasons == ["NOT_PRESUMPTIVE"]
    assert next(a for a in r.assumptions_applied if a["id"] == "A-3")["reading"] == "b"
