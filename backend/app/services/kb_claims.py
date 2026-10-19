"""The one decision behind every Career KB intake: does this text restate a claim
already on this item (in sync), rephrase one (a wording), or say something new?

Deterministic and LLM-free: an exact normalized match, else the pinned local
embedder (services/ats/embeddings) against the item's active claims. Base sync
calls it today; import, the document mint and the write-backs are follow-ups,
so "the same claim" comes to mean one thing everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career_kb import KBPoint, KBPortLog
from app.services.kb_consolidation import point_text_key

# A bullet whose best same-item match scores here or above is a WORDING of that
# claim, never a second bullet. Shared with services/kb_groom so "similar" means
# one thing. Owner decision 2026-10-17/19: not 0.75 (half the extra hits are
# distinct claims), not 0.85 (misses half the real rewrites).
SYNC_WORDING_COSINE = 0.80


@dataclass(frozen=True)
class Placement:
    kind: str  # "in_sync" | "wording" | "new"
    point: KBPoint | None
    score: float | None
    # False when the embedder raised: kind is then "new" with no point, and the
    # caller must say so instead of reading it as "nothing similar".
    compared: bool = True


def candidates(points: list[KBPoint]) -> list[KBPoint]:
    """Claims a text may match: active, and never user_cannot_confirm (retired
    anyway; this guards the invariant on its own). Provenance is read only to
    exclude, never to rank or write."""
    return [p for p in points if p.state != "retired" and p.provenance != "user_cannot_confirm"]


def place(text: str, points: list[KBPoint]) -> Placement:
    key = point_text_key(text)
    for point in points:
        if point_text_key(point.text) == key:
            return Placement("in_sync", point, None)
    if not points:
        return Placement("new", None, None)
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([text] + [p.text for p in points])
    except Exception:
        return Placement("new", None, None, compared=False)
    best_point: KBPoint | None = None
    best_score = -1.0
    for point, vector in zip(points, vectors[1:], strict=True):
        score = cosine(vectors[0], vector)
        if score > best_score:
            best_score, best_point = score, point
    if best_point is not None and best_score >= SYNC_WORDING_COSINE:
        return Placement("wording", best_point, round(best_score, 4))
    return Placement("new", None, None)


class CombineError(ValueError):
    """A combine the server refuses; the message is the user's sentence."""


def combine(db: Session, keeper: KBPoint, others: list[KBPoint]) -> None:
    """Retire `others` and point them at `keeper`. Only state, approved_at and
    merged_into_point_id move; text, provenance and the losers' own placement
    history stay where they are. Reversible with PATCH unmerge."""
    if keeper.state == "retired" or keeper.provenance == "user_cannot_confirm":
        raise CombineError("That bullet can't be the one to keep.")
    for other in others:
        if other.id == keeper.id:
            raise CombineError("A bullet can't be combined into itself.")
        if other.entity_id != keeper.entity_id:
            raise CombineError("These bullets are on different items.")
    for other in others:
        other.state = "retired"
        other.approved_at = None
        other.merged_into_point_id = keeper.id


def split_wording(db: Session, claim: KBPoint, text: str, resume_key: str | None) -> KBPoint:
    """A resume wording becomes its own approved claim on the same item, and the
    from_source rows that carried it follow the words. Raises LookupError when no
    row matches (the wording is not one the KB noted)."""
    key = point_text_key(text)
    stmt = select(KBPortLog).where(KBPortLog.point_id == claim.id, KBPortLog.direction == "from_source")
    if resume_key is not None:
        stmt = stmt.where(KBPortLog.resume_key == resume_key)
    rows = [r for r in db.scalars(stmt).all() if point_text_key(r.ported_text) == key]
    if not rows:
        raise LookupError("That wording isn't one your resumes noted.")
    new = KBPoint(
        entity_id=claim.entity_id,
        text=text,
        state="approved",
        approved_at=datetime.now(UTC),
        origin="base_sync",
        provenance="user_authored",  # the user's own resume sentence
    )
    db.add(new)
    db.flush()
    for row in rows:
        row.point_id = new.id
    return new
