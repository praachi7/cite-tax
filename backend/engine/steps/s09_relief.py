"""Step 9: relief routing. Credit in India for US tax the US was entitled to charge; refund from the US otherwise."""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from ..context import Ctx
from ..models import FtcClaim, IndiaTax, ReceiptsTest, ReliefResult, SourceResult, SubstantialPresence, TreatyResult, UsRefund


def _statement_due(ctx: Ctx) -> str:
    """Twelve months after the end of the previous year (31 March), which is the end of the assessment year."""
    months = ctx.p("ftc.statement_deadline_months_after_year_end")
    end = date(ctx.inp.tax_year + 1, 3, 31)
    idx = end.year * 12 + (end.month - 1) + months
    year, month = divmod(idx, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1]).isoformat()


def _cap(ctx: Ctx, india: IndiaTax, rt: ReceiptsTest, us_taxable: Decimal) -> tuple[Decimal, str]:
    """Indian tax attributable to the US income, under assumption A-5."""
    t = india.in_force
    tax = t.tax_after_rebate + t.surcharge + t.cess
    if t.total_income == 0 or rt.total == 0:
        return Decimal(0), ctx.config.ftc_cap_basis
    if ctx.config.ftc_cap_basis == "gross_receipts":
        # reading b: the US gross receipts, not their 50% share, are set against total income
        return min(tax, tax * us_taxable / t.total_income), "gross_receipts"
    # reading a: the deemed income from the US receipts, pro rata to total income
    return tax * us_taxable / rt.total, "deemed_income"


def route_relief(ctx: Ctx, india: IndiaTax | None, rt: ReceiptsTest, spt: SubstantialPresence,
                 source: SourceResult, treaty: TreatyResult) -> ReliefResult:
    form, rule = ctx.p("ftc.form"), ctx.p("ftc.rule")
    ctx.p("ftc.credit_is_lower_of_indian_and_foreign_tax")
    engagements = ctx.inp.engagements
    src = {i: s for i, s in enumerate(source.engagements)}

    for e in engagements:
        if e.client_is_us_person and e.us_tax_withheld_inr > 0 and not e.w8ben_on_file:
            ctx.flag("W8BEN_MISSING", "info", f"US tax was withheld by {e.label or 'a client'} and no Form W-8BEN "
                     "is on file; giving the client a valid W-8BEN stops further withholding.",
                     "ENG.09.relief", ctx.params.cite("us.withholding.foreign_person_rate_percent"))

    if spt.substantial_presence:
        ctx.log(9, "ENG.09.relief", "Relief routing", outputs={"route": "manual_review"},
                note="Substantial presence is met, so relief depends on the person's US status. Review needed.")
        return ReliefResult(route="manual_review", ftc=None, refunds=[])

    creditable = Decimal(0)
    refunds: dict[str, Decimal] = {}
    for i, e in enumerate(engagements):
        if e.us_tax_withheld_inr <= 0:
            continue
        s = src[i]
        if s.us_source and treaty.us_may_tax:
            creditable += e.us_tax_withheld_inr
        else:
            reason = "TREATY_EXEMPT" if s.us_source else "NOT_US_SOURCE"
            refunds[reason] = refunds.get(reason, Decimal(0)) + e.us_tax_withheld_inr

    claim = None
    if creditable > 0:
        if india is None:
            ctx.flag("FTC_NOT_COMPUTED", "warning", "Indian tax is unknown, so the credit cannot be capped.",
                     "ENG.09.relief")
        else:
            cap, basis = _cap(ctx, india, rt, treaty.us_taxable_inr)
            credit = min(creditable, cap)
            threshold = ctx.p("ftc.accountant_verification_threshold_inr")
            claim = FtcClaim(form=form, rule=rule, foreign_tax_inr=creditable, cap_inr=cap, cap_basis=basis,
                             credit_inr=credit, unrelieved_inr=creditable - credit, statement_due=_statement_due(ctx),
                             accountant_verification=threshold is not None and creditable >= threshold)
            ctx.flag("FTC_CAP_ASSUMPTION", "info", "The credit cap rests on assumption A-5 (contested).",
                     "ENG.09.relief", ctx.params.cite("ftc.credit_is_lower_of_indian_and_foreign_tax"))
            if claim.accountant_verification:
                ctx.flag("FTC_ACCOUNTANT_VERIFICATION", "warning", f"Foreign tax of Rs {creditable:,.0f} needs "
                         "verification by an accountant.", "ENG.09.relief",
                         ctx.params.cite("ftc.accountant_verification_threshold_inr"))

    refund_rows = []
    for reason, amount in refunds.items():
        forms = ["Form 1040-NR"]
        forms.append("Form 8233" if reason == "TREATY_EXEMPT" else "Form W-8BEN")
        refund_rows.append(UsRefund(amount_inr=amount, forms=forms, reason=reason))

    has_credit, has_refund = claim is not None, bool(refund_rows)
    route = ("credit_and_refund" if has_credit and has_refund else "credit" if has_credit
             else "refund" if has_refund else "none")
    if has_refund:
        ctx.p("us.form8233.claims_exemption_for_services_performed_in_us")
    ctx.log(9, "ENG.09.relief", "Relief routing: credit in India or refund from the US",
            cites=["IRS_1040NR:all", "IRS_F8233:all", "IRS_W8BEN:withholding"] if has_refund else None,
            inputs={"creditable_withholding_inr": creditable, "refundable": {k: str(v) for k, v in refunds.items()},
                    "A-5": ctx.config.ftc_cap_basis},
            outputs={"route": route, "credit_inr": claim.credit_inr if claim else Decimal(0),
                     "cap_inr": claim.cap_inr if claim else Decimal(0)},
            note="US tax is taken as withheld; the US liability itself is not computed.")
    return ReliefResult(route=route, ftc=claim, refunds=refund_rows)
