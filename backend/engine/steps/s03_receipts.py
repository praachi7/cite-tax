"""Step 3: the gross receipts limit (Rs 50 lakh, or Rs 75 lakh when cash is 5% or less)."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import Eligibility, ReceiptsTest
from ..money import D


def check_receipts_limit(ctx: Ctx, eligibility: Eligibility) -> ReceiptsTest:
    r = ctx.inp.receipts
    total = r.total
    cash_like = r.cash_like if ctx.p("presumptive.profession.non_account_payee_cheque_counts_as_cash") else r.cash
    share = (cash_like * 100 / total) if total else Decimal(0)

    low_cash = share <= D(ctx.p("presumptive.profession.low_cash_max_percent"))   # 5% or less qualifies
    limit = D(ctx.p("presumptive.profession.limit_low_cash_inr" if low_cash else "presumptive.profession.limit_inr"))
    within = total <= limit                                                       # "not exceeding"
    pct = (total * 100 / limit)
    near = within and eligibility.eligible and pct >= D(ctx.p("flags.receipts_near_limit_percent"))

    ctx.log(3, "ENG.03.receipts_limit", "Gross receipts limit",
            inputs={"total_receipts": total, "cash_like_receipts": cash_like},
            outputs={"cash_share_percent": share, "low_cash": low_cash, "applicable_limit": limit,
                     "within_limit": within, "percent_of_limit": pct})
    if near:
        ctx.flag("RECEIPTS_NEAR_LIMIT", "warning",
                 f"Receipts are {pct:.1f}% of the Rs {limit:,.0f} limit.", "ENG.03.receipts_limit",
                 ctx.params.cite("presumptive.profession.limit_inr"))
    return ReceiptsTest(total=total, cash_like=cash_like, cash_share_percent=share, low_cash=low_cash,
                        applicable_limit=limit, within_limit=within, percent_of_limit=pct, near_limit=near)
