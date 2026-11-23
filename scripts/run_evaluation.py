"""Phase H: run every evaluation slice and write eval/results/phase_h_summary.json.

Reuses the Phase C/D scripts (eval_retrieval, calibrate_judge, eval_answers) and the engine golden-set
helpers in backend/tests/engine/test_personas.py; nothing here changes engine, retrieval, answer, corpus
or params behaviour. Each slice is reported on the original labelled set and on the held-out set
(written before any Phase H run; the script refuses to run if a held-out file no longer matches the
hash recorded in eval/heldout_hashes.json).

Everything runs in one process, one slice after another, so BGE-M3 is loaded once (about 2 GB).
Model responses are cached in build/llm_cache, so re-runs send no requests.

Run from the repo root (database up, index loaded):
    .venv/Scripts/python scripts/run_evaluation.py [--skip-llm]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

RESULTS = ROOT / "eval" / "results"
SUMMARY = RESULTS / "phase_h_summary.json"
HASHES = ROOT / "eval" / "heldout_hashes.json"
HAND_CHECK = ROOT / "eval" / "hand_check_heldout.yaml"
HELDOUT = {
    "queries": ROOT / "backend" / "tests" / "retrieval" / "queries_heldout.yaml",
    "cases": ROOT / "backend" / "tests" / "answer" / "answer_cases_heldout.yaml",
    "pairs": ROOT / "backend" / "tests" / "answer" / "claim_pairs_heldout.yaml",
}


# ---------------------------------------------------------------- held-out integrity

def file_hash(path: Path) -> str:
    """SHA-256 of the file with line endings normalised, so a CRLF checkout gives the same hash."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_heldout_hashes(hashes_file: Path = HASHES) -> dict[str, str]:
    recorded = json.loads(hashes_file.read_text(encoding="utf8"))["sha256"]
    changed = [rel for rel, h in recorded.items() if file_hash(ROOT / rel) != h]
    if changed:
        raise SystemExit(f"held-out files changed after they were frozen: {changed}. "
                         "Do not edit the held-out sets; write a new set instead.")
    return recorded


# ---------------------------------------------------------------- slice 1: arithmetic golden set

def _persona_helpers():
    spec = importlib.util.spec_from_file_location(
        "persona_golden", ROOT / "backend" / "tests" / "engine" / "test_personas.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def arithmetic_slice() -> dict:
    from engine.models import TaxpayerInput
    from engine.pipeline import run

    h = _persona_helpers()
    personas, figures, matched, failures = [], 0, 0, []
    for path in h.FILES:
        fx = h._load(path)
        view = h._view(run(TaxpayerInput(**fx["input"])))
        ok = 0
        for field, exp in fx["expected"].items():
            got = h._dig(view, field)
            if h._equal(got, exp["value"]):
                ok += 1
            else:
                failures.append({"persona": fx["id"], "field": field, "got": got, "want": exp["value"]})
        figures += len(fx["expected"])
        matched += ok
        personas.append({"id": fx["id"], "title": fx.get("title", ""), "figures": len(fx["expected"]), "matched": ok})
    return {"metric": "exact match per hand-computed, cited figure", "personas": len(personas),
            "personas_all_match": sum(p["figures"] == p["matched"] for p in personas),
            "figures": figures, "matched": matched, "by_persona": personas, "failures": failures,
            "note": "Expected values are hand-computed from the statute; the official e-filing calculator "
                    "cross-check (NFR-5) has not been done."}


# ---------------------------------------------------------------- helpers

def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _slice_counts(ans: dict, name: str) -> dict:
    s = ans["by_slice"].get(name)
    return {"pass": s["pass"], "n": s["n"], "rate": _rate(s["pass"], s["n"])} if s else {"pass": 0, "n": 0, "rate": None}


def retrieval_view(res: dict) -> dict:
    from eval_retrieval import DEFAULT_CONFIG
    cfg = res["configs"][DEFAULT_CONFIG]
    misses = [{"id": q["id"], "q": q["q"], "expect": q["expect"], "top5": q["top5"]}
              for q in cfg["queries"] if q["expect"] and not (q["first_relevant_rank"] and q["first_relevant_rank"] <= 5)]
    # n = queries with an expected passage (hit@k is computed over these); out-of-scope queries have none
    return {"n": cfg["overall"]["n"], "n_queries": res["n_queries"], "overall": cfg["overall"], "by_category": cfg["by_category"],
            "wrong_act_returned": cfg["wrong_act_returned"], "misses_at_5": misses}


def faithfulness(ans: dict) -> dict:
    v = ans["sentence_verdicts"]
    total = sum(v.values())
    return {"sentences": total, "supported": v.get("supported", 0), "rate": _rate(v.get("supported", 0), total),
            "verdicts": v}


def relevance_view(ans: dict) -> dict:
    kf = [r["key_facts"] for r in ans["rows"] if r.get("key_facts") is not None]
    cr = [r["context_recall"] for r in ans["rows"] if r.get("context_recall") is not None]
    return {"key_fact_cases": len(kf), "key_fact_relevance": round(sum(kf) / len(kf), 3) if kf else None,
            "context_recall_cases": len(cr), "context_recall": _rate(sum(cr), len(cr)),
            "key_facts_missing": [{"id": r["id"], "missing": r["key_facts_missing"]}
                                  for r in ans["rows"] if r.get("key_facts_missing")],
            "context_missed": [r["id"] for r in ans["rows"] if r.get("context_recall") is False]}


def stage1_violations(ans: dict) -> list[str]:
    return [f"{r['id']}: {p}" for r in ans["rows"] for p in r["problems"]
            if "fails stage 1" in p or "other Act" in p]


def judge_view(result: dict) -> dict:
    keep = ("n", "accuracy", "macro_f1", "false_support_rate", "missed_support_rate", "confusion")
    return {**{k: result[k] for k in keep},
            "errors": [{"id": e["id"], "kind": e["kind"], "label": e["label"], "verdict": e["verdict"]}
                       for e in result["errors"]]}


def hand_check(ans_heldout: dict, path: Path = HAND_CHECK) -> dict:
    """Agreement between the stage 2 judge and hand labels on sentences from held-out answers."""
    if not path.exists():
        return {"status": "pending", "n": 0}
    import yaml
    items = yaml.safe_load(path.read_text(encoding="utf8"))["sentences"]
    rows = {r["id"]: r for r in ans_heldout["rows"]}
    checked, agree, false_support, negatives, disagreements = 0, 0, 0, 0, []
    for it in items:
        sent = rows[it["case"]]["answer"]["sentences"][it["index"]]
        judged = "supported" if sent["verdict"] == "supported" else "not_supported"
        checked += 1
        agree += judged == it["label"]
        if it["label"] == "not_supported":
            negatives += 1
            false_support += judged == "supported"
        if judged != it["label"]:
            disagreements.append({"case": it["case"], "index": it["index"], "label": it["label"],
                                  "judge": sent["verdict"], "text": sent["text"], "note": it.get("note", "")})
    return {"status": "done", "n": checked, "agreement": _rate(agree, checked),
            "false_support_rate": _rate(false_support, negatives), "negatives": negatives,
            "disagreements": disagreements, "labelled_by": "developer, against the cited chunk text"}


def corpus_size() -> dict:
    from lawdata.chunks import load_all_chunks
    from retrieval.db import connect
    on_disk = len(load_all_chunks())
    try:
        with connect() as conn:
            in_db = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    except Exception as e:  # database down: still report the corpus on disk
        in_db = f"unavailable ({type(e).__name__})"
    return {"chunks_on_disk": on_disk, "chunks_in_index": in_db}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def write(name: str, data: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf8")


# ---------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-llm", action="store_true", help="only the slices that need no model calls")
    args = ap.parse_args(argv)

    hashes = check_heldout_hashes()
    t0 = time.time()

    print("== arithmetic golden set")
    arithmetic = arithmetic_slice()
    print(f"   {arithmetic['matched']}/{arithmetic['figures']} figures, "
          f"{arithmetic['personas_all_match']}/{arithmetic['personas']} personas")

    import eval_retrieval
    print("== retrieval (default config), original then held-out")
    default_only = {eval_retrieval.DEFAULT_CONFIG: eval_retrieval.CONFIGS[eval_retrieval.DEFAULT_CONFIG]}
    ret_orig = eval_retrieval.run(eval_retrieval.QUERIES, default_only)
    ret_held = eval_retrieval.run(HELDOUT["queries"], default_only)
    write("phase_h_retrieval_original.json", ret_orig)
    write("phase_h_retrieval_heldout.json", ret_held)
    r_orig, r_held = retrieval_view(ret_orig), retrieval_view(ret_held)

    from answer.llm import DEFAULT_MODEL
    summary: dict = {
        "date": date.today().isoformat(), "git_commit": git_commit(), "model": DEFAULT_MODEL,
        "embedding_model": ret_orig["embedding_model"], "corpus": corpus_size(),
        "heldout": {"sha256": hashes, "frozen_at": json.loads(HASHES.read_text(encoding="utf8"))["frozen_at"],
                    "written_by": "the developer, after seeing the corpus and the Phase C/D sets; never used for tuning"},
        "counts": {"personas": arithmetic["personas"], "figures": arithmetic["figures"],
                   "retrieval_queries": {"original": r_orig["n"], "heldout": r_held["n"]}},
    }
    slices: dict = {
        "arithmetic": arithmetic,
        "tax_year_retrieval": {"metric": "hit@k and recall@5 with the tax-year pre-filter; wrong-Act chunks returned",
                               "original": r_orig, "heldout": r_held},
    }
    requests = {"sent": 0, "cache_hits": 0}

    if not args.skip_llm:
        from answer.llm import GroqLLM
        from calibrate_judge import PAIRS, load_pairs, run_model
        from eval_answers import CASES
        from eval_answers import run as run_answers
        from lawdata.chunks import Resolver, load_all_chunks

        resolver = Resolver(load_all_chunks())
        print("== citation verification (stage 2 judge), original then held-out")
        j_orig = run_model(DEFAULT_MODEL, load_pairs(PAIRS), resolver)
        j_held = run_model(DEFAULT_MODEL, load_pairs(HELDOUT["pairs"]), resolver)
        write("phase_h_judge_original.json", j_orig)
        write("phase_h_judge_heldout.json", j_held)
        for j in (j_orig, j_held):
            requests["sent"] += j["requests_sent"]
            requests["cache_hits"] += j["cache_hits"]
            print(f"   accuracy {j['accuracy']} false-support {j['false_support_rate']} ({j['requests_sent']} requests)")

        print("== answers, original then held-out")
        llm = GroqLLM(DEFAULT_MODEL)
        a_orig = run_answers(llm, CASES)
        a_held = run_answers(llm, HELDOUT["cases"])
        write("phase_h_answers_original.json", a_orig)
        write("phase_h_answers_heldout.json", a_held)
        requests["sent"] += llm.calls
        requests["cache_hits"] += llm.cache_hits

        both = {"original": a_orig, "heldout": a_held}
        slices["temporal_traps"] = {
            "metric": "retrieval: right Act in top 3 for old/new-number questions, wrong-Act rate; answers: cite only the year's Act",
            **{k: {"retrieval_hit@3": r["by_category"].get("temporal", {}).get("hit@3"),
                   "retrieval_n": r["by_category"].get("temporal", {}).get("n"),
                   "wrong_act_returned": len(r["wrong_act_returned"]),
                   "answers": _slice_counts(both[k], "temporal")} for k, r in (("original", r_orig), ("heldout", r_held))}}
        slices["false_premise"] = {"metric": "false premise reported (correct rejection rate)",
                                   **{k: _slice_counts(v, "false_premise") for k, v in both.items()}}
        slices["wrong_jurisdiction"] = {"metric": "declined, or the other-jurisdiction problem reported (decline rate)",
                                        "original": None, "heldout": _slice_counts(a_held, "wrong_jurisdiction"),
                                        "note": "New in Phase H; the original Phase D set had no such cases."}
        slices["out_of_scope"] = {"metric": "declined", **{k: _slice_counts(v, "out_of_scope") for k, v in both.items()}}
        slices["contested_interpretation"] = {"metric": "notice shown with both readings and citations (pass/fail)",
                                              **{k: _slice_counts(v, "contested") for k, v in both.items()}}
        slices["citation_verification"] = {
            "metric": "stage 2 judge vs hand labels (accuracy, false-support rate); stage 1 violations in answers",
            "original": {**judge_view(j_orig), "stage1_violations": stage1_violations(a_orig)},
            "heldout": {**judge_view(j_held), "stage1_violations": stage1_violations(a_held)}}
        slices["rag_quality"] = {
            "metric": "faithfulness = share of answer sentences the stage 2 judge rates supported; key-fact "
                      "relevance; context recall. RAGAS was not used (see eval/REPORT.md).",
            "original": {"faithfulness": faithfulness(a_orig), **relevance_view(a_orig)},
            "heldout": {"faithfulness": faithfulness(a_held), **relevance_view(a_held),
                        "judge_vs_hand_check": hand_check(a_held)}}
        summary["counts"].update({"claim_pairs": {"original": j_orig["n"], "heldout": j_held["n"]},
                                  "answer_cases": {"original": a_orig["cases"], "heldout": a_held["cases"]},
                                  "answer_cases_passed": {"original": a_orig["passed"], "heldout": a_held["passed"]}})
        summary["known_failures"] = (
            [{"set": k, "kind": "answer", "id": r["id"], "slice": r["slice"], "problems": r["problems"]}
             for k, v in both.items() for r in v["rows"] if not r["pass"]]
            + [{"set": k, "kind": "retrieval miss@5", "id": m["id"], "q": m["q"]}
               for k, r in (("original", r_orig), ("heldout", r_held)) for m in r["misses_at_5"]]
            + [{"set": k, "kind": "judge error", **e}
               for k, j in (("original", j_orig), ("heldout", j_held)) for e in judge_view(j)["errors"]]
            + [{"set": "heldout", "kind": "checker accepted an unsupported answer sentence", "id": f"{d['case']}[{d['index']}]",
                "problems": [d["note"] or d["text"]]}
               for d in slices["rag_quality"]["heldout"]["judge_vs_hand_check"].get("disagreements", [])
               if d["label"] == "not_supported"]
            + [{"set": k, "kind": "contested question declined (notice shown, no answer)", "id": r["id"], "slice": r["slice"],
                "problems": [r["answer"]["decline_reason"]]}
               for k, v in both.items() for r in v["rows"] if r["slice"] == "contested" and r["answer"]["status"] == "declined"])

    summary["slices"] = slices
    summary["requests"] = {**requests, "note": "Groq requests sent by this run (cached responses cost none)"}
    summary["seconds"] = round(time.time() - t0)
    write("phase_h_summary.json", summary)
    print(f"written {SUMMARY.relative_to(ROOT)}  ({summary['seconds']} s, {requests['sent']} requests sent, "
          f"{requests['cache_hits']} cached)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
