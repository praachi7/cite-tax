"""The error rates in the disclaimer (frontend/lib/disclaimer.ts) must match the stored Phase H results."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "eval" / "results" / "phase_h_summary.json"
DISCLAIMER_TS = ROOT / "frontend" / "lib" / "disclaimer.ts"


def _measured() -> dict[str, str]:
    block = re.search(r"MEASURED = \{(.*?)\};", DISCLAIMER_TS.read_text(encoding="utf8"), re.S).group(1)
    return dict(re.findall(r'(\w+): "([^"]*)"', block))


@pytest.mark.skipif(not SUMMARY.exists(), reason="run scripts/run_evaluation.py first")
def test_disclaimer_figures_match_the_evaluation_summary():
    s = json.loads(SUMMARY.read_text(encoding="utf8"))
    sl = s["slices"]
    ar, ret = sl["arithmetic"], sl["tax_year_retrieval"]["heldout"]
    fp = sl["false_premise"]["heldout"]
    hand = sl["rag_quality"]["heldout"]["judge_vs_hand_check"]
    unsupported = hand["negatives"]
    accepted = round(hand["false_support_rate"] * unsupported)
    expected = {
        "figures": f"{ar['matched']}/{ar['figures']}",
        "personas": str(ar["personas"]),
        "retrievalTop5": f"{ret['n'] - len(ret['misses_at_5'])}/{ret['n']}",
        "wrongAct": str(len(ret["wrong_act_returned"])),
        "casesAsExpected": f"{s['counts']['answer_cases_passed']['heldout']}/{s['counts']['answer_cases']['heldout']}",
        "falsePremiseMissed": f"{fp['n'] - fp['pass']}/{fp['n']}",
        "sentencesUnsupported": f"{unsupported}/{hand['n']}",
        "checkerAccepted": f"{accepted}/{unsupported}",
    }
    measured = _measured()
    assert {k: measured[k] for k in expected} == expected
