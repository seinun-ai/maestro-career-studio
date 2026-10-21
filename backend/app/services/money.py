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
- **A typed figure names its currency or none.** `parse_amount` reads "€70,000", "70.000 €",
  "150k" or "70000 EUR": a symbol or an ISO code in capitals names the currency; a bare "$" (the
  dollar of a dozen countries) names none, and the caller reads that as the home currency.

`frontend/lib/money.ts` mirrors the arithmetic for the browser.
"""

from __future__ import annotations

import re
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


# Symbols that name one currency, longest first ("US$" before "$"). A bare "$" is no currency.
_MARKS = (("US$", "USD"), ("CA$", "CAD"), ("AU$", "AUD"), ("NZ$", "NZD"), ("HK$", "HKD"),
          ("C$", "CAD"), ("A$", "AUD"), ("S$", "SGD"), ("£", "GBP"), ("€", "EUR"), ("₹", "INR"))
_FIGURE = re.compile(r"(\d[\d,.]*)\s*([kK])?")
_CODE = re.compile(r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])")
_WHOLE = re.compile(r"\s*(?:[A-Z]{0,2}\$)?\s*\d[\d,.]*\s*[kK]?\s*")


def _figure(digits: str) -> Decimal | None:
    """ "150,000" and "70.000" (dots grouping thousands, as in German and Dutch) are both whole
    numbers; "70.000,50" is too."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", digits):
        digits = digits.replace(".", "").replace(",", ".")
    try:
        return Decimal(digits.replace(",", "").rstrip("."))
    except InvalidOperation:
        return None


def _named_currency(text: str) -> str | None:
    """The one currency a typed figure names, by symbol or by ISO code; None for none or two."""
    from app.services import countries

    named: set[str] = set()
    rest = text
    for mark, code in _MARKS:
        if mark in rest:
            named.add(code)
            rest = rest.replace(mark, " ")
    named |= {c for c in _CODE.findall(text) if c in countries.currency_codes()}
    return named.pop() if len(named) == 1 else None


def parse_amount(raw: Any, *, whole: bool = False) -> tuple[Decimal | None, str | None]:
    """A pay figure as typed: its first number ("150k" is 150,000) and the currency it names.

    `whole`: the text must be the figure and nothing else (a mark or code beside it is fine), so
    "120-150k" or "150k plus equity" is no amount. A number passes through with no currency.
    """
    if isinstance(raw, bool) or raw is None:
        return None, None
    if isinstance(raw, (int, float, Decimal)):
        return _decimal(raw), None
    if not isinstance(raw, str):
        return None, None
    currency = _named_currency(raw)
    if whole:
        bare = raw
        for mark, _code in _MARKS:
            bare = bare.replace(mark, " ")
        bare = _CODE.sub(" ", bare) if currency else bare
        if not _WHOLE.fullmatch(bare):
            return None, None
    match = _FIGURE.search(raw)
    if not match:
        return None, None
    value = _figure(match.group(1))
    if value is None:
        return None, None
    return (value * 1000 if match.group(2) else value), currency
