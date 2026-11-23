"""CSV parsing: accepted formats, and every bad row reported with its line rather than guessed."""
from datetime import date
from decimal import Decimal

from ingest.csv_parser import parse_csv_file, parse_csv_text, to_csv_text
from ingest.models import Direction, ModeSource, ReceiptMode

HEADER = "id,date,direction,amount,currency,amount_inr,counterparty,counterparty_country,description,receipt_mode,fira_ref,purpose_code\n"


def test_happy_path_mixed_rows():
    text = HEADER + (
        "R1,2026-04-15,receipt,1200.50,USD,100842.00,Acme Inc,us,SWIFT INWARD ACME,electronic,FIRA/1,p0802\n"
        "E1,15/05/2026,expense,\"1,499\",INR,,GitHub,,GITHUB INC,,,\n"
        "R2,20-06-2026,credit,Rs 50000,,,Local client,IN,CASH DEPOSIT,cash,,\n"
    )
    res = parse_csv_text(text)
    assert res.ok, res.errors
    r1, e1, r2 = res.transactions
    assert (r1.date, r1.amount, r1.amount_inr, r1.counterparty_country, r1.purpose_code) == \
        (date(2026, 4, 15), Decimal("1200.50"), Decimal("100842.00"), "US", "P0802")
    assert r1.receipt_mode is ReceiptMode.electronic and r1.mode_source is ModeSource.column
    assert e1.direction is Direction.expense and e1.amount_inr == Decimal(1499) and e1.receipt_mode is None
    assert e1.date == date(2026, 5, 15)
    assert r2.direction is Direction.receipt and r2.amount_inr == Decimal(50000) and r2.receipt_mode is ReceiptMode.cash


def test_header_aliases_and_bom_and_missing_ids():
    text = "﻿Txn Date,Type,Amount,Narration,Mode\n2026-07-01,CR,1000,NEFT FROM CLIENT,\n2026-07-02,DR,200,AIRTEL BILL,\n"
    res = parse_csv_text(text)
    assert res.ok, res.errors
    a, b = res.transactions
    assert a.id == "L2" and b.id == "L3"
    assert a.receipt_mode is ReceiptMode.electronic and a.mode_source is ModeSource.inferred


def test_fx_rate_used_when_amount_inr_missing():
    res = parse_csv_text("date,direction,amount,currency,fx_rate\n2026-04-01,receipt,1000,USD,85.25\n")
    assert res.ok, res.errors
    assert res.transactions[0].amount_inr == Decimal("85250.00")


def test_withholding_adds_to_gross_receipt():
    res = parse_csv_text("date,direction,amount,foreign_tax_withheld_inr,receipt_mode\n2026-04-01,receipt,70000,30000,electronic\n")
    assert res.ok, res.errors
    assert res.transactions[0].gross_inr == Decimal(100000)


def test_missing_required_column_stops_the_file():
    res = parse_csv_text("date,amount\n2026-04-01,100\n")
    assert not res.transactions
    assert res.errors[0].line == 1 and "direction" in res.errors[0].message


def test_bad_rows_are_reported_with_line_and_skipped():
    text = HEADER + (
        "A,2026-13-01,receipt,100,INR,,,,,,,\n"          # line 2: bad date
        "B,2026-04-01,receipt,-100,INR,,,,,,,\n"         # line 3: negative
        "C,2026-04-01,refund,100,INR,,,,,,,\n"           # line 4: unknown direction
        "D,2026-04-01,receipt,100,USD,,,,,,,\n"          # line 5: foreign, no rupees
        "E,2026-04-01,receipt,abc,INR,,,,,,,\n"          # line 6: not a number
        "F,2026-04-01,receipt,100,INR,120,,,,,,\n"       # line 7: INR amounts disagree
        "G,2026-04-01,receipt,100,INR,,,USA,,,,\n"       # line 8: three-letter country
        "H,2026-04-01,receipt,100\n"                     # line 9: short row
        "I,04/15/2026,receipt,100,INR,,,,,,,\n"          # line 10: month-first is refused
        "OK,2026-04-01,receipt,100,INR,,,,,cash,,\n"     # line 11: fine
        "OK,2026-04-02,receipt,100,INR,,,,,cash,,\n"     # line 12: duplicate id
    )
    res = parse_csv_text(text)
    assert [t.id for t in res.transactions] == ["OK"]
    assert [(e.line, e.field) for e in res.errors] == [
        (2, "date"), (3, "amount"), (4, "direction"), (5, "amount_inr"), (6, "amount"), (7, "amount_inr"),
        (8, "counterparty_country"), (9, "row"), (10, "date"), (12, "id")]


def test_withholding_on_an_expense_is_rejected():
    res = parse_csv_text("date,direction,amount,foreign_tax_withheld_inr\n2026-04-01,expense,100,10\n")
    assert res.errors and res.errors[0].field == "foreign_tax_withheld_inr"


def test_unknown_columns_are_reported_but_not_fatal():
    res = parse_csv_text("date,direction,amount,balance\n2026-04-01,expense,100,5000\n")
    assert len(res.transactions) == 1
    assert res.errors[0].line == 1 and "balance" in res.errors[0].message


def test_empty_file():
    assert parse_csv_text("").errors[0].field == "header"


def test_round_trip(tmp_path):
    res = parse_csv_text(HEADER + "R1,2026-04-15,receipt,1200.50,USD,100842.00,Acme Inc,US,SWIFT INWARD,electronic,FIRA/1,P0802\n")
    path = tmp_path / "t.csv"
    path.write_text(to_csv_text(res.transactions), encoding="utf8")
    again = parse_csv_file(path)
    assert again.ok and again.transactions[0].model_dump(exclude={"line"}) == res.transactions[0].model_dump(exclude={"line"})
