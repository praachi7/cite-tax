"""PostgreSQL + pgvector access for the retrieval index (docker compose service `db`)."""
from __future__ import annotations

import os
import re

import psycopg
from pgvector.psycopg import register_vector

from .embedder import DIM

DB_URL = os.environ.get("CITETAX_DB_URL", "postgresql://citetax:citetax@localhost:5433/citetax")

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
  id              text PRIMARY KEY,
  source_id       text NOT NULL,
  doc_type        text NOT NULL,
  authority_rank  smallint NOT NULL,
  tax_year_first  smallint,
  tax_year_last   smallint,
  breadcrumb      text NOT NULL,
  heading         text,
  body            text NOT NULL,
  covers          text[] NOT NULL DEFAULT '{{}}',
  cross_refs      text[] NOT NULL DEFAULT '{{}}',
  id_terms        text NOT NULL,
  content_hash    text NOT NULL,
  embed_model     text NOT NULL,
  embedding       vector({DIM}) NOT NULL,
  tsv             tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', id_terms || ' ' || breadcrumb || ' ' || coalesce(heading, '') || ' ' || body)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
"""

# Applies to every query: a chunk is eligible only if the tax year falls inside its validity.
YEAR_FILTER = ("(tax_year_first IS NULL OR tax_year_first <= %(year)s) "
               "AND (tax_year_last IS NULL OR tax_year_last >= %(year)s)")


def connect() -> psycopg.Connection:
    conn = psycopg.connect(DB_URL, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def id_terms(cid: str) -> str:
    """Searchable tokens of a citation id: IT2025:s58(2)/T3 -> 'IT2025 s58 2 T3 58'."""
    parts = [p for p in re.split(r"[:()/]", cid) if p]
    nums = [re.sub(r"^(s|r|art)(?=\d)", "", p) for p in parts]
    return " ".join(dict.fromkeys(parts + nums))
