"""Phase C step C7: embed every corpus chunk with BGE-M3, cached by content hash.

Only new or changed chunks are embedded. The cache is build/embeddings/<model>.npz
(git-ignored) and holds {content_hash: vector}.

Run from the repo root:  .venv/Scripts/python scripts/embed_chunks.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lawdata.chunks import load_all_chunks  # noqa: E402
from retrieval.embedder import MODEL_NAME, embed  # noqa: E402

CACHE = ROOT / "build" / "embeddings" / f"{MODEL_NAME.replace('/', '__')}.npz"


def load_cache() -> dict[str, np.ndarray]:
    if not CACHE.exists():
        return {}
    data = np.load(CACHE)
    return {k: data[k] for k in data.files}


def main() -> int:
    chunks = load_all_chunks()
    cache = load_cache()
    todo = [c for c in chunks if c.content_hash not in cache]
    print(f"{len(chunks)} chunks, {len(chunks) - len(todo)} cached, {len(todo)} to embed with {MODEL_NAME}")
    if todo:
        # longest first, so batches hold similar lengths and padding is small
        todo.sort(key=lambda c: len(c.embed_text), reverse=True)
        t0 = time.time()
        vecs = embed([c.embed_text for c in todo])
        print(f"embedded in {time.time() - t0:.0f} s")
        for c, v in zip(todo, vecs):
            cache[c.content_hash] = v
    live = {c.content_hash for c in chunks}
    cache = {k: v for k, v in cache.items() if k in live}  # drop vectors of deleted or edited chunks
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, **cache)
    print(f"cache: {CACHE.relative_to(ROOT)} ({len(cache)} vectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
