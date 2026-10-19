"""The one decision behind every Career KB intake: does this text restate a claim
already on this item (in sync), rephrase one (a wording), or say something new?

Deterministic and LLM-free: an exact normalized match, else the pinned local
embedder (services/ats/embeddings) against the item's active claims. Base sync
calls it today; import, the document mint and the write-backs are follow-ups,
so "the same claim" comes to mean one thing everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.career_kb import KBPoint
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
