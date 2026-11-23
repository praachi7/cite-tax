"""Find legal references in a question and map them to the Act that applies to the tax year.

Pure functions (no database), so they are unit-tested directly.

"What is the 44ADA limit?" for Tax Year 2026-27 -> 44ADA is a 1961 Act section ->
the concordance maps IT1961:s44ADA to IT2025:s58(2)/T3 -> the exact-match list looks for that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.params import ParamSet
from lawdata.loader import load_concordance

# "section 44ADA", "s. 58(2)", "sec 139(1)", "u/s 44AB"
SECTION_RE = re.compile(r"\b(?:sections?|secs?\.?|s\.|u/s)\s*(\d{1,3}[A-Z]{0,3})((?:\(\w{1,4}\))*)", re.I)
# a bare section-like token with letters, e.g. 44ADA, 115BAC, 87A (numbers alone are too ambiguous)
BARE_RE = re.compile(r"\b(\d{1,3}[A-Z]{1,3})\b", re.I)
NOT_SECTIONS = {"ST", "ND", "RD", "TH", "L", "K", "CR", "AM", "PM", "D", "M", "Y"}  # 1st, 50L, 90d ...
RULE_RE = re.compile(r"\brules?\s*(\d{1,3}[A-Z]{0,2})((?:\(\w{1,4}\))*)", re.I)
ARTICLE_RE = re.compile(r"\b(?:articles?|art\.?)\s*(\d{1,2})((?:\(\w{1,4}\))*)", re.I)
FORM_RE = re.compile(r"\bform\s*(?:no\.?\s*)?(44|67|W-?8\s?BEN|8233|8833|1040-?NR)\b", re.I)

FORM_IDS = {"44": "FORM44:all", "67": "FORM67:all", "W8BEN": "IRS_W8BEN:all",
            "8233": "IRS_F8233:all", "8833": "IRS_F8833:all", "1040NR": "IRS_1040NR:all"}


@dataclass
class Mapping:
    asked: str       # the reference as found, e.g. IT1961:s44ADA
    target: str      # the provision for the tax year, e.g. IT2025:s58(2)/T3
    via: str         # "same Act" | "concordance" | "treaty" | "form"


@dataclass
class QueryRefs:
    tax_year: int
    act_id: str
    rules_id: str
    mappings: list[Mapping] = field(default_factory=list)

    @property
    def targets(self) -> list[str]:
        seen: list[str] = []
        for m in self.mappings:
            if m.target not in seen:
                seen.append(m.target)
        return seen

    @property
    def search_terms(self) -> list[str]:
        """Section numbers of the targets, added to the keyword query (e.g. s58, T3)."""
        terms: list[str] = []
        for t in self.targets:
            _, rest = t.split(":", 1)
            terms += [w for w in re.split(r"[()/]", rest) if w and w != "all"]
        return terms


def base(cid: str) -> str:
    """IT2025:s58(2)/T3 -> IT2025:s58"""
    return re.split(r"[(/]", cid, maxsplit=1)[0]


def _concordance_map(cid: str, target_act: str) -> list[str]:
    """Map a provision of one Act to the other through the concordance (both directions)."""
    out: list[str] = []
    for row in load_concordance():
        for frm, to in ((row.old_ref, row.new_ref), (row.new_ref, row.old_ref)):
            if base(frm) == base(cid) and to.startswith(target_act + ":") and to not in out:
                # a more specific ask keeps its tail when the numbers line up (s44ADA(1) -> s58(2)/T3)
                out.append(to)
    return out


def detect(question: str, tax_year: int) -> QueryRefs:
    ps = ParamSet.for_tax_year(tax_year)
    act, rules = ps.act_id, ps.rules_id
    other_act = "IT1961" if act == "IT2025" else "IT2025"
    other_rules = "RULES1962" if rules == "RULES2026" else "RULES2026"
    refs = QueryRefs(tax_year=tax_year, act_id=act, rules_id=rules)

    def add(asked: str, target: str, via: str) -> None:
        if not any(m.asked == asked and m.target == target for m in refs.mappings):
            refs.mappings.append(Mapping(asked, target, via))

    def provision(num: str, subs: str, label: str, own: str, other: str) -> None:
        # The same number in the year's own Act (harmless if the corpus has no such provision) ...
        own_id = f"{own}:{label}{num.upper()}{subs}"
        add(own_id, own_id, "same Act")
        # ... and, if the number belongs to the other Act, where the concordance says it went.
        other_id = f"{other}:{label}{num.upper()}{subs}"
        for t in _concordance_map(other_id, own):
            add(other_id, t, "concordance")

    sections = [(m.group(1), m.group(2)) for m in SECTION_RE.finditer(question)]
    seen = {s.upper() for s, _ in sections}
    for b in BARE_RE.findall(question):
        letters = re.sub(r"\d", "", b).upper()
        if b.upper() not in seen and letters not in NOT_SECTIONS:
            sections.append((b, ""))
            seen.add(b.upper())
    for num, subs in sections:
        provision(num, subs, "s", act, other_act)
    for m in RULE_RE.finditer(question):
        provision(m.group(1), m.group(2), "r", rules, other_rules)
    for m in ARTICLE_RE.finditer(question):
        add(f"DTAA_US:art{m.group(1)}{m.group(2)}", f"DTAA_US:art{m.group(1)}{m.group(2)}", "treaty")
    for m in FORM_RE.finditer(question):
        key = re.sub(r"[\s-]", "", m.group(1)).upper()
        fid = FORM_IDS.get(key)
        if fid in ("FORM44:all", "FORM67:all"):  # Form 67 (1961) became Form 44 (2025)
            fid = "FORM44:all" if act == "IT2025" else "FORM67:all"
            add(f"FORM{key}", fid, "form" if fid.startswith(f"FORM{key}") else "concordance")
        elif fid:
            add(f"FORM{key}", fid, "form")
    return refs
