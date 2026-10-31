"""The engine runs with no database, no language model and no network."""
import ast
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from engine.models import TaxpayerInput
from engine.pipeline import run

ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"
FORBIDDEN = {"socket", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "ssl", "sqlite3", "sqlalchemy",
             "psycopg", "psycopg2", "asyncpg", "pymongo", "redis", "anthropic", "openai", "langchain", "sentence_transformers"}


# Third-party libraries only: the standard library is loaded transitively by pydantic and PyYAML, and
# network use by the engine itself is covered by the source scan and by the socket test below.
THIRD_PARTY_FORBIDDEN = FORBIDDEN - {"socket", "http", "urllib", "ssl", "sqlite3"}


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_engine_source_imports_no_network_database_or_model_library():
    files = list(ENGINE_DIR.rglob("*.py"))
    assert files
    for f in files:
        bad = set(_imports(f)) & FORBIDDEN
        assert not bad, f"{f.name} imports {bad}"


def test_importing_the_engine_loads_no_forbidden_module():
    code = ("import sys; import engine.pipeline; "
            f"bad = sorted(m for m in sys.modules if m.split('.')[0] in {sorted(THIRD_PARTY_FORBIDDEN)!r}); "
            "print(','.join(bad))")
    env = dict(os.environ, PYTHONPATH=str(ENGINE_DIR.parent))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip() == "", out.stdout


def test_a_full_run_opens_no_socket(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the engine tried to open a network socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    r = run(TaxpayerInput(tax_year=2026, receipts=dict(electronic=4000000),
                          engagements=[dict(country_of_performance="US", amount_inr=800000, us_tax_withheld_inr=240000),
                                       dict(country_of_performance="IN", amount_inr=3200000)],
                          us_days_by_year={2026: 95}))
    assert r.india_tax.in_force.payable == 208000


def test_the_engine_is_deterministic():
    inp = TaxpayerInput(tax_year=2026, receipts=dict(electronic=4000000))
    assert run(inp).model_dump(mode="json") == run(inp).model_dump(mode="json")
