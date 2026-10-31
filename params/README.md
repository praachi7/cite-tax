# Law as data: conventions

This folder will hold one YAML file per Act and tax year (for example the 1961 Act for FY 2025-26, and the 2025 Act for Tax Year 2026-27). The engine reads rates, thresholds, form names and deadlines from these files, so no law is hard-coded in code. The related files live in `corpus/`: the source registry, the sources manifest, the concordance and (later) the assumptions register.

## Tax years

A tax year is keyed by the calendar year in which it **starts**: FY 2025-26 is `2025`, Tax Year 2026-27 is `2026`.

## Citation IDs

Every value cites its evidence as `SOURCE:provision[/part]`. `SOURCE` must be a `cite_prefix` from `corpus/registry.yaml`.

| Example | Meaning |
|---|---|
| `IT2025:s58(2)/T3` | Income-tax Act 2025, s.58(2), Table Sl. 3 |
| `IT1961:s44ADA(1)` | Income-tax Act 1961, s.44ADA(1) |
| `RULES2026:r76(7)(a)` | Income-tax Rules 2026, rule 76(7)(a) |
| `DTAA_US:art15(1)(b)` | India-US Convention, Article 15(1)(b) |
| `CBDT_FAQ_PRES:Q17` | CBDT presumptive-taxation FAQ, question 17 |
| `FORM44:all` | The whole document (use `:all` when there is no section number) |
| `FA2026:sch1-partIA-paraA(I)` | A schedule location: First Schedule, Part I-A, Paragraph A, item (I) |
| `IRS_PUB901:india` | A short topic label, for guidance documents that have no section numbers (replace it with a page reference when the chunk exists) |

## Parameter files

A parameter file has a header (`act_id`, `rules_id`, `label`, `tax_year`, `valid_from`, `valid_to`) and a `params` map. Keys are dotted lower-case names such as `presumptive.limit.default`. Each parameter has:

| Field | Meaning |
|---|---|
| `value` | The value. Money is a whole number of rupees; percentages are plain numbers (50 means 50%); dates are ISO. |
| `unit` | Optional, for example `INR`, `percent`, `days`. |
| `sources` | One or more citation IDs. Required. |
| `status` | `verified` (read from the primary text), `secondary` (only secondary sources support it) or `to_verify`. |
| `verified_by` | Names of team members who cross-checked the value against the PDF page. Stays empty until someone has. |
| `note` | Optional. Anything a reader should know, such as which reading was applied. |

**Both parameter files must define the same keys**, so that the same engine code runs for both years. The validator checks this. A rule that exists in only one Act gets the key in both files, with a value that says it does not apply.

## Checking the files

From the repository root, with the virtual environment active:

```
python -m pytest -q                         # all tests
set PYTHONPATH=backend && python -m lawdata.validate           # structure and cross-references
set PYTHONPATH=backend && python -m lawdata.validate --files   # also checks source files and checksums
python scripts/update_manifest.py --check   # source files against the manifest
```

The source PDFs are not in the repository. Their official download links and checksums are in `corpus/sources_manifest.yaml`.
