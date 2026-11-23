"""Phase C step C8: (re)build the retrieval index in Postgres from the chunk files and cached vectors.

Run scripts/embed_chunks.py first. The table is rebuilt from scratch each time: the chunk
files are the source of truth, so nothing in the database needs to be kept.

Run from the repo root (with `docker compose up -d db`):  .venv/Scripts/python scripts/load_index.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from embed_chunks import load_cache  # noqa: E402
from lawdata.chunks import load_all_chunks  # noqa: E402
from lawdata.loader import load_registry  # noqa: E402
from retrieval.db import SCHEMA, connect, id_terms  # noqa: E402
from retrieval.embedder import MODEL_NAME  # noqa: E402


def main() -> int:
    chunks = load_all_chunks()
    cache = load_cache()
    missing = [c.id for c in chunks if c.content_hash not in cache]
    if missing:
        print(f"{len(missing)} chunks have no vector; run scripts/embed_chunks.py first (e.g. {missing[:3]})")
        return 1
    doc_type = {s.id: s.doc_type.value for s in load_registry()}
    with connect() as conn:
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute(SCHEMA)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (id, source_id, doc_type, authority_rank, tax_year_first, tax_year_last,
                       breadcrumb, heading, body, covers, cross_refs, id_terms, content_hash, embed_model, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(c.id, c.source_id, doc_type[c.source_id], c.authority_rank, c.tax_year_first, c.tax_year_last,
                  c.breadcrumb, c.heading, c.text, c.covers, c.cross_refs,
                  " ".join([id_terms(c.id)] + [id_terms(a) for a in c.covers]),
                  c.content_hash, MODEL_NAME, cache[c.content_hash]) for c in chunks])
        n = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    print(f"loaded {n} chunks into the index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
