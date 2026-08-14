"""JD-independent resume health check v2: evidence-ladder scoring + gates.

The LLM only classifies bullets; everything
here is deterministic. Score is the mean of evidence levels over experience +
projects + custom-section bullets, capped by structure/content gates. Attention
zones drive severity, fix ordering, C1, and UI — never the score.

See SYSTEM.md §4 (ResumeLintReport) for the report's place in the workflow.
"""
import hashlib
import logging
import re
from collections.abc import Mapping
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.health_gate_waiver import HealthGateWaiver
from app.models.resume_lint_report import ResumeLintReport
from app.services import (
    bullet_classify,
    health_gates,
    health_guards,
    health_score,
    health_verify,
    health_zones,
    model_settings,
    template_registry,
    template_validation,
)
from app.services.resume_versions import latest_version as _latest_version

logger = logging.getLogger(__name__)

MODEL_VERSION = "health-v2"
MAX_REWRITES = 5
HOT_ZONE_FLOOR = 0.40  # C1: midpoint of 0.30 (learns nothing) and 0.50 (learns what)

# Kept from v1 — now advisory/classifier inputs, not score terms.
WEAK_OPENERS = (
    "responsible for", "worked on", "helped", "assisted", "involved in",
    "participated in", "tasked with", "duties included",
)
PASSIVE_HINT = re.compile(r"^\s*(was|were)\s+\w+ed\b", re.IGNORECASE)
MAX_BULLET_WORDS = 34
MIN_BULLET_WORDS = 8
MAX_SKILL_ITEM_WORDS = 5  # a skills item longer than this reads as a sentence
MAX_BULLETS_PER_ENTRY = 7

# Static coaching copy per level (design ladder table). No LLM cost.
LADDER_COPY: dict[str, dict[str, str]] = {
    "unaddressed": {
        "issue": "Describes a duty, not an achievement.",
        "why": "Duty phrasing signals passivity; recruiters scan the first words for ownership.",
        "how": "Rewrite to lead with an ownership verb that names what you did.",
    },
    "implied": {
        "issue": "A reader can't tell what you did here.",
        "why": "The contribution is vague or team-level, so your role is unclear.",
        "how": "Rewrite to name the specific action you personally took.",
    },
    "adjacent": {
        "issue": "Specific, but carries no number.",
        "why": "You say what you built; you don't say what it did.",
        "how": "Add the metric that measures it.",
        "question": "What number measures this — users, rows, %, time saved?",
    },
    "analogue": {
        "issue": "Has a scale metric, but not a business outcome.",
        "why": "The number measures the thing, not the result it produced.",
        "how": "Add the outcome if you have it; otherwise this bullet is already strong.",
        "question": "Do you know what this saved, earned, or improved?",
    },
}

Location = tuple  # (section, index|None, bullet_index|None)


# --------------------------------------------------------------------------- #
# small helpers

def _fid(ftype: str, location: Location, issue: str) -> str:
    """Deterministic finding id (content-derived, so re-runs are byte-identical)."""
    return hashlib.sha256(f"{ftype}|{location}|{issue}".encode()).hexdigest()[:10]


def _loc_dict(location: Location) -> dict[str, Any]:
    section, index, bi = location
    d: dict[str, Any] = {"section": section}
    if index is not None:
        d["index"] = index
    if bi is not None:
        d["bullet_index"] = bi
    return d


def _finding(ftype: str, location: Location, label: str, issue: str, why: str, how: str,
             *, severity: str = "minor", level: float | None = None, cost: float = 0.0,
             zone: str | None = None, suggestion: str | None = None,
             question: str | None = None, source: str = "rule",
             content_hash: str | None = None,
             classification_level: str | None = None,
             classification_source: str | None = None,
             classification_reason: str | None = None,
             rule: str | None = None,
             subject: str | None = None) -> dict[str, Any]:
    """`subject`, when set, is the RAW source string this finding is about —
    unstripped, unnormalized — suitable as an exact-match needle against the
    resume's own arrays (e.g. `items.index(subject)`). Display copy (label,
    issue) may use a cleaned-up version of the same text; `subject` must not
    be that cleaned-up version, or a downstream exact-match lookup silently
    fails against a padded source item. Absent when the rule has no single
    source string to point at (e.g. summary.missing, entry.too_many_bullets).
    """
    finding = {
        "id": _fid(ftype, location, issue),
        "type": ftype,               # gate | fix | ask | note
        "severity": severity,        # critical | minor
        "location": _loc_dict(location),
        "label": label,
        "issue": issue,
        "why": why,
        "how": how,
        "level": level,
        "cost": round(cost, 3),
        "zone": zone,                # hot | cold | None
        "suggestion": suggestion,
        "question": question,
        "source": source,
    }
    if content_hash is not None:
        finding.update({
            "content_hash": content_hash,
            "classification_level": classification_level,
            "classification_source": classification_source,
            "classification_reason": classification_reason,
        })
    if rule is not None:
        finding["rule"] = rule
    if subject is not None:
        finding["subject"] = subject
    return finding


_PUNCT_NAMES = {".": "period", ",": "comma", ";": "semicolon", "…": "ellipsis"}


def _punct_note(section: str, label_prefix: str, text: str, raw: str) -> dict:
    """`text` is the stripped display form (quoted in label/issue); `raw` is
    the unstripped source string, passed through unchanged as `subject` so it
    stays a valid exact-match needle against the resume's own array."""
    name = _PUNCT_NAMES.get(text[-1], "punctuation mark")
    return _finding(
        "note", (section, None, None), f"{label_prefix} · {text}",
        f'"{text}" ends with a stray {name}.',
        "List items aren't sentences; stray punctuation reads as careless.",
        "Drop the trailing punctuation.", source="rule",
        rule=f"{section}.trailing_punct", subject=raw)


def _classification_fields(resume: dict, loc: Location, result: dict) -> dict[str, Any]:
    """Stable API metadata for findings produced by the evidence classifier."""
    return {
        "content_hash": bullet_classify.content_hash(_text_at(resume, loc)),
        "classification_level": result["level"],
        "classification_source": result.get("source"),
        "classification_reason": result.get("reason") or None,
    }


def _gate_dict(gate_id: str, tier: str, status: str, label: str, detail: str) -> dict[str, Any]:
    return {
        "id": gate_id,
        "tier": tier,
        "status": status,
        "label": label,
        "detail": detail,
        **health_gates.gate_copy(gate_id),
    }


def _prior_gate(prior_report: dict | None, gate_id: str) -> dict | None:
    if not prior_report:
        return None
    return next((g for g in prior_report.get("gates", []) if g.get("id") == gate_id), None)


def _entry_label(section: str, entry: dict) -> str:
    if section == "experience":
        return f"{entry.get('company', '?')} — {entry.get('role', '?')}"
    if section == "projects":
        return str(entry.get("name", "?"))
    return f"{entry.get('institution', '?')} — {entry.get('degree', '?')}"


def _extra_section(resume: dict, section_loc: str) -> dict:
    key = section_loc.removeprefix("extra:")
    for section in resume.get("extra_sections") or []:
        if section.get("key") == key:
            return section
    return {}


def _label_at(resume: dict, location: Location) -> str:
    section, index, bi = location
    if section == "summary":
        return "Summary"
    if section.startswith("extra:"):
        # A location may outlive its section (rename/delete between runs, or a
        # caller of the assemble seam) — degrade like the frontend does, never raise.
        sec = _extra_section(resume, section)
        label = str(sec.get("title") or sec.get("key") or "Custom section")
        if index is not None:
            entries = sec.get("entries") or []
            heading = str((entries[index] if index < len(entries) else {}).get("heading") or "")
            if heading:
                label += f" — {heading}"
        if bi is not None:
            label += f" · bullet {bi + 1}"
        return label
    entry = (resume.get(section) or [])[index]
    label = _entry_label(section, entry)
    if bi is not None:
        label += f" · bullet {bi + 1}"
    return label


def _text_at(resume: dict, location: Location) -> str:
    section, index, bi = location
    if section == "summary":
        return str(resume.get("summary") or "")
    if section.startswith("extra:"):
        # Same stale-location tolerance as _label_at: "" not IndexError.
        sec = _extra_section(resume, section)
        if index is None:  # flat bullets section
            bullets = sec.get("bullets") or []
            return str(bullets[bi]) if bi < len(bullets) else ""
        entries = sec.get("entries") or []
        bullets = (entries[index] if index < len(entries) else {}).get("bullets") or []
        return str(bullets[bi]) if bi < len(bullets) else ""
    entry = (resume.get(section) or [])[index]
    return str((entry.get("bullets") or [])[bi])


def _classify_hints(text: str) -> list[str]:
    lowered = text.lower().strip()
    if any(lowered.startswith(w) for w in WEAK_OPENERS):
        return ["weak_opener"]
    if PASSIVE_HINT.search(text):
        return ["passive"]
    return []


def _ladder_items(resume: dict) -> list[tuple[Location, str]]:
    """(location, text) for summary + every enabled experience/projects/custom-section bullet.
    Education/certifications are facts, never on the ladder."""
    items: list[tuple[Location, str]] = []
    summary = (resume.get("summary") or "").strip()
    if summary:
        items.append((("summary", None, None), summary))
    for section in ("experience", "projects"):
        for index, entry in health_zones.enabled_entries(resume, section):
            for bi, bullet in enumerate(entry.get("bullets") or []):
                items.append(((section, index, bi), str(bullet)))
    for section in resume.get("extra_sections") or []:
        if not section.get("enabled", True):
            continue
        skey = f"extra:{section.get('key')}"
        if section.get("type") == "bullets":
            for bi, bullet in enumerate(section.get("bullets") or []):
                items.append(((skey, None, bi), str(bullet)))
        else:
            for ei, entry in enumerate(section.get("entries") or []):
                if not entry.get("enabled", True):
                    continue
                for bi, bullet in enumerate(entry.get("bullets") or []):
                    items.append(((skey, ei, bi), str(bullet)))
    return items


def _level_name(value: float) -> str:
    for name, v in health_score.LEVEL_VALUES.items():
        if v == value:
            return name
    return "adjacent"


# --------------------------------------------------------------------------- #
# structure gates (template-inherited + resume-JSON contact)

def structure_gates(db: Session, template_id: str | None, resume: dict) -> list[dict]:
    """S1 (parse fidelity, fatal), S2 (contact reachable, fatal), S4 (headers, serious).

    Inherited from the resume's template certification. If the template was never
    certified (parse_certified is None), certify it lazily — a gate you didn't run
    is not a gate you passed, so we run it rather than reporting a green checkmark.
    """
    tmpl = template_registry.get_usable_template(template_id, db)
    if tmpl.parse_certified is None:
        try:
            template_validation.validate_template(tmpl.id, db)
            db.refresh(tmpl)
        except Exception:  # noqa: BLE001 — never let a cert failure crash the health run
            logger.exception("lazy template certification failed for %s", tmpl.id)
    report = tmpl.parse_report_json or {}

    # S1 — parse fidelity
    if tmpl.parse_certified is None:
        s1 = _gate_dict("S1", "fatal", "not_assessed", "Parse fidelity",
                        "Could not certify the template's PDF text extraction.")
    elif tmpl.parse_certified:
        s1 = _gate_dict("S1", "fatal", "pass", "Parse fidelity",
                        "The template's PDF round-trips through a strict extractor intact.")
    else:
        missing = report.get("missing") or []
        s1 = _gate_dict("S1", "fatal", "fail", "Parse fidelity",
                        "The template's PDF drops text under a strict extractor: "
                        + ", ".join(missing))

    # S2 — contact reachable: email required in JSON AND extractable from the template.
    # Phone is optional in 2026 norms → contact-hygiene advisory, not this fatal gate.
    contact = resume.get("contact") or {}
    has_email = bool(str(contact.get("email") or "").strip())
    email_ok = report.get("email_ok")  # True/False/None(not assessed)
    if not has_email:
        s2 = _gate_dict("S2", "fatal", "fail", "Contact reachable",
                        "No email address in the resume — recruiters can't reach you.")
    elif email_ok is False:
        s2 = _gate_dict("S2", "fatal", "fail", "Contact reachable",
                        "Your email is in the data but the template's PDF renders it "
                        "where a strict extractor drops it.")
    elif email_ok is None:
        s2 = _gate_dict("S2", "fatal", "not_assessed", "Contact reachable",
                        "Email present in data; template extraction not certified.")
    else:
        s2 = _gate_dict("S2", "fatal", "pass", "Contact reachable",
                        "Email present and survives PDF extraction.")

    # S4 — standard headers, from the template's extracted text
    if not report:
        s4 = _gate_dict("S4", "serious", "not_assessed", "Standard headers",
                        "Template header extraction not certified.")
    else:
        headers_missing = report.get("headers_missing") or []
        if headers_missing:
            s4 = _gate_dict("S4", "serious", "fail", "Standard headers",
                            "These standard section headers didn't survive extraction: "
                            + ", ".join(headers_missing))
        else:
            s4 = _gate_dict("S4", "serious", "pass", "Standard headers",
                            "Standard section headers are present and extractable.")

    return [s1, s2, s4]


# --------------------------------------------------------------------------- #
# assembly (pure — no DB, no LLM; rewrite_fn is injected)

def _final_gates(
    levels_by_loc: dict[Location, dict], base_gates: list[dict], hot: set,
    waivers: set[str] | Mapping[str, str], c2_hit: dict | None, prior_report: dict | None,
) -> tuple[list[dict], float | None]:
    """Base gates + the two assembled-here gates (C1/C2), waivers applied."""
    gates = [
        {**g, **health_gates.gate_copy(g["id"])}
        for g in base_gates
    ]  # copy; we mutate status for waivers

    # C1 — hot-zone evidence floor (serious). E_hot spans hot locations incl. the summary.
    hot_values = [levels_by_loc[loc]["value"] for loc in hot if loc in levels_by_loc]
    e_hot = sum(hot_values) / len(hot_values) if hot_values else None
    if e_hot is not None and e_hot < HOT_ZONE_FLOOR:
        gates.append(_gate_dict(
            "C1", "serious", "fail", "Hot-zone evidence floor",
            f"Top-of-resume evidence averages {e_hot:.2f} (floor {HOT_ZONE_FLOOR}); "
            "a dead opening sharply cuts the odds of a deep read."))

    # C2 — claim/date consistency: ask on first detection, cap once ignored.
    if c2_hit:
        prior_c2 = _prior_gate(prior_report, "C2")
        escalate = prior_c2 is not None and prior_c2.get("status") in ("ask", "fail")
        gates.append(_gate_dict(
            "C2", "serious", "fail" if escalate else "ask", "Claim/date consistency",
            f"Summary claims {c2_hit['claimed_years']}+ years; the dates support "
            f"~{c2_hit['actual_years']}."))

    # Waivers: a user-waived FAILING gate stops capping.
    for g in gates:
        if g["id"] in waivers and g["status"] == "fail":
            g["status"] = "waived"
            if isinstance(waivers, Mapping):
                g["waiver_reason"] = waivers[g["id"]]
    return gates, e_hot


def _gate_findings(gates: list[dict]) -> list[dict]:
    """One finding per failing/asking gate (not pass/waived/not_assessed)."""
    findings: list[dict] = []
    for g in gates:
        if g["status"] == "fail":
            findings.append(_finding(
                "gate", ("gate", None, None), g["label"], g["detail"],
                g["why"], g["fix_hint"],
                severity="critical", source="rule"))
        elif g["status"] == "ask" and g["id"] == "C2":
            findings.append(_finding(
                "ask", ("summary", None, None), "Summary", g["detail"],
                "A recruiter who catches a year mismatch stops trusting the rest.",
                "Confirm the number or add the missing role.",
                severity="critical",
                question="Is a role missing from your dates, or should the summary say fewer years?",
                source="rule"))
    return findings


def _ladder_findings(
    resume: dict, levels_by_loc: dict[Location, dict], hot: set,
    rewrite_fn: Callable[[str], str | None] | None,
) -> list[dict]:
    """Per-bullet findings from the ladder, weakest bullets rewritten first."""
    findings: list[dict] = []
    fix_candidates: list[tuple[Location, dict]] = []
    for loc, r in levels_by_loc.items():
        value = r["value"]
        is_hot = loc in hot
        zone = "hot" if is_hot else "cold"
        sev = health_zones.severity(value, hot=is_hot)
        cost = health_zones.cost(value, hot=is_hot)
        label = _label_at(resume, loc)
        classification = _classification_fields(resume, loc, r)

        if r.get("uncertain"):
            copy = LADDER_COPY["adjacent"]
            findings.append(_finding(
                "ask", loc, label, "Ambiguous — this may be missing a number.",
                "The classifier couldn't decide; usually that means a metric is almost there.",
                copy["how"], severity=sev, level=value, cost=cost, zone=zone,
                question="Is there a number attached to this that you left out?", source="llm",
                **classification))
            continue
        if value >= 1.0:
            continue  # direct accomplishment — nothing to say
        if value >= 0.80:
            if not is_hot:
                continue  # stop nagging strong cold bullets
            copy = LADDER_COPY["analogue"]
            findings.append(_finding(
                "ask", loc, label, copy["issue"], copy["why"], copy["how"],
                severity=sev, level=value, cost=cost, zone=zone,
                question=copy["question"], source="llm", **classification))
            continue
        if value >= 0.50:
            copy = LADDER_COPY["adjacent"]
            findings.append(_finding(
                "ask", loc, label, copy["issue"], copy["why"], copy["how"],
                severity=sev, level=value, cost=cost, zone=zone,
                question=copy["question"], source="llm", **classification))
            continue
        # value <= 0.30 → fix candidate (rewrite), deferred so we can rank by cost
        fix_candidates.append((loc, r))

    # rewrite the top MAX_REWRITES fix candidates by cost; the rest become asks.
    fix_candidates.sort(
        key=lambda kv: health_zones.cost(kv[1]["value"], hot=(kv[0] in hot)), reverse=True)
    for i, (loc, r) in enumerate(fix_candidates):
        value = r["value"]
        is_hot = loc in hot
        zone = "hot" if is_hot else "cold"
        sev = health_zones.severity(value, hot=is_hot)
        cost = health_zones.cost(value, hot=is_hot)
        label = _label_at(resume, loc)
        copy = LADDER_COPY[_level_name(value)]
        classification = _classification_fields(resume, loc, r)
        suggestion = (
            rewrite_fn(_text_at(resume, loc))
            if (rewrite_fn and i < MAX_REWRITES and not loc[0].startswith("extra:"))
            else None
        )  # extras have no bullet-scoped /edits op yet (SYSTEM.md §11 item 20) — ask, don't offer Apply
        if suggestion:
            findings.append(_finding(
                "fix", loc, label, copy["issue"], copy["why"], copy["how"],
                severity=sev, level=value, cost=cost, zone=zone,
                suggestion=suggestion, source="llm", **classification))
        else:
            findings.append(_finding(
                "ask", loc, label, copy["issue"], copy["why"], copy["how"],
                severity=sev, level=value, cost=cost, zone=zone,
                question="What did you personally do here, and what changed because of it?",
                source="llm", **classification))
    return findings


def _gap_findings(gap_hits: list[dict]) -> list[dict]:
    """Employment-gap asks (best-evidenced finding; a stated reason recovers most of it)."""
    findings: list[dict] = []
    for gap in gap_hits:
        loc = ("experience", None, None)
        covered = gap.get("covered_months", 0)
        uncovered = gap.get("uncovered_months", gap["months"])
        if covered > 0:
            issue = (f"{gap['months']}-month gap between {gap['after']} and {gap['before']} — "
                     f"{covered} months covered by your education; "
                     f"{uncovered} months unaccounted.")
            question = f"What were you doing in the remaining {uncovered} months?"
        else:
            issue = (f"Unexplained {gap['months']}-month gap between "
                     f"{gap['after']} and {gap['before']}.")
            question = f"What were you doing between {gap['after']} and {gap['before']}?"
        if gap.get("context"):
            issue += f" ({gap['context']})"
        findings.append(_finding(
            "ask", loc, "Employment gap", issue,
            "Unexplained gaps cost ~45% of callbacks; one line of explanation recovers most of it.",
            "Add a short line (study, care, travel, contracting) covering the gap.",
            question=question,
            source="rule"))
    return findings


def assemble(resume: dict, levels_by_loc: dict[Location, dict], base_gates: list[dict],
             tier: str, hot: set, *, prior_report: dict | None = None,
             waivers: set[str] | Mapping[str, str] | None = None,
             gap_hits: list[dict] | None = None,
             c2_hit: dict | None = None,
             rewrite_fn: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Turn classified levels + gates into a scored report with typed findings.

    This is the Health Report ASSEMBLY INTERFACE — the pure seam the test suite
    drives directly (run_report is the DB/LLM-orchestrating wrapper around it).
    Treat its signature as a contract, not an internal.

    `rewrite_fn(text) -> str | None` produces a guarded rewrite (None = ask). It is
    called for at most MAX_REWRITES fix candidates, ranked by cost.
    """
    gates, e_hot = _final_gates(
        levels_by_loc, base_gates, hot, waivers or set(), c2_hit, prior_report
    )

    # Score: mean over experience + projects + custom-section levels
    # (summary is not scored), then capped by gates.
    score_levels = [r["value"] for loc, r in levels_by_loc.items()
                    if loc[0] in ("experience", "projects") or loc[0].startswith("extra:")]
    raw_score = health_score.compute_score(score_levels)
    score = health_score.apply_gates(raw_score, gates)
    grade = health_score.grade_for(score)

    # 1) gates, 2) per-bullet ladder, 3) employment gaps
    findings = [
        *_gate_findings(gates),
        *_ladder_findings(resume, levels_by_loc, hot, rewrite_fn),
        *_gap_findings(gap_hits or []),
    ]

    # 4) shape notes + advisories — all type=note, weight 0.
    # A per-bullet advisory (length, etc.) must not duplicate a bullet that
    # already carries a ladder fix/ask; the ladder finding is the primary signal.
    covered = {
        (f["location"].get("section"), f["location"].get("index"),
         f["location"].get("bullet_index"))
        for f in findings
        if f["type"] in ("fix", "ask") and f["location"].get("bullet_index") is not None
    }
    findings.extend(_shape_notes(resume, levels_by_loc, tier, hot))
    for note in _advisories(resume):
        nloc = note["location"]
        if nloc.get("bullet_index") is not None and (
            nloc.get("section"), nloc.get("index"), nloc.get("bullet_index")
        ) in covered:
            continue
        findings.append(note)

    findings.sort(key=_sort_key)

    counts = {
        "gate": sum(1 for g in gates if g["status"] == "fail"),
        "critical": sum(1 for f in findings
                        if f["severity"] == "critical" and f["type"] in ("fix", "ask")),
        "ask": sum(1 for f in findings if f["type"] == "ask"),
        "note": sum(1 for f in findings if f["type"] == "note"),
    }

    report = {
        "score": score, "grade": grade, "tier": tier,
        "gates": gates, "counts": counts, "findings": findings,
    }
    features = {
        "levels": {f"{loc[0]}:{loc[1]}:{loc[2]}": r["value"]
                   for loc, r in levels_by_loc.items()},
        "e_hot": e_hot, "raw_score": raw_score,
        "hot": [f"{loc[0]}:{loc[1]}:{loc[2]}" for loc in sorted(hot, key=str)],
    }
    return {"report": report, "features": features}


_TYPE_RANK = {"gate": 0, "fix": 1, "ask": 1, "note": 2}


def _sort_key(f: dict) -> tuple:
    # gates first, then fix/ask by cost desc, notes last.
    return (_TYPE_RANK.get(f["type"], 1), -float(f.get("cost") or 0.0), f["label"])


# --------------------------------------------------------------------------- #
# shape notes + advisories (deterministic, weight 0)

def _shape_notes(resume: dict, levels_by_loc: dict, tier: str, hot: set) -> list[dict]:
    notes: list[dict] = []
    exp = health_zones.enabled_entries(resume, "experience")
    proj = health_zones.enabled_entries(resume, "projects")
    job_bullets = sum(len(e.get("bullets") or []) for _, e in exp)
    proj_bullets = sum(len(e.get("bullets") or []) for _, e in proj)

    if tier != "early" and proj_bullets > job_bullets and job_bullets > 0:
        notes.append(_finding(
            "note", ("projects", None, None), "Evidence concentrated in projects",
            f"{proj_bullets} project bullets vs {job_bullets} employment bullets.",
            "For an experienced candidate, project-heavy evidence can read junior.",
            "Lead with employment; move projects below.", source="rule"))

    if len(exp) >= 2:
        b0 = len((exp[0][1].get("bullets") or []))
        b1 = len((exp[1][1].get("bullets") or []))
        if b0 < b1:
            notes.append(_finding(
                "note", ("experience", exp[0][0], None), "Current role is thin",
                f"Your current role has {b0} bullets; a previous one has {b1}.",
                "Recruiters weight the most recent role most; a thin one undersells you.",
                "Add outcomes to the current role.", source="rule"))

    # strongest work buried
    if levels_by_loc:
        best_loc = max(levels_by_loc, key=lambda loc: levels_by_loc[loc]["value"])
        if levels_by_loc[best_loc]["value"] >= 0.8 and best_loc not in hot:
            notes.append(_finding(
                "note", best_loc, "Strongest work is buried",
                "Your highest-evidence bullet is below the high-attention zone.",
                "A screener may never reach it in the first pass.",
                "Move it into the summary or the top of the first role.", source="rule"))

    return notes


_WORD = re.compile(r"\S+")
_PUNCT_CHARS = re.escape("".join(_PUNCT_NAMES))
# Derived from _PUNCT_NAMES so the charset and the copy cannot drift apart.
_TRAILING_PUNCT = re.compile(f"[{_PUNCT_CHARS}]$")
# \s folded in so a stray space *before* the trailing punctuation (e.g. "Python .")
# is removed along with it, not left dangling after the punctuation is gone.
_TRAILING_PUNCT_RUN = re.compile(rf"[{_PUNCT_CHARS}\s]+$")


def _norm_item(text: str) -> str:
    """Canonical form of a list item: casefold, strip a trailing run of
    punctuation (the same charset _TRAILING_PUNCT flags as stray) and
    whitespace, then collapse internal whitespace.

    Two callers, two comparison semantics: duplicate detection compares these
    keys for EQUALITY; the never-demonstrated rule tests one as a SUBSTRING of
    a bullet blob normalized the same way *minus* the trailing-punctuation
    strip. Invariant: any folding added here must also be applied to that blob,
    or a skill that IS in a bullet gets falsely flagged as undemonstrated.
    """
    stripped = _TRAILING_PUNCT_RUN.sub("", str(text).strip())
    return re.sub(r"\s+", " ", stripped).casefold()


def _advisories(resume: dict) -> list[dict]:
    notes: list[dict] = []
    if not (resume.get("summary") or "").strip():
        notes.append(_finding(
            "note", ("summary", None, None), "Summary", "No summary.",
            "The summary is the first thing read; without one the resume opens with no positioning.",
            "Add 2–3 lines: role identity, years, strongest proof points.", source="rule",
            rule="summary.missing"))

    for section in ("experience", "projects"):
        for index, entry in health_zones.enabled_entries(resume, section):
            bullets = entry.get("bullets") or []
            label = _entry_label(section, entry)
            if len(bullets) > MAX_BULLETS_PER_ENTRY:
                notes.append(_finding(
                    "note", (section, index, None), label,
                    f"{len(bullets)} bullets in one entry.",
                    "Past ~7 bullets, each extra one dilutes the others.",
                    "Keep the strongest 4–6.", source="rule",
                    rule="entry.too_many_bullets"))
            for bi, bullet in enumerate(bullets):
                words = len(_WORD.findall(str(bullet)))
                loc = (section, index, bi)
                if words > MAX_BULLET_WORDS:
                    notes.append(_finding(
                        "note", loc, f"{label} · bullet {bi + 1}",
                        f"Long bullet ({words} words).",
                        "Long bullets get skimmed past.",
                        "Tighten to one line.", source="rule",
                        rule="bullet.too_long", subject=str(bullet)))
                elif 0 < words < MIN_BULLET_WORDS:
                    notes.append(_finding(
                        "note", loc, f"{label} · bullet {bi + 1}",
                        "Very short bullet.", "A few words rarely carry an accomplishment.",
                        "Expand with what changed because of your work.", source="rule",
                        rule="bullet.too_short", subject=str(bullet)))

    # duplicate skills across groups
    seen: dict[str, str] = {}
    for group in resume.get("skills") or []:
        cat = str(group.get("category", ""))
        for item in group.get("items") or []:
            key = _norm_item(item)
            if key in seen and seen[key] != cat:
                notes.append(_finding(
                    "note", ("skills", None, None), f"Skills · {item}",
                    f'"{item}" appears in both "{seen[key]}" and "{cat}".',
                    "Duplicate skills read as padding.",
                    "Keep each skill in one group.", source="rule",
                    rule="skills.duplicate_across_groups", subject=str(item)))
            else:
                seen.setdefault(key, cat)

    # skill listed but never demonstrated in a bullet
    # NOTE: this is a substring match, so a short/punctuated token (e.g. "R.",
    # which normalizes to "r") can match almost any bullet. Bare "R" already
    # had this hole; a word-boundary fix is out of scope (\b breaks on "C++").
    bullet_blob = re.sub(r"\s+", " ", " ".join(
        str(b)
        for section in ("experience", "projects")
        for _, e in health_zones.enabled_entries(resume, section)
        for b in (e.get("bullets") or [])
    )).casefold()
    for group in resume.get("skills") or []:
        for item in group.get("items") or []:
            token = _norm_item(item)
            if token and token not in bullet_blob:
                notes.append(_finding(
                    "note", ("skills", None, None), f"Skills · {item}",
                    f'"{item}" is listed but never demonstrated in a bullet.',
                    "Keyword credit only; an LLM screener sees no evidence behind it.",
                    "Show it in a bullet, or accept it as keyword-only.", source="rule",
                    rule="skills.undemonstrated", subject=str(item)))

    # list-item hygiene: trailing punctuation + sentence-like skills items
    for group in resume.get("skills") or []:
        for item in group.get("items") or []:
            text = str(item).strip()
            if _TRAILING_PUNCT.search(text):
                notes.append(_punct_note("skills", "Skills", text, str(item)))
            if len(_WORD.findall(text)) > MAX_SKILL_ITEM_WORDS:
                notes.append(_finding(
                    "note", ("skills", None, None), f"Skills · {text}",
                    f'"{text}" reads like a sentence, not a skill keyword.',
                    "Skills lists are keyword-scanned; sentences dilute matching.",
                    "Shorten to the tool or technique name; put the story in a bullet.",
                    source="rule", rule="skills.sentence_like", subject=str(item)))
    for cert in resume.get("certifications") or []:
        text = str(cert).strip()
        if _TRAILING_PUNCT.search(text):
            notes.append(_punct_note("certifications", "Certifications", text, str(cert)))

    # duplicate certifications (punctuation/spacing-blind)
    seen_certs: set[str] = set()
    for cert in resume.get("certifications") or []:
        key = _norm_item(cert)
        if not key:
            continue
        if key in seen_certs:
            text = str(cert).strip()
            notes.append(_finding(
                "note", ("certifications", None, None), f"Certifications · {text}",
                f'"{text}" appears more than once.',
                "Duplicate credentials read as padding.",
                "Keep one copy.", source="rule",
                rule="certifications.duplicate", subject=str(cert)))
        seen_certs.add(key)

    return notes


def rule_notes(resume: dict) -> list[dict]:
    """Deterministic, JD-independent rule notes for a resume dict.

    Public because the post-tailoring coherence check reuses these rules
    (design 2026-08-12). Pure — no DB, no LLM, no template. `_shape_notes` is
    deliberately NOT included: it reads LLM-classified evidence levels.
    """
    return _advisories(resume)


# --------------------------------------------------------------------------- #
# orchestration

def run_report(db: Session, kind: str, key: str, resume: dict, *,
               template_id: str | None = None, use_llm: bool = True) -> ResumeLintReport:
    gates = structure_gates(db, template_id, resume)
    gates.append(health_gates.gate_dates(resume))
    gates.append(health_gates.gate_placeholders(resume))

    tier = health_zones.compute_tier(resume)
    zoning_tier = "experienced" if tier == "unknown" else tier
    hot = health_zones.hot_locations(resume, zoning_tier)

    items = _ladder_items(resume)
    levels_by_loc: dict[Location, dict] = {}
    model = None
    if use_llm and items:
        model = model_settings.get_smart_model(db)
        classified = bullet_classify.classify_items(
            db, [{"text": t, "hints": _classify_hints(t)} for _, t in items])
        for loc, text in items:
            r = classified.get(bullet_classify.content_hash(text))
            if r is not None:
                levels_by_loc[loc] = r

    waiver_rows = db.scalars(
        select(HealthGateWaiver).where(
            HealthGateWaiver.resume_kind == kind, HealthGateWaiver.resume_key == key)).all()
    waivers = {w.gate_id: w.reason for w in waiver_rows}

    prior = latest_report(db, kind, key)

    # Rule detectors allege; the LLM verifier may veto or annotate — never create.
    gap_hits = health_gates.detect_gaps(resume)
    c2_hit = health_gates.detect_claim_overstatement(resume)
    verifier_cache: dict = {}
    if use_llm:
        prior_verifier = (prior.features_json or {}).get("verifier") if prior else None
        gap_hits, c2_hit, verifier_cache = health_verify.verify_detections(
            db, resume, gap_hits, c2_hit, prior_cache=prior_verifier)

    def _rewrite(text: str) -> str | None:
        try:
            return health_guards.guarded_rewrite(db, text, context="")
        except Exception:  # noqa: BLE001 — a failed rewrite just degrades to ask
            logger.exception("guarded_rewrite failed")
            return None

    result = assemble(
        resume, levels_by_loc, gates, tier, hot,
        prior_report=prior.report_json if prior else None,
        waivers=waivers,
        gap_hits=gap_hits,
        c2_hit=c2_hit,
        rewrite_fn=_rewrite if use_llm else None,
    )
    result["features"]["verifier"] = verifier_cache

    latest = _latest_version(db, kind, key)
    row = ResumeLintReport(
        resume_kind=kind, resume_key=key,
        resume_version_number=latest.version_number if latest else None,
        report_json=result["report"],
        features_json=result["features"],
        model=model, model_version=MODEL_VERSION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_report(db: Session, kind: str, key: str) -> ResumeLintReport | None:
    return db.scalars(
        select(ResumeLintReport)
        .where(ResumeLintReport.resume_kind == kind, ResumeLintReport.resume_key == key)
        .order_by(ResumeLintReport.created_at.desc())
        .limit(1)
    ).first()
