"""Evidence-ladder classification: one batched LLM call for cache misses,
per-bullet cache keyed by content hash. The LLM never emits severities,
scores, or findings — a bounded enum only (design: 'the three calls')."""
import hashlib
import json
import logging
from string import Template as StringTemplate

from sqlalchemy.orm import Session

from app.models.bullet_classification import BulletClassification
from app.services import llm, model_settings, prompts
from app.services.health_score import LEVEL_VALUES

logger = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.6


def content_hash(text: str) -> str:
    normalized = " ".join(str(text).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _result(level: str, *, reason: str = "", confidence: float | None = None,
            source: str = "llm", uncertain: bool = False) -> dict:
    return {
        "level": level,
        "value": LEVEL_VALUES[level],
        "reason": reason,
        "confidence": confidence,
        "source": source,
        "uncertain": uncertain,
    }


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
    Empty text is deterministic; cached rows are free; only misses hit the LLM."""
    out: dict[str, dict] = {}
    pending: dict[str, dict] = {}

    for item in items:
        text = str(item.get("text") or "").strip()
        chash = content_hash(text)
        if chash in out or chash in pending:
            continue
        if not text:
            out[chash] = _result("unaddressed", reason="empty bullet",
                                 confidence=1.0, source="deterministic")
            continue
        row = db.get(BulletClassification, chash)
        if row is not None:
            if row.override_level:
                out[chash] = _result(row.override_level,
                                     reason=row.override_reason or "user override",
                                     confidence=1.0, source="override")
            else:
                out[chash] = _result(
                    row.level, reason=row.reason or "", confidence=row.confidence,
                    source="cache",
                    uncertain=(row.confidence if row.confidence is not None else 1.0)
                    < CONFIDENCE_FLOOR,
                )
            continue
        pending[chash] = {"id": chash, "text": text, "hints": item.get("hints") or []}

    if pending:
        out.update(_classify_batch(db, pending))
    return out


def _classify_batch(db: Session, pending: dict[str, dict]) -> dict[str, dict]:
    template = prompts.get_prompt("resume_bullet_classify", db)
    prompt = StringTemplate(template).safe_substitute(
        items_json=json.dumps(list(pending.values()), indent=2)
    )
    model = model_settings.get_smart_model(db)
    raw = llm.call_openai(
        prompt=prompt, model=model, response_format="json",
        trace_name="resume_bullet_classify",
    )
    by_id = {}
    for entry in (raw or {}).get("classifications") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") in pending and entry.get("level") in LEVEL_VALUES:
            by_id[entry["id"]] = entry

    out: dict[str, dict] = {}
    for chash, item in pending.items():
        entry = by_id.get(chash)
        if entry is None:
            # Model skipped or mangled this item → degrade into a question,
            # never a guess (design hatch #2). 'implied' + uncertain routes to ask.
            out[chash] = _result("implied", reason="classifier could not decide",
                                 confidence=0.0, uncertain=True)
            continue
        confidence = float(entry.get("confidence") or 0.0)
        out[chash] = _result(
            entry["level"], reason=str(entry.get("reason") or "")[:120],
            confidence=confidence, source="cache",
            uncertain=confidence < CONFIDENCE_FLOOR,
        )
        db.merge(BulletClassification(
            content_hash=chash, level=entry["level"],
            reason=str(entry.get("reason") or "")[:120],
            confidence=confidence, model=model,
        ))
    db.commit()
    return out
