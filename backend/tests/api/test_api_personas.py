"""Each persona's API result matches its hand-computed fixture.

The fixture input goes in as JSON and the expected values are checked against the JSON that comes
back, so this also proves that serialisation keeps every figure exact (Decimal money travels as a string).
"""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import app

PERSONA_DIR = Path(__file__).resolve().parents[1] / "engine" / "personas"
FILES = sorted(PERSONA_DIR.glob("p*.yaml"), key=lambda p: int(p.stem[1:]))

client = TestClient(app)


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


def test_there_are_ten_persona_fixtures():
    assert [p.stem for p in FILES] == [f"p{i}" for i in range(1, 11)]


@pytest.mark.parametrize("path", FILES, ids=[p.stem.upper() for p in FILES])
def test_api_result_matches_hand_computed_fixture(path):
    fx = yaml.safe_load(path.read_text(encoding="utf8"))
    resp = client.post("/tax/estimate", json={"input": fx["input"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body["flag_codes"] = [f["code"] for f in body["flags"]]
    assert body["persona_id"] == fx["id"]
    for field, exp in fx["expected"].items():
        got = _dig(body, field)
        assert _equal(got, exp["value"]), f"{fx['id']} {field}: got {got!r}, want {exp['value']!r}"


@pytest.mark.parametrize("path", FILES, ids=[p.stem.upper() for p in FILES])
def test_persona_from_get_personas_gives_the_same_result_as_the_fixture(path):
    fx = yaml.safe_load(path.read_text(encoding="utf8"))
    listed = next(p for p in client.get("/personas").json() if p["id"] == fx["id"])
    a = client.post("/tax/estimate", json={"input": listed["input"]}).json()
    b = client.post("/tax/estimate", json={"input": fx["input"]}).json()
    assert a == b
