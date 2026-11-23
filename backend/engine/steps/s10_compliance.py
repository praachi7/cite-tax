"""Step 10: compliance outputs: ITR form, advance tax, return due date, Form 44 / Form 67 readiness,
the deadline tracker, and the compliance and audit-risk flags of SRS/SDS Table 3.1."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from .. import flag_rules
from ..context import Ctx
from ..models import (AdvanceTax, ComplianceResult, Deadline, Eligibility, FtcReadiness, Instalment, Itr4Bar,
                      IndiaTax, PresumptiveIncome, ReadinessItem, ReceiptsTest, ReliefResult, RegimeResolution,
                      TreatyResult)
from ..money import D, round_to_multiple


def _on(ctx: Ctx, mm_dd: str, year_of_april: int) -> date:
    """A date in the financial year that starts in April of year_of_april."""
    month, day = (int(x) for x in mm_dd.split("-"))
    return date(year_of_april if month >= 4 else year_of_april + 1, month, day)


def _cite(ctx: Ctx, *keys: str) -> list[str]:
    """Read the parameters (so the trace records them) and return their sources."""
    out: list[str] = []
    for k in keys:
        ctx.p(k)
        out += [c for c in ctx.params.cite(k) if c not in out]
    return out


def _itr4_bars(ctx: Ctx, income: PresumptiveIncome, relief: ReliefResult) -> list[Itr4Bar]:
    inp, cfg = ctx.inp, ctx.config
    known = ctx.p("itr4.bars")
    unknown = [b for b in inp.other_itr4_bars if b not in known]
    if unknown:
        raise ValueError(f"unknown ITR-4 bar(s) {unknown}; {ctx.params.act_id} knows {known}")

    found: list[Itr4Bar] = []
    if inp.foreign_assets_held:
        found.append(Itr4Bar(bar="foreign_assets", source="firm"))
    elif inp.platform_wallet_balance_abroad and cfg.platform_wallet_is_foreign_asset:     # A-12
        found.append(Itr4Bar(bar="foreign_assets", source="A-12"))
    foreign_clients = inp.foreign_clients or any(e.client_is_us_person for e in inp.engagements)
    if foreign_clients and not cfg.itr4_foreign_client_income_is_indian_source:           # A-16
        found.append(Itr4Bar(bar="foreign_source_income", source="A-16"))
    if income.income is not None and income.income > D(ctx.p("itr4.total_income_limit_inr")):
        found.append(Itr4Bar(bar="total_income_over_limit", source="firm"))
    if relief.ftc is not None:
        found.append(Itr4Bar(bar="foreign_tax_relief_claimed", source="firm"))
    for b in inp.other_itr4_bars:
        if all(f.bar != b for f in found):
            found.append(Itr4Bar(bar=b, source="firm"))
    return [f for f in found if f.bar in known]


def choose_itr_form(ctx: Ctx, income: PresumptiveIncome, relief: ReliefResult):
    presumptive_used = income.scheme_available and income.basis in ("presumptive", "declared_higher")
    bars = _itr4_bars(ctx, income, relief) if presumptive_used else []
    if bars:
        ctx.p("itr4.bars")
    contested_only = presumptive_used and bool(bars) and all(b.source != "firm" for b in bars)
    depends = sorted({b.source for b in bars if b.source != "firm"}) if contested_only else []

    if not presumptive_used:
        form, reasons = ctx.p("itr.fallback_form"), ["NOT_PRESUMPTIVE"]
    elif bars:
        form, reasons = ctx.p("itr.fallback_form"), [b.bar for b in bars]
    else:
        form, reasons = ctx.p("itr.presumptive_form"), []
    ctx.log(10, "ENG.10.itr_form", "Choose the ITR form",
            inputs={"presumptive_used": presumptive_used, "A-12": ctx.config.platform_wallet_is_foreign_asset,
                    "A-16": ctx.config.itr4_foreign_client_income_is_indian_source},
            outputs={"itr_form": form, "reasons": reasons, "bars": [f"{b.bar}:{b.source}" for b in bars],
                     "depends_on_contested": depends})
    return form, reasons, bars, contested_only, depends


def plan_advance_tax(ctx: Ctx, india: IndiaTax | None, income: PresumptiveIncome, relief: ReliefResult) -> AdvanceTax:
    if india is None:
        ctx.p("advance_tax.threshold_inr")
        ctx.log(10, "ENG.10.advance_tax", "Advance tax", outputs={"schedule": "unknown"},
                note="Indian tax is unknown, so advance tax cannot be worked out.")
        return AdvanceTax(required=False, net_tax_inr=Decimal(0), schedule="unknown", instalments=[])
    credit = relief.ftc.credit_inr if relief.ftc else Decimal(0)
    net = round_to_multiple(max(india.in_force.payable - credit, Decimal(0)), ctx.p("rounding.payable_multiple_inr"))
    required = net >= D(ctx.p("advance_tax.threshold_inr"))
    presumptive = income.scheme_available and income.basis in ("presumptive", "declared_higher")
    instalments: list[Instalment] = []
    interest = None
    if not required:
        schedule = "none"
    elif presumptive:
        schedule = "single_instalment"
        due = _on(ctx, ctx.p("advance_tax.presumptive.single_instalment_due"), ctx.inp.tax_year)
        instalments = [Instalment(due=due.isoformat(), cumulative_percent=Decimal(100), cumulative_amount_inr=net)]
        interest = D(ctx.p("advance_tax.presumptive.shortfall_interest_percent"))
    else:
        schedule = "four_instalments"
        for mm_dd, pct in ctx.p("advance_tax.regular.instalments"):
            instalments.append(Instalment(due=_on(ctx, mm_dd, ctx.inp.tax_year).isoformat(),
                                          cumulative_percent=D(pct), cumulative_amount_inr=net * D(pct) / 100))
    ctx.p("advance_tax.threshold_inr")
    ctx.log(10, "ENG.10.advance_tax", "Advance tax: threshold and instalments",
            inputs={"payable_inr": india.in_force.payable, "ftc_credit_inr": credit},
            outputs={"net_tax_inr": net, "required": required, "schedule": schedule,
                     "due": [i.due for i in instalments]})
    return AdvanceTax(required=required, net_tax_inr=net, schedule=schedule, instalments=instalments,
                      shortfall_interest_percent=interest)


def _return_key(income: PresumptiveIncome) -> str:
    return "return.due_date_audit_cases" if income.tax_audit_required else "return.due_date_business_profession_non_audit"


def return_due(ctx: Ctx, income: PresumptiveIncome) -> tuple[str, str]:
    audit = income.tax_audit_required
    month, day = (int(x) for x in ctx.p(_return_key(income)).split("-"))
    due = date(ctx.inp.tax_year + 1, month, day)
    basis = "audit_case" if audit else "non_audit"
    ctx.log(10, "ENG.10.return_due_date", "Due date for the return of income",
            inputs={"tax_audit_required": audit}, outputs={"return_due_date": due.isoformat(), "basis": basis})
    return due.isoformat(), basis


# ---- Form 44 / Form 67 readiness (Rule 76(10) to (16), 2026; Rule 128(8) and (9), 1962) ----

def ftc_readiness(ctx: Ctx, relief: ReliefResult, return_due_date: str) -> FtcReadiness:
    form, rule = ctx.p("ftc.form"), ctx.p("ftc.rule")
    claim = relief.ftc
    if claim is None:
        ctx.log(10, "ENG.10.ftc_readiness", f"{form} readiness", outputs={"applicable": False},
                note="No foreign tax credit is claimed, so no statement is needed.")
        return FtcReadiness(applicable=False, form=form, rule=rule, statement_due=None, items=[], ready=True)

    docs, on = ctx.inp.ftc_documents, ctx.inp.as_of
    have = lambda ok: "ready" if ok else "missing"                     # noqa: E731
    items = [
        ReadinessItem(key="foreign_tin", title="foreign tax identification number", status=have(docs.foreign_tin),
                      citations=_cite(ctx, "ftc.form")),
        ReadinessItem(key="foreign_tax_certificate", title="certificate or statement of the US tax deducted or paid",
                      status=have(docs.foreign_tax_certificate), citations=_cite(ctx, "ftc.form")),
        ReadinessItem(key="dtaa_article_and_rate", title="the DTAA article and rate relied on",
                      status=have(docs.dtaa_article_and_rate),
                      citations=_cite(ctx, "ftc.excess_over_treaty_rate_ignored") + ["DTAA_US:art15(1)"],
                      note="Foreign tax above what the treaty allows is not creditable."),
    ]
    threshold = ctx.p("ftc.accountant_verification_threshold_inr")
    if claim.accountant_verification:
        items.append(ReadinessItem(
            key="accountant_verification", title="verification by an accountant", status=have(docs.accountant_verification),
            citations=_cite(ctx, "ftc.accountant_verification_threshold_inr"),
            note=f"Foreign tax of Rs {claim.foreign_tax_inr:,.0f} is at or above Rs {threshold:,.0f}."))
    else:
        items.append(ReadinessItem(
            key="accountant_verification", title="verification by an accountant", status="not_required",
            citations=_cite(ctx, "ftc.accountant_verification_threshold_inr"),
            note="No verification rule applies under this Act." if threshold is None else
                 f"Foreign tax is below Rs {threshold:,.0f}."))

    due = date.fromisoformat(return_due_date)
    timely = ("ready" if ctx.inp.return_filed else "missing" if on is not None and on > due else "pending")
    items.append(ReadinessItem(key="timely_return", title=f"return of income filed by {return_due_date}", status=timely,
                               citations=_cite(ctx, "ftc.statement_requires_timely_return"),
                               note="The statement deadline below assumes the return is filed on time."))
    stmt_due = claim.statement_due
    stmt = ("ready" if docs.statement_filed else
            "missing" if on is not None and on > date.fromisoformat(stmt_due) else "pending")
    items.append(ReadinessItem(key="statement_filed", title=f"{form} furnished by {stmt_due}", status=stmt,
                               citations=_cite(ctx, "ftc.statement_deadline_months_after_year_end")))
    if docs.foreign_tax_disputed:
        follow = ctx.p("ftc.disputed_tax_followup_form")
        months = ctx.p("ftc.disputed_tax_followup_window_months")
        items.append(ReadinessItem(
            key="disputed_tax", title="evidence of settlement of the disputed US tax", status="pending",
            citations=_cite(ctx, "ftc.disputed_tax_credit_deferred", "ftc.disputed_tax_followup_form"),
            note=f"Credit for the disputed part waits for settlement; file {follow or 'the evidence and undertaking'} "
                 f"within {months} months of it."))

    ready = all(i.status != "missing" for i in items)
    ctx.log(10, "ENG.10.ftc_readiness", f"{form} readiness checklist",
            inputs={"foreign_tax_inr": claim.foreign_tax_inr, "accountant_verification": claim.accountant_verification},
            outputs={"ready": ready, "missing": [i.key for i in items if i.status == "missing"],
                     "statement_due": stmt_due})
    return FtcReadiness(applicable=True, form=form, rule=rule, statement_due=stmt_due, items=items, ready=ready)


# ---- deadline tracker (SRS/SDS FR-21) ----

def _status(ctx: Ctx, due: date, done: bool) -> tuple[str, Optional[int]]:
    on = ctx.inp.as_of
    days = (due - on).days if on is not None else None
    if done:
        return "done", days
    if days is None:
        return "scheduled", None
    if days < 0:
        return "passed", days
    return ("due_soon" if days <= ctx.p("flags.deadline_warning_days") else "upcoming"), days


def deadlines(ctx: Ctx, income: PresumptiveIncome, receipts: ReceiptsTest, advance: AdvanceTax,
              readiness: FtcReadiness, return_due_date: str) -> list[Deadline]:
    inp = ctx.inp
    out: list[Deadline] = []

    def add(key, title, due: date, citations, done=False, amount=None, note=None):
        status, days = _status(ctx, due, done)
        out.append(Deadline(key=key, title=title, due=due.isoformat(), citations=citations, status=status,
                            days_left=days, amount_inr=amount, source_note=note))

    add("return", "Return of income", date.fromisoformat(return_due_date), _cite(ctx, _return_key(income)),
        done=inp.return_filed)
    sched_key = ("advance_tax.presumptive.single_instalment_due" if advance.schedule == "single_instalment"
                 else "advance_tax.regular.instalments")
    for n, i in enumerate(advance.instalments, 1):
        add(f"advance_tax_{n}", f"Advance tax: {i.cumulative_percent}% cumulative", date.fromisoformat(i.due),
            _cite(ctx, sched_key, "advance_tax.threshold_inr"), done=inp.advance_tax_paid_inr >= i.cumulative_amount_inr,
            amount=i.cumulative_amount_inr)
    if readiness.applicable and readiness.statement_due:
        add("ftc_statement", f"{readiness.form} statement for the foreign tax credit",
            date.fromisoformat(readiness.statement_due), _cite(ctx, "ftc.statement_deadline_months_after_year_end"),
            done=inp.ftc_documents.statement_filed)
    for e in inp.engagements:
        if e.client_is_us_person and e.w8ben_on_file and e.w8ben_signed is not None:
            add(f"w8ben:{e.label or 'client'}", f"Form W-8BEN expires ({e.label or 'client'})",
                flag_rules.w8ben_expiry(ctx, e.w8ben_signed), _cite(ctx, "us.w8ben.validity_calendar_years_after_signing"))
    gst_threshold = D(ctx.p("gst.registration_threshold_inr"))
    if flag_rules.exports_services(ctx) and receipts.total >= gst_threshold:
        add("gst_lut", "GST Letter of Undertaking for the year's exports", date(inp.tax_year, 3, 31),
            _cite(ctx, "gst.registration_threshold_inr"), done=inp.lut_current is True,
            note="Furnished before the financial year starts: IGST Act s.16(3) and CGST Rules r.96A, secondary, "
                 "not yet in corpus/registry.yaml (to verify).")

    out.sort(key=lambda d: d.due)
    ctx.log(10, "ENG.10.deadlines", "Deadline tracker",
            inputs={"as_of": inp.as_of.isoformat() if inp.as_of else "none"},
            outputs={"deadlines": [f"{d.key}:{d.due}:{d.status}" for d in out]})
    return out


def compliance_outputs(ctx: Ctx, india: IndiaTax | None, income: PresumptiveIncome, relief: ReliefResult,
                       regime: RegimeResolution, eligibility: Eligibility, receipts: ReceiptsTest,
                       treaty: TreatyResult) -> ComplianceResult:
    form, reasons, bars, contested_only, depends = choose_itr_form(ctx, income, relief)
    advance = plan_advance_tax(ctx, india, income, relief)
    due, basis = return_due(ctx, income)
    readiness = ftc_readiness(ctx, relief, due)
    tracker = deadlines(ctx, income, receipts, advance, readiness, due)
    flag_rules.evaluate(ctx, flag_rules.Facts(
        eligibility=eligibility, receipts=receipts, income=income, india=india, treaty=treaty, relief=relief,
        advance_tax=advance, return_due=date.fromisoformat(due), ftc_readiness=readiness))
    return ComplianceResult(itr_form=form, itr_form_reasons=reasons, itr4_bars=bars,
                            itr4_possible_under_other_reading=contested_only, depends_on_contested=depends,
                            advance_tax=advance, return_due_date=due, return_due_basis=basis,
                            regime_filing=regime.filing, ftc_readiness=readiness, deadlines=tracker)
