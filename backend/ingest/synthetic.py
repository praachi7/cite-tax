"""Synthetic transactions for personas P1 to P10 (the PaySim dataset was rejected as unsuitable).

Every persona's receipts add up, by mode, exactly to the receipts in its engine fixture
(backend/tests/engine/personas/pN.yaml), so the generated CSV reproduces the engine's golden figures.
Where a persona declares a profit (P4, P10), business expenses by gold label equal receipts less that
profit. Other personas get a modest expense profile; those amounts are synthetic choices that the
engine never reads.

Each expense carries a gold label and a kind:
  known      the description names a merchant or word the rules cover
  ambiguous  a mixed-use merchant (Amazon, Uber, Swiggy); the right answer for the rules is "uncertain"
  unseen     a business merchant the rules do not know; tests abstention rather than guessing
  trap       a business-looking merchant used for personal spend (a family flight); rules get it wrong
The labelled set this produces is what classifier accuracy and abstention are measured on. Because the
same authors wrote the rules and the templates, accuracy on "known" rows is optimistic by construction;
the "ambiguous", "unseen" and "trap" rows are the informative part.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .models import Direction, ExpenseCategory, ModeSource, ReceiptMode, Transaction
from .receipt_mode import tax_year_bounds

C = ExpenseCategory


@dataclass(frozen=True)
class ClientStream:
    name: str
    country: str
    gross_inr: int                   # receipts for the year, before any foreign withholding
    mode: ReceiptMode = ReceiptMode.electronic
    currency: str = "USD"
    withheld_inr: int = 0            # US tax withheld at source on this stream
    channel: str = "SWIFT INWARD REMITTANCE"
    note: str = ""                   # e.g. "on-site work in the US"


@dataclass(frozen=True)
class PersonaSpec:
    id: str
    tax_year: int
    clients: tuple[ClientStream, ...]
    business_expenses_inr: int
    note: str = ""

    def receipts_by_mode(self) -> dict[str, int]:
        out = {"electronic": 0, "cash": 0, "non_account_payee_cheque": 0}
        key = {ReceiptMode.electronic: "electronic", ReceiptMode.cash: "cash", ReceiptMode.other: "non_account_payee_cheque"}
        for c in self.clients:
            out[key[c.mode]] += c.gross_inr
        return out


_BOREALIS = "Borealis Systems Inc"
PERSONAS: dict[str, PersonaSpec] = {s.id: s for s in (
    PersonaSpec("P1", 2026, (ClientStream("Acme Analytics Inc", "US", 2_400_000),), 240_000),
    PersonaSpec("P2", 2025, (ClientStream("Acme Analytics Inc", "US", 2_400_000),), 240_000),
    PersonaSpec("P3", 2026, (
        ClientStream("Northwind Data LLC", "US", 4_000_000),
        ClientStream("Contoso Health Inc", "US", 2_860_000),
        ClientStream("Shreeji Traders", "IN", 140_000, ReceiptMode.cash, "INR", channel="CASH DEPOSIT"),
    ), 600_000),
    PersonaSpec("P4", 2026, (
        ClientStream("Fabrikam Labs Inc", "US", 3_520_000),
        ClientStream("Tailspin Media LLC", "US", 2_000_000),
        ClientStream("Local retail clients", "IN", 480_000, ReceiptMode.cash, "INR", channel="CASH DEPOSIT"),
    ), 2_700_000, note="declared profit 33,00,000 = 60,00,000 less 27,00,000 business expenses"),
    PersonaSpec("P5", 2026, (
        ClientStream(_BOREALIS, "US", 800_000, withheld_inr=240_000, note="on-site work in the US"),
        ClientStream(_BOREALIS, "US", 3_200_000, note="work done in India"),
    ), 300_000),
    PersonaSpec("P6", 2026, (
        ClientStream("Initech Corp", "US", 4_000_000, withheld_inr=1_200_000, note="no W-8BEN; 30% withheld"),
    ), 300_000),
    PersonaSpec("P7", 2026, (
        ClientStream("Upwork clients via Payoneer", "US", 3_000_000, channel="PAYONEER INWARD"),
    ), 250_000),
    PersonaSpec("P8", 2026, (ClientStream("Globex Software Inc", "US", 4_000_000),), 300_000),
    PersonaSpec("P9", 2026, (
        ClientStream(_BOREALIS, "US", 800_000, withheld_inr=240_000, note="on-site work in the US"),
        ClientStream(_BOREALIS, "US", 3_200_000, note="work done in India"),
    ), 300_000),
    PersonaSpec("P10", 2026, (ClientStream("Umbrella Interactive Inc", "US", 3_000_000),), 1_800_000,
                note="declared profit 12,00,000 = 30,00,000 less 18,00,000 business expenses"),
)}


# (description, counterparty, gold label, kind)
BUSINESS_TEMPLATES: list[tuple[str, str, ExpenseCategory, str]] = [
    ("GITHUB INC SUBSCRIPTION", "GitHub", C.software_subscriptions, "known"),
    ("AWS EMEA CLOUD SERVICES", "Amazon Web Services", C.software_subscriptions, "known"),
    ("JETBRAINS ALL PRODUCTS PACK", "JetBrains", C.software_subscriptions, "known"),
    ("FIGMA PROFESSIONAL PLAN", "Figma", C.software_subscriptions, "known"),
    ("GOOGLE CLOUD INDIA", "Google Cloud", C.software_subscriptions, "known"),
    ("ZOOM VIDEO COMMUNICATIONS", "Zoom", C.software_subscriptions, "known"),
    ("CROMA ELECTRONICS POS", "Croma", C.hardware_equipment, "known"),
    ("DELL INDIA ONLINE", "Dell", C.hardware_equipment, "known"),
    ("27 INCH MONITOR PURCHASE", "Electronics shop", C.hardware_equipment, "known"),
    ("AIRTEL XSTREAM FIBER BILL", "Airtel", C.internet_phone, "known"),
    ("JIO POSTPAID BILL", "Jio", C.internet_phone, "known"),
    ("WEWORK MEMBERSHIP", "WeWork", C.office_rent_coworking, "known"),
    ("AWFIS HOT DESK", "Awfis", C.office_rent_coworking, "known"),
    ("INDIGO FLIGHT CLIENT VISIT", "IndiGo", C.business_travel, "known"),
    ("MAKEMYTRIP HOTEL CONFERENCE", "MakeMyTrip", C.business_travel, "known"),
    ("CA FEES ITR FILING", "Sharma & Co Chartered Accountants", C.professional_services, "known"),
    ("PAYONEER FEE ANNUAL", "Payoneer", C.bank_platform_fees, "known"),
    ("SWIFT CHARGES INWARD", "Bank", C.bank_platform_fees, "known"),
    ("UDEMY COURSE PURCHASE", "Udemy", C.training_books, "known"),
    ("OREILLY LEARNING ANNUAL", "O'Reilly Media", C.training_books, "known"),
    # unseen: real business spend the rules do not know
    ("POSTMAN INC TEAM PLAN", "Postman", C.software_subscriptions, "unseen"),
    ("SENTRY IO BILLING", "Sentry", C.software_subscriptions, "unseen"),
    ("LINEAR ORBIT INC", "Linear", C.software_subscriptions, "unseen"),
    ("MEETUP CONF TICKET DEVFEST", "DevFest", C.training_books, "unseen"),
]

OTHER_TEMPLATES: list[tuple[str, str, ExpenseCategory, str]] = [
    ("NETFLIX SUBSCRIPTION", "Netflix", C.personal, "known"),
    ("ZOMATO ORDER", "Zomato", C.personal, "known"),
    ("BIGBASKET GROCERIES", "BigBasket", C.personal, "known"),
    ("HOUSE RENT MONTHLY", "Landlord", C.personal, "known"),
    ("APOLLO PHARMACY", "Apollo", C.personal, "known"),
    ("SELF TRANSFER TO SAVINGS", "Own account", C.own_transfer, "known"),
    ("ADVANCE TAX CHALLAN 280", "Income Tax Department", C.tax_payment, "known"),
    # ambiguous: mixed-use merchants; the gold answer is the real use, the right rule answer is uncertain
    ("AMAZON PAY INDIA ORDER", "Amazon", C.personal, "ambiguous"),
    ("UBER TRIP", "Uber", C.personal, "ambiguous"),
    ("SWIGGY ORDER", "Swiggy", C.personal, "ambiguous"),
    ("FLIPKART ORDER", "Flipkart", C.personal, "ambiguous"),
    # trap: a business-looking merchant used for personal spend; rules cannot see purpose and get these wrong
    ("INDIGO FLIGHT FAMILY HOLIDAY GOA", "IndiGo", C.personal, "trap"),
    ("APPLE STORE IPHONE GIFT", "Apple", C.personal, "trap"),
]


@dataclass
class GeneratedSet:
    persona: PersonaSpec
    transactions: list[Transaction]
    gold: dict[str, ExpenseCategory] = field(default_factory=dict)       # expense id -> gold label
    kind: dict[str, str] = field(default_factory=dict)                   # expense id -> known | ambiguous | unseen | trap
    blank_mode_ids: frozenset[str] = frozenset()                         # receipts written with an empty mode cell


def split_exact(total: int, parts: int, rng: random.Random) -> list[int]:
    """Split a whole-rupee total into `parts` positive whole-rupee amounts that add up exactly."""
    if parts < 1 or total < parts:
        raise ValueError("cannot split")
    weights = [rng.randint(70, 130) for _ in range(parts)]
    wsum = sum(weights)
    out = [max(1, total * w // wsum) for w in weights]
    out[-1] = total - sum(out[:-1])
    if out[-1] < 1:
        raise ValueError("cannot split")
    return out


def _day(rng: random.Random, year: int, month: int) -> date:
    return date(year, month, rng.randint(1, 28))


_MONTHS = [(4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0), (12, 0), (1, 1), (2, 1), (3, 1)]


def generate(persona_id: str, seed: int = 7) -> GeneratedSet:
    spec = PERSONAS[persona_id]
    rng = random.Random(f"{persona_id}:{seed}")
    ty = spec.tax_year
    txs: list[Transaction] = []
    blank: set[str] = set()
    n_r = 0

    for ci, c in enumerate(spec.clients):
        months = _MONTHS if c.mode is ReceiptMode.electronic else rng.sample(_MONTHS, 4)
        months = sorted(months, key=lambda m: (m[1], m[0]))
        gross = split_exact(c.gross_inr, len(months), rng)
        withheld = [g * c.withheld_inr // c.gross_inr for g in gross]
        withheld[-1] = c.withheld_inr - sum(withheld[:-1])
        for (month, add), g, w in zip(months, gross, withheld):
            n_r += 1
            tid = f"{spec.id}-R{n_r:03d}"
            credited = g - w
            if c.currency == "INR":
                amount = Decimal(credited)
            else:
                fx = Decimal(rng.randint(8300, 8800)) / 100
                amount = (Decimal(credited) / fx).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            desc = f"{c.channel} {c.name.upper()}"
            if c.note:
                desc += f" ({c.note})"
            foreign = c.country != "IN"
            mode = c.mode
            if mode is ReceiptMode.electronic and rng.random() < 0.25:
                blank.add(tid)          # written with an empty mode cell; the tagger must infer it
            txs.append(Transaction(
                id=tid, date=_day(rng, ty + add, month), direction=Direction.receipt, amount=amount,
                currency=c.currency, amount_inr=Decimal(credited), foreign_tax_withheld_inr=Decimal(w),
                counterparty=c.name, counterparty_country=c.country, description=desc,
                receipt_mode=mode, mode_source=ModeSource.column, mode_reason="receipt_mode column",
                fira_ref=f"FIRA/{spec.id}/{ci + 1}/{n_r:03d}" if foreign and mode is ReceiptMode.electronic else "",
                purpose_code="P0802" if foreign else ""))

    gold: dict[str, ExpenseCategory] = {}
    kind: dict[str, str] = {}
    n_e = 0

    def add_expense(desc: str, cp: str, label: ExpenseCategory, k: str, amount: int) -> None:
        nonlocal n_e
        n_e += 1
        tid = f"{spec.id}-E{n_e:03d}"
        month, add = rng.choice(_MONTHS)
        txs.append(Transaction(id=tid, date=_day(rng, ty + add, month), direction=Direction.expense,
                               amount=Decimal(amount), currency="INR", amount_inr=Decimal(amount),
                               counterparty=cp, description=desc))
        gold[tid], kind[tid] = label, k

    n_business = 24 if spec.business_expenses_inr < 1_000_000 else 40
    picks = [BUSINESS_TEMPLATES[i % len(BUSINESS_TEMPLATES)] for i in range(n_business)]
    rng.shuffle(picks)
    for (desc, cp, label, k), amount in zip(picks, split_exact(spec.business_expenses_inr, n_business, rng)):
        add_expense(desc, cp, label, k, amount)
    for desc, cp, label, k in OTHER_TEMPLATES:
        for _ in range(2):
            add_expense(desc, cp, label, k, rng.randint(300, 60_000))

    txs.sort(key=lambda t: (t.date, t.id))
    start, end = tax_year_bounds(ty)
    assert all(start <= t.date <= end for t in txs)
    return GeneratedSet(spec, txs, gold, kind, frozenset(blank))
