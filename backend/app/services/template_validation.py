from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.template import Template
from app.schemas.template import validate_template_id
from app.services import pdf_render

SAMPLE_RESUME: dict = {
    "contact": {
        "name": "Jordan Sample",
        "email": "jordan.sample@example.com",
        "phone": "+1 (555) 010-1234",
        "location": "San Francisco, CA",
        "linkedin": "linkedin.com/in/jordansample",
        "github": "github.com/jordansample",
        "website": "jordansample.dev",
    },
    "summary": (
        "Senior software engineer with experience building reliable backend "
        "systems and data pipelines."
    ),
    "skills": [
        {"category": "Languages", "items": ["Python", "Go", "SQL"]},
        {"category": "Infrastructure", "items": ["PostgreSQL", "Docker", "AWS"]},
    ],
    "experience": [
        {
            "company": "Acme Corp",
            "role": "Senior Software Engineer",
            "location": "San Francisco, CA",
            "start_date": "2021",
            "end_date": "Present",
            "bullets": [
                "Built a high-throughput ingestion service handling 10M events/day.",
                "Reduced API p99 latency by 40% through query and caching work.",
            ],
        },
        {
            "company": "Globex",
            "role": "Software Engineer",
            "location": "Remote",
            "start_date": "2018",
            "end_date": "2021",
            "bullets": [
                "Led migration of a monolith to modular services.",
            ],
        },
    ],
    "projects": [
        {
            "name": "Maestro CS",
            "enabled": True,
            "tech": "Python, FastAPI, LaTeX",
            "date": "2024",
            "bullets": [
                "Automated tailoring of resumes to job descriptions.",
            ],
        },
    ],
    "education": [
        {
            "institution": "State University",
            "degree": "B.S. Computer Science",
            "field": "Computer Science",
            "location": "Berkeley, CA",
            "start_date": "2014",
            "end_date": "2018",
            # Prefixed exactly like the real base resumes ("GPA 4.0/4.0"); the
            # sentinel guards against a template re-labeling it ("GPA: GPA ...").
            "gpa": "GPA 3.8/4.0",
            "coursework": ["Algorithms", "Distributed Systems"],
            "bullets": ["Teaching assistant for introductory programming."],
        },
    ],
    "certifications": ["AWS Certified Solutions Architect"],
    # Sentinel custom sections — one of each union variant. Their sole purpose is
    # template certification: a template that renders custom sections reproduces
    # these unmistakable phrases in the extracted PDF text; a template that omits
    # the extra_sections block silently drops them, which build_parse_report
    # detects as extra_sections_supported=False. The phrases are deliberately
    # unique so they cannot be confused with core-section content.
    "extra_sections": [
        {
            "key": "publications",
            "title": "Publications",
            "type": "entries",
            "entries": [
                {
                    "heading": "Sentinel Publication Alpha",
                    "subheading": "Journal of Sentinels",
                    "location": "Remote",
                    "date": "2024",
                    "link": "https://example.com/sentinel-paper",
                    "bullets": ["Sentinel entry bullet detail."],
                }
            ],
        },
        {
            "key": "awards",
            "title": "Awards",
            "type": "bullets",
            "bullets": ["Sentinel award bullet detail, 2024"],
        },
    ],
}


def _preview_path(template_id: str) -> Path:
    """Where this template's preview PDF is written. Never outside that folder.

    The caller mkdir's this path's parent and `shutil.copy`s into it, so before
    the id was validated anywhere but the REST schema, a stored id of
    `../../logs/pwned` wrote a PDF outside the preview root (SEC-05).

    Two checks, and the second is not redundant: `validate_template_id` says the
    id is a slug, and the `relative_to` says the resolved path is still under
    the root. If the alphabet ever widens, the containment check is what keeps
    holding — it is the same resolve-then-`relative_to` that
    `template_registry._resolve_partial` uses for bundled partials.
    """
    validate_template_id(template_id)
    root = (Path(settings.base_resumes_dir) / "template_previews").resolve()
    candidate = (root / f"{template_id}.pdf").resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:  # pragma: no cover - unreachable while the slug holds
        raise ValueError(f"preview path escapes its directory: {template_id!r}") from exc
    return candidate


# Multi-word phrases from SAMPLE_RESUME's CORE sections (contact name,
# experience, education) — the parts essentially every resume template renders.
# A word-joining template damages every multi-word phrase, so if these survive a
# strict extractor the template preserves word boundaries (see the interword
# space fix in pdf_render). Deliberately no phrases from optional sections
# (certifications/coursework): a well-spaced template that simply omits a section
# must not be mistaken for a broken one. Line wraps are fine — whitespace is
# normalised before matching.
PARSE_FIDELITY_PROBES: list[str] = [
    "Jordan Sample",  # contact name
    "Senior Software Engineer",  # experience role
    "Software Engineer",  # experience role
    "Acme Corp",  # experience company
    "Computer Science",  # education degree/field
    "State University",  # education institution
]

# S2's template half: does contact survive into the extracted body text?
# Email only — phone formats vary too much across templates to probe reliably.
CONTACT_PROBES: list[str] = ["jordan.sample@example.com"]

# S4: are the standard section header strings present in the extracted text?
# Recorded in the parse report (headers_missing) — a serious gate, not part of
# the fatal word-boundary certification. Letterspaced/smallcaps headers can
# legitimately fail extraction; S4 is waivable for that reason.
HEADER_PROBES: list[str] = ["experience", "education", "skills"]

# Custom-section capability probes: one phrase from the entries-style sentinel
# heading, one from an entries-style bullet, and one from the bullets-style
# section. If ALL survive extraction the template renders both custom-section
# styles; if they are absent the template omitted the extra_sections block and
# would SILENTLY drop a real resume's custom sections. Reported as
# extra_sections_supported — a separate capability signal, NOT part of
# parse_certified (a template may legitimately certify for core-only resumes).
# Deliberately kept OUT of HEADER_PROBES: a core-only-ready template must not be
# failed for lacking custom-section support.
EXTRA_SECTION_PROBES: list[str] = [
    "sentinel publication alpha",  # entries-style heading
    "sentinel entry bullet detail",  # entries-style bullet
    "sentinel award bullet detail",  # bullets-style item
]


def _extract_normalized(pdf_path: Path) -> str | None:
    """Extract `pdf_path` with pdfplumber (strict) → whitespace-normalized,
    lowercased text, or None if the extractor is unavailable or the PDF unreadable.
    None means NOT ASSESSED — never treat it as a pass."""
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(pdf_path) as doc:
            text = " ".join((page.extract_text() or "") for page in doc.pages)
    except Exception:  # noqa: BLE001 — unreadable PDF = not assessed, never certified
        return None
    return " ".join(text.split()).lower()


def check_parse_fidelity(
    pdf_path: Path, probes: list[str] | None = None
) -> tuple[bool | None, list[str]]:
    """Extract `pdf_path` and report whether EVERY probe's word boundaries survive.

    Certified only when all probes survive — word-joining damage is systematic,
    and a template that eats a third of its phrases is not certified. Degrades
    CLOSED: (None, []) when pdfplumber is unavailable or the PDF can't be read.
    """
    probes = probes if probes is not None else PARSE_FIDELITY_PROBES
    normalized = _extract_normalized(pdf_path)
    if normalized is None:
        return None, []
    missing = [p for p in probes if p.lower() not in normalized]
    return (not missing), missing


def build_parse_report(pdf_path: Path) -> dict | None:
    """Full extraction report for a compiled template preview, or None when the
    extractor couldn't run (not assessed)."""
    normalized = _extract_normalized(pdf_path)
    if normalized is None:
        return None
    try:
        import pdfplumber
        version = getattr(pdfplumber, "__version__", "unknown")
    except ImportError:  # pragma: no cover — _extract_normalized already returned text
        version = "unknown"
    missing = [p for p in PARSE_FIDELITY_PROBES if p.lower() not in normalized]
    extra_missing = [p for p in EXTRA_SECTION_PROBES if p not in normalized]
    return {
        "extractor": "pdfplumber",
        "extractor_version": version,
        "missing": missing,
        "email_ok": all(p.lower() in normalized for p in CONTACT_PROBES),
        "headers_missing": [h for h in HEADER_PROBES if h not in normalized],
        # Capability signal (NOT part of parse_certified): does the template
        # render the sentinel custom sections in SAMPLE_RESUME? A template that
        # omits extra_sections extracts none of the sentinel phrases → False.
        "extra_sections_supported": not extra_missing,
        "extra_sections_missing": extra_missing,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def compile_against_sample(
    source: str,
    keep_pdf_at: Path | None = None,
    default_formatting: dict | None = None,
    engine: str = "latex",
) -> str | None:
    """Render `source` against SAMPLE_RESUME and compile it with the template's
    engine (pdflatex subprocess, or in-process typst via sys_inputs). Returns
    None on success (copying the PDF to `keep_pdf_at` when given), or the error
    text on failure. The pdfplumber probe gate downstream is engine-neutral —
    it operates on the produced PDF."""
    if engine == "typst":
        try:
            sys_inputs = pdf_render.build_typst_sys_inputs(
                source, SAMPLE_RESUME, default_formatting
            )
        except Exception as exc:  # noqa: BLE001
            return f"render error: {exc}"[-2000:]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            try:
                pdf_render.compile_typst_pdf(
                    source, out_dir, stem="preview", sys_inputs=sys_inputs
                )
            except Exception as exc:  # noqa: BLE001
                return str(exc)[-2000:]
            if keep_pdf_at is not None:
                keep_pdf_at.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(out_dir / "preview.pdf", keep_pdf_at)
        return None

    # ---- latex (unchanged) ----
    try:
        tex = pdf_render.render_tex_from_source(
            source, SAMPLE_RESUME, formatting=default_formatting
        )
    except Exception as exc:  # noqa: BLE001
        return f"render error: {exc}"[-2000:]

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        try:
            pdf_render.compile_pdf(tex, out_dir, stem="preview")
        except Exception as exc:  # noqa: BLE001
            return str(exc)[-2000:]
        if keep_pdf_at is not None:
            keep_pdf_at.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(out_dir / "preview.pdf", keep_pdf_at)
    return None


def validate_template(template_id: str, session: Session) -> dict:
    row = session.get(Template, template_id)
    if row is None:
        raise LookupError(f"Template not found: {template_id}")

    preview = _preview_path(template_id)
    error = compile_against_sample(
        row.source,
        keep_pdf_at=preview,
        default_formatting=row.default_formatting,
        engine=row.engine,
    )
    if error is not None:
        row.status = "draft"
        row.last_error = error
        row.validated_at = None
        row.parse_certified = None
        row.parse_report_json = None
        session.commit()
        return {"ok": False, "error": row.last_error, "parse_certified": None, "parse_report": None}

    row.status = "ready"
    row.validated_at = datetime.now(UTC)
    row.last_error = None
    report = build_parse_report(preview)
    if report is None:
        row.parse_certified = None
        row.parse_report_json = None
    else:
        row.parse_certified = not report["missing"]
        row.parse_report_json = report
    session.commit()
    return {"ok": True, "error": None, "parse_certified": row.parse_certified, "parse_report": row.parse_report_json}
