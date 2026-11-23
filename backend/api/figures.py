"""Join each summary figure to the trace step that produced it.

The engine records citations per trace step, not per number. This table says which step produced
which result field, so the interface can show every figure next to its rule ID and citations.
The citations shown are therefore all those of the step, not only the one provision behind the figure.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from engine.models import EngineResult

# (section, dotted path into the JSON result, label, rule ID of the producing trace step)
FIGURES: list[tuple[str, str, str, str]] = [
    ("Law applied", "act.label", "Governing Act", "ENG.01.act_selection"),
    ("Law applied", "regime.regime_in_force", "Regime in force", "ENG.01.regime"),
    ("Law applied", "regime.filing", "Regime filing", "ENG.01.regime"),
    ("Eligibility", "eligibility.eligible", "Eligible for presumptive taxation", "ENG.02.eligibility"),
    ("Eligibility", "eligibility.failed", "Failed conditions", "ENG.02.eligibility"),
    ("Receipts", "receipts_test.total", "Gross receipts", "ENG.03.receipts_limit"),
    ("Receipts", "receipts_test.cash_share_percent", "Cash share (%)", "ENG.03.receipts_limit"),
    ("Receipts", "receipts_test.applicable_limit", "Applicable receipts limit", "ENG.03.receipts_limit"),
    ("Receipts", "receipts_test.within_limit", "Within the limit", "ENG.03.receipts_limit"),
    ("Income", "income.presumptive_amount", "Presumptive amount (50%)", "ENG.04.presumptive_income"),
    ("Income", "income.income", "Taxable profession income", "ENG.04.presumptive_income"),
    ("Income", "income.basis", "Basis", "ENG.04.presumptive_income"),
    ("Income", "income.books_audit_required", "Books and audit required", "ENG.04.presumptive_income"),
    ("India tax", "india_tax.in_force.total_income", "Total income (rounded)", "ENG.05.india_tax"),
    ("India tax", "india_tax.in_force.slab_tax", "Tax on slabs", "ENG.05.india_tax"),
    ("India tax", "india_tax.in_force.rebate", "Rebate", "ENG.05.india_tax"),
    ("India tax", "india_tax.in_force.surcharge", "Surcharge", "ENG.05.india_tax"),
    ("India tax", "india_tax.in_force.cess", "Health and education cess", "ENG.05.india_tax"),
    ("India tax", "india_tax.in_force.payable", "Tax payable (regime in force)", "ENG.05.india_tax"),
    ("India tax", "india_tax.other.payable", "Tax payable (other regime)", "ENG.05.india_tax"),
    ("India tax", "india_tax.cheaper", "Cheaper regime", "ENG.05.india_tax"),
    ("US position", "us_presence.weighted_days", "Weighted US days", "ENG.06.substantial_presence"),
    ("US position", "us_presence.substantial_presence", "Substantial presence", "ENG.06.substantial_presence"),
    ("US position", "us_source.us_source_inr", "US-source receipts", "ENG.07.source_rule"),
    ("US position", "treaty.us_may_tax", "US may tax under Article 15", "ENG.08.article_15"),
    ("US position", "treaty.basis", "Article 15 basis", "ENG.08.article_15"),
    ("US position", "treaty.us_taxable_inr", "Receipts the US may tax", "ENG.08.article_15"),
    ("Relief", "relief.route", "Relief route", "ENG.09.relief"),
    ("Relief", "relief.ftc.form", "Credit form", "ENG.09.relief"),
    ("Relief", "relief.ftc.credit_inr", "Foreign tax credit", "ENG.09.relief"),
    ("Relief", "relief.ftc.unrelieved_inr", "Unrelieved foreign tax", "ENG.09.relief"),
    ("Compliance", "compliance.itr_form", "ITR form", "ENG.10.itr_form"),
    ("Compliance", "compliance.advance_tax.net_tax_inr", "Net tax for advance tax", "ENG.10.advance_tax"),
    ("Compliance", "compliance.advance_tax.schedule", "Advance tax schedule", "ENG.10.advance_tax"),
    ("Compliance", "compliance.return_due_date", "Return due date", "ENG.10.return_due_date"),
]


INR_PATHS = {
    "receipts_test.total", "receipts_test.applicable_limit", "income.presumptive_amount", "income.income",
    "india_tax.in_force.total_income", "india_tax.in_force.slab_tax", "india_tax.in_force.rebate",
    "india_tax.in_force.surcharge", "india_tax.in_force.cess", "india_tax.in_force.payable",
    "india_tax.other.payable", "us_source.us_source_inr", "treaty.us_taxable_inr", "relief.ftc.credit_inr",
    "relief.ftc.unrelieved_inr", "compliance.advance_tax.net_tax_inr",
}
UNITS = {"receipts_test.cash_share_percent": "percent", "us_presence.weighted_days": "days"}


def unit_of(path: str) -> Optional[str]:
    return "inr" if path in INR_PATHS else UNITS.get(path)


class Figure(BaseModel):
    section: str
    path: str
    label: str
    value: Any
    unit: Optional[str]          # inr | percent | days | None
    rule_id: str
    citations: list[str]
    param_version: Optional[str]


_MISSING = object()


def _dig(data: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if data is None:
            return _MISSING
        data = data.get(part, _MISSING) if isinstance(data, dict) else _MISSING
        if data is _MISSING:
            return _MISSING
    return data


def build_figures(result: EngineResult, dumped: dict) -> list[Figure]:
    """Figures whose step ran and whose value exists. Steps that did not run (e.g. no India tax) are left out."""
    steps = {}
    for t in result.trace:
        s = steps.setdefault(t.rule_id, {"citations": [], "param_version": t.param_version})
        s["citations"] += [c for c in t.citations if c not in s["citations"]]
    out = []
    for section, path, label, rule_id in FIGURES:
        value = _dig(dumped, path)
        if value is _MISSING or rule_id not in steps:
            continue
        out.append(Figure(section=section, path=path, label=label, value=value, unit=unit_of(path), rule_id=rule_id,
                          citations=steps[rule_id]["citations"], param_version=steps[rule_id]["param_version"]))
    return out
