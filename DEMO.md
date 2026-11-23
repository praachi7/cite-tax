# CiteTax demo script

About 15 minutes. Five personas (P1, P2, P7, P9, P10), one question on the Ask screen, then the Evaluation page.
Every figure shown comes from the deterministic engine; the language model is used only on the Ask screen.

## Before the audience arrives

1. Start the database, API and frontend (README, "Running the project"), then open <http://localhost:3000>.
2. **Warm up the Ask screen.** The first `/ask` after the API starts loads the BGE-M3 embedding model and then
   drafts and checks every sentence, so it takes **about 2 minutes**. Later questions take 30–60 s. Ask the demo
   question once before the demo; the answer is then cached and comes back at once.
3. Close other heavy programs: the API needs about 2 GB of RAM for BGE-M3.
4. Have the disclaimer banner visible at the top: it now carries the measured error rates and links to the
   Evaluation page.

## 1. P1 — the baseline (Tax Year 2026-27, Income-tax Act 2025)

**Click:** Persona and upload → pick **P1** → **Use P1's sample CSV** → **Classify and estimate** → **3 · Tax summary**.

**Say:**
- "An IT consultant with ₹24 lakh of receipts, all received electronically. The Act is chosen from the tax year, not
  by the model: Tax Year 2026-27 falls under the Income-tax Act 2025."
- "Deemed income is 50%, ₹12 lakh, under section 58(2) Table serial 3. Slab tax is ₹60,000, fully cancelled by the
  section 156 rebate, so nothing is payable. Each row shows its rule ID and the provisions it cites; click a citation
  to open the passage in the sources panel."
- "The return form is ITR-3, and the summary says why: it rests on assumption A-16, a contested point, so both readings
  are shown with the conservative default applied."

## 2. P2 — same figures, different law (FY 2025-26, Income-tax Act 1961)

**Click:** back to step 1 → pick **P2** → sample CSV → **Classify and estimate** → **3 · Tax summary**.

**Say:**
- "Same person, one year earlier. The numbers are identical, ₹12 lakh income and nil tax, because the rates did not
  change. What changes is the law: the citations are now section 44ADA, 115BAC and 87A of the 1961 Act."
- "This is the main risk the project targets: a system that cites the wrong Act for the year. The engine selects the
  Act from the year, and retrieval filters by year before searching."
- On **4 · Compliance checklist**: "The return is due on 31 August 2026 under section 139(1); viewed on 10 August, that
  is 21 days away, so a RETURN_DUE reminder shows."

## 3. P7 — foreign account and missing FIRA (A-12)

**Click:** pick **P7** → sample CSV → **Classify and estimate** → **5 · Audit-risk report**, then **3 · Tax summary**.

**Say:**
- "₹30 lakh of receipts, part of it through a Payoneer balance held abroad."
- "Two flags. FOREIGN_ACCOUNT_HELD: under assumption A-12 a platform wallet balance abroad is treated as a foreign
  asset, so Schedule FA applies and ITR-4 is barred. FIRA_MISSING: the Payoneer withdrawal has no foreign inward
  remittance advice and no RBI purpose code, which matter for GST export treatment; the flag cites IGST section 2(6)
  and the RBI purpose code P0802."
- On the summary, open the **Interpretation uncertain** notice for A-12: "Both readings, their citations, and the
  conservative default. No chartered accountant reviewed this, and the screen says so."

## 4. P9 — 85 days in the US, just under the treaty limit

**Click:** pick **P9** → sample CSV → **Classify and estimate** → **3 · Tax summary** (US position) → **5 · Audit-risk report**.

**Say:**
- "This consultant spent about 85 days in the US, and the US client withheld ₹2.4 lakh on the work done there."
- "Article 15 of the India-US treaty lets the US tax that income only at 90 days or more, or with a fixed base. At 85
  days the US may not tax it, so the withholding is refundable on Form 1040-NR, and Form 8233 stops future withholding."
- "US_DAYS_WARNING fires because 85 days is inside the warning band: five more days would change the answer."

## 5. P10 — profit declared below 50% (books, audit, review screen)

**Click:** pick **P10** → sample CSV → **Classify and estimate** → **2 · Classification review** → **5 · Audit-risk report**.

**Say:**
- "₹30 lakh of receipts, but the consultant declares 40% profit instead of the presumptive 50%."
- On the review screen: "Each expense row says why it is listed. The classifier marks one expense as uncertain and
  one below the confidence floor. You can relabel them and rerun. Classification never changes presumptive income;
  here it supports the declared profit."
- On the audit-risk report: "PROFIT_BELOW_50: declaring lower profit with income above the exemption limit means books
  of account and a tax audit under section 58(3), even though the tax is nil. LOW_CLASSIFICATION_CONFIDENCE asks
  for the review we just saw."

## 6. Ask a question (the only screen that uses the language model)

**Click:** **Ask a question** → tax year **2026-27** → type: *What is the 44ADA gross receipts limit?* → **Ask**.

**Say (while it runs, if not warmed up: about 2 minutes on the first question):**
- "This is a temporal trap: 44ADA is a 1961 Act section, but the year is governed by the 2025 Act. Retrieval maps it
  through the concordance to section 58(2) Table serial 3 and never returns 1961 Act text for this year."
- "The model writes the answer but can cite only the retrieved passages, by placeholder. Every sentence is then
  checked twice: stage 1 checks that the citation exists in the right Act version; stage 2, a judge model, checks
  that the passage supports the sentence. Sentences that fail are shown and labelled, not hidden."

Also say: "'Supported' means the checker model judged the passage supports the sentence. On real answers it accepted
3 of 9 sentences we found unsupported, so it is not a verification by a person."

**Do not ask live:** *My US client must withhold 30% on the work I do remotely from India. How do I get it back?*
(held-out case HF04). CiteTax currently accepts this false premise; see Known failures below.

Optional second question showing a refusal: *What are the UK income tax bands for a self-employed developer?* —
CiteTax declines or says it covers only Indian income tax (see the Evaluation page for how often this works).

## 7. Evaluation page

**Click:** **Evaluation** (or the link in the disclaimer banner).

**Say:**
- "This page shows where the system fails. Every slice from our design is measured on the set we built with, and on a
  held-out set written before the final run and never used for tuning."
- Point at the arithmetic row (all hand-computed figures match), the held-out retrieval row, the wrong-Act row (zero),
  and then at **Known failures**: "These are the cases that still go wrong, kept on the page on purpose."
- "We make no claim to be hallucination-free; the rates are on every page."

## Known failures to avoid in the live demo (and to mention if asked)

From `eval/REPORT.md`; the Evaluation page lists all of them.

- **HF04, the 30% withholding question** (above): the premise is not rejected. The answer repeats the 30% rule, suggests
  Forms 8233/W-8BEN and cites s.160(2), which does not apply. The engine's P6 persona handles this case correctly
  (US_TAX_ON_INDIA_WORK, refund route); show P6 if the topic comes up, not `/ask`.
- **HF03, "I must get a tax audit every year on the presumptive scheme"**: declined instead of saying no audit is needed.
- **Schedule FA / which return form / Payoneer balance questions** (HX01, HX02, X02): the "Interpretation uncertain"
  notice appears, but the answer is declined.
- **"Supported" labels**: judged by the model, not verified; 3 of 9 unsupported real sentences were accepted.

## If something goes wrong

- **Ask takes longer than 5 minutes or returns HTTP 503:** the Groq free tier is rate-limited (8,000 tokens per minute).
  Wait a minute and ask again; cached questions return at once.
- **"The CiteTax API did not answer":** the API is not running, or the database container is down
  (`docker compose ps`).
- **Evaluation page says no results:** run `scripts/run_evaluation.py` (README), or check that
  `eval/results/phase_h_summary.json` exists.
