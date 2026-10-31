"""Step 8: India-US Convention, Article 15 (independent personal services)."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import SourceResult, TreatyResult
from .s06_us_presence import us_calendar_year


def apply_article_15(ctx: Ctx, source: SourceResult) -> TreatyResult:
    threshold = ctx.p("treaty.art15.stay_days_threshold")
    days = ctx.inp.us_days_by_year.get(us_calendar_year(ctx), 0)
    warn_at = ctx.p("flags.us_days_warning_threshold")
    ctx.p("treaty.art15.counting_period")

    if not source.any_us_source:
        ctx.log(8, "ENG.08.article_15", "Treaty Article 15", inputs={"us_days": days},
                outputs={"reached": False, "basis": "not_reached"},
                note="No income is US-source, so the US has no right to tax it and the treaty is not reached.")
        return TreatyResult(reached=False, us_may_tax=False, basis="not_reached", us_days=days,
                            days_threshold=threshold, us_taxable_inr=Decimal(0))

    if ctx.inp.us_fixed_base and ctx.p("treaty.art15.fixed_base_test"):
        may_tax, basis = True, "fixed_base"
    elif days >= threshold:                       # "amounts to or exceeds 90 days"
        may_tax, basis = True, "days_threshold"
    else:
        may_tax, basis = False, "exempt"

    ctx.log(8, "ENG.08.article_15", "Treaty Article 15: fixed base or 90 days",
            inputs={"us_days": days, "fixed_base": ctx.inp.us_fixed_base, "us_source_inr": source.us_source_inr},
            outputs={"us_may_tax": may_tax, "basis": basis},
            note="Days are counted in the calendar year, the US taxable year of an individual.")
    if basis == "fixed_base":
        ctx.flag("US_FIXED_BASE", "warning", "A fixed base regularly available in the US lets the US tax the income "
                 "attributable to it.", "ENG.08.article_15", ctx.params.cite("treaty.art15.fixed_base_test"))
    elif basis == "days_threshold":
        ctx.flag("ARTICLE_15_TRIGGERED", "warning", f"{days} US days reach the {threshold}-day trigger, so the US may "
                 "tax the income from work done there.", "ENG.08.article_15", ctx.params.cite("treaty.art15.stay_days_threshold"))
    elif days >= warn_at:
        ctx.flag("US_DAYS_WARNING", "warning", f"{days} US days is close to the {threshold}-day trigger.",
                 "ENG.08.article_15", ctx.params.cite("treaty.art15.stay_days_threshold"))
    if may_tax:
        ctx.flag("US_RETURN_REQUIRED", "warning", "The US may tax this income; a US return (Form 1040-NR) is needed.",
                 "ENG.08.article_15", ctx.params.cite("treaty.art15.stay_days_threshold") + ["IRS_1040NR:all"])
    return TreatyResult(reached=True, us_may_tax=may_tax, basis=basis, us_days=days, days_threshold=threshold,
                        us_taxable_inr=source.us_source_inr if may_tax else Decimal(0))
