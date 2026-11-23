"""answer(question, tax_year): retrieve -> decide whether to answer -> draft with citations -> verify.

Nothing is shown without a checked source:
* the Act comes from the tax year (engine ParamSet), never from the model;
* the model cites placeholders (P1..Pn), which are resolved to chunk IDs, so it cannot invent a citation;
* stage 1 (exact) and stage 2 (judge) run on every sentence; a sentence that fails is labelled, not hidden;
* low retrieval confidence, an unanswerable question or a false premise is said openly;
* contested points get an "Interpretation uncertain" notice built from corpus/assumptions.yaml.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from engine.params import ParamSet
from lawdata.chunks import Resolver, load_all_chunks

from .llm import LLM
from .notices import Notice, notices_for
from .prompts import DRAFT_SYSTEM, draft_user
from .verify import judge, stage1

# Below this cosine similarity, with no section named in the question, the corpus has nothing close
# enough: decline before calling the model. Measured 23 Nov 2026: in-scope questions scored 0.46-0.77
# (lowest: "substantial presence test 183 days"); a non-tax question scored 0.34; off-topic TAX questions
# (GST rates, HRA, capital gains, UK bands) scored 0.48-0.56 and overlap in-scope ones. So this gate only
# stops clearly unrelated questions; off-topic tax questions are caught by the model's "answerable": false.
MIN_SIMILARITY = 0.45
DRAFT_PASSAGES = 5
MAX_DRAFT_CHARS = 2000
ACT_LABEL = {"IT1961": "the Income-tax Act, 1961", "IT2025": "the Income-tax Act, 2025"}


@dataclass
class Sentence:
    text: str
    cites: list[str]                  # placeholders as the model wrote them
    chunk_ids: list[str]              # resolved citations that passed stage 1
    stage1_ok: bool
    stage1_problems: list[str]
    verdict: str                      # supported | partially_supported | not_supported | unsupported_citation
    reason: str = ""


@dataclass
class Answer:
    question: str
    tax_year: int
    act_id: str
    status: str            # answered | partially_verified | declined
    sentences: list[Sentence] = field(default_factory=list)
    premise_issue: str = ""
    decline_reason: str = ""
    notices: list[Notice] = field(default_factory=list)
    passages: list[str] = field(default_factory=list)   # chunk IDs shown to the model
    retrieval_similarity: float = 0.0
    model: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_SOURCE_NAME = {"IT1961": "the Income-tax Act, 1961", "IT2025": "the Income-tax Act, 2025",
                "RULES1962": "the Income-tax Rules, 1962", "RULES2026": "the Income-tax Rules, 2026"}


def pretty_ref(cid: str) -> str:
    """IT1961:s44ADA -> 'section 44ADA of the Income-tax Act, 1961'; FORM44:all -> 'Form 44'."""
    prefix, _, rest = cid.partition(":")
    if prefix.startswith("FORM"):
        return f"Form {prefix[4:]}"
    if prefix in _SOURCE_NAME:
        kind = "rule" if prefix.startswith("RULES") else "section"
        num = (rest[1:] if rest[:1] in "sr" else rest).replace("/T", " Table Sl. ")
        return f"{kind} {num} of {_SOURCE_NAME[prefix]}"
    return cid


def numbering_notes(refs, tax_year: int) -> list[str]:
    """One note per concordance mapping that retrieval applied to the question."""
    targets: dict[str, list[str]] = {}
    for m in getattr(refs, "mappings", []):
        if m.via == "concordance":
            t = targets.setdefault(m.asked, [])
            if pretty_ref(m.target) not in t:
                t.append(pretty_ref(m.target))
    return [f"For {year_label(tax_year)}, the question's {pretty_ref(asked)} corresponds to {' / '.join(ts)}."
            for asked, ts in targets.items()]


def year_label(tax_year: int) -> str:
    span = f"{tax_year}-{(tax_year + 1) % 100:02d}"
    return f"FY {span}" if tax_year <= 2025 else f"Tax Year {span}"


_RESOLVER: Resolver | None = None


def corpus_resolver() -> Resolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = Resolver(load_all_chunks())
    return _RESOLVER


def answer(question: str, tax_year: int, llm: LLM, retriever: Callable | None = None,
           resolver: Resolver | None = None, engine_facts: list[str] | None = None) -> Answer:
    if retriever is None:
        from retrieval.search import retrieve as retriever  # needs the database; tests pass their own
    resolver = resolver or corpus_resolver()
    act_id = ParamSet.for_tax_year(tax_year).act_id
    res = retriever(question, tax_year, k=DRAFT_PASSAGES)
    hits = res.hits[:DRAFT_PASSAGES]
    out = Answer(question=question, tax_year=tax_year, act_id=act_id, status="answered", model=llm.model,
                 passages=[h.id for h in hits], retrieval_similarity=round(res.top_similarity, 3))
    out.notices = notices_for(question, out.passages, resolver)

    if not hits or (not res.exact_matched and res.top_similarity < MIN_SIMILARITY):
        out.status = "declined"
        out.decline_reason = ("The corpus has no passage close enough to this question, so CiteTax will not answer it. "
                              "It covers Indian income tax for IT professionals with US clients.")
        return out

    labels = {f"P{i}": h.id for i, h in enumerate(hits, start=1)}
    passages = [(label, h.breadcrumb, h.text[:MAX_DRAFT_CHARS]) for label, h in zip(labels, hits)]
    draft = llm.complete_json(DRAFT_SYSTEM, draft_user(question, year_label(tax_year), ACT_LABEL.get(act_id, act_id),
                                                       passages, engine_facts, numbering_notes(res.refs, tax_year)),
                             max_tokens=1500)
    out.premise_issue = str(draft.get("premise_issue") or "").strip()
    if not draft.get("answerable", True) or not draft.get("sentences"):
        out.status = "declined"
        out.decline_reason = str(draft.get("reason") or "The retrieved passages do not answer this question.").strip()
        return out

    for s in draft.get("sentences", []):
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        cites = [str(c) for c in (s.get("cites") or [])]
        st1 = stage1(cites, labels, resolver, tax_year)
        if not st1.ok:
            out.sentences.append(Sentence(text, cites, [], False, st1.problems, "unsupported_citation"))
            continue
        chunks = [resolver.resolve(cid) for cid in st1.chunk_ids]
        j = judge(llm, text, chunks)
        out.sentences.append(Sentence(text, cites, st1.chunk_ids, True, [], j.verdict, j.reason))

    if not out.sentences:
        out.status = "declined"
        out.decline_reason = "The model returned no usable sentences."
    elif any(s.verdict != "supported" for s in out.sentences):
        out.status = "partially_verified"
    return out
