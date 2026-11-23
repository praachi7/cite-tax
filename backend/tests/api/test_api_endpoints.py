"""Endpoint behaviour: persona listing, citations on every output, config overrides and errors."""
from fastapi.testclient import TestClient

from api.app import DISCLAIMER, app
from api.figures import FIGURES

client = TestClient(app)


def _persona(pid):
    return next(p for p in client.get("/personas").json() if p["id"] == pid)["input"]


def _estimate(pid, **config):
    resp = client.post("/tax/estimate", json={"input": _persona(pid), "config": config})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_personas_lists_p1_to_p10_in_order_without_expected_values():
    body = client.get("/personas").json()
    assert [p["id"] for p in body] == [f"P{i}" for i in range(1, 11)]
    for p in body:
        assert set(p) == {"id", "title", "input"}
        assert p["title"] and p["input"]["persona_id"] == p["id"]


def test_result_carries_trace_flags_assumptions_and_disclaimer():
    body = _estimate("P5")
    for key in ("act", "india_tax", "relief", "compliance", "trace", "flags", "config", "assumptions_applied", "figures"):
        assert key in body
    assert body["disclaimer"] == DISCLAIMER


def test_every_trace_step_figure_and_flag_carries_a_rule_id_and_citations():
    for pid in [f"P{i}" for i in range(1, 11)]:
        body = _estimate(pid)
        for t in body["trace"]:
            assert t["rule_id"].startswith("ENG.")
            assert t["param_version"].endswith(".yaml")
            if t["rule_id"] != "ENG.01.act_selection":
                assert t["citations"], f"{pid} {t['rule_id']}"
        trace_ids = {t["rule_id"] for t in body["trace"]}
        for f in body["figures"]:
            assert f["rule_id"] in trace_ids
            assert f["param_version"].endswith(".yaml")
            if f["rule_id"] != "ENG.01.act_selection":
                assert f["citations"], f"{pid} {f['path']}"
        for fl in body["flags"]:
            assert fl["rule_id"].startswith("ENG.")


def test_figure_values_are_the_result_values():
    body = _estimate("P5")
    by_path = {f["path"]: f for f in body["figures"]}
    assert by_path["india_tax.in_force.payable"]["value"] == body["india_tax"]["in_force"]["payable"]
    assert by_path["relief.ftc.credit_inr"]["value"] == body["relief"]["ftc"]["credit_inr"]
    assert by_path["compliance.itr_form"]["rule_id"] == "ENG.10.itr_form"
    assert by_path["india_tax.in_force.payable"]["unit"] == "inr"
    assert by_path["compliance.itr_form"]["unit"] is None


def test_every_inr_path_is_a_listed_figure():
    from api.figures import INR_PATHS, UNITS
    listed = {p for _, p, _, _ in FIGURES}
    assert INR_PATHS <= listed and set(UNITS) <= listed


def test_figures_whose_step_did_not_produce_a_value_are_left_out():
    body = _estimate("P4")   # presumptive scheme unavailable; no relief claim
    paths = {f["path"] for f in body["figures"]}
    assert "relief.ftc.credit_inr" not in paths
    assert paths <= {p for _, p, _, _ in FIGURES}


def test_money_travels_as_exact_strings():
    body = _estimate("P1")
    assert isinstance(body["income"]["income"], str)


def test_config_override_switches_the_reading():
    default = _estimate("P1")
    other = _estimate("P1", itr4_foreign_client_income_is_indian_source=True)
    assert default["compliance"]["itr_form"] == "ITR-3"
    assert other["compliance"]["itr_form"] == "ITR-4"
    a16 = next(a for a in other["assumptions_applied"] if a["id"] == "A-16")
    assert a16["reading"] == "a" and a16["is_default"] is False


def test_undocumented_assumption_value_is_rejected():
    resp = client.post("/tax/estimate", json={"input": _persona("P5"), "config": {"ftc_cap_basis": "whatever"}})
    assert resp.status_code == 422


def test_unknown_config_key_is_rejected():
    resp = client.post("/tax/estimate", json={"input": _persona("P1"), "config": {"made_up": True}})
    assert resp.status_code == 422


def test_invalid_input_is_rejected():
    bad = {"tax_year": 2026, "receipts": {"electronic": -5}}
    assert client.post("/tax/estimate", json={"input": bad}).status_code == 422
    assert client.post("/tax/estimate", json={"input": {"receipts": {}}}).status_code == 422


def test_unsupported_tax_year_is_a_400():
    resp = client.post("/tax/estimate", json={"input": {"tax_year": 2019, "receipts": {"electronic": 100000}}})
    assert resp.status_code == 400
    assert "2019" in resp.json()["detail"]
