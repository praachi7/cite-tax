"""Step 5: Indian income tax: slabs, rebate with marginal relief, surcharge guard, cess, old versus new."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import IndiaTax, Regime, RegimeResolution, RegimeTax
from ..money import D, percent_of, round_to_multiple


def slab_tax(slabs: list, income: Decimal) -> Decimal:
    tax = Decimal(0)
    for lower, upper, rate in slabs:
        lower = D(lower)
        top = income if upper is None else min(income, D(upper))
        if top > lower:
            tax += percent_of(top - lower, rate)
    return tax


def regime_tax(ctx: Ctx, regime: Regime, income: Decimal) -> RegimeTax:
    """Tax for one regime on a total income, using slabs and rebate only (no deductions)."""
    r = regime.value
    income = round_to_multiple(income, ctx.p("rounding.total_income_multiple_inr"))   # s.288A / s.516
    tax = slab_tax(ctx.p(f"regime.{r}.slabs"), income)

    limit = D(ctx.p(f"regime.{r}.rebate.income_limit_inr"))
    cap = D(ctx.p(f"regime.{r}.rebate.max_inr"))
    if income <= limit:
        after = max(tax - cap, Decimal(0))
    elif ctx.params.has(f"regime.{r}.rebate.marginal_relief") and ctx.p(f"regime.{r}.rebate.marginal_relief"):
        after = min(tax, income - limit)      # tax cannot exceed the income above the rebate limit
    else:
        after = tax
    rebate = tax - after

    surcharge = Decimal(0)
    if income > D(ctx.p("tax.surcharge.start_income_inr")):
        surcharge = percent_of(after, ctx.p("tax.surcharge.first_rate_percent"))
        ctx.flag("SURCHARGE_APPROXIMATE", "warning",
                 "Total income exceeds the surcharge threshold; marginal relief and the higher bands are not modelled.",
                 "ENG.05.surcharge", ctx.params.cite("tax.surcharge.start_income_inr"))
    cess = percent_of(after + surcharge, ctx.p("tax.cess_percent"))
    payable = round_to_multiple(after + surcharge + cess, ctx.p("rounding.payable_multiple_inr"))   # s.288B / s.516
    return RegimeTax(regime=regime, total_income=income, slab_tax=tax, rebate=rebate, tax_after_rebate=after,
                     surcharge=surcharge, cess=cess, payable=payable)


def compute_india_tax(ctx: Ctx, income: Decimal | None, reg: RegimeResolution) -> IndiaTax | None:
    if income is None:
        ctx.log(5, "ENG.05.india_tax", "Indian income tax", outputs={"computed": False},
                note="Total income is unknown, so no tax is computed.")
        return None
    in_force = reg.regime_in_force
    other = Regime.old if in_force == Regime.new else Regime.new
    a = regime_tax(ctx, in_force, income)
    b = regime_tax(ctx, other, income)
    cheaper = in_force if a.payable <= b.payable else other
    saving = a.payable - b.payable if b.payable < a.payable else Decimal(0)
    ctx.log(5, "ENG.05.india_tax", "Indian income tax: slabs, rebate, surcharge, cess",
            inputs={"income_before_rounding": income, "regime_in_force": in_force},
            outputs={"total_income": a.total_income, "slab_tax": a.slab_tax, "rebate": a.rebate,
                     "surcharge": a.surcharge, "cess": a.cess, "payable": a.payable,
                     "other_regime_payable": b.payable, "cheaper": cheaper})
    return IndiaTax(in_force=a, other=b, cheaper=cheaper, saving_inr=saving)
