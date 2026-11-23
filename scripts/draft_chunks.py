"""Phase C step C4: draft corpus chunks from build/text/ according to corpus/scope.yaml.

Writes corpus/chunks/<SOURCE_ID>.yaml. Drafts are marked extraction: auto, reviewed: false.
Chunks a person has touched (reviewed: true, or extraction other than auto) are never
overwritten; they are kept as they are and drafts with the same id are dropped.

Run from the repo root:  .venv/Scripts/python scripts/draft_chunks.py [SOURCE_ID ...]
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lawdata.chunks import CHUNKS_DIR, Chunk, load_chunk_file  # noqa: E402
from lawdata.loader import CORPUS_DIR, load_registry  # noqa: E402
from lawdata.models import SourceEntry  # noqa: E402

TEXT_DIR = ROOT / "build" / "text"

# Lines that are page furniture, not law.
NOISE_RE = re.compile(
    r"^\s*(Income Tax Department|Ministry of Finance, Government of India|Page \d+( of \d+)?|\d{1,4}"
    r"|Publication \d+ \([\w -]+\)|Chapter \d+ [A-Z][^.]*\?)\s*$"
)
SCHEDULE_RE = re.compile(r"^\s*(THE\s+)?([A-Z]+\s+)?SCHEDULE(\s+[IVXL]+)?\s*$")
# Amendment footnotes in consolidated texts: "12. Inserted by the IT (Tenth Amdt.) Rules, 2021, ..."
FOOTNOTE_RE = re.compile(
    r"^\s*\d+\.\s+(Inserted|Substituted|Omitted|Words?|Renumbered|Re-numbered|Brackets|Figures?|"
    r"Earlier|Prior to|For the words?|The words|Clause|Sub-section|Sub-rule|Proviso|Explanation)\b"
)
SECTION_START_RE = re.compile(r"^\s{0,3}(?:\d+\[)?(?P<num>\d+[A-Z]*)\.\s+(?P<rest>\S.*)$")
SUB_RE = re.compile(r"^\s{0,3}(?:\d+\[)?\((?P<sub>\d+[A-Z]*)\)[\s(]")
FIRST_SUB_RE = re.compile(r"^\s*\((?P<sub>\d+[A-Z]*)\)[\s(]")
ARTICLE_RE = re.compile(r"^\s*ARTICLE\s+(?P<num>\d+)\s*$")
PARA_RE = re.compile(r"^\s{0,10}(?P<num>\d+)\.\s+\S")


@dataclass
class Doc:
    text: str
    lines: list[str]
    line_page: list[int]  # 1-based PDF page of each line

    @classmethod
    def load(cls, source_id: str) -> "Doc":
        text = (TEXT_DIR / f"{source_id}.txt").read_text(encoding="utf8", errors="replace")
        lines, pages, page = [], [], 1
        for raw in text.split("\n"):
            page += raw.count("\f")
            ln = raw.replace("\f", "").replace("\t", " ")
            ln = re.sub(r"\(\s+(\d)", r"(\1", ln)  # "( 1)" -> "(1)" in the 2025 Act extract
            lines.append(ln)
            pages.append(page)
        return cls(text, lines, pages)

    def pages(self, start: int, end: int) -> list[int]:
        return sorted(set(self.line_page[start:end]))


_LABEL = r"(?:[a-z]{1,4}|\d{1,2}[A-Z]{0,2})"
_EMPTY = re.compile(r"\(\s*\)")


def fix_labels(ln: str) -> str:
    """Repair the 1961 Act extract, which moves clause labels out of their brackets.

    "1( ) An individual"                         -> "(1) An individual"
    "a b ( ) all the assessees ... clause ( )"   -> "(a) all the assessees ... clause (b)"
    "b ix 24 ( ) income ... sub-clause ( ) of clause ( )" -> "(b) income ... sub-clause (ix) of clause (24)"
    Labels piled at the start of a line fill the empty brackets in order, but only when the counts match.
    """
    ln = re.sub(rf"^({_LABEL})\(\s*\)", r"(\1)", ln)
    empties = len(_EMPTY.findall(ln))
    if not empties:
        return ln
    words = ln.split(" ")
    for k in range(1, min(empties, 4) + 1):  # shortest run of leading labels that matches the empty pairs
        labels, rest = words[:k], " ".join(words[k:])
        if all(re.fullmatch(_LABEL, w) for w in labels) and len(_EMPTY.findall(rest)) == k:
            for lab in labels:
                rest = _EMPTY.sub(f"({lab})", rest, count=1)
            return rest
    return ln


C1_MAP = str.maketrans({"\x91": "‘", "\x92": "’", "\x93": "“", "\x94": "”", "\x96": "–", "\x97": "—"})


def clean(lines: list[str]) -> str:
    out = []
    for ln in lines:
        if not ln.strip() or NOISE_RE.match(ln) or FOOTNOTE_RE.match(ln):
            continue
        ln = ln.strip().translate(C1_MAP).replace("`", "₹")  # the 2025 Act's rupee glyph extracts as a backtick
        ln = fix_labels(ln)
        out.append(re.sub(r"\s+", " ", ln))
    return "\n".join(out).strip()


def num_key(num: str) -> tuple[int, str]:
    m = re.match(r"(\d+)(.*)", num)
    return (int(m.group(1)), m.group(2)) if m else (0, num)


def heading_before(lines: list[str], idx: int) -> tuple[str, int]:
    """The margin heading sits on the 1-3 lines right above a section start."""
    got: list[str] = []
    i = idx - 1
    while i >= 0 and len(got) < 3:
        ln = lines[i].strip()
        if not ln:
            if got:
                break
            i -= 1
            continue
        if ln[0] in "(“\"" or ln.startswith(("Provided", "Explanation")) or ln.endswith((":", ";", ",")):
            break
        got.insert(0, ln)
        i -= 1
        if not re.sub(r"^\d+\[", "", ln)[:1].islower():
            break  # reached the first line of the heading
    if got and re.sub(r"^\d+\[", "", got[0])[:1].islower():
        got = []  # never found the heading's first line: this is body text, not a heading
    heading = re.sub(r"\s+", " ", " ".join(got)).strip()
    heading = re.sub(r"^\d+\[", "", heading).rstrip(".")
    return heading, (i + 1 if got else idx)


AMEND_RE = re.compile(r"\b(inserted|substituted|omitted|renumbered)\s+by\b|\bw\.e\.f\.", re.I)


def is_body_start(rest: str) -> bool:
    if FOOTNOTE_RE.match("1. " + rest) or AMEND_RE.search(rest):
        return False
    return rest.startswith("(1)") or rest[:1].isupper() or rest[:1] in "“\""


# ---------------------------------------------------------------- statute mode

def find_section(doc: Doc, num: str) -> tuple[int, int] | None:
    starts = []
    for i, ln in enumerate(doc.lines):
        m = SECTION_START_RE.match(ln)
        if m and is_body_start(m.group("rest")):
            starts.append((i, m.group("num")))
    # A real section has a margin heading above it; numbered table rows ("6. Above Rs ...") do not.
    def has_heading(i: int) -> bool:
        h, _ = heading_before(doc.lines, i)
        return bool(h) and not h[0].isdigit()

    candidates = [pos for pos, (i, n) in enumerate(starts) if n == num]
    with_heading = [pos for pos in candidates if has_heading(starts[pos][0])]
    # Sections come before the Schedules, which reuse the same numbers: take the first headed match.
    best = None
    for pos in with_heading[:1] or candidates:
        i, n = starts[pos]
        end = len(doc.lines)
        for j, n2 in starts[pos + 1:]:
            if n2 != num and num_key(n2) > num_key(num):
                end = j
                break
        if best is None or end - i > best[1] - best[0]:
            best = (i, end)
    if best is None:
        return None
    i, end = best
    for j in range(i + 1, end):  # the last section must not run on into the Schedules
        if SCHEDULE_RE.match(doc.lines[j]):
            end = j
            break
    if end < len(doc.lines):
        _, end = heading_before(doc.lines, end)
    return i, end


def split_subsections(doc: Doc, start: int, end: int) -> list[tuple[str | None, int, int]]:
    first = SECTION_START_RE.match(doc.lines[start]).group("rest")
    m = FIRST_SUB_RE.match(first)
    if not m:
        return [(None, start, end)]
    parts = [(m.group("sub"), start)]
    for i in range(start + 1, end):
        sm = SUB_RE.match(doc.lines[i])
        if sm and num_key(sm.group("sub")) > num_key(parts[-1][0]):
            parts.append((sm.group("sub"), i))
    return [(sub, s, parts[k + 1][1] if k + 1 < len(parts) else end) for k, (sub, s) in enumerate(parts)]


def draft_statute(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    label = cfg["label"]
    only = {str(k): [str(x) for x in v] for k, v in (cfg.get("only") or {}).items()}
    for num in cfg["units"]:
        span = find_section(doc, num)
        if span is None:
            problems.append(f"{src.id}: {label}.{num} not found")
            continue
        start, end = span
        heading, _ = heading_before(doc.lines, start)
        subs = split_subsections(doc, start, end)
        keep = only.get(num)
        found = set()
        for sub, s, e in subs:
            if keep is not None and sub not in keep:
                continue
            found.add(sub)
            ref = f"{label}{num}" + (f"({sub})" if sub else "")
            pretty = f"{label}.{num}" + (f"({sub})" if sub else "")
            out.append(make(src, cfg, f"{src.cite_prefix}:{ref}", pretty, heading, clean(doc.lines[s:e]), doc.pages(s, e)))
        if keep:
            for k in keep:
                if k not in found:
                    problems.append(f"{src.id}: {label}.{num}({k}) not found")
    return out, problems


# ---------------------------------------------------------------- article mode

def draft_article(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    heads = [(i, ARTICLE_RE.match(ln).group("num")) for i, ln in enumerate(doc.lines) if ARTICLE_RE.match(ln)]
    for num in cfg["units"]:
        cands = []
        for k, (i, n) in enumerate(heads):
            if n == num:
                end = heads[k + 1][0] if k + 1 < len(heads) else len(doc.lines)
                cands.append((end - i, i, end))
        if not cands:
            problems.append(f"{src.id}: Article {num} not found")
            continue
        _, start, end = max(cands)
        j = start + 1
        while j < end and not doc.lines[j].strip():
            j += 1
        heading = doc.lines[j].strip() if j < end else ""
        paras: list[tuple[str, int]] = []
        for i in range(j + 1, end):
            m = PARA_RE.match(doc.lines[i])
            if m and int(m.group("num")) == len(paras) + 1:
                paras.append((m.group("num"), i))
        if not paras:
            out.append(make(src, cfg, f"{src.cite_prefix}:art{num}", f"Art. {num}", heading, clean(doc.lines[j + 1:end]), doc.pages(start, end)))
            continue
        for k, (p, s) in enumerate(paras):
            e = paras[k + 1][1] if k + 1 < len(paras) else end
            out.append(make(src, cfg, f"{src.cite_prefix}:art{num}({p})", f"Art. {num}({p})", heading, clean(doc.lines[s:e]), doc.pages(s, e)))
    return out, problems


# ---------------------------------------------------------------- faq, anchor, whole

def draft_faq(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    q_re = re.compile(cfg["q_regex"])
    starts: list[tuple[str, int]] = []
    for i, ln in enumerate(doc.lines):
        m = q_re.match(ln.strip())
        if m and int(m.group(1)) == len(starts) + 1:
            starts.append((m.group(1), i))
    wanted = {str(x) for x in cfg.get("units") or []}
    out = []
    for k, (q, s) in enumerate(starts):
        if wanted and q not in wanted:
            continue
        e = starts[k + 1][1] if k + 1 < len(starts) else len(doc.lines)
        body = clean(doc.lines[s:e])
        question = body.split("\n")[0]
        out.append(make(src, cfg, f"{src.cite_prefix}:Q{q}", f"Q{q}", question, body, doc.pages(s, e)))
    return out, ([] if starts else [f"{src.id}: no questions matched {cfg['q_regex']!r}"])


def draft_anchor(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    for unit in cfg["units"]:
        s_re = re.compile(unit["start"])
        e_re = re.compile(unit["end"]) if unit.get("end") else None
        skip = unit.get("occurrence", 1)
        start = None
        for i, ln in enumerate(doc.lines):
            if s_re.search(ln):
                skip -= 1
                if skip == 0:
                    start = i
                    break
        if start is None:
            problems.append(f"{src.id}: start of {unit['id']} not found")
            continue
        end = len(doc.lines)
        if e_re:
            for i in range(start + 1, len(doc.lines)):
                if e_re.search(doc.lines[i]):
                    end = i
                    break
            else:
                problems.append(f"{src.id}: end of {unit['id']} not found")
        cid = unit["id"] if ":" in unit["id"] else f"{src.cite_prefix}:{unit['id']}"
        row = make(src, cfg, cid, unit.get("label", cid.split(":", 1)[1]), unit["heading"], clean(doc.lines[start:end]), doc.pages(start, end))
        for key in ("tax_year_first", "tax_year_last"):
            if key in unit:  # per-passage override, e.g. FA2026 s.2 (1961 Act year) vs s.3 (2025 Act year)
                row[key] = unit[key]
        if "years" in unit:
            row["breadcrumb"] = " > ".join([cfg["breadcrumb"], row["breadcrumb"].split(" > ")[1], unit["years"]])
        out.append(row)
    return out, problems


def draft_whole(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    return [make(src, cfg, cfg["id"], "whole document", cfg.get("heading"), clean(doc.lines), doc.pages(0, len(doc.lines)))], []


def draft_pages(src: SourceEntry, cfg: dict, doc: Doc) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    for unit in cfg["units"]:
        first, last = unit["pages"]
        idx = [i for i, p in enumerate(doc.line_page) if first <= p <= last]
        if not idx:
            problems.append(f"{src.id}: pages {first}-{last} not found")
            continue
        s, e = idx[0], idx[-1] + 1
        cid = unit["id"] if ":" in unit["id"] else f"{src.cite_prefix}:{unit['id']}"
        label = f"p.{first}" if first == last else f"pp.{first}-{last}"
        out.append(make(src, cfg, cid, label, unit["heading"], clean(doc.lines[s:e]), doc.pages(s, e)))
    return out, problems


MODES = {"pages": draft_pages,"statute": draft_statute, "article": draft_article, "faq": draft_faq, "anchor": draft_anchor, "whole": draft_whole}


# ---------------------------------------------------------------- output

def year_label(src: SourceEntry) -> str | None:
    f, l = src.tax_year_first, src.tax_year_last
    fy = lambda y: f"{y}-{(y + 1) % 100:02d}"  # noqa: E731
    if f is None and l is None:
        return None
    if f is None:
        return f"FY {fy(l)} and earlier"
    if l is None:
        return f"Tax Year {fy(f)} onward"
    return f"FY {fy(f)}" if f == l else f"FY {fy(f)} to {fy(l)}"


def make(src: SourceEntry, cfg: dict, cid: str, pretty: str, heading: str | None, text: str, pages: list[int]) -> dict:
    crumbs = [cfg["breadcrumb"], pretty]
    yl = year_label(src)
    if yl:
        crumbs.append(yl)
    return {
        "id": cid,
        "source_id": src.id,
        "breadcrumb": " > ".join(crumbs),
        "heading": heading or None,
        "text": text,
        "tax_year_first": src.tax_year_first,
        "tax_year_last": src.tax_year_last,
        "authority_rank": src.authority_rank,
        "pdf_pages": pages,
        "extraction": "auto",
        "reviewed": False,
    }


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def write(src: SourceEntry, drafts: list[dict]) -> tuple[int, int]:
    path = CHUNKS_DIR / f"{src.id}.yaml"
    kept: list[Chunk] = []
    if path.exists():
        kept = [c for c in load_chunk_file(path) if c.reviewed or c.extraction.value != "auto"]
    kept_ids = {c.id for c in kept}
    fresh = [d for d in drafts if d["id"] not in kept_ids]
    for d in fresh:
        Chunk(**d)  # validate
    rows = [c.model_dump(mode="json", exclude_defaults=True) for c in kept] + fresh
    order = {d["id"]: k for k, d in enumerate(drafts)}
    rows.sort(key=lambda r: order.get(r["id"], len(order)))
    header = (
        f"# Corpus chunks for {src.id}: {src.title}\n"
        "# Drafted by scripts/draft_chunks.py from corpus/scope.yaml. Review each chunk against the PDF,\n"
        "# fix the text, then set reviewed: true (and extraction: hand_corrected if you changed it).\n"
        "# Reviewed or hand-made chunks are never overwritten by the drafter.\n"
    )
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf8", newline="\n") as fh:
        fh.write(header)
        yaml.dump({"chunks": rows}, fh, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10_000)
    return len(fresh), len(kept)


def main(argv: list[str]) -> int:
    scope = yaml.safe_load((CORPUS_DIR / "scope.yaml").read_text(encoding="utf8"))["sources"]
    registry = {s.id: s for s in load_registry()}
    wanted = set(argv)
    all_problems = []
    for sid, cfg in scope.items():
        if wanted and sid not in wanted:
            continue
        src = registry[sid]
        drafts, problems = MODES[cfg["mode"]](src, cfg, Doc.load(sid))
        long = [d["id"] for d in drafts if len(d["text"]) > 6000]
        new, kept = write(src, drafts)
        print(f"{sid:16} drafted {new:3}  kept {kept:3}" + (f"  long: {', '.join(long)}" if long else ""))
        all_problems += problems
    for p in all_problems:
        print("PROBLEM", p)
    return 1 if all_problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
