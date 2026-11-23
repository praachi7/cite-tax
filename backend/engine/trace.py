"""Audit trail: every step records its rule ID, citations and the parameter version it used."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TraceStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step: int                     # pipeline step 1 to 10
    rule_id: str                  # e.g. ENG.05.rebate
    title: str
    param_version: str            # parameter file the values came from
    param_keys: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None


SEVERITIES = ("info", "low", "medium", "high", "blocker")   # lowest to highest; SRS/SDS Table 3.1 uses the first four


class Flag(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                     # e.g. PROFIT_BELOW_50
    severity: str                 # one of SEVERITIES
    message: str                  # the reason, with the figures that triggered it
    rule_id: str
    citations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)   # contested assumption IDs the flag rests on
    source_note: Optional[str] = None   # a source not yet in corpus/registry.yaml, or "internal"

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in SEVERITIES:
            raise ValueError(f"severity {v!r} is not one of {SEVERITIES}")
        return v
