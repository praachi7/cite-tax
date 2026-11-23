"""Turn parsed and classified transactions into the engine's input shapes (Phase E -> Phase F).

The engine never imports this package. Data flows one way: ingest builds plain engine.models
objects, and the caller puts them into TaxpayerInput.

    receipts                -> Receipts                (receipt_mode.receipts_for_engine)
    export receipts         -> list[Remittance]        (feeds FIRA_MISSING)
    classified expenses     -> list[ClassifiedExpense] (feeds LOW_CLASSIFICATION_CONFIDENCE)

Note on confidence: the engine reads ClassifiedExpense.confidence as agreement across repeated
classifier samples (floor: flags.classification_confidence_min_percent, 80%). The rule-based
classifier's confidences are placeholder tiers (merchant 0.95, keyword 0.75; see expense_rules.yaml),
so keyword matches fall below the floor and are flagged for review. That is passed through on purpose;
the LLM stage replaces the tiers with measured agreement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from engine.models import ClassifiedExpense, Receipts, Remittance

from .models import Classification, Direction, ReceiptMode, Transaction
from .receipt_mode import receipts_for_engine, tax_year_bounds

HOME_COUNTRY = "IN"


def is_export_receipt(t: Transaction) -> bool:
    """A receipt from a client outside India: a foreign counterparty country, or paid in a foreign currency."""
    if t.direction is not Direction.receipt:
        return False
    country = t.counterparty_country.strip().upper()
    return (country not in ("", HOME_COUNTRY)) or t.currency.strip().upper() != "INR"


def remittances_for_engine(transactions: Iterable[Transaction], tax_year: int) -> list[Remittance]:
    """Export receipts of the tax year, with their FIRA / e-FIRA reference and RBI purpose code if known."""
    start, end = tax_year_bounds(tax_year)
    out = []
    for t in transactions:
        if is_export_receipt(t) and start <= t.date <= end:
            label = f"{t.id} {t.counterparty}".strip()
            out.append(Remittance(label=label, amount_inr=t.gross_inr,
                                  fira_ref=t.fira_ref or None, purpose_code=t.purpose_code or None))
    return out


def classifications_for_engine(transactions: Iterable[Transaction],
                               classifications: Iterable[Classification]) -> list[ClassifiedExpense]:
    """One ClassifiedExpense per classified expense row, carrying its amount and description."""
    by_id = {t.id: t for t in transactions}
    out = []
    for c in classifications:
        t = by_id.get(c.transaction_id)
        if t is None:
            raise ValueError(f"classification for unknown transaction {c.transaction_id!r}")
        if t.direction is not Direction.expense:
            continue  # receipts are never classified into expense labels
        out.append(ClassifiedExpense(label=c.category.value, confidence=c.confidence,
                                     amount_inr=t.amount_inr, description=t.description))
    return out


@dataclass
class EngineInputs:
    receipts: Receipts
    remittances: list[Remittance]
    expense_classifications: list[ClassifiedExpense]
    warnings: list[str] = field(default_factory=list)

    def as_fields(self) -> dict:
        """Keyword arguments to merge into TaxpayerInput(...)."""
        return {"receipts": self.receipts, "remittances": self.remittances,
                "expense_classifications": self.expense_classifications}


def engine_inputs(transactions: list[Transaction], classifications: Iterable[Classification], tax_year: int,
                  unknown_as: ReceiptMode = ReceiptMode.cash) -> EngineInputs:
    receipts, warnings = receipts_for_engine(transactions, tax_year, unknown_as=unknown_as)
    return EngineInputs(receipts=receipts,
                        remittances=remittances_for_engine(transactions, tax_year),
                        expense_classifications=classifications_for_engine(transactions, classifications),
                        warnings=warnings)


__all__ = ["EngineInputs", "engine_inputs", "remittances_for_engine", "classifications_for_engine",
           "is_export_receipt"]
