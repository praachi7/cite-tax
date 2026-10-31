"""Run context: parameter reads, trace and flags for one engine run."""
from __future__ import annotations

from typing import Any

from .config import EngineConfig
from .models import TaxpayerInput
from .params import ParamSet
from .trace import Flag, TraceStep


class Ctx:
    def __init__(self, inp: TaxpayerInput, params: ParamSet, config: EngineConfig):
        self.inp = inp
        self.params = params
        self.config = config
        self.trace: list[TraceStep] = []
        self.flags: list[Flag] = []
        self._read: list[str] = []

    def p(self, key: str) -> Any:
        """Read a parameter; the key is remembered and cited by the next log() call."""
        if key not in self._read:
            self._read.append(key)
        return self.params.get(key)

    def log(self, step: int, rule_id: str, title: str, *, cites: list[str] | None = None,
            inputs: dict | None = None, outputs: dict | None = None, note: str | None = None) -> None:
        keys, self._read = self._read, []
        citations: list[str] = []
        for c in [c for k in keys for c in self.params.cite(k)] + list(cites or []):
            if c not in citations:
                citations.append(c)
        self.trace.append(TraceStep(
            step=step, rule_id=rule_id, title=title, param_version=self.params.version,
            param_keys=keys, citations=citations,
            inputs=_plain(inputs or {}), outputs=_plain(outputs or {}), note=note))

    def flag(self, code: str, severity: str, message: str, rule_id: str, cites: list[str] | None = None) -> None:
        if any(f.code == code and f.rule_id == rule_id for f in self.flags):
            return
        self.flags.append(Flag(code=code, severity=severity, message=message, rule_id=rule_id,
                               citations=list(cites or [])))


def _plain(d: dict) -> dict:
    """Keep Decimals exact but make the values JSON-friendly."""
    from decimal import Decimal
    out = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif hasattr(v, "value"):
            out[k] = v.value
        else:
            out[k] = v
    return out
