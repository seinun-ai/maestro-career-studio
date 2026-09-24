from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.template import Template
from app.schemas.template import validate_template_id
from app.services import engines, pdf_render, typst_compiler

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

# Canonical starter for new drafts (create_draft with source=None). A COMPLETE
# skeleton on purpose: it renders every core section, the contact line (email
# included) and both custom-section shapes, so a fresh draft clears every
# parse probe in template_validation and lands `ready` + certified. The first
# version rendered name, summary and experience alone; the web "New template"
# flow validates on create, so that draft failed the education/skills/email
# probes and the gallery flagged it "ATS spacing" before the user had typed a
# character — the from-scratch flow looked broken on its first screen. It also
# stays free of `fmt.*` knobs (a starter opts into nothing; see
# test_supported_fmt_keys_default_and_starter) and of packages outside the
# image's TeX layer (backend/Dockerfile).
STARTER_SOURCE = r"""\documentclass[11pt]{article}
\usepackage[margin=0.75in]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage{enumitem}
\setlist[itemize]{leftmargin=1.2em, itemsep=1pt, topsep=2pt, parsep=0pt}
\setlength{\parindent}{0pt}
\pagestyle{empty}
% A section title with a rule under it. Edit freely. Triple-paren tags print a
% resume field and paren-star tags are control flow; keep |latex_escape on
% every user string so a stray ampersand or percent sign cannot break TeX.
\newcommand{\sectiontitle}[1]{\par\vspace{8pt}{\large\bfseries #1}\par\vspace{1pt}\hrule\vspace{5pt}}
\begin{document}
((* macro bullets(items) *))((* if items *))
\begin{itemize}
((* for b in items *))
\item ((( b|latex_escape )))
((* endfor *))
\end{itemize}
((* else *))
\par
((* endif *))((* endmacro *))
\begin{center}
((* if resume.contact.name *))
{\LARGE\bfseries ((( resume.contact.name|latex_escape )))}\\[3pt]
((* endif *))
\small ((( resume.contact.email|latex_escape )))((* if resume.contact.phone *)) ~$\cdot$~ ((( resume.contact.phone|latex_escape )))((* endif *))((* if resume.contact.location *)) ~$\cdot$~ ((( resume.contact.location|latex_escape )))((* endif *))
((* if resume.contact.linkedin or resume.contact.github or resume.contact.website *))
\\[1pt] \small
((* if resume.contact.linkedin *))\href{https://((( resume.contact.linkedin|latex_escape_url )))}{((( resume.contact.linkedin|latex_escape )))}((* endif *))
((* if resume.contact.github *)) ~$\cdot$~ \href{https://((( resume.contact.github|latex_escape_url )))}{((( resume.contact.github|latex_escape )))}((* endif *))
((* if resume.contact.website *)) ~$\cdot$~ \href{https://((( resume.contact.website|latex_escape_url )))}{((( resume.contact.website|latex_escape )))}((* endif *))
((* endif *))
\end{center}
((* if resume.summary *))
\sectiontitle{Summary}
((( resume.summary|latex_escape )))
((* endif *))
((* if resume.skills *))
\sectiontitle{Skills}
((* for group in resume.skills *))
\textbf{((( group.category|latex_escape )))}: ((( group.items|map("latex_escape")|join(", ") )))((* if not loop.last *))\\((* endif *))
((* endfor *))
((* endif *))
((* if resume.experience *))
\sectiontitle{Experience}
((* for e in resume.experience *))
\textbf{((( e.role|latex_escape )))} $|$ ((( e.company|latex_escape )))((* if e.location *)), ((( e.location|latex_escape )))((* endif *))\hfill ((* if e.start_date *))((( e.start_date|latex_escape )))((* if e.end_date *)) -- ((( e.end_date|latex_escape )))((* endif *))((* elif e.end_date *))((( e.end_date|latex_escape )))((* endif *))
((( bullets(e.bullets) )))
((* endfor *))
((* endif *))
((* if resume.projects *))
\sectiontitle{Projects}
((* for p in resume.projects *))
\textbf{((( p.name|latex_escape )))}((* if p.tech *)) $|$ \emph{((( p.tech|latex_escape )))}((* endif *))\hfill ((( p.date|latex_escape if p.date else "" )))
((( bullets(p.bullets) )))
((* endfor *))
((* endif *))
((* for section in resume.extra_sections *))
((* if section.type == "entries" and section.entries *))
\sectiontitle{((( section.title|latex_escape )))}
((* for entry in section.entries *))
\textbf{((( entry.heading|latex_escape )))}((* if entry.subheading *)) $|$ ((( entry.subheading|latex_escape )))((* endif *))((* if entry.location *)), ((( entry.location|latex_escape )))((* endif *))\hfill ((( entry.date|latex_escape if entry.date else "" )))
((* if entry.link *))
\begin{itemize}
\item \href{((( entry.link|latex_escape_url )))}{((( entry.link|latex_escape )))}
((* for b in entry.bullets *))
\item ((( b|latex_escape )))
((* endfor *))
\end{itemize}
((* else *))
((( bullets(entry.bullets) )))
((* endif *))
((* endfor *))
((* elif section.type == "bullets" and section.bullets *))
\sectiontitle{((( section.title|latex_escape )))}
((( bullets(section.bullets) )))
((* endif *))
((* endfor *))
((* if resume.education *))
\sectiontitle{Education}
((* for edu in resume.education *))
\textbf{((( edu.institution|latex_escape )))}((* if edu.location *)), ((( edu.location|latex_escape )))((* endif *))\hfill ((* if edu.start_date *))((( edu.start_date|latex_escape )))((* if edu.end_date *)) -- ((( edu.end_date|latex_escape )))((* endif *))((* elif edu.end_date *))((( edu.end_date|latex_escape )))((* elif edu.graduation_date *))((( edu.graduation_date|latex_escape )))((* endif *))\\
((* if edu.degree *))((( edu.degree|latex_escape )))((* endif *))((* if edu.field and edu.field not in (edu.degree or "") *)), ((( edu.field|latex_escape )))((* endif *))((* if edu.gpa *)) ~$\cdot$~ ((( edu.gpa|latex_escape )))((* endif *))
((* if edu.coursework *))
\begin{itemize}
\item Coursework: ((( edu.coursework|map("latex_escape")|join(", ") )))
((* for b in edu.bullets *))
\item ((( b|latex_escape )))
((* endfor *))
\end{itemize}
((* else *))
((( bullets(edu.bullets) )))
((* endif *))
((* endfor *))
((* endif *))
((* if resume.certifications *))
\sectiontitle{Certifications}
((( bullets(resume.certifications) )))
((* endif *))
\end{document}"""


def _bootstrap_default(session: Session, *, validate: bool = True) -> Template:
    # Invariant: at most ONE is_default=True row. Only bootstrap a default when
    # none exists (fail closed). Guarding on the DEFAULT_ID row's absence instead
    # would spawn a SECOND default next to a user's chosen default if the seed
    # 'default' row had been deleted after the user re-pointed the default.
    current = session.scalar(select(Template).where(Template.is_default.is_(True)))
    if current is not None:
        # The seed default gets the same "another go on the next ensure" as
        # every other seed (`_bootstrap_seeded`): a first boot without TeX
        # leaves it a draft with "requires TeX", and returning here unconditionally
        # meant installing TeX never re-validated it. A user-chosen default is
        # the user's and is never validated on their behalf.
        if validate and current.id == DEFAULT_ID and _needs_seed_validation(current):
            _seed_validate(session, current)
        return current
    existing = session.get(Template, DEFAULT_ID)
    if existing is not None:
        # The seed row exists but nothing is marked default: promote it rather
        # than insert a duplicate id.
        existing.is_default = True
        session.commit()
        session.refresh(existing)
        if validate and _needs_seed_validation(existing):
            _seed_validate(session, existing)
        return existing
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    # status="draft" and NO validated_at: both are earned by _seed_validate
    # below, exactly as the typst seed earns them. This row used to be inserted
    # `ready` with validated_at=now() and no render ever attempted, so every
    # fresh install showed its DEFAULT template as "Not validated" with a 404
    # thumbnail — and the in-product fix (Re-validate) was refused, because
    # editing the default needs allow_default_edit.
    tmpl = Template(
        id=DEFAULT_ID,
        display_name="Classic",
        source=source,
        status="draft",
        is_default=True,
        origin="seed",
    )
    try:
        with session.begin_nested():
            session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
        if validate:
            _seed_validate(session, tmpl)
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


# Template ids this PROCESS has already tried to seed-validate. Bounds the
# retry to once per boot, which is what "recover on the next ensure" always
# meant — `ensure_seed_templates` runs on EVERY `GET /api/templates`, so
# without this a template that cannot validate (unwritable preview dir, no
# pdflatex) re-renders on every list request forever. With six seeded templates
# instead of two that stopped being theoretical: it made each list call attempt
# six PDF renders, and each failed attempt's commit/rollback disturbed the
# caller's transaction, which surfaced as 31 unrelated tests failing in
# full-suite order while passing alone.
_SEED_VALIDATION_ATTEMPTED: set[str] = set()


def reset_seed_validation_attempts() -> None:
    """Forget this process's attempts, i.e. behave like a fresh boot.

    For tests, which truncate `templates` between cases and would otherwise
    inherit the guard from an earlier test and never re-validate.
    """
    _SEED_VALIDATION_ATTEMPTED.clear()


def _seed_validate(session: Session, tmpl: Template) -> None:
    """Validate a seeded template exactly like a fresh draft: success flips it
    ready + parse-certified AND writes the preview PDF the gallery renders.

    A validation problem (e.g. unwritable preview dir on a dev host) must never
    take down seeding or the list endpoint, so it is swallowed -- but the reason
    is recorded on last_error (previously left None, which stranded the row as a
    draft with no diagnosis and no retry signal).
    """
    from app.services import template_validation  # lazy: avoid import cycle

    if tmpl.id in _SEED_VALIDATION_ATTEMPTED:
        return
    if tmpl.engine == "latex" and not engines.pdflatex_available():
        # Not an attempt: nothing compiled, so the guard stays unconsumed and
        # the next validating ensure (startup, or POST /validate) re-checks the
        # probe. The reason is recorded so the gallery can say "requires TeX".
        reason = template_validation.REQUIRES_TEX
        if tmpl.last_error != reason:
            tmpl.last_error = reason
            session.commit()
        return
    _SEED_VALIDATION_ATTEMPTED.add(tmpl.id)
    try:
        template_validation.validate_template(tmpl.id, session)
        session.refresh(tmpl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s seed validation failed; left as draft", tmpl.id)
        try:
            tmpl.last_error = f"seed validation error: {exc}"[:4000]
            session.commit()
        except Exception:  # noqa: BLE001 -- bookkeeping must not break seeding
            session.rollback()


def _needs_seed_validation(tmpl: Template) -> bool:
    """True when a seeded row cannot produce the preview the gallery asks for.

    Two cases, and the second is the one that shipped. A row that never reached
    `ready` obviously needs another go. But a row can ALSO be `ready` with a
    `validated_at` stamp and still have no preview PDF on disk — which is
    exactly what `_bootstrap_default` used to create, because it asserted both
    fields at INSERT without ever rendering. The frontend keys the thumbnail URL
    off `validated_at`, so that row asks for a file that was never written and
    renders "Not validated" forever. Checking the artifact, not the flag, is
    what lets an already-broken install heal itself on the next boot.
    """
    from app.services import template_validation  # lazy: avoid import cycle

    if tmpl.status != "ready":
        return True
    return not template_validation._preview_path(tmpl.id).exists()


# Digests (sha256 of the utf-8 source) of every version of a bundled seed that
# SHIPPED before the current one: one entry per `main` commit that changed the
# file, listed oldest first. A seeded row carrying one of these is ours and
# never resynced ("untouched applies to the SOURCE", ensure_seed_templates), so
# it is safe to replace with the current bundle; a user-edited row matches
# nothing and is left alone. Pinned literals, checked against the frozen bytes
# under tests/fixtures/templates_superseded/<seed_id>/<n>.tex.j2 — a wrong
# digest is a silent no-op. Seed-time rather than alembic because rows that
# v0.4.0 imported verbatim from the old Postgres database never passed through
# a SQLite migration, and only seeding — which runs on every boot — ever sees
# them. Whenever a bundled user template's bytes change, the bytes it had
# become a version that shipped: freeze them as the next fixture and pin here
# (CURRENT_SEED_DIGESTS below fails a test until that is done).
SUPERSEDED_SEED_DIGESTS: dict[str, frozenset[str]] = {
    "carlito_dense": frozenset({
        # e81696be, c4b40be0, c27b05d4 (last change on main; identical at
        # main's tip). All three pass \href targets through latex_escape,
        # which body-escapes ~ and _ in URLs.
        "a7de33995feedd47bf8021b9ab89d3c74614477ce7d20c1c22a6f7692b55f29b",
        "32a6aef985681c89664187cfc70c53de0f642e53335574ec541e3ce894b9af20",
        "167050b70047a07e0ad3111e51fbc82bfe4724a69ae7de65a19a21424401b8bb",
        # 590cb2d5: \href targets fixed; the name line still ended an empty
        # line when contact.name was blank (the web Blank tab).
        "7a7484a25d6f93db395899e63084ad1f9f9d317f6c8f727ef475df8979102b8e",
    }),
    "harshibar": frozenset({
        # e81696be, c4b40be0, c27b05d4 (last change on main; identical at
        # main's tip): the same three releases, the same \href bug on the
        # project link.
        "a676b9f7f9a44fb8e3f77fc1c5beddc419ff3efff24fff452e3d85a45ed3c546",
        "b3dc762c7e52b134cc39f98d584eeef329086673045c51efcb0a460a0813498f",
        "5bdc42534d3f8f9f03de09f7455b0a8ac813b759d5b86232ffc188698051ee89",
        # 590cb2d5: \href fixed; a contact line with nothing on it still
        # ended with a bare \\ (the web Blank tab).
        "4ec93a33152635603d7d8d2281cf5e8c23db964cd36ac818f22c9346493473c6",
    }),
    "xcharter_serif": frozenset({
        # e81696be, c4b40be0, c27b05d4 (identical at 8878731d): all three end
        # an empty name line with \\ when contact.name is blank.
        "3b69c685a8f9ca528886432fc16a71bd36b4ae3720cd39f99b8f306915aae0a6",
        "6fbbb40605eaefd3994104866540dc297a827292edcb955709db05f637a7f979",
        "7f577cd106ad0bbe6e2ccff58131d68da3c967597c802215d10dcb9d0ce4f289",
    }),
}

# sha256 of each CURRENTLY bundled source, for every seed with a history
# above. Its only job is to fail `test_current_bundled_sources_are_pinned`
# when someone edits one of these templates without freezing the version being
# superseded: the bytes on disk today are what every install seeded from this
# release will carry, and the resync can only recognise what was pinned.
# Update it LAST, after the fixture and the SUPERSEDED_SEED_DIGESTS entry.
CURRENT_SEED_DIGESTS: dict[str, str] = {
    "carlito_dense": "f6f0203fc1d6ab08a03827d20172118edc417989e4d893a9aba2af68c2bb38ea",
    "harshibar": "d9853145206988204e1b8e9b15838d64efefc5bbbc49ae99655b29426586023c",
    "xcharter_serif": "a06c8ecba153c566efeab09470152d931bc3dab1b737830dad583bbc25797e45",
}


def _resync_superseded_seed(session: Session, row: Template, source_path: Path) -> bool:
    """Replace a seeded row's source when it is a version we shipped before.

    Returns True when it did. Status drops to draft so startup validation
    re-earns `ready` against the new source — the stored parse evidence
    described the old bytes; the user's default_formatting is never touched.

    Digest first, bundle second: this runs on every GET /api/templates, and a
    row's digest stops matching the moment it is resynced, so the steady state
    is one in-memory hash and no disk read per list request.
    """
    pins = SUPERSEDED_SEED_DIGESTS.get(row.id)
    if not pins or row.origin != "seed":
        return False
    if hashlib.sha256(row.source.encode("utf-8")).hexdigest() not in pins:
        return False
    if not source_path.exists():
        logger.warning("bundled template source missing, not resynced: %s", source_path)
        return False
    current = source_path.read_text(encoding="utf-8")
    if current == row.source:
        return False
    row.source = current
    row.status = "draft"
    row.validated_at = None
    row.parse_certified = None
    row.parse_report_json = None
    row.last_error = None
    try:
        session.commit()
    except Exception:  # noqa: BLE001 -- a locked file at boot must not break seeding
        session.rollback()
        logger.exception("%s superseded-source resync failed; left as is", row.id)
        return False
    logger.info("resynced superseded bundled template source: %s", row.id)
    return True


def _bootstrap_seeded(
    session: Session,
    *,
    template_id: str,
    display_name: str,
    engine: str,
    source_path,
    default_formatting: dict | None = None,
    validate: bool = True,
) -> Template:
    """Insert a seeded template as a draft, then earn `ready` by validating.

    One function for every non-default seed. Generalized from the typst-classic
    bootstrap because the four bundled designs in `app/templates/user/` needed
    exactly the same lifecycle, and a second hand-written copy of it is how the
    default seed drifted into asserting `ready` without rendering.
    """
    existing = session.get(Template, template_id)
    if existing is not None:
        # A row seeded from an OLDER bundle keeps that bundle's bytes on its
        # own forever, so a fix to a bundled file never reaches an upgraded
        # install. Resync it when its digest proves it is ours — before the
        # validation check, so the new source re-earns `ready` in this same
        # startup.
        _resync_superseded_seed(session, existing, source_path)
        # A row stranded non-ready by an earlier first-boot validation failure —
        # or ready with a missing preview — gets another go on the next ensure,
        # instead of staying broken forever.
        if validate and _needs_seed_validation(existing):
            _seed_validate(session, existing)
        return existing
    if not source_path.exists():
        logger.warning("bundled template source missing, skipping: %s", source_path)
        return None
    tmpl = Template(
        id=template_id,
        display_name=display_name,
        source=source_path.read_text(encoding="utf-8"),
        engine=engine,
        status="draft",
        origin="seed",
        # Only set on INSERT. An existing row's default_formatting is the
        # user's (the templates API lets them edit it), so re-seeding must
        # never reach it; the migration applies the same rule to installs that
        # predate this field.
        default_formatting=default_formatting,
    )
    try:
        with session.begin_nested():
            session.add(tmpl)
        session.commit()
        session.refresh(tmpl)
    except IntegrityError:
        # Concurrent first load inserted it between the check and this insert;
        # recover to the existing row rather than 500ing.
        existing = session.get(Template, template_id)
        if existing is None:
            raise
        if validate and _needs_seed_validation(existing):
            _seed_validate(session, existing)
        return existing
    if validate:
        _seed_validate(session, tmpl)
    return tmpl


# The bundled designs in app/templates/user/. These shipped inside the image
# from the start and never reached the database: ensure_seed_templates only
# minted the two classics, and the only loader for this directory was
# scripts/apply_template_sources.py, a maintainer script no installer runs. So
# every user downloaded four finished templates and saw two.
_USER_TEMPLATE_DIR = pdf_render.TEMPLATE_DIR / "user"

# Harshibar is the one bundled template whose native order is not the common
# one, AND the one that renders Certifications as its own section. Seeding the
# order explicitly costs nothing at render time (it IS the native order, so the
# output is unchanged) and buys the formatting panel the truth: the control
# shows the template's real order, including the Certifications row that no
# other bundled template has. Every other template leaves the knob unset, which
# means "native order" and keeps the panel on its generic fallback list.
HARSHIBAR_DEFAULT_FORMATTING = {
    "section_order": [
        "summary",
        "experience",
        "projects",
        "education",
        "certifications",
        "skills",
    ]
}

BUNDLED_TEMPLATES = (
    ("xcharter_serif", "XCharter Serif", "latex", "xcharter_serif.tex.j2", None),
    (
        "xcharter_serif_typst",
        "XCharter Serif (Typst)",
        "typst",
        "xcharter_serif.typ",
        None,
    ),
    ("carlito_dense", "Carlito Dense", "latex", "carlito_dense.tex.j2", None),
    ("harshibar", "Harshibar", "latex", "harshibar.tex.j2",
     HARSHIBAR_DEFAULT_FORMATTING),
)


def _bootstrap_typst_classic(session: Session, *, validate: bool = True) -> Template:
    return _bootstrap_seeded(
        session,
        template_id=TYPST_CLASSIC_ID,
        display_name="Typst Classic",
        engine="typst",
        source_path=pdf_render.TEMPLATE_DIR / TYPST_CLASSIC_FILE,
        validate=validate,
    )


def _bootstrap_bundled(session: Session, *, validate: bool = True) -> None:
    for template_id, display_name, engine, filename, formatting in BUNDLED_TEMPLATES:
        _bootstrap_seeded(
            session,
            template_id=template_id,
            display_name=display_name,
            engine=engine,
            source_path=_USER_TEMPLATE_DIR / filename,
            default_formatting=formatting,
            validate=validate,
        )


def ensure_seed_templates(session: Session, *, validate: bool = True) -> None:
    """Idempotent: bootstrap the Classic LaTeX default, typst-classic, and the
    four bundled designs in app/templates/user/.

    "Untouched" applies to the SOURCE of an existing row when that source is
    the user's. A row still carrying a bundle we shipped before is ours and is
    resynced to the current bundle (`SUPERSEDED_SEED_DIGESTS`). Validation
    state is never untouched: a row that cannot produce a preview is
    re-validated so a broken first boot heals on the next one rather than
    persisting.

    `validate=False` means "make sure the ROWS exist, render nothing", and it is
    what `GET /api/templates` must use. `template_validation.validate_template`
    COMMITS the session it is handed, so validating from inside a request commits
    that request's transaction as a side effect of listing templates. With one
    seeded template that was survivable; at six it corrupted unrelated state
    nondeterministically — the symptom was a different handful of unrelated
    tests failing on each full-suite run while every one of them passed alone.
    Validation belongs at startup, which has no caller transaction to damage.
    """
    _bootstrap_default(session, validate=validate)
    _bootstrap_typst_classic(session, validate=validate)
    _bootstrap_bundled(session, validate=validate)


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


def first_ready_typst(session: Session) -> Template | None:
    """The substitute for a LaTeX template on a TeX-less host, in a FIXED
    order so the same install always falls back the same way: the default if
    it is a ready Typst template, else typst-classic, else any ready Typst
    template by id."""
    default = session.scalar(select(Template).where(Template.is_default.is_(True)))
    for candidate in (default, session.get(Template, TYPST_CLASSIC_ID)):
        if (
            candidate is not None
            and candidate.engine == "typst"
            and candidate.status == "ready"
            and candidate.archived_at is None
        ):
            return candidate
    return session.scalar(
        select(Template)
        .where(
            Template.engine == "typst",
            Template.status == "ready",
            Template.archived_at.is_(None),
        )
        .order_by(Template.id)
    )


def create_draft(
    session: Session, *, id: str, display_name: str, source: str | None, origin: str,
    engine: str = "latex",
) -> Template:
    # Validated HERE, not only in the REST schema: chat and MCP reach this
    # function directly, and an id is also a filename (see validate_template_id).
    validate_template_id(id)
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
    validate_template_id(new_id)
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
        raise ValueError("Only a template that passed its check can be the default.")
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
        raise ValueError("This is your default template. Make another one the default first.")
    session.delete(row)
    session.commit()
