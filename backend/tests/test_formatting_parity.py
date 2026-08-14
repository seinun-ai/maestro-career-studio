"""Guard: the hand-mirrored frontend formatting defaults must not drift.

`frontend/lib/formatting.ts` reproduces the backend `ResumeFormatting` schema
defaults by hand (there is no build-time codegen). This test parses the
`FORMATTING_DEFAULTS` object out of that TS file and asserts every value equals
`ResumeFormatting().model_dump()`, so a change to one side without the other
fails CI instead of silently rendering resumes with the wrong baseline.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from app.schemas.formatting import ResumeFormatting

_FORMATTING_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "formatting.ts"
)


_VALUE_RE = re.compile(
    r"""(\w+)\s*:\s*(              # key, then one value:
          \[[^\]]*\]               #   a list literal (section_order's shape)
        | "[^"]*" | '[^']*'        #   a quoted string
        | [^,\n}]+                 #   a number / bool / null
    )""",
    re.VERBOSE,
)


def _parse_formatting_defaults(text: str) -> dict:
    """Extract the FORMATTING_DEFAULTS object literal from the TS source.

    The object is a plain JSON-ish literal (unquoted keys, trailing comma,
    numeric/string/boolean/null/list values). Normalise it to JSON and parse.

    The list branch is not hypothetical: `section_order` is a `string[] | null`,
    and the original `[^,\\n}]+` value pattern stopped at the first comma INSIDE
    the brackets, so a non-null list default would have parsed as a fragment and
    failed this test with a message about the wrong thing.
    """
    m = re.search(
        r"export const FORMATTING_DEFAULTS[^=]*=\s*(\{.*?\})\s*;",
        text,
        re.DOTALL,
    )
    assert m, "FORMATTING_DEFAULTS object literal not found in formatting.ts"
    body = m.group(1)

    out: dict = {}
    for key, raw in _VALUE_RE.findall(body):
        raw = raw.strip()
        if raw in ("true", "false"):
            out[key] = raw == "true"
        elif raw.startswith(('"', "'")):
            out[key] = ast.literal_eval(raw)
        elif raw.startswith("["):
            # ast, not json: the TS literal may use single-quoted members.
            out[key] = list(ast.literal_eval(raw))
        else:
            out[key] = json.loads(raw)
    return out


def test_frontend_defaults_match_backend_schema():
    ts_defaults = _parse_formatting_defaults(_FORMATTING_TS.read_text(encoding="utf-8"))
    schema_defaults = ResumeFormatting().model_dump()

    assert set(ts_defaults) == set(schema_defaults), (
        "FORMATTING_DEFAULTS keys drifted from ResumeFormatting schema"
    )
    for key, expected in schema_defaults.items():
        assert ts_defaults[key] == expected, (
            f"formatting.ts default for {key!r} is {ts_defaults[key]!r}, "
            f"schema says {expected!r}"
        )
