"""Free-text disputes (plan Task 7): the ordinary evaluation, run again with the user's note.

The note may change how the text is READ. A fact it adds counts only once the user puts it in the
bullet, so it comes back as a guarded suggestion (a new text, a new hash, a fresh evaluation).
The reply is written here from the before/after comparison, never by the model. The dispute is
stored on `bullet_disputes`, never on `bullet_classifications`: the ordinary evaluation of the
text stays untouched, and `bullet_classify.classify_items` decides which one the report shows.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bullet_dispute import BulletDispute
from app.models.types import utcnow
from app.services import bullet_classify, health_guards, model_settings, resume_lint

logger = logging.getLogger(__name__)

# The words the report UI uses for each level.
LEVEL_WORDS = {
    "direct": "a strong result",
    "analogue": "a partial result",
    "adjacent": "specific, but with no result",
    "implied": "vague",
    "unaddressed": "a duty statement",
}
ADD_IT_YOURSELF = "Add it to the bullet in your own words."


class DisputeUnreadable(RuntimeError):
    """The model's answer failed validation. Nothing is stored; the user can send it again."""


def shown(result: dict) -> dict:
    """The level and the ask the report shows for an evaluation (fallback question included)."""
    level = result["level"]
    if level == "direct":
        return {"level": level, "question": None, "ask_kind": None}
    fields = resume_lint._question_fields(result)
    return {"level": level, "question": fields["question"], "ask_kind": fields["ask_kind"]}


def _reply(before: dict, after: dict, reason: str) -> str:
    rank = bullet_classify._LEVEL_RANK.index
    if rank(after["level"]) > rank(before["level"]):
        return f"Re-read: this now counts as {LEVEL_WORDS[after['level']]}."
    if rank(after["level"]) < rank(before["level"]):
        return (f"Re-read: on a closer look this reads as {LEVEL_WORDS[after['level']]}. "
                f"{after['question'] or ''}").strip()
    if before["ask_kind"] == "measure" and after["ask_kind"] == "detail":
        return f"Understood. No number needed: {after['question']}"
    if after["question"] != before["question"]:
        return f"Same rating, a better question: {after['question']}"
    return f"Still flagged: {reason.strip().rstrip('.') or 'the text reads the same'}."


def _suggest(db: Session, text: str, new_fact: str, question: str | None) -> str | None:
    try:
        return health_guards.guarded_rewrite(db, text, context=new_fact, question=question or "")
    except Exception:  # noqa: BLE001 — a failed draft degrades to "add it yourself"
        logger.exception("dispute suggestion failed")
        return None


def dispute(db: Session, text: str, note: str) -> dict:
    text, note = str(text).strip(), str(note).strip()
    if not text or not note:
        raise ValueError("A dispute needs a bullet and a note.")
    chash = bullet_classify.content_hash(text)
    hints = resume_lint._classify_hints(text)
    before = bullet_classify.classify_items(db, [{"text": text, "hints": hints}])[chash]
    # Uncached on purpose: the note must never reach the ordinary evaluation's cache row.
    after = bullet_classify._evaluate_batch(
        db, {chash: {"id": chash, "text": text, "note": note, "hints": hints}}).get(chash)
    if after is None:
        raise DisputeUnreadable("Couldn't re-read this bullet. Try again.")
    row = db.get(BulletDispute, chash)
    # A stored "no number exists" stays until the user reopens it, whatever this note says.
    if row is not None and row.metric_unavailable:
        after = bullet_classify._validate(text, after, metric_unavailable=True)

    before_shown, after_shown = shown(before), shown(after)
    reply = _reply(before_shown, after_shown, after["reason"])
    suggestion = None
    if after["new_fact"]:
        suggestion = _suggest(db, text, after["new_fact"], after_shown["question"])
        if suggestion is None:
            reply = f"{reply} {ADD_IT_YOURSELF}"

    if row is None:
        row = BulletDispute(content_hash=chash)
        db.add(row)
    row.metric_unavailable = bool(row.metric_unavailable) or after["metric_unavailable"]
    row.note, row.reply, row.suggestion = note, reply, suggestion
    row.original_json, row.revised_json = before, after
    row.rubric_version = bullet_classify.RUBRIC_VERSION
    row.model = model_settings.get_smart_model(db)
    row.created_at = utcnow()
    db.commit()
    return {"before": {"level": before_shown["level"], "question": before_shown["question"]},
            "after": after_shown, "reply": reply, "suggestion": suggestion,
            "content_hash": chash}


def for_resume(db: Session, resume: dict) -> list[dict]:
    """Disputes whose text is still in `resume`, one row per location of that text."""
    located = [(loc, text.strip(), bullet_classify.content_hash(text.strip()))
               for loc, text in resume_lint._ladder_items(resume)]
    rows = {d.content_hash: d for d in db.scalars(select(BulletDispute).where(
        BulletDispute.content_hash.in_({chash for _, _, chash in located})))}
    out = []
    for loc, text, chash in located:
        row = rows.get(chash)
        if row is None:
            continue
        before = shown(row.original_json)
        out.append({"content_hash": chash, "location": resume_lint._loc_dict(loc),
                    "label": resume_lint._label_at(resume, loc), "text": text,
                    "note": row.note, "reply": row.reply, "suggestion": row.suggestion,
                    "metric_unavailable": bool(row.metric_unavailable),
                    "before": {"level": before["level"], "question": before["question"]},
                    "after": shown(row.revised_json), "created_at": row.created_at})
    return out


def reopen(db: Session, chash: str) -> bool:
    """Drop the dispute, including a stored "no number exists". True when one existed."""
    row = db.get(BulletDispute, chash)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
