"""Step 10: compliance outputs: ITR form, advance tax, return due date."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..context import Ctx
from ..models import (AdvanceTax, ComplianceResult, Instalment, Itr4Bar, IndiaTax, PresumptiveIncome,
                      ReliefResult, RegimeResolution)
from ..money import D, round_to_multiple


def _on(ctx: Ctx, mm_dd: str, year_of_april: int) -> date:
    """A date in the financial year that starts in April of year_of_april."""
    month, day = (int(x) for x in mm_dd.split("-"))
    return date(year_of_april if month >= 4 else year_of_april + 1, month, day)


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
    if any(b.bar == "foreign_assets" for b in bars):
        ctx.flag("SCHEDULE_FA_REQUIRED", "warning", "Foreign assets or accounts must be reported in Schedule FA.",
                 "ENG.10.itr_form", ctx.params.cite("itr4.bars"))
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


def return_due(ctx: Ctx, income: PresumptiveIncome) -> tuple[str, str]:
    audit = income.tax_audit_required
    key = "return.due_date_audit_cases" if audit else "return.due_date_business_profession_non_audit"
    month, day = (int(x) for x in ctx.p(key).split("-"))
    due = date(ctx.inp.tax_year + 1, month, day)
    basis = "audit_case" if audit else "non_audit"
    ctx.log(10, "ENG.10.return_due_date", "Due date for the return of income",
            inputs={"tax_audit_required": audit}, outputs={"return_due_date": due.isoformat(), "basis": basis})
    return due.isoformat(), basis


def compliance_outputs(ctx: Ctx, india: IndiaTax | None, income: PresumptiveIncome, relief: ReliefResult,
                       regime: RegimeResolution) -> ComplianceResult:
    form, reasons, bars, contested_only, depends = choose_itr_form(ctx, income, relief)
    advance = plan_advance_tax(ctx, india, income, relief)
    due, basis = return_due(ctx, income)
    return ComplianceResult(itr_form=form, itr_form_reasons=reasons, itr4_bars=bars,
                            itr4_possible_under_other_reading=contested_only, depends_on_contested=depends,
                            advance_tax=advance, return_due_date=due, return_due_basis=basis,
                            regime_filing=regime.filing)
