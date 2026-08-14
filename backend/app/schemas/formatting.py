"""Structured formatting knobs rendered into LaTeX templates as `fmt.*`.

Defaults reproduce the seeded Classic template's current output, so a resume
with no stored formatting renders as before. Templates opt in per-variable;
templates that never reference `fmt` are unaffected.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# The orderable render units. `certifications` is only a UNIT in templates that
# render certs standalone (harshibar); templates that fold certs into Skills
# ignore the token, which is why it is valid everywhere but honored by one
# template. Contact/header is never orderable — it is the document's masthead,
# not a section.
SECTION_ORDER_TOKENS: tuple[str, ...] = (
    "summary",
    "experience",
    "projects",
    "extra_sections",
    "skills",
    "education",
    "certifications",
)


class ResumeFormatting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    font_size: Literal[10, 11, 12] = 11
    side_margins: float = Field(default=0.4, ge=0.3, le=1.0)
    top_bottom_margin: float = Field(default=0.3, ge=0.3, le=1.0)
    section_spacing: int = Field(default=6, ge=0, le=14)
    entry_spacing: int = Field(default=0, ge=0, le=10)
    line_spacing: float = Field(default=1.0, ge=0.9, le=1.4)
    bullet_icon: Literal["bullet", "dash"] = "bullet"
    hide_divider: bool = False
    header_align: Literal["left", "center", "right"] = "center"
    justify: bool = False
    date_format: Literal["verbatim", "short_month", "long_month", "numeric"] = (
        "verbatim"
    )
    education_order: Literal["degree_first", "institution_first"] = "degree_first"
    skills_layout: Literal["inline", "bulleted"] = "inline"
    # None/absent = the template's NATIVE order (today's output). A partial list
    # orders its members first and the template appends its remaining native
    # sections afterwards, so a stale stored list can never drop a section.
    section_order: list[str] | None = None

    @field_validator("section_order", mode="before")
    @classmethod
    def _sanitize_section_order(cls, value: Any) -> Any:
        """Drop unknown/duplicate tokens instead of raising.

        Deliberately TOLERANT, because this validator runs on the RENDER path
        too (``merge_formatting`` re-validates whatever is already stored). A
        list written by an older build, or one naming a token a later release
        renamed, must still render — the append-remainder rule in each template
        keeps the document whole. Rejecting a bad token belongs at the WRITE
        gate (``validate_formatting``), which is strict on purpose.
        """
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        seen: set[str] = set()
        out: list[str] = []
        for token in value:
            if not isinstance(token, str):
                continue
            if token in SECTION_ORDER_TOKENS and token not in seen:
                seen.add(token)
                out.append(token)
        return out


def _check_section_order(value: Any) -> None:
    """Write-gate check for ``section_order``: strict where render is tolerant."""
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(t, str) for t in value):
        raise ValueError("section_order must be a list of section-name strings")
    unknown = [t for t in value if t not in SECTION_ORDER_TOKENS]
    if unknown:
        raise ValueError(
            f"unknown section_order entries: {', '.join(sorted(set(unknown)))}; "
            f"valid entries are {', '.join(SECTION_ORDER_TOKENS)}"
        )
    if len(set(value)) != len(value):
        raise ValueError("section_order must not repeat a section")


def validate_formatting(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate a (possibly partial) stored formatting override before persisting.

    Rejects unknown keys and out-of-range values (``extra="forbid"`` + bounded
    fields) so an invalid override can't be written and silently break every
    later render. Returns the value unchanged on success; raises ``ValueError``
    otherwise. ``None`` (clear/inherit) is always valid.

    ``section_order`` needs its own check: the model's validator SANITIZES
    (see ``_sanitize_section_order``) so stale stored data still renders, which
    means ``model_validate`` alone would silently accept — and then silently
    drop — a typo'd token at write time. The write gate is where a typo must
    surface as a 422.
    """
    if value is None:
        return None
    if "section_order" in value:
        _check_section_order(value["section_order"])
    try:
        ResumeFormatting.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"invalid formatting override: {exc}") from exc
    return value


def resolve_section_order(
    requested: list[str] | None, native: list[str] | tuple[str, ...]
) -> list[str]:
    """The order a template renders its sections in.

    ``native`` is the template's own section list, in the order its body used to
    emit them. ``requested`` is ``fmt.section_order``.

    The load-bearing rule: **requested members first, the template's remaining
    native sections appended in native order**. A partial or stale list can
    therefore never silently drop a section — the worst it can do is leave one
    where the template always put it. Tokens the template does not render
    (``certifications`` in a template that folds certs into Skills, or
    ``extra_sections`` in one that has no extras block) are simply not in
    ``native``, so they fall out here rather than needing a per-template guard.

    ``None``/empty reproduces ``native`` exactly, which is what makes "knob
    absent = today's output" true by construction rather than by care.
    """
    if not requested:
        return list(native)
    # `dict.fromkeys`, not a plain comprehension: a repeated token would
    # otherwise render its section TWICE. In the shipped path the schema
    # validator has already de-duplicated, so this is belt-and-braces — but the
    # function's contract is "every native section exactly once", and a helper
    # that only holds that contract for pre-cleaned input is a trap for the next
    # caller.
    ordered = list(dict.fromkeys(token for token in requested if token in native))
    return ordered + [token for token in native if token not in ordered]


def overlay(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """Shallow-merge partial formatting diffs (later wins), WITHOUT filling
    schema defaults — for stacking user layers before the template default."""
    out: dict[str, Any] = {}
    for layer in layers:
        if layer:
            out.update({k: v for k, v in layer.items() if v is not None})
    return out


def merge_formatting(*layers: dict[str, Any] | None) -> ResumeFormatting:
    """Defaults <- earlier layers <- later layers; None layers/values skipped."""
    merged: dict[str, Any] = {}
    for layer in layers:
        if layer:
            merged.update({k: v for k, v in layer.items() if v is not None})
    return ResumeFormatting.model_validate(merged)
