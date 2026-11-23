"""Phase E output feeds the Phase F engine: synthetic CSV rows -> classifier -> adapter -> engine flags."""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.models import TaxpayerInput
from engine.pipeline import run
from ingest.classifier import classify_all
from ingest.models import Classification, Direction, ExpenseCategory, Transaction
from ingest.synthetic import PERSONAS, generate
from ingest.to_engine import engine_inputs, is_export_receipt

FIXTURES = Path(__file__).resolve().parents[1] / "engine" / "personas"


def _fixture_input(pid: str) -> dict:
    return yaml.safe_load((FIXTURES / f"{pid.lower()}.yaml").read_text(encoding="utf8"))["input"]


def _run(pid: str, transactions, classifications):
    fx = _fixture_input(pid)
    ei = engine_inputs(transactions, classifications, fx["tax_year"])
    result = run(TaxpayerInput(**{**fx, **ei.as_fields()}))
    return ei, result, {f.code for f in result.flags}


@pytest.mark.parametrize("pid", list(PERSONAS))
def test_every_persona_runs_end_to_end(pid):
    g = generate(pid)
    ei, result, codes = _run(pid, g.transactions, classify_all(g.transactions))
    assert ei.receipts.total == sum(g.persona.receipts_by_mode().values())
    exports = [t for t in g.transactions if is_export_receipt(t)]
    assert len(ei.remittances) == len(exports)
    # FIRA_MISSING fires exactly when some export receipt lacks a FIRA reference or purpose code
    lacking = any(not r.fira_ref or not r.purpose_code for r in ei.remittances)
    assert ("FIRA_MISSING" in codes) == lacking
    # LOW_CLASSIFICATION_CONFIDENCE fires exactly when some expense is uncertain or below the 80% floor
    weak = any(c.label == "uncertain" or c.confidence < Decimal("0.8") for c in ei.expense_classifications)
    assert ("LOW_CLASSIFICATION_CONFIDENCE" in codes) == weak


@pytest.mark.parametrize("pid", list(PERSONAS))
def test_classifications_never_change_income_or_tax(pid):
    g = generate(pid)
    _, with_labels, _ = _run(pid, g.transactions, classify_all(g.transactions))
    _, without, _ = _run(pid, g.transactions, [])
    assert with_labels.income == without.income
    assert with_labels.india_tax == without.india_tax


def _tx(tid, direction, country="US", currency="USD", fira="", code="", amount="100000"):
    return Transaction(id=tid, date="2026-06-15", direction=direction, amount=Decimal(amount), currency=currency,
                       amount_inr=Decimal(amount), counterparty="Client", counterparty_country=country,
                       description="x", fira_ref=fira, purpose_code=code,
                       receipt_mode="electronic" if direction is Direction.receipt else None)


def test_only_foreign_receipts_become_remittances():
    txs = [_tx("r1", Direction.receipt, fira="F1", code="P0802"),
           _tx("r2", Direction.receipt, country="IN", currency="INR"),
           _tx("e1", Direction.expense)]
    ei = engine_inputs(txs, [], 2026)
    assert [r.label for r in ei.remittances] == ["r1 Client"]
    assert ei.remittances[0].fira_ref == "F1" and ei.remittances[0].purpose_code == "P0802"


def test_blank_fira_becomes_none_so_the_flag_can_see_it():
    ei = engine_inputs([_tx("r1", Direction.receipt)], [], 2026)
    assert ei.remittances[0].fira_ref is None and ei.remittances[0].purpose_code is None


def test_classification_of_an_unknown_transaction_is_rejected():
    bad = Classification(transaction_id="nope", category=ExpenseCategory.personal, confidence=Decimal(1), method="rule")
    with pytest.raises(ValueError):
        engine_inputs([_tx("e1", Direction.expense)], [bad], 2026)
