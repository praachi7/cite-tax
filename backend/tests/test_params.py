import pytest
from pydantic import ValidationError

from lawdata import validate
from lawdata.loader import PARAMS_DIR, load_all_param_files
from lawdata.models import Param, ParamFile, ParamScope, Status

FILES = load_all_param_files(PARAMS_DIR)
Y1961 = FILES["it1961_fy2025-26.yaml"]
Y2025 = FILES["it2025_ty2026-27.yaml"]
COMMON = FILES["common.yaml"]


def val(pf, key):
    return pf.params[key].value


def test_all_parameter_files_are_consistent():
    assert validate.check_param_files() == []


def test_the_two_year_files_define_identical_keys():
    assert set(Y1961.params) == set(Y2025.params)


def test_year_files_are_for_the_right_act_and_year():
    assert (Y1961.act_id.value, Y1961.rules_id.value, Y1961.tax_year) == ("IT1961", "RULES1962", 2025)
    assert (Y2025.act_id.value, Y2025.rules_id.value, Y2025.tax_year) == ("IT2025", "RULES2026", 2026)
    assert COMMON.scope == ParamScope.common


@pytest.mark.parametrize("pf", [Y1961, Y2025, COMMON], ids=["1961", "2025", "common"])
def test_every_non_design_value_has_a_source(pf):
    for key, p in pf.params.items():
        if p.status != Status.design_choice:
            assert p.sources, key
        else:
            assert not p.sources, key


@pytest.mark.parametrize("pf", [Y1961, Y2025], ids=["1961", "2025"])
def test_slabs_are_contiguous_and_rising(pf):
    for key in ("regime.new.slabs", "regime.old.slabs"):
        rows = val(pf, key)
        assert rows[0][0] == 0
        assert rows[-1][1] is None
        for a, b in zip(rows, rows[1:]):
            assert a[1] == b[0], key
            assert a[2] < b[2], key


def test_new_regime_slabs_are_identical_in_both_years():
    assert val(Y1961, "regime.new.slabs") == val(Y2025, "regime.new.slabs")


def test_known_values_from_the_statute():
    for pf in (Y1961, Y2025):
        assert val(pf, "presumptive.profession.rate_percent") == 50
        assert val(pf, "presumptive.profession.limit_inr") == 5_000_000
        assert val(pf, "presumptive.profession.limit_low_cash_inr") == 7_500_000
        assert val(pf, "regime.new.rebate.max_inr") == 60_000
        assert val(pf, "regime.new.rebate.income_limit_inr") == 1_200_000
        assert val(pf, "tax.cess_percent") == 4
        assert val(pf, "advance_tax.threshold_inr") == 10_000
        assert val(pf, "advance_tax.presumptive.single_instalment_due") == "03-15"
        assert val(pf, "return.due_date_business_profession_non_audit") == "08-31"
    assert val(COMMON, "treaty.art15.stay_days_threshold") == 90


def test_huf_is_not_eligible_for_the_profession_scheme():
    for pf in (Y1961, Y2025):
        assert "huf" not in val(pf, "presumptive.profession.eligible_entities")


def test_the_forms_differ_between_the_acts():
    assert val(Y1961, "ftc.form") == "Form 67" and val(Y2025, "ftc.form") == "Form 44"
    assert val(Y1961, "ftc.accountant_verification_threshold_inr") is None
    assert val(Y2025, "ftc.accountant_verification_threshold_inr") == 100_000


def test_no_value_is_left_unverified():
    for name, pf in FILES.items():
        for key, p in pf.params.items():
            assert p.status != Status.to_verify, f"{name}: {key}"


def test_the_opt_out_route_differs_between_the_acts():
    assert val(Y1961, "regime.opt_out_form") == "Form 10-IEA"
    assert val(Y2025, "regime.opt_out_form") == "return_of_income"


def test_surcharge_starts_at_50_lakh_in_both_years():
    for pf in (Y1961, Y2025):
        assert val(pf, "tax.surcharge.start_income_inr") == 5_000_000
        assert val(pf, "tax.surcharge.first_rate_percent") == 10


def test_design_choice_needs_no_source_but_law_does():
    Param(value=1, status="design_choice")
    with pytest.raises(ValidationError):
        Param(value=1, status="verified")


def test_a_year_file_needs_its_identity():
    with pytest.raises(ValidationError):
        ParamFile(label="x", params={})
