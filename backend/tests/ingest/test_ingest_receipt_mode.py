"""Receipt-mode tagging and the receipts total handed to the engine."""
from datetime import date
from decimal import Decimal

import pytest

from ingest.csv_parser import parse_csv_text
from ingest.models import ModeSource, ReceiptMode
from ingest.receipt_mode import receipts_for_engine, tag_receipt_mode


@pytest.mark.parametrize("column, description, mode, source", [
    ("electronic", "CASH DEPOSIT", ReceiptMode.electronic, ModeSource.column),   # the column wins
    ("Account Payee", "", ReceiptMode.electronic, ModeSource.column),
    ("NEFT", "", ReceiptMode.electronic, ModeSource.column),
    ("cash", "", ReceiptMode.cash, ModeSource.column),
    ("bearer_cheque", "", ReceiptMode.other, ModeSource.column),
    ("", "NEFT CR ACME", ReceiptMode.electronic, ModeSource.inferred),
    ("", "SWIFT INWARD REMITTANCE", ReceiptMode.electronic, ModeSource.inferred),
    ("", "PAYONEER INWARD", ReceiptMode.electronic, ModeSource.inferred),
    ("", "UPI/CR/1234", ReceiptMode.electronic, ModeSource.inferred),
    ("", "CASH DEP BRANCH", ReceiptMode.cash, ModeSource.inferred),
    ("", "CHQ DEP A/C PAYEE 004512", ReceiptMode.electronic, ModeSource.inferred),
    ("", "BEARER CHEQUE 004512", ReceiptMode.other, ModeSource.inferred),
    ("", "CHQ DEP 004512", ReceiptMode.unknown, ModeSource.none),    # crossing not shown
    ("", "PAYMENT FROM CLIENT", ReceiptMode.unknown, ModeSource.none),
    ("carrier pigeon", "NEFT", ReceiptMode.electronic, ModeSource.inferred),   # unrecognised cell, description decides
    ("unknown", "", ReceiptMode.unknown, ModeSource.none),
])
def test_tagging(column, description, mode, source):
    got_mode, got_source, _ = tag_receipt_mode(column, description)
    assert (got_mode, got_source) == (mode, source)


def _parse(rows):
    res = parse_csv_text("id,date,direction,amount,receipt_mode,description,foreign_tax_withheld_inr\n" + rows)
    assert res.ok, res.errors
    return res.transactions


def test_totals_by_mode_with_withholding_and_expenses_ignored():
    txs = _parse(
        "a,2026-04-10,receipt,700,electronic,,300\n"
        "b,2026-05-10,receipt,200,cash,,\n"
        "c,2026-06-10,receipt,50,other,,\n"
        "d,2026-06-11,expense,99999,,,\n")
    receipts, warnings = receipts_for_engine(txs, 2026)
    assert (receipts.electronic, receipts.cash, receipts.non_account_payee_cheque) == (Decimal(1000), Decimal(200), Decimal(50))
    assert warnings == []


def test_unknown_mode_is_counted_as_cash_and_warned():
    txs = _parse("a,2026-04-10,receipt,1000,,CHQ DEP 1234,\n")
    receipts, warnings = receipts_for_engine(txs, 2026)
    assert receipts.cash == Decimal(1000) and receipts.electronic == 0
    assert "unknown" in warnings[0]
    receipts, _ = receipts_for_engine(txs, 2026, unknown_as=ReceiptMode.other)
    assert receipts.non_account_payee_cheque == Decimal(1000)
    with pytest.raises(ValueError):
        receipts_for_engine(txs, 2026, unknown_as=ReceiptMode.electronic)   # never the generous reading


def test_rows_outside_the_tax_year_are_left_out():
    txs = _parse("a,2026-03-31,receipt,1,electronic,,\nb,2026-04-01,receipt,2,electronic,,\n"
                 "c,2027-03-31,receipt,4,electronic,,\nd,2027-04-01,receipt,8,electronic,,\n")
    receipts, warnings = receipts_for_engine(txs, 2026)
    assert receipts.electronic == Decimal(6)
    assert len(warnings) == 2 and all("outside tax year" in w for w in warnings)
    assert {t.date for t in txs} >= {date(2026, 4, 1), date(2027, 3, 31)}
