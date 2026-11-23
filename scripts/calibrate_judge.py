"""Phase D: measure the stage 2 judge on the hand-labelled claim-passage pairs, per model.

Runs every pair through each candidate model (in parallel: Groq's free limits are per model), then
reports accuracy, macro-F1 and the false-support rate (a wrong sentence judged supported), which is
the error that matters most. Responses are cached, so re-runs cost no quota.

Run from the repo root:  .venv/Scripts/python scripts/calibrate_judge.py [model ...]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from answer.llm import GroqLLM  # noqa: E402
from answer.verify import judge  # noqa: E402
from lawdata.chunks import Resolver, load_all_chunks  # noqa: E402

PAIRS = ROOT / "backend" / "tests" / "answer" / "claim_pairs.yaml"
OUT = ROOT / "eval" / "results" / "phase_d_judge.json"
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def f1(tp: int, fp: int, fn: int) -> float:
    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def run_model(model: str, pairs: list[dict], resolver: Resolver) -> dict:
    llm = GroqLLM(model)
    rows, t0 = [], time.time()
    for p in pairs:
        chunk = resolver.resolve(p["chunk"])
        j = judge(llm, p["claim"], [chunk])
        predicted = "supported" if j.verdict == "supported" else "not_supported"
        rows.append({**p, "verdict": j.verdict, "predicted": predicted, "correct": predicted == p["label"],
                     "reason": j.reason})
    tp = sum(r["label"] == "supported" and r["predicted"] == "supported" for r in rows)
    tn = sum(r["label"] == "not_supported" and r["predicted"] == "not_supported" for r in rows)
    fp = sum(r["label"] == "not_supported" and r["predicted"] == "supported" for r in rows)
    fn = sum(r["label"] == "supported" and r["predicted"] == "not_supported" for r in rows)
    negatives = tn + fp
    return {"model": model, "n": len(rows), "accuracy": round((tp + tn) / len(rows), 3),
            "macro_f1": round((f1(tp, fp, fn) + f1(tn, fn, fp)) / 2, 3),
            "false_support_rate": round(fp / negatives, 3) if negatives else None,
            "missed_support_rate": round(fn / (tp + fn), 3) if tp + fn else None,
            "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "seconds": round(time.time() - t0), "requests_sent": llm.calls, "cache_hits": llm.cache_hits,
            "errors": [r for r in rows if not r["correct"]]}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # model explanations contain characters the Windows console lacks
    models = argv or MODELS
    pairs = yaml.safe_load(PAIRS.read_text(encoding="utf8"))["pairs"]
    resolver = Resolver(load_all_chunks())
    missing = [p["chunk"] for p in pairs if resolver.resolve(p["chunk"]) is None]
    if missing:
        print("pairs cite chunks that do not exist:", missing)
        return 1
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        results = list(pool.map(lambda m: run_model(m, pairs, resolver), models))
    for r in results:
        print(f"{r['model']:24} accuracy {r['accuracy']:.3f}  macro-F1 {r['macro_f1']:.3f}  "
              f"false-support {r['false_support_rate']}  missed-support {r['missed_support_rate']}  "
              f"({r['seconds']} s, {r['requests_sent']} requests, {r['cache_hits']} cached)")
        for e in r["errors"]:
            print(f"    {e['id']} [{e['kind']}] label={e['label']} verdict={e['verdict']}: {e['reason'][:110]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"date": date.today().isoformat(), "pairs": len(pairs), "results": results},
                              indent=2, ensure_ascii=False), encoding="utf8")
    print(f"written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
