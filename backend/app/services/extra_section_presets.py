"""Canonical custom-section presets — the ONE catalog of common extra_sections.

Single-source vocabulary shared by the resume-ingest prompt (kb_resume_parse
substitutes ``$extra_section_presets`` with ``prompt_block()``) and, later, the
section-add picker UI. Keys/titles must satisfy the ResumeData extra-section
rules (lowercase slug keys; titles must not collide with core headers) — pinned
by tests/test_extra_section_presets.py.

Deliberately NOT here: dated employment-like roles (teaching/research
positions belong in ``experience``) and plain certifications (core
``certifications``). ``match`` lists the section headings that should map to
the preset; anything unmatched mints a fresh slug from its own heading.
"""

PRESETS: list[dict] = [
    {
        "key": "publications", "title": "Publications", "type": "entries",
        "match": ["publications", "selected publications", "papers", "research output"],
    },
    {
        "key": "presentations", "title": "Presentations & Talks", "type": "entries",
        "match": ["presentations", "conference presentations", "talks",
                  "invited talks", "posters"],
    },
    {
        "key": "volunteer", "title": "Volunteer Experience", "type": "entries",
        "match": ["volunteer", "volunteering", "community involvement",
                  "community service"],
    },
    {
        "key": "awards", "title": "Awards & Honors", "type": "bullets",
        "match": ["awards", "honors", "achievements", "scholarships", "fellowships"],
    },
    {
        "key": "languages", "title": "Languages", "type": "bullets",
        "match": ["languages", "language proficiency"],
    },
    {
        "key": "licenses", "title": "Licenses", "type": "bullets",
        "match": ["licenses", "licensure", "professional licenses",
                  "bar admissions", "board certifications"],
    },
    {
        "key": "clearance", "title": "Security Clearance", "type": "bullets",
        "match": ["security clearance", "clearance"],
    },
    {
        "key": "memberships", "title": "Professional Affiliations", "type": "bullets",
        "match": ["memberships", "professional affiliations",
                  "professional associations", "organizations"],
    },
]


def prompt_block(indent: str = "  ") -> str:
    """Render the catalog as prompt text, one preset per line."""
    lines = []
    for p in PRESETS:
        headings = ", ".join(p["match"])
        lines.append(f'{indent}- `{p["key"]}` — "{p["title"]}" ({p["type"]}): {headings}')
    return "\n".join(lines)
