"""Step 2: is the taxpayer eligible for presumptive taxation of a specified profession?"""
from __future__ import annotations

from ..context import Ctx
from ..models import Eligibility, Profession, ResidentialStatus


def check_eligibility(ctx: Ctx) -> Eligibility:
    inp = ctx.inp
    failed: list[str] = []

    entities = ctx.p("presumptive.profession.eligible_entities")
    if inp.entity_type.value not in entities:
        failed.append("ENTITY_NOT_ELIGIBLE")     # an HUF, an LLP or a company

    resident_ok = inp.residential_status in (ResidentialStatus.resident, ResidentialStatus.rnor)
    if ctx.p("presumptive.profession.resident_required") and not resident_ok:
        failed.append("NOT_RESIDENT")

    if inp.profession == Profession.information_technology:
        specified = bool(ctx.p("presumptive.specified_profession.includes_information_technology"))
        if ctx.params.act_id == "IT1961":
            specified = specified and ctx.config.it_specified_profession_1961   # assumption A-3
    else:
        specified = inp.profession == Profession.other_specified
    if not specified:
        failed.append("PROFESSION_NOT_SPECIFIED")

    ctx.log(2, "ENG.02.eligibility", "Eligibility for presumptive taxation of a specified profession",
            inputs={"entity_type": inp.entity_type, "residential_status": inp.residential_status,
                    "profession": inp.profession, "A-3": ctx.config.it_specified_profession_1961},
            outputs={"eligible": not failed, "failed": failed})
    for code in failed:
        ctx.flag(code, "blocker", f"Presumptive taxation is not available: {code}.", "ENG.02.eligibility",
                 ctx.params.cite("presumptive.profession.eligible_entities"))
    return Eligibility(eligible=not failed, failed=failed)
