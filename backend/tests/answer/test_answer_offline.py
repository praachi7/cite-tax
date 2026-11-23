"""Phase D logic with a fake language model and a fake retriever (no network, no database)."""
from lawdata.chunks import Resolver, load_all_chunks
from lawdata.loader import load_assumptions
from answer.llm import parse_json
from answer.notices import notices_by_id, notices_for
from answer.pipeline import MIN_SIMILARITY, answer
from answer.verify import judge, stage1
from retrieval.refs import QueryRefs
from retrieval.search import Hit, RetrievalResult

CHUNKS = {c.id: c for c in load_all_chunks()}
RESOLVER = Resolver(list(CHUNKS.values()))


class FakeLLM:
    """Returns a scripted draft for the drafting prompt and a scripted verdict per sentence for the judge."""

    model = "fake"

    def __init__(self, draft: dict, verdicts: dict[str, str] | None = None):
        self.draft, self.verdicts, self.calls = draft, verdicts or {}, []

    def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict:
        self.calls.append(system[:20])
        if "check whether passages" in system:
            sentence = user.split("Sentence to check:\n", 1)[1].split("\n", 1)[0]
            return {"verdict": self.verdicts.get(sentence, "supported"), "reason": "scripted"}
        return self.draft


def fake_retriever(ids: list[str], similarity: float = 0.7, exact: bool = False):
    def retrieve(question, tax_year, k=5):
        hits = [Hit(cid, CHUNKS[cid].breadcrumb, CHUNKS[cid].heading, CHUNKS[cid].text, CHUNKS[cid].authority_rank,
                    0.03, {"dense": i + 1, **({"exact": 1} if exact and i == 0 else {})}, similarity)
                for i, cid in enumerate(ids)]
        return RetrievalResult(question, tax_year, "IT2025", QueryRefs(tax_year, "IT2025", "RULES2026"), hits, [])
    return retrieve


# ---- stage 1

def test_stage1_accepts_a_retrieved_passage_valid_for_the_year():
    r = stage1(["P1"], {"P1": "IT2025:s58(2)/T3"}, RESOLVER, 2026)
    assert r.ok and r.chunk_ids == ["IT2025:s58(2)/T3"]


def test_stage1_rejects_an_invented_placeholder():
    r = stage1(["P9"], {"P1": "IT2025:s58(2)/T3"}, RESOLVER, 2026)
    assert not r.ok and "not one of the retrieved passages" in r.problems[0]


def test_stage1_rejects_the_other_acts_passage():
    r = stage1(["P1"], {"P1": "IT1961:s44ADA(1)"}, RESOLVER, 2026)
    assert not r.ok and "not valid for tax year 2026" in r.problems[0]


def test_stage1_rejects_a_sentence_with_no_citation():
    assert not stage1([], {"P1": "IT2025:s516"}, RESOLVER, 2026).ok


def test_unreadable_verdict_never_counts_as_support():
    class Garbled(FakeLLM):
        def complete_json(self, system, user, max_tokens=1500):
            return {"verdict": "probably yes"}
    assert judge(Garbled({}), "x", [CHUNKS["IT2025:s516"]]).verdict == "not_supported"


def test_parse_json_tolerates_fences_and_text():
    assert parse_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}


# ---- notices

def test_contested_assumptions_have_topics():
    for a in load_assumptions():
        if a.status.value == "contested":
            assert a.topics, a.id


def test_itr4_question_shows_the_a16_notice_with_both_readings():
    ns = notices_for("Can I file ITR-4 if my clients are in the US?", [], RESOLVER)
    a16 = next(n for n in ns if n.assumption_id == "A-16")
    assert len(a16.readings) == 2 and a16.default.key == "b"
    assert all(r.citations for r in a16.readings)
    assert "Not professionally reviewed" in a16.disclaimer


def test_payoneer_question_shows_a12_and_ftc_question_shows_a5():
    assert "A-12" in {n.assumption_id for n in notices_for("Is my Payoneer balance a foreign asset?", [], RESOLVER)}
    assert "A-5" in {n.assumption_id for n in notices_for("How is the foreign tax credit capped?", [], RESOLVER)}


def test_retrieved_passage_cited_by_a_reading_triggers_the_notice():
    ns = notices_for("What does the rule say?", ["RULES2026:r164(6)"], RESOLVER)
    assert {"A-12", "A-16"} <= {n.assumption_id for n in ns}


def test_unrelated_question_shows_no_notice_and_resolved_points_never_do():
    assert notices_for("How is total income rounded off?", ["IT2025:s516"], RESOLVER) == []
    assert "A-3" not in {n.assumption_id for n in notices_for("information technology profession", [], RESOLVER)}


def test_notices_by_engine_ids():
    assert [n.assumption_id for n in notices_by_id(["A-16", "A-3"])] == ["A-16"]


# ---- pipeline

def test_low_similarity_declines_without_calling_the_model():
    llm = FakeLLM({})
    out = answer("best laptop?", 2026, llm, retriever=fake_retriever(["IT2025:s516"], MIN_SIMILARITY - 0.1),
                 resolver=RESOLVER)
    assert out.status == "declined" and llm.calls == []


def test_a_named_section_is_answered_even_at_low_similarity():
    llm = FakeLLM({"answerable": True, "sentences": [{"text": "Rounded to ten rupees.", "cites": ["P1"]}]})
    out = answer("s.516?", 2026, llm, retriever=fake_retriever(["IT2025:s516"], 0.2, exact=True), resolver=RESOLVER)
    assert out.status == "answered"


def test_model_says_unanswerable_so_the_answer_is_declined():
    llm = FakeLLM({"answerable": False, "reason": "The passages are about income tax, not GST rates.", "sentences": []})
    out = answer("GST rate on food?", 2026, llm, retriever=fake_retriever(["CGST:s22(1)"]), resolver=RESOLVER)
    assert out.status == "declined" and "GST rates" in out.decline_reason


def test_verified_answer_maps_placeholders_to_chunk_ids():
    llm = FakeLLM({"answerable": True, "sentences": [
        {"text": "Presumptive income is 50% of gross receipts.", "cites": ["P1"]}]})
    out = answer("44ADA rate?", 2026, llm, retriever=fake_retriever(["IT2025:s58(2)/T3", "IT2025:s58(3)"]),
                 resolver=RESOLVER)
    assert out.status == "answered"
    s = out.sentences[0]
    assert s.stage1_ok and s.chunk_ids == ["IT2025:s58(2)/T3"] and s.verdict == "supported"


def test_failed_checks_are_labelled_not_hidden():
    llm = FakeLLM({"answerable": True, "sentences": [
        {"text": "Supported sentence.", "cites": ["P1"]},
        {"text": "Invented citation.", "cites": ["P7"]},
        {"text": "Wrong number.", "cites": ["P1"]}]},
        verdicts={"Wrong number.": "not_supported"})
    out = answer("q", 2026, llm, retriever=fake_retriever(["IT2025:s58(2)/T3"]), resolver=RESOLVER)
    assert out.status == "partially_verified"
    assert [s.verdict for s in out.sentences] == ["supported", "unsupported_citation", "not_supported"]
    assert out.sentences[1].chunk_ids == []   # a failed citation is never shown as a source


def test_numbering_notes_tell_the_model_what_replaced_an_old_number():
    from answer.pipeline import numbering_notes
    from retrieval.refs import detect
    assert numbering_notes(detect("What is the 44ADA limit?", 2026), 2026) == [
        "For Tax Year 2026-27, the question's section 44ADA of the Income-tax Act, 1961 corresponds to "
        "section 58(2) Table Sl. 3 of the Income-tax Act, 2025."]
    assert numbering_notes(detect("Do I need Form 67?", 2026), 2026) == [
        "For Tax Year 2026-27, the question's Form 67 corresponds to Form 44."]
    assert numbering_notes(detect("How is income rounded off?", 2026), 2026) == []


def test_false_premise_is_reported():
    llm = FakeLLM({"answerable": True, "premise_issue": "The limit is fifty lakh rupees, not one crore.",
                   "sentences": [{"text": "The limit is fifty lakh rupees.", "cites": ["P1"]}]})
    out = answer("Since the 44ADA limit is 1 crore...", 2026, llm,
                 retriever=fake_retriever(["IT2025:s58(2)/T3"]), resolver=RESOLVER)
    assert "fifty lakh" in out.premise_issue
