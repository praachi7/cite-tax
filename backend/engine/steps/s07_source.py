"""Step 7: US source rule (IRC s.861(a)(3), s.862(a)(3)). Services are US-source where they are performed."""
from __future__ import annotations

from decimal import Decimal

from ..context import Ctx
from ..models import EngagementSource, SourceResult
from ..money import D
from .s06_us_presence import us_calendar_year


def _de_minimis(ctx: Ctx, us_engagements) -> bool:
    """s.861(a)(3): US work is not US-source if the person was in the US 90 days or fewer, the pay for it is
    $3,000 or less, and it was done for a foreign office or a non-US person. Unknown dollar amounts or a
    US-person client mean the exception is not applied, which is the conservative result."""
    days = ctx.inp.us_days_by_year.get(us_calendar_year(ctx), 0)
    if days > ctx.p("us.source.deminimis_days"):
        return False
    if not us_engagements or any(e.client_is_us_person or e.amount_usd is None for e in us_engagements):
        return False
    return sum((e.amount_usd for e in us_engagements), Decimal(0)) <= D(ctx.p("us.source.deminimis_amount_usd"))


def apply_source_rule(ctx: Ctx) -> SourceResult:
    us_work = [e for e in ctx.inp.engagements if e.country_of_performance.upper() == "US"]
    de_minimis = _de_minimis(ctx, us_work)
    rows = []
    for e in ctx.inp.engagements:
        in_us = e.country_of_performance.upper() == "US"
        if not in_us:
            us_source, reason = False, "PERFORMED_OUTSIDE_US"
        elif de_minimis:
            us_source, reason = False, "DE_MINIMIS"
        else:
            us_source, reason = True, "PERFORMED_IN_US"
        rows.append(EngagementSource(label=e.label, country_of_performance=e.country_of_performance.upper(),
                                     amount_inr=e.amount_inr, us_source=us_source, reason=reason))
    us_inr = sum((r.amount_inr for r in rows if r.us_source), Decimal(0))
    ctx.log(7, "ENG.07.source_rule", "Source of income: where the services were performed",
            inputs={"engagements": len(rows), "de_minimis_applied": de_minimis},
            outputs={"us_source_inr": us_inr, "reasons": [r.reason for r in rows]},
            note="Work done in India for a US client is not US-source, so the treaty is never reached for it.")
    return SourceResult(engagements=rows, us_source_inr=us_inr, any_us_source=us_inr > 0)
