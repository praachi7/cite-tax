"""Compliance and audit-risk flags of SRS/SDS Table 3.1, as named, parameterised rules.

Each rule is one row: a code, a severity, the Table 3.1 trigger, the parameter keys whose sources it
cites, a note for any source not yet in corpus/registry.yaml, and a check. The check reads its thresholds
through ctx.p() (never a literal) and returns the reason, with the figures that triggered it, or None.

A check that needs information the user has not given (a date, a LUT status, remittance records,
classifier output) does not fire: an unchecked item is not a finding. Foreign tax credit documents are
the exception, because the credit cannot be claimed without them, so FtcDocuments defaults to "not in hand".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional

from .context import Ctx
from .models import (AdvanceTax, Eligibility, FtcReadiness, IndiaTax, PresumptiveIncome, ReceiptsTest,
                     ReliefResult, TreatyResult)
from .money import D

RULE_PREFIX = "ENG.10.flag"
_RETURN_NON_AUDIT = "return.due_date_business_profession_non_audit"
_RETURN_AUDIT = "return.due_date_audit_cases"


@dataclass(frozen=True)
class Facts:
    """The step results the rules look at."""

    eligibility: Eligibility
    receipts: ReceiptsTest
    income: PresumptiveIncome
    india: Optional[IndiaTax]
    treaty: TreatyResult
    relief: ReliefResult
    advance_tax: AdvanceTax
    return_due: date
    ftc_readiness: FtcReadiness


@dataclass(frozen=True)
class Hit:
    reason: str
    assumptions: tuple[str, ...] = ()
    cite_keys: tuple[str, ...] = ()     # parameters to cite for this case only (e.g. which schedule applies)


@dataclass(frozen=True)
class FlagRule:
    code: str
    severity: str                       # info | low | medium | high, as in SRS/SDS Table 3.1
    trigger: str                        # the Table 3.1 wording
    cite_keys: tuple[str, ...]          # parameters whose sources are the flag's citations
    check: Callable[[Ctx, Facts], Optional[Hit]]
    extra_cites: tuple[str, ...] = ()
    source_note: Optional[str] = None   # a source not yet in corpus/registry.yaml, or "internal"
    case_cite_keys: tuple[str, ...] = ()   # parameters a hit may add for its case (Hit.cite_keys)

    @property
    def rule_id(self) -> str:
        return f"{RULE_PREFIX}.{self.code}"


def _rs(x: Decimal) -> str:
    return f"Rs {x:,.0f}"


def exports_services(ctx: Ctx) -> bool:
    return ctx.inp.foreign_clients or any(e.client_is_us_person for e in ctx.inp.engagements)


def w8ben_expiry(ctx: Ctx, signed: date) -> date:
    """Valid to the last day of the third calendar year after the year of signing."""
    return date(signed.year + ctx.p("us.w8ben.validity_calendar_years_after_signing"), 12, 31)


# ---- checks ----

def _w8ben_invalid(ctx: Ctx, f: Facts) -> Optional[Hit]:
    on = ctx.inp.as_of or date(ctx.inp.tax_year + 1, 3, 31)      # undated: the form must cover the whole year
    problems = []
    for e in ctx.inp.engagements:
        if not e.client_is_us_person:
            continue
        name = e.label or "a US client"
        if not e.w8ben_on_file:
            problems.append(f"no Form W-8BEN is on file with {name}")
        elif e.w8ben_signed is not None and on > w8ben_expiry(ctx, e.w8ben_signed):
            problems.append(f"the W-8BEN given to {name} expired on {w8ben_expiry(ctx, e.w8ben_signed).isoformat()}")
    if not problems:
        return None
    rate = ctx.p("us.withholding.foreign_person_rate_percent")
    text = "; ".join(problems)
    return Hit(f"{text[0].upper()}{text[1:]}. Without a valid form the client may withhold {rate}%.")


def _us_tax_on_india_work(ctx: Ctx, f: Facts) -> Optional[Hit]:
    rows = [e for e in ctx.inp.engagements if e.country_of_performance != "US" and e.us_tax_withheld_inr > 0]
    if not rows:
        return None
    total = sum((e.us_tax_withheld_inr for e in rows), Decimal(0))
    return Hit(f"US tax of {_rs(total)} was withheld on work performed outside the US. That income is not "
               "US-source, so the tax is not creditable in India; claim it back from the IRS on Form 1040-NR.")


def _us_days_warning(ctx: Ctx, f: Facts) -> Optional[Hit]:
    t = f.treaty
    warn = ctx.p("flags.us_days_warning_threshold")
    if t.reached and warn <= t.us_days < t.days_threshold:
        return Hit(f"{t.us_days} US days in the calendar year is {t.days_threshold - t.us_days} days short of "
                   f"the {t.days_threshold}-day Article 15 trigger.")
    return None


def _us_days_trigger(ctx: Ctx, f: Facts) -> Optional[Hit]:
    t = f.treaty
    if t.reached and t.us_days >= t.days_threshold:
        return Hit(f"{t.us_days} US days reach the {t.days_threshold}-day Article 15 trigger, so the US may tax "
                   "the income from the work done there.")
    return None


def _receipts_near_limit(ctx: Ctx, f: Facts) -> Optional[Hit]:
    ctx.p("flags.receipts_near_limit_percent")      # applied in step 3, which sets near_limit
    r = f.receipts
    if r.near_limit:
        return Hit(f"Gross receipts of {_rs(r.total)} are {r.percent_of_limit:.1f}% of the "
                   f"{_rs(r.applicable_limit)} limit.")
    return None


def _cash_share_above_5(ctx: Ctx, f: Facts) -> Optional[Hit]:
    r = f.receipts
    if not f.eligibility.eligible or r.total == 0 or r.low_cash:
        return None
    pct = ctx.p("presumptive.profession.low_cash_max_percent")
    low = D(ctx.p("presumptive.profession.limit_inr"))
    high = D(ctx.p("presumptive.profession.limit_low_cash_inr"))
    return Hit(f"Cash and non-account-payee receipts are {r.cash_share_percent:.1f}% of gross receipts, above "
               f"{pct}%, so the presumptive limit is {_rs(low)} instead of {_rs(high)}.")


def _profit_below_50(ctx: Ctx, f: Facts) -> Optional[Hit]:
    i = f.income
    if i.basis != "declared_lower" or not i.books_audit_required:
        return None
    rate = ctx.p("presumptive.profession.rate_percent")
    return Hit(f"Profit declared ({_rs(i.declared_profit)}) is below {rate}% of receipts ({_rs(i.presumptive_amount)}) "
               f"and income exceeds the {_rs(i.exemption_limit)} exemption limit, so books of account and a tax "
               "audit are required.")


def _foreign_account_held(ctx: Ctx, f: Facts) -> Optional[Hit]:
    if ctx.inp.foreign_assets_held:
        return Hit("Foreign assets or accounts were held during the year; report them in Schedule FA. "
                   "This also bars ITR-4.")
    if ctx.inp.platform_wallet_balance_abroad and ctx.config.platform_wallet_is_foreign_asset:
        return Hit("A balance held abroad on a payment platform is treated as a foreign account (assumption A-12, "
                   "conservative reading); report it in Schedule FA. This also bars ITR-4.", ("A-12",))
    return None


def _ftc_docs_incomplete(ctx: Ctx, f: Facts) -> Optional[Hit]:
    rd = f.ftc_readiness
    if not rd.applicable:
        return None
    parts = []
    missing = [i.title for i in rd.items if i.status == "missing"]
    if missing:
        parts.append(f"{rd.form} is not ready; missing: " + "; ".join(missing) + ".")
    if ctx.inp.as_of and rd.statement_due and not ctx.inp.ftc_documents.statement_filed:
        days = (date.fromisoformat(rd.statement_due) - ctx.inp.as_of).days
        if days < 0:
            parts.append(f"The {rd.form} window closed on {rd.statement_due}.")
        elif days <= ctx.p("flags.deadline_warning_days"):
            parts.append(f"The {rd.form} window closes on {rd.statement_due}, in {days} days.")
    return Hit(" ".join(parts)) if parts else None


def _fira_missing(ctx: Ctx, f: Facts) -> Optional[Hit]:
    need_code = ctx.p("flags.fira_purpose_code_required")
    bad = []
    for r in ctx.inp.remittances:
        gaps = (["FIRA"] if not r.fira_ref else []) + (["purpose code"] if need_code and not r.purpose_code else [])
        if gaps:
            bad.append(f"{r.label or 'a receipt'} ({_rs(r.amount_inr)}): no {' or '.join(gaps)}")
    if not bad:
        return None
    return Hit(f"{len(bad)} export receipt(s) lack remittance evidence: " + "; ".join(bad) + ".")


def _gst_lut_missing(ctx: Ctx, f: Facts) -> Optional[Hit]:
    if ctx.inp.lut_current is not False or not exports_services(ctx):
        return None
    ctx.p("gst.aggregate_turnover_includes_exports")
    threshold = D(ctx.p("gst.registration_threshold_inr"))
    if f.receipts.total < threshold:
        return None
    return Hit(f"Aggregate turnover of {_rs(f.receipts.total)} (exports included) is at or above {_rs(threshold)} "
               "and no Letter of Undertaking is in force for the year, so exports cannot be zero-rated without "
               "paying IGST.")


def _advance_tax_due(ctx: Ctx, f: Facts) -> Optional[Hit]:
    a, on = f.advance_tax, ctx.inp.as_of
    if on is None or not a.required:
        return None
    window = timedelta(days=ctx.p("flags.deadline_warning_days"))
    current = [i for i in a.instalments if on >= date.fromisoformat(i.due) - window]
    if not current:
        return None
    inst, paid = current[-1], ctx.inp.advance_tax_paid_inr
    short = inst.cumulative_amount_inr - paid
    if short <= 0:
        return None
    when = "was due" if on > date.fromisoformat(inst.due) else "is due"
    if a.schedule == "single_instalment":
        keys = ("advance_tax.presumptive.single_instalment_due", "advance_tax.presumptive.shortfall_interest_percent")
        tail = f" Simple interest at {a.shortfall_interest_percent}% runs on the shortfall."
    else:
        keys, tail = ("advance_tax.regular.instalments",), " Interest runs on the shortfall."
    return Hit(f"Advance tax of {_rs(inst.cumulative_amount_inr)} {when} by {inst.due}; {_rs(paid)} paid, "
               f"shortfall {_rs(short)}.{tail}", cite_keys=keys)


def _return_due(ctx: Ctx, f: Facts) -> Optional[Hit]:
    on = ctx.inp.as_of
    if on is None or ctx.inp.return_filed:
        return None
    days = (f.return_due - on).days
    if days > ctx.p("flags.deadline_warning_days"):
        return None
    key = (_RETURN_AUDIT if f.income.tax_audit_required else _RETURN_NON_AUDIT,)
    if days < 0:
        return Hit(f"The return of income was due on {f.return_due.isoformat()}, {-days} days ago.", cite_keys=key)
    return Hit(f"The return of income is due on {f.return_due.isoformat()}, in {days} days.", cite_keys=key)


def _low_classification_confidence(ctx: Ctx, f: Facts) -> Optional[Hit]:
    floor = D(ctx.p("flags.classification_confidence_min_percent"))
    uncertain = ctx.p("flags.classification_uncertain_label")
    low = [c for c in ctx.inp.expense_classifications if c.label == uncertain or c.confidence * 100 < floor]
    if not low:
        return None
    amount = sum((c.amount_inr for c in low), Decimal(0))
    return Hit(f"{len(low)} expense(s) totalling {_rs(amount)} are labelled {uncertain!r} or below {floor}% "
               "agreement; review them. They affect only the actual-profit comparison, never presumptive income.")


# ---- SRS/SDS Table 3.1, in table order (US_DAYS_WARNING / US_DAYS_TRIGGER share one row) ----

RULES: tuple[FlagRule, ...] = (
    FlagRule("W8BEN_INVALID", "high",
             "No W-8BEN on file with a US client, or past the last day of the third calendar year after signing",
             ("us.w8ben.validity_calendar_years_after_signing", "us.withholding.foreign_person_rate_percent"),
             _w8ben_invalid),
    FlagRule("US_TAX_ON_INDIA_WORK", "high", "US tax withheld on services performed in India",
             ("ftc.excess_over_treaty_rate_ignored",), _us_tax_on_india_work,
             extra_cites=("IRC:s862(a)(3)", "IRS_PUB515:all", "IRS_1040NR:all")),
    FlagRule("US_DAYS_WARNING", "medium", "80 or more days in the US in the calendar year",
             ("treaty.art15.stay_days_threshold",), _us_days_warning),
    FlagRule("US_DAYS_TRIGGER", "high", "90 or more days in the US in the calendar year",
             ("treaty.art15.stay_days_threshold",), _us_days_trigger),
    FlagRule("RECEIPTS_NEAR_LIMIT", "medium", "Gross receipts at or above 90% of the applicable Rs 50L / Rs 75L limit",
             ("presumptive.profession.limit_inr", "presumptive.profession.limit_low_cash_inr"), _receipts_near_limit),
    FlagRule("CASH_SHARE_ABOVE_5", "medium",
             "Cash and non-account-payee receipts above 5%, so the limit falls to Rs 50L",
             ("presumptive.profession.low_cash_max_percent",
              "presumptive.profession.non_account_payee_cheque_counts_as_cash"), _cash_share_above_5),
    FlagRule("PROFIT_BELOW_50", "high", "Declared profit below 50% and total income above the exemption limit",
             ("presumptive.profession.books_audit_if_lower_profit_and_income_above_exemption",), _profit_below_50),
    FlagRule("FOREIGN_ACCOUNT_HELD", "high", "Any balance held abroad during the calendar year",
             ("itr4.bars",), _foreign_account_held),
    FlagRule("FTC_DOCS_INCOMPLETE", "high",
             "Foreign TIN, foreign tax certificate or DTAA article missing; Form 44 window closing",
             ("ftc.form", "ftc.statement_deadline_months_after_year_end"), _ftc_docs_incomplete),
    FlagRule("FIRA_MISSING", "medium", "Export receipt without FIRA / e-FIRA or purpose code (e.g. P0802)",
             ("gst.export_of_services_requires_foreign_exchange", "flags.fira_purpose_code_required"), _fira_missing,
             source_note="Purpose codes are RBI reporting codes for banks (guidance, not tax law); a missing code "
                         "is a documentation gap, not a breach of the Income-tax Act."),
    FlagRule("GST_LUT_MISSING", "medium", "Aggregate turnover of Rs 20L or more and exports without a current LUT",
             ("gst.registration_threshold_inr", "gst.aggregate_turnover_includes_exports",
              "gst.lut_allows_export_without_igst"), _gst_lut_missing),
    FlagRule("ADVANCE_TAX_DUE", "medium", "Tax of Rs 10,000 or more not paid by 15 March",
             ("advance_tax.threshold_inr",), _advance_tax_due,
             case_cite_keys=("advance_tax.presumptive.single_instalment_due",
                             "advance_tax.presumptive.shortfall_interest_percent", "advance_tax.regular.instalments")),
    FlagRule("RETURN_DUE", "info", "Return due date approaching (31 August, non-audit)", (), _return_due,
             case_cite_keys=(_RETURN_NON_AUDIT, _RETURN_AUDIT)),
    FlagRule("LOW_CLASSIFICATION_CONFIDENCE", "low", "Classifier confidence below threshold, or label uncertain",
             (), _low_classification_confidence, source_note="Internal (SRS/SDS NFR-7): not a legal requirement."),
)

TABLE_3_1_CODES = tuple(r.code for r in RULES)


def evaluate(ctx: Ctx, facts: Facts) -> list[str]:
    """Run every rule, raise the flags that fire, and log one trace step. Returns the codes raised."""
    raised = []
    for rule in RULES:
        for k in rule.cite_keys:
            ctx.p(k)
        hit = rule.check(ctx, facts)
        if hit is None:
            continue
        undeclared = set(hit.cite_keys) - set(rule.case_cite_keys)
        if undeclared:
            raise ValueError(f"{rule.code}: case citations {sorted(undeclared)} are not declared in the rule")
        for k in hit.cite_keys:
            ctx.p(k)
        keys = rule.cite_keys + hit.cite_keys
        cites = [c for k in keys for c in ctx.params.cite(k)] + list(rule.extra_cites)
        ctx.flag(rule.code, rule.severity, hit.reason, rule.rule_id, cites,
                 assumptions=list(hit.assumptions), source_note=rule.source_note)
        raised.append(rule.code)
    ctx.log(10, "ENG.10.audit_flags", "Compliance and audit-risk flags (SRS/SDS Table 3.1)",
            cites=[c for r in RULES for c in r.extra_cites],
            inputs={"rules": len(RULES), "as_of": ctx.inp.as_of.isoformat() if ctx.inp.as_of else "none"},
            outputs={"raised": raised})
    return raised
