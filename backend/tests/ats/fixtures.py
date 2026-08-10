"""Deterministic sample JD + resume used across engine tests and the golden snapshot,
plus the shared fake embedder for semantic-stage tests (no model download).
"""
import hashlib

# --- semantic test fake: known strings -> hand-crafted vectors ---
#
# Vector layout: the first four coordinates are the "topic axes" (machine
# learning, kubernetes, salesforce, statistics); coordinates 5..(4+_JUNK_DIMS)
# are a high-dimensional "junk" tail reserved for UNKNOWN strings. Known vectors
# are ZERO throughout the junk tail, so cos(known, unknown) == 0 exactly. Unknown
# strings get a deterministic per-string unit vector confined ENTIRELY to the
# junk tail (topic axes zero) — so two *distinct* unknown strings are near
# orthogonal (cos ~0) rather than identical. This matters for the evidence
# stage, where "snowflake" (JD) and "bigquery" (a resume skills item) are both
# unknown to the fake: they must NOT semantic-match each other (the pair is an
# adjacency case, not a semantic one). The original single shared default vector
# collapsed every unknown pair to cos 1.0.
#
# The fake also models the ANCHOR GATE (post-review C1): the per-skill semantic
# stage only *considers* a candidate that shares a non-stopword token with the JD
# term (or its aliases). So the two high-cosine relationships below split by
# token overlap:
#   - "statistical modeling" (JD) <-> "statistical analysis" (resume): cos 0.96
#     AND share the token "statistical" -> gate PASSES -> semantic hit.
#   - "kubernetes" (JD) <-> "container orchestration ..." (resume): cos 0.96 but
#     ZERO shared tokens -> gate BLOCKS (this genuine reformulation now lives in
#     adjacency.yaml instead). The high cosine is retained so tests can prove the
#     gate — not the threshold — is what suppresses it.
#
# Hand-computed cosines (topic vectors unit length; 0.96^2 + 0.28^2 = 1.0):
#   cos("machine learning", "shipped ml models to production") = 1*0.96          = 0.96  (share "ml" via alias -> gate ok)
#   cos("machine learning", "ml systems in production")        = 1*0.96          = 0.96  (tie-break tests; share "ml")
#   cos("statistical modeling", "statistical analysis")        = 1*0.96          = 0.96  (share "statistical" -> gate ok)
#   cos("kubernetes", "container orchestration experience")    = 1*0.96          = 0.96  (ZERO overlap -> gate blocks)
#   cos("machine learning", "container orchestration experience") = 1*0.28       = 0.28  (< 0.60: miss)
#   cos(any known, any unknown)                                = 0.0             (disjoint dims)
#   cos(unknown_a, unknown_b) for a != b                       ~ 0.0             (independent junk vectors)
# Topic axes: 0 ml, 1 k8s, 2 sfdc, 3 stats, 4 data-domain.
_JUNK_DIMS = 32
_TOPIC_DIMS = 5
_VEC_DIMS = _TOPIC_DIMS + _JUNK_DIMS


def _pad(topic: tuple[float, ...]) -> list[float]:
    return list(topic) + [0.0] * _JUNK_DIMS


_FAKE_VECTORS = {
    # jd term / similar resume evidence            (ml,   k8s,  sfdc, stats, data)
    "machine learning": _pad((1.0, 0.0, 0.0, 0.0, 0.0)),
    "shipped ml models to production": _pad((0.96, 0.28, 0.0, 0.0, 0.0)),
    "ml systems in production": _pad((0.96, 0.28, 0.0, 0.0, 0.0)),  # same vector: tie-break tests
    "kubernetes": _pad((0.0, 1.0, 0.0, 0.0, 0.0)),
    "container orchestration experience": _pad((0.28, 0.96, 0.0, 0.0, 0.0)),
    "salesforce": _pad((0.0, 0.0, 1.0, 0.0, 0.0)),
    # non-generic-anchor pair (share "statistical"); both project onto stats axis:
    "statistical modeling": _pad((0.0, 0.0, 0.0, 1.0, 0.0)),
    "statistical analysis": _pad((0.0, 0.0, 0.0, 0.8, 0.6)),
    # generic-only-anchor pairs for the two-threshold rule. "Data Analysis"
    # anchors only generic tokens ("data", "analysis").
    #   cos("data analysis", "statistical analysis") = 0.6*0.8 + 0.8*0.6 = 0.96
    #     -> generic-only but clears the 0.82 generic floor -> hit.
    #   cos("data mining", "data pipeline chores") = 0.6 (see below)
    #     -> generic-only, clears 0.60 base but NOT 0.82 -> blocked.
    "data analysis": _pad((0.0, 0.0, 0.0, 0.6, 0.8)),
    "data mining": _pad((0.0, 0.0, 0.0, 0.0, 1.0)),
    "data pipeline chores": _pad((0.0, 0.0, 0.0, 0.8, 0.6)),  # cos vs data mining = 0.6
}


def _junk_vector(text: str) -> list[float]:
    """Deterministic unit vector in the junk tail only (topic axes zero). Distinct
    unknown strings hash to independent SIGNED tails, so their cosine hovers near
    0 (well below the 0.60 threshold) — unrelated resume text never semantic-
    matches unrelated JD text. One byte per dim, centred to a signed value."""
    # one sha256 per 32 dims keeps the bytes independent (32-byte digest)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    tail = [(digest[i] - 128) or 1 for i in range(_JUNK_DIMS)]  # signed byte, nonzero
    norm = sum(x * x for x in tail) ** 0.5
    return [0.0] * _TOPIC_DIMS + [x / norm for x in tail]


def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """Drop-in monkeypatch target for app.services.ats.embeddings.embed_texts."""
    return [
        list(_FAKE_VECTORS[key]) if (key := t.lower().strip()) in _FAKE_VECTORS
        else _junk_vector(key)
        for t in texts
    ]

SAMPLE_JD = {
    "title": "Senior Data Scientist",
    "company": "Acme Corp",
    "role_category": "data_scientist",  # production form (snake_case), not the old title-cased YAML key
    "level": "Senior",
    "years_experience_min": 5,
    "years_experience_max": None,
    "skills": [
        {"skill_name": "Python", "skill_category": "Programming Language", "requirement_level": "required"},
        {"skill_name": "Snowflake", "skill_category": "Data Warehouse", "requirement_level": "required"},
        {"skill_name": "Salesforce", "skill_category": "CRM", "requirement_level": "required"},
        {"skill_name": "AWS", "skill_category": "Cloud", "requirement_level": "preferred"},
        {"skill_name": "Tableau", "skill_category": "BI", "requirement_level": "preferred"},
        {"skill_name": "Docker", "skill_category": "DevOps", "requirement_level": "mentioned"},
    ],
    "responsibilities": ["Build ML models"],
    "qualifications": ["5+ years of experience"],
}

SAMPLE_RESUME = {
    "contact": {
        "name": "Jane Doe", "email": "jane@example.com", "phone": "+1-555-0100",
        "location": "Austin, TX", "linkedin": None, "github": None, "website": None,
    },
    "summary": "Data scientist with production ML experience.",
    "skills": [
        {"category": "Languages", "items": ["Python", "SQL"]},
        {"category": "Cloud", "items": ["Amazon Web Services", "BigQuery"]},
        {"category": "Tools", "items": ["Git", "Jira"]},
    ],
    "experience": [
        {
            "company": "DataCo", "role": "Data Scientist", "location": "Austin, TX",
            "start_date": "Jul 2023", "end_date": None, "enabled": True,
            "bullets": ["Shipped Python forecasting models on AWS reducing costs 20%."],
        },
        {
            "company": "OldCo", "role": "Analyst", "location": "Dallas, TX",
            "start_date": "Jun 2019", "end_date": "Jun 2021", "enabled": True,
            "bullets": ["Built Tableau dashboards for execs."],
        },
        {
            "company": "HiddenCo", "role": "Intern", "location": "Remote",
            "start_date": "Jan 2018", "end_date": "May 2018", "enabled": False,
            "bullets": ["Salesforce admin work."],
        },
    ],
    "projects": [
        {"name": "RAG Search", "enabled": True, "tech": "Python, LangChain",
         "link": None, "date": "Feb 2026", "bullets": ["Built RAG pipeline."]},
    ],
    "education": [
        {"institution": "UT Austin", "degree": "MS", "field": "Data Science",
         "location": "Austin, TX", "graduation_date": "May 2019", "gpa": None,
         "coursework": [], "bullets": []},
    ],
    "certifications": [],
}
