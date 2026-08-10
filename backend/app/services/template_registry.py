from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.template import Template
from app.services import pdf_render, typst_compiler

logger = logging.getLogger(__name__)

DEFAULT_ID = "default"

_FMT_KEY_RE = re.compile(r"fmt\.([a-z_]+)")
_INCLUDE_RE = re.compile(r"include\s+['\"]([^'\"]+)['\"]")
# Include targets must be a plain basename of a bundled partial. This bars
# absolute paths, "..", path separators, and devices — template `source` is
# user-authored (create/update/AI-edit), so an unrestricted read would be an
# arbitrary-file-read / DoS primitive (e.g. include '/etc/passwd' or '/dev/zero').
_SAFE_PARTIAL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _resolve_partial(name: str):
    """Return the path of a bundled partial iff ``name`` is safely inside
    TEMPLATE_DIR, else None."""
    if not _SAFE_PARTIAL_RE.match(name) or name in (".", ".."):
        return None
    base = pdf_render.TEMPLATE_DIR.resolve()
    candidate = (base / name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def iter_partial_sources(source: str):
    """Yield the raw text of every bundled partial ``source`` transitively
    ``((* include 'name' *))``-s. Include targets are restricted to safe bundled
    basenames (see ``_resolve_partial``) so a crafted ``source`` cannot read
    arbitrary files; unresolved/unreadable includes are skipped.

    Shared by ``supported_fmt_keys`` and ``pdf_render.source_references_extras``
    so both discover content a template renders via an included partial rather
    than duplicating this walk."""
    seen: set[str] = set()
    pending = list(_INCLUDE_RE.findall(source))
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        partial = _resolve_partial(name)
        if partial is None:
            continue
        try:
            text = partial.read_text(encoding="utf-8")
        except OSError:
            continue
        yield text
        pending.extend(_INCLUDE_RE.findall(text))


# Formatting knobs the Typst data layer applies server-side for EVERY typst
# template regardless of source (date_format via pdf_render._preformat_dates), so
# the panel must offer them even though the .typ never names them.
_TYPST_SERVER_APPLIED_FMT_KEYS = frozenset({"date_format"})


def supported_fmt_keys(source: str, engine: str = "latex") -> list[str]:
    """Sorted, unique ``fmt.<key>`` names a template opts into.

    LaTeX (default): findall over the source and any ``((* include 'partial' *))``
    bundled partials (e.g. ``_header.tex.j2``, where ``fmt.header_align`` lives)
    so a template that renders the header via the shared partial still reports the
    header knobs. Byte-identical to the pre-Typst behavior.

    Typst: there is no Jinja include layer, but a naive findall miscredits an
    ``fmt.<key>`` that appears only inside a ``//`` or ``/* */`` comment. Scan the
    comment/string-aware stripped source (the same scanner as the extras check),
    then add the knobs the Typst path applies server-side for every template.
    """
    if engine == "typst":
        stripped = typst_compiler.strip_typst_comments(source)
        return sorted(
            set(_FMT_KEY_RE.findall(stripped)) | _TYPST_SERVER_APPLIED_FMT_KEYS
        )
    keys: set[str] = set(_FMT_KEY_RE.findall(source))
    for text in iter_partial_sources(source):
        keys.update(_FMT_KEY_RE.findall(text))
    return sorted(keys)

# Canonical starter for new drafts (create_draft with source=None). Kept small
# on purpose: it demonstrates the custom delimiters + latex_escape and compiles
# as-is, so a fresh draft validates before any editing.
STARTER_SOURCE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\begin{document}
\begin{center}{\Large\bfseries ((( resume.contact.name|latex_escape )))}\end{center}
((* if resume.summary *))((( resume.summary|latex_escape )))((* endif *))
\section*{Experience}
((* for e in resume.experience *))
\textbf{((( e.company|latex_escape )))} — ((( e.role|latex_escape )))\\
((* for b in e.bullets *))$\bullet$ ((( b|latex_escape )))\\
((* endfor *))
((* endfor *))
\end{document}"""


def _bootstrap_default(session: Session) -> Template:
    # Invariant: at most ONE is_default=True row. Only bootstrap a default when
    # none exists (fail closed). Guarding on the DEFAULT_ID row's absence instead
    # would spawn a SECOND default next to a user's chosen default if the seed
    # 'default' row had been deleted after the user re-pointed the default.
    current = session.scalar(select(Template).where(Template.is_default.is_(True)))
    if current is not None:
        return current
    existing = session.get(Template, DEFAULT_ID)
    if existing is not None:
        # The seed row exists but nothing is marked default: promote it rather
        # than insert a duplicate id.
        existing.is_default = True
        session.commit()
        session.refresh(existing)
        return existing
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    tmpl = Template(
        id=DEFAULT_ID,
        display_name="Classic",
        source=source,
        status="ready",
        is_default=True,
        origin="seed",
        validated_at=datetime.now(UTC),
    )
    try:
        with session.begin_nested():
            session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        return tmpl
    except IntegrityError:
        # A concurrent first load (GET /api/templates seeds inline) inserted the
        # row between the checks above and this insert; recover to the winner's
        # row instead of surfacing a 500.
        row = session.scalar(select(Template).where(Template.is_default.is_(True)))
        return row if row is not None else session.get(Template, DEFAULT_ID)


def get_default(session: Session) -> Template:
    row = session.scalar(select(Template).where(Template.is_default.is_(True)))
    return row if row is not None else _bootstrap_default(session)


TYPST_CLASSIC_ID = "typst-classic"
TYPST_CLASSIC_FILE = "typst_classic.typ"


def _seed_validate_typst_classic(session: Session, tmpl: Template) -> None:
    """Validate the typst-classic seed exactly like a fresh draft: success flips
    it ready + parse-certified. A validation problem (e.g. unwritable preview dir
    on a dev host) must never take down seeding or the list endpoint, so it is
    swallowed -- but the reason is recorded on last_error (previously left None,
    which stranded the row as a draft with no diagnosis and no retry signal)."""
    from app.services import template_validation  # lazy: avoid import cycle

    try:
        template_validation.validate_template(TYPST_CLASSIC_ID, session)
        session.refresh(tmpl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("typst-classic seed validation failed; left as draft")
        try:
            tmpl.last_error = f"seed validation error: {exc}"[:4000]
            session.commit()
        except Exception:  # noqa: BLE001 -- bookkeeping must not break seeding
            session.rollback()


def _bootstrap_typst_classic(session: Session) -> Template:
    existing = session.get(Template, TYPST_CLASSIC_ID)
    if existing is not None:
        # A row stranded non-ready by an earlier first-boot validation failure
        # gets re-validated on the next ensure so it can recover, instead of
        # staying draft forever.
        if existing.status != "ready":
            _seed_validate_typst_classic(session, existing)
        return existing
    source = (pdf_render.TEMPLATE_DIR / TYPST_CLASSIC_FILE).read_text(encoding="utf-8")
    tmpl = Template(
        id=TYPST_CLASSIC_ID,
        display_name="Typst Classic",
        source=source,
        engine="typst",
        status="draft",
        origin="seed",
    )
    try:
        with session.begin_nested():
            session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
    except IntegrityError:
        # Concurrent first load inserted it between the check and this insert;
        # recover to the existing row (re-validating it if not ready) rather than
        # 500ing.
        existing = session.get(Template, TYPST_CLASSIC_ID)
        if existing is None:
            raise
        if existing.status != "ready":
            _seed_validate_typst_classic(session, existing)
        return existing
    _seed_validate_typst_classic(session, tmpl)
    return tmpl


def ensure_seed_templates(session: Session) -> None:
    """Idempotent: bootstrap the seeded templates (Classic LaTeX default +
    typst-classic). Existing rows are returned untouched."""
    _bootstrap_default(session)
    _bootstrap_typst_classic(session)


def get(session: Session, template_id: str) -> Template | None:
    return session.get(Template, template_id)


def list_all(session: Session) -> list[Template]:
    return list(session.scalars(select(Template).order_by(Template.id)))


def get_usable_template(template_id: str | None, session: Session) -> Template:
    """Resolve the template to render with, tolerant of a stale persisted id.

    Render must not break when a resume's persisted ``template_id`` points at a
    template that has since been deleted or is being edited (a draft, i.e. not
    ``ready``): in either case we fall back to the default template rather than
    raising, so the resume stays renderable. ``None`` also maps to the default.
    """
    if template_id is None:
        return get_default(session)
    row = session.get(Template, template_id)
    if row is None:
        logger.warning(
            "Render template %r not found; falling back to default.", template_id
        )
        return get_default(session)
    if row.status != "ready":
        logger.warning(
            "Render template %r is not ready (status=%s); falling back to default.",
            template_id,
            row.status,
        )
        return get_default(session)
    return row


def create_draft(
    session: Session, *, id: str, display_name: str, source: str | None, origin: str,
    engine: str = "latex",
) -> Template:
    if session.get(Template, id) is not None:
        raise ValueError(f"Template already exists: {id}")
    tmpl = Template(
        id=id,
        display_name=display_name,
        source=source if source is not None else STARTER_SOURCE,
        engine=engine,
        status="draft",
        origin=origin,
    )
    session.add(tmpl)
    session.commit()
    session.refresh(tmpl)
    return tmpl


def update_draft(session: Session, template_id: str, *, source: str | None = None,
                 display_name: str | None = None) -> Template:
    row = session.get(Template, template_id)
    if row is None:
        raise LookupError(f"Template not found: {template_id}")
    if source is not None:
        row.source = source
        row.status = "draft"
        row.last_error = None
        row.validated_at = None
        # A prior validate certified the OLD source's parse fidelity; a new
        # source invalidates that until the next validate re-certifies it.
        row.parse_certified = None
        row.parse_report_json = None
    if display_name is not None:
        row.display_name = display_name
    session.commit()
    session.refresh(row)
    return row


def duplicate(
    session: Session, source_id: str, new_id: str, *, display_name: str | None = None,
    origin: str = "chat",
) -> Template:
    """Copy an existing template's source + default_formatting into a NEW draft.

    Raises LookupError if the source is missing, ValueError if `new_id` collides.
    The copy always starts as a draft (must be re-validated before use).
    """
    src = session.get(Template, source_id)
    if src is None:
        raise LookupError(f"Template not found: {source_id}")
    if session.get(Template, new_id) is not None:
        raise ValueError(f"Template already exists: {new_id}")
    tmpl = Template(
        id=new_id,
        display_name=display_name
        or (f"{src.display_name} (copy)" if src.display_name else new_id),
        source=src.source,
        engine=src.engine,
        status="draft",
        origin=origin,
        default_formatting=src.default_formatting,
    )
    session.add(tmpl)
    session.commit()
    session.refresh(tmpl)
    return tmpl


def set_default(session: Session, template_id: str) -> Template:
    row = session.get(Template, template_id)
    if row is None:
        raise LookupError(f"Template not found: {template_id}")
    if row.status != "ready":
        raise ValueError("Only a 'ready' template can become the default")
    session.execute(update(Template).where(Template.is_default.is_(True)).values(is_default=False))
    row.is_default = True
    session.commit()
    session.refresh(row)
    return row


def delete(session: Session, template_id: str) -> None:
    row = session.get(Template, template_id)
    if row is None:
        raise LookupError(f"Template not found: {template_id}")
    if row.is_default:
        raise ValueError("Cannot delete the default template")
    session.delete(row)
    session.commit()
