"""Scoped placeholder ratchet.

A placeholder may be an example prefixed ``e.g.`` (a following space or a
newline, so the persona block's ``e.g.\\n`` still counts), or exactly the URL
format cue ``https://…``. An ellipsis prompt is allowed only when the file and
the exact string are on the search / composer / chip-add-row list. Anything
else fails. ``SelectValue`` and image ``placeholder`` props are not inputs.

Values are the attribute or object-key expressions themselves: string
literals, template literals, ternaries, ``??`` and ``||`` (both sides), the
right side of ``&&``, ``as`` casts, ``.join()`` constants, and identifiers
bound to those in the same file. A file that merely contains ``e.g.``
somewhere does not pass.

The scan fails closed. An expression it cannot resolve to strings (a
concatenation, a member access, a call, a prop filled in by another file)
fails unless the file and the exact expression are on the pass-through list.
Those are components that hand a caller's value on; each caller's own
``placeholder`` is a site the scan reads.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ROOTS = ("app", "components", "lib")
_SKIP_TAGS = frozenset({"SelectValue", "PreviewThumbnail"})
_ELLIPSIS = "…"
_URL_CUE = "https://" + _ELLIPSIS
_QUOTES = "\"'`"

# Exact prompts, not whole files. profile-panel.tsx is a chip add-row caller
# and also had a statement placeholder; a file-wide allow would let that
# statement back in.
_PROMPTS = frozenset(
    {
        ("app/applications/page.tsx", "Search company or role" + _ELLIPSIS),
        ("components/role-picker.tsx", "Search roles, or type your own" + _ELLIPSIS),
        ("components/career/merge-entity-dialog.tsx", "Search by title" + _ELLIPSIS),
        ("components/chat/chat-page.tsx", "Ask about your resume" + _ELLIPSIS),
        ("components/ui/chip-input.tsx", "Add" + _ELLIPSIS),
        ("components/career/profile-panel.tsx", "Add skills" + _ELLIPSIS),
        ("components/resume-editor/skills-editor.tsx", "Add skill" + _ELLIPSIS),
        ("components/resume-editor/editor-body.tsx", "Add certification" + _ELLIPSIS),
        (
            "components/resume-editor/tailored-resume-studio.tsx",
            "Add certification" + _ELLIPSIS,
        ),
        ("components/resume-editor/education-editor.tsx", "Add course" + _ELLIPSIS),
    }
)

# The only expressions allowed to stay unresolved: values handed on from a
# caller (whose own site is scanned) and the image placeholder's type line.
_PASS_THROUGH = frozenset(
    {
        ("components/resume-editor/field.tsx", "placeholder"),
        ("components/resume-editor/contact-form.tsx", "placeholder"),
        ("components/settings/autofill-section.tsx", "field.placeholder"),
        ("components/role-picker.tsx", "props.placeholder"),
        ("components/gallery/preview-thumbnail.tsx", "string"),
    }
)

_NOT_INPUTS = (
    "None",
    "—",
    "Choose a base resume",
    "Choose base resume",
    "Not rendered yet",
    "Not validated",
)

# Indirect values the scanner must actually read, not a substring search.
_MUST_SEE = (
    ("components/settings/persona-section.tsx", "e.g.\nVision:"),
    ("components/ui/chip-input.tsx", "Add" + _ELLIPSIS),
    ("components/settings/autofill-section.tsx", "e.g. Apt 4B"),
    ("components/resume-editor/contact-form.tsx", "e.g. you@example.com"),
    ("components/settings/models-section.tsx", "e.g. sk-..."),
    ("components/settings/models-section.tsx", "e.g. AIza..."),
    (
        "components/gap-analysis/gap-card.tsx",
        "e.g. Data scientist who ships forecasting models to production",
    ),
    ("components/role-picker.tsx", "Search roles, or type your own" + _ELLIPSIS),
)

_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_TAG_NAME = re.compile(r"[A-Za-z_$][\w.$]*")
# `placeholder?:` is a type member, not a value.
_SITE = re.compile(r"(?<![\w$])placeholder\s*(\?:|=(?![=>])|:)")
_NO_VALUE = frozenset({"undefined", "null", "true", "false"})

# (line, value, expression); value is None when the expression did not resolve.
Found = tuple[int, str | None, str]


def _line_of(src: str, index: int) -> int:
    return src.count("\n", 0, index) + 1


def _skip_ws(src: str, i: int) -> int:
    while i < len(src) and src[i].isspace():
        i += 1
    return i


def _decode_escapes(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] != "\\" or i + 1 >= len(raw):
            out.append(raw[i])
            i += 1
            continue
        nxt = raw[i + 1]
        mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "`": "`"}
        if nxt == "u" and i + 5 < len(raw):
            hex_digits = raw[i + 2 : i + 6]
            if re.fullmatch(r"[0-9a-fA-F]{4}", hex_digits):
                out.append(chr(int(hex_digits, 16)))
                i += 6
                continue
        out.append(mapping.get(nxt, nxt))
        i += 2
    return "".join(out)


def _read_quoted(src: str, i: int) -> tuple[str, int]:
    """Decoded text (a template keeps its `${…}` verbatim) and the index after the closer."""
    quote = src[i]
    i += 1
    raw: list[str] = []
    while i < len(src):
        if quote == "`" and src.startswith("${", i):
            end = _match_brace(src, i + 1)
            raw.append(src[i:end])
            i = end
            continue
        if src[i] == "\\":
            raw.append(src[i : i + 2])
            i += 2
            continue
        if src[i] == quote:
            return _decode_escapes("".join(raw)), i + 1
        raw.append(src[i])
        i += 1
    return _decode_escapes("".join(raw)), i


def _skip_string_or_comment(src: str, i: int) -> int | None:
    if src.startswith("//", i):
        nxt = src.find("\n", i)
        return len(src) if nxt < 0 else nxt
    if src.startswith("/*", i):
        nxt = src.find("*/", i + 2)
        return len(src) if nxt < 0 else nxt + 2
    if src[i] in _QUOTES:
        return _read_quoted(src, i)[1]
    return None


def _top_level(expr: str) -> Iterator[tuple[int, int]]:
    """(index, bracket depth after it) for every character outside strings and comments."""
    depth = 0
    i = 0
    while i < len(expr):
        skipped = _skip_string_or_comment(expr, i)
        if skipped is not None:
            i = skipped
            continue
        depth += (expr[i] in "([{") - (expr[i] in ")]}")
        yield i, depth
        i += 1


def _match_brace(src: str, open_at: int) -> int:
    """Index after the `}` matching the `{` at open_at."""
    tail = src[open_at:]
    return open_at + 1 + next((j for j, depth in _top_level(tail) if depth == 0), len(tail) - 1)


def _expr_end(src: str, start: int) -> int:
    """Index of the top-level `,` or `;` ending the expression at start, or of the bracket closing around it."""
    tail = src[start:]
    ends = (j for j, depth in _top_level(tail) if depth < 0 or (depth == 0 and tail[j] in ",;"))
    return start + next(ends, len(tail))


def _find_op(expr: str, op: str) -> int | None:
    return next((i for i, depth in _top_level(expr) if depth == 0 and expr.startswith(op, i)), None)


def _wrapped(expr: str) -> bool:
    """True when a leading `(` closes at the very end."""
    closes = (i for i, depth in _top_level(expr) if depth == 0)
    return expr.startswith("(") and next(closes, -1) == len(expr) - 1


def _not_conditional(expr: str, i: int) -> bool:
    """`?.` and `??` are not the conditional operator."""
    return expr[i] == "?" and (expr.startswith(("?.", "??"), i) or expr[i - 1 : i] == "?")


def _split_ternary(expr: str) -> tuple[str, str, str] | None:
    open_q: list[int] = []
    for i, depth in _top_level(expr):
        if depth or expr[i] not in "?:" or _not_conditional(expr, i):
            continue
        if expr[i] == "?":
            open_q.append(i)
        elif open_q:
            q_at = open_q.pop()
            if not open_q:
                return expr[:q_at], expr[q_at + 1 : i], expr[i + 1 :]
    return None


# Binary operators and which operands can be the value: `x as T` keeps x,
# `a && b` keeps b, `??` and `||` keep both.
_VALUE_OPS = (("??", "both"), ("||", "both"), ("&&", "right"), (" as ", "left"))


def _operands(expr: str) -> list[tuple[int, str]] | None:
    """(offset, sub-expression) pairs whose values are expr's values, or None for a leaf."""
    if _wrapped(expr):
        return [(1, expr[1:-1])]
    tern = _split_ternary(expr)
    if tern is not None:
        cond, then, else_ = tern
        return [(len(cond) + 1, then), (len(cond) + len(then) + 2, else_)]
    for op, keep in _VALUE_OPS:
        at = _find_op(expr, op)
        if at is not None:
            left, right = (0, expr[:at]), (at + len(op), expr[at + len(op) :])
            return {"both": [left, right], "left": [left], "right": [right]}[keep]
    return None


def _try_join(expr: str) -> str | None:
    match = re.fullmatch(
        r"\[(.*)\]\s*\.join\(\s*(['\"])(.*)\2\s*\)",
        expr.strip(),
        re.S,
    )
    if not match:
        return None
    parts = re.findall(r"(['\"])((?:\\.|(?!\1).)*)\1", match.group(1))
    if not parts:
        return None
    sep = _decode_escapes(match.group(3))
    return sep.join(_decode_escapes(part) for _q, part in parts)


def _literal(expr: str) -> str | None:
    if expr[0] in _QUOTES:
        text, end = _read_quoted(expr, 0)
        if end == len(expr):
            return text
    return _try_join(expr)


class _Tags:
    """The JSX tag the scan is inside: set between `<Name` and its `>`.

    `{…}` attribute values nest, and a `>` inside one (an arrow) does not
    close the tag.
    """

    def __init__(self) -> None:
        self.name: str | None = None
        self.depth = 0

    def step(self, src: str, i: int) -> int | None:
        """Index after a tag boundary or attribute brace at i; None when there is none."""
        ch = src[i]
        if self.depth or (self.name is not None and ch == "{"):
            self.depth += (ch == "{") - (ch == "}")
            return i + 1 if ch in "{}" else None
        if self.name is None:
            return self._open(src, i)
        if ch != ">":
            return None
        self.name = None
        return i + 1

    def _open(self, src: str, i: int) -> int | None:
        if src[i] != "<":
            return None
        match = _TAG_NAME.match(src, i + 1)
        if match:
            self.name = match.group()
            return match.end()
        return i + 2 if src.startswith("</", i) else None


def _site_at(src: str, i: int) -> tuple[int, int | None]:
    """(where to resume, index of the value) for a placeholder site at i; the value index is None when there is none."""
    match = _SITE.match(src, i)
    if not match:
        return i + 1, None
    return match.end(), None if match.group(1) == "?:" else match.end()


class _Scan:
    def __init__(self, src: str) -> None:
        self.src = src
        self.resolving: set[str] = set()
        self.sites = self._find_sites()
        # `placeholder="x"` on a tag is a use, not a binding of the identifier.
        self.jsx_values = {at for at, tag in self.sites if tag is not None}

    def _find_sites(self) -> list[tuple[int, str | None]]:
        """(index of the value, enclosing JSX tag or None)."""
        found: list[tuple[int, str | None]] = []
        tags = _Tags()
        i = 0
        while i < len(self.src):
            nxt = _skip_string_or_comment(self.src, i)
            if nxt is None:
                nxt = tags.step(self.src, i)
            if nxt is None:
                nxt, value_at = _site_at(self.src, i)
                if value_at is not None:
                    found.append((value_at, tags.name))
            i = nxt
        return found

    def values_at(self, value_at: int) -> list[Found]:
        src = self.src
        i = _skip_ws(src, value_at)
        if src[i : i + 1] == "{":
            return self._strings(src[i + 1 : _match_brace(src, i) - 1], i + 1)
        end = _read_quoted(src, i)[1] if i < len(src) and src[i] in _QUOTES else _expr_end(src, i)
        return self._strings(src[i:end], i)

    def _strings(self, expr: str, base: int) -> list[Found]:
        stripped = expr.strip()
        if not stripped:
            return []
        at = base + expr.find(stripped)
        parts = _operands(stripped)
        if parts is not None:
            return [found for off, part in parts for found in self._strings(part, at + off)]
        text = _literal(stripped)
        if text is None and _IDENT.fullmatch(stripped):
            return self._identifier(stripped, at)
        return [(_line_of(self.src, at), text, stripped)]

    def _identifier(self, name: str, at: int) -> list[Found]:
        if name in _NO_VALUE or name in self.resolving:
            return []
        self.resolving.add(name)
        found = [hit for value_at in self._bindings(name) for hit in self.values_at(value_at)]
        self.resolving.discard(name)
        return found or [(_line_of(self.src, at), None, name)]

    def _bindings(self, name: str) -> Iterator[int]:
        """Value indexes of `name = …`: declarations, defaults, and same-file props."""
        for match in re.finditer(rf"(?<![\w$.]){re.escape(name)}\s*=(?![=>])", self.src):
            value_at = _skip_ws(self.src, match.end())
            # `{` is a JSX expression attribute, an object or a destructure.
            if match.end() not in self.jsx_values and self.src[value_at : value_at + 1] != "{":
                yield match.end()


def _allowed(value: str) -> bool:
    return value in ("", _URL_CUE) or re.match(r"e\.g\.(\s|$)", value) is not None


def _sources() -> Iterator[tuple[str, str]]:
    for root in _ROOTS:
        for path in sorted((_FRONTEND / root).rglob("*")):
            if path.suffix in {".ts", ".tsx"} and ".test." not in path.name:
                yield path.relative_to(_FRONTEND).as_posix(), path.read_text()


def collect() -> list[tuple[str, int, str | None, str]]:
    """(file, line, value or None when unresolved, expression) for every input placeholder."""
    found: list[tuple[str, int, str | None, str]] = []
    for rel, src in _sources():
        scan = _Scan(src)
        for value_at, tag in scan.sites:
            if tag not in _SKIP_TAGS:
                found.extend((rel, *hit) for hit in scan.values_at(value_at))
    return found


def _passes(rel: str, value: str | None, expr: str) -> bool:
    if value is None:
        return (rel, expr) in _PASS_THROUGH
    return _allowed(value) or ((rel, value) in _PROMPTS and value.endswith(_ELLIPSIS))


def violations() -> list[str]:
    return [
        f"{rel}:{line}: " + (repr(value) if value is not None else f"unresolved {expr!r}")
        for rel, line, value, expr in collect()
        if not _passes(rel, value, expr)
    ]


def _seen() -> set[tuple[str, str | None]]:
    return {(rel, value) for rel, _line, value, _expr in collect()}


def test_placeholders_are_examples_or_named_prompts():
    bad = violations()
    assert not bad, "placeholder is not an example or a named prompt:\n" + "\n".join(bad)


def test_scanner_reads_indirect_placeholder_values():
    """Object fields, defaults, ternaries and joined constants, not just placeholder=\"...\"."""
    seen = _seen()
    missing = [
        f"{rel} :: {prefix!r}"
        for rel, prefix in _MUST_SEE
        if not any(path == rel and (value or "").startswith(prefix) for path, value in seen)
    ]
    assert not missing, "scanner missed:\n" + "\n".join(missing)


def test_select_and_image_placeholders_are_not_inputs():
    values = {value for _rel, value in _seen()}
    leaked = [text for text in _NOT_INPUTS if text in values]
    assert not leaked, leaked


def test_named_prompts_are_the_ones_on_screen():
    missing = sorted(f"{rel} :: {value}" for rel, value in _PROMPTS - _seen())
    assert not missing, missing


def test_pass_through_list_is_current():
    unresolved = {(rel, expr) for rel, _line, value, expr in collect() if value is None}
    stale = sorted(f"{rel} :: {expr}" for rel, expr in _PASS_THROUGH - unresolved)
    assert not stale, stale




def test_conventions_record_the_govuk_deviation():
    doc = (
        Path(__file__).resolve().parents[2] / "docs/frontend-conventions.md"
    ).read_text()
    assert re.search(r"a placeholder may hold only an\s+example value", doc)
    assert re.search(r"Exceptions: a short `…` prompt", doc)
    assert "fails closed" in doc
    assert "prefixed `e.g.`" in doc
    assert "This deviates from GOV.UK on purpose" in doc
    assert "`--muted-foreground`" in doc


def _src(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _order(src: str, *needles: str) -> None:
    at = 0
    for needle in needles:
        found = src.find(needle, at)
        assert found >= 0, needle
        at = found + len(needle)


def test_locations_hint_is_between_the_label_and_the_field():
    src = _src("components/settings/job-preferences-section.tsx")
    _order(
        src,
        'htmlFor="job-preferences-locations"',
        'id="job-preferences-locations-hint"',
        "One location per line.",
        'aria-describedby="job-preferences-locations-hint"',
        'id="job-preferences-locations"',
    )


def test_tracking_url_hint_is_between_the_label_and_the_field():
    src = _src("components/job-tracking-url-field.tsx")
    _order(
        src,
        "<Label",
        "id={`${id}-hint`}",
        "{description}",
        "<Input",
        "aria-describedby={description ? `${id}-hint` : undefined}",
    )


def test_question_constraint_is_a_hint():
    src = _src("components/qa-tab.tsx")
    assert "One question per line" + _ELLIPSIS not in src
    # The hint already says one per line; the name need not say it again.
    assert 'aria-label="Questions to ask"' in src
    _order(
        src,
        "One question per line.",
        "aria-describedby={questionsHintId}",
        'placeholder="e.g. Why this team?"',
    )


def test_saved_key_is_a_hint_not_a_placeholder():
    src = _src("components/settings/models-section.tsx")
    assert "Saved · type to replace" not in src
    # Only a configured key has the hint line; the inputs align at the bottom.
    assert re.search(r'className="grid items-end gap-3 sm:grid-cols-2">\s*<KeyField', src)
    assert 'placeholderUnset="e.g. sk-..."' in src
    assert 'placeholderUnset="e.g. AIza..."' in src
    _order(
        src,
        "Type a new key to replace the saved one.",
        "aria-describedby={configured ? hintId : undefined}",
        "placeholder={configured ? undefined : placeholderUnset}",
    )


def test_file_import_name_defaults_in_a_hint():
    src = _src("components/base-resumes/new-base-resume-dialog.tsx")
    assert 'placeholder="Defaults to the file name"' not in src
    assert 'placeholder={mode === "file" ? "Defaults to the file name"' not in src
    _order(
        src,
        "htmlFor={ids.name}",
        "id={ids.nameHint}",
        "Defaults to the file name.",
        'aria-describedby={mode === "file" ? ids.nameHint : undefined}',
        "id={ids.name}",
        'placeholder={mode === "file" ? undefined : "e.g. Machine Learning Engineer"}',
    )


def test_summary_placeholder_is_an_example_and_the_consequence_stays_visible():
    gap = _src("components/gap-analysis/gap-card.tsx")
    controls = _src("components/gap-analysis/resolution-controls.tsx")
    assert "Draft your JD-aligned value proposition" not in gap
    assert re.search(
        r'isSummary\s*\?\s*"e\.g\. Data scientist who ships forecasting models to production"', gap
    )
    # The question above already says it refreshes the summary; a hint saying
    # so again only repeats the label.
    assert "This refreshes the summary section." in gap
    assert "This becomes your summary." not in gap
    assert "Only what you write here is used.\n" in controls
    _order(controls, "Exact wording", 'placeholder="e.g. PySpark"')
    assert "Exact wording to add" not in controls


def test_demonstrate_skill_has_a_visible_label_and_no_placeholder():
    src = _src("components/resume-health/demonstrate-skill-dialog.tsx")
    assert "placeholder=" not in src
    assert "How {skill} shows up in this bullet" in src
    assert "<Label" in src


def test_metric_units_are_examples():
    src = _src("components/resume-health/metric-ask-input.tsx")
    assert 'placeholder="e.g. 5,000"' in src
    # Not one of the unit options: the custom box is for a unit the list lacks.
    assert 'placeholder="e.g. tickets"' in src
    assert '{ id: "tickets"' not in _src("lib/health-report.ts")
    assert 'placeholder="e.g. 6 months"' in src
    assert 'placeholder="unit"' not in src


def test_custom_answer_has_a_visible_label_not_a_placeholder():
    src = _src("components/settings/autofill-section.tsx")
    assert 'placeholder="Answer"' not in src
    _order(
        src,
        "htmlFor={`af-custom-${i}-answer`}",
        "Answer",
        "<Textarea",
        "id={`af-custom-${i}-answer`}",
        "aria-label={`Answer to custom question ${i + 1}`}",
    )


# kind -> (title example, organization example). Education and certification
# used to fall through to the job-title and employer examples.
_ENTITY_EXAMPLES = {
    "extra": ("e.g. Best Paper Award", "e.g. NeurIPS 2024"),
    "project": ("e.g. Fraud detection pipeline", None),
    "education": ("e.g. MSc Computer Science", "e.g. University of Toronto"),
    "certification": ("e.g. AWS Solutions Architect", "e.g. Amazon Web Services"),
}


def test_new_entity_placeholders_are_examples():
    src = _src("components/career/new-entity-dialog.tsx")
    for kind, examples in _ENTITY_EXAMPLES.items():
        for example in filter(None, examples):
            assert re.search(rf'kind === "{kind}"\s*\?\s*"{re.escape(example)}"', src), example
    for text in ("e.g. Senior Data Scientist", "e.g. Acme Corp", "e.g. Jan 2025", "e.g. Mar 2025"):
        assert text in src, text
    for retired in (
        "Project name",
        "Role or title",
        "Conference, publisher, or org",
        "Company, institution, or issuer",
        'placeholder="Present"',
        'placeholder="Jan 2025"',
    ):
        assert retired not in src, retired


def test_entity_dates_are_examples_not_the_ongoing_word():
    src = _src("components/career/entity-detail.tsx")
    assert 'placeholder="e.g. Acme Labs"' in src
    assert 'placeholder="e.g. Jan 2025"' in src
    assert 'placeholder="e.g. Mar 2025"' in src
    assert 'placeholder="Present"' not in src


def test_profile_and_notes_statements_are_hints():
    profile = _src("components/career/profile-panel.tsx")
    notes = _src("components/career/notes-editor.tsx")
    assert 'placeholder="ML Ops"' not in profile
    assert 'placeholder="e.g. ML Ops"' in profile
    assert "Visa timeline, target roles" not in profile
    _order(
        profile,
        'htmlFor="kb-profile-notes"',
        'id="kb-profile-notes-hint"',
        "Private context such as visa timeline, target roles, location constraints.",
        'aria-describedby="kb-profile-notes-hint"',
        'id="kb-profile-notes"',
    )
    assert "Stack, scale, constraints, collaborators, and what you personally owned" not in notes
    _order(
        notes,
        "htmlFor={`kb-notes-${entityId}`}",
        "id={`kb-notes-${entityId}-hint`}",
        "Stack, scale, constraints, collaborators, and what you owned.",
        "aria-describedby={`kb-notes-${entityId}-hint`}",
        "id={`kb-notes-${entityId}`}",
    )


def test_experience_end_date_empty_means_current():
    field = _src("components/resume-editor/field.tsx")
    editor = _src("components/resume-editor/experience-editor.tsx")
    _order(field, "<Label", "id={hintId}", "{hint}", "<Input", "aria-describedby={hint ? hintId : undefined}")
    # A narrow editor column stacks the fields (as the contact form does)
    # instead of clipping `e.g. Jan 2023` in a 96px date box.
    assert re.search(r'"@container grid gap-3">\s*<div className="grid gap-3 @md:grid-cols-2">', editor)
    assert 'placeholder="e.g. Jan 2023"' in editor
    assert 'placeholder="e.g. Mar 2025"' in editor
    assert 'hint="Leave empty for a current role."' in editor
    assert 'placeholder="Present"' not in editor


def test_template_slug_rule_stays_on_screen():
    src = _src("app/templates/page.tsx")
    _order(
        src,
        'htmlFor="new_id"',
        'id="new_id_hint"',
        "Use only lowercase letters, numbers, hyphens, and underscores.",
        'aria-describedby={idError ? "new_id_hint new_id_error" : "new_id_hint"}',
        'placeholder="e.g. classic_serif"',
        'id="new_id_error" role="alert"',
        "That ID has a character that isn&apos;t allowed.",
    )
    # The rule is the hint; the error says what went wrong, not the rule again.
    assert src.count("Use only lowercase letters, numbers, hyphens, and underscores.") == 1


def test_bare_examples_are_prefixed():
    expectations = {
        "app/base-resumes/page.tsx": ('placeholder="e.g. Data Scientist (1 page)"',),
        "app/new/page.tsx": ('placeholder="e.g. https://boards.example.com/job/123"',),
        "components/resume-editor/extra-sections-editor.tsx": (
            'placeholder="e.g. 2025"',
            'placeholder="https://\u2026"',
            'placeholder="e.g. Publications"',
        ),
        "components/settings/llm-endpoint.tsx": (
            'placeholder="e.g. http://host.docker.internal:11434/v1"',
        ),
        "components/settings/models-section.tsx": ('placeholder="e.g. llama3.2:3b"',),
        "components/career/capture-box.tsx": (
            'placeholder="e.g. This week I shipped\u2026"',
        ),
        "components/role-category-picker.tsx": ('"e.g. Data Scientist"',),
    }
    for rel, needles in expectations.items():
        src = _src(rel)
        for needle in needles:
            assert needle in src, f"{rel} missing {needle}"
    # The create form already had these. The table edit row is a second copy;
    # a single `in` check stays green if only the row regresses.
    referrals = _src("app/referrals/page.tsx")
    assert referrals.count('placeholder="e.g. Jane Doe"') == 2
    assert referrals.count('placeholder="e.g. Met at the AWS meetup"') == 2
    assert re.search(
        r'aria-label="Contact name"\s*placeholder="e\.g\. Jane Doe"[^>]*className="min-w-32"', referrals
    )
    assert re.search(r'aria-label="Notes"\s*placeholder="e\.g\. Met at the AWS meetup"', referrals)


def test_retired_non_examples_are_not_placeholder_values():
    retired = {
        "One question per line" + _ELLIPSIS,
        "Saved · type to replace",
        "Defaults to the file name",
        "Draft your JD-aligned value proposition. This becomes your summary.",
        "Exact wording to add",
        "How ${skill} shows up here",
        "Answer",
        "unit",
        "Present",
        "Set role" + _ELLIPSIS,
        "Project name",
        "Role or title",
        "ML Ops",
        "classic_serif",
        "you@example.com",
        "llama3.2:3b",
        "5,000",
        "6 months",
    }
    leaked = [
        f"{rel}:{line}: {value!r}"
        for rel, line, value, _expr in collect()
        if value in retired
    ]
    assert not leaked, leaked



def _tags(src: str, name: str) -> list[str]:
    """The attribute text of each `<name …>` opening tag."""
    found = []
    for match in re.finditer(rf"<{name}\b", src):
        tail = src[match.end() :]
        found.append(tail[: next(j for j, depth in _top_level(tail) if depth == 0 and tail[j] == ">")])
    return found


def _named(src: str, attrs: str) -> bool:
    """An aria-label, or an id (literal or a `useId` expression) that a `<Label htmlFor>`
    in the same file points at."""
    id_match = re.search(r'\bid=("[^"]+"|\{[^}]+\})', attrs)
    return "aria-label=" in attrs or bool(id_match and f"htmlFor={id_match.group(1)}" in src)


def test_every_role_picker_input_has_a_name():
    """Base UI's ComboboxInput only takes a name from a Field, and there is none
    here. Unnamed, the empty picker is read by its placeholder, and a picker
    with a role set is read as nothing at all."""
    picker = _src("components/role-picker.tsx")
    assert re.search(r'<Combobox\.Input\s+id=\{props\.id\}\s+aria-label=\{props\["aria-label"\]\}', picker)
    category = _src("components/role-category-picker.tsx")
    assert '"aria-label": ariaLabel = "Target role",' in category
    # Callers of RoleCategoryPicker may lean on that default; the import
    # dialog lists several resumes, so it names each one.
    assert "aria-label={`Target role for ${b.display_name}`}" in _src(
        "components/career/resume-import-dialog.tsx"
    )
    unnamed = [
        f"{rel}: <RolePicker{attrs[:60]!r}"
        for rel, src in _sources()
        for attrs in _tags(src, "RolePicker")
        if not _named(src, attrs)
    ]
    assert not unnamed, unnamed
