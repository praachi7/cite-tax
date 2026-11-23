"""Phase D end-to-end check: real retrieval and the real model on the answer cases.

Checks the plan card's "done when": no citation appears without passing stage 1 (verified sentences
carry only stage-1-checked chunk IDs from the right Act); failures show as unsupported; the
contested-interpretation slice shows its notices; false premises are reported; out-of-scope is declined.
Writes eval/results/phase_d_answers.json. Model responses are cached, so re-runs are free.

Phase H adds the wrong-jurisdiction slice (pass = declined, or the jurisdiction/premise problem is reported)
and two RAG-quality measures per case: key-fact relevance (share of the case's key facts found in the answer)
and context recall (an expected chunk is among the passages given to the model).

Run from the repo root (database up, index loaded):
    .venv/Scripts/python scripts/eval_answers.py [model] [--cases FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from answer.llm import DEFAULT_MODEL, GroqLLM  # noqa: E402
from answer.pipeline import answer, corpus_resolver  # noqa: E402
from answer.verify import valid_for_year  # noqa: E402

CASES = ROOT / "backend" / "tests" / "answer" / "answer_cases.yaml"
OUT = ROOT / "eval" / "results" / "phase_d_answers.json"
OTHER_ACT = {"IT2025": ("IT1961", "RULES1962"), "IT1961": ("IT2025", "RULES2026")}


def check(case: dict, a) -> list[str]:
    exp, problems = case["expect"], []
    if a.status not in exp.get("status", [a.status]):
        problems.append(f"status {a.status}, expected {exp['status']}")
    shown = {n.assumption_id for n in a.notices}
    for nid in exp.get("notices", []):
        if nid not in shown:
            problems.append(f"notice {nid} missing")
    if exp.get("premise") and not a.premise_issue:
        problems.append("false premise not reported")
    if exp.get("jurisdiction") and a.status != "declined" and not a.premise_issue:
        problems.append("other-jurisdiction question answered without saying it is out of scope")
    resolver = corpus_resolver()
    for s in a.sentences:
        for cid in s.chunk_ids:  # only stage-1-passed IDs are ever attached to a sentence
            chunk = resolver.resolve(cid)
            if chunk is None or not valid_for_year(chunk, case["year"]):
                problems.append(f"citation {cid} shown but fails stage 1")
            if exp.get("cite_act") and cid.split(":")[0] in OTHER_ACT[exp["cite_act"]]:
                problems.append(f"citation {cid} is from the other Act")
    return problems


def answer_text(a) -> str:
    return " ".join([a.premise_issue, a.decline_reason, *(s.text for s in a.sentences)])


_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")


def normalise(text: str) -> str:
    """Lower case, with the model's narrow no-break spaces (U+202F) and non-breaking hyphens (U+2011) made plain."""
    return unicodedata.normalize("NFKC", text).translate(_DASHES).lower()


def relevance(case: dict, a) -> dict:
    """Key-fact relevance and context recall; None where the case does not define them."""
    exp = case["expect"]
    groups = exp.get("key_facts") or []
    text = normalise(answer_text(a))
    found = [any(normalise(alt) in text for alt in g) for g in groups]
    wanted = exp.get("passages") or []
    return {"key_facts": round(sum(found) / len(found), 3) if found else None,
            "key_facts_missing": [g[0] for g, ok in zip(groups, found) if not ok],
            "context_recall": (any(p in a.passages for p in wanted) if wanted else None)}


def run(llm, cases_path: Path = CASES) -> dict:
    cases = yaml.safe_load(cases_path.read_text(encoding="utf8"))["cases"]
    rows, t0 = [], time.time()
    calls0, hits0 = llm.calls, llm.cache_hits
    for c in cases:
        a = answer(c["q"], c["year"], llm)
        problems = check(c, a)
        verdicts = Counter(s.verdict for s in a.sentences)
        rows.append({"id": c["id"], "slice": c["slice"], "q": c["q"], "year": c["year"], "pass": not problems,
                     "problems": problems, "answer": a.to_dict(), "verdicts": dict(verdicts), **relevance(c, a)})
        print(f"{c['id']} {c['slice']:18} {'PASS' if not problems else 'FAIL'} {a.status:18} "
              f"notices={[n.assumption_id for n in a.notices]} verdicts={dict(verdicts)} {'; '.join(problems)}")
    by_slice: dict[str, dict] = {}
    for r in rows:
        s = by_slice.setdefault(r["slice"], {"pass": 0, "n": 0})
        s["n"] += 1
        s["pass"] += r["pass"]
    all_verdicts = Counter(v for r in rows for v, n in r["verdicts"].items() for _ in range(n))
    return {"date": date.today().isoformat(), "model": llm.model, "cases_file": cases_path.name, "cases": len(rows),
            "passed": sum(r["pass"] for r in rows), "by_slice": by_slice,
            "sentence_verdicts": dict(all_verdicts), "seconds": round(time.time() - t0),
            "requests_sent": llm.calls - calls0, "cache_hits": llm.cache_hits - hits0, "rows": rows}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # model text contains characters the Windows console lacks
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", default=DEFAULT_MODEL)
    ap.add_argument("--cases", type=Path, default=CASES, help="e.g. the Phase H held-out cases")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    result = run(GroqLLM(args.model), args.cases)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf8")
    print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
