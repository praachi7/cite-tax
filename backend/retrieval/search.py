"""retrieve(question, tax_year): tax-year-filtered hybrid search over the corpus chunks.

1. Act from the tax year (engine ParamSet), never from the language model.
2. Detect section, rule, article and form references; map old numbers through the concordance.
3. Hard SQL filter on tax year before any ranking, so the other Act's text never competes.
4. Ranked lists: exact citation match and dense (BGE-M3 cosine) by default; keyword (Postgres full
   text) is available for the ablation but off by default (see DEFAULT_LISTS).
5. Reciprocal rank fusion (k = 60); ties go to the higher authority (statute before guidance).
6. Cross-references of the top hits are attached as context, not ranked.
7. Every hit carries a trace of which lists found it and at what rank (Phase D uses this).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import psycopg

from .db import YEAR_FILTER, connect
from .embedder import embed_query
from .refs import QueryRefs, detect

RRF_K = 60
LIST_DEPTH = 30
STOPWORDS = set("""a an the of to in on for and or is are was were be been do does did i my me we our you your
it its this that these those what which who whom how when where why can could should would will shall may might
must have has had not no if as at by from with about into than then there their them they he she his her
under per any all each also so such""".split())


@dataclass
class Hit:
    id: str
    breadcrumb: str
    heading: str | None
    text: str
    authority_rank: int
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # list name -> 1-based rank


@dataclass
class RetrievalResult:
    question: str
    tax_year: int
    act_id: str
    refs: QueryRefs
    hits: list[Hit]
    context: list[Hit]  # cross-referenced chunks of the top hits

    def ids(self) -> list[str]:
        return [h.id for h in self.hits]


_COLS = "id, breadcrumb, heading, body, authority_rank"


def _exact(cur: psycopg.Cursor, refs: QueryRefs, year: int) -> list[str]:
    out: list[str] = []
    for t in refs.targets:
        if t.endswith(":all"):
            rows = cur.execute(f"SELECT id FROM chunks WHERE id LIKE %(p)s AND {YEAR_FILTER} ORDER BY id LIMIT 3",
                               {"p": t[:-3] + "%", "year": year}).fetchall()
        else:
            rows = cur.execute(
                f"""SELECT id FROM chunks
                    WHERE (id = %(t)s OR %(t)s = ANY(covers)
                           OR id LIKE %(t)s || '(%%' OR id LIKE %(t)s || '/%%'
                           OR %(t)s LIKE id || '(%%' OR %(t)s LIKE id || '/%%')
                      AND {YEAR_FILTER}
                    ORDER BY (id = %(t)s OR %(t)s = ANY(covers)) DESC, length(id), id LIMIT 6""",
                {"t": t, "year": year}).fetchall()
        out += [r[0] for r in rows if r[0] not in out]
    return out


def _dense(cur: psycopg.Cursor, question: str, year: int) -> list[str]:
    q = embed_query(question)
    rows = cur.execute(f"SELECT id FROM chunks WHERE {YEAR_FILTER} ORDER BY embedding <=> %(q)s LIMIT {LIST_DEPTH}",
                       {"q": q, "year": year}).fetchall()
    return [r[0] for r in rows]


def keyword_terms(question: str, refs: QueryRefs) -> list[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    terms = [w for w in words if w not in STOPWORDS and (len(w) > 1 or w.isdigit())]
    terms += [t.lower() for t in refs.search_terms]
    return list(dict.fromkeys(terms))


def _keyword(cur: psycopg.Cursor, question: str, refs: QueryRefs, year: int) -> list[str]:
    terms = keyword_terms(question, refs)
    if not terms:
        return []
    rows = cur.execute(
        f"""SELECT id FROM chunks, to_tsquery('simple', %(q)s) query
            WHERE tsv @@ query AND {YEAR_FILTER}
            ORDER BY ts_rank_cd(tsv, query) DESC, authority_rank, id LIMIT {LIST_DEPTH}""",
        # Length normalisation (flag 1) was tried on 23 Nov 2026 and lowered hit@5 from 0.80 to 0.775.
        {"q": " | ".join(terms), "year": year}).fetchall()
    return [r[0] for r in rows]


def fuse(lists: dict[str, list[str]]) -> dict[str, tuple[float, dict[str, int]]]:
    fused: dict[str, tuple[float, dict[str, int]]] = {}
    for name, ids in lists.items():
        for rank, cid in enumerate(ids, start=1):
            score, ranks = fused.get(cid, (0.0, {}))
            ranks[name] = rank
            fused[cid] = (score + 1.0 / (RRF_K + rank), ranks)
    return fused


def _rows(cur: psycopg.Cursor, ids: list[str], year: int) -> dict[str, tuple]:
    if not ids:
        return {}
    rows = cur.execute(f"SELECT {_COLS} FROM chunks WHERE id = ANY(%(ids)s) AND {YEAR_FILTER}",
                       {"ids": ids, "year": year}).fetchall()
    return {r[0]: r for r in rows}


# Exact citation match + dense vectors. Keyword search is kept for the ablation only: on the labelled set
# (23 Nov 2026) adding it at full weight lowered hit@5 from 0.85 to 0.80 and hit@10 from 0.925 to 0.825,
# because the exact list already covers section numbers and keyword ranking favours long FAQ answers.
DEFAULT_LISTS = ("exact", "dense")


def retrieve(question: str, tax_year: int, k: int = 8, use: tuple[str, ...] = DEFAULT_LISTS,
             conn: psycopg.Connection | None = None) -> RetrievalResult:
    """`use` picks the ranked lists, so the evaluation can measure each one alone (ablation)."""
    refs = detect(question, tax_year)
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            lists: dict[str, list[str]] = {}
            if "exact" in use:
                lists["exact"] = _exact(cur, refs, tax_year)
            if "dense" in use:
                lists["dense"] = _dense(cur, question, tax_year)
            if "keyword" in use:
                lists["keyword"] = _keyword(cur, question, refs, tax_year)
            fused = fuse(lists)
            rows = _rows(cur, list(fused), tax_year)
            order = sorted(fused, key=lambda cid: (-fused[cid][0], rows[cid][4], cid))[:k]
            hits = [Hit(cid, rows[cid][1], rows[cid][2], rows[cid][3], rows[cid][4], fused[cid][0], fused[cid][1])
                    for cid in order]
            refs_wanted = cur.execute("SELECT DISTINCT unnest(cross_refs) FROM chunks WHERE id = ANY(%(ids)s)",
                                      {"ids": order[:3]}).fetchall()
            extra = [r[0] for r in refs_wanted if r[0] not in order]
            ctx_rows = _rows(cur, extra, tax_year)
            context = [Hit(cid, r[1], r[2], r[3], r[4], 0.0, {"cross_ref": 1}) for cid, r in ctx_rows.items()]
    finally:
        if own:
            conn.close()
    return RetrievalResult(question, tax_year, refs.act_id, refs, hits, context)
