"""Retrieval against the live index. Skipped unless Postgres is up and the index is loaded:

    docker compose up -d db
    .venv/Scripts/python scripts/embed_chunks.py && .venv/Scripts/python scripts/load_index.py
"""
from pathlib import Path

import pytest
import yaml

QUERIES_PATH = Path(__file__).with_name("queries.yaml")
psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def conn():
    from retrieval.db import connect
    try:
        c = connect()
        if c.execute("SELECT to_regclass('chunks')").fetchone()[0] is None:
            pytest.skip("index not loaded (run scripts/load_index.py)")
    except psycopg.OperationalError:
        pytest.skip("database not running (docker compose up -d db)")
    yield c
    c.close()


QUERIES = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf8"))["queries"]
TEMPORAL = [q for q in QUERIES if q["category"] == "temporal"]


@pytest.mark.parametrize("q", TEMPORAL, ids=[q["id"] for q in TEMPORAL])
def test_temporal_trap_finds_the_right_act_in_top_3(conn, q):
    from retrieval.search import retrieve
    ids = retrieve(q["q"], q["year"], k=3, conn=conn).ids()
    assert set(ids) & set(q["expect"]), f"{q['q']} ({q['year']}) returned {ids}"


@pytest.mark.parametrize("q", QUERIES, ids=[q["id"] for q in QUERIES])
def test_nothing_from_the_wrong_act_is_ever_returned(conn, q):
    from retrieval.search import retrieve
    res = retrieve(q["q"], q["year"], k=10, conn=conn)
    rows = conn.execute("SELECT id, tax_year_first, tax_year_last FROM chunks WHERE id = ANY(%s)",
                        ([h.id for h in res.hits + res.context],)).fetchall()
    for cid, lo, hi in rows:
        assert (lo is None or lo <= q["year"]) and (hi is None or hi >= q["year"]), cid


def test_hits_carry_a_trace(conn):
    from retrieval.search import retrieve
    res = retrieve("What is the 44ADA limit?", 2026, conn=conn)
    top = res.hits[0]
    assert top.id == "IT2025:s58(2)/T3"
    assert "exact" in top.ranks
    assert any(m.via == "concordance" for m in res.refs.mappings)
