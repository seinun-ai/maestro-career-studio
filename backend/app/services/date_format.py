"""Best-effort reformatting of free-text resume dates.

Resume dates are free-text; anything unrecognized (including "Present" and
bare years) passes through verbatim so no data is ever mangled.
"""

from datetime import datetime
from typing import Any

_PARSE_FORMATS = ("%b %Y", "%B %Y", "%Y-%m", "%m/%Y", "%b. %Y")
_OUTPUT_FORMATS = {
    "short_month": "%b %Y",
    "long_month": "%B %Y",
    "numeric": "%m/%Y",
}


def format_date(value: Any, mode: str = "verbatim") -> str:
    if value is None:
        return ""
    text = str(value).strip()
    out_fmt = _OUTPUT_FORMATS.get(mode)
    if not text or out_fmt is None:
        return text
    for fmt in _PARSE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.strftime(out_fmt)
    return text
