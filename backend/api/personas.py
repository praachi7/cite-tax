"""Test personas P1 to P10, read from the engine's golden fixtures."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PERSONA_DIR = Path(__file__).resolve().parents[1] / "tests" / "engine" / "personas"


@lru_cache(maxsize=1)
def load_personas() -> list[dict]:
    """Each persona's id, title and engine input, in numeric order. Expected values stay out: they are test data."""
    files = sorted(PERSONA_DIR.glob("p*.yaml"), key=lambda p: int(p.stem[1:]))
    out = []
    for path in files:
        fx = yaml.safe_load(path.read_text(encoding="utf8"))
        out.append({"id": fx["id"], "title": fx["title"], "input": fx["input"]})
    return out
