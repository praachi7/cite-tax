# CiteTax

An AI-assisted decision-support prototype for **India-resident freelancers in specified professions (such as information technology) who work for clients in the United States**. It works out what tax is owed in India, whether the US can tax any of the income, and which filings and documents are needed. Every figure, classification and flag comes with a **verified citation** to the governing law, and the system says so openly when the law is unclear.

> **Status: research and design are complete. Implementation has not started.**
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

## Planned stack

Next.js, FastAPI, PostgreSQL with pgvector, one hosted LLM API, and Docker Compose. The LLM provider and the embedding model will be chosen when the phase that needs them begins.

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

Not available yet. Instructions will be added when the first implementation phase is complete.

## Disclaimer

CiteTax is an educational prototype. Its output is not legal or tax advice, has not been reviewed by a chartered accountant or other professional, and should not be relied on for filing a return. Points of law that the sources do not settle are handled as documented, conservative assumptions.

## Licence

To be decided. Note that code from AGPL-licensed or unlicensed projects must not be copied into this repository.
