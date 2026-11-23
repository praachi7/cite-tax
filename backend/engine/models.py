"""Input and output shapes for the tax engine. Money is Decimal rupees."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import EngineConfig
from .trace import Flag, TraceStep


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityType(str, Enum):
    individual = "individual"
    non_llp_firm = "non_llp_firm"
    llp = "llp"
    huf = "huf"
    company = "company"


class ResidentialStatus(str, Enum):
    resident = "resident"        # resident and ordinarily resident
    rnor = "rnor"                # resident but not ordinarily resident (still a resident under s.6)
    non_resident = "non_resident"


class Profession(str, Enum):
    information_technology = "information_technology"
    other_specified = "other_specified"   # legal, medical, engineering and the other s.44AA(1) professions
    not_specified = "not_specified"


class Regime(str, Enum):
    new = "new"
    old = "old"


class Receipts(_Strict):
    """Gross receipts of the year in rupees, split by how they were received."""

    electronic: Decimal = Decimal(0)
    cash: Decimal = Decimal(0)
    non_account_payee_cheque: Decimal = Decimal(0)   # counts as cash for the limit test

    @model_validator(mode="after")
    def _non_negative(self) -> "Receipts":
        if min(self.electronic, self.cash, self.non_account_payee_cheque) < 0:
            raise ValueError("receipts cannot be negative")
        return self

    @property
    def total(self) -> Decimal:
        return self.electronic + self.cash + self.non_account_payee_cheque

    @property
    def cash_like(self) -> Decimal:
        return self.cash + self.non_account_payee_cheque


class Engagement(_Strict):
    """One body of work for one client. It says where the work was done, which step 7 needs."""

    label: str = ""
    country_of_performance: str = "IN"     # ISO code of where the services were performed
    amount_inr: Decimal                    # receipts for this work, in rupees
    amount_usd: Optional[Decimal] = None   # needed only for the s.861(a)(3) de minimis test
    client_is_us_person: bool = True
    w8ben_on_file: bool = True             # a valid Form W-8BEN given to this client
    w8ben_signed: Optional[date] = None    # when it was signed; needed for the expiry check
    us_tax_withheld_inr: Decimal = Decimal(0)   # converted at the rate in ftc.rate_conversion


class Remittance(_Strict):
    """One inward export receipt and its bank evidence (Transaction.fira_ref and purpose_code in SRS/SDS 3.4)."""

    label: str = ""
    amount_inr: Decimal
    fira_ref: Optional[str] = None         # FIRA or e-FIRA reference
    purpose_code: Optional[str] = None     # RBI purpose code, e.g. P0802


class ClassifiedExpense(_Strict):
    """One expense as labelled by the classifier (Phase E). It never changes presumptive income."""

    label: str                             # a label from the fixed set, or "uncertain"
    confidence: Decimal                    # agreement across repeated samples, 0 to 1
    amount_inr: Decimal = Decimal(0)
    description: str = ""


class FtcDocuments(_Strict):
    """What the taxpayer already has for the Form 44 / Form 67 statement. False means not yet in hand."""

    foreign_tin: bool = False
    foreign_tax_certificate: bool = False      # certificate or statement of the US tax deducted or paid
    dtaa_article_and_rate: bool = False        # the treaty article and rate the claim relies on
    accountant_verification: bool = False      # needed only where the foreign tax reaches the threshold
    foreign_tax_disputed: bool = False         # some of the US tax is in dispute
    statement_filed: bool = False              # Form 44 / Form 67 already furnished


class RegimeElection(_Strict):
    """The regime used in one earlier tax year. The history spans both Acts."""

    tax_year: int
    regime: Regime


class TaxpayerInput(_Strict):
    persona_id: str = ""
    tax_year: int                          # first calendar year: 2025 is FY 2025-26, 2026 is Tax Year 2026-27
    entity_type: EntityType = EntityType.individual
    residential_status: ResidentialStatus = ResidentialStatus.resident
    profession: Profession = Profession.information_technology
    receipts: Receipts
    # The profit the taxpayer declares. None means the presumptive 50% is declared.
    # At or above 50% it is the higher sum the statute allows; below 50% it is the lower profit that
    # triggers the books-and-audit rule. It is also required when the presumptive scheme is unavailable.
    declared_profit: Optional[Decimal] = None
    regime_choice: Regime = Regime.new
    election_history: list[RegimeElection] = Field(default_factory=list)   # earlier years only
    engagements: list[Engagement] = Field(default_factory=list)            # empty means all work done in India
    us_days_by_year: dict[int, int] = Field(default_factory=dict)          # calendar year -> days in the US
    us_calendar_year: Optional[int] = None   # US tax year to test; defaults to the first calendar year of the Indian year
    us_fixed_base: bool = False
    foreign_clients: bool = True             # fees come from clients outside India (the product's premise)
    foreign_assets_held: bool = False
    platform_wallet_balance_abroad: bool = False
    other_itr4_bars: list[str] = Field(default_factory=list)
    # ---- compliance inputs (Phase F). Unknown means "not checked", and a check that is not made raises no flag. ----
    as_of: Optional[date] = None             # the date deadlines are measured from; None leaves them undated
    advance_tax_paid_inr: Decimal = Decimal(0)
    return_filed: bool = False
    ftc_documents: FtcDocuments = Field(default_factory=FtcDocuments)
    remittances: list[Remittance] = Field(default_factory=list)
    lut_current: Optional[bool] = None       # a GST Letter of Undertaking in force for this year; None is unknown
    expense_classifications: list[ClassifiedExpense] = Field(default_factory=list)

    @model_validator(mode="after")
    def _engagements_within_receipts(self) -> "TaxpayerInput":
        if sum((e.amount_inr for e in self.engagements), Decimal(0)) > self.receipts.total:
            raise ValueError("engagement amounts add up to more than total receipts")
        if self.declared_profit is not None and self.declared_profit < 0:
            raise ValueError("declared_profit cannot be negative")
        years = [h.tax_year for h in self.election_history]
        if len(years) != len(set(years)):
            raise ValueError("election_history has two entries for the same tax year")
        if any(y >= self.tax_year for y in years):
            raise ValueError("election_history must hold earlier tax years only")
        if self.advance_tax_paid_inr < 0:
            raise ValueError("advance_tax_paid_inr cannot be negative")
        if any(not (0 <= c.confidence <= 1) for c in self.expense_classifications):
            raise ValueError("classification confidence must be between 0 and 1")
        return self


# ---- results ----

class ActSelection(_Strict):
    act_id: str
    rules_id: str
    label: str
    tax_year: int
    param_version: str


class RegimeResolution(_Strict):
    requested: Regime
    regime_in_force: Regime
    overridden: bool                 # the request was refused under the one-withdrawal rule
    withdrawal_this_year: bool       # switched from old back to new this year
    opt_out_barred_after: bool       # no further opt-out is allowed
    filing: Optional[str] = None     # "Form 10-IEA", "return_of_income" or None when the regime is unchanged


class Eligibility(_Strict):
    eligible: bool
    failed: list[str] = Field(default_factory=list)   # ENTITY_NOT_ELIGIBLE, NOT_RESIDENT, PROFESSION_NOT_SPECIFIED


class ReceiptsTest(_Strict):
    total: Decimal
    cash_like: Decimal
    cash_share_percent: Decimal
    low_cash: bool
    applicable_limit: Decimal
    within_limit: bool
    percent_of_limit: Decimal
    near_limit: bool


class PresumptiveIncome(_Strict):
    scheme_available: bool
    presumptive_amount: Decimal                 # 50% of receipts
    declared_profit: Optional[Decimal]
    income: Optional[Decimal]                   # None when it cannot be worked out
    basis: str                                  # presumptive | declared_higher | declared_lower | books_profit | unknown
    books_audit_required: bool
    tax_audit_required: bool
    audit_note: Optional[str] = None
    exemption_limit: Decimal


class RegimeTax(_Strict):
    regime: Regime
    total_income: Decimal            # after rounding under s.288A / s.516
    slab_tax: Decimal
    rebate: Decimal
    tax_after_rebate: Decimal
    surcharge: Decimal
    cess: Decimal
    payable: Decimal                 # after rounding under s.288B / s.516


class IndiaTax(_Strict):
    in_force: RegimeTax
    other: RegimeTax
    cheaper: Regime
    saving_inr: Decimal              # payable under the regime in force minus the other, if the other is cheaper else 0


class SubstantialPresence(_Strict):
    calendar_year: int
    days_current: int
    days_prior: int
    days_prior_2: int
    weighted_days: Decimal           # current + one third of prior + one sixth of the year before
    met_current_minimum: bool        # at least 31 days this year
    met_weighted: bool               # weighted total at least 183
    substantial_presence: bool


class EngagementSource(_Strict):
    label: str
    country_of_performance: str
    amount_inr: Decimal
    us_source: bool
    reason: str                      # PERFORMED_OUTSIDE_US | PERFORMED_IN_US | DE_MINIMIS


class SourceResult(_Strict):
    engagements: list[EngagementSource]
    us_source_inr: Decimal
    any_us_source: bool


class TreatyResult(_Strict):
    reached: bool                    # only reached when some income is US-source
    us_may_tax: bool
    basis: str                       # not_reached | fixed_base | days_threshold | exempt
    us_days: int
    days_threshold: int
    us_taxable_inr: Decimal          # US-source receipts the US may tax under Article 15


class FtcClaim(_Strict):
    form: str
    rule: str
    foreign_tax_inr: Decimal         # US tax on income the US may tax
    cap_inr: Decimal                 # Indian tax attributable, under the A-5 reading in force
    cap_basis: str
    credit_inr: Decimal              # lower of the two
    unrelieved_inr: Decimal
    statement_due: str               # ISO date: 12 months after the end of the year
    accountant_verification: bool


class UsRefund(_Strict):
    amount_inr: Decimal
    forms: list[str]
    reason: str                      # NOT_US_SOURCE | TREATY_EXEMPT


class ReliefResult(_Strict):
    route: str                       # none | credit | refund | credit_and_refund | manual_review
    ftc: Optional[FtcClaim]
    refunds: list[UsRefund]


class Itr4Bar(_Strict):
    bar: str
    source: str                      # firm | A-12 | A-16


class Instalment(_Strict):
    due: str                         # ISO date
    cumulative_percent: Decimal
    cumulative_amount_inr: Decimal


class AdvanceTax(_Strict):
    required: bool
    net_tax_inr: Decimal             # Indian tax payable less the foreign tax credit, rounded under s.288B
    schedule: str                    # none | single_instalment | four_instalments | unknown
    instalments: list[Instalment]
    shortfall_interest_percent: Optional[Decimal] = None


class Deadline(_Strict):
    key: str                         # return | advance_tax_1.. | ftc_statement | w8ben:<label> | gst_lut
    title: str
    due: str                         # ISO date
    citations: list[str]
    status: str                      # scheduled (no as_of) | upcoming | due_soon | passed | done
    days_left: Optional[int] = None  # from as_of; negative once passed
    amount_inr: Optional[Decimal] = None
    source_note: Optional[str] = None


class ReadinessItem(_Strict):
    key: str
    title: str
    status: str                      # ready | missing | pending | not_required
    citations: list[str]
    note: Optional[str] = None


class FtcReadiness(_Strict):
    """Form 44 (Rule 76, 2026) or Form 67 (Rule 128, 1962) readiness."""

    applicable: bool                 # a credit is being claimed
    form: str
    rule: str
    statement_due: Optional[str]
    items: list[ReadinessItem]
    ready: bool                      # nothing missing (pending items are not yet due)


class ComplianceResult(_Strict):
    itr_form: str
    itr_form_reasons: list[str]      # NOT_PRESUMPTIVE, or the ITR-4 bars that apply
    itr4_bars: list[Itr4Bar]
    itr4_possible_under_other_reading: bool   # ITR-3 only because of a contested assumption
    depends_on_contested: list[str]           # assumption IDs the form choice rests on
    advance_tax: AdvanceTax
    return_due_date: str
    return_due_basis: str            # non_audit | audit_case
    regime_filing: Optional[str] = None
    ftc_readiness: Optional[FtcReadiness] = None
    deadlines: list[Deadline] = Field(default_factory=list)


class EngineResult(_Strict):
    persona_id: str
    act: ActSelection
    regime: RegimeResolution
    eligibility: Eligibility
    receipts_test: ReceiptsTest
    income: PresumptiveIncome
    india_tax: Optional[IndiaTax]
    us_presence: SubstantialPresence
    us_source: SourceResult
    treaty: TreatyResult
    relief: ReliefResult
    compliance: ComplianceResult
    flags: list[Flag]
    trace: list[TraceStep]
    config: EngineConfig
    assumptions_applied: list[dict]
