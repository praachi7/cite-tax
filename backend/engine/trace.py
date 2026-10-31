"""Audit trail: every step records its rule ID, citations and the parameter version it used."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class Flag(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                     # e.g. BOOKS_AUDIT_REQUIRED
    severity: str                 # info | warning | blocker
    message: str
    rule_id: str
    citations: list[str] = Field(default_factory=list)
