# How to review the corpus (step by step)

CiteTax answers tax questions by quoting passages of the law. These passages ("chunks") were copied out of the PDFs by a program, and the program makes mistakes: words in the wrong order, missing brackets, page headers mixed into the text. Your job is to compare each chunk with the PDF, fix what is wrong, and mark it as checked.

You do **not** need Python, Docker or any coding. You need Git, VS Code and the PDFs.

---

## Part 1. One-time setup (about 20 minutes)

1. **Install Git:** https://git-scm.com/download/win. Accept all the defaults.
2. **Install VS Code:** https://code.visualstudio.com.
3. **Get the project.** Open "Git Bash" from the Start menu and type these two lines, pressing Enter after each:
   ```
   cd ~/Documents
   git clone https://github.com/praachi7/cite-tax.git
   ```
4. **Get the PDFs.** They are not on GitHub because some are too big. Ask your teammate for the `sources` folder, and put it inside the `cite-tax` folder. You should then have `Documents/cite-tax/sources/` with 28 files in it.
5. **Open the project in VS Code:** File > Open Folder > choose `Documents/cite-tax`.
6. **Make your own branch,** so your work stays separate until it is merged. In Git Bash:
   ```
   cd ~/Documents/cite-tax
   git checkout -b review-chunks
   ```

---

## Part 2. What a chunk looks like

The chunks are in the folder `corpus/chunks/`, one file per document. For example, `IT2025.yaml` holds the Income-tax Act 2025. Each chunk looks like this:

```yaml
- id: IT2025:s58(3)
  source_id: IT2025
  breadcrumb: Income-tax Act 2025 > s.58(3) > Tax Year 2026-27 onward
  heading: Special provision for computing profits and gains ...
  text: |-
    (3) Any assessee mentioned in column C of the Table in sub-section (2), who claims
    that—
    (a) the profits or gains actually earned ...
  tax_year_first: 2026
  tax_year_last: null
  authority_rank: 1
  pdf_pages:
  - 105
  - 106
  extraction: auto
  reviewed: false
```

| Field | What it means | Do you change it? |
|---|---|---|
| `id` | The name of the passage, e.g. section 58(3) of the 2025 Act | **Never** |
| `text` | The passage itself | **Yes, this is what you fix** |
| `heading` | The section's title | Fix it if it is wrong |
| `pdf_pages` | The PDF page(s) where the passage is | Fix it if it is wrong |
| `extraction` | `auto` = copied by the program. Change it to `hand_corrected` if you change the text | Yes (see below) |
| `reviewed` | `false` = not checked yet. Change it to `true` when you are done | **Yes** |
| everything else | Used by the program | **Never** |

---

## Part 3. How to review one chunk

1. In VS Code, open the chunk file (for example `corpus/chunks/IT2025.yaml`).
2. Find the chunk. Press `Ctrl+F` and type its id, for example `IT2025:s58(3)`.
3. Open the matching PDF from the `sources` folder. The table in Part 6 tells you which PDF goes with which file. Go to the page number in `pdf_pages`.
   Note: the PDF viewer's page number is the page count from the start of the file, not the number printed on the page.
4. Read the chunk's `text` next to the PDF, and look for these problems:
   - **Numbers.** These matter most: amounts (₹50 lakh, 75 lakh), percentages (50%, 5%), dates, days (90 days) and section numbers. Each one must match the PDF exactly.
   - **Words in the wrong order,** or words missing.
   - **Broken brackets,** like `a( )` or `clause ( )` where the PDF says `(a)` or `clause (b)`.
   - **Junk that is not law,** such as page headers ("THE GAZETTE OF INDIA"), page numbers, or footnotes like "Inserted by the Finance Act, 2026".
   - **The end of the passage.** It should stop where the PDF's sub-section stops. If text from the next section crept in, delete it. If a "Provided that…" sentence belongs to this sub-section but is missing, add it.
5. Fix the text by typing directly in VS Code. Keep these rules:
   - **Keep the 4 spaces at the start of every text line.** The text block only works if every line is indented the same way. VS Code shows it in the same colour when it is right.
   - Line breaks do not matter. You can join or split lines freely.
   - Use the PDF's exact wording. Do not summarise or improve it.
6. Mark it done:
   - If you changed anything in `text` or `heading`, change `extraction: auto` to `extraction: hand_corrected`.
   - Change `reviewed: false` to `reviewed: true`.
   - If something confuses you, add a line `note: ` with your question at the same indentation as `reviewed:`, for example:
     ```yaml
     note: The PDF page shows a different amount, please check.
     ```
     Then leave `reviewed: false` so your teammate sees it.
7. Save the file (`Ctrl+S`).

---

## Part 4. Save your work to GitHub (do this at the end of every session)

In Git Bash, inside the `cite-tax` folder:

```
git add corpus/chunks
git commit -m "Review IT2025 chunks"
git push -u origin review-chunks
```

The first time, Git may ask you to sign in to GitHub. A browser window opens; sign in there. After the first time, `git push` alone is enough.

Tell your teammate when you have pushed. They will check your branch and merge it.

**Never do these:** delete a whole chunk, change an `id`, or edit any file outside `corpus/chunks/`. If a chunk seems to be in the wrong place, write a `note:` instead.

---

## Part 5. The order to work in

### Step A. The 9 hand-typed tables (most important)

These are tables typed in by hand, because the program scrambled them. Check every number against the PDF. They are marked `is_table: true`.

| File | Chunk id | PDF page(s) | Extra check |
|---|---|---|---|
| IT2025.yaml | `IT2025:s58(2)/T1` | 103-104 | |
| IT2025.yaml | `IT2025:s58(2)/T2` | 104-105 | Column D (the turnover limit) looks empty. Confirm that the PDF has nothing there. |
| IT2025.yaml | `IT2025:s58(2)/T3` | 105 | The most important chunk in the project: 50 lakh, 75 lakh, 5% cash, 50% of receipts. |
| IT2025.yaml | `IT2025:s263(1)/T3` | 342-343 | The PDF shows two tables here. Confirm that the one in [square brackets] gives **31st August** for row 3. |
| IT2025.yaml | `IT2025:s63(1)/T1` | 113 | |
| FA2026.yaml | `FA2026:sch1-partIA-paraA(I)` | 106 | |
| FA2026.yaml | `FA2026:sch1-partIB-paraA(I)` | 111-112 | |
| FA2026.yaml | `FA2026:sch1-partIA-paraF/T1` | 108-110 | After the table, the PDF has a "Provided that…" paragraph about marginal relief. Type it in at the end of the text. |
| FA2026.yaml | `FA2026:sch1-partIB-paraF/T1` | 114-115 | Same as above: add the marginal-relief paragraph. |

### Step B. The 92 chunks the tax engine relies on

Search for each id with `Ctrl+F` in the file shown. Work through one file at a time, top to bottom of this list.

- **IT2025.yaml** (24): s6(1), s58(3), s58(4), s58(9), s58(11), s62(1), s62(4), s63(1), s63(2), s156(1), s156(2), s159(1), s160(1), s202(1), s202(4), s263(1), s404, s405(1), s406(1), s408(1), s408(2), s425(1), s425(3), s516
- **IT1961.yaml** (22): s6, s44AA(1), s44AB, s44AD(1), s44ADA(1), s44ADA(2), s44ADA(4), s44AE(1), s87A, s90(1), s91(1), s115BAC(1), s115BAC(1A), s139(1), s208, s209(1), s210(1), s211(1), s234B(1), s234C(1), s288A, s288B
  - This PDF is the messiest. Expect broken brackets in most chunks.
  - `s115BAC(1A)` and the nearby `s115BAC(2)` still contain `( )` with the letter missing. Fill it in from the PDF.
- **RULES2026.yaml** (13): r46(1), r76(1), r76(5), r76(6), r76(7), r76(10), r76(12), r76(15), r76(16), r136, r164(5), r164(6), r164(7)
- **RULES1962.yaml** (7): r6F(1), r12(1), r128(1), r128(4), r128(5), r128(8), r128(9)
- **CBDT_FAQ_ITR4.yaml** (4): Q1, Q5, Q6, Q16
- **Two each:** CGST.yaml (s2(6), s22(1)), DTAA_US.yaml (art15(1), art25(2)), FA2026.yaml (s2(6), s3(15)), IRS_PUB901.yaml (form8833, india), IRS_W8BEN.yaml (withholding, validity)
- **One each:** CBDT_FAQ_PRES.yaml (Q17), FORM44.yaml (p1), FORM67.yaml (p1), IRC_S861.yaml, IRC_S862.yaml, IRS_1040NR.yaml, IRS_F8233.yaml, IRS_PUB515.yaml, IRS_PUB519.yaml (spt), NOTIF385E_2001.yaml, NOTIF45_2026.yaml, NOTIF47_2026.yaml

### Step C. Everything else

Do the remaining chunks with `reviewed: false` in any order. To find them, press `Ctrl+Shift+F` (search all files) and search for `reviewed: false`.

**Leave these six long chunks to your teammate.** They need splitting, which involves the program. Check their text, but do not split them yourself:
- `DTAA_US:art12(2)`
- `IRS_PUB515:personal_services`
- `IRS_PUB519:spt_days`
- `IT1961:s139(1)`
- `IT2025:s536(2)`
- `NOTIF64_2026:p1-2`

---

## Part 6. Which PDF goes with which chunk file

| Chunk file | PDF in `sources/` |
|---|---|
| IT2025.yaml | Income_Tax_Act_2025_as_amended_by_FA_Act_2026.pdf |
| IT1961.yaml | Income_Tax_Act_1961_as_amended_by_FA_Act_2026 (1).pdf |
| RULES2026.yaml | Income-tax-Rules-2026_20-3-2026.pdf |
| RULES1962.yaml | Income-tax-Rules-1962_2026-04-01_05-44-55_6f86ac_en.pdf |
| FA2026.yaml | Finance-Act-2026.pdf |
| DTAA_US.yaml | India–US Convention (1989).pdf |
| DTAA_US_TE.yaml | IRS_India_Technical_Explanation_1989.pdf |
| CBDT_FAQ_PRES.yaml | FAQs on Tax on Presumptive Taxation Scheme.pdf |
| CBDT_FAQ_ITR4.yaml | ITR-4 (Sugam) Online FAQs.pdf |
| CGST.yaml | CGST_Act_2017_as_on_30-09-2020.pdf |
| FORM44.yaml | form-no-44.pdf |
| FORM67.yaml | itr62form67.pdf |
| NOTIF45_2026.yaml | Notification No.45_2026.pdf |
| NOTIF47_2026.yaml | Notification_No_47_2026.pdf |
| NOTIF64_2026.yaml | Notification-no-64-2026.pdf |
| NOTIF385E_2001.yaml | CBDT_Notification_385E_2001_IT_profession.txt |
| IRC_S861.yaml | US_IRC_s861_govinfo_2024_edition.pdf |
| IRC_S862.yaml | US_IRC_s862_govinfo_2024_edition.pdf |
| IRS_PUB515.yaml | IRS_Pub_515_2026.pdf |
| IRS_PUB519.yaml | IRS_Pub_519_US_Tax_Guide_for_Aliens_2025.pdf |
| IRS_PUB901.yaml | IRS_Pub_901.pdf |
| IRS_W8BEN.yaml | IRS_W-8BEN_instructions.pdf |
| IRS_F8233.yaml | IRS_Form_8233.pdf |
| IRS_1040NR.yaml | IRS_Form_1040-NR_instructions.pdf |

---

## For the developer: after a review branch is pushed

```
git fetch && git merge origin/review-chunks
.venv/Scripts/python scripts/draft_chunks.py           # keeps reviewed chunks; should report no PROBLEM lines
set PYTHONPATH=backend && python -m lawdata.validate --chunks
.venv/Scripts/python scripts/embed_chunks.py           # re-embeds only the edited chunks
.venv/Scripts/python scripts/load_index.py
.venv/Scripts/python -m pytest -q
```
