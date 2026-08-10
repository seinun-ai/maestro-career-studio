import re
from functools import lru_cache

from app.services import role_categories

# Labels derive from ats/data/role_categories.yaml — the single vocabulary
# source (the hand-written version carried a "hybrid" key the schema could
# never produce). Read LAZILY per call, not frozen at import: role_categories
# caches the load, and an import-time constant was the one place a YAML edit
# mid-process could not reach.

# Management level: a DIFFERENT job, not a rank on the same one. Kept separate
# from the shared seniority vocabulary precisely so the ATS title tier never
# sees it — stripping "manager" there would score "Engineering Manager" as a
# direct match for "Engineer". Display labels may strip it; scoring may not.
_MANAGEMENT_PATTERN = re.compile(
    r"\b(manager|director|head|vp|vice[\s-]?president)\b",
    re.IGNORECASE,
)


def _alternation(terms) -> str:
    """Longest-first alternation; each term's spaces accept a hyphen too."""
    ordered = sorted((t for t in terms if t), key=len, reverse=True)
    return "|".join(re.escape(t).replace(r"\ ", r"[\s-]?") for t in ordered)


@lru_cache(maxsize=1)
def _seniority_pattern() -> re.Pattern[str]:
    """Always-strip rank markers, matched anywhere in the title."""
    return re.compile(rf"\b({_alternation(role_categories.seniority_always())})\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _leading_rank_pattern() -> re.Pattern[str]:
    """Prefix-only rank markers, anchored to the START of the title.

    Mirrors `ats/layers._strip_seniority`: `associate`/`principal`/`staff`/
    `lead` are head nouns in the suffix position, so an unanchored strip turned
    "Tech Lead" into "Tech" — a wrong artifact filename as surely as it was a
    wrong match core. The two consumers read one vocabulary and must not
    diverge; that divergence is the bug class this file already documents for
    the management pattern below.
    """
    return re.compile(
        rf"^\s*({_alternation(role_categories.seniority_prefix_only())})\b", re.IGNORECASE
    )

_NICHE_MODIFIER_PATTERN = re.compile(
    r"\b("
    r"llm|nlp|gen[\s-]?ai|rag|applied|machine[\s-]?learning|ml|ai|deep[\s-]?learning|"
    r"analytics|quantitative|research|product|platform|cloud|software|full[\s-]?stack|"
    r"computational|statistical|business|marketing|financial|clinical|"
    r"computer[\s-]?vision|cv|reinforcement|generative"
    r")\b",
    re.IGNORECASE,
)

_CORE_ROLE_PATTERN = re.compile(
    r"(data[\s-]?scientist|data[\s-]?analyst|data[\s-]?engineer|"
    r"ai[\s/\\-]?ml[\s-]?engineer|machine[\s-]?learning[\s-]?engineer|"
    r"software[\s-]?engineer|analytics[\s-]?engineer|research[\s-]?scientist)",
    re.IGNORECASE,
)

_CANONICAL_ROLES: dict[str, str] = {
    "data scientist": "Data Scientist",
    "data analyst": "Data Analyst",
    "data engineer": "Data Engineer",
    "ai/ml engineer": "AI/ML Engineer",
    "ai ml engineer": "AI/ML Engineer",
    "machine learning engineer": "Machine Learning Engineer",
    "software engineer": "Software Engineer",
    "analytics engineer": "Analytics Engineer",
    "research scientist": "Research Scientist",
}


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _title_case_role(text: str) -> str:
    words = text.split()
    if not words:
        return text
    return " ".join(
        word.upper() if word.lower() in {"ai", "ml"} else word.capitalize()
        for word in words
    )


def _canonicalize_role(text: str) -> str:
    normalized = _normalize_whitespace(text).lower()
    if normalized in _CANONICAL_ROLES:
        return _CANONICAL_ROLES[normalized]
    return _title_case_role(text)


def _strip_title(title: str | None) -> str | None:
    if not title or not title.strip():
        return None

    text = _normalize_whitespace(title)
    core = _CORE_ROLE_PATTERN.search(text)
    if core:
        return _canonicalize_role(core.group(0))

    text = _leading_rank_pattern().sub(" ", text)
    text = _seniority_pattern().sub(" ", text)
    text = _MANAGEMENT_PATTERN.sub(" ", text)
    text = _NICHE_MODIFIER_PATTERN.sub(" ", text)
    text = _normalize_whitespace(text)
    if not text:
        return None

    return _canonicalize_role(text)


def generic_role_title(
    *,
    role_category: str | None = None,
    base_resume_role: str | None = None,
    title: str | None = None,
) -> str:
    """Return a generic role label for summaries and artifact filenames.

    Precedence: the JOB decides the label. A real role_category wins; otherwise
    the job title stripped of seniority and niche modifiers. The base resume's
    DECLARED role is the last resort — an ML-engineer application tailored from
    the data-scientist base must not be filed as "Data Scientist"
    (user-reported naming bug, 2026-07-16).

    `base_resume_role` is the resume's `role_category` column, not its slug.
    This branch used to test the SLUG for membership in the job-role vocabulary,
    which resolved only when a resume happened to be named after a category —
    so `data_scientist` produced "Data Scientist" while `data_scientist_new`
    produced "Professional" despite targeting the same role, and every
    arbitrarily-named resume (i.e. every new user's) always fell through.
    """
    if (
        role_category
        and role_category not in {"other", "unknown"}
        and role_category in role_categories.labels()
    ):
        return role_categories.labels()[role_category]

    stripped = _strip_title(title)
    if stripped:
        return stripped

    if (
        base_resume_role
        and base_resume_role not in {"other", "unknown"}
        and base_resume_role in role_categories.labels()
    ):
        return role_categories.labels()[base_resume_role]

    return "Professional"
