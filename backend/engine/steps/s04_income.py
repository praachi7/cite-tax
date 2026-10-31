"""Step 4: presumptive income, the books-and-audit rule, and tax audit."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import Eligibility, PresumptiveIncome, ReceiptsTest, RegimeResolution
from ..money import D, percent_of


def exemption_limit(ctx: Ctx, regime: str) -> Decimal:
    """Upper end of the nil-rate slab: the most that is not chargeable to tax."""
    return D(ctx.p(f"regime.{regime}.slabs")[0][1])


def compute_income(ctx: Ctx, elig: Eligibility, rt: ReceiptsTest, reg: RegimeResolution) -> PresumptiveIncome:
    total = rt.total
    rate = ctx.p("presumptive.profession.rate_percent")
    presumptive = percent_of(total, rate)
    declared = ctx.inp.declared_profit
    exempt = exemption_limit(ctx, reg.regime_in_force.value)
    available = elig.eligible and rt.within_limit
    audit_threshold = D(ctx.p("audit.profession.receipts_threshold_inr"))

    books_audit = tax_audit = False
    note = None
    income: Decimal | None

    if available:
        if declared is None or declared == presumptive:
            income, basis = presumptive, "presumptive"
        elif declared > presumptive:
            income, basis = declared, "declared_higher"   # "a sum higher than 50% claimed by the assessee"
        else:
            income, basis = declared, "declared_lower"
            # Declaring less than 50%: books and audit are needed if income exceeds the exemption limit.
            ctx.p("presumptive.profession.books_audit_if_lower_profit_and_income_above_exemption")
            if declared > exempt:
                books_audit = tax_audit = True
                note = "Profit declared below 50% of receipts and income above the exemption limit."
                ctx.flag("BOOKS_AUDIT_REQUIRED", "warning",
                         "Books of account and a tax audit are required because the profit declared is below "
                         f"{rate}% of receipts and income exceeds Rs {exempt:,.0f}.", "ENG.04.books_audit",
                         ctx.params.cite("presumptive.profession.books_audit_if_lower_profit_and_income_above_exemption"))
        if not books_audit and total > audit_threshold:
            ctx.p("audit.exempt_if_declared_as_presumptive")
            note = "Receipts exceed the audit threshold, but a person declaring under the presumptive scheme is exempt."
    else:
        # Presumptive taxation is unavailable, so books profit is needed and tax audit follows the receipts bar.
        income = declared
        basis = "books_profit" if declared is not None else "unknown"
        tax_audit = total > audit_threshold
        if tax_audit:
            note = "Presumptive taxation is unavailable and receipts exceed the audit threshold."
            ctx.flag("TAX_AUDIT_REQUIRED", "warning",
                     f"Receipts exceed Rs {audit_threshold:,.0f} and the presumptive scheme is not available.",
                     "ENG.04.books_audit", ctx.params.cite("audit.profession.receipts_threshold_inr"))
        if declared is None:
            ctx.flag("PROFIT_REQUIRED", "blocker",
                     "Presumptive taxation is unavailable, so the profit from books of account is needed.",
                     "ENG.04.presumptive_income")

    ctx.log(4, "ENG.04.presumptive_income", "Presumptive income and audit position",
            inputs={"total_receipts": total, "declared_profit": declared if declared is not None else "none",
                    "scheme_available": available},
            outputs={"presumptive_amount": presumptive, "income": income if income is not None else "unknown",
                     "basis": basis, "books_audit_required": books_audit, "tax_audit_required": tax_audit,
                     "exemption_limit": exempt},
            note=note)
    return PresumptiveIncome(scheme_available=available, presumptive_amount=presumptive, declared_profit=declared,
                             income=income, basis=basis, books_audit_required=books_audit,
                             tax_audit_required=tax_audit, audit_note=note, exemption_limit=exempt)
