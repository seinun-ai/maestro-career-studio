"""Pure-JSON structure/content gates and detectors (framework v2).

Gate dicts: {"id", "tier": "fatal"|"serious", "status": "pass"|"fail"|"not_assessed",
"label", "detail"}. S1/S2/S4 come from the template certification (see
resume_lint.py assembly); this module holds everything computable from the
resume JSON alone.
"""
import re

from app.services import resume_dates
from app.services.health_zones import (
    enabled_entries,
    now_ym,
    to_index,
    parse_ym,
    total_experience_months,
)

PLACEHOLDER = re.compile(
    r"(?<!\w)\[[^\]]*\]|\bTODO\b|\bTBD\b|\bXXX?\b|XX%|lorem ipsum",
    re.IGNORECASE,
)
YEARS_CLAIM = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?", re.IGNORECASE)
CLAIM_SLACK_YEARS = 1.0
GAP_THRESHOLD_MONTHS = 6


# Static gate coaching is part of the report contract. Keep it here so every
# gate serializer and the agent-facing findings use the same explanation.
GATE_COPY: dict[str, dict[str, str]] = {
    "S1": {
        "why": "If the PDF drops or changes content, automated screeners and recruiters evaluate a different resume than the one you wrote. This blocks tailoring until fixed or waived.",
        "fix_hint": "Use a template that preserves every section and bullet in extracted PDF text, then validate it again.",
    },
    "S2": {
        "why": "A resume that loses its email address in the PDF gives recruiters no reliable way to contact you. This blocks tailoring until fixed or waived.",
        "fix_hint": "Add a valid email address and use a template that keeps it readable in extracted PDF text.",
    },
    "S3": {
        "why": "Automated screeners read your dates to compute tenure and recency; a date they can't parse can erase that credit.",
        "fix_hint": "Write dates like 'Jan 2022' or '2022'. For your current role, leave the end date blank or write 'Present'. Both are understood.",
    },
    "S4": {
        "why": "Standard section headings help screeners classify your experience, education, and skills instead of merging or skipping them.",
        "fix_hint": "Use recognizable headings such as 'Experience', 'Education', and 'Technical Skills', then validate the template again.",
    },
    "S5": {
        "why": "Placeholder text makes the resume look unfinished and can expose drafting notes to employers.",
        "fix_hint": "Replace every TODO, TBD, bracketed prompt, or sample value with final text, or remove it.",
    },
    "C1": {
        "why": "The summary and most recent role carry extra weight; weak evidence there can hide stronger work farther down the resume.",
        "fix_hint": "Strengthen the summary or newest relevant role with specific actions and outcomes.",
    },
    "C2": {
        "why": "A years-of-experience claim that exceeds the dated work history can undermine trust in the rest of the resume.",
        "fix_hint": "Add the missing dated role, correct the summary's years claim, or waive the gate with a recorded reason if the dates intentionally omit work.",
    },
}

def gate_copy(gate_id: str) -> dict[str, str]:
    """Return the report-contract coaching copy for one known health gate."""
    return GATE_COPY[gate_id]


def _gate(gate_id: str, tier: str, status: str, label: str, detail: str = "") -> dict:
    return {
        "id": gate_id,
        "tier": tier,
        "status": status,
        "label": label,
        "detail": detail,
        **gate_copy(gate_id),
    }


def gate_dates(resume: dict) -> dict:
    """S3 — every dated enabled experience role has readable dates.

    An absent start date is a legal representation (schemas/resume.py:
    ``ExperienceEntry.start_date`` is optional), so an undated role is not a
    defect here — it simply earns no recency credit and no tenure. The shared
    ``resume_dates.is_open_ended`` rule treats blank/missing ends and explicit
    current tokens as ongoing. A non-empty, non-ongoing unparseable end fails.
    """
    bad: list[str] = []
    for _, entry in enabled_entries(resume, "experience"):
        name = f"{entry.get('company', '?')} — {entry.get('role', '?')}"
        raw_start = str(entry.get("start_date") or "").strip()
        raw_end = entry.get("end_date")
        open_ended = resume_dates.is_open_ended(raw_end)
        if not raw_start and open_ended:
            continue  # wholly undated role
        if raw_start and parse_ym(raw_start) in (None, "present"):
            bad.append(f"{name}: start date unparseable")
        if not open_ended and parse_ym(raw_end) is None:
            bad.append(f"{name}: end date unparseable")
    status = "fail" if bad else "pass"
    return _gate("S3", "serious", status, "Dates parseable",
                 "; ".join(bad) or "No unparseable experience dates found.")


def _extra_sections(resume: dict) -> list:
    sections = resume.get("extra_sections")
    return sections if isinstance(sections, list) else []


def _iter_texts(resume: dict):
    yield "summary", str(resume.get("summary") or "")
    for section in ("experience", "projects"):
        for index, entry in enabled_entries(resume, section):
            for field in ("company", "role", "name"):
                if entry.get(field):
                    yield f"{section}[{index}].{field}", str(entry[field])
            for bi, bullet in enumerate(entry.get("bullets") or []):
                yield f"{section}[{index}].bullet[{bi}]", str(bullet)
    for index, entry in enabled_entries(resume, "education"):
        for field in ("institution", "degree"):
            if entry.get(field):
                yield f"education[{index}].{field}", str(entry[field])
    # Custom (extra) sections: phase 1 is ATS-neutral, but the placeholder gate
    # (S5) must still traverse every *rendered* extra text — title, entry
    # metadata, and bullets — so a "[TODO]" in a custom section can't ship. Only
    # ENABLED sections/entries render, so only those are scanned. Malformed
    # shapes are skipped rather than raising, so the report never crashes on a
    # hand-authored resume.
    for section in _extra_sections(resume):
        if not isinstance(section, dict) or section.get("enabled") is False:
            continue
        key = section.get("key") or "?"
        if section.get("title"):
            yield f"extra[{key}].title", str(section["title"])
        if section.get("type") == "bullets":
            for bi, bullet in enumerate(section.get("bullets") or []):
                yield f"extra[{key}].bullet[{bi}]", str(bullet)
        else:  # entries (the default discriminator)
            for ei, entry in enumerate(section.get("entries") or []):
                if not isinstance(entry, dict) or entry.get("enabled") is False:
                    continue
                for field in ("heading", "subheading", "location", "date", "link"):
                    if entry.get(field):
                        yield f"extra[{key}].entry[{ei}].{field}", str(entry[field])
                for bi, bullet in enumerate(entry.get("bullets") or []):
                    yield f"extra[{key}].entry[{ei}].bullet[{bi}]", str(bullet)


def gate_placeholders(resume: dict) -> dict:
    """S5 — no unresolved placeholders anywhere a reader will look."""
    hits = [where for where, text in _iter_texts(resume) if PLACEHOLDER.search(text)]
    status = "fail" if hits else "pass"
    return _gate("S5", "serious", status, "No placeholders",
                 "; ".join(hits) or "No placeholder text found.")


def detect_claim_overstatement(resume: dict, now=None) -> dict | None:
    """C2 detector. Returns claim info when the summary overclaims years beyond
    slack, None otherwise (including when dates are unparseable — never guess).
    The caller decides ask-vs-cap; this only detects."""
    summary = str(resume.get("summary") or "")
    claims = [float(m.group(1)) for m in YEARS_CLAIM.finditer(summary)]
    if not claims:
        return None
    months = total_experience_months(resume, now)
    if months == 0:
        return None  # nothing parseable to compare against → not assessed
    actual_years = months / 12
    claimed = max(claims)
    if claimed > actual_years + CLAIM_SLACK_YEARS:
        return {"claimed_years": claimed, "actual_years": round(actual_years, 1)}
    return None


def detect_gaps(resume: dict, now=None) -> list[dict]:
    """Employment gaps whose education-uncovered remainder exceeds 6 months,
    using a sweep-line with a running max end so a long role that spans a later
    apparent gap suppresses it. Coverage is remainder-based: months overlapping
    merged education spans are subtracted, and only the uncovered remainder is
    tested against the threshold (a fully-covered gap has remainder 0). Emitted
    as ASK findings by the caller — a stated reason recovers most of the
    recruiter penalty (see design appendix B)."""
    now = now or now_ym()
    spans = []
    for _, entry in enabled_entries(resume, "experience"):
        start, end = parse_ym(entry.get("start_date")), parse_ym(entry.get("end_date"))
        if start in (None, "present") or end is None:
            # Undated or unparseable: no sweep at all, not a skipped span. An
            # undated role could cover any apparent gap, so dropping it would
            # manufacture a gap finding out of a date the resume never claimed.
            # (Unparseable is S3's problem; undated is nobody's.)
            return []
        end_ym = now if end == "present" else end
        spans.append((to_index(start), to_index(end_ym), entry.get("company") or "?"))
    if not spans:
        return []
    spans.sort(key=lambda s: s[0])

    edu = []
    for _, entry in enabled_entries(resume, "education"):
        start, end = parse_ym(entry.get("start_date")), parse_ym(entry.get("end_date"))
        if start in (None, "present") or end is None:
            continue
        end_ym = now if end == "present" else end
        edu.append((to_index(start), to_index(end_ym)))
    edu.sort()
    merged_edu: list[list[int]] = []
    for s, e in edu:
        if merged_edu and s <= merged_edu[-1][1]:
            merged_edu[-1][1] = max(merged_edu[-1][1], e)
        else:
            merged_edu.append([s, e])

    gaps = []
    prev_end, prev_company = spans[0][1], spans[0][2]
    for s, e, c in spans[1:]:
        months = s - prev_end
        if months > 0:
            covered = sum(
                max(0, min(ee, s) - max(es, prev_end)) for es, ee in merged_edu
            )
            uncovered = months - covered
            if uncovered > GAP_THRESHOLD_MONTHS:
                gaps.append({"after": prev_company, "before": c, "months": months,
                             "uncovered_months": uncovered, "covered_months": covered})
        if e > prev_end:
            prev_end, prev_company = e, c
    return gaps
