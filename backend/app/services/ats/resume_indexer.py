from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from app.services.ats import degrees
from app.services.ats.matching import normalize_term
from app.services import resume_dates
from app.services.resume_projects import extra_entry_live, extra_section_live

if TYPE_CHECKING:
    from app.services.ats.config import AtsConfig

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# Shared with the health gate — see services/resume_dates. Two definitions of
# "still here" previously disagreed, so the ATS engine scored a role as current
# while gate S3 called the same end date unparseable.
_CURRENT_TOKENS = resume_dates.CURRENT_TOKENS


def parse_month_year(value: str | None) -> date | None:
    """Parse "Jul 2023" → date(2023, 7, 1). "Present"/None/garbage → None.

    Never raises — this runs on user-editable application customized_json.
    Year-only strings ("2019") deliberately return None: the data model uses
    "Mon YYYY", and an undated entry earning no recency credit is the honest
    default.
    """
    if not value:
        return None
    if resume_dates.is_current(value):
        return None
    parts = str(value).strip().lower().split()
    if len(parts) != 2:
        return None
    month = _MONTHS.get(parts[0][:3])
    if month is None or not parts[1].isascii() or not parts[1].isdigit():
        return None
    try:
        return date(int(parts[1]), month, 1)
    except ValueError:  # year out of range, e.g. "Jun 20233" or "Jul 0"
        return None


@dataclass(frozen=True)
class SkillsItem:
    raw: str
    norm: str
    category: str


@dataclass(frozen=True)
class IndexedEntry:
    section: str          # "experience" | "projects" | "extra" | "credential"
    index: int            # index within the ORIGINAL section list (for edit ops)
    label: str            # "DataCo — Data Scientist" / project name
    text: str             # normalized prose: role/name + bullets + tech
    last_date: date | None
    is_current: bool
    date_parse_ok: bool
    # Stable identity for an extra section. Core entries leave this unset.
    section_key: str | None = None
    # True for an unstructured KEYWORD CHANNEL: content that scores as evidence
    # but must NOT corroborate the skills-stuffing lint, because letting it would
    # trivially defeat that integrity check. Two users: a flat `bullets` custom
    # section (finding F#12) and the certifications list. Structured `entries`
    # extras — which SYSTEM.md §4 allows to affect skills-item corroboration —
    # leave this False.
    is_keyword_channel: bool = False


@dataclass(frozen=True)
class ResumeIndex:
    skills_items: list[SkillsItem]
    entries: list[IndexedEntry]
    summary: str
    recent_role: str      # role of the most recent enabled experience entry
    contact_ok: bool
    total_experience_years: float
    sections_present: dict[str, bool]
    # Highest parseable degree level, or None. Read ONLY by the advisory l4_gate
    # — it is not evidence and no layer that produces a subscore may consume it.
    degree_level: int | None = None


def _entry_text(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, list):
            chunks.extend(str(p) for p in part)
        elif part:
            chunks.append(str(part))
    return normalize_term(" ".join(chunks))


def _merged_years(spans: list[tuple[date, date]]) -> float:
    if not spans:
        return 0.0
    spans = sorted(spans)
    total_days = 0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total_days += (cur_end - cur_start).days
            cur_start, cur_end = start, end
    total_days += (cur_end - cur_start).days
    return total_days / 365.25


def _index_experience(
    resume: dict[str, Any], as_of: date
) -> tuple[list[IndexedEntry], list[tuple[date, date]], str]:
    """Experience entries plus the two signals only this section produces:
    merged tenure spans and the most-recent role."""
    entries: list[IndexedEntry] = []
    spans: list[tuple[date, date]] = []
    recent_role = ""
    recent_key: tuple[bool, date] | None = None

    for i, exp in enumerate(resume.get("experience") or []):
        if exp.get("enabled") is False:
            continue
        start = parse_month_year(exp.get("start_date"))
        # Currency comes from the RAW end_date field: only a missing/empty value
        # or an explicit "Present"-style token means current. A non-empty
        # end_date that fails to parse is a data problem, not a current role.
        raw_end = exp.get("end_date")
        raw_end_text = str(raw_end).strip() if raw_end else ""
        # Whole-string match, not first-token: "Present" is current, but a value
        # that merely STARTS with one of these words is not.
        raw_says_current = not raw_end_text or resume_dates.is_current(raw_end_text)
        if raw_says_current:
            is_current = start is not None
            last = as_of if is_current else None
            date_ok = start is not None
        else:
            end = parse_month_year(raw_end)
            is_current = False
            last = end
            date_ok = start is not None and end is not None
        if start is not None and last is not None:
            span_end = min(last, as_of)  # never count time beyond as_of
            if span_end < start:
                date_ok = False  # reversed/future-start span: no years credit
            else:
                spans.append((start, span_end))
        entries.append(IndexedEntry(
            section="experience", index=i,
            label=f"{exp.get('company', '')} — {exp.get('role', '')}",
            text=_entry_text(exp.get("role"), exp.get("bullets")),
            last_date=last, is_current=is_current, date_parse_ok=date_ok,
        ))
        if last is not None:
            key = (is_current, last)
            if recent_key is None or key > recent_key:
                recent_key = key
                recent_role = str(exp.get("role") or "")
    return entries, spans, recent_role


def _index_projects(resume: dict[str, Any]) -> list[IndexedEntry]:
    entries: list[IndexedEntry] = []
    for i, proj in enumerate(resume.get("projects") or []):
        if proj.get("enabled") is False:
            continue
        proj_date = parse_month_year(proj.get("date"))
        entries.append(IndexedEntry(
            section="projects", index=i,
            label=str(proj.get("name") or f"project {i}"),
            text=_entry_text(proj.get("name"), proj.get("tech"), proj.get("bullets")),
            last_date=proj_date, is_current=False, date_parse_ok=proj_date is not None,
        ))
    return entries


def _index_extra_sections(
    resume: dict[str, Any], config: "AtsConfig"
) -> list[IndexedEntry]:
    # Phase-2 custom-section evidence is deliberately narrower than the render
    # model. The versioned config explicitly chooses searchable fields and the
    # layers assign these chunks a separate undated evidence tier. In
    # particular, display titles, links, locations and user-entered dates do not
    # become evidence, employment recency, recent-role, or tenure signals.
    # FIX F#2: feature-off fallback — a legacy/custom weights.yaml lacking the
    # extra_section_evidence key must not crash indexing. With no configured
    # evidence fields, entry_fields is empty (entry text -> "") and bullets are
    # disabled, so no extra entry is indexed and the engine behaves pre-phase-2,
    # exactly matching resolve_evidence's extras-off path.
    extras_cfg = config.extras_config()
    evidence_fields = extras_cfg.get("evidence_fields") or {}
    entry_fields = evidence_fields.get("entries") or []
    bullets_enabled = "bullets" in (evidence_fields.get("bullets") or [])
    entries: list[IndexedEntry] = []
    for section in resume.get("extra_sections") or []:
        # extra_section_live / extra_entry_live are the shared "is this custom
        # content live?" predicate the gap placement-target builder also uses, so
        # the ATS-evidence view and the placement-target view never disagree
        # (dict-guarded; enabled omitted/None -> live, matching the render view).
        if not extra_section_live(section):
            continue
        section_key = str(section.get("key") or "")
        title = str(section.get("title") or section_key or "extra section")
        if section.get("type") == "entries":
            for i, entry in enumerate(section.get("entries") or []):
                if not extra_entry_live(entry):
                    continue
                text = _entry_text(*(entry.get(field) for field in entry_fields))
                if not text:
                    continue
                entries.append(IndexedEntry(
                    section="extra",
                    index=i,
                    label=str(entry.get("heading") or f"{title} entry {i + 1}"),
                    text=text,
                    last_date=None,
                    is_current=False,
                    date_parse_ok=True,
                    section_key=section_key,
                ))
        elif section.get("type") == "bullets" and bullets_enabled:
            text = _entry_text(section.get("bullets"))
            if text:
                entries.append(IndexedEntry(
                    section="extra",
                    index=0,
                    label=title,
                    text=text,
                    last_date=None,
                    is_current=False,
                    date_parse_ok=True,
                    section_key=section_key,
                    is_keyword_channel=True,  # unstructured: no stuffing-lint credit
                ))
    return entries


def _index_credentials(
    resume: dict[str, Any], config: "AtsConfig"
) -> list[IndexedEntry]:
    # Credential evidence. Deliberately narrower than the extras channel: only the
    # certification STRING is evidence. Each cert is its own undated entry on a
    # dedicated `credential` section, which keeps it out of every dated code path
    # by construction — `dates_ok` filters section == "experience", tenure/spans
    # and recent_role are built from experience only, and sections_present has no
    # credential key. Education is NOT indexed here (see weights.yaml).
    # Feature-off fallback (extras F#2 pattern): no configured block -> no entries.
    credentials_cfg = config.credentials_config()
    credential_tier = credentials_cfg.get("placement_tier")
    credential_fields = (credentials_cfg.get("evidence_fields") or {}).get("certifications") or []
    entries: list[IndexedEntry] = []
    if credential_tier and "item" in credential_fields:
        for i, cert in enumerate(resume.get("certifications") or []):
            text = _entry_text(cert)
            if not text:
                continue
            entries.append(IndexedEntry(
                section="credential",
                index=i,
                label=str(cert),
                text=text,
                last_date=None,
                is_current=False,
                date_parse_ok=True,
                # a credential list is a keyword channel: it must not corroborate
                # the skills-stuffing lint (same rule as a flat extra section)
                is_keyword_channel=True,
            ))
    return entries


def index_resume(
    resume: dict[str, Any],
    *,
    as_of: date,
    config: "AtsConfig | None" = None,
) -> ResumeIndex:
    # Direct indexer callers get the same versioned behavior as score_resume;
    # engine callers pass their explicit config so custom/test configs cannot
    # silently mix indexing semantics with the process-global config.
    if config is None:
        from app.services.ats.config import load_config

        config = load_config()
    skills_items = [
        SkillsItem(raw=str(item), norm=normalize_term(str(item)), category=str(group.get("category", "")))
        for group in resume.get("skills") or []
        for item in group.get("items") or []
    ]

    exp_entries, spans, recent_role = _index_experience(resume, as_of)
    entries = [
        *exp_entries,
        *_index_projects(resume),
        *_index_extra_sections(resume, config),
        *_index_credentials(resume, config),
    ]

    contact = resume.get("contact") or {}
    # Phone is deliberately required here even though the resume schema allows
    # omitting it: ATS parsers score contact-block completeness, so the
    # completeness check is stricter than the schema.
    return ResumeIndex(
        skills_items=skills_items,
        entries=entries,
        summary=normalize_term(str(resume.get("summary") or "")),
        recent_role=recent_role,
        contact_ok=bool(contact.get("name") and contact.get("email") and contact.get("phone")),
        total_experience_years=_merged_years(spans),
        sections_present={
            "summary": bool(resume.get("summary")),
            "skills": bool(skills_items),
            "experience": any(e.section == "experience" for e in entries),
            "education": bool(resume.get("education")),
        },
        degree_level=degrees.resume_degree_level(resume.get("education") or []),
    )
