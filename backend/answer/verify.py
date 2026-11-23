"""Two-stage citation verification.

Stage 1 (exact, no language model): the cited placeholder must name a passage that was retrieved,
the passage must exist in the corpus, and it must be valid for the tax year asked about.
A sentence whose citation fails stage 1 is shown as unsupported, never with the citation.

Stage 2 (language model as judge): do the cited passages support the sentence?
supported / partially_supported / not_supported. Measured against a hand-labelled set
(backend/tests/answer/claim_pairs.yaml, scripts/calibrate_judge.py), because it is imperfect.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lawdata.chunks import Chunk, Resolver

from .llm import LLM
from .prompts import JUDGE_SYSTEM, judge_user

MAX_JUDGE_CHARS = 2500  # per passage; keeps a judge call well inside the free tier's tokens per minute
VERDICTS = ("supported", "partially_supported", "not_supported")


@dataclass
class Stage1:
    ok: bool
    chunk_ids: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def valid_for_year(chunk: Chunk, year: int) -> bool:
    return ((chunk.tax_year_first is None or chunk.tax_year_first <= year)
            and (chunk.tax_year_last is None or chunk.tax_year_last >= year))


def stage1(cites: list[str], label_to_id: dict[str, str], resolver: Resolver, year: int) -> Stage1:
    """cites are placeholders such as "P2"; label_to_id maps them to the retrieved chunk IDs."""
    if not cites:
        return Stage1(False, problems=["no citation"])
    ids, problems = [], []
    for label in cites:
        cid = label_to_id.get(str(label).strip().upper())
        if cid is None:
            problems.append(f"{label}: not one of the retrieved passages")
            continue
        chunk = resolver.resolve(cid)
        if chunk is None:
            problems.append(f"{cid}: not in the corpus")
        elif not valid_for_year(chunk, year):
            problems.append(f"{cid}: not valid for tax year {year}")
        else:
            ids.append(chunk.id)
    return Stage1(ok=not problems and bool(ids), chunk_ids=ids, problems=problems)


@dataclass
class Judgement:
    verdict: str
    reason: str


def judge(llm: LLM, sentence: str, chunks: list[Chunk]) -> Judgement:
    passages = [(c.breadcrumb, c.text[:MAX_JUDGE_CHARS]) for c in chunks]
    out = llm.complete_json(JUDGE_SYSTEM, judge_user(sentence, passages), max_tokens=800)
    verdict = str(out.get("verdict", "")).strip().lower().replace(" ", "_")
    if verdict not in VERDICTS:
        verdict = "not_supported"  # an unreadable verdict never counts as support
    return Judgement(verdict, str(out.get("reason", "")).strip())
