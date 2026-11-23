# CiteTax evaluation report (Phase H)

Run on 23 November 2026 with `scripts/run_evaluation.py`. All figures below are in
`eval/results/phase_h_summary.json`, with per-case detail in the `phase_h_*_original.json` and
`phase_h_*_heldout.json` files next to it, and on the app's **Evaluation** page.

| Setting | Value |
|---|---|
| Language model (answers and stage 2 check) | `openai/gpt-oss-120b` on the Groq free tier, temperature 0, responses cached |
| Embedding model | BGE-M3, local CPU |
| Corpus | 300 passages on disk, 300 in the index |
| Model requests sent | 88 on the first full run (the held-out cases and pairs); 0 on re-runs (all cached) |

## 1. How the evaluation was set up

**Two sets per slice.** Every slice is reported twice:

- **Original:** the labelled sets used while building Phases C and D (40 retrieval queries, 14 answer cases,
  42 claim–passage pairs). The default retrieval lists were chosen on these same queries, so these numbers are
  optimistic.
- **Held-out:** 32 retrieval queries, 31 answer cases and 22 claim–passage pairs, written on 23 November 2026
  **before any Phase H run** and never used to change prompts, thresholds, the corpus, parameters or code. Their
  SHA-256 hashes were recorded at 16:41 in `eval/heldout_hashes.json`, and the evaluation script refuses to run if a
  held-out file changes. **Caveat: the developer wrote the held-out set after seeing the corpus and the Phase C/D
  sets**, and chose the expected passages by reading the corpus. The questions are unseen by the tuning, not blind.

**Labels.** All expected passages and claim labels were written by the developer agent; a second person has not
re-checked them. **The 35 hand-checked answer sentences (section 3.8) were labelled by the developer agent after the
run, with the checker's verdicts visible, not by an independent person.** Like the held-out questions, they are an
internal check, not an independent review.

**What "supported" means.** On real answers the stage 2 checker accepted **3 of the 9 sentences** that the hand check
labelled unsupported. A sentence shown as "supported" has been *judged supported by the language model*; it has not
been verified by a person.

**No tuning.** Nothing in the engine, retrieval, answer pipeline, ingestion, corpus or parameters was changed
during Phase H. One defect was found and fixed in the *new scoring code* (section 3.8, key facts); no held-out
file was edited.

## 2. Results at a glance

| Slice | Metric | Original | Held-out |
|---|---|---|---|
| Arithmetic golden set | Figures equal to hand-computed, cited values | 189/189 (10/10 personas) | – |
| Tax-year retrieval | Right passage in top 5 (hit@5) | 0.85 (34/40) | 0.906 (29/32) |
| | Passages from the Act not in force for the year | 0 | 0 |
| Temporal traps | Right passage in top 3 | 16/16 | 11/12 |
| | Answers citing only the year's Act | 2/2 | 4/4 |
| False premise | Premise pointed out | 3/3 | **4/6** |
| Wrong jurisdiction | Declined or flagged | not tested | 8/8 |
| Out of scope | Declined | 3/3 | 2/2 |
| Contested interpretation | Notice with both readings shown | 3/3 (1 declined) | 4/4 (2 declined; see 3.6) |
| Citation verification | Checker agrees with labelled pairs | 0.976 (41/42) | 1.0 (22/22) |
| | False support on labelled pairs | 0 | 0 |
| | Citations shown that fail stage 1 | 0 | 0 |
| RAG quality | Faithfulness: sentences the checker rates supported | 0.762 (16/21) | 0.714 (25/35) |
| | Faithfulness by hand label | – | 0.743 (26/35) |
| | Checker vs hand label on real answer sentences | – | **0.80 (28/35)** |
| | Checker accepted sentences labelled unsupported | – | **3/9** |
| | Key-fact relevance | – | 0.909 (10/11 cases) |
| | Context recall (expected passage given to the model) | – | 0.706 (12/17) |
| All answer cases | Behaved as expected | 14/14 | 29/31 |

## 3. Slice by slice

### 3.1 Arithmetic golden set

All 189 hand-computed figures across P1–P10 match the engine exactly (`backend/tests/engine/personas/`). Each
expected figure cites its section and shows its working. **Not done:** the cross-check of totals against the official
e-filing tax calculator (NFR-5). The arithmetic is therefore checked against the statute as read by the developer,
not against an independent calculator.

### 3.2 Tax-year retrieval

Hit@5 is 0.85 on the original queries and 0.906 on the held-out ones; MRR 0.73 and 0.82. No query in either set
returned a passage from the Act that does not apply to the year. The held-out result is higher than the original,
which suggests the Phase C settings were not over-fitted to the 40 tuning questions; with 32 questions the
difference is within noise.

Misses (expected passage not in the top 5):

- Original: P07 (cash share and the 75 lakh limit), P08 (advance-tax timing, FY 2025-26), P10 (HUF eligibility,
  s.58(11) never found), P13 (old-regime slabs), U02 (fixed base: the Technical Explanation and Art. 14 outrank
  Art. 15(1)), U05 (substantial presence test).
- Held-out: H-T12 (Rule 128 documents: the right rule, wrong sub-rule, rank 7), H-P03 and H-P04 (deductions on top
  of presumptive income: CBDT FAQ answers outrank s.58(4) and s.44ADA(2); the FAQs may well answer the question,
  but the label asked for the statute).

The pattern is the same in both sets: long FAQ chunks and long treaty chunks outrank the shorter statutory text, and
sub-rules of one rule compete with each other. The Phase C review list (split long chunks) addresses the first.

### 3.3 Temporal traps

Old-numbering questions asked for the other year (for example "44ADA" for Tax Year 2026-27) reach the right Act in the
top 3 for 16/16 original and 11/12 held-out questions; the one held-out miss (H-T12) still returned only 1961-Act
Rules, at the wrong sub-rule. Every answer in the temporal slices cited only the year's Act (6/6). Wrong-version
rate: 0 in retrieval and in answers.

### 3.4 False premise

The original three pass. On the held-out set **4/6** pass; two fail:

- **HF04 — "My US client must withhold 30% on the work I do remotely from India. How do I get it back?"** This is the
  example in SRS/SDS §3.8. The model did not reject the premise: it repeated the 30% rule for services performed in the
  US, suggested Forms 8233 and W-8BEN, and then described Indian relief citing **s.160(2)**, which is about a
  non-resident partner's income from a country with no treaty. The correct answer is that fees for work done in India
  are not US-source (IRC s.862(a)(3)), so nothing should be withheld, and any tax withheld is refunded through
  Form 1040-NR. Retrieval did not give the model the IRC passages (context recall missed). Two sentences were
  labelled "not supported" and shown as such, but the checker rated the s.160(2) rate sentence "supported" (see 3.8).
- **HF03 — "As an IT consultant on the presumptive scheme I must get a tax audit every year. Who can do it?"** The
  answer declined ("passages do not specify who is authorised to conduct the audit") instead of saying that no audit
  is needed under s.58(2)/s.63(2). Retrieval returned s.63(1) and FAQs, not s.63(2) or s.58(3).

Both failures are a retrieval miss followed by the model answering the question as asked; the pipeline has no
separate premise check beyond the drafting prompt.

### 3.5 Wrong jurisdiction (new)

8/8 held-out questions (UK bands, California, the India-UK and India-Canada treaties, New York City, German VAT,
Singapore, Texas) were declined. All eight passed the similarity gate (0.48–0.61) and were declined by the model
saying the passages do not cover that jurisdiction, so this rests on the model, not on a rule (see CHALLENGES 16).
Out-of-scope questions were declined 3/3 and 2/2; only the two non-tax questions (a laptop, a biryani recipe) were
stopped by the similarity gate, and the off-topic tax questions (GST on restaurant food, HRA, mutual-fund gains) were
declined by the model.

### 3.6 Contested interpretation

The notice for the contested assumption (A-5, A-12, A-16) appeared in 3/3 original and 4/4 held-out cases, each with
both readings, citations and the default. A-3 is resolved, so it is not in this slice. **But the slice measures the
notice, not the answer:** HX01 ("Must I declare my Wise USD balance in Schedule FA?") and HX02 ("Which return form
should I file?") were *declined*, because retrieval returned US withholding passages instead of Rule 164 or the ITR-4
FAQs; the original Phase D case X02 ("Do I have to report my Payoneer balance as a foreign asset?") was declined the
same way. So 3 of the 7 contested questions get the right notice but no answer. HX04 answered that foreign-client income "does not prevent" ITR-4,
which states one reading of A-16 as fact; the notice beside it shows both readings, but the sentence itself overstates
(and the checker accepted it; see 3.8).

### 3.7 Citation verification

Stage 1 (the cited passage exists, is in the right Act version and was among the retrieved passages) never let a bad
citation through: 0 violations in 45 answers. Stage 2, on labelled claim–passage pairs, scored 41/42 on the original
pairs and 22/22 on the held-out pairs, with no false support on either.

### 3.8 RAG quality (own measures, not RAGAS)

RAGAS was not used: it adds langchain and a second embedding model, makes four to six long-prompt model calls per
answer (hours per run on the Groq free tier's 8,000 tokens per minute), expects a JSON format gpt-oss does not always
follow, and its scores would still need checking against our labels. Instead:

- **Faithfulness.** The share of answer sentences the stage 2 checker rates fully supported: 0.762 original, 0.714
  held-out. "Partially supported" counts as not supported.
- **Checker vs hand check on real answers.** Every one of the 35 held-out answer sentences was labelled by hand against
  its cited passage (`eval/hand_check_heldout.yaml`). The checker agreed on **28/35 (0.80)**. It accepted **3 of the 9**
  sentences labelled unsupported:
  - HF04[4]: the s.160(2) rate wording, applied to a case s.160(2) does not cover;
  - HX04[1]: "the passages impose no restriction on foreign-client income", an absence claim on a contested point;
  - HT01[0]: a correct limit plus "section 44AB was replaced by section 63", which comes from the concordance, not the
    cited passage.

  It also rejected 4 sentences labelled supported (over-strict, the safe direction). **So the checker is reliable on
  short constructed claims (0 false support on 64 pairs) but weaker on real answers, where the error is usually a
  correct quotation applied to the wrong situation.** Faithfulness by hand label is 0.743, close to the checker's
  0.714, but the two disagree on which sentences.
- **Answer relevance (key facts).** 10 of 11 held-out cases with key facts contain them (0.909). The miss is HT04: asked
  the rebate *income limit* for FY 2025-26, the answer gave the rebate *amount* (₹60,000), not the ₹12 lakh limit.
  *Scoring defect found and fixed:* the first run scored 0.636 because the model writes a narrow no-break space
  ("15 March", U+202F) and a non-breaking hyphen ("eighty‑two", U+2011); the matcher now normalises them
  (`eval_answers.normalise`, with a test). The answers and the held-out file were not changed.
- **Context recall.** For 12 of 17 cases with an expected passage, it was among the five given to the model (0.706).
  The misses (HF01, HF03, HF04, HF06, HP01) are mostly false-premise cases, where the question's wrong premise pulls
  retrieval towards the wrong passages; HF01 and HF06 still passed using equivalent FAQ passages.

## 4. Known failures and limits

1. **False premises where retrieval misses the rebutting passage** (HF03, HF04). HF04 is the SRS's own example.
2. **The stage 2 checker accepted 3 of 9 unsupported sentences in real answers**, usually a correct quotation applied
   to the wrong case. "Supported" in the interface means "judged supported by the model", not verified. Sentences are
   shown with their citation so a reader can check them.
3. **Core contested questions declined** (HX01 Schedule FA, HX02 which return form, and original X02 Payoneer) because
   retrieval favours US withholding passages; the notice shows, the answer does not.
4. **Concordance sentences** ("44AB corresponds to section 63") are judged unsupported, or wrongly supported, because
   the mapping is not in the cited passage (known since Phase D).
5. **Retrieval misses on long chunks** (FAQ answers, treaty articles, the Technical Explanation) and on HUF eligibility
   (s.58(11)).
6. **Wrong-jurisdiction and off-topic refusals depend on the model**; the similarity gate stops only clearly unrelated
   questions.
7. **Not measured:** the official e-filing calculator cross-check (NFR-5); the expense classifier on real data (Phase E
   measured it on synthetic data only); latency under load (NFR-11). An `/ask` takes one to two minutes on the free
   tier, about two minutes for the first call while BGE-M3 loads.
8. **Small sets, one labeller.** 31 held-out answer cases and 35 hand-labelled sentences; a few cases move a rate by
   several points. All labels are by one developer.

## 5. Changes made after the evaluation (not part of the measured results)

The results above are frozen: they describe the 300-chunk corpus and the code as evaluated on 23 Nov 2026. Two changes
were made afterwards, in response to the known failures. Neither was tuned on the held-out sets.

1. **Two IRS passages stating the US source rule for personal services** (IRS_PUB515:source_personal_services and
   IRS_PUB519:source_personal_services, the latter including the self-employed rule), because HF04 showed that rule was
   missing from what the model saw. The corpus is now 302 chunks. Checked on four new questions written before the fix
   was run (`backend/tests/retrieval/queries_post_evaluation.yaml`): 2 of 4 have the source rule in the top 5 (PE03
   first, PE02 fifth); PE04 ranks it 7th; PE01 ("does an American company have to deduct US tax…") still misses.
   Re-run on the original and held-out retrieval sets: unchanged (hit@5 0.85 and 0.906; temporal 16/16 and 11/12;
   no wrong-Act passage). **HF04 itself is not fixed**: re-run after the change, its retrieval and answer are the same,
   because the question's withholding wording still pulls in withholding and treaty-relief passages. A real fix would
   ground US-withholding questions in the engine's own source-rule step (step 7) instead of retrieval; that is future
   work. The answer slices were not re-run.
2. **The Ask screen now says "judged supported" instead of "supported"**, explains that the first check (the
   citation exists in the right Act) is exact while the second (support) is a language model's judgement, and links
   to the Evaluation page for the measured rates. No scoring changed.

## 6. Reproducing

```
docker compose up -d db
.venv/Scripts/python scripts/run_evaluation.py          # all slices; cached responses make re-runs free
.venv/Scripts/python scripts/run_evaluation.py --skip-llm
```

The first full run sent 88 requests to Groq (22 held-out claim pairs and 66 for the held-out answers); the original
sets were already cached from Phases C and D.
