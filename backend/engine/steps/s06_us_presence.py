"""Step 6: US substantial presence test (Pub. 519). Calendar-year days, weighted over three years."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import SubstantialPresence


def us_calendar_year(ctx: Ctx) -> int:
    return ctx.inp.us_calendar_year or ctx.inp.tax_year


def check_substantial_presence(ctx: Ctx) -> SubstantialPresence:
    year = us_calendar_year(ctx)
    days = ctx.inp.us_days_by_year
    cur, prior, prior2 = days.get(year, 0), days.get(year - 1, 0), days.get(year - 2, 0)
    # current days + 1/3 of last year's + 1/6 of the year before. Compared as sixths so no rounding creeps in.
    sixths = 6 * cur + 2 * prior + prior2
    weighted = Decimal(sixths) / 6
    met_min = cur >= ctx.p("us.spt.current_year_min_days")
    met_weighted = sixths >= 6 * ctx.p("us.spt.three_year_min_weighted_days")
    spt = met_min and met_weighted
    ctx.log(6, "ENG.06.substantial_presence", "US substantial presence test",
            inputs={"calendar_year": year, "days_current": cur, "days_prior": prior, "days_prior_2": prior2},
            outputs={"weighted_days": round(weighted, 4), "met_current_minimum": met_min,
                     "met_weighted": met_weighted, "substantial_presence": spt},
            note="The closer-connection exception and the treaty tie-breaker are not modelled.")
    if spt:
        ctx.flag("US_SUBSTANTIAL_PRESENCE", "blocker",
                 "The substantial presence test is met, so the person may be a US resident for tax and taxed there "
                 "on worldwide income. The closer-connection exception or the treaty tie-breaker may apply; "
                 "this needs review outside the engine.", "ENG.06.substantial_presence",
                 ctx.params.cite("us.spt.three_year_min_weighted_days"))
    return SubstantialPresence(calendar_year=year, days_current=cur, days_prior=prior, days_prior_2=prior2,
                               weighted_days=weighted, met_current_minimum=met_min,
                               met_weighted=met_weighted, substantial_presence=spt)
