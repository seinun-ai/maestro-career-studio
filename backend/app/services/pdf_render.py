import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

from app.config import settings
from app.schemas.formatting import merge_formatting
from app.schemas.resume import ResumeData
from app.services import typst_compiler
from app.services.date_format import format_date
from app.services.resume_projects import resume_for_render


TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
RESUME_TEMPLATE = "resume.tex.j2"


class TemplateMissingExtraSectionsError(ValueError):
    """A resume has enabled, non-empty custom (extra) sections but the chosen
    template's source never references ``extra_sections`` — rendering would
    silently drop that content. We hard-fail with a clear message instead of
    emitting a PDF that quietly loses sections the user authored.

    Phase-1 template-incompatibility behavior (see the 2026-07-16 custom-resume-
    sections design doc): block rather than silently omit.

    Subclasses ``ValueError`` (not ``RuntimeError``) so it is a user-actionable
    "incompatible template" signal: every render call site that already maps
    ``ValueError`` to a clean HTTP 400 (base-resume PUT / render, application
    render) surfaces the actionable message instead of leaking an unhandled 500.
    The base-resume typed-edit PATCH deliberately keeps degrading it to a
    persisted ``render_error`` — see that handler."""


# A LaTeX line comment: an unescaped ``%`` to end of line. The negative
# lookbehind + even-backslash group anchors on a ``%`` preceded by an EVEN number
# of backslashes (zero or more ``\\`` pairs), so a literal ``\%`` (odd count) is
# NOT treated as a comment while ``\\%`` (escaped backslash, then comment) is.
_LATEX_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")


def _strip_latex_comments(source: str) -> str:
    """Drop LaTeX line comments so a token that appears only inside a comment
    does not read as live template code. Preserves escaped ``\\%`` and any
    backslashes that precede the comment marker."""
    return _LATEX_COMMENT_RE.sub(r"\1", source)


def source_references_extras(source: str) -> bool:
    """Does a template actually render custom (extra) sections?

    A naive ``"extra_sections" in source`` is wrong in two directions, so this
    (a) strips LaTeX comments first — a template that names ``extra_sections``
    only in a ``% ...`` comment does NOT render them, and must not read as
    supporting them (that would silently drop the user's sections); and
    (b) follows ``((* include 'partial' *))`` directives into bundled partials
    (reusing the registry's safe partial resolution) — a template that renders
    the extras block from an included partial DOES support them, and must not
    hard-fail. A template that never names ``extra_sections`` in any live
    (non-comment) location, inline or via a partial, cannot render them, so an
    extras-bearing resume must not be routed through it."""
    if "extra_sections" in _strip_latex_comments(source):
        return True
    # Lazy import: template_registry imports pdf_render at module load.
    from app.services import template_registry

    return any(
        "extra_sections" in _strip_latex_comments(text)
        for text in template_registry.iter_partial_sources(source)
    )


def _renderable_extra_sections(resume: dict[str, Any]) -> list[dict[str, Any]]:
    """Enabled extra sections that would produce visible output, i.e. an
    ``entries`` section with at least one (enabled) entry or a ``bullets``
    section with at least one bullet. Expects the post-``resume_for_render``
    shape, where disabled sections/entries are already filtered out. An enabled
    but empty section renders nothing, so it is not counted (and never trips the
    incompatibility guard)."""
    out: list[dict[str, Any]] = []
    for section in resume.get("extra_sections") or []:
        if section.get("type") == "entries" and section.get("entries"):
            out.append(section)
        elif section.get("type") == "bullets" and section.get("bullets"):
            out.append(section)
    return out


# pdfTeX places most interword spaces as positional kerns (not space glyphs) for
# many fonts, so strict PDF text extractors and some ATS/LLM parsers join words
# ("DataScientist"). \pdfinterwordspaceon makes pdfTeX emit a real space glyph
# from the bundled dummy-space font at every interword glue, restoring
# copy/paste and extraction fidelity for EVERY template and font. Injected at the
# compile boundary as CLI pre-input (pdfTeX runs a leading arg starting with "\"
# before reading the file) so no template can bypass it — even one without a
# standard \begin{document}.
_INTERWORD_SPACE = r"\pdfmapline{+dummy-space <dummy-space}\pdfinterwordspaceon"


def _pdflatex_argv(tex_path: Path, out_dir: Path, jobname: str) -> list[str]:
    """pdflatex argv that enables interword spaces, then \\input{tex_path}.

    ``-no-shell-escape`` is UNCONDITIONAL and has no opt-out parameter. Shell
    escape lets a document run host commands via ``\\write18``, and the only
    thing standing between generated text and that primitive is one
    ``|latex_escape`` in one template — a filter someone editing the shared
    ``_header.tex.j2`` partial could drop without knowing the flag existed.
    The cover-letter compile used to pass ``no_shell_escape=False`` for no
    recorded reason; it does not need it.
    """
    argv = ["pdflatex", "-no-shell-escape"]
    argv += [
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={out_dir}",
        f"-jobname={jobname}",
        f"{_INTERWORD_SPACE}\\input{{{tex_path}}}",
    ]
    return argv


LATEX_REPLACEMENTS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    return "".join(LATEX_REPLACEMENTS.get(char, char) for char in text)


# Escaping for a URL passed as the FIRST argument of hyperref's ``\href{url}{text}``.
# That argument is not read verbatim, but it needs far less escaping than body
# text — and full ``latex_escape`` actively CORRUPTS it: ``~`` -> ``\textasciitilde{}``
# rewrites the link target (a tilde in the path becomes literal command text).
# So escape only the characters that would otherwise break TeX's parse of the
# argument, and leave ``~ ^ &`` (and ``_``, ``$`` …) raw so the URL round-trips.
# Verified against hyperref by compile test: ``~ ^ & _`` compile raw inside
# ``\href``; ``\textbackslash{}`` blows the input stack there, so a literal
# backslash uses the primitive ``\char92`` instead. Display text keeps
# ``latex_escape`` (it is typeset, not a link target).
LATEX_URL_REPLACEMENTS = {
    "\\": r"\char92{}",
    "%": r"\%",
    "#": r"\#",
    "{": r"\{",
    "}": r"\}",
}


def latex_escape_url(value: Any) -> str:
    """Escape a URL for use as a hyperref ``\\href`` URL argument (see
    ``LATEX_URL_REPLACEMENTS``)."""
    if value is None:
        return ""

    text = str(value)
    return "".join(LATEX_URL_REPLACEMENTS.get(char, char) for char in text)


def _environment() -> SandboxedEnvironment:
    """Jinja environment for LaTeX templates. SANDBOXED — never plain ``Environment``.

    Template source is DATA, not trusted code: ``render_tex_from_source`` compiles
    ``Template.source`` straight from the database, and that column is writable by
    the web editor, the chat agent's template tools and MCP ``update_template_draft``.
    A plain ``Environment`` allows attribute traversal, so a template body reaching
    ``__init__.__globals__`` executes arbitrary Python in this process — reachable
    by importing someone else's template file, or by prompt-injecting the chat
    agent, which reads untrusted job descriptions and uploaded documents.

    The custom delimiters below are ergonomics (``{{ }}`` collides with LaTeX
    braces), NOT a security control. The sandbox is the control.
    """
    env = SandboxedEnvironment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        # This renders LaTeX, not HTML. HTML autoescaping must always be OFF
        # (latex_escape handles LaTeX escaping). select_autoescape() defaulted
        # autoescape ON for from_string templates, turning data "&" into "&amp;".
        autoescape=False,
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["latex_escape"] = latex_escape
    env.filters["latex_escape_url"] = latex_escape_url
    env.filters["format_date"] = format_date
    return env


def render_tex_from_source(
    source: str,
    resume_data: dict[str, Any] | ResumeData,
    formatting: dict[str, Any] | None = None,
    *,
    enforce_extras_support: bool = False,
) -> str:
    """Render ``source`` against ``resume_data``.

    ``enforce_extras_support`` is the render-time template-incompatibility gate:
    when True and the resume has enabled, non-empty custom sections that the
    template source cannot render, raise ``TemplateMissingExtraSectionsError``
    rather than silently dropping them. It defaults to False so the low-level
    primitive stays permissive — template *certification*
    (``compile_against_sample``) deliberately renders the sentinel-bearing sample
    through templates that lack extra-section support to *measure* capability,
    and must not hard-fail. The real render entry point (``render_document``) opts in.
    """
    raw = (
        resume_data.model_dump()
        if isinstance(resume_data, ResumeData)
        else resume_data
    )
    normalized = resume_for_render(raw)
    if enforce_extras_support:
        renderable = _renderable_extra_sections(normalized)
        if renderable and not source_references_extras(source):
            keys = ", ".join(str(s.get("key", "?")) for s in renderable)
            raise TemplateMissingExtraSectionsError(
                "This resume has custom section(s) "
                f"[{keys}] but the selected template cannot render custom "
                "sections, so they would be silently dropped. Choose a "
                "template that supports custom sections, or disable those "
                "sections before rendering."
            )
    resume = ResumeData.model_validate(normalized)
    fmt = merge_formatting(formatting)
    template = _environment().from_string(source)
    return template.render(resume=resume, fmt=fmt)


def compile_pdf(
    tex_text: str, out_dir: Path, stem: str = "resume", *, document: str = ""
) -> Path:
    """Write ``tex_text`` beside its PDF and compile it with pdflatex.

    The ONE pdflatex entry point. It used to have a cover-letter twin that
    differed in exactly one argument — ``-shell-escape``, i.e. permission to run
    host commands — so the twin was both a duplicate and the weaker of the two.
    Removing that flag left the bodies identical; keep it that way, and pass
    ``document`` if a failure needs naming in the error.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{stem}.tex"
    pdf_path = out_dir / f"{stem}.pdf"
    tex_path.write_text(tex_text, encoding="utf-8")

    result = subprocess.run(
        _pdflatex_argv(tex_path, out_dir, stem),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not pdf_path.exists():
        label = f"pdflatex failed ({document})" if document else "pdflatex failed"
        raise RuntimeError(
            f"{label}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return pdf_path


# --- Typst engine ------------------------------------------------------------
# Second render engine, added alongside the LaTeX one rather than replacing it;
# the retirement sequence is tracked in SYSTEM.md §13 (`typst-default-flip` →
# `latex-render-path` → `texlive-layer`, strictly in that order).
# A typst template's `source` IS the .typ text (no Jinja
# layer, no escape tables); data flows via typst-py sys_inputs as JSON strings,
# read in-template as `json(bytes(sys.inputs.resume))` / `...sys_inputs.fmt`.

def typst_source_references_extras(source: str) -> bool:
    """Typst analogue of source_references_extras: does the .typ text reference
    extra_sections in LIVE (non-comment) code? Uses the shared comment/string
    aware scanner (typst_compiler.strip_typst_comments), so extra_sections named
    only in a comment is not credited (which would silently drop the user's
    sections), a `//` inside a string literal does not eat a real reference on
    the same line, and nested `/* /* */ */` is handled. Plain source heuristic;
    `typst query` AST introspection is a recorded Phase-2 item."""
    return "extra_sections" in typst_compiler.strip_typst_comments(source)


def _preformat_dates(resume: dict[str, Any], mode: str) -> None:
    """Apply fmt.date_format server-side for the Typst path (there is no Jinja
    filter layer). Mirrors every `|format_date` call site in resume.tex.j2.
    Mutates in place; None stays None so in-template `!= none` checks work."""

    def _fmt(value: Any) -> Any:
        return None if value is None else format_date(value, mode)

    for exp in resume.get("experience") or []:
        exp["start_date"] = _fmt(exp.get("start_date"))
        exp["end_date"] = _fmt(exp.get("end_date"))
    for project in resume.get("projects") or []:
        project["date"] = _fmt(project.get("date"))
    for edu in resume.get("education") or []:
        edu["start_date"] = _fmt(edu.get("start_date"))
        edu["end_date"] = _fmt(edu.get("end_date"))
        edu["graduation_date"] = _fmt(edu.get("graduation_date"))
    for section in resume.get("extra_sections") or []:
        for entry in section.get("entries") or []:
            entry["date"] = _fmt(entry.get("date"))


def _coerce_blank_to_none(value: Any) -> Any:
    """Recursively map empty / whitespace-only STRINGS to None through dicts and
    lists. The typed-edit editor writes '' (not null) for cleared optional fields
    (location, phone, tech, gpa, subheading, summary, ...); the LaTeX path treats
    '' as falsy via Jinja truthiness, but the Typst template guards on `!= none`.
    Coercing at the data layer (once, here) matches LaTeX truthiness for every
    guard site at once, so a cleared field never leaves a dangling separator, a
    stray en dash, or an empty section heading + divider."""
    if isinstance(value, str):
        return None if value.strip() == "" else value
    if isinstance(value, dict):
        return {k: _coerce_blank_to_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_blank_to_none(v) for v in value]
    return value


def build_typst_sys_inputs(
    source: str,
    resume_data: dict[str, Any] | ResumeData,
    formatting: dict[str, Any] | None = None,
    *,
    enforce_extras_support: bool = False,
) -> dict[str, str]:
    """Typst analogue of render_tex_from_source: normalize + validate the
    resume, merge formatting, serialize both as JSON strings for sys_inputs."""
    raw = (
        resume_data.model_dump()
        if isinstance(resume_data, ResumeData)
        else resume_data
    )
    normalized = resume_for_render(raw)
    if enforce_extras_support:
        renderable = _renderable_extra_sections(normalized)
        if renderable and not typst_source_references_extras(source):
            keys = ", ".join(str(s.get("key", "?")) for s in renderable)
            raise TemplateMissingExtraSectionsError(
                "This resume has custom section(s) "
                f"[{keys}] but the selected template cannot render custom "
                "sections, so they would be silently dropped. Choose a "
                "template that supports custom sections, or disable those "
                "sections before rendering."
            )
    fmt = merge_formatting(formatting)
    resume = ResumeData.model_validate(normalized).model_dump(mode="json")
    # Match LaTeX Jinja truthiness: '' / whitespace-only optional strings become
    # None so the Typst template's `!= none` guards suppress them (no dangling
    # separators / empty sections). Done once at the data layer, not per-guard.
    resume = _coerce_blank_to_none(resume)
    _preformat_dates(resume, fmt.date_format)
    return {"resume": json.dumps(resume), "fmt": fmt.model_dump_json()}


def _compile_typst_file(
    typ_path: Path, pdf_path: Path, sys_inputs: dict[str, str] | None
) -> None:
    """Compile ``typ_path`` -> ``pdf_path`` with the pdflatex branch's
    RuntimeError contract. Hardened (see app.services.typst_compiler): a
    wall-clock timeout, a fail-closed reject of remote (@preview) package
    imports, and a per-render staging root so a template cannot ``read()`` other
    renders' sources. The message carries typst's located diagnostic."""
    source = typ_path.read_text(encoding="utf-8")
    typst_compiler.compile_typst(
        source=source,
        input_name=typ_path.name,
        output=pdf_path,
        font_paths=[str(p) for p in settings.typst_font_paths],
        sys_inputs=sys_inputs or {},
    )
    if not pdf_path.exists():
        raise RuntimeError("typst failed\nno PDF produced")


def compile_typst_pdf(
    typ_text: str,
    out_dir: Path,
    stem: str = "resume",
    *,
    sys_inputs: dict[str, str],
) -> Path:
    """Typst counterpart of compile_pdf: writes `stem.typ` beside `stem.pdf`
    (same artifact layout as .tex) and compiles in-process."""
    out_dir.mkdir(parents=True, exist_ok=True)
    typ_path = out_dir / f"{stem}.typ"
    pdf_path = out_dir / f"{stem}.pdf"
    typ_path.write_text(typ_text, encoding="utf-8")
    _compile_typst_file(typ_path, pdf_path, sys_inputs)
    return pdf_path


@dataclass(frozen=True)
class RenderedDoc:
    """Engine-tagged, ready-to-compile document. For latex, source_text is the
    rendered TeX; for typst it is the template source verbatim (data flows via
    sys_inputs at compile time)."""

    engine: str  # "latex" | "typst"
    source_text: str
    sys_inputs: dict[str, str] | None = None

    @property
    def source_suffix(self) -> str:
        return ".typ" if self.engine == "typst" else ".tex"


def render_document(
    resume_data: dict[str, Any] | ResumeData,
    *,
    template_id: str | None = None,
    session=None,
    formatting: dict[str, Any] | None = None,
) -> RenderedDoc:
    """Engine-dispatching render half of the compile boundary. The latex branch
    resolves the template, applies the 4-layer formatting merge, and enforces
    extras support before rendering."""
    if session is None:
        source = (TEMPLATE_DIR / RESUME_TEMPLATE).read_text(encoding="utf-8")
        return RenderedDoc(
            "latex",
            render_tex_from_source(
                source, resume_data, formatting=formatting, enforce_extras_support=True
            ),
        )

    from app.services import template_registry  # lazy import to avoid a cycle

    tmpl = template_registry.get_usable_template(template_id, session)
    merged = merge_formatting(tmpl.default_formatting, formatting).model_dump()
    if tmpl.engine == "typst":
        sys_inputs = build_typst_sys_inputs(
            tmpl.source, resume_data, merged, enforce_extras_support=True
        )
        return RenderedDoc("typst", tmpl.source, sys_inputs)
    return RenderedDoc(
        "latex",
        render_tex_from_source(
            tmpl.source, resume_data, formatting=merged, enforce_extras_support=True
        ),
    )


def compile_document(
    doc: RenderedDoc, out_dir: Path, stem: str = "resume"
) -> tuple[Path, Path]:
    """Compile a RenderedDoc into out_dir; returns (source_path, pdf_path). The
    source artifact is written beside the PDF for both engines."""
    if doc.engine == "typst":
        pdf_path = compile_typst_pdf(doc.source_text, out_dir, stem, sys_inputs=doc.sys_inputs)
        return out_dir / f"{stem}.typ", pdf_path
    pdf_path = compile_pdf(doc.source_text, out_dir, stem)  # writes stem.tex itself
    return out_dir / f"{stem}.tex", pdf_path


def render_and_compile(
    resume_data: dict[str, Any] | ResumeData,
    out_tex_path: Path,
    out_pdf_path: Path,
    *,
    template_id: str | None = None,
    session=None,
    formatting: dict[str, Any] | None = None,
) -> Path:
    """Render + compile to explicit paths. Returns the ACTUAL source-artifact
    path: `out_tex_path` for latex, `out_tex_path.with_suffix('.typ')` for
    typst — callers persist it in their existing tex_path column (the column
    stores whichever source artifact the engine produced; no schema change)."""
    doc = render_document(
        resume_data, template_id=template_id, session=session, formatting=formatting
    )
    source_path = out_tex_path.with_suffix(doc.source_suffix)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(doc.source_text, encoding="utf-8")

    if doc.engine == "typst":
        _compile_typst_file(source_path, out_pdf_path, doc.sys_inputs)
        return source_path

    result = subprocess.run(
        _pdflatex_argv(source_path, out_pdf_path.parent, out_pdf_path.stem),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not out_pdf_path.exists():
        raise RuntimeError(
            "pdflatex failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return source_path


def render_cover_letter_tex(
    *,
    contact: dict[str, Any],
    body: str,
    today: _date,
) -> str:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    template = _environment().get_template("cover_letter.tex.j2")
    # The cover letter includes the shared _header.tex.j2 partial, which reads
    # fmt.* (e.g. fmt.header_align). Pass default formatting so the header keeps
    # its historical centered layout and does not raise UndefinedError.
    return template.render(
        contact=contact,
        body_paragraphs=paragraphs,
        today_date=today.strftime("%B %-d, %Y"),
        fmt=merge_formatting(None),
    )


def compile_cover_letter_pdf(
    tex_text: str,
    out_dir: Path,
    stem: str = "cover_letter",
) -> Path:
    """Cover-letter compile. A thin alias for `compile_pdf` — see its docstring
    for why the two are no longer separate implementations. Kept as a named
    entry point because callers read better for it, and because the
    `latex-render-path` ledger row (SYSTEM §13) tracks it by name."""
    return compile_pdf(tex_text, out_dir, stem, document="cover letter")
