"""The ONE definition of "this role is still ongoing".

Why this exists: there were two, and they disagreed. `ats/resume_indexer.py`
accepted `{present, current, now, ongoing}` and granted the entry recency
credit; `health_zones.parse_ym` accepted only `present|current|now`, so a
resume saying "Ongoing" was scored as a CURRENT role by the ATS engine and
simultaneously flagged by health gate S3 (tier `serious`) as having an
unparseable end date. Same document, two subsystems, opposite readings.

Kept as a token set rather than a regex so both consumers can use it in their
own way — the indexer matches the first whitespace-split token, the health
parser matches the whole trimmed string.

`to date` / `till date` are here because they are ordinary in UK and Indian
CVs, which are inside the English-language scope this project declares. They
are NOT a locale feature; they are the same English concept spelled
differently, and refusing them told a correct CV it was broken.

Adding a token here makes an entry count as CURRENT everywhere. That is a
scoring-relevant change: a current role earns full recency credit. Do not add
speculative synonyms — add what real resumes actually say.
"""

from __future__ import annotations

CURRENT_TOKENS: frozenset[str] = frozenset(
    {
        "present",
        "current",
        "currently",
        "now",
        "ongoing",
        "to date",
        "till date",
        "to present",
    }
)


def is_current(value: object) -> bool:
    """Whether a resume date means "still in this role".

    Whole-string match on the trimmed, lowercased value. A date that merely
    CONTAINS one of these words ("Present day rotation") is not a current
    marker and must not be treated as one.
    """
    return str(value or "").strip().lower() in CURRENT_TOKENS
