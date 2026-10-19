"""Per-item groom: similar bullets on one Career KB item, read-only.

Zero LLM calls and zero writes. Embeds the item's active bullets once through
the pinned local embedder, joins pairs at kb_claims.SYNC_WORDING_COSINE and above
(minus the pairs the user marked "Not the same"), takes single-link components
as clusters and proposes a keeper. The user combines or retires through their
own endpoints; nothing here changes a row. Re-run safe by construction.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.schemas.career_kb import GroomCluster, GroomMember, GroomReport
from app.services.kb_claims import SYNC_WORDING_COSINE, candidates

logger = logging.getLogger(__name__)


def _usage_counts(db: Session, ids: list[UUID]) -> dict[UUID, int]:
    """Distinct resumes over every usage row, as the points list's "On N
    resumes" chip counts them."""
    if not ids:
        return {}
    rows = db.execute(
        select(KBPortLog.point_id, func.count(distinct(KBPortLog.resume_key)))
        .where(KBPortLog.point_id.in_(ids))
        .group_by(KBPortLog.point_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def _kept(db: Session, ids: list[UUID]) -> set[tuple[UUID, UUID]]:
    if not ids:
        return set()
    rows = db.scalars(
        select(KBPointKeptPair).where(
            KBPointKeptPair.point_a_id.in_(ids), KBPointKeptPair.point_b_id.in_(ids)
        )
    ).all()
    return {(r.point_a_id, r.point_b_id) for r in rows}


def _components(ids: list[UUID], edges: list[tuple[UUID, UUID, float]]) -> list[list[UUID]]:
    """Single link on purpose: a chain of rewrites (A→B→C) is one claim even
    when A and C fall under the band."""
    parent = {i: i for i in ids}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    groups: dict[UUID, list[UUID]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return [g for g in groups.values() if len(g) >= 2]


def _keeper(points: list[KBPoint]) -> KBPoint:
    """Approved over draft, then most recently updated, then longest text, then id.
    Stated in the dialog, so the proposal is explainable."""
    return min(
        points,
        key=lambda p: (p.state != "approved", -p.updated_at.timestamp(), -len(p.text), str(p.id)),
    )


def groom_entity(db: Session, entity_id: UUID) -> GroomReport:
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise LookupError("Entity not found")
    # Drafts in; retired and user_cannot_confirm out. A stable order, so the
    # report is the same on every read.
    points = candidates(sorted(entity.points, key=lambda p: (p.created_at, p.id)))
    base = dict(entity_id=entity.id, entity_title=entity.title, active_points=len(points))
    if len(points) < 2:
        return GroomReport(**base, compared_wording=True, clusters=[])
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([p.text for p in points])
    except Exception as exc:
        logger.warning("groom could not compare wording: %s", exc)
        return GroomReport(**base, compared_wording=False, clusters=[])

    by_id = {p.id: p for p in points}
    ids = [p.id for p in points]
    kept = _kept(db, ids)
    score: dict[tuple[UUID, UUID], float] = {}
    edges: list[tuple[UUID, UUID, float]] = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            s = cosine(vectors[i], vectors[j])
            key = kept_pair_key(ids[i], ids[j])
            score[key] = s
            if s >= SYNC_WORDING_COSINE and key not in kept:
                edges.append((key[0], key[1], round(s, 4)))

    usage = _usage_counts(db, ids)
    clusters: list[GroomCluster] = []
    for group in _components(ids, edges):
        group_set = set(group)
        members = [by_id[i] for i in group]
        keeper = _keeper(members)
        pairs = sorted(e for e in edges if e[0] in group_set and e[1] in group_set)
        to_keeper: dict[UUID, float] = {
            p.id: 1.0 if p.id == keeper.id else round(score[kept_pair_key(p.id, keeper.id)], 4)
            for p in members
        }
        ordered = sorted(members, key=lambda p: (p.id != keeper.id, -to_keeper[p.id], str(p.id)))
        clusters.append(
            GroomCluster(
                score=max(e[2] for e in pairs),
                keeper_id=keeper.id,
                members=[
                    GroomMember(
                        id=p.id, text=p.text, state=p.state, origin=p.origin,
                        provenance=p.provenance, usage_count=usage.get(p.id, 0),
                        best_score=to_keeper[p.id],
                    )
                    for p in ordered
                ],
                pairs=pairs,
            )
        )
    clusters.sort(key=lambda c: (-c.score, str(c.keeper_id)))
    return GroomReport(**base, compared_wording=True, clusters=clusters)
