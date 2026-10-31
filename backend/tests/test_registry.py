import pytest
from pydantic import ValidationError

from lawdata import validate
from lawdata.loader import SOURCES_DIR, load_manifest, load_registry
from lawdata.models import CITATION_RE, Param, ParamFile


def test_registry_loads_and_is_consistent():
    assert validate.check_registry_and_manifest() == []


def test_registry_covers_every_manifest_row():
    assert {s.id for s in load_registry()} == {m.id for m in load_manifest()}


@pytest.mark.skipif(not SOURCES_DIR.exists(), reason="source PDFs are not in the repository")
def test_source_files_match_manifest_checksums():
    assert validate.check_registry_and_manifest(SOURCES_DIR) == []


@pytest.mark.parametrize("cid", [
    "IT2025:s58(2)/T3", "IT1961:s44ADA(1)", "RULES2026:r76(7)(a)", "RULES2026:r164(6)(c)",
    "DTAA_US:art15(1)(b)", "IRC:s861(a)(3)", "CBDT_FAQ_PRES:Q17", "CBDT_FAQ_TRANS:Q8.17",
])
def test_good_citation_ids(cid):
    assert CITATION_RE.match(cid)


@pytest.mark.parametrize("cid", ["s58(2)", "it2025:s58", "IT2025:", "IT2025 s58", "IT2025:s58//T3"])
def test_bad_citation_ids(cid):
    assert not CITATION_RE.match(cid)


def test_param_needs_a_source():
    with pytest.raises(ValidationError):
        Param(value=1, sources=[], status="verified")


def test_param_rejects_bad_citation():
    with pytest.raises(ValidationError):
        Param(value=1, sources=["section 58"], status="verified")


def test_param_file_rejects_bad_key():
    ok = dict(value=1, sources=["IT2025:s58(2)/T3"], status="verified")
    with pytest.raises(ValidationError):
        ParamFile(act_id="IT2025", rules_id="RULES2026", label="x", tax_year=2026,
                  valid_from="2026-04-01", params={"Bad Key": ok})


def test_param_file_accepts_good_data():
    pf = ParamFile(act_id="IT2025", rules_id="RULES2026", label="Tax Year 2026-27", tax_year=2026,
                   valid_from="2026-04-01",
                   params={"presumptive.limit.default": dict(value=5000000, unit="INR",
                                                           sources=["IT2025:s58(2)/T3"], status="verified")})
    assert pf.params["presumptive.limit.default"].value == 5000000


def test_param_prefix_must_exist_in_registry():
    pf = ParamFile(act_id="IT2025", rules_id="RULES2026", label="x", tax_year=2026, valid_from="2026-04-01",
                   params={"a.b": dict(value=1, sources=["NOPE:s1"], status="verified")})
    problems = validate.check_param_files({"x.yaml": pf})
    assert any("unknown citation prefix" in p for p in problems)


def test_param_files_must_share_keys():
    a = ParamFile(act_id="IT1961", rules_id="RULES1962", label="a", tax_year=2025, valid_from="2025-04-01",
                  params={"k.one": dict(value=1, sources=["IT1961:s1"], status="verified")})
    b = ParamFile(act_id="IT2025", rules_id="RULES2026", label="b", tax_year=2026, valid_from="2026-04-01",
                  params={"k.two": dict(value=1, sources=["IT2025:s1"], status="verified")})
    problems = validate.check_param_files({"a.yaml": a, "b.yaml": b})
    assert len(problems) == 2
