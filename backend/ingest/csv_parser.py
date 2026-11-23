"""Transaction CSV parsing (SRS/SDS v2: one row per transaction).

Columns (header names are case-insensitive; common bank-export aliases are accepted):
  required  date, amount, direction
  optional  id, currency (default INR), amount_inr, fx_rate, foreign_tax_withheld_inr, counterparty,
            counterparty_country, description, receipt_mode, fira_ref, purpose_code

Rules:
  * Dates are ISO (2026-04-15) or Indian day-first (15/04/2026, 15-04-2026). Month-first is not accepted.
  * Amounts are positive; the direction gives the sign. Commas, "Rs", "INR" and the rupee sign are stripped.
  * A foreign-currency row needs amount_inr (the rupees credited) or fx_rate. No rate is ever looked up.
  * Bad rows are reported with their line number and left out; nothing is guessed or silently dropped.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .models import Direction, ParseResult, RowError, Transaction
from .receipt_mode import tag_receipt_mode

REQUIRED = ("date", "amount", "direction")
KNOWN = REQUIRED + ("id", "currency", "amount_inr", "fx_rate", "foreign_tax_withheld_inr", "counterparty",
                    "counterparty_country", "description", "receipt_mode", "fira_ref", "purpose_code")

HEADER_ALIASES = {
    "txn_date": "date", "transaction_date": "date", "value_date": "date",
    "type": "direction", "dr_cr": "direction", "cr_dr": "direction",
    "narration": "description", "particulars": "description", "remarks": "description",
    "mode": "receipt_mode", "payment_mode": "receipt_mode",
    "client": "counterparty", "payee": "counterparty", "payer": "counterparty",
    "country": "counterparty_country",
    "firc": "fira_ref", "fira": "fira_ref", "e_fira": "fira_ref",
    "rbi_purpose_code": "purpose_code",
    "inr_amount": "amount_inr", "amount_in_inr": "amount_inr",
    "tax_withheld_inr": "foreign_tax_withheld_inr", "withholding_inr": "foreign_tax_withheld_inr",
}

DIRECTIONS = {
    "receipt": Direction.receipt, "credit": Direction.receipt, "cr": Direction.receipt, "in": Direction.receipt,
    "income": Direction.receipt,
    "expense": Direction.expense, "debit": Direction.expense, "dr": Direction.expense, "out": Direction.expense,
    "payment": Direction.expense,
}

_MONEY_JUNK = re.compile(r"(?i)rs\.?|inr|₹|,|\s")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")


class _RowFault(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


def _norm_header(h: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")
    return HEADER_ALIASES.get(key, key)


def _date(raw: str) -> date:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise _RowFault("date", f"unreadable date {raw!r}; use YYYY-MM-DD or DD/MM/YYYY")


def _money(raw: str, field: str, required: bool = True) -> Optional[Decimal]:
    s = _MONEY_JUNK.sub("", raw or "")
    if not s:
        if required:
            raise _RowFault(field, "missing")
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise _RowFault(field, f"not a number: {raw!r}") from None
    if not value.is_finite():
        raise _RowFault(field, f"not a number: {raw!r}")
    return value


def _row(cells: dict[str, str], line: int) -> Transaction:
    get = lambda k: (cells.get(k) or "").strip()   # noqa: E731

    direction = DIRECTIONS.get(get("direction").lower())
    if direction is None:
        raise _RowFault("direction", f"expected receipt or expense, got {get('direction')!r}")

    amount = _money(get("amount"), "amount")
    if amount <= 0:
        raise _RowFault("amount", "must be positive; use the direction column for the sign")

    currency = (get("currency") or "INR").upper()
    if not _CURRENCY.match(currency):
        raise _RowFault("currency", f"expected a three-letter code, got {currency!r}")

    amount_inr = _money(get("amount_inr"), "amount_inr", required=False)
    fx_rate = _money(get("fx_rate"), "fx_rate", required=False)
    if currency == "INR":
        if amount_inr is not None and amount_inr != amount:
            raise _RowFault("amount_inr", "differs from amount on an INR row")
        amount_inr = amount
    elif amount_inr is None:
        if fx_rate is None or fx_rate <= 0:
            raise _RowFault("amount_inr", f"a {currency} row needs amount_inr or a positive fx_rate")
        amount_inr = (amount * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount_inr <= 0:
        raise _RowFault("amount_inr", "must be positive")

    withheld = _money(get("foreign_tax_withheld_inr"), "foreign_tax_withheld_inr", required=False) or Decimal(0)
    if withheld < 0:
        raise _RowFault("foreign_tax_withheld_inr", "cannot be negative")

    country = get("counterparty_country").upper()
    if country and not _COUNTRY.match(country):
        raise _RowFault("counterparty_country", f"expected a two-letter ISO code, got {country!r}")

    mode = source = None
    reason = ""
    if direction is Direction.receipt:
        mode, source, reason = tag_receipt_mode(get("receipt_mode"), get("description"))
        if get("receipt_mode") and source.value != "column" and get("receipt_mode").lower() != "unknown":
            reason = f"unrecognised receipt_mode {get('receipt_mode')!r}; {reason}"
    else:
        if withheld:
            raise _RowFault("foreign_tax_withheld_inr", "applies to receipts only")

    try:
        return Transaction(
            id=get("id") or f"L{line}", line=line, date=_date(get("date")), direction=direction, amount=amount,
            currency=currency, amount_inr=amount_inr, foreign_tax_withheld_inr=withheld,
            counterparty=get("counterparty"), counterparty_country=country, description=get("description"),
            receipt_mode=mode, mode_source=source, mode_reason=reason,
            fira_ref=get("fira_ref"), purpose_code=get("purpose_code").upper(),
        )
    except ValidationError as e:
        raise _RowFault("row", "; ".join(err["msg"] for err in e.errors())) from None


def parse_csv_text(text: str) -> ParseResult:
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration:
        return ParseResult(errors=[RowError(line=1, field="header", message="the file is empty")])

    header = [_norm_header(h) for h in raw_header]
    errors: list[RowError] = []
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        return ParseResult(errors=[RowError(line=1, field="header", message=f"missing column(s): {', '.join(missing)}")])
    dupes = sorted({h for h in header if header.count(h) > 1 and h})
    if dupes:
        return ParseResult(errors=[RowError(line=1, field="header", message=f"repeated column(s): {', '.join(dupes)}")])
    unknown = [h for h in header if h and h not in KNOWN]
    if unknown:
        errors.append(RowError(line=1, field="header", message=f"ignored unknown column(s): {', '.join(unknown)}"))

    transactions: list[Transaction] = []
    seen: dict[str, int] = {}
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(cells) != len(header):
            errors.append(RowError(line=line, field="row", message=f"{len(cells)} cells, header has {len(header)}"))
            continue
        try:
            t = _row(dict(zip(header, cells)), line)
        except _RowFault as f:
            errors.append(RowError(line=line, field=f.field, message=f.message))
            continue
        if t.id in seen:
            errors.append(RowError(line=line, field="id", message=f"id {t.id!r} already used on line {seen[t.id]}"))
            continue
        seen[t.id] = line
        transactions.append(t)
    return ParseResult(transactions=transactions, errors=errors)


def parse_csv_file(path: str | Path) -> ParseResult:
    return parse_csv_text(Path(path).read_text(encoding="utf-8-sig"))


CSV_COLUMNS = ("id", "date", "direction", "amount", "currency", "amount_inr", "foreign_tax_withheld_inr",
               "counterparty", "counterparty_country", "description", "receipt_mode", "fira_ref", "purpose_code")


def to_csv_text(transactions: list[Transaction], blank_modes: frozenset[str] = frozenset()) -> str:
    """Write transactions in the parser's own format. Ids in blank_modes get an empty receipt_mode cell."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for t in transactions:
        mode = "" if (t.receipt_mode is None or t.id in blank_modes) else t.receipt_mode.value
        w.writerow([t.id, t.date.isoformat(), t.direction.value, t.amount, t.currency, t.amount_inr,
                    t.foreign_tax_withheld_inr if t.foreign_tax_withheld_inr else "", t.counterparty,
                    t.counterparty_country, t.description, mode, t.fira_ref, t.purpose_code])
    return buf.getvalue()
