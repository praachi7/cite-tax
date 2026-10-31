import pytest
from pydantic import ValidationError

from lawdata import validate
from lawdata.loader import load_assumptions
from lawdata.models import Assumption

A = {a.id: a for a in load_assumptions()}


def test_assumptions_are_consistent():
    assert validate.check_assumptions() == []


def test_the_four_expected_assumptions_exist():
    assert set(A) == {"A-3", "A-5", "A-12", "A-16"}


def test_a3_is_resolved_and_the_others_are_contested():
    assert A["A-3"].status.value == "resolved"
    assert all(A[i].status.value == "contested" for i in ("A-5", "A-12", "A-16"))


def test_conservative_defaults():
    # A-5: cap at Indian tax on deemed income (under-claims, never over-claims)
    assert A["A-5"].config_default == "deemed_income"
    # A-12: treat platform balances as foreign assets (over-disclosure is harmless)
    assert A["A-12"].config_default is True
    # A-16: do not treat US-client fees as Indian-source, so ITR-3 is recommended
    assert A["A-16"].config_default is False
    # A-3: IT is a notified profession
    assert A["A-3"].config_default is True


def test_every_contested_assumption_shows_two_readings_with_citations():
    for a in A.values():
        if a.status.value == "contested":
            assert len(a.readings) >= 2
            assert all(r.citations for r in a.readings)


def test_the_default_reading_matches_the_flag_value():
    for a in A.values():
        chosen = next(r for r in a.readings if r.key == a.default)
        assert chosen.flag_value == a.config_default


def _base(**over):
    d = dict(id="A-1", question="q", status="contested", default="a", default_reason="r",
             config_flag="flag_one", config_default=True,
             readings=[dict(key="a", statement="s", citations=["IT2025:s1"], flag_value=True),
                       dict(key="b", statement="t", citations=["IT2025:s1"], flag_value=False)])
    d.update(over)
    return d


def test_model_accepts_a_good_assumption():
    Assumption(**_base())


def test_model_rejects_a_default_that_is_not_a_reading():
    with pytest.raises(ValidationError):
        Assumption(**_base(default="z"))


def test_model_rejects_a_default_that_disagrees_with_the_flag():
    with pytest.raises(ValidationError):
        Assumption(**_base(config_default=False))


def test_model_rejects_a_contested_assumption_with_one_reading():
    with pytest.raises(ValidationError):
        Assumption(**_base(readings=[dict(key="a", statement="s", citations=["IT2025:s1"], flag_value=True)]))


def test_model_rejects_a_bad_id():
    with pytest.raises(ValidationError):
        Assumption(**_base(id="X5"))
