"""Phase D end-to-end check: real retrieval and the real model on the answer cases.

Checks the plan card's "done when": no citation appears without passing stage 1 (verified sentences
carry only stage-1-checked chunk IDs from the right Act); failures show as unsupported; the
contested-interpretation slice shows its notices; false premises are reported; out-of-scope is declined.
Writes eval/results/phase_d_answers.json. Model responses are cached, so re-runs are free.

Run from the repo root (database up, index loaded):
    .venv/Scripts/python scripts/eval_answers.py [model]
"""
from __future__ import annotations

import json
import sys
import time
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
    resolver = corpus_resolver()
    for s in a.sentences:
        for cid in s.chunk_ids:  # only stage-1-passed IDs are ever attached to a sentence
            chunk = resolver.resolve(cid)
            if chunk is None or not valid_for_year(chunk, case["year"]):
                problems.append(f"citation {cid} shown but fails stage 1")
            if exp.get("cite_act") and cid.split(":")[0] in OTHER_ACT[exp["cite_act"]]:
                problems.append(f"citation {cid} is from the other Act")
    return problems


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # model text contains characters the Windows console lacks
    model = argv[0] if argv else DEFAULT_MODEL
    llm = GroqLLM(model)
    cases = yaml.safe_load(CASES.read_text(encoding="utf8"))["cases"]
    rows, t0 = [], time.time()
    for c in cases:
        a = answer(c["q"], c["year"], llm)
        problems = check(c, a)
        verdicts = Counter(s.verdict for s in a.sentences)
        rows.append({"id": c["id"], "slice": c["slice"], "pass": not problems, "problems": problems,
                     "answer": a.to_dict(), "verdicts": dict(verdicts)})
        print(f"{c['id']} {c['slice']:13} {'PASS' if not problems else 'FAIL'} {a.status:18} "
              f"notices={[n.assumption_id for n in a.notices]} verdicts={dict(verdicts)} {'; '.join(problems)}")
    by_slice = {}
    for r in rows:
        s = by_slice.setdefault(r["slice"], {"pass": 0, "n": 0})
        s["n"] += 1
        s["pass"] += r["pass"]
    all_verdicts = Counter(v for r in rows for v, n in r["verdicts"].items() for _ in range(n))
    summary = {"date": date.today().isoformat(), "model": model, "cases": len(rows),
               "passed": sum(r["pass"] for r in rows), "by_slice": by_slice,
               "sentence_verdicts": dict(all_verdicts), "seconds": round(time.time() - t0),
               "requests_sent": llm.calls, "cache_hits": llm.cache_hits}
    print(json.dumps(summary, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({**summary, "rows": rows}, indent=2, ensure_ascii=False, default=str), encoding="utf8")
    print(f"written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
