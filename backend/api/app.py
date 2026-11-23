"""FastAPI app.

POST /tax/estimate          engine on figures typed in
POST /tax/estimate/upload   transactions CSV + profile -> ingest -> classify -> engine (api/upload.py)
GET  /personas              P1-P10 engine inputs
GET  /personas/{id}/transactions.csv   the persona's synthetic transactions (ingest.synthetic)
GET  /sources?ids=...       corpus passages behind citation IDs
POST /ask                   Phase D cited answers
GET  /evaluation            Phase H measured results (eval/results/phase_h_summary.json)

Run: uvicorn api.app:app --app-dir backend --port 8000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.config import EngineConfig
from engine.models import TaxpayerInput
from engine.params import UnsupportedTaxYear
from engine.pipeline import run
from lawdata.loader import load_assumptions

from .figures import Figure, build_figures
from .personas import load_personas
from .upload import UploadError, UploadRequest, run_upload

MAX_SOURCE_IDS = 60
EVALUATION_SUMMARY = Path(__file__).resolve().parents[2] / "eval" / "results" / "phase_h_summary.json"

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


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=1000)
    tax_year: int


class UploadBody(UploadRequest):
    """A transactions CSV plus the profile fields; see api/upload.py."""

    config: ConfigOverrides = Field(default_factory=ConfigOverrides)


def _default_answerer():
    """The real Phase D pipeline: retrieval from Postgres, Groq for drafting and judging. Built on first use."""
    state: dict = {}

    def ask(question: str, tax_year: int):
        from answer.llm import GroqLLM
        from answer.pipeline import answer
        if "llm" not in state:
            state["llm"] = GroqLLM()
        return answer(question, tax_year, state["llm"])
    return ask


def _engine_config(cfg: ConfigOverrides) -> EngineConfig:
    """Assumption overrides checked against the documented readings, then merged over the defaults."""
    overrides = cfg.model_dump(exclude_none=True)
    allowed = {a.config_flag: [r.flag_value for r in a.readings] for a in load_assumptions()}
    for flag, value in overrides.items():
        if value not in allowed.get(flag, []):
            raise HTTPException(status_code=422, detail=f"{flag}={value!r} is not a documented reading; allowed: {allowed.get(flag)}")
    try:
        return EngineConfig.defaults(**overrides)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_context=False))


def create_app(answerer: Optional[Callable] = None, evaluation_summary: Path = EVALUATION_SUMMARY) -> FastAPI:
    """answerer(question, tax_year) -> answer.pipeline.Answer; tests pass a fake."""
    app = FastAPI(title="CiteTax API", version="0.1.0", description=DISCLAIMER)
    ask_fn = answerer or _default_answerer()

    @app.get("/evaluation")
    def evaluation() -> dict:
        """The stored Phase H results; written by scripts/run_evaluation.py, never computed on request."""
        if not evaluation_summary.exists():
            raise HTTPException(status_code=404, detail="no evaluation results yet: run scripts/run_evaluation.py")
        return {**json.loads(evaluation_summary.read_text(encoding="utf8")), "disclaimer": DISCLAIMER}

    @app.post("/ask")
    def ask(req: AskRequest) -> dict:
        from answer.llm import LLMError
        try:
            result = ask_fn(req.question, req.tax_year)
        except UnsupportedTaxYear as e:
            raise HTTPException(status_code=400, detail=str(e))
        except LLMError as e:
            raise HTTPException(status_code=503, detail=f"language model unavailable: {e}")
        body = result.to_dict()
        body["disclaimer"] = DISCLAIMER
        return body

    @app.get("/personas", response_model=list[Persona])
    def personas() -> list[dict]:
        return load_personas()

    @app.get("/personas/{persona_id}/transactions.csv", response_class=PlainTextResponse)
    def persona_csv(persona_id: str) -> PlainTextResponse:
        from ingest.csv_parser import to_csv_text
        from ingest.synthetic import PERSONAS, generate
        pid = persona_id.upper()
        if pid not in PERSONAS:
            raise HTTPException(status_code=404, detail=f"no synthetic transactions for {persona_id!r}")
        g = generate(pid)
        return PlainTextResponse(to_csv_text(g.transactions, g.blank_mode_ids), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{pid}_transactions.csv"'})

    @app.get("/sources")
    def sources(ids: list[str] = Query(default_factory=list)) -> dict:
        from answer.pipeline import corpus_resolver, pretty_ref
        if len(ids) > MAX_SOURCE_IDS:
            raise HTTPException(status_code=422, detail=f"at most {MAX_SOURCE_IDS} ids per request")
        resolver = corpus_resolver()
        out = []
        for cid in dict.fromkeys(ids):
            chunk = resolver.resolve(cid)
            row: dict[str, Any] = {"id": cid, "label": pretty_ref(cid), "resolved": chunk is not None}
            if chunk is not None:
                row.update(chunk_id=chunk.id, source_id=chunk.source_id, breadcrumb=chunk.breadcrumb,
                           heading=chunk.heading, text=chunk.text, reviewed=chunk.reviewed,
                           tax_year_first=chunk.tax_year_first, tax_year_last=chunk.tax_year_last)
            out.append(row)
        return {"sources": out, "disclaimer": DISCLAIMER}

    @app.post("/tax/estimate")
    def estimate(req: EstimateRequest) -> dict:
        config = _engine_config(req.config)
        try:
            result = run(req.input, config)
        except UnsupportedTaxYear as e:
            raise HTTPException(status_code=400, detail=str(e))
        dumped = result.model_dump(mode="json")
        dumped["figures"] = [f.model_dump(mode="json") for f in build_figures(result, dumped)]
        dumped["disclaimer"] = DISCLAIMER
        return dumped

    @app.post("/tax/estimate/upload")
    def estimate_upload(req: UploadBody) -> dict:
        config = _engine_config(req.config)
        try:
            body = run_upload(req, config)
        except UploadError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_context=False))
        except UnsupportedTaxYear as e:
            raise HTTPException(status_code=400, detail=str(e))
        body["disclaimer"] = DISCLAIMER
        return body

    return app


app = create_app()

__all__ = ["app", "create_app", "Figure"]
