"""Consolidation pipeline.

The Task-8 core (``collect_entries`` / ``group_by_identity`` / ``identity_key``)
is pure — no DB or LLM. The Task-9 ``consolidate`` entry point below layers the
DB write + LLM stages on top: entity resolution, bullet clustering, point
writing, port-log backfill, and profile/skills merge.
"""

import copy
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.schemas.career_kb import ConsolidationReport
from app.services import llm, model_settings, prompts


def _norm(s: Any) -> str:
    return " ".join(str(s or "").lower().split())


def point_text_key(text: str) -> str:
    """Normalized bullet text for exact / whitespace-insensitive dedup.

    Shared by the LLM cluster path and ``consolidate_deterministic`` so the
    two entry points cannot drift on what "the same bullet" means.
    """
    return _norm(text)


@dataclass
class SourceEntry:
    resume_key: str
    section: str            # "experience" | "projects" | "education" | "certifications"
    index: int
    entry: Any              # dict for experience/projects/education; str for certifications


@dataclass
class Group:
    section: str
    key: tuple
    members: list[SourceEntry] = field(default_factory=list)


@dataclass
class DeterministicEntityRef:
    id: Any
    kind: str
    title: str
    org: str | None
    created: bool


@dataclass
class DeterministicPointRef:
    id: Any
    entity_id: Any
    text: str


@dataclass
class DeterministicConsolidationReport:
    """Ids-bearing report for the LLM-free ingest path. Not a substitute for
    ConsolidationReport — web callers keep that shape unchanged.

    ``points_created`` counts rows written, NOT rows approved: this path lands
    every point as a draft and ``kb_approve_points`` / the web inbox is the
    gate. ``duplicates_skipped`` counts every source bullet that did not become
    a new point — collapsed within the batch, or already present on the entity
    (including as a retired point).
    """

    entities: list[DeterministicEntityRef] = field(default_factory=list)
    points: list[DeterministicPointRef] = field(default_factory=list)
    entities_created: int = 0
    entities_matched: int = 0
    points_created: int = 0
    duplicates_skipped: int = 0
    # Two different questions, two fields. ``skills_merged`` names the
    # CATEGORIES touched (one entry per category written), which is the shape
    # the port report has always had and which tests assert. It cannot answer
    # "how many skills did this add" — two new items in one category append it
    # once — so ``skills_items_added`` names the ITEMS that actually landed in
    # the profile.
    skills_merged: list[str] = field(default_factory=list)
    skills_items_added: list[str] = field(default_factory=list)
    # Entities this run RENAMED to a richer role title on a near-identity hit.
    # THIS is the shape that fills it: experience resolves here through
    # ``_match_or_create_identity``, which is where the upgrade happens. The
    # same field on ConsolidationReport is reserved and stays empty — see the
    # comment there.
    titles_upgraded: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


ENTRY_SECTIONS = ("experience", "projects", "education", "certifications")
ALL_SECTIONS = ("experience", "projects", "education", "certifications", "extra")


def collect_entries(sources: list[tuple[str, dict]]) -> list[SourceEntry]:
    """Flatten every list-shaped section of every source into tagged SourceEntry rows.

    `sources` is a list of (resume_key, resume_data_dict). Sections that are
    missing or non-list are skipped. Order is source-order, then section order
    (ENTRY_SECTIONS), then original index.
    """
    out: list[SourceEntry] = []
    for resume_key, data in sources:
        for section in ENTRY_SECTIONS:
            items = data.get(section)
            if not isinstance(items, list):
                continue
            for index, entry in enumerate(items):
                out.append(SourceEntry(resume_key=resume_key, section=section, index=index, entry=entry))
        extra_sections = data.get("extra_sections")
        if isinstance(extra_sections, list):
            for sec_idx, sec in enumerate(extra_sections):
                if not isinstance(sec, dict):
                    continue
                sec_type = sec.get("type")
                sec_key = sec.get("key")
                sec_title = sec.get("title")
                if not sec_key or not sec_type:
                    continue
                if sec_type == "entries":
                    entries = sec.get("entries")
                    if isinstance(entries, list):
                        for entry_idx, entry in enumerate(entries):
                            if isinstance(entry, dict):
                                entry_dict = {
                                    **entry,
                                    "section_key": sec_key,
                                    "section_type": "entries",
                                    "section_title": sec_title,
                                }
                                out.append(
                                    SourceEntry(
                                        resume_key=resume_key,
                                        section="extra",
                                        index=entry_idx,
                                        entry=entry_dict,
                                    )
                                )
                elif sec_type == "bullets":
                    entry_dict = {
                        "section_key": sec_key,
                        "section_type": "bullets",
                        "section_title": sec_title,
                        "title": sec_title,
                        "bullets": sec.get("bullets", []) if isinstance(sec.get("bullets"), list) else [],
                        "enabled": sec.get("enabled", True),
                    }
                    out.append(
                        SourceEntry(
                            resume_key=resume_key,
                            section="extra",
                            index=sec_idx,
                            entry=entry_dict,
                        )
                    )
    return out


def identity_key(section: str, entry: Any) -> tuple:
    """Normalized identity tuple used to cluster the same real-world item across variants."""
    if section == "experience":
        e = entry if isinstance(entry, dict) else {}
        return (_norm(e.get("company")), _norm(e.get("role")), (e.get("start_date") or ""))
    if section == "projects":
        e = entry if isinstance(entry, dict) else {}
        return (_norm(e.get("name")),)
    if section == "education":
        e = entry if isinstance(entry, dict) else {}
        return (_norm(e.get("institution")), _norm(e.get("degree")))
    if section == "certifications":
        return (_norm(entry),)   # entry is a string
    if section == "extra":
        e = entry if isinstance(entry, dict) else {}
        sec_key = _norm(e.get("section_key"))
        sec_type = e.get("section_type")
        if sec_type == "entries":
            return ("extra", sec_key, _norm(e.get("heading") or e.get("title")))
        return ("extra", sec_key)
    raise ValueError(f"unknown section {section!r}")


def group_by_identity(entries: list[SourceEntry]) -> list[Group]:
    """Group entries by (section, identity_key), preserving first-seen order of groups."""
    groups: list[Group] = []
    index: dict[tuple, Group] = {}
    for se in entries:
        gkey = (se.section, identity_key(se.section, se.entry))
        g = index.get(gkey)
        if g is None:
            g = Group(section=se.section, key=identity_key(se.section, se.entry))
            index[gkey] = g
            groups.append(g)
        g.members.append(se)
    return groups


# ===========================================================================
# Conservative near-identity matching (second pass, on exact-key MISS only)
# ===========================================================================
#
# Why it is deliberately mean: a false merge fuses two real entities and the
# evidence of one of them is gone; a false fork costs the user one click in the
# entity-merge UI. So every rule below prefers to say None.
#
# It compares identity KEY TUPLES, not stored columns. The keys in an
# ``_existing_*_index`` dict are already built to line up with
# ``identity_key`` (see ``_identity_title``); reading the KBEntity columns
# again here would re-open exactly that divergence. The dict values are opaque
# — whatever matched is handed straight back.

#: Words that say nothing about WHICH certification this is.
CERT_NOISE_TOKENS = frozenset({"certified", "certificate", "certification", "professional"})
#: Vendors droppable only as the FIRST remaining token ("AWS Certified X" == "X"),
#: never mid-title where the word is doing real work ("Amazon AWS Practitioner").
CERT_VENDOR_TOKENS = frozenset({"aws", "microsoft", "google", "ibm", "oracle"})
#: Projects have no company/date to corroborate a subset, so the bar is a cap.
PROJECT_MAX_EXTRA_TOKENS = 2

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PARENTHETICAL_RE = re.compile(r"\([^()]*\)")
#: An exam code is an unspaced, HYPHENATED run of letters/digits: AIF-C01,
#: AZ-900, DP-203I, SAA-C03. Case-insensitive by construction — an identity
#: key arrives ``_norm``ed, so casing is long gone by here.
_EXAM_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


def _tokens(s: Any) -> set[str]:
    return set(_TOKEN_RE.findall(str(s or "").lower()))


def _is_exam_code(text: str) -> bool:
    """True for a code-shaped parenthetical, which is noise, not an issuer.

    The two misreadings are NOT symmetric. Mistaking a code for an issuer only
    ever forks — two entities where one belonged, one click to merge. Mistaking
    an ISSUER for a code drops the only thing telling two certifications apart
    and fuses them, destroying evidence. So the test is built to fail toward
    "issuer".

    Hence three requirements: no spaces, a mix of letters and digits, and a
    hyphen. The hyphen is what separates the real codes above from code-shaped
    ISSUERS — ISC2, 3M, O2, A10, E5, V2 are all unhyphenated and stay identity.
    Plain words ("AWS", "Amazon Web Services") and bare years ("2023", no
    letter) fall through to issuer as well.

    Accepted cost: an unhyphenated code like "AZ900" reads as an issuer, so
    "(AZ900)" and "(DP900)" fork instead of matching — the safe direction, and
    such titles usually differ anyway.
    """
    s = text.strip().lower()
    if not _EXAM_CODE_RE.match(s):
        return False
    return any(c.isdigit() for c in s) and any(c.isalpha() for c in s)


def _cert_signature(raw: Any) -> tuple[frozenset[str], str | None, str | None]:
    """(comparable token set, leading vendor token, issuing org) for a cert.

    A cert identity key is ``_cert_string`` — ``f"{title} ({org})"`` — so the
    ISSUER lives inside a trailing parenthetical. Treating every parenthetical
    as noise made "AI Practitioner (AWS)" and "AI Practitioner (Google)" the
    same cert; the leading-vendor guard cannot save that, because the org is
    never a leading token. So the trailing parenthetical is parsed with
    ``_split_cert`` — the same parser that wrote it — and classified: code-
    shaped is noise, anything else is an org the caller must compare.

    Any code-shaped parenthetical still standing inside the remaining title is
    dropped too, so a code is noise wherever it sits. A non-code one is left
    as residue and simply becomes tokens, which forks rather than fuses.

    Noise tokens go next, from anywhere in the title. Only then is the FIRST
    surviving token tested against the vendor list, so "AWS Certified X" and
    "Certified AWS X" reduce alike.
    """
    title, parenthetical = _split_cert(str(raw or ""))
    org: str | None = None
    if parenthetical is not None and not _is_exam_code(parenthetical):
        org = _norm(parenthetical)
    # `_split_cert` hands back the whole (stripped) string when there is no
    # trailing parenthetical, so `title` is already the right text either way.
    text = title
    text = _PARENTHETICAL_RE.sub(
        lambda m: " " if _is_exam_code(m.group(0)[1:-1]) else m.group(0), text
    )
    ordered = [t for t in _TOKEN_RE.findall(text.lower()) if t not in CERT_NOISE_TOKENS]
    vendor: str | None = None
    if ordered and ordered[0] in CERT_VENDOR_TOKENS:
        vendor = ordered[0]
        ordered = ordered[1:]
    return frozenset(ordered), vendor, org


def _near_experience(incoming: tuple, candidate: tuple) -> bool:
    """Same company, same start date, and one role title contained in the other.

    The start date must be PRESENT, not merely equal on both sides. Two dateless
    entries at the same company with subset roles would otherwise match on the
    company alone — the loosest path in the whole matcher, and the one most
    likely to fuse a promotion into the role it succeeded. An empty start on the
    incoming side refuses; a dateless duplicate costs one manual merge, which is
    the cheap direction.
    """
    company_a, role_a, start_a = incoming
    company_b, role_b, start_b = candidate
    if not start_a:
        return False
    if not company_a or company_a != company_b or start_a != start_b:
        return False
    tokens_a, tokens_b = _tokens(role_a), _tokens(role_b)
    if not tokens_a or not tokens_b:
        return False
    return tokens_a <= tokens_b or tokens_b <= tokens_a


def _near_certification(incoming: tuple, candidate: tuple) -> bool:
    """Equal token sets after the noise/vendor/parenthetical strip.

    Design §4b writes the rule as "equality OR subset", but the strip is what
    makes a subset legitimate: once the noise words are gone, any remaining
    extra token is a real one. "azure fundamentals" vs "azure data
    fundamentals" (AZ-900 vs DP-900) differ by "data", and a plain subset test
    would fuse them. So the surviving rule is equality — the subset case is
    the one normalization has already turned into equality.
    """
    sig_a, vendor_a, org_a = _cert_signature(incoming[0])
    sig_b, vendor_b, org_b = _cert_signature(candidate[0])
    if not sig_a or not sig_b:
        return False
    if org_a and org_b and org_a != org_b:
        # Two named issuers that disagree are two certifications. Only a
        # two-sided clash vetoes: one side routinely omits the org, and an
        # absent org is no evidence of anything.
        return False
    if vendor_a and vendor_b and vendor_a != vendor_b:
        # Both shed a leading vendor; without this the remainders of
        # "AWS Certified AI Practitioner" and "Google Certified AI
        # Practitioner" are identical.
        return False
    return sig_a == sig_b


def _near_project(incoming: tuple, candidate: tuple) -> bool:
    """One name's tokens contained in the other's, by at most two extra tokens."""
    tokens_a, tokens_b = _tokens(incoming[0]), _tokens(candidate[0])
    if not tokens_a or not tokens_b:
        return False
    if tokens_a <= tokens_b:
        return len(tokens_b - tokens_a) <= PROJECT_MAX_EXTRA_TOKENS
    if tokens_b <= tokens_a:
        return len(tokens_a - tokens_b) <= PROJECT_MAX_EXTRA_TOKENS
    return False


_NEAR_MATCHERS = {
    "experience": _near_experience,
    "certifications": _near_certification,
    "projects": _near_project,
}


def find_near_identity(section: str, entry: Any, candidates: dict[tuple, Any]) -> Any:
    """The one near-duplicate candidate for ``entry``, or None.

    Call ONLY after an exact ``identity_key`` lookup missed — this function
    does not check for an exact hit and, handed an exactly-equal entry, simply
    returns that candidate (equality is the degenerate subset).

    A near-hit, unlike an exact hit, may mean the incoming entry is the RICHER
    variant — the experience callers upgrade the entity title; a poorer variant
    never renames.

    ``entry`` is a source entry (dict for experience/projects, str for
    certifications) or an already-computed identity key tuple, which is what
    callers holding a ``Group.key`` have. ``candidates`` is an
    ``_existing_*_index`` dict — ``{identity_key_tuple: KBEntity}``. Matching
    reads only the keys, so any value type works; the values are compared by
    IDENTITY (``is``) for the ambiguity gate below, and one value reached
    through two keys is therefore still one candidate.

    Handles experience, certifications and projects. ``education`` and
    ``extra`` are exact-identity only and always return None: a degree and an
    extra-section heading have no second signal to corroborate a fuzzy hit.

    Two or more distinct candidates matching is ambiguity, not a match, and
    returns None — otherwise the answer would depend on dict order. Never
    compares two existing entities against each other; fusing those is the
    human merge action's job.

    That gate is ONE-DIRECTIONAL: it covers many candidates for one incoming
    entry, not many incoming entries converging on one candidate. Two sibling
    engagements in the same import that both near-hit the same entity all land
    on it, and for experience the first one seen in group order wins the
    rename. The callers' re-verification is what keeps that from thrashing —
    once the title is upgraded the next sibling is no longer strictly richer,
    so it renames nothing. Deliberate: those siblings genuinely are the one
    stored role until a human splits them.

    Deterministic. No DB, no LLM. O(len(candidates)) per call with regex work
    per pair; called only on an exact-key miss, so the common path never
    reaches it.
    """
    matcher = _NEAR_MATCHERS.get(section)
    if matcher is None:
        return None
    key = entry if isinstance(entry, tuple) else identity_key(section, entry)
    hits: list[Any] = []
    for candidate_key, value in candidates.items():
        if matcher(key, candidate_key) and not any(value is seen for seen in hits):
            hits.append(value)
    return hits[0] if len(hits) == 1 else None


# ===========================================================================
# Task 9 — consolidate(): entity resolution + point clustering + DB write
# ===========================================================================

# Section -> KB entity kind. certifications handled separately (no bullets).
_SECTION_KIND = {"experience": "experience", "projects": "project", "education": "education"}
_ONGOING_TOKENS = {"present", "current", "ongoing", "now"}
_CERT_ORG_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")


def _field_count(entry: Any) -> int:
    if isinstance(entry, dict):
        return sum(1 for v in entry.values() if v not in (None, "", [], {}, ()))
    return 1 if str(entry or "").strip() else 0


def _richest_member(members: list[SourceEntry]) -> SourceEntry:
    """Member whose entry has the most non-empty fields (first wins on ties)."""
    return max(members, key=lambda m: _field_count(m.entry))


def _derive_status(section: str, members: list[SourceEntry]) -> str:
    """Ongoing/completed status for a created entity.

    Experience is ongoing when ANY member lacks an end_date (or marks it
    present/current). Projects/education default to completed — an empty
    end_date is the norm there, not a signal — flipping to ongoing only on an
    explicit present/current token. Certifications are always completed.
    """
    if section == "certifications":
        return "completed"
    for m in members:
        e = m.entry if isinstance(m.entry, dict) else {}
        end = (e.get("end_date") or "").strip()
        if section == "experience" and (not end or _norm(end) in _ONGOING_TOKENS):
            return "ongoing"
        if section != "experience" and _norm(end) in _ONGOING_TOKENS:
            return "ongoing"
    return "completed"


def _split_cert(raw: str) -> tuple[str, str | None]:
    """Split a cert string into (title, org): a trailing '(org)' becomes org."""
    s = str(raw or "").strip()
    m = _CERT_ORG_RE.match(s)
    if m and m.group(1).strip():
        return m.group(1).strip(), (m.group(2).strip() or None)
    return s, None


def _cert_string(entity: KBEntity) -> str:
    return entity.title if not entity.org else f"{entity.title} ({entity.org})"


def _group_repr(group: Group) -> dict[str, Any]:
    """Best {kind,title,org,start_date,end_date} for a group's richest member."""
    m = _richest_member(group.members)
    e = m.entry if isinstance(m.entry, dict) else {}
    if group.section == "experience":
        return {"kind": "experience", "title": e.get("role") or "", "org": e.get("company") or None,
                "start_date": e.get("start_date"), "end_date": e.get("end_date")}
    if group.section == "projects":
        return {"kind": "project", "title": e.get("name") or "", "org": None,
                "start_date": e.get("date"), "end_date": None}
    if group.section == "education":
        return {"kind": "education", "title": e.get("degree") or "", "org": e.get("institution") or None,
                "start_date": e.get("start_date"), "end_date": e.get("end_date")}
    return {"kind": group.section, "title": _norm(m.entry), "org": None,
            "start_date": None, "end_date": None}


# --- rendering helpers (LLM prompt inputs) ---------------------------------


def _render_groups(family_groups: list[Group]) -> str:
    lines = []
    for i, g in enumerate(family_groups):
        r = _group_repr(g)
        dates = " – ".join(x for x in (r.get("start_date"), r.get("end_date")) if x) or "—"
        lines.append(f"[{i}] {r['kind']} | {r['title']} | {r.get('org') or ''} | {dates}")
    return "\n".join(lines) or "(none)"


def _render_existing_entities(entities: list[KBEntity]) -> str:
    return "\n".join(f"{e.id} | {e.title} | {e.org or ''}" for e in entities) or "(none)"


def _render_candidates(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates):
        srcs = ", ".join(sorted({s["resume_key"] for s in c["sources"]}))
        lines.append(f"[{i}] ({srcs}) {c['rep_text']}")
    return "\n".join(lines)


def _render_existing_points(points: list[KBPoint]) -> str:
    return "\n".join(f"{p.id} | {p.text}" for p in points) or "(none)"


def _entity_ctx_line(entity: KBEntity) -> str:
    lines = [f"kind: {entity.kind}", f"title: {entity.title}"]
    if entity.org:
        lines.append(f"org: {entity.org}")
    tech = (entity.detail_json or {}).get("tech")
    if tech:
        lines.append(f"tech: {tech}")
    return "\n".join(lines)


# --- entity construction ---------------------------------------------------


def _make_entity(
    section: str,
    canonical: dict,
    groups_in: list[Group],
    *,
    origin: str | None = None,
    origin_detail: str | None = None,
) -> KBEntity:
    """Build a new KBEntity for an experience/project cluster from canonical +
    richest-member fallbacks."""
    kb_kind = _SECTION_KIND[section]
    members = [m for g in groups_in for m in g.members]
    repr0 = _group_repr(groups_in[0])
    title = (str(canonical.get("title") or "").strip()) or repr0["title"] or "(untitled)"
    org = canonical.get("org")
    org = str(org).strip() if (org and str(org).strip()) else repr0["org"]
    start = canonical.get("start_date") or repr0["start_date"]
    end = canonical.get("end_date") or repr0["end_date"]

    detail: dict[str, Any] = {}
    rich = _richest_member(members)
    e = rich.entry if isinstance(rich.entry, dict) else {}
    if section == "projects":
        org = None  # projects carry no org
        for k in ("tech", "link", "date"):
            if e.get(k):
                detail[k] = e[k]
    elif section == "experience":
        if e.get("location"):
            detail["location"] = e["location"]
    return KBEntity(
        kind=kb_kind, title=title, org=org,
        start_date=start or None, end_date=end or None,
        status=_derive_status(section, members), detail_json=detail,
        origin=origin, origin_detail=origin_detail,
    )


def _make_education_entity(
    group: Group, *, origin: str | None = None, origin_detail: str | None = None
) -> KBEntity:
    m = _richest_member(group.members)
    e = m.entry if isinstance(m.entry, dict) else {}
    detail: dict[str, Any] = {}
    for k in ("field", "gpa", "coursework", "location", "graduation_date"):
        if e.get(k):
            detail[k] = e[k]
    title = (e.get("degree") or "").strip() or (e.get("institution") or "").strip() or "(education)"
    org = (e.get("institution") or "").strip() or None
    return KBEntity(
        kind="education", title=title, org=org,
        start_date=(e.get("start_date") or None), end_date=(e.get("end_date") or None),
        status=_derive_status("education", group.members), detail_json=detail,
        origin=origin, origin_detail=origin_detail,
    )


def _make_cert_entity(
    group: Group, *, origin: str | None = None, origin_detail: str | None = None
) -> KBEntity:
    rep = next((str(m.entry).strip() for m in group.members if str(m.entry or "").strip()), "")
    title, org = _split_cert(rep)
    return KBEntity(kind="certification", title=title or rep or "(certification)",
                    org=org, status="completed", detail_json={},
                    origin=origin, origin_detail=origin_detail)


def _make_extra_entity(
    group: Group, *, origin: str | None = None, origin_detail: str | None = None
) -> KBEntity:
    m = _richest_member(group.members)
    e = m.entry if isinstance(m.entry, dict) else {}
    sec_key = e.get("section_key") or "section"
    sec_type = e.get("section_type") or "entries"
    sec_title = e.get("section_title") or sec_key.title()
    detail: dict[str, Any] = {
        "section_key": sec_key,
        "section_type": sec_type,
        "section_title": sec_title,
    }
    if sec_type == "entries":
        title = (e.get("heading") or "").strip() or (e.get("title") or "").strip() or "(untitled)"
        org = (e.get("subheading") or "").strip() or None
        for k in ("subheading", "location", "date", "link"):
            if e.get(k):
                detail[k] = e[k]
    else:  # bullets
        title = (e.get("section_title") or e.get("title") or sec_key.title() or "").strip()
        org = None

    return KBEntity(
        kind="extra",
        title=title,
        org=org,
        status="completed",
        detail_json=detail,
        origin=origin,
        origin_detail=origin_detail,
    )


# --- existing-entity identity indexes (no-LLM matching) --------------------
#
# These dicts are also the CANDIDATE SETS handed to ``find_near_identity`` on
# an exact-key miss, which is the second reason their keys must equal what
# ``identity_key`` builds.
#
# An index key MUST equal the ``identity_key`` of the source entry that would
# create the same row, or a re-run forks a second entity forever. The catch is
# that ``identity_key`` reads the SOURCE fields while the index reads the
# STORED ones, and the ``_make_*`` builders substitute a fallback title when the
# source field is blank (``degree or institution``, ``role or "(untitled)"``,
# ``name or "(untitled)"``). ``_identity_title`` reverses exactly those
# substitutions so the two keys agree again.

# Titles no source entry can supply — they only ever come from a _make_* fallback.
_FALLBACK_TITLES = frozenset({"(untitled)", "(education)"})


def _identity_title(entity: KBEntity) -> str:
    """The stored title as ``identity_key`` would have seen the source field."""
    title = _norm(entity.title)
    if title in _FALLBACK_TITLES:
        return ""
    if entity.kind == "education" and entity.org and title == _norm(entity.org):
        # _make_education_entity fell back `degree or institution`.
        return ""
    return title


def _identity_index(
    session: Session,
    kind: str,
    key: Any,
    *,
    incoming_org: str | None = None,
) -> dict[tuple, KBEntity]:
    """Identity key -> entity for one kind, oldest row winning a tie.

    Ordered because when two rows share an identity key the SAME one has to win
    on every run, and an unordered select promises nothing. Oldest-first
    because the older row is the one carrying the accumulated points and port
    logs, so it is the right thing to merge onto.
    """
    out: dict[tuple, KBEntity] = {}
    normalized_incoming_org = _norm(incoming_org)
    entities = session.scalars(
        select(KBEntity)
        .where(KBEntity.kind == kind)
        .order_by(KBEntity.created_at, KBEntity.id)
    )
    for e in entities:
        candidate_org = _norm(e.org)
        if (
            normalized_incoming_org
            and candidate_org
            and normalized_incoming_org != candidate_org
        ):
            continue
        out.setdefault(key(e), e)
    return out


def _existing_edu_index(
    session: Session, *, incoming_org: str | None = None
) -> dict[tuple, KBEntity]:
    # institution=org, degree=title
    return _identity_index(
        session,
        "education",
        lambda e: (_norm(e.org), _identity_title(e)),
        incoming_org=incoming_org,
    )


def _existing_cert_index(
    session: Session, *, incoming_org: str | None = None
) -> dict[tuple, KBEntity]:
    return _identity_index(
        session,
        "certification",
        lambda e: (_norm(_cert_string(e)),),
        incoming_org=incoming_org,
    )


def _existing_exp_index(
    session: Session, *, incoming_org: str | None = None
) -> dict[tuple, KBEntity]:
    return _identity_index(
        session,
        "experience",
        lambda e: (_norm(e.org), _identity_title(e), e.start_date or ""),
        incoming_org=incoming_org,
    )


def _existing_proj_index(
    session: Session, *, incoming_org: str | None = None
) -> dict[tuple, KBEntity]:
    return _identity_index(
        session,
        "project",
        lambda e: (_identity_title(e),),
        incoming_org=incoming_org,
    )


def _existing_extra_index(
    session: Session, *, incoming_org: str | None = None
) -> dict[tuple, KBEntity]:
    def _key(e: KBEntity) -> tuple:
        detail = e.detail_json or {}
        sec_key = _norm(detail.get("section_key"))
        sec_type = detail.get("section_type")
        if sec_type == "entries":
            return ("extra", sec_key, _identity_title(e))
        return ("extra", sec_key)

    return _identity_index(session, "extra", _key, incoming_org=incoming_org)


def richer_experience_title(stored: str, incoming: Any) -> str | None:
    """The incoming role title, when it is strictly richer than ``stored``.

    A near-hit says the two titles are variants of one role; it does not say
    which variant to keep. The rule is one-directional: the incoming title wins
    only when its token set is a proper SUPERSET of the stored one — "Data
    Analyst" becoming "Data Analyst, British Airways Account". A poorer or equal
    variant returns None, so re-importing an older, terser resume can never
    strip detail the KB already has.

    Read-only, so the read-only sync classifier can PROPOSE a rename that only
    the writing path performs. Certifications and projects never rename at all:
    a cert's title carries its exam code and issuer, and a project name has no
    company or date corroborating which form is the real one.
    """
    title = str(incoming or "").strip()
    tokens = _tokens(title)
    if not tokens or not (_tokens(stored) < tokens):
        return None
    return title


def upgrade_experience_title(entity: KBEntity, incoming_title: Any) -> bool:
    """Apply ``richer_experience_title`` to ``entity``; True when it renamed."""
    title = richer_experience_title(entity.title, incoming_title)
    if title is None:
        return False
    entity.title = title
    return True


def _match_or_create_identity(
    session: Session,
    section: str,
    groups: list[Group],
    index: dict[tuple, KBEntity],
    make: Any,
    report: Any,
    on_entity: Any,
) -> None:
    """Identity-key match-or-create used by both consolidation entry points.

    Second pass on an exact-key MISS only: ``find_near_identity`` gets a look
    before a new entity is created, so a re-imported "AWS Certified AI
    Practitioner (AIF-C01)" lands on the "AWS Certified AI Practitioner"
    already in the KB instead of forking. A near-matched entity is filed under
    the incoming key too, so a later group with the same key hits exactly.
    """
    for g in groups:
        ent = index.get(g.key)
        if ent is None:
            ent = find_near_identity(section, g.key, index)
        created = ent is None
        if created:
            ent = make(g)
            session.add(ent)
            report.entities_created += 1
        else:
            report.entities_matched += 1
            if section == "experience" and upgrade_experience_title(ent, _group_repr(g)["title"]):
                report.titles_upgraded.append(ent.title)
        index[g.key] = ent
        on_entity(ent, g, created)


# --- Stage B: experience/project entity resolution (LLM) -------------------


def _resolve_family(
    session: Session, family_groups: list[Group], section: str,
    tmpl: str, smart_model: str, report: ConsolidationReport,
) -> dict[int, KBEntity]:
    """Resolve one LLM family (experience or projects) into KBEntities.

    Returns id(group) -> KBEntity for every group. Never loses a group: unknown
    LLM indices are dropped (warned), omitted groups become singletons, and an
    unusable response falls back to one-entity-per-group.

    THIS PATH NEVER RENAMES an existing entity. Matching here is the LLM
    picking an ``existing_entity_id`` out of a list it was shown, which is a
    different act from the deterministic near-identity hit that
    ``_match_or_create_identity`` upgrades a title on: there the two titles are
    provably token-subsets, here the model asserted the match and its
    ``canonical`` title is its own invention. So a cluster that matches keeps
    the stored title untouched, and ``ConsolidationReport.titles_upgraded``
    stays empty on this path by construction, not by accident. Anything added
    here that renames on a match needs its own justification and its own tests
    — do not reach for ``upgrade_experience_title`` because it is nearby.
    """
    result: dict[int, KBEntity] = {}
    if not family_groups:
        return result
    kb_kind = _SECTION_KIND[section]
    existing = list(session.scalars(select(KBEntity).where(KBEntity.kind == kb_kind)))
    existing_by_id = {str(e.id): e for e in existing}

    prompt = (
        tmpl.replace("$groups", _render_groups(family_groups))
        .replace("$existing_entities", _render_existing_entities(existing))
    )
    clusters = None
    try:
        res = llm.call_openai(prompt=prompt, model=smart_model,
                              response_format="json", trace_name="kb-entity-resolve")
        if isinstance(res, dict):
            clusters = res.get("clusters")
    except Exception as exc:  # noqa: BLE001 — LLM failure must not lose groups
        report.warnings.append(f"entity_resolve LLM failed for {kb_kind}: {exc}")

    def _new_singleton(g: Group) -> None:
        ent = _make_entity(section, {}, [g], origin="consolidated")
        session.add(ent)
        report.entities_created += 1
        result[id(g)] = ent

    if not (isinstance(clusters, list) and clusters):
        report.warnings.append(f"entity_resolve unusable for {kb_kind}; one entity per group")
        for g in family_groups:
            _new_singleton(g)
        return result

    covered: set[int] = set()
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        idxs: list[int] = []
        for gi in cluster.get("group_indices") or []:
            if not (isinstance(gi, int) and 0 <= gi < len(family_groups)):
                report.warnings.append(f"entity_resolve unknown group index {gi!r} for {kb_kind}")
            elif gi in covered:
                report.warnings.append(f"group {gi} ({kb_kind}) in multiple clusters; keeping first")
            else:
                idxs.append(gi)
        if not idxs:
            continue
        covered.update(idxs)
        groups_in = [family_groups[i] for i in idxs]
        raw_existing = cluster.get("existing_entity_id")
        matched = existing_by_id.get(str(raw_existing)) if raw_existing else None
        if matched is not None:
            ent = matched
            report.entities_matched += 1
        else:
            canonical = cluster.get("canonical")
            ent = _make_entity(
                section,
                canonical if isinstance(canonical, dict) else {},
                groups_in,
                origin="consolidated",
            )
            session.add(ent)
            report.entities_created += 1
        for g in groups_in:
            result[id(g)] = ent

    for i, g in enumerate(family_groups):
        if id(g) not in result:
            report.warnings.append(f"group {i} ({kb_kind}) omitted by entity_resolve; kept as singleton")
            _new_singleton(g)
    return result


# --- Stage C: bullet clustering + point writing (LLM) ----------------------


def _gather_source_bullets(groups: list[Group]) -> list[dict]:
    bullets: list[dict] = []
    for g in groups:
        for m in g.members:
            e = m.entry if isinstance(m.entry, dict) else {}
            for b in e.get("bullets") or []:
                if isinstance(b, str) and b.strip():
                    bullets.append({"text": b, "resume_key": m.resume_key, "section": m.section})
    return bullets


def _cluster_candidates(source_bullets: list[dict]) -> tuple[list[dict], int]:
    """Collapse exact/normalized duplicate bullets into candidates.

    Returns (candidates, duplicates_skipped). Each candidate has rep_text,
    sources, and key (the point_text_key).
    """
    candidates: list[dict] = []
    by_norm: dict[str, dict] = {}
    for sb in source_bullets:
        key = point_text_key(sb["text"])
        c = by_norm.get(key)
        if c is None:
            c = {"rep_text": sb["text"], "sources": [], "key": key}
            by_norm[key] = c
            candidates.append(c)
        c["sources"].append(sb)
    return candidates, len(source_bullets) - len(candidates)


def _cluster_points_for_entity(
    session: Session, entity: KBEntity, groups: list[Group],
    tmpl: str, smart_model: str, report: ConsolidationReport,
) -> None:
    """Cluster an entity's source bullets into KB points, then backfill port logs.

    Exact/normalized duplicates collapse in code before the LLM. Each candidate
    (distinct-norm bullet) maps to exactly one point; every source bullet gets a
    port-log row pointing at its candidate's point. No bullet is ever lost.
    """
    source_bullets = _gather_source_bullets(groups)
    if not source_bullets:
        return

    candidates, skipped = _cluster_candidates(source_bullets)
    report.duplicates_skipped += skipped

    existing_points = [p for p in entity.points if p.state != "retired"]
    prompt = (
        tmpl.replace("$entity_context", _entity_ctx_line(entity))
        .replace("$bullets", _render_candidates(candidates))
        .replace("$existing_points", _render_existing_points(existing_points))
    )
    clusters = None
    try:
        res = llm.call_openai(prompt=prompt, model=smart_model,
                              response_format="json", trace_name="kb-cluster-points")
        if isinstance(res, dict):
            clusters = res.get("clusters")
    except Exception as exc:  # noqa: BLE001 — LLM failure must not lose bullets
        report.warnings.append(f"cluster_points LLM failed for {entity.title!r}: {exc}")

    candidate_point: dict[int, KBPoint] = {}
    now = datetime.now(UTC)

    def _new_approved(idx: int) -> None:
        p = KBPoint(entity_id=entity.id, text=candidates[idx]["rep_text"],
                    state="approved", origin="consolidated",
                    provenance="user_authored", approved_at=now)
        session.add(p)
        report.points_approved += 1
        candidate_point[idx] = p

    if not (isinstance(clusters, list) and clusters):
        report.warnings.append(f"cluster_points unusable for {entity.title!r}; one approved point per candidate")
        for i in range(len(candidates)):
            _new_approved(i)
    else:
        existing_pt_by_id = {str(p.id): p for p in existing_points}
        covered: set[int] = set()
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            idxs: list[int] = []
            for bi in cluster.get("bullet_indices") or []:
                if not (isinstance(bi, int) and 0 <= bi < len(candidates)):
                    report.warnings.append(f"cluster_points unknown bullet index {bi!r} for {entity.title!r}")
                elif bi in covered:
                    report.warnings.append(f"candidate {bi} in multiple clusters for {entity.title!r}; keeping first")
                else:
                    idxs.append(bi)
            if not idxs:
                continue
            covered.update(idxs)
            raw_existing = cluster.get("existing_point_id")
            existing_pt = existing_pt_by_id.get(str(raw_existing)) if raw_existing else None
            merged = cluster.get("merged_text")
            merged = merged.strip() if isinstance(merged, str) and merged.strip() else None

            if existing_pt is not None:
                for i in idxs:
                    candidate_point[i] = existing_pt
            elif len(idxs) > 1 and merged:
                srcs = [
                    {"resume_key": sb["resume_key"], "section": sb["section"], "text": sb["text"]}
                    for i in idxs for sb in candidates[i]["sources"]
                ]
                p = KBPoint(entity_id=entity.id, text=merged, state="draft",
                            origin="consolidated", provenance="derived_unverified",
                            merge_sources_json=srcs)
                session.add(p)
                report.points_draft += 1
                for i in idxs:
                    candidate_point[i] = p
            else:
                for i in idxs:
                    _new_approved(i)

        for i in range(len(candidates)):
            if i not in covered:
                report.warnings.append(f"candidate {i} omitted by cluster_points for {entity.title!r}; kept as singleton")
                _new_approved(i)

    session.flush()  # new points get ids before port-log FKs
    # Idempotent backfill: re-running consolidate() with identical sources must
    # not accumulate duplicate rows (POST /api/kb/consolidate is re-invokable).
    # Dedup against existing rows in one query rather than N.
    existing_logs = session.scalars(
        select(KBPortLog).where(KBPortLog.entity_id == entity.id)
    ).all()
    seen = {(r.point_id, r.resume_key, r.section, _norm(r.ported_text)) for r in existing_logs}
    for idx, cand in enumerate(candidates):
        point = candidate_point.get(idx)
        pid = point.id if point is not None else None
        for sb in cand["sources"]:
            key = (pid, sb["resume_key"], sb["section"], _norm(sb["text"]))
            if key in seen:
                continue
            seen.add(key)
            session.add(KBPortLog(
                entity_id=entity.id, point_id=pid, resume_kind="base",
                resume_key=sb["resume_key"], section=sb["section"], ported_text=sb["text"],
                direction="from_source",
            ))


# --- Stage D/E: skills union + profile seed --------------------------------


def _merge_skills(session: Session, sources: list[tuple[str, dict]], report: ConsolidationReport) -> None:
    """Union {category, items} skill groups across sources into the profile.

    Categories union by normalized name (first-seen name wins); items dedup by
    normalized text. Existing profile categories are extended, never removed.

    Reports both granularities: ``skills_merged`` (categories touched) and
    ``skills_items_added`` (the individual skills that landed). See
    ConsolidationReport — a summary that counts the former reads "1 skill" when
    two arrived in the same category.
    """
    unioned: list[dict] = []
    cat_index: dict[str, dict] = {}
    for _rk, data in sources:
        for grp in data.get("skills") or []:
            if not isinstance(grp, dict):
                continue
            cat = grp.get("category")
            if not (isinstance(cat, str) and cat.strip()):
                continue
            entry = cat_index.get(_norm(cat))
            if entry is None:
                entry = {"category": cat.strip(), "items": [], "norms": set()}
                cat_index[_norm(cat)] = entry
                unioned.append(entry)
            for it in grp.get("items") or []:
                if isinstance(it, str) and it.strip() and _norm(it) not in entry["norms"]:
                    entry["norms"].add(_norm(it))
                    entry["items"].append(it.strip())
    if not unioned:
        return

    from app.services.career_kb import get_or_create_profile
    profile = get_or_create_profile(session)
    # DEEP copy: a shallow list() would share the nested category dicts with
    # SQLAlchemy's committed JSONB snapshot, so mutating items in place would
    # leave has_changes() False and silently emit no UPDATE.
    skills = copy.deepcopy(profile.skills_json or [])
    by_norm: dict[str, dict] = {
        _norm(g["category"]): g for g in skills if isinstance(g, dict) and isinstance(g.get("category"), str)
    }
    # This loop is the PROFILE write — the union above only decides what the
    # sources collectively claim. An item counts as added here and nowhere
    # else: in the source union it may well be something the profile already
    # has.
    for entry in unioned:
        target = by_norm.get(_norm(entry["category"]))
        if target is None:
            new_grp = {"category": entry["category"], "items": list(entry["items"])}
            skills.append(new_grp)
            by_norm[_norm(entry["category"])] = new_grp
            report.skills_merged.append(entry["category"])
            # Brand-new category: every item in it is new to the profile.
            report.skills_items_added.extend(entry["items"])
        else:
            have = {_norm(x) for x in (target.get("items") or []) if isinstance(x, str)}
            items = list(target.get("items") or [])
            newly_added: list[str] = []
            for it in entry["items"]:
                if _norm(it) not in have:
                    items.append(it)
                    have.add(_norm(it))
                    newly_added.append(it)
            if newly_added:
                target["items"] = items
                report.skills_merged.append(target.get("category", entry["category"]))
                report.skills_items_added.extend(newly_added)
    profile.skills_json = skills


def _seed_profile(session: Session, sources: list[tuple[str, dict]]) -> None:
    """Seed profile contact/summary from the last source without clobbering."""
    if not sources:
        return
    from app.services.career_kb import get_or_create_profile
    profile = get_or_create_profile(session)
    master = sources[-1][1]
    contact = profile.contact_json if isinstance(profile.contact_json, dict) else {}
    if not (contact.get("name") or "").strip():
        src_contact = master.get("contact")
        if isinstance(src_contact, dict) and src_contact:
            profile.contact_json = src_contact
    if not (profile.summary or "").strip():
        src_summary = master.get("summary")
        if isinstance(src_summary, str) and src_summary.strip():
            profile.summary = src_summary.strip()


# --- resume-text parsing (upload path) -------------------------------------


RESUME_PARSE_CAP = 40_000


def _validate_with_salvage(payload: dict) -> tuple[dict, list[str]]:
    """Validate as ResumeData; on failure drop ONLY the rejected list entries and retry once.

    Salvage never touches contact/summary errors (they mean the parse is unusable) and
    reports every drop, so a bad row in one section cannot cost the whole file.
    """
    from pydantic import ValidationError
    from app.schemas.resume import ResumeData

    try:
        return ResumeData.model_validate(payload).model_dump(mode="json"), []
    except ValidationError as exc:
        salvageable = {"experience", "projects", "education", "certifications",
                       "skills", "extra_sections"}
        drop: dict[str, set[int]] = {}
        for err in exc.errors():
            loc = err.get("loc") or ()
            if len(loc) >= 2 and loc[0] in salvageable and isinstance(loc[1], int):
                drop.setdefault(loc[0], set()).add(loc[1])
            else:
                raise  # not an entry-level defect — salvage can't help
        pruned = dict(payload)
        warnings: list[str] = []
        for section, indices in drop.items():
            rows = list(pruned.get(section) or [])
            pruned[section] = [r for i, r in enumerate(rows) if i not in indices]
            warnings.append(f"dropped {len(indices)} unparseable {section} item(s)")
        return ResumeData.model_validate(pruned).model_dump(mode="json"), sorted(warnings)


def prefetch_prompts(session: Session) -> None:
    """Resolve every prompt this pipeline uses, on a clean session.

    `prompts.get_prompt` INSERTs its file default and COMMITS on first use. Any
    caller that builds rows and then resolves a prompt mid-flight gets that
    half-built state committed underneath it. The consolidate() body already
    pre-fetches for this reason; multi-step callers (kb_import) need the same
    guarantee before they add anything to the session.
    """
    for key in (
        "kb_resume_parse",
        "kb_entity_resolve",
        "kb_cluster_points",
    ):
        prompts.get_prompt(key, session)
    model_settings.get_smart_model(session)


def parse_resume_text(session: Session, text: str) -> tuple[dict, list[str]]:
    """Parse raw resume text into validated ResumeData plus salvage warnings.

    Raises ValueError (router -> 422) on unusable/invalid output.
    """
    if not (text or "").strip():
        raise ValueError("resume text is empty")
    from app.services import extra_section_presets
    prompt = (
        prompts.get_prompt("kb_resume_parse", session)
        .replace("$extra_section_presets", extra_section_presets.prompt_block())
        .replace("$resume_text", (text or "")[:RESUME_PARSE_CAP])
    )
    try:
        result = llm.call_openai(prompt=prompt, model=model_settings.get_smart_model(session),
                                 response_format="json", trace_name="kb-resume-parse")
    except Exception as exc:  # noqa: BLE001 — provider outage is transient, not a bad file
        # RuntimeError (not ValueError) so the router maps it to 502, keeping 422
        # for genuinely invalid ResumeData. A 422 would tell the client its file
        # is bad and not to retry, which is wrong for an upstream outage.
        raise RuntimeError(f"resume parse LLM call failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("resume parse returned a non-object")
    try:
        return _validate_with_salvage(result)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"resume parse produced invalid ResumeData: {e}") from e


# --- entry point -----------------------------------------------------------


def consolidate(
    session: Session,
    sources: list[tuple[str, dict]],
    *,
    commit: bool = True,
) -> ConsolidationReport:
    """Consolidate resume sources into the Career KB.

    ``sources`` is a list of (resume_key, ResumeData-dict). Runs entity
    resolution (identity key for education/certs/extras — the near-identity
    second pass is effective only for certifications, the one of the three
    with a matcher — and ``kb_entity_resolve`` for experience/projects),
    bullet clustering + point writing
    (``kb_cluster_points``), port-log backfill, a code-only skills union, and a
    non-clobbering profile seed. Commits by default and returns a
    ``ConsolidationReport``; callers may pass ``commit=False`` to own the
    surrounding transaction.
    """
    report = ConsolidationReport()
    groups = group_by_identity(collect_entries(sources))
    by_section: dict[str, list[Group]] = {s: [] for s in ALL_SECTIONS}
    for g in groups:
        by_section[g.section].append(g)

    # Pre-fetch prompt templates + model. get_prompt() may INSERT+commit its
    # default on first use; do it now on a clean session, before we create rows.
    entity_tmpl = prompts.get_prompt("kb_entity_resolve", session)
    cluster_tmpl = prompts.get_prompt("kb_cluster_points", session)
    smart_model = model_settings.get_smart_model(session)

    entity_groups: dict[KBEntity, list[Group]] = {}

    def _register(ent: KBEntity, group: Group, _created: bool = False) -> None:
        entity_groups.setdefault(ent, []).append(group)

    # Stage B — education / certifications / extras (no LLM: identity key,
    # then near-identity on a miss, so a re-imported cert that grew an exam
    # code lands on the cert already there)
    _match_or_create_identity(
        session, "education", by_section["education"], _existing_edu_index(session),
        lambda g: _make_education_entity(g, origin="consolidated"), report, _register,
    )
    _match_or_create_identity(
        session, "certifications", by_section["certifications"], _existing_cert_index(session),
        lambda g: _make_cert_entity(g, origin="consolidated"), report, _register,
    )
    _match_or_create_identity(
        session, "extra", by_section["extra"], _existing_extra_index(session),
        lambda g: _make_extra_entity(g, origin="consolidated"), report, _register,
    )

    # Stage B — experience + projects (kb_entity_resolve, one call per family)
    for section in ("experience", "projects"):
        fam = by_section[section]
        mapping = _resolve_family(session, fam, section, entity_tmpl, smart_model, report)
        for g in fam:
            _register(mapping[id(g)], g)

    session.flush()  # every entity gets an id before point/port-log FKs

    # Stage C — bullet clustering + point writing (certifications have no bullets)
    for ent, gs in list(entity_groups.items()):
        if ent.kind == "certification":
            continue
        _cluster_points_for_entity(session, ent, gs, cluster_tmpl, smart_model, report)

    # Stage D — skills union
    _merge_skills(session, sources, report)
    # Stage E — profile contact/summary seed
    _seed_profile(session, sources)

    if commit:
        session.commit()
    return report


def _write_verbatim_points(
    session: Session,
    entity: KBEntity,
    groups: list[Group],
    report: DeterministicConsolidationReport,
    *,
    origin: str,
    origin_detail: str | None,
) -> list[KBPoint]:
    """One DRAFT point per distinct-norm bullet; no LLM merge.

    Draft, not approved: the bullets were transcribed by an agent, and a
    docstring convention is not a gate. ``kb_approve_points`` (or the /career
    inbox) is where they enter the approved set that composes resumes.

    Dedup is against the entity's points in EVERY state — a retired point is a
    decision the user already made, and re-ingesting the same resume must not
    resurrect it as a fresh draft.
    """
    source_bullets = _gather_source_bullets(groups)
    if not source_bullets:
        return []

    existing_points = session.scalars(
        select(KBPoint).where(KBPoint.entity_id == entity.id)
    ).all()
    existing_norms = {point_text_key(p.text) for p in existing_points}

    candidates, skipped = _cluster_candidates(source_bullets)
    report.duplicates_skipped += skipped

    created: list[KBPoint] = []
    for cand in candidates:
        if cand["key"] in existing_norms:
            # The candidate's own representative bullet is a duplicate too —
            # the within-batch collapse above only counted its siblings.
            report.duplicates_skipped += 1
            continue
        p = KBPoint(
            entity_id=entity.id,
            text=cand["rep_text"],
            state="draft",
            origin=origin,
            origin_detail=origin_detail,
            provenance="user_authored",
            merge_sources_json=[
                {"resume_key": s["resume_key"], "section": s["section"], "text": s["text"]}
                for s in cand["sources"]
            ],
        )
        session.add(p)
        report.points_created += 1
        created.append(p)
        existing_norms.add(cand["key"])

    # Port logs mirror what _cluster_points_for_entity backfills per source
    # bullet — every bullet, including one that deduped onto a point already
    # there. Without them _usage_from_logs reports zero usage and the explore
    # build-areas view misclassifies every point this path wrote.
    session.flush()  # new points need ids before the port-log FKs
    existing_logs = session.scalars(
        select(KBPortLog).where(KBPortLog.entity_id == entity.id)
    ).all()
    seen = {(r.point_id, r.resume_key, r.section, _norm(r.ported_text)) for r in existing_logs}
    by_key = {point_text_key(p.text): p for p in [*existing_points, *created]}
    for cand in candidates:
        point = by_key.get(cand["key"])
        if point is None:
            continue
        for sb in cand["sources"]:
            key = (point.id, sb["resume_key"], sb["section"], _norm(sb["text"]))
            if key in seen:
                continue
            seen.add(key)
            session.add(KBPortLog(
                entity_id=entity.id, point_id=point.id, resume_kind="base",
                resume_key=sb["resume_key"], section=sb["section"], ported_text=sb["text"],
                direction="from_source",
            ))
    return created


def consolidate_deterministic(
    session: Session,
    sources: list[tuple[str, dict]],
    *,
    origin: str | None = None,
    origin_detail: str | None = None,
    commit: bool = True,
) -> DeterministicConsolidationReport:
    """LLM-free consolidation: identity match, verbatim draft points.

    Experience/projects match by ``identity_key`` first, then — like every
    section with a matcher (experience, certifications, projects) — by the
    conservative near-identity second pass on a miss (``find_near_identity``);
    education/extras stay identity-key only. The caller no longer has to normalize entity
    names across resumes for the near cases that pass covers, but everything
    outside them still forks. Near-duplicate bullets that do not share a
    normalized-text key both land; that is accepted. New points land as
    ``draft``; approval is a separate, explicit step.

    This path can RENAME an existing entity: an experience near-hit whose
    incoming role title is strictly richer upgrades the stored title, and every
    rename is named in ``report.titles_upgraded``. It is the only entity write
    here that touches a row the run did not create.

    ``origin``/``origin_detail`` come from the request's write origin. An
    ``mcp`` write stamps its points ``origin="mcp"`` so they show up in the
    /career entity timeline, which only reports agent-written rows.
    """
    report = DeterministicConsolidationReport()
    groups = group_by_identity(collect_entries(sources))
    by_section: dict[str, list[Group]] = {s: [] for s in ALL_SECTIONS}
    for g in groups:
        by_section[g.section].append(g)

    entity_groups: dict[KBEntity, list[Group]] = {}
    created_flag: dict[int, bool] = {}

    def _register(ent: KBEntity, group: Group, created: bool) -> None:
        entity_groups.setdefault(ent, []).append(group)
        if id(ent) not in created_flag:
            created_flag[id(ent)] = created
            if created:
                ent.origin = origin
                ent.origin_detail = origin_detail

    _match_or_create_identity(
        session, "education", by_section["education"], _existing_edu_index(session),
        lambda g: _make_education_entity(g, origin=origin, origin_detail=origin_detail),
        report, _register,
    )
    _match_or_create_identity(
        session, "certifications", by_section["certifications"], _existing_cert_index(session),
        lambda g: _make_cert_entity(g, origin=origin, origin_detail=origin_detail),
        report, _register,
    )
    _match_or_create_identity(
        session, "extra", by_section["extra"], _existing_extra_index(session),
        lambda g: _make_extra_entity(g, origin=origin, origin_detail=origin_detail),
        report, _register,
    )
    _match_or_create_identity(
        session, "experience", by_section["experience"], _existing_exp_index(session),
        lambda g: _make_entity("experience", {}, [g], origin=origin, origin_detail=origin_detail),
        report, _register,
    )
    _match_or_create_identity(
        session, "projects", by_section["projects"], _existing_proj_index(session),
        lambda g: _make_entity("projects", {}, [g], origin=origin, origin_detail=origin_detail),
        report, _register,
    )

    session.flush()

    point_origin = "mcp" if origin == "mcp" else "consolidated"
    created_points: list[KBPoint] = []
    for ent, gs in list(entity_groups.items()):
        if ent.kind == "certification":
            continue
        landed = _write_verbatim_points(
            session, ent, gs, report,
            origin=point_origin, origin_detail=origin_detail,
        )
        if landed and ent.status == "archived":
            # Matching an archived entity is LLM-path parity, but the points
            # are invisible to every composed resume until it is un-archived.
            report.warnings.append(
                f"points landed on archived entity '{ent.title}' — "
                "hidden from composed resumes"
            )
        created_points.extend(landed)

    _merge_skills(session, sources, report)
    _seed_profile(session, sources)

    session.flush()

    report.entities = [
        DeterministicEntityRef(
            id=ent.id, kind=ent.kind, title=ent.title, org=ent.org,
            created=created_flag[id(ent)],
        )
        for ent in entity_groups
    ]
    report.points = [
        DeterministicPointRef(id=p.id, entity_id=p.entity_id, text=p.text)
        for p in created_points
    ]

    if commit:
        session.commit()
    return report
