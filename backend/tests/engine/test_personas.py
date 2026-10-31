"""Golden personas: engine output against hand-computed, statute-cited expected values.

Each fixture in personas/ holds the input and an `expected` map from a dotted result path to
{value, cite, work}. The expected values are written by hand from the statute (the arithmetic is in
each file's header comment) and are never copied from engine output.
"""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.models import TaxpayerInput
from engine.pipeline import run
from lawdata.loader import load_registry
from lawdata.models import CITATION_RE

PERSONA_DIR = Path(__file__).parent / "personas"
FILES = sorted(PERSONA_DIR.glob("p*.yaml"), key=lambda p: int(p.stem[1:]))
PREFIXES = {s.cite_prefix for s in load_registry()}


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf8"))


def _dig(data, dotted):
    for part in dotted.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _equal(actual, expected):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if isinstance(expected, list):
        return sorted(actual) == sorted(expected)
    if isinstance(expected, (int, float, Decimal)) or (isinstance(expected, str) and expected.replace(".", "", 1).isdigit()):
        return Decimal(str(actual)) == Decimal(str(expected))
    return actual == expected


@pytest.fixture(scope="module")
def results():
    out = {}
    for path in FILES:
        fx = _load(path)
        out[fx["id"]] = (fx, run(TaxpayerInput(**fx["input"])))
    return out


def _view(res):
    d = res.model_dump(mode="json")
    d["flag_codes"] = [f["code"] for f in d["flags"]]
    return d


@pytest.mark.parametrize("path", FILES, ids=[p.stem.upper() for p in FILES])
def test_persona_matches_hand_computed_values(path, results):
    fx = _load(path)
    _, res = results[fx["id"]]
    view = _view(res)
    for field, exp in fx["expected"].items():
        assert _equal(_dig(view, field), exp["value"]), f"{fx['id']} {field}: got {_dig(view, field)!r}, want {exp['value']!r}"


@pytest.mark.parametrize("path", FILES, ids=[p.stem.upper() for p in FILES])
def test_every_expected_figure_cites_its_provision_and_shows_its_work(path):
    fx = _load(path)
    assert fx["expected"], "a persona needs expected values"
    for field, exp in fx["expected"].items():
        assert exp["cite"], f"{field}: no citation"
        assert exp["work"].strip(), f"{field}: no working shown"
        for c in exp["cite"]:
            assert CITATION_RE.match(c), f"{field}: bad citation {c!r}"
            assert c.split(":")[0] in PREFIXES, f"{field}: unknown source {c!r}"


@pytest.mark.parametrize("path", FILES, ids=[p.stem.upper() for p in FILES])
def test_every_output_step_carries_a_rule_id_and_parameter_version(path, results):
    fx = _load(path)
    _, res = results[fx["id"]]
    assert res.trace
    for t in res.trace:
        assert t.rule_id.startswith("ENG.") and t.rule_id.split(".")[1] == f"{t.step:02d}", t.rule_id
        assert t.param_version.endswith(".yaml")
        if t.rule_id != "ENG.01.act_selection":
            assert t.citations, f"{t.rule_id} has no citation"
    for f in res.flags:
        assert f.rule_id.startswith("ENG."), f.code


@pytest.mark.parametrize("path", [p for p in FILES if "trace_expect" in _load(p)], ids=lambda p: p.stem.upper())
def test_trace_uses_only_the_selected_acts_citations(path, results):
    fx = _load(path)
    _, res = results[fx["id"]]
    te = fx["trace_expect"]
    cites = {c for t in res.trace for c in t.citations}
    for c in te.get("has_cite", []):
        assert c in cites, c
    for prefix in te.get("lacks_prefix", []):
        assert not any(c.startswith(prefix + ":") for c in cites), prefix
    assert {t.param_version for t in res.trace} == {te["param_version"]}
