"""Phase H evaluation helpers (offline): held-out integrity, the wrong-jurisdiction check, relevance measures."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from answer.pipeline import Answer, Sentence

ROOT = Path(__file__).resolve().parents[2]


def _script(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def run_eval():
    return _script("run_evaluation")


@pytest.fixture(scope="module")
def eval_answers():
    return _script("eval_answers")


def test_heldout_files_still_match_the_hashes_recorded_before_any_run(run_eval):
    recorded = run_eval.check_heldout_hashes()
    assert set(recorded) == {str(p.relative_to(ROOT)).replace("\\", "/") for p in run_eval.HELDOUT.values()}


def test_a_changed_heldout_file_stops_the_run(run_eval, tmp_path):
    fake = tmp_path / "hashes.json"
    rel = "backend/tests/retrieval/queries_heldout.yaml"
    fake.write_text(json.dumps({"frozen_at": "x", "sha256": {rel: "0" * 64}}), encoding="utf8")
    with pytest.raises(SystemExit, match="changed after they were frozen"):
        run_eval.check_heldout_hashes(fake)


def test_hash_ignores_line_endings(run_eval, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"x: 1\ny: 2\n")
    b.write_bytes(b"x: 1\r\ny: 2\r\n")
    assert run_eval.file_hash(a) == run_eval.file_hash(b)


def test_heldout_sets_share_no_question_with_the_original_sets():
    def qs(path, key):
        return {item["q"].strip().lower() for item in yaml.safe_load(path.read_text(encoding="utf8"))[key]}
    tests = ROOT / "backend" / "tests"
    assert not qs(tests / "retrieval" / "queries.yaml", "queries") & qs(tests / "retrieval" / "queries_heldout.yaml", "queries")
    assert not qs(tests / "answer" / "answer_cases.yaml", "cases") & qs(tests / "answer" / "answer_cases_heldout.yaml", "cases")
    claims = lambda p: {x["claim"] for x in yaml.safe_load(p.read_text(encoding="utf8"))["pairs"]}  # noqa: E731
    assert not claims(tests / "answer" / "claim_pairs.yaml") & claims(tests / "answer" / "claim_pairs_heldout.yaml")


def _answer(status="answered", premise="", sentences=(), passages=()):
    return Answer(question="q", tax_year=2026, act_id="IT2025", status=status, premise_issue=premise,
                  sentences=[Sentence(t, [], [], True, [], "supported") for t in sentences], passages=list(passages))


def test_wrong_jurisdiction_passes_when_declined_or_flagged_and_fails_when_answered(eval_answers):
    case = {"year": 2026, "expect": {"jurisdiction": True}}
    assert eval_answers.check(case, _answer(status="declined")) == []
    assert eval_answers.check(case, _answer(premise="This is UK law, which CiteTax does not cover.", sentences=["x"])) == []
    assert eval_answers.check(case, _answer(sentences=["The UK basic rate is 20%."]))


def test_key_fact_relevance_and_context_recall(eval_answers):
    case = {"expect": {"key_facts": [["75 lakh", "7500000"], ["31 August"]], "passages": ["IT2025:s58(2)/T3"]}}
    r = eval_answers.relevance(case, _answer(sentences=["The limit is 75 Lakh."], passages=["IT2025:s58(2)/T3"]))
    assert r == {"key_facts": 0.5, "key_facts_missing": ["31 August"], "context_recall": True}
    # the model writes narrow no-break spaces and non-breaking hyphens; they must still match
    case = {"expect": {"key_facts": [["15 March"], ["one hundred and eighty-two"]]}}
    r = eval_answers.relevance(case, _answer(sentences=["Pay by 15 March; one hundred and eighty‑two days."]))
    assert r["key_facts"] == 1.0
    r = eval_answers.relevance({"expect": {}}, _answer())
    assert r["key_facts"] is None and r["context_recall"] is None
