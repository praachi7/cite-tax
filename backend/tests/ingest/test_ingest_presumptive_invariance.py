"""Classification never changes presumptive income (s.44ADA(2); s.58(4) of the 2025 Act).

Three layers: the engine's receipts are built from receipt rows only; any relabelling or rewriting of
expenses leaves the engine result byte-identical; and the import graph has no path from the
classifier to the engine's computation.
"""
import ast
import random
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.models import TaxpayerInput
from engine.pipeline import run
from ingest.classifier import classify_all, compare_profit
from ingest.models import Classification, Direction, ExpenseCategory, Transaction
from ingest.receipt_mode import receipts_for_engine
from ingest.synthetic import PERSONAS, generate

BACKEND = Path(__file__).resolve().parents[2]
FIXTURES = BACKEND / "tests" / "engine" / "personas"


def _engine(pid, transactions):
    fx = yaml.safe_load((FIXTURES / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]
    receipts, _ = receipts_for_engine(transactions, fx["tax_year"])
    return run(TaxpayerInput(**{**fx, "receipts": receipts.model_dump()})).model_dump()


@pytest.mark.parametrize("pid", list(PERSONAS))
def test_rewriting_expenses_leaves_the_engine_result_unchanged(pid):
    g = generate(pid)
    base = _engine(pid, g.transactions)
    rng = random.Random(pid)
    receipts = [t for t in g.transactions if t.direction is Direction.receipt]
    expenses = [t for t in g.transactions if t.direction is Direction.expense]

    inflated = [t.model_copy(update={"amount": t.amount * 100, "amount_inr": t.amount_inr * 100}) for t in expenses]
    reworded = [t.model_copy(update={"description": rng.choice(["GITHUB", "NETFLIX", "AMAZON PAY", "WEWORK"])})
                for t in expenses]
    for variant in ([], inflated, reworded, expenses[::2]):
        assert _engine(pid, receipts + variant) == base


@pytest.mark.parametrize("pid", list(PERSONAS))
def test_relabelling_changes_the_profit_comparison_but_not_presumptive_income(pid):
    g = generate(pid)
    result = run(TaxpayerInput(**{**yaml.safe_load((FIXTURES / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]}))
    income_before = result.income.model_dump()
    rng = random.Random(f"relabel:{pid}")
    labels = list(ExpenseCategory)
    seen_actual = set()
    for _ in range(20):
        cls = [Classification(transaction_id=c.transaction_id, category=rng.choice(labels), confidence=Decimal(1),
                              method="test") for c in classify_all(g.transactions)]
        pc = compare_profit(g.transactions, cls, result.receipts_test.total, result.income.presumptive_amount)
        seen_actual.add(pc.actual_profit_high)
        assert pc.presumptive_income == result.income.presumptive_amount
    assert len(seen_actual) > 1      # the labels did move the comparison, so the test is not vacuous
    assert _engine(pid, g.transactions)["income"] == income_before


def test_receipts_for_engine_reads_no_expense_or_classification_field():
    """Expense rows are skipped before any field is read; even a malformed copy would not be touched."""
    g = generate("P1")
    receipts = [t for t in g.transactions if t.direction is Direction.receipt]
    poisoned = [Transaction.model_construct(id="x", direction=Direction.expense)]   # no amount, no date
    assert receipts_for_engine(receipts + poisoned, 2026) == receipts_for_engine(receipts, 2026)


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield ("." * node.level) + node.module


def test_import_graph_keeps_classification_out_of_the_engine():
    for f in (BACKEND / "engine").rglob("*.py"):
        assert not any(m.split(".")[0] == "ingest" for m in _imports(f)), f"engine file {f.name} imports ingest"
    for f in (BACKEND / "ingest").rglob("*.py"):
        engine_mods = {m for m in _imports(f) if m.startswith("engine")}
        assert engine_mods <= {"engine.models"}, f"{f.name} imports {engine_mods}"
    users = [f.name for f in (BACKEND / "ingest").rglob("*.py") if "engine.models" in set(_imports(f))]
    assert users == ["receipt_mode.py"]


def test_ingest_uses_no_language_model_or_network():
    banned = {"anthropic", "openai", "langchain", "requests", "httpx", "urllib", "socket", "http", "aiohttp"}
    for f in (BACKEND / "ingest").rglob("*.py"):
        assert not {m.lstrip(".").split(".")[0] for m in _imports(f)} & banned, f.name
