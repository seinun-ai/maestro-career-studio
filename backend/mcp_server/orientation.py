"""The tool sets, in the order a job search moves through them.

One table that the per-set server instructions and get_setup_status read, so a
set's name and its job are written once. Pure: no httpx, no app imports.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSet:
    name: str
    use_when: str  # what the user says, in their own words
    holds: str


SETS: tuple[ToolSet, ...] = (
    ToolSet(
        "profile",
        "set me up, import my resume, add a project, make a resume for a role",
        "career history, base resumes and their anchors, the health check, versions, "
        "form answers, job preferences, markets and persona",
    ),
    ToolSet("hunt", "find me jobs", "the search brief, saving jobs, scoring them and proposing them"),
    ToolSet(
        "tailor",
        "tailor my resume for this job",
        "looking up or saving the job, scoring, gaps, the tailored resume and its PDF, "
        "the health check, undo and the tailoring presets",
    ),
    ToolSet(
        "apply",
        "apply to this job, work my queue",
        "the cover letter and answers, form answers, the proposal, evidence, the user's yes "
        "and submitting",
    ),
    ToolSet(
        "track",
        "update my statuses, how is my search going",
        "applications and their statuses, referrals and the analytics charts",
    ),
    ToolSet("templates", "make a resume design", "resume templates: drafting, checking and previewing"),
    ToolSet("full", "anything", "every tool"),
)

SET_NAMES: tuple[str, ...] = tuple(s.name for s in SETS)
