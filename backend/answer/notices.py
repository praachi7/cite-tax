"""'Interpretation uncertain' notices for contested assumptions (A-5, A-12, A-16).

Deterministic: built from corpus/assumptions.yaml, never written by the language model. A notice is
shown when the question mentions one of the assumption's topics, or when the retrieved passages
include a provision that one of its readings cites. Each notice carries both readings with their
citations, the default the engine applies and why, and the flag that switches it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lawdata.chunks import Resolver
from lawdata.loader import load_assumptions
from lawdata.models import Assumption, AssumptionStatus

NOT_REVIEWED = "Not professionally reviewed: CiteTax has no chartered accountant; this is a documented assumption."


@dataclass
class NoticeReading:
    key: str
    statement: str
    citations: list[str]
    is_default: bool


@dataclass
class Notice:
    assumption_id: str
    question: str
    readings: list[NoticeReading]
    default_reason: str
    config_flag: str
    triggered_by: list[str] = field(default_factory=list)   # "topic: ..." or "passage: ..."
    disclaimer: str = NOT_REVIEWED

    @property
    def default(self) -> NoticeReading:
        return next(r for r in self.readings if r.is_default)


def _mentions(text: str, topic: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(topic.lower()) + r"(?![a-z0-9])", text.lower()) is not None


def _to_notice(a: Assumption, why: list[str]) -> Notice:
    return Notice(assumption_id=a.id, question=a.question, default_reason=a.default_reason,
                  config_flag=a.config_flag, triggered_by=why,
                  readings=[NoticeReading(r.key, r.statement, list(r.citations), r.key == a.default)
                            for r in a.readings])


def notices_for(question: str, passage_ids: list[str], resolver: Resolver | None = None,
                assumptions: list[Assumption] | None = None) -> list[Notice]:
    """Notices for every contested assumption the question or the retrieved passages touch."""
    out = []
    for a in assumptions if assumptions is not None else load_assumptions():
        if a.status is not AssumptionStatus.contested:
            continue
        why = [f"topic: {t}" for t in a.topics if _mentions(question, t)]
        if resolver is not None:
            cited = {c.id for r in a.readings for cid in r.citations if (c := resolver.resolve(cid)) is not None}
            why += [f"passage: {pid}" for pid in passage_ids if pid in cited]
        if why:
            out.append(_to_notice(a, why))
    return out


def notices_by_id(ids: list[str]) -> list[Notice]:
    """Notices for assumptions named by the engine (EngineResult compliance.depends_on_contested)."""
    wanted = set(ids)
    return [_to_notice(a, ["engine result depends on it"]) for a in load_assumptions()
            if a.id in wanted and a.status is AssumptionStatus.contested]
