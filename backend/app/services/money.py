"""Pay arithmetic: convert between currencies, make a figure yearly, take a range's middle.

Pure and `Decimal` only: no session, no network, no float. The rates come from
`fx_rates.current` (ECB daily reference rates, quoted per euro) and are passed in, so every
function here is testable on its own. The rules (D8):

- **A conversion goes through the euro and never guesses.** A currency the ECB does not quote,
  or no cache at all, gives None: the caller shows the posted amount and leaves the job out of
  comparisons. A rate is never invented or carried over from a neighbour currency.
- **A yearly figure uses the stated period.** Hour × hours per year (2080 by default, the US
  full-time figure the BLS uses; a setting under Advanced), day × 260 working days, week × 52,
  month × 12, year × 1. An unknown period is None, not a guess.
- **Missing pay stays missing.** None in, None out, everywhere.

`frontend/lib/money.ts` mirrors these rules for the browser.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

HOURS_PER_YEAR = 2080
DAYS_PER_YEAR = 260
_PER_YEAR = {"day": DAYS_PER_YEAR, "week": 52, "month": 12, "year": 1}


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _per_base(code: str, rates: Mapping[str, Any]) -> Decimal | None:
    """Units of `code` per one unit of the base currency (the euro for ECB rates)."""
    if code == str(rates.get("base") or "EUR").upper():
        return Decimal(1)
    rate = _decimal((rates.get("rates") or {}).get(code))
    return rate if rate is not None and rate > 0 else None


def convert(
    amount: Decimal | None,
    from_currency: str | None,
    to_currency: str | None,
    rates: Mapping[str, Any] | None,
) -> Decimal | None:
    """`amount` in `from_currency`, expressed in `to_currency`; None when it cannot be known.

    The same currency needs no rate. Otherwise both must be quoted in `rates`
    (`{"base": "EUR", "rates": {"USD": Decimal("1.0870"), ...}}`, values may also be text).
    """
    if amount is None or not from_currency or not to_currency:
        return None
    source, target = from_currency.strip().upper(), to_currency.strip().upper()
    if source == target:
        return amount
    if not rates:
        return None
    source_rate, target_rate = _per_base(source, rates), _per_base(target, rates)
    if source_rate is None or target_rate is None:
        return None
    return amount / source_rate * target_rate


def to_yearly(
    amount: Decimal | None, period: str | None, hours_per_year: int = HOURS_PER_YEAR
) -> Decimal | None:
    """A per-period amount as a yearly one; None for no amount or a period it does not know."""
    if amount is None or not period:
        return None
    if period == "hour":
        return amount * hours_per_year
    factor = _PER_YEAR.get(period)
    return amount * factor if factor is not None else None


def midpoint(low: Decimal | None, high: Decimal | None) -> Decimal | None:
    """The middle of a range, or the one end given; None when neither is."""
    if low is None:
        return high
    if high is None:
        return low
    return (low + high) / 2
