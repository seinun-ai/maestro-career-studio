"""Structured formatting knobs rendered into LaTeX templates as `fmt.*`.

Defaults reproduce the seeded Classic template's current output, so a resume
with no stored formatting renders as before. Templates opt in per-variable;
templates that never reference `fmt` are unaffected.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


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


def validate_formatting(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate a (possibly partial) stored formatting override before persisting.

    Rejects unknown keys and out-of-range values (``extra="forbid"`` + bounded
    fields) so an invalid override can't be written and silently break every
    later render. Returns the value unchanged on success; raises ``ValueError``
    otherwise. ``None`` (clear/inherit) is always valid.
    """
    if value is None:
        return None
    try:
        ResumeFormatting.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"invalid formatting override: {exc}") from exc
    return value


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
