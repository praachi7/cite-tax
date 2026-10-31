"""Assumption switches. Defaults come from corpus/assumptions.yaml so the two cannot drift apart."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lawdata.loader import load_assumptions


class EngineConfig(BaseModel):
    """One field per assumption config_flag in corpus/assumptions.yaml."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    it_specified_profession_1961: bool              # A-3
    ftc_cap_basis: str                              # A-5: deemed_income | gross_receipts
    platform_wallet_is_foreign_asset: bool          # A-12
    itr4_foreign_client_income_is_indian_source: bool  # A-16

    @classmethod
    def defaults(cls, **overrides: Any) -> "EngineConfig":
        values = {a.config_flag: a.config_default for a in load_assumptions()}
        values.update(overrides)
        return cls(**values)


def applied_assumptions(config: EngineConfig) -> list[dict]:
    """For each assumption: which reading the config selects, and whether that is the default.

    The interface uses this to show "Interpretation uncertain" with both readings.
    """
    out = []
    for a in load_assumptions():
        value = getattr(config, a.config_flag)
        reading = next((r for r in a.readings if r.flag_value == value), None)
        out.append({
            "id": a.id,
            "status": a.status.value,
            "config_flag": a.config_flag,
            "value": value,
            "reading": reading.key if reading else None,
            "is_default": value == a.config_default,
            "citations": list(reading.citations) if reading else [],
        })
    return out
