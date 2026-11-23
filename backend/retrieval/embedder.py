"""BGE-M3 dense embeddings, run locally on CPU.

The model is loaded once per process (about 2.3 GB, 10-20 s cold start). Vectors are
L2-normalised, so cosine similarity is a dot product. Swapping the model means changing
MODEL_NAME and DIM and rebuilding the index; the database records which model made each vector.
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

MODEL_NAME = os.environ.get("CITETAX_EMBED_MODEL", "BAAI/bge-m3")
DIM = 1024
MAX_TOKENS = 2048  # chunks are short; a few long ones (s.139(1), Pub 519) are reviewed for splitting


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # heavy import, only when needed

    try:
        # Once the model is cached, load it with no network access. Online loading also starts a
        # background download of a second copy of the weights (a safetensors conversion), ~2.3 GB.
        m = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
    except OSError:
        m = SentenceTransformer(MODEL_NAME, device="cpu")  # first run: download once
    m.max_seq_length = MAX_TOKENS
    return m


def embed(texts: list[str], batch_size: int = 4) -> np.ndarray:
    vecs = _model().encode(texts, batch_size=batch_size, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=len(texts) > 20)
    return vecs.astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed([text])[0]
