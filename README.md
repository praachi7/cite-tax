# CiteTax

An AI-assisted decision-support prototype for **India-resident freelancers in specified professions (such as information technology) who work for clients in the United States**. It works out what tax is owed in India, whether the US can tax any of the income, and which filings and documents are needed. Every figure, classification and flag comes with a **verified citation** to the governing law, and the system says so openly when the law is unclear.

> **Status: Phases A to G are built: law as data, the deterministic tax engine, corpus and retrieval (awaiting hand review of the corpus), cited answers, ingestion and classification, compliance and audit-risk flags, and the API, dashboard and deployment. Phase H (evaluation) has not started, so error rates are not yet measured.**
> This is an educational student project. It does not give legal or tax advice, and it uses synthetic data only.

## The idea in one paragraph

Fees for work done physically in India are foreign-source income under US law, so the US usually does not tax them and the India-US treaty is rarely needed. The real burden is Indian, and it depends on the tax year. Income up to FY 2025-26 falls under the Income-tax Act, 1961. Income from Tax Year 2026-27 falls under the Income-tax Act, 2025, which renumbers sections, brings new Rules, and replaces Form 67 with Form 44. CiteTax chooses the right law for the chosen year, computes tax with a deterministic engine, and cites the exact provisions behind every output.

## What the user provides, and what they get

| The user provides | The user receives |
|---|---|
| A persona profile: residency, profession, tax year, US days, cash share, foreign accounts, GST status, regime history | A tax summary, with the governing Act shown |
| Transactions (CSV) and invoices (PDF) | US-side status and the relief route |
| Client details: W-8BEN date, US tax withheld, where the work was done | A compliance checklist: ITR form, Form 44 or 67, W-8BEN, Schedule FA, GST/LUT, deadlines |
| The tax year, and corrections to expense classifications | An audit-risk report and "Interpretation uncertain" notices |

## How it works

- **The LLM never computes and never picks the law version.** A deterministic law selector maps the tax year to the Act, and a rules engine produces every number.
- **Law is data, not code.** Rates, thresholds, form names and section numbers live in dated YAML files, with a concordance mapping old section numbers to new ones (44ADA to s.58(2) Sl. 3, and so on).
- **Retrieval is filtered by tax year first.** A hybrid keyword and vector search runs only over provisions valid for the chosen year.
- **Citations are checked twice.** First, does the cited section exist in the right Act version? Second, does the passage support the claim? Failures are shown as unsupported, not hidden.
- **Uncertainty is shown.** Where the sources do not settle a point, the system gives both readings with citations and the conservative default it applied.

## Scope

- **Users:** resident individuals in a specified profession, taxed under s.44ADA (1961 Act) or s.58(2) Table Sl. 3 (2025 Act). Other freelancers, other countries and old-regime deductions are planned for later.
- **Tax years:** FY 2025-26 (1961 Act) and Tax Year 2026-27 (2025 Act).
- **Country:** United States only, with a design that can extend to others.

## Stack

Next.js, FastAPI, PostgreSQL with pgvector, BGE-M3 embeddings run locally, Groq as the hosted LLM API (Phase D), and Docker Compose.

## Documentation

The project documents are kept outside this repository for now. They are:

| Document | What it is |
|---|---|
| SRS/SDS v2 | Requirements and design |
| Implementation Plan | Build phases, source and RAG conventions, what the user provides |
| Research report and source verification | The research behind the design, checked against the official texts, with the assumptions register |
| Challenges log | Problems met and how they were handled |

## Build phases

The work is divided by what is built, not by dates (details in the Implementation Plan):

A. Law as data, B. Deterministic tax engine, C. Corpus and retrieval, D. Citation verification and uncertainty handling, E. Ingestion and expense classification, F. Compliance and audit-risk flags, G. API, dashboard and deployment, H. Evaluation and final documentation.

## Legal sources

The law the system relies on comes from official publications: the Income-tax Acts of 1961 and 2025, the Income-tax Rules of 1962 and 2026, the Finance Acts of 2025 and 2026, CBDT notifications and FAQs, the India-US Convention of 1989, and IRS and US Code texts. The source PDFs are **not stored in this repository**, because some exceed GitHub's 100 MB file limit. A manifest with official download links is planned.

## Running the project

The parts are the law data (`params/`, `corpus/`), the loader and validator (`backend/lawdata/`), the tax engine (`backend/engine/`), retrieval (`backend/retrieval/`), cited answers (`backend/answer/`), ingestion (`backend/ingest/`), the API (`backend/api/`) and the dashboard (`frontend/`). The web app is described under "Web app (Phase G)" below.

```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt    # Python 3.12
.venv/Scripts/python -m pytest -q                                        # all tests
set PYTHONPATH=backend && python -m lawdata.validate                     # check the law-data files
```

The engine is a pure function over the parameter files, with no database, language model or network:

```python
from engine.models import TaxpayerInput
from engine.pipeline import run

result = run(TaxpayerInput(tax_year=2026, receipts={"electronic": 2400000}))
result.india_tax.in_force.payable      # Decimal rupees, rounded to Rs 10 as s.516 requires
result.compliance.itr_form             # "ITR-3" under the default A-16 assumption
result.trace                           # every step: rule ID, citations, parameter file used
```

The ten pipeline steps are in `backend/engine/steps/`. Assumption switches (A-3, A-5, A-12, A-16) are passed as an `EngineConfig`, whose defaults come from `corpus/assumptions.yaml`. Test personas P1 to P10 are in `backend/tests/engine/personas/`, each with hand-computed expected values and the statute citation for every figure.

### Corpus and retrieval (Phase C)

The corpus is a curated set of passages in `corpus/chunks/<SOURCE>.yaml`, one file per source, drafted from the PDFs according to `corpus/scope.yaml` and then reviewed by hand. Tables are typed by hand. Retrieval filters by tax year in SQL first, then fuses two ranked lists by default (exact citation match with concordance mapping, and BGE-M3 vectors). A third list, Postgres full text, is built but off by default: it lowered hit@5 from 0.85 to 0.80 on the labelled queries. The source PDFs must be in `sources/`.

```
.venv/Scripts/python scripts/extract_text.py          # PDFs -> build/text/ (needs poppler's pdftotext)
.venv/Scripts/python scripts/draft_chunks.py          # build/text + scope.yaml -> corpus/chunks/ (keeps reviewed chunks)
python -m lawdata.validate --chunks                   # chunk checks + every cited ID resolves (--strict: all reviewed)
docker compose up -d db                               # Postgres 17 + pgvector on port 5433
.venv/Scripts/python scripts/embed_chunks.py          # BGE-M3 on CPU, cached by content hash in build/embeddings/
.venv/Scripts/python scripts/load_index.py            # rebuild the index from the chunk files
.venv/Scripts/python scripts/eval_retrieval.py        # labelled queries -> eval/results/phase_c_retrieval.json
```

```python
from retrieval.search import retrieve
res = retrieve("What is the 44ADA limit?", tax_year=2026)
res.ids()             # ['IT2025:s58(2)/T3', ...]: the 2025 Act provision, never the 1961 text
res.refs.mappings     # 44ADA -> s.58(2) Table Sl. 3, via the concordance
res.hits[0].ranks     # which ranked lists found it, and at what rank
```

Tests marked `db` need the index loaded and are skipped otherwise.

### Web app (Phase G)

Screens, in the order of SRS/SDS section 3.5: **Persona & upload** (a P1–P10 persona or your own profile, plus a transactions CSV; each persona has a synthetic sample CSV) → **Classification review** (low-confidence and uncertain expenses first; relabel and re-run) → **Tax summary** → **Compliance checklist** → **Audit-risk report**, with a **Sources and notices** panel on the last three, and an **Ask a question** screen on `POST /ask`. The prototype disclaimer is on every page.

API endpoints (`backend/api/`):

| Endpoint | What it does |
|---|---|
| `POST /tax/estimate/upload` | Profile + transactions CSV (+ optional relabels) → parse → classify → `to_engine` → engine. Returns the estimate, transactions, classifications, the correction log, profit comparison and notices. Receipts come only from the CSV; relabels never change presumptive income. |
| `POST /tax/estimate` | The engine on figures typed in directly. |
| `GET /personas`, `GET /personas/{id}/transactions.csv` | Test personas P1–P10 and their synthetic transactions. |
| `GET /sources?ids=…` | The corpus passage behind each citation ID. |
| `POST /ask` | A cited answer, verified sentence by sentence (needs the index and `GROQ_API_KEY`). |
| `GET /evaluation` | The stored Phase H results (`eval/results/phase_h_summary.json`). |

Run it locally (two terminals):

```
.venv/Scripts/pip install -r requirements-api.txt
.venv/Scripts/python -m uvicorn api.app:app --app-dir backend --port 8000
cd frontend && npm install && npm run dev                                 # http://localhost:3000
```

Or the whole stack in Docker (the first build downloads CPU PyTorch, about 1.5 GB; the first `/ask` downloads BGE-M3):

```
docker compose up -d --build        # db :5433, api :8000, frontend :3000
```

CI (`.github/workflows/ci.yml`) runs ruff, mypy on `backend/api` (both pinned in `requirements-dev.txt`), `lawdata.validate --chunks` and `pytest -m "not db"` on the backend, and eslint, `tsc` and `next build` on the frontend. It uses no secrets and never calls the Groq API.

Known gaps: invoice PDF upload is not built (no PDF ingestion yet); classification corrections are logged in the response and the browser session only, because there is no audit table yet.

### Evaluation (Phase H)

One script runs every evaluation slice of SRS/SDS section 3.8 and writes `eval/results/phase_h_summary.json`, which the **Evaluation** screen (`GET /evaluation`) and the disclaimer on every page read from. The method, the results and the known failures are in [`eval/REPORT.md`](eval/REPORT.md); the demo walk-through is [`DEMO.md`](DEMO.md).

```
docker compose up -d db                                         # index loaded (scripts/load_index.py)
.venv/Scripts/python scripts/run_evaluation.py                  # all slices; needs GROQ_API_KEY for the model slices
.venv/Scripts/python scripts/run_evaluation.py --skip-llm       # arithmetic and retrieval only, no model calls
```

Each slice is measured on the original labelled sets and on held-out sets (`*_heldout.yaml` in `backend/tests/retrieval/` and `backend/tests/answer/`) written before the Phase H run. Their hashes are in `eval/heldout_hashes.json`, and the script stops if a held-out file has changed. Model responses are cached in `build/llm_cache/`, so a re-run sends no requests. The three Phase C/D scripts still run on their own and take `--queries`, `--cases` or `--pairs` to point at another set.

## Disclaimer

CiteTax is an educational prototype. Its output is not legal or tax advice, has not been reviewed by a chartered accountant or other professional, and should not be relied on for filing a return. Points of law that the sources do not settle are handled as documented, conservative assumptions.

## Licence

To be decided. Note that code from AGPL-licensed or unlicensed projects must not be copied into this repository.
