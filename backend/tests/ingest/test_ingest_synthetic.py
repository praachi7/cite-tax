"""Synthetic data for P1 to P10 loads cleanly and reproduces the engine's golden inputs and outputs."""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.models import TaxpayerInput
from engine.pipeline import run
from ingest.classifier import classify_all, compare_profit
from ingest.csv_parser import parse_csv_text, to_csv_text
from ingest.evaluate import evaluate_personas
from ingest.models import BUSINESS_CATEGORIES, Classification, Direction, ModeSource
from ingest.receipt_mode import receipts_for_engine
from ingest.synthetic import PERSONAS, generate, split_exact

FIXTURES = Path(__file__).resolve().parents[1] / "engine" / "personas"
IDS = list(PERSONAS)


def fixture_input(pid):
    return yaml.safe_load((FIXTURES / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]


def load(pid):
    g = generate(pid)
    res = parse_csv_text(to_csv_text(g.transactions, g.blank_mode_ids))
    return g, res


def test_every_persona_has_a_spec_and_a_fixture():
    assert IDS == [f"P{i}" for i in range(1, 11)]
    assert all((FIXTURES / f"{p.lower()}.yaml").exists() for p in IDS)


@pytest.mark.parametrize("pid", IDS)
def test_csv_loads_cleanly(pid):
    g, res = load(pid)
    assert res.ok, res.errors
    assert len(res.transactions) == len(g.transactions)
    receipts, warnings = receipts_for_engine(res.transactions, g.persona.tax_year)
    assert warnings == []
    # rows written with no mode were inferred from the description, not left unknown
    inferred = [t for t in res.transactions if t.id in g.blank_mode_ids]
    assert all(t.mode_source is ModeSource.inferred for t in inferred)


@pytest.mark.parametrize("pid", IDS)
def test_receipts_match_the_engine_fixture(pid):
    g, res = load(pid)
    fx = fixture_input(pid)
    assert g.persona.tax_year == fx["tax_year"]
    receipts, _ = receipts_for_engine(res.transactions, g.persona.tax_year)
    expected = {"electronic": 0, "cash": 0, "non_account_payee_cheque": 0, **fx["receipts"]}
    assert receipts.model_dump() == {k: Decimal(v) for k, v in expected.items()}
    withheld = sum(t.foreign_tax_withheld_inr for t in res.transactions)
    assert withheld == sum(Decimal(e.get("us_tax_withheld_inr", 0)) for e in fx.get("engagements", []))


@pytest.mark.parametrize("pid", IDS)
def test_engine_on_ingested_receipts_equals_the_golden_run(pid):
    g, res = load(pid)
    fx = fixture_input(pid)
    receipts, _ = receipts_for_engine(res.transactions, g.persona.tax_year)
    golden = run(TaxpayerInput(**fx))
    ingested = run(TaxpayerInput(**{**fx, "receipts": receipts.model_dump()}))
    assert ingested.model_dump() == golden.model_dump()


@pytest.mark.parametrize("pid", ["P4", "P10"])
def test_gold_business_expenses_reproduce_declared_profit(pid):
    g, res = load(pid)
    fx = fixture_input(pid)
    result = run(TaxpayerInput(**fx))
    gold = [Classification(transaction_id=i, category=c, confidence=Decimal(1), method="gold") for i, c in g.gold.items()]
    pc = compare_profit(res.transactions, gold, result.receipts_test.total, result.income.presumptive_amount)
    assert pc.actual_profit_high == Decimal(fx["declared_profit"])


def test_generation_is_deterministic_and_seeded():
    a, b = generate("P3", seed=1), generate("P3", seed=1)
    assert to_csv_text(a.transactions) == to_csv_text(b.transactions) and a.gold == b.gold
    assert to_csv_text(generate("P3", seed=2).transactions) != to_csv_text(a.transactions)


def test_gold_labels_cover_every_expense():
    for pid in IDS:
        g = generate(pid)
        expenses = {t.id for t in g.transactions if t.direction is Direction.expense}
        assert expenses == set(g.gold) == set(g.kind)
        biz = sum(t.amount_inr for t in g.transactions if g.gold.get(t.id) in BUSINESS_CATEGORIES)
        assert biz == g.persona.business_expenses_inr


@pytest.mark.parametrize("total, parts", [(10, 10), (2_400_000, 12), (1_800_000, 40), (7, 3)])
def test_split_exact(total, parts):
    import random
    out = split_exact(total, parts, random.Random(0))
    assert sum(out) == total and len(out) == parts and min(out) >= 1


def test_classifier_accuracy_and_abstention_on_the_labelled_set():
    """Measured numbers, pinned so a rule change that moves them is noticed. Not a quality claim:
    the rules and the "known" templates share authors, so only the hard rows say much."""
    m = evaluate_personas()
    assert m["n"] == sum(len(generate(p).gold) for p in IDS)
    assert m["by_kind"]["known"]["committed_correct"] == m["by_kind"]["known"]["n"]
    assert m["by_kind"]["ambiguous"]["committed"] == 0          # mixed-use merchants: always abstain
    assert m["by_kind"]["unseen"]["committed"] == 0             # unknown merchants: abstain, never guess
    assert m["by_kind"]["trap"]["committed_correct"] == 0       # the known failure mode: purpose is invisible
    assert m["committed_accuracy"] < 1                          # so committed accuracy is not perfect
    assert m["errors"] == ["personal -> business_travel x20", "personal -> hardware_equipment x20"]
    assert Decimal("0.70") < m["coverage"] < Decimal("0.80")


def test_classify_all_on_generated_set_covers_expenses_only():
    g = generate("P1")
    cls = classify_all(g.transactions)
    assert {c.transaction_id for c in cls} == set(g.gold)
