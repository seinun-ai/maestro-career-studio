# backend/app/services/health_zones.py
"""Attention zones, career tier, and the derived severity/cost.

Zones are a JSON index lookup, never page geometry. They are NOT score
weights — health_score works on bare levels. Zones exist for C1, severity,
fix-list ordering (cost), and UI highlighting.
"""
import re
from datetime import UTC, datetime

from app.services.resume_dates import is_current

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
_YM_PATTERNS = (
    re.compile(r"^\s*([a-zA-Z]{3,9})\.?\s+(\d{4})\s*$"),   # Jan 2021 / January 2021
    re.compile(r"^\s*(\d{4})-(\d{1,2})\s*$"),               # 2021-03
    re.compile(r"^\s*(\d{1,2})/(\d{4})\s*$"),               # 03/2021
    re.compile(r"^\s*(\d{4})\s*$"),                          # 2021
)

# Seasonal and quarter dates, read by the HEALTH GATE only. Academic CVs and
# internships routinely say "Summer 2022" or "Q3 2021"; those are readable
# dates, and gate S3 (tier `serious`) calling them unparseable told a correct
# CV it was broken.
#
# The ATS indexer deliberately does NOT learn these: it grants recency credit
# from precise months, and a season is not one. Same split as year-only —
# readable for the gate, no precise credit for the score. The month each maps
# to is the START of the period, which is an approximation and only ever feeds
# tenure/zone math, never a matching decision.
_SEASONS = {"winter": 12, "spring": 3, "summer": 6, "fall": 9, "autumn": 9}
_SEASON_PATTERN = re.compile(
    r"^\s*(winter|spring|summer|fall|autumn)\s+(\d{4})\s*$", re.IGNORECASE
)
_QUARTER_PATTERN = re.compile(r"^\s*[qQ]([1-4])\s+(\d{4})\s*$")

HOT_WEIGHT = 1.0
COLD_WEIGHT = 0.5
EARLY_TIER_MAX_MONTHS = 24


def parse_ym(value) -> tuple[int, int] | str | None:
    """Parse a resume date into (year, month), the string 'present', or None."""
    text = str(value or "").strip()
    if not text:
        return None
    if is_current(text):
        return "present"
    m = _YM_PATTERNS[0].match(text)
    if m:
        month = _MONTHS.get(m.group(1)[:3].lower())
        if month:
            return (int(m.group(2)), month)
        # An alphabetic word that is NOT a month name falls through rather than
        # returning None here — this pattern also matches "Summer 2022", and
        # returning early shadowed the season pattern below.
    m = _YM_PATTERNS[1].match(text)
    if m:
        month = int(m.group(2))
        if not (1 <= month <= 12):
            return None
        return (int(m.group(1)), month)
    m = _YM_PATTERNS[2].match(text)
    if m:
        month = int(m.group(1))
        if not (1 <= month <= 12):
            return None
        return (int(m.group(2)), month)
    m = _YM_PATTERNS[3].match(text)
    if m:
        return (int(m.group(1)), 1)
    m = _SEASON_PATTERN.match(text)
    if m:
        return (int(m.group(2)), _SEASONS[m.group(1).lower()])
    m = _QUARTER_PATTERN.match(text)
    if m:
        return (int(m.group(2)), (int(m.group(1)) - 1) * 3 + 1)
    return None


def now_ym() -> tuple[int, int]:
    now = datetime.now(UTC)
    return (now.year, now.month)


def to_index(ym: tuple[int, int]) -> int:
    return ym[0] * 12 + (ym[1] - 1)


def enabled_entries(resume: dict, section: str) -> list[tuple[int, dict]]:
    return [
        (i, e) for i, e in enumerate(resume.get(section) or [])
        if e.get("enabled") is not False
    ]


def date_intervals(resume: dict, now: tuple[int, int] | None = None):
    """(start_idx, end_idx) month intervals for enabled roles with parseable dates."""
    now = now or now_ym()
    intervals = []
    for _, entry in enabled_entries(resume, "experience"):
        start = parse_ym(entry.get("start_date"))
        end = parse_ym(entry.get("end_date"))
        if start in (None, "present") or end is None:
            continue
        end_ym = now if end == "present" else end
        s, e = to_index(start), to_index(end_ym)
        if e >= s:
            intervals.append((s, e))
    return sorted(intervals)


def total_experience_months(resume: dict, now: tuple[int, int] | None = None) -> int:
    merged: list[list[int]] = []
    for s, e in date_intervals(resume, now):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged)


def compute_tier(resume: dict, now: tuple[int, int] | None = None) -> str:
    """'early' (<24 months employment), 'experienced', or 'unknown' (no parseable dates).

    Per the design's escape hatch #3, 'unknown' must never silently pick the
    harsher tier — callers treat it as experienced for zoning and emit a note.
    """
    if not date_intervals(resume, now):
        return "unknown"
    months = total_experience_months(resume, now)
    return "early" if months < EARLY_TIER_MAX_MONTHS else "experienced"


Location = tuple[str, int | None, int | None]


def hot_locations(resume: dict, tier: str) -> set[Location]:
    """Summary, plus whichever section carries this candidate's evidence.

    The rule is one choice, not two overlapping ones: an experienced candidate
    is read on their most recent ROLE, an early-career one on their PROJECTS,
    because for someone with no employment history the projects ARE the
    experience. Summary is hot either way.

    This replaced a rule that gave early-career resumes BOTH — the first three
    bullets of their first role AND every bullet of every project — which on a
    junior resume made most of the document hot. That is self-defeating twice
    over: `cost()` can only order a fix list if some content is cold, and
    `severity()` calls every weak hot bullet `critical`, so a blanket made the
    report read as uniformly alarming rather than prioritised.

    Granularity is the FIRST enabled entry, not every entry, for the same
    reason. "All experience" would be most of an experienced resume, and the
    hot/cold weighting would stop discriminating. Most-recent-role is also the
    part the (directional, weakly-evidenced) reading research actually supports.

    The old three-bullet cap on the first role is gone: three was arbitrary,
    and an entry's bullets are one unit of evidence.
    """
    hot: set[Location] = {("summary", None, None)}
    section = "projects" if tier == "early" else "experience"
    entries = enabled_entries(resume, section)
    if entries:
        index, first = entries[0]
        for bi in range(len(first.get("bullets") or [])):
            hot.add((section, index, bi))
    return hot


def severity(level: float, *, hot: bool) -> str:
    return "critical" if level <= 0.3 and hot else "minor"


def cost(level: float, *, hot: bool) -> float:
    return (HOT_WEIGHT if hot else COLD_WEIGHT) * (1.0 - level)
