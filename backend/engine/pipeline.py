"""The ordered pipeline. Pure functions over the parameter files: no database, no model, no network."""
from __future__ import annotations

from .config import EngineConfig, applied_assumptions
from .context import Ctx
from .models import EngineResult, TaxpayerInput
from .params import ParamSet
from .steps.s01_act import resolve_regime, select_act
from .steps.s02_eligibility import check_eligibility
from .steps.s03_receipts import check_receipts_limit
from .steps.s04_income import compute_income
from .steps.s05_india_tax import compute_india_tax
from .steps.s06_us_presence import check_substantial_presence
from .steps.s07_source import apply_source_rule
from .steps.s08_treaty import apply_article_15
from .steps.s09_relief import route_relief
from .steps.s10_compliance import compliance_outputs


def run(inp: TaxpayerInput, config: EngineConfig | None = None, params: ParamSet | None = None) -> EngineResult:
    config = config or EngineConfig.defaults()
    params = params or ParamSet.for_tax_year(inp.tax_year)
    ctx = Ctx(inp, params, config)

    act = select_act(ctx)
    regime = resolve_regime(ctx)
    elig = check_eligibility(ctx)
    receipts = check_receipts_limit(ctx, elig)
    income = compute_income(ctx, elig, receipts, regime)
    india = compute_india_tax(ctx, income.income, regime)
    presence = check_substantial_presence(ctx)
    source = apply_source_rule(ctx)
    treaty = apply_article_15(ctx, source)
    relief = route_relief(ctx, india, receipts, presence, source, treaty)
    compliance = compliance_outputs(ctx, india, income, relief, regime)

    return EngineResult(persona_id=inp.persona_id, act=act, regime=regime, eligibility=elig,
                        receipts_test=receipts, income=income, india_tax=india, us_presence=presence,
                        us_source=source, treaty=treaty, relief=relief,
                        compliance=compliance, flags=ctx.flags,
                        trace=ctx.trace, config=config, assumptions_applied=applied_assumptions(config))
