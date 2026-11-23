"""POST /tax/estimate/upload: each persona from CSV to dashboard data; relabels never move presumptive income."""
import random

import pytest
from fastapi.testclient import TestClient

from api.app import DISCLAIMER, app
from api.upload import CSV_FIELDS, strip_csv_fields
from ingest.models import ExpenseCategory

client = TestClient(app)
PIDS = [f"P{i}" for i in range(1, 11)]
CSV_DEPENDENT_FLAGS = {"FIRA_MISSING", "LOW_CLASSIFICATION_CONFIDENCE"}   # read remittances / classifications


def _persona_input(pid):
    return next(p for p in client.get("/personas").json() if p["id"] == pid)["input"]


def _csv(pid):
    resp = client.get(f"/personas/{pid}/transactions.csv")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    return resp.text


def _upload(pid, relabels=None, **extra):
    body = {"profile": strip_csv_fields(_persona_input(pid)), "csv_text": _csv(pid), "relabels": relabels or {}, **extra}
    resp = client.post("/tax/estimate/upload", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("pid", PIDS)
def test_each_persona_runs_from_upload_to_dashboard_data_and_matches_the_figures_route(pid):
    up = _upload(pid)
    typed = client.post("/tax/estimate", json={"input": _persona_input(pid)}).json()
    est = up["estimate"]
    assert est["receipts_test"]["total"] == typed["receipts_test"]["total"]
    for key in ("act", "income", "india_tax", "treaty", "relief"):
        assert est[key] == typed[key], key
    assert est["compliance"]["itr_form"] == typed["compliance"]["itr_form"]
    assert ({f["code"] for f in est["flags"]} - CSV_DEPENDENT_FLAGS) == \
           ({f["code"] for f in typed["flags"]} - CSV_DEPENDENT_FLAGS)
    assert est["figures"] and all(f["citations"] for f in est["figures"] if f["rule_id"] != "ENG.01.act_selection")
    assert up["disclaimer"] == DISCLAIMER
    expenses = [t for t in up["transactions"] if t["direction"] == "expense"]
    assert len(up["classifications"]) == len(expenses)
    for n in up["notices"]:
        assert len(n["readings"]) >= 2 and n["disclaimer"].startswith("Not professionally reviewed")


@pytest.mark.parametrize("pid", PIDS)
def test_relabelling_every_expense_never_changes_presumptive_income_or_tax(pid):
    base = _upload(pid)
    rng = random.Random(pid)
    labels = [c.value for c in ExpenseCategory]
    relabels = {c["transaction_id"]: rng.choice(labels) for c in base["classifications"]}
    after = _upload(pid, relabels=relabels)
    for key in ("receipts_test", "income", "india_tax", "relief", "treaty"):
        assert after["estimate"][key] == base["estimate"][key], key
    assert after["profit_comparison"]["presumptive_income"] == base["profit_comparison"]["presumptive_income"]
    changed = [c for c in base["classifications"] if relabels[c["transaction_id"]] != c["category"]]
    assert len([c for c in after["corrections"] if c["kind"] == "corrected"]) == len(changed)
    assert len(after["corrections"]) == len(relabels)
    for c in after["classifications"]:
        assert c["method"] == "user" and c["category"] == relabels[c["transaction_id"]]


def test_relabelling_uncertain_expenses_clears_the_low_confidence_flag():
    base = _upload("P1")
    weak = {c["transaction_id"]: "personal" for c in base["classifications"]
            if c["category"] == "uncertain" or float(c["confidence"]) < 0.8}
    assert weak, "P1's synthetic set should contain an uncertain expense"
    assert "LOW_CLASSIFICATION_CONFIDENCE" in {f["code"] for f in base["estimate"]["flags"]}
    after = _upload("P1", relabels=weak)
    assert "LOW_CLASSIFICATION_CONFIDENCE" not in {f["code"] for f in after["estimate"]["flags"]}


@pytest.mark.parametrize("field", CSV_FIELDS)
def test_profile_may_not_carry_what_the_csv_supplies(field):
    profile = {**strip_csv_fields(_persona_input("P1")), field: {"electronic": 1} if field == "receipts" else []}
    resp = client.post("/tax/estimate/upload", json={"profile": profile, "csv_text": _csv("P1")})
    assert resp.status_code == 422 and field in resp.text


def test_relabelling_a_receipt_or_an_unknown_row_is_rejected():
    receipt = next(t["id"] for t in _upload("P1")["transactions"] if t["direction"] == "receipt")
    for tid in (receipt, "NOPE-1"):
        resp = client.post("/tax/estimate/upload", json={"profile": strip_csv_fields(_persona_input("P1")),
                                                         "csv_text": _csv("P1"), "relabels": {tid: "personal"}})
        assert resp.status_code == 422


def test_bad_rows_are_reported_and_an_empty_csv_is_rejected():
    csv = _csv("P1") + "X-1,not-a-date,receipt,100,INR,100,,,,,,,\n"
    resp = client.post("/tax/estimate/upload", json={"profile": {"tax_year": 2026}, "csv_text": csv})
    assert resp.status_code == 200
    assert any(e["field"] == "date" for e in resp.json()["parse_errors"])
    resp = client.post("/tax/estimate/upload", json={"profile": {"tax_year": 2026}, "csv_text": "date,amount,direction\n"})
    assert resp.status_code == 422


def test_unknown_persona_csv_is_404_and_bad_profile_is_422():
    assert client.get("/personas/P99/transactions.csv").status_code == 404
    resp = client.post("/tax/estimate/upload", json={"profile": {"tax_year": 2026, "nonsense": 1}, "csv_text": _csv("P1")})
    assert resp.status_code == 422


def test_sources_resolves_citations_to_corpus_passages():
    resp = client.get("/sources", params=[("ids", "IT2025:s58(2)/T3"), ("ids", "IT2025:s99999")])
    rows = {r["id"]: r for r in resp.json()["sources"]}
    assert rows["IT2025:s58(2)/T3"]["resolved"] and rows["IT2025:s58(2)/T3"]["text"]
    assert rows["IT2025:s99999"]["resolved"] is False
    assert client.get("/sources", params=[("ids", f"X:{i}") for i in range(61)]).status_code == 422
