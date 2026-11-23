"""FastAPI app: POST /tax/estimate and GET /personas.

Run: uvicorn api.app:app --app-dir backend --port 8000
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.params import UnsupportedTaxYear
from engine.pipeline import run
from lawdata.loader import load_assumptions

from .figures import Figure, build_figures
from .personas import load_personas

DISCLAIMER = ("CiteTax is an educational prototype. Its output is not legal or tax advice, has not been "
              "reviewed by a chartered accountant or other professional, and should not be relied on for filing a return.")


class ConfigOverrides(BaseModel):
    """Assumption switches; any left out take their default from corpus/assumptions.yaml."""

    model_config = ConfigDict(extra="forbid")

    it_specified_profession_1961: Optional[bool] = None          # A-3
    ftc_cap_basis: Optional[str] = None                          # A-5: deemed_income | gross_receipts
    platform_wallet_is_foreign_asset: Optional[bool] = None      # A-12
    itr4_foreign_client_income_is_indian_source: Optional[bool] = None  # A-16


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: TaxpayerInput
    config: ConfigOverrides = Field(default_factory=ConfigOverrides)


class Persona(BaseModel):
    id: str
    title: str
    input: dict[str, Any]


def create_app() -> FastAPI:
    app = FastAPI(title="CiteTax API", version="0.1.0", description=DISCLAIMER)

    @app.get("/personas", response_model=list[Persona])
    def personas() -> list[dict]:
        return load_personas()

    @app.post("/tax/estimate")
    def estimate(req: EstimateRequest) -> dict:
        overrides = req.config.model_dump(exclude_none=True)
        allowed = {a.config_flag: [r.flag_value for r in a.readings] for a in load_assumptions()}
        for flag, value in overrides.items():
            if value not in allowed.get(flag, []):
                raise HTTPException(status_code=422, detail=f"{flag}={value!r} is not a documented reading; allowed: {allowed.get(flag)}")
        try:
            config = EngineConfig.defaults(**overrides)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_context=False))
        try:
            result = run(req.input, config)
        except UnsupportedTaxYear as e:
            raise HTTPException(status_code=400, detail=str(e))
        dumped = result.model_dump(mode="json")
        dumped["figures"] = [f.model_dump(mode="json") for f in build_figures(result, dumped)]
        dumped["disclaimer"] = DISCLAIMER
        return dumped

    return app


app = create_app()

__all__ = ["app", "create_app", "Figure"]
