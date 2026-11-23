"""Estimate from an uploaded transactions CSV: parse -> classify -> user relabels -> to_engine -> engine.

Every step is a public function of ingest or engine; this module only wires them together.
Receipts, remittances and expense classifications come from the CSV alone, so the profile may not carry them.
Relabels replace classifier output for expense rows only. They feed the engine's classification-confidence
flag and the profit comparison, never the receipts, so presumptive income cannot move
(backend/tests/ingest/test_ingest_presumptive_invariance.py; backend/tests/api/test_api_upload.py).
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from answer.notices import notices_by_id
from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.pipeline import run
from ingest.classifier import classify_all, compare_profit
from ingest.csv_parser import parse_csv_text
from ingest.models import Classification, Direction, ExpenseCategory, ReceiptMode
from ingest.to_engine import engine_inputs

from .figures import build_figures

# Fields the CSV supplies; a profile that sets them would bypass the upload.
CSV_FIELDS = ("receipts", "remittances", "expense_classifications")
MAX_CSV_CHARS = 2_000_000
USER_METHOD = "user"


class UploadError(ValueError):
    """A request the pipeline cannot run; the API answers 422 with this message."""


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: dict[str, Any]                                       # TaxpayerInput fields other than CSV_FIELDS
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_CHARS)
    relabels: dict[str, ExpenseCategory] = Field(default_factory=dict)   # expense id -> category the user chose
    # receipts whose mode the CSV does not settle count as cash (default) or other; both are cash-like for the limit
    unknown_mode_as: Literal["cash", "other"] = "cash"


def _apply_relabels(predicted: list[Classification], relabels: dict[str, ExpenseCategory],
                    receipt_ids: set[str]) -> tuple[list[Classification], list[dict]]:
    by_id = {c.transaction_id: c for c in predicted}
    for tid in relabels:
        if tid in receipt_ids:
            raise UploadError(f"{tid} is a receipt; only expenses can be relabelled")
        if tid not in by_id:
            raise UploadError(f"relabel for unknown transaction {tid!r}")
    final, corrections = [], []
    for c in predicted:
        new = relabels.get(c.transaction_id)
        if new is None:
            final.append(c)
            continue
        kind = "confirmed" if new is c.category else "corrected"
        final.append(Classification(transaction_id=c.transaction_id, category=new, confidence=Decimal(1),
                                    method=USER_METHOD, reason=f"{kind} by the user (classifier said {c.category.value})"))
        corrections.append({"transaction_id": c.transaction_id, "kind": kind, "predicted": c.category.value,
                            "predicted_confidence": str(c.confidence), "corrected_to": new.value})
    return final, corrections


def _notices(dumped: dict) -> list[dict]:
    """'Interpretation uncertain' notices for every contested assumption the run applied."""
    depends = set(dumped["compliance"]["depends_on_contested"])
    applied = [a["id"] for a in dumped["assumptions_applied"]]
    out = []
    for n in notices_by_id(applied):
        d = asdict(n)
        d["result_depends_on_it"] = n.assumption_id in depends
        if not d["result_depends_on_it"]:
            d["triggered_by"] = ["applied by the engine; this result does not turn on it"]
        out.append(d)
    return out


def run_upload(req: UploadRequest, config: EngineConfig) -> dict:
    present = [f for f in CSV_FIELDS if f in req.profile]
    if present:
        raise UploadError(f"{', '.join(present)} come from the CSV; remove them from the profile")
    if "tax_year" not in req.profile:
        raise UploadError("profile.tax_year is required")

    parsed = parse_csv_text(req.csv_text)
    if not parsed.transactions:
        msgs = "; ".join(f"line {e.line} {e.field}: {e.message}" for e in parsed.errors[:5])
        raise UploadError(f"no usable transactions in the CSV{': ' + msgs if msgs else ''}")
    txs = parsed.transactions

    predicted = classify_all(txs)
    receipt_ids = {t.id for t in txs if t.direction is Direction.receipt}
    final, corrections = _apply_relabels(predicted, req.relabels, receipt_ids)

    tax_year = req.profile["tax_year"]
    if not isinstance(tax_year, int):
        raise UploadError("profile.tax_year must be an integer such as 2026")
    ei = engine_inputs(txs, final, tax_year, unknown_as=ReceiptMode(req.unknown_mode_as))
    taxpayer = TaxpayerInput(**{**req.profile, **ei.as_fields()})   # ValidationError -> 422 in the app
    result = run(taxpayer, config)

    dumped = result.model_dump(mode="json")
    dumped["figures"] = [f.model_dump(mode="json") for f in build_figures(result, dumped)]
    profit = compare_profit(txs, final, result.receipts_test.total, result.income.presumptive_amount)
    pred_by_id = {c.transaction_id: c for c in predicted}

    return {
        "estimate": dumped,
        "transactions": [t.model_dump(mode="json") for t in txs],
        "classifications": [
            {**c.model_dump(mode="json"), "predicted": pred_by_id[c.transaction_id].model_dump(mode="json")}
            for c in final
        ],
        "corrections": corrections,
        "parse_errors": [e.model_dump(mode="json") for e in parsed.errors],
        "receipt_warnings": ei.warnings,
        "unknown_mode_as": req.unknown_mode_as,
        "profit_comparison": profit.model_dump(mode="json"),
        "notices": _notices(dumped),
    }


def strip_csv_fields(persona_input: dict) -> dict:
    """A persona's engine input with the CSV-supplied fields removed: the profile half of an upload."""
    return {k: v for k, v in persona_input.items() if k not in CSV_FIELDS}


__all__ = ["UploadRequest", "UploadError", "run_upload", "strip_csv_fields", "CSV_FIELDS"]
