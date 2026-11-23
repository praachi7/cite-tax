"""Phase C step C10: measure retrieval on the labelled query set and store the results.

Runs the full hybrid and each ranked list alone (ablation), then writes
eval/results/phase_c_retrieval.json. Phase H shows these numbers in the interface.

Run from the repo root (index loaded, database up):  .venv/Scripts/python scripts/eval_retrieval.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from retrieval.db import connect  # noqa: E402
from retrieval.embedder import MODEL_NAME  # noqa: E402
from retrieval.search import retrieve  # noqa: E402

QUERIES = ROOT / "backend" / "tests" / "retrieval" / "queries.yaml"
OUT = ROOT / "eval" / "results" / "phase_c_retrieval.json"
CONFIGS = {"default (exact+dense)": ("exact", "dense"), "all three lists": ("exact", "dense", "keyword"),
           "exact_only": ("exact",), "dense_only": ("dense",), "keyword_only": ("keyword",),
           "dense+keyword": ("dense", "keyword")}


def load_queries() -> list[dict]:
    return yaml.safe_load(QUERIES.read_text(encoding="utf8"))["queries"]


def wrong_act(conn, ids: list[str], year: int) -> list[str]:
    """Returned chunks whose validity does not include the tax year (must always be empty)."""
    if not ids:
        return []
    rows = conn.execute("SELECT id, tax_year_first, tax_year_last FROM chunks WHERE id = ANY(%s)", (ids,)).fetchall()
    return [i for i, lo, hi in rows if (lo is not None and lo > year) or (hi is not None and hi < year)]


def evaluate(conn, queries: list[dict], use: tuple[str, ...]) -> dict:
    per_query, wrong = [], []
    for q in queries:
        res = retrieve(q["q"], q["year"], k=10, use=use, conn=conn)
        ids = res.ids()
        expect = q["expect"]
        first = next((i + 1 for i, cid in enumerate(ids) if cid in expect), None)
        wrong += wrong_act(conn, ids, q["year"])
        per_query.append({"id": q["id"], "category": q["category"], "year": q["year"], "q": q["q"],
                          "expect": expect, "top5": ids[:5], "first_relevant_rank": first,
                          "recall@5": (len(set(expect) & set(ids[:5])) / len(expect)) if expect else None,
                          "top_score": res.hits[0].score if res.hits else 0.0})

    def summary(rows: list[dict]) -> dict:
        rows = [r for r in rows if r["expect"]]
        n = len(rows)
        if not n:
            return {}
        hit = lambda k: sum(1 for r in rows if r["first_relevant_rank"] and r["first_relevant_rank"] <= k) / n  # noqa: E731
        return {"n": n, "hit@1": round(hit(1), 3), "hit@3": round(hit(3), 3), "hit@5": round(hit(5), 3),
                "hit@10": round(hit(10), 3),
                "recall@5": round(sum(r["recall@5"] for r in rows) / n, 3),
                "mrr": round(sum(1 / r["first_relevant_rank"] for r in rows if r["first_relevant_rank"]) / n, 3)}

    cats = sorted({q["category"] for q in queries if q["expect"]})
    return {"overall": summary(per_query), "by_category": {c: summary([r for r in per_query if r["category"] == c]) for c in cats},
            "wrong_act_returned": sorted(set(wrong)), "queries": per_query}


def main() -> int:
    queries = load_queries()
    results = {"date": date.today().isoformat(), "embedding_model": MODEL_NAME, "n_queries": len(queries), "configs": {}}
    with connect() as conn:
        for name, use in CONFIGS.items():
            t0 = time.time()
            results["configs"][name] = evaluate(conn, queries, use)
            o = results["configs"][name]
            print(f"{name:22} {o['overall']}  temporal hit@3={o['by_category']['temporal']['hit@3']}"
                  f"  wrong-Act={len(o['wrong_act_returned'])}  ({time.time() - t0:.0f} s)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf8")
    print(f"written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
