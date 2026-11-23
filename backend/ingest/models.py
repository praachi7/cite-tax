"""Shapes for ingested transactions and their expense classifications. Money is Decimal rupees."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Direction(str, Enum):
    receipt = "receipt"
    expense = "expense"


class ReceiptMode(str, Enum):
    """How a receipt reached the taxpayer, as the presumptive ITR schedules split it.

    electronic: account-payee cheque or draft, or a bank electronic mode (NEFT, RTGS, IMPS, UPI, SWIFT and so on).
    cash: cash.
    other: any other mode, chiefly a cheque or draft not crossed account-payee. It counts as cash for the limit test.
    unknown: the file does not say and the description does not settle it. Treated as cash unless the user confirms.
    """

    electronic = "electronic"
    cash = "cash"
    other = "other"
    unknown = "unknown"


class ModeSource(str, Enum):
    column = "column"        # the receipt_mode column named a mode
    inferred = "inferred"    # read from the description (NEFT, SWIFT, CASH DEP ...)
    none = "none"            # neither settled it


class Transaction(_Strict):
    id: str
    line: int = 0                                   # line in the source CSV (header is line 1), 0 if not from a file
    date: date
    direction: Direction
    amount: Decimal                                 # in `currency`, always positive
    currency: str = "INR"
    amount_inr: Decimal                             # what reached the account, in rupees
    foreign_tax_withheld_inr: Decimal = Decimal(0)  # tax a foreign payer withheld before paying; part of gross receipts
    counterparty: str = ""
    counterparty_country: str = ""                  # ISO code, blank when unknown
    description: str = ""
    receipt_mode: Optional[ReceiptMode] = None      # receipts only
    mode_source: Optional[ModeSource] = None
    mode_reason: str = ""
    fira_ref: str = ""
    purpose_code: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Transaction":
        if self.amount <= 0 or self.amount_inr <= 0:
            raise ValueError("amounts must be positive; the direction carries the sign")
        if self.foreign_tax_withheld_inr < 0:
            raise ValueError("foreign_tax_withheld_inr cannot be negative")
        if self.direction is Direction.receipt and self.receipt_mode is None:
            raise ValueError("a receipt needs a receipt_mode (use unknown when it is not known)")
        if self.direction is Direction.expense and (self.receipt_mode is not None or self.foreign_tax_withheld_inr):
            raise ValueError("receipt_mode and foreign_tax_withheld_inr apply to receipts only")
        return self

    @property
    def gross_inr(self) -> Decimal:
        """Gross receipt for the year's receipts total: the credit plus any tax withheld at source abroad."""
        return self.amount_inr + self.foreign_tax_withheld_inr


class RowError(_Strict):
    line: int
    field: str
    message: str


class ParseResult(_Strict):
    transactions: list[Transaction] = Field(default_factory=list)
    errors: list[RowError] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# ---- expense classification ----

class ExpenseCategory(str, Enum):
    """The fixed label set. The classifier may answer only with one of these."""

    software_subscriptions = "software_subscriptions"
    hardware_equipment = "hardware_equipment"
    internet_phone = "internet_phone"
    office_rent_coworking = "office_rent_coworking"
    business_travel = "business_travel"
    professional_services = "professional_services"
    bank_platform_fees = "bank_platform_fees"
    training_books = "training_books"
    personal = "personal"
    tax_payment = "tax_payment"
    own_transfer = "own_transfer"
    uncertain = "uncertain"


BUSINESS_CATEGORIES = frozenset({
    ExpenseCategory.software_subscriptions, ExpenseCategory.hardware_equipment, ExpenseCategory.internet_phone,
    ExpenseCategory.office_rent_coworking, ExpenseCategory.business_travel, ExpenseCategory.professional_services,
    ExpenseCategory.bank_platform_fees, ExpenseCategory.training_books,
})


class Classification(_Strict):
    transaction_id: str
    category: ExpenseCategory
    confidence: Decimal                 # rule tier for now (see expense_rules.yaml); 0 for uncertain
    method: str                         # rule | none
    rule_id: Optional[str] = None
    reason: str = ""
    candidates: list[ExpenseCategory] = Field(default_factory=list)   # categories that matched, when they conflicted


class ProfitComparison(_Strict):
    """Actual profit beside the presumptive figure. Informational: it never feeds the tax computation."""

    gross_receipts: Decimal
    presumptive_income: Decimal
    business_expenses: Decimal          # classified into a business category
    uncertain_expenses: Decimal         # labelled uncertain; could go either way
    actual_profit_high: Decimal         # if every uncertain expense is personal
    actual_profit_low: Decimal          # if every uncertain expense is business
    below_presumptive: str              # yes | no | depends_on_uncertain
    note: str
