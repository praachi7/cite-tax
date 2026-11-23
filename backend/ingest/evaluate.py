"""Classifier accuracy and abstention on the labelled synthetic set.

  coverage             share of expenses the classifier committed to (did not label uncertain)
  abstention_rate      1 - coverage
  committed_accuracy   correct among committed answers: how far a committed label can be trusted
  overall_accuracy     correct among all expenses, an abstention counting as not correct
  abstained_correctly  among ambiguous and unseen rows, the share labelled uncertain (higher is better)
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Iterable

from .classifier import classify_all
from .models import Classification, ExpenseCategory
from .synthetic import PERSONAS, GeneratedSet, generate


def _ratio(n: int, d: int) -> Decimal:
    return (Decimal(n) / Decimal(d)).quantize(Decimal("0.0001")) if d else Decimal(0)


def score(gold: dict[str, ExpenseCategory], kind: dict[str, str], predictions: Iterable[Classification]) -> dict:
    preds = {p.transaction_id: p.category for p in predictions}
    if set(preds) != set(gold):
        raise ValueError("predictions and gold labels cover different expenses")
    total = len(gold)
    committed = [i for i, c in preds.items() if c is not ExpenseCategory.uncertain]
    correct = [i for i in committed if preds[i] is gold[i]]
    hard = [i for i in gold if kind.get(i) in ("ambiguous", "unseen")]
    confusion = Counter((gold[i].value, preds[i].value) for i in gold)
    by_kind = {}
    for k in sorted(set(kind.values())):
        ids = [i for i in gold if kind[i] == k]
        com = [i for i in ids if preds[i] is not ExpenseCategory.uncertain]
        by_kind[k] = {"n": len(ids), "committed": len(com),
                      "committed_correct": sum(1 for i in com if preds[i] is gold[i])}
    return {
        "n": total,
        "coverage": _ratio(len(committed), total),
        "abstention_rate": _ratio(total - len(committed), total),
        "committed_accuracy": _ratio(len(correct), len(committed)),
        "overall_accuracy": _ratio(len(correct), total),
        "abstained_correctly": _ratio(sum(1 for i in hard if preds[i] is ExpenseCategory.uncertain), len(hard)),
        "by_kind": by_kind,
        "errors": sorted(f"{g} -> {p} x{n}" for (g, p), n in confusion.items()
                         if p != g and p != ExpenseCategory.uncertain.value),
    }


def evaluate_personas(persona_ids: Iterable[str] | None = None, seed: int = 7) -> dict:
    """Score the classifier on the pooled labelled set of the given personas (default P1 to P10)."""
    gold: dict[str, ExpenseCategory] = {}
    kind: dict[str, str] = {}
    preds: list[Classification] = []
    for pid in persona_ids or PERSONAS:
        g: GeneratedSet = generate(pid, seed)
        gold.update(g.gold)
        kind.update(g.kind)
        preds.extend(classify_all(g.transactions))
    return score(gold, kind, preds)


if __name__ == "__main__":
    import json
    print(json.dumps(evaluate_personas(), indent=2, default=str))
