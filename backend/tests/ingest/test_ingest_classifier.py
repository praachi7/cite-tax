"""Rule-based expense classifier: fixed label set, tier precedence, and "uncertain" on doubt."""
from datetime import date
from decimal import Decimal

import pytest

from ingest.classifier import RULES_FILE, classify, classify_all, compare_profit, default_rules, load_rules
from ingest.models import Direction, ExpenseCategory, ReceiptMode, Transaction

C = ExpenseCategory


def _exp(desc, cp="", amount=1000, tid="e"):
    return Transaction(id=tid, date=date(2026, 5, 1), direction=Direction.expense, amount=Decimal(amount),
                       amount_inr=Decimal(amount), description=desc, counterparty=cp)


@pytest.mark.parametrize("desc, cp, category", [
    ("GITHUB INC", "", C.software_subscriptions),
    ("CLOUD BILL", "Amazon Web Services", C.software_subscriptions),
    ("AIRTEL BROADBAND", "", C.internet_phone),
    ("WEWORK MEMBERSHIP", "", C.office_rent_coworking),
    ("INDIGO FLIGHT", "", C.business_travel),
    ("UDEMY", "", C.training_books),
    ("SWIFT CHARGES", "", C.bank_platform_fees),
    ("ADVANCE TAX CHALLAN 280", "", C.tax_payment),
    ("SELF TRANSFER", "", C.own_transfer),
    ("NETFLIX", "", C.personal),
])
def test_known_merchants(desc, cp, category):
    c = classify(_exp(desc, cp))
    assert c.category is category and c.method == "rule" and c.confidence > 0


def test_merchant_tier_beats_keyword_tier():
    # "JIO" is a merchant (internet); "conference" is a travel keyword. The merchant wins.
    c = classify(_exp("JIO POSTPAID CONFERENCE ADDON"))
    assert c.category is C.internet_phone and c.confidence == Decimal("0.95")


def test_keyword_only_gets_the_lower_confidence():
    c = classify(_exp("NEW LAPTOP"))
    assert c.category is C.hardware_equipment and c.confidence == Decimal("0.75")


def test_conflicting_merchants_give_uncertain():
    c = classify(_exp("NETFLIX VIA GITHUB SPONSORS"))
    assert c.category is C.uncertain and c.confidence == 0
    assert set(c.candidates) == {C.personal, C.software_subscriptions}


@pytest.mark.parametrize("desc", ["AMAZON PAY INDIA", "UBER TRIP", "SWIGGY ORDER", "PAYMENT 88213", ""])
def test_mixed_use_or_unknown_gives_uncertain(desc):
    c = classify(_exp(desc))
    assert c.category is C.uncertain and c.confidence == 0


def test_word_boundaries():
    assert classify(_exp("ZOMATO")).category is C.personal      # not "zoom"
    assert classify(_exp("NOTIONAL CHARGE")).category is C.uncertain   # not "notion"


def test_receipts_are_not_classified():
    r = Transaction(id="r", date=date(2026, 5, 1), direction=Direction.receipt, amount=Decimal(1),
                    amount_inr=Decimal(1), receipt_mode=ReceiptMode.electronic)
    with pytest.raises(ValueError):
        classify(r)
    assert classify_all([r, _exp("GITHUB")]) and len(classify_all([r, _exp("GITHUB")])) == 1


def test_rules_file_uses_only_the_fixed_label_set():
    rs = load_rules(RULES_FILE)
    assert rs.rules and {r.category for r in rs.rules} <= set(C) - {C.uncertain}
    assert len({r.id for r in rs.rules}) == len(rs.rules)


@pytest.mark.parametrize("bad, msg", [
    ("version: 1\ntiers: {merchant: 0.9}\nrules:\n  - {id: a, tier: merchant, category: snacks, pattern: x}\n", "snacks"),
    ("version: 1\ntiers: {merchant: 0.9}\nrules:\n  - {id: a, tier: merchant, category: uncertain, pattern: x}\n", "uncertain"),
    ("version: 1\ntiers: {merchant: 0.9}\nrules:\n  - {id: a, tier: gut, category: personal, pattern: x}\n", "tier"),
    ("version: 1\ntiers: {merchant: 0.9}\nrules:\n  - {id: a, tier: merchant, category: personal, pattern: x}\n"
     "  - {id: a, tier: merchant, category: personal, pattern: y}\n", "duplicate"),
])
def test_bad_rule_files_are_refused(tmp_path, bad, msg):
    p = tmp_path / "rules.yaml"
    p.write_text(bad, encoding="utf8")
    with pytest.raises(ValueError, match=msg):
        load_rules(p)


def test_profit_comparison_reports_a_range_and_never_declares():
    txs = [_exp("GITHUB", amount=600_000, tid="a"), _exp("AMAZON PAY", amount=300_000, tid="b"),
           _exp("NETFLIX", amount=50_000, tid="c")]
    cls = classify_all(txs)
    pc = compare_profit(txs, cls, gross_receipts=Decimal(2_000_000), presumptive_income=Decimal(1_000_000))
    assert (pc.business_expenses, pc.uncertain_expenses) == (Decimal(600_000), Decimal(300_000))
    assert (pc.actual_profit_high, pc.actual_profit_low) == (Decimal(1_400_000), Decimal(1_100_000))
    assert pc.below_presumptive == "no"
    pc = compare_profit(txs, cls, gross_receipts=Decimal(1_700_000), presumptive_income=Decimal(850_000))
    assert pc.below_presumptive == "depends_on_uncertain" and "unchanged" in pc.note
    pc = compare_profit(txs, cls, gross_receipts=Decimal(1_000_000), presumptive_income=Decimal(500_000))
    assert pc.below_presumptive == "yes" and "books of account" in pc.note
    with pytest.raises(ValueError):
        compare_profit(txs[:1], cls, Decimal(1), Decimal(1))


def test_default_rules_are_cached():
    assert default_rules() is default_rules()
