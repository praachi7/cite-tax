"""POST /ask with a fake answerer (no network, no database)."""
from fastapi.testclient import TestClient

from answer.llm import LLMError
from answer.notices import notices_by_id
from answer.pipeline import Answer, Sentence
from api.app import DISCLAIMER, create_app


def fake_answerer(question, tax_year):
    if question.startswith("boom"):
        raise LLMError("rate limited")
    return Answer(question=question, tax_year=tax_year, act_id="IT2025", status="answered",
                  sentences=[Sentence("Presumptive income is 50% of gross receipts.", ["P1"], ["IT2025:s58(2)/T3"],
                                      True, [], "supported", "stated in column E")],
                  notices=notices_by_id(["A-16"]), passages=["IT2025:s58(2)/T3"], retrieval_similarity=0.66,
                  model="fake")


client = TestClient(create_app(answerer=fake_answerer))


def test_ask_returns_sentences_citations_notices_and_disclaimer():
    r = client.post("/ask", json={"question": "What is the 44ADA rate?", "tax_year": 2026})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sentences"][0]["chunk_ids"] == ["IT2025:s58(2)/T3"]
    assert body["sentences"][0]["verdict"] == "supported"
    assert body["notices"][0]["assumption_id"] == "A-16"
    assert body["disclaimer"] == DISCLAIMER


def test_model_outage_is_a_503_not_a_crash():
    r = client.post("/ask", json={"question": "boom question", "tax_year": 2026})
    assert r.status_code == 503 and "language model unavailable" in r.json()["detail"]


def test_bad_request_is_rejected():
    assert client.post("/ask", json={"question": "", "tax_year": 2026}).status_code == 422
    assert client.post("/ask", json={"question": "fine question", "tax_year": 2026, "extra": 1}).status_code == 422
