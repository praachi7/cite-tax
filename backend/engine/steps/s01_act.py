"""Step 1: select the Act by tax year, and resolve the regime in force across both Acts."""
from __future__ import annotations

from ..context import Ctx
from ..models import ActSelection, Regime, RegimeResolution


def select_act(ctx: Ctx) -> ActSelection:
    ps = ctx.params
    ctx.log(1, "ENG.01.act_selection", "Select the Act and parameter file for the tax year",
            inputs={"tax_year": ctx.inp.tax_year},
            outputs={"act_id": ps.act_id, "rules_id": ps.rules_id, "label": ps.label},
            note="The Act follows from the tax year in the parameter files; it is never chosen by a language model.")
    return ActSelection(act_id=ps.act_id, rules_id=ps.rules_id, label=ps.label,
                        tax_year=ps.tax_year, param_version=ps.version)


def resolve_regime(ctx: Ctx) -> RegimeResolution:
    """One withdrawal of an opt-out is allowed; after it the person can never opt out again.

    The history can cross the 1961 and 2025 Acts, so the rule is read from the current year's file:
    s.115BAC(6) read with CBDT FAQ Q5 for 1961, and s.202(4)(a)(iii) and (iv) for 2025.
    """
    inp = ctx.inp
    limit = ctx.p("regime.switch_back_limit")
    form = ctx.p("regime.opt_out_form")
    prior = sorted(inp.election_history, key=lambda h: h.tax_year)

    withdrawals_before = 0
    opted_out = False
    for h in prior:
        if h.regime == Regime.old:
            if withdrawals_before >= limit:
                ctx.flag("REGIME_HISTORY_INCONSISTENT", "warning",
                         f"Tax year {h.tax_year} shows an opt-out after the one allowed withdrawal.",
                         "ENG.01.regime", ctx.params.cite("regime.switch_back_limit"))
            opted_out = True
        elif opted_out:
            withdrawals_before += 1
            opted_out = False
    last = prior[-1].regime if prior else Regime.new
    barred_before = withdrawals_before >= limit

    requested = inp.regime_choice
    in_force = requested
    overridden = False
    withdrawal_now = False
    if requested == Regime.old and barred_before:
        in_force, overridden = Regime.new, True
        ctx.flag("REGIME_OPT_OUT_BARRED", "blocker",
                 "The one allowed withdrawal of an opt-out has been used, so the old regime cannot be chosen again. "
                 "The new regime is applied.", "ENG.01.regime", ctx.params.cite("regime.switch_back_limit"))
    elif requested == Regime.new and last == Regime.old:
        withdrawal_now = True

    changed = in_force != last
    filing = form if changed else None
    ctx.log(1, "ENG.01.regime", "Resolve the regime election across both Acts",
            inputs={"requested": requested, "last_prior_regime": last, "withdrawals_before": withdrawals_before},
            outputs={"regime_in_force": in_force, "overridden": overridden,
                     "withdrawal_this_year": withdrawal_now, "filing": filing})
    return RegimeResolution(
        requested=requested, regime_in_force=in_force, overridden=overridden,
        withdrawal_this_year=withdrawal_now,
        opt_out_barred_after=barred_before or withdrawal_now, filing=filing)
