"""Receipt-mode tagging and the receipts total the tax engine needs.

The presumptive ITR schedules split gross receipts by mode, and the Rs 75 lakh limit depends on the
cash share (s.44ADA(1) proviso; s.58(2) Table Sl. 3). A receipt whose mode is not known is counted as
cash: if that is wrong the user loses only the higher limit they would otherwise have had, and the
review screen asks them to confirm the mode.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from engine.models import Receipts

from .models import Direction, ModeSource, ReceiptMode, Transaction

_COLUMN_ALIASES = {
    "electronic": ReceiptMode.electronic, "account_payee": ReceiptMode.electronic, "a/c payee": ReceiptMode.electronic,
    "account payee": ReceiptMode.electronic, "account-payee": ReceiptMode.electronic, "bank": ReceiptMode.electronic,
    "neft": ReceiptMode.electronic, "rtgs": ReceiptMode.electronic, "imps": ReceiptMode.electronic,
    "upi": ReceiptMode.electronic, "swift": ReceiptMode.electronic, "wire": ReceiptMode.electronic,
    "ecs": ReceiptMode.electronic, "ach": ReceiptMode.electronic,
    "cash": ReceiptMode.cash,
    "other": ReceiptMode.other, "bearer_cheque": ReceiptMode.other, "non_account_payee_cheque": ReceiptMode.other,
    "unknown": ReceiptMode.unknown, "": ReceiptMode.unknown,
}

# Order matters: the first pattern that matches decides.
_DESCRIPTION_RULES: list[tuple[re.Pattern, ReceiptMode, str]] = [
    (re.compile(r"\bcash\b|\bcsh\s*dep", re.I), ReceiptMode.cash, "description mentions cash"),
    (re.compile(r"\b(a/?c|account)[\s-]*payee\b", re.I), ReceiptMode.electronic, "account-payee cheque or draft"),
    (re.compile(r"\b(bearer|self)\s*(chq|cheque)\b", re.I), ReceiptMode.other, "bearer cheque"),
    (re.compile(r"\b(chq|cheque|clg|clearing|dd|draft)\b", re.I), ReceiptMode.unknown,
     "cheque or draft not shown as account-payee; confirm the crossing"),
    (re.compile(r"\b(neft|rtgs|imps|upi|swift|inward\s+remit\w*|wire|ach|ecs|payoneer|wise|transferwise|"
                r"paypal|skydo|razorpay|stripe|fira|firc)\b", re.I),
     ReceiptMode.electronic, "electronic channel named in the description"),
]


def parse_mode_column(raw: str) -> Optional[ReceiptMode]:
    """Map a receipt_mode cell to a mode. None means the cell holds something unrecognised."""
    key = raw.strip().lower()
    if key in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[key]
    return _COLUMN_ALIASES.get(key.replace("-", "_").replace(" ", "_"))


def tag_receipt_mode(column_value: str, description: str) -> tuple[ReceiptMode, ModeSource, str]:
    """Decide a receipt's mode. A mode named in the column wins; otherwise the description is read."""
    mode = parse_mode_column(column_value or "")
    if mode is not None and mode is not ReceiptMode.unknown:
        return mode, ModeSource.column, "receipt_mode column"
    for pattern, inferred, reason in _DESCRIPTION_RULES:
        if pattern.search(description or ""):
            source = ModeSource.none if inferred is ReceiptMode.unknown else ModeSource.inferred
            return inferred, source, reason
    return ReceiptMode.unknown, ModeSource.none, "no mode in the file or the description"


def tax_year_bounds(tax_year: int) -> tuple[date, date]:
    """1 April of the start year to 31 March of the next (tax years are keyed by start year)."""
    return date(tax_year, 4, 1), date(tax_year + 1, 3, 31)


def receipts_for_engine(transactions: Iterable[Transaction], tax_year: int,
                        unknown_as: ReceiptMode = ReceiptMode.cash) -> tuple[Receipts, list[str]]:
    """Total the year's receipts by mode for the engine. Returns the totals and warnings.

    Built from receipt rows only. Expense rows and their classifications are not read, so no
    classification can change gross receipts or presumptive income.
    """
    if unknown_as not in (ReceiptMode.cash, ReceiptMode.other):
        raise ValueError("unknown receipts can only be counted as cash or other (both cash-like)")
    start, end = tax_year_bounds(tax_year)
    buckets = {"electronic": Decimal(0), "cash": Decimal(0), "non_account_payee_cheque": Decimal(0)}
    warnings: list[str] = []
    for t in transactions:
        if t.direction is not Direction.receipt:
            continue
        if not (start <= t.date <= end):
            warnings.append(f"{t.id}: dated {t.date.isoformat()}, outside tax year {tax_year}; left out")
            continue
        mode = t.receipt_mode
        if mode is ReceiptMode.unknown:
            warnings.append(f"{t.id}: receipt mode unknown ({t.mode_reason}); counted as {unknown_as.value}")
            mode = unknown_as
        key = {"electronic": "electronic", "cash": "cash", "other": "non_account_payee_cheque"}[mode.value]
        buckets[key] += t.gross_inr
    return Receipts(**buckets), warnings
