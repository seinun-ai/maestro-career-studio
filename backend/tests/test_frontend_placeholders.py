"""Scoped placeholder ratchet.

A placeholder may be an example prefixed ``e.g.`` (a following space or a
newline, so the persona block's ``e.g.\\n`` still counts), or the URL format
cue ``https://…``. An ellipsis prompt is allowed only when the file and the
exact string are on the search / composer / chip-add-row list. Anything else
fails. ``SelectValue`` and image ``placeholder`` props are not inputs.

Values are the attribute or object-key expressions themselves: string
literals, template literals, ternaries, ``??``, ``.join()`` constants, and
identifiers bound to those. A file that merely contains ``e.g.`` somewhere
does not pass.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ROOTS = ("app", "components")
_SKIP_TAGS = frozenset({"SelectValue", "PreviewThumbnail"})
_ELLIPSIS = "\u2026"
_URL_CUE = "https://" + _ELLIPSIS

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

_NOT_INPUTS = (
    "None",
    "\u2014",
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


def _line_of(src: str, index: int) -> int:
    return src.count("\n", 0, index) + 1


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


def _read_quoted(src: str, i: int) -> tuple[str, int, bool]:
    """Return decoded text, index after the closer, and whether a template interpolates."""
    quote = src[i]
    i += 1
    raw: list[str] = []
    dynamic = False
    while i < len(src):
        if quote == "`" and src.startswith("${", i):
            dynamic = True
            end = _match_brace(src, i + 1)
            raw.append(src[i:end])
            i = end
            continue
        if src[i] == "\\":
            raw.append(src[i : i + 2])
            i += 2
            continue
        if src[i] == quote:
            return _decode_escapes("".join(raw)), i + 1, dynamic
        raw.append(src[i])
        i += 1
    return _decode_escapes("".join(raw)), i, dynamic


def _match_brace(src: str, open_at: int) -> int:
    """Index after the `}` matching the `{` at open_at."""
    depth = 0
    i = open_at
    while i < len(src):
        ch = src[i]
        if ch in "\"'`":
            _, i, _ = _read_quoted(src, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _skip_string_or_comment(src: str, i: int) -> int | None:
    if src.startswith("//", i):
        nxt = src.find("\n", i)
        return len(src) if nxt < 0 else nxt
    if src.startswith("/*", i):
        nxt = src.find("*/", i + 2)
        return len(src) if nxt < 0 else nxt + 2
    if src[i] in "\"'`":
        _, end, _ = _read_quoted(src, i)
        return end
    return None


class _Scan:
    def __init__(self, src: str) -> None:
        self.src = src
        self.resolving: set[str] = set()

    def sites(self) -> list[tuple[int, str | None, str]]:
        """(index of the value, enclosing JSX tag or None, introducer '=' or ':')."""
        src = self.src
        found: list[tuple[int, str | None, str]] = []
        tag_stack: list[str] = []
        in_tag = False
        expr_depth = 0
        i = 0
        n = len(src)
        while i < n:
            skipped = _skip_string_or_comment(src, i)
            if skipped is not None:
                i = skipped
                continue
            if not in_tag and expr_depth == 0 and src[i] == "<" and i + 1 < n:
                nxt = src[i + 1]
                if nxt.isalpha() or nxt in "_$":
                    j = i + 1
                    while j < n and (src[j].isalnum() or src[j] in "._$"):
                        j += 1
                    tag_stack.append(src[i + 1 : j])
                    in_tag = True
                    i = j
                    continue
                if nxt == "/":
                    in_tag = False
                    i += 2
                    continue
            if in_tag and expr_depth == 0 and src[i] == ">":
                in_tag = False
                if tag_stack:
                    tag_stack.pop()
                i += 1
                continue
            if in_tag and src[i] == "{":
                expr_depth += 1
                i += 1
                continue
            if expr_depth and src[i] == "{":
                expr_depth += 1
                i += 1
                continue
            if expr_depth and src[i] == "}":
                expr_depth -= 1
                i += 1
                continue
            if src.startswith("placeholder", i):
                before = src[i - 1] if i else " "
                after_i = i + len("placeholder")
                after = src[after_i] if after_i < n else " "
                ident = before.isalnum() or before in "_$" or after.isalnum() or after in "_$"
                if not ident:
                    k = after_i
                    while k < n and src[k] in " \t\n":
                        k += 1
                    if src.startswith("?:", k):
                        i = k + 2
                        continue
                    if k < n and src[k] in "=:":
                        tag = tag_stack[-1] if in_tag and tag_stack else None
                        found.append((k + 1, tag, src[k]))
                        i = k + 1
                        continue
            i += 1
        return found

    def values_at(self, value_at: int) -> list[tuple[int, str]]:
        src = self.src
        i = value_at
        while i < len(src) and src[i] in " \t\n":
            i += 1
        if i >= len(src):
            return []
        if src[i] == "{":
            end = _match_brace(src, i)
            return self._strings(src[i + 1 : end - 1], i + 1)
        if src[i] in "\"'`":
            text, end, dynamic = _read_quoted(src, i)
            if dynamic and not text.startswith("e.g."):
                return [(_line_of(src, i), text)]
            return [(_line_of(src, i), text)]
        end = i
        depth = 0
        while end < len(src):
            skipped = _skip_string_or_comment(src, end)
            if skipped is not None:
                end = skipped
                continue
            ch = src[end]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch in ",;" and depth == 0:
                break
            end += 1
        return self._strings(src[i:end], i)

    def _strings(self, expr: str, base: int) -> list[tuple[int, str]]:
        expr_stripped = expr.strip()
        if not expr_stripped:
            return []
        offset = expr.find(expr_stripped)
        abs_at = base + offset
        if (
            expr_stripped[0] == "("
            and _match_paren(expr_stripped, 0) == len(expr_stripped) - 1
        ):
            return self._strings(expr_stripped[1:-1], abs_at + 1)
        if expr_stripped[0] in "\"'`":
            text, consumed, _dynamic = _read_quoted(expr_stripped, 0)
            if consumed >= len(expr_stripped.rstrip()):
                return [(_line_of(self.src, abs_at), text)]
        joined = _try_join(expr_stripped)
        if joined is not None:
            return [(_line_of(self.src, abs_at), joined)]
        tern = _split_ternary(expr_stripped)
        if tern is not None:
            _cond, then, else_ = tern
            then_at = abs_at + expr_stripped.find(then)
            else_at = abs_at + expr_stripped.rfind(else_)
            return self._strings(then, then_at) + self._strings(else_, else_at)
        nullish = _split_nullish(expr_stripped)
        if nullish is not None:
            left, right = nullish
            return self._strings(left, abs_at) + self._strings(
                right, abs_at + expr_stripped.rfind(right)
            )
        if re.fullmatch(r"[A-Za-z_$][\w$]*", expr_stripped):
            if expr_stripped in {"undefined", "null", "true", "false"}:
                return []
            return self._resolve(expr_stripped)
        return []

    def _resolve(self, name: str) -> list[tuple[int, str]]:
        if name in self.resolving:
            return []
        self.resolving.add(name)
        found: list[tuple[int, str]] = []
        src = self.src
        patterns = (
            re.compile(rf"(?:const|let)\s+{name}\s*="),
            re.compile(rf"(?<![\w$]){name}\s*="),
        )
        seen_at: set[int] = set()
        for pattern in patterns:
            for match in pattern.finditer(src):
                if match.start() in seen_at:
                    continue
                # `placeholder={` is a use, not a binding to a literal.
                value_at = match.end()
                while value_at < len(src) and src[value_at] in " \t\n":
                    value_at += 1
                if value_at < len(src) and src[value_at] == "{":
                    continue
                # `name="literal"` is the whole binding. Reading on to the next
                # comma would swallow the rest of the JSX tag.
                if value_at < len(src) and src[value_at] in "\"'`":
                    text, _end, _dynamic = _read_quoted(src, value_at)
                    found.append((_line_of(src, value_at), text))
                    seen_at.add(match.start())
                    continue
                seen_at.add(match.start())
                expr_end = value_at
                depth = 0
                while expr_end < len(src):
                    skipped = _skip_string_or_comment(src, expr_end)
                    if skipped is not None:
                        expr_end = skipped
                        continue
                    ch = src[expr_end]
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif ch in ",;" and depth == 0:
                        break
                    expr_end += 1
                found.extend(self._strings(src[value_at:expr_end], value_at))
        self.resolving.remove(name)
        return found


def _match_paren(src: str, open_at: int) -> int:
    depth = 0
    i = open_at
    while i < len(src):
        skipped = _skip_string_or_comment(src, i)
        if skipped is not None:
            i = skipped
            continue
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_ternary(expr: str) -> tuple[str, str, str] | None:
    tern = 0
    depth = 0
    q_at = None
    i = 0
    while i < len(expr):
        skipped = _skip_string_or_comment(expr, i)
        if skipped is not None:
            i = skipped
            continue
        ch = expr[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "?" and depth == 0:
            nxt = expr[i + 1] if i + 1 < len(expr) else ""
            # `?.` and `??` are not the conditional operator.
            if nxt in ".?":
                i += 2
                continue
            tern += 1
            if tern == 1:
                q_at = i
        elif ch == ":" and depth == 0 and tern:
            tern -= 1
            if tern == 0 and q_at is not None:
                return expr[:q_at], expr[q_at + 1 : i], expr[i + 1 :]
        i += 1
    return None


def _split_nullish(expr: str) -> tuple[str, str] | None:
    depth = 0
    i = 0
    while i < len(expr):
        skipped = _skip_string_or_comment(expr, i)
        if skipped is not None:
            i = skipped
            continue
        ch = expr[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and expr.startswith("??", i):
            return expr[:i], expr[i + 2 :]
        i += 1
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


def _allowed(value: str) -> bool:
    if value == "":
        return True
    if value.startswith("e.g.") and (len(value) == 4 or value[4].isspace()):
        return True
    if value == _URL_CUE or value.startswith(_URL_CUE):
        return True
    return False


def collect() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for root in _ROOTS:
        for path in sorted((_FRONTEND / root).rglob("*")):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            if ".test." in path.name:
                continue
            src = path.read_text()
            rel = path.relative_to(_FRONTEND).as_posix()
            scan = _Scan(src)
            for value_at, tag, _intro in scan.sites():
                if tag in _SKIP_TAGS:
                    continue
                for line, value in scan.values_at(value_at):
                    found.append((rel, line, value))
    return found


def violations() -> list[str]:
    bad: list[str] = []
    for rel, line, value in collect():
        if _allowed(value):
            continue
        if (rel, value) in _PROMPTS and value.endswith(_ELLIPSIS):
            continue
        bad.append(f"{rel}:{line}: {value!r}")
    return bad


def test_placeholders_are_examples_or_named_prompts():
    bad = violations()
    assert not bad, "placeholder is not an example or a named prompt:\n" + "\n".join(bad)


def test_scanner_reads_indirect_placeholder_values():
    """Object fields, defaults, ternaries and joined constants, not just placeholder=\"...\"."""
    seen = {(rel, value) for rel, _line, value in collect()}
    missing = []
    for rel, prefix in _MUST_SEE:
        if not any(path == rel and value.startswith(prefix) for path, value in seen):
            missing.append(f"{rel} :: {prefix!r}")
    assert not missing, "scanner missed:\n" + "\n".join(missing)


def test_select_and_image_placeholders_are_not_inputs():
    values = {value for _rel, _line, value in collect()}
    leaked = [text for text in _NOT_INPUTS if text in values]
    assert not leaked, leaked


def test_named_prompts_are_the_ones_on_screen():
    seen = {(rel, value) for rel, _line, value in collect()}
    missing = sorted(f"{rel} :: {value}" for rel, value in _PROMPTS if (rel, value) not in seen)
    assert not missing, missing


def test_conventions_record_the_govuk_deviation():
    doc = (
        Path(__file__).resolve().parents[2] / "docs/frontend-conventions.md"
    ).read_text()
    assert "a placeholder may hold only an example value" in doc
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
    _order(
        src,
        "One question per line.",
        "aria-describedby={questionsHintId}",
        'placeholder="e.g. Why this team?"',
    )


def test_saved_key_is_a_hint_not_a_placeholder():
    src = _src("components/settings/models-section.tsx")
    assert "Saved · type to replace" not in src
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
        'htmlFor="nbr_name"',
        'id="nbr_name_hint"',
        "Defaults to the file name.",
        'aria-describedby={mode === "file" ? "nbr_name_hint" : undefined}',
        'id="nbr_name"',
        'placeholder={mode === "file" ? undefined : "e.g. Machine Learning Engineer"}',
    )


def test_summary_placeholder_is_an_example_and_the_consequence_stays_visible():
    gap = _src("components/gap-analysis/gap-card.tsx")
    controls = _src("components/gap-analysis/resolution-controls.tsx")
    assert "Draft your JD-aligned value proposition" not in gap
    assert (
        'isSummary\n                ? "e.g. Data scientist who ships forecasting models to production"'
        in gap
    )
    assert 'hint={isSummary ? "This becomes your summary." : undefined}' in gap
    assert "Only what you write here is used.{hint ? ` ${hint}` : " in controls
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
    assert 'placeholder="e.g. users"' in src
    assert 'placeholder="e.g. 6 months"' in src
    assert 'placeholder="unit"' not in src


def test_custom_answer_has_no_placeholder():
    src = _src("components/settings/autofill-section.tsx")
    assert 'placeholder="Answer"' not in src


def test_new_entity_placeholders_are_examples():
    src = _src("components/career/new-entity-dialog.tsx")
    for text in (
        "e.g. Best Paper Award",
        "e.g. Fraud detection pipeline",
        "e.g. Senior Data Scientist",
        "e.g. NeurIPS 2024",
        "e.g. Acme Corp",
        "e.g. Jan 2025",
        "e.g. Mar 2025",
    ):
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
        'aria-describedby="new_id_hint"',
        'placeholder="e.g. classic_serif"',
    )
    assert src.count("Use only lowercase letters, numbers, hyphens, and underscores.") == 2


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
    assert 'aria-label="Contact name"\n          placeholder="e.g. Jane Doe"' in referrals
    assert 'aria-label="Notes"\n          placeholder="e.g. Met at the AWS meetup"' in referrals


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
        for rel, line, value in collect()
        if value in retired
    ]
    assert not leaked, leaked
