"""Evidence-ladder classification: one batched LLM call for cache misses,
per-bullet cache keyed by content hash. The LLM never emits severities,
scores, or findings — a bounded enum only (design: 'the three calls')."""
import hashlib
import json
import logging
import math
import re
from string import Template as StringTemplate

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bullet_classification import BulletClassification
from app.models.bullet_dispute import BulletDispute
from app.services import llm, model_settings, prompts
from app.services.health_score import LEVEL_VALUES

logger = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.6

RUBRIC_VERSION = 2
_LEVEL_RANK = ("unaddressed", "implied", "adjacent", "analogue", "direct")
_NUMBER_ASK = re.compile(r"\d|\bhow (?:many|much)\b|\bwhat (?:number|percent|percentage)\b"
                         r"|\bquantif|\bmetric", re.IGNORECASE)
_WORD = re.compile(r"[a-z][a-z'-]{3,}")


def _s(value, limit: int) -> str | None:
    """A trimmed string of at most `limit` chars, or None for anything else (the model may send
    numbers, lists or objects where a string belongs)."""
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(c, 0.0), 1.0) if math.isfinite(c) else 0.0


def _validate(text: str, entry: dict, *, metric_unavailable: bool = False) -> dict | None:
    """STRUCTURAL checks on one model entry. They catch malformed and invented output; they
    do not prove the judgment is right (the golden set measures that)."""
    level = entry.get("level") if isinstance(entry, dict) else None
    if not isinstance(level, str) or level not in LEVEL_VALUES:   # a list/dict level must not raise
        return None
    # Resolve applicability FIRST, so this very response's flag demotes its own number ask.
    metric_unavailable = metric_unavailable or entry.get("metric_unavailable") is True
    norm = " ".join(text.split()).lower()
    raw_ev = entry.get("evidence")
    raw_ev = raw_ev if isinstance(raw_ev, list) else []   # a bare string is not a list of quotes
    spans = []
    for s in raw_ev:
        s = _s(s, 200)
        # A quote must be verbatim AND carry content: at least 3 words, so "the" can't back a level.
        if s and len(s.split()) >= 3 and " ".join(s.split()).lower() in norm:
            spans.append(s)
    spans = spans[:3]
    if _LEVEL_RANK.index(level) > _LEVEL_RANK.index("adjacent") and not spans:
        level = "adjacent"

    question = _s(entry.get("question"), 200)
    ask_kind = entry.get("ask_kind") if entry.get("ask_kind") in ("measure", "detail") else "detail"
    target = _s(entry.get("measure_target"), 60)
    alt = _s(entry.get("alt_question"), 200)
    # The target must name the bullet's own thing: at least half of its content words appear
    # as WHOLE words in the text (not as substrings of other words).
    text_words = set(_WORD.findall(norm))
    target_words = _WORD.findall(target.lower()) if target else []
    target_in_text = bool(target_words) and (
        sum(w in text_words for w in target_words) * 2 >= len(target_words))
    alt_ok = bool(alt) and not _NUMBER_ASK.search(alt)
    if ask_kind == "measure" and (metric_unavailable or not (target_in_text and alt_ok)):
        # Demote to a detail ask. The number question itself must go too: use the number-free
        # alternative when it is valid, else None (Task 6 falls back to static detail copy).
        ask_kind, question = "detail", (alt if alt_ok else None)
    if ask_kind == "detail" and question and _NUMBER_ASK.search(question):
        question = alt if alt_ok else None   # a "detail" ask may not smuggle in a number demand
    if level == "direct":
        question, ask_kind = None, None
    elif question is None:
        ask_kind = "detail"
    keep_measure = ask_kind == "measure"

    raw_lang = entry.get("language")
    langs = []
    for x in raw_lang if isinstance(raw_lang, list) else []:
        span, fix = (_s(x.get("span"), 80), _s(x.get("fix"), 80)) if isinstance(x, dict) else (None, None)
        if span and fix and span != fix and span in text:
            langs.append({"span": span, "fix": fix})
    return {"level": level, "evidence": spans, "question": question, "ask_kind": ask_kind,
            "measure_target": target if keep_measure else None,
            "alt_question": alt if keep_measure else None,
            "language": langs[:3], "reason": _s(entry.get("reason"), 120) or "",
            "confidence": _confidence(entry.get("confidence")),
            "new_fact": _s(entry.get("new_fact"), 300),          # dispute calls only (Task 7)
            "metric_unavailable": metric_unavailable}


def content_hash(text: str) -> str:
    normalized = " ".join(str(text).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _result(level: str, *, reason: str = "", confidence: float | None = None,
            source: str = "llm", uncertain: bool = False, assessment: dict | None = None) -> dict:
    fields = assessment or {}
    return {
        "evidence": fields.get("evidence") or [],
        "question": fields.get("question"),
        "ask_kind": fields.get("ask_kind"),
        "measure_target": fields.get("measure_target"),
        "alt_question": fields.get("alt_question"),
        "language": fields.get("language") or [],
        "level": level,
        "value": LEVEL_VALUES[level],
        "reason": reason,
        "confidence": confidence,
        "source": source,
        "uncertain": uncertain,
    }


_ASK_FIELDS = ("question", "ask_kind", "measure_target", "alt_question")


def without_number_ask(text: str, result: dict) -> dict:
    """`result` with `_validate(..., metric_unavailable=True)` applied to its ask: the user said no
    number exists for this text, so a measure ask becomes its number-free alternative. Only the
    ask fields change; the level, evidence and source stay as they are."""
    revalidated = _validate(text, result, metric_unavailable=True)
    if revalidated is None:
        return result
    return {**result, **{k: revalidated[k] for k in _ASK_FIELDS}}


def _dispute_result(row: BulletDispute) -> dict:
    revised = row.revised_json or {}
    confidence = revised.get("confidence")
    return _result(revised["level"], reason=revised.get("reason") or "", confidence=confidence,
                   source="dispute",
                   uncertain=(confidence if confidence is not None else 1.0) < CONFIDENCE_FLOOR,
                   assessment=revised)


def set_override(
    db: Session, chash: str, level: str | None, reason: str | None = None
) -> None:
    if level is not None and level not in LEVEL_VALUES:
        raise ValueError(f"Unknown level: {level}")
    row = db.get(BulletClassification, chash)
    if row is None:
        row = BulletClassification(content_hash=chash, level=level or "adjacent")
        db.add(row)
    row.override_level = level
    row.override_reason = reason.strip() if level is not None and reason else None
    db.commit()


def classify_items(db: Session, items: list[dict]) -> dict[str, dict]:
    """items: [{text, hints: [str]}] → {content_hash: result}.
    Empty text is deterministic; cached rows are free; only misses hit the LLM.
    Precedence: override > dispute (same rubric version and model) > evaluation. A dispute's
    `metric_unavailable` is the user's fact about the work, so it demotes number asks on every
    evaluation of that text, whatever the model or rubric."""
    out: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    texts: dict[str, str] = {}
    model = model_settings.get_smart_model(db)
    hashes = {content_hash(str(item.get("text") or "").strip()) for item in items}
    disputes = {d.content_hash: d for d in db.scalars(
        select(BulletDispute).where(BulletDispute.content_hash.in_(hashes)))}

    for item in items:
        text = str(item.get("text") or "").strip()
        chash = content_hash(text)
        if chash in out or chash in pending:
            continue
        if not text:
            out[chash] = _result("unaddressed", reason="empty bullet",
                                 confidence=1.0, source="deterministic")
            continue
        texts[chash] = text
        row = db.get(BulletClassification, chash)
        if row is not None and row.override_level:
            out[chash] = _result(row.override_level,
                                 reason=row.override_reason or "user override",
                                 confidence=1.0, source="override")
            continue
        dispute = disputes.get(chash)
        if (dispute is not None and dispute.rubric_version == RUBRIC_VERSION
                and dispute.model == model):
            out[chash] = _dispute_result(dispute)
            continue
        if row is not None:
            if row.rubric_version == RUBRIC_VERSION and row.model == model:
                out[chash] = _result(
                    row.level, reason=row.reason or "", confidence=row.confidence,
                    source="cache",
                    uncertain=(row.confidence if row.confidence is not None else 1.0)
                    < CONFIDENCE_FLOOR,
                    assessment={"evidence": row.evidence_json, "question": row.question,
                                "ask_kind": row.ask_kind, "measure_target": row.measure_target,
                                "alt_question": row.alt_question, "language": row.language_json},
                )
                continue
        pending[chash] = {"id": chash, "text": text, "hints": item.get("hints") or []}

    if pending:
        out.update(_classify_batch(db, pending))
    for chash, dispute in disputes.items():
        if dispute.metric_unavailable and out.get(chash, {}).get("source") in ("cache", "llm"):
            out[chash] = without_number_ask(texts[chash], out[chash])
    return out


def _evaluate_batch(db: Session, pending: dict[str, dict]) -> dict[str, dict]:
    """Uncached validated assessments; no classification writes (also used by disputes)."""
    template = prompts.get_prompt("resume_bullet_classify", db)
    prompt = StringTemplate(template).safe_substitute(
        items_json=json.dumps(list(pending.values()), indent=2)
    )
    raw = llm.call_openai(
        prompt=prompt, model=model_settings.get_smart_model(db), response_format="json",
        trace_name="resume_bullet_classify",
    )
    entries = raw.get("classifications") if isinstance(raw, dict) else None
    by_id = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("id")
        if not isinstance(key, str) or key not in pending:
            continue
        assessment = _validate(pending[key]["text"], entry)
        if assessment is not None:
            by_id[key] = assessment
    return by_id


def _classify_batch(db: Session, pending: dict[str, dict]) -> dict[str, dict]:
    by_id = _evaluate_batch(db, pending)
    model = model_settings.get_smart_model(db)
    out: dict[str, dict] = {}
    for chash in pending:
        entry = by_id.get(chash)
        if entry is None:
            out[chash] = _result("implied", reason="classifier could not decide",
                                 confidence=0.0, uncertain=True)
            continue
        confidence = entry["confidence"]
        out[chash] = _result(
            entry["level"], reason=entry["reason"], confidence=confidence,
            source="cache", uncertain=confidence < CONFIDENCE_FLOOR, assessment=entry,
        )
        row = db.get(BulletClassification, chash)
        if row is None:
            row = BulletClassification(content_hash=chash)
            db.add(row)
        row.level, row.reason, row.confidence = entry["level"], entry["reason"], confidence
        row.model, row.rubric_version = model, RUBRIC_VERSION
        row.evidence_json, row.language_json = entry["evidence"], entry["language"]
        row.question, row.ask_kind = entry["question"], entry["ask_kind"]
        row.measure_target, row.alt_question = entry["measure_target"], entry["alt_question"]
    db.commit()
    return out
