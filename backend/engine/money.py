"""Exact rupee arithmetic. Floats are never used for money."""
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal


def D(x) -> Decimal:
    """Convert to Decimal without going through float."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        raise TypeError("money must not be a float; pass an int, str or Decimal")
    return Decimal(str(x))


def round_to_multiple(amount: Decimal, multiple: int) -> Decimal:
    """Statutory rounding (s.288A and s.288B of the 1961 Act, s.516 of the 2025 Act).

    Paise are ignored first, then the amount goes to the nearest multiple, a last
    figure of five or more rounding up. For a multiple of 10 this is the statute's rule.
    """
    rupees = int(amount.quantize(Decimal(1), rounding=ROUND_FLOOR))
    return Decimal((rupees + multiple // 2) // multiple * multiple)


def percent_of(amount: Decimal, percent) -> Decimal:
    return amount * D(percent) / Decimal(100)
