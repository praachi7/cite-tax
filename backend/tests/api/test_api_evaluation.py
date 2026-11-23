"""GET /evaluation serves the stored Phase H summary and says so when there is none."""
import json

from fastapi.testclient import TestClient

from api.app import DISCLAIMER, create_app


def _fake_answerer(question, tax_year):  # /ask is not exercised here
    raise AssertionError("not called")


def test_evaluation_returns_the_stored_summary_with_the_disclaimer(tmp_path):
    path = tmp_path / "phase_h_summary.json"
    path.write_text(json.dumps({"date": "2026-11-23", "model": "m", "slices": {"arithmetic": {"matched": 1}}}), encoding="utf8")
    client = TestClient(create_app(_fake_answerer, evaluation_summary=path))
    body = client.get("/evaluation").json()
    assert body["date"] == "2026-11-23" and body["slices"]["arithmetic"]["matched"] == 1
    assert body["disclaimer"] == DISCLAIMER


def test_evaluation_is_404_until_the_evaluation_has_run(tmp_path):
    client = TestClient(create_app(_fake_answerer, evaluation_summary=tmp_path / "missing.json"))
    resp = client.get("/evaluation")
    assert resp.status_code == 404 and "run_evaluation" in resp.json()["detail"]
