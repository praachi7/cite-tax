"""Rule-based expense classifier with an "uncertain" label. No language model yet.

Only expense rows are classified. The output feeds the actual-profit comparison and the evidence
trail; it is never an input to the tax engine (s.44ADA(2); s.58(4) of the 2025 Act).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

from .models import BUSINESS_CATEGORIES, Classification, Direction, ExpenseCategory, ProfitComparison, Transaction

RULES_FILE = Path(__file__).with_name("expense_rules.yaml")


@dataclass(frozen=True)
class Rule:
    id: str
    tier: str
    category: ExpenseCategory
    pattern: re.Pattern
    confidence: Decimal


@dataclass(frozen=True)
class RuleSet:
    version: str
    tier_order: tuple[str, ...]        # strongest first
    rules: tuple[Rule, ...]


def load_rules(path: Path = RULES_FILE) -> RuleSet:
    data = yaml.safe_load(path.read_text(encoding="utf8"))
    tiers = {name: Decimal(str(v)) for name, v in data["tiers"].items()}
    order = tuple(sorted(tiers, key=lambda n: tiers[n], reverse=True))
    rules, ids = [], set()
    for r in data["rules"]:
        if r["id"] in ids:
            raise ValueError(f"duplicate rule id {r['id']}")
        ids.add(r["id"])
        if r["tier"] not in tiers:
            raise ValueError(f"{r['id']}: unknown tier {r['tier']}")
        category = ExpenseCategory(r["category"])        # raises on a label outside the fixed set
        if category is ExpenseCategory.uncertain:
            raise ValueError(f"{r['id']}: a rule cannot assign 'uncertain'")
        pattern = re.compile(rf"(?<![a-z0-9])(?:{r['pattern']})(?![a-z0-9])", re.I)
        rules.append(Rule(r["id"], r["tier"], category, pattern, tiers[r["tier"]]))
    return RuleSet(str(data["version"]), order, tuple(rules))


@lru_cache(maxsize=1)
def default_rules() -> RuleSet:
    return load_rules()


def classify(t: Transaction, rules: RuleSet | None = None) -> Classification:
    if t.direction is not Direction.expense:
        raise ValueError(f"{t.id} is a receipt; only expenses are classified")
    rules = rules or default_rules()
    text = f"{t.description} {t.counterparty}"
    hits = [r for r in rules.rules if r.pattern.search(text)]
    if not hits:
        return Classification(transaction_id=t.id, category=ExpenseCategory.uncertain, confidence=Decimal(0),
                              method="none", reason="no rule matched")
    for tier in rules.tier_order:
        at_tier = [r for r in hits if r.tier == tier]
        if not at_tier:
            continue
        categories = sorted({r.category for r in at_tier}, key=lambda c: c.value)
        if len(categories) > 1:
            return Classification(
                transaction_id=t.id, category=ExpenseCategory.uncertain, confidence=Decimal(0), method="rule",
                rule_id=",".join(r.id for r in at_tier), candidates=categories,
                reason=f"{tier} rules disagree: {', '.join(c.value for c in categories)}")
        r = at_tier[0]
        return Classification(transaction_id=t.id, category=r.category, confidence=r.confidence, method="rule",
                              rule_id=",".join(x.id for x in at_tier), reason=f"{tier} rule")
    raise AssertionError("unreachable: every hit has a known tier")


def classify_all(transactions: Iterable[Transaction], rules: RuleSet | None = None) -> list[Classification]:
    return [classify(t, rules) for t in transactions if t.direction is Direction.expense]


def compare_profit(transactions: Iterable[Transaction], classifications: Iterable[Classification],
                   gross_receipts: Decimal, presumptive_income: Decimal) -> ProfitComparison:
    """Actual profit (receipts less business expenses) beside the presumptive figure.

    gross_receipts and presumptive_income come from the engine result (receipts_test.total and
    income.presumptive_amount). This function only reports; nothing it returns goes back to the engine,
    and a profit below the presumptive figure is never declared on the user's behalf.
    """
    amounts = {t.id: t.amount_inr for t in transactions if t.direction is Direction.expense}
    business = uncertain = Decimal(0)
    for c in classifications:
        if c.transaction_id not in amounts:
            raise ValueError(f"classification for unknown expense {c.transaction_id}")
        if c.category in BUSINESS_CATEGORIES:
            business += amounts[c.transaction_id]
        elif c.category is ExpenseCategory.uncertain:
            uncertain += amounts[c.transaction_id]
    high = gross_receipts - business
    low = high - uncertain
    if high < presumptive_income:
        below = "yes"
    elif low >= presumptive_income:
        below = "no"
    else:
        below = "depends_on_uncertain"
    note = {
        "no": "Actual profit is at or above the presumptive figure; the presumptive income stands.",
        "yes": ("Actual profit is below the presumptive figure. The presumptive income still stands unless the "
                "user chooses to declare lower, which needs books of account and a tax audit "
                "(s.44ADA(4) of the 1961 Act; s.58(3) of the 2025 Act)."),
        "depends_on_uncertain": ("Whether actual profit is below the presumptive figure depends on expenses "
                                 "labelled uncertain; review them. The presumptive income is unchanged."),
    }[below]
    return ProfitComparison(gross_receipts=gross_receipts, presumptive_income=presumptive_income,
                            business_expenses=business, uncertain_expenses=uncertain,
                            actual_profit_high=high, actual_profit_low=low, below_presumptive=below, note=note)
