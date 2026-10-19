"""Read-only per-item groom: clusters of similar bullets, a proposed keeper, kept pairs."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.services import kb_groom
from tests.kb_vectors import _embedder_down, _vectors

A = "Cleansed and validated 2M rows nightly"
B = "Cleansed, standardized and validated 2M rows"
C = "Validated two million rows every night"
FAR = "Mentored two interns"

# A~B 0.85, B~C 0.85, A~C 0.445 (a chain: A and C meet only through B); FAR on its own axis, 0 to all.
# cos(A,B) = 0.85; cos(B,C) = 0.85*0.445 + 0.52678*0.8955 = 0.85; cos(A,C) = 0.445
VEC = {
    A: (1.0, 0.0, 0.0),
    B: (0.85, 0.52678, 0.0),
    C: (0.445, 0.8955, 0.0),
    FAR: (0.0, 0.0, 1.0),
}


def _item(db_session, *texts, states=None, provenances=None, updated=None):
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    points = []
    for text in texts:
        p = KBPoint(
            entity_id=ent.id, text=text, origin="manual",
            state=(states or {}).get(text, "approved"),
            provenance=(provenances or {}).get(text, "user_authored"),
        )
        db_session.add(p)
        db_session.flush()
        if updated and text in updated:
            p.updated_at = updated[text]
            db_session.flush()
        points.append(p)
    db_session.commit()
    return ent, {p.text: p for p in points}


def test_fixed_vectors_give_deterministic_clusters_and_single_link_joins_a_chain(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C, FAR)
    first = kb_groom.groom_entity(db_session, ent.id)
    second = kb_groom.groom_entity(db_session, ent.id)
    assert first == second
    assert first.compared_wording is True
    assert first.active_points == 4
    (cluster,) = first.clusters
    assert {m.id for m in cluster.members} == {by[A].id, by[B].id, by[C].id}
    assert cluster.score == pytest.approx(0.85, abs=0.01)
    assert len(cluster.pairs) == 2  # A-B and B-C; A-C is under the band
    assert cluster.members[0].id == cluster.keeper_id


def test_keeper_rule_in_each_tiebreak_order(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    now = datetime.now(UTC)
    # approved beats draft
    ent, by = _item(db_session, A, B, states={A: "draft", B: "approved"})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id
    # then most recently updated
    ent, by = _item(db_session, A, B, updated={A: now - timedelta(days=2), B: now - timedelta(days=1)})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id
    # then the longer text (same updated_at)
    same = now - timedelta(days=3)
    ent, by = _item(db_session, A, B, updated={A: same, B: same})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id  # B is longer
    # then the id (same state, same updated_at, same length: 38 characters each)
    twin = "Cleansed and validated 2M rows weekly."
    assert len(twin) == len(A)
    _vectors(monkeypatch, {**VEC, twin: (1.0, 0.0, 0.0)})
    ent, by = _item(db_session, A, twin, updated={A: same, twin: same})
    report = kb_groom.groom_entity(db_session, ent.id)
    assert report.clusters[0].keeper_id == min(p.id for p in by.values())


def test_kept_pairs_break_an_edge(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    lo, hi = kept_pair_key(by[A].id, by[B].id)
    db_session.add(KBPointKeptPair(point_a_id=lo, point_b_id=hi))
    db_session.commit()
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    assert {m.id for m in cluster.members} == {by[B].id, by[C].id}  # A fell out with its only edge


def test_drafts_included_retired_and_unconfirmable_excluded(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C, states={A: "draft", C: "retired"})
    report = kb_groom.groom_entity(db_session, ent.id)
    assert report.active_points == 2
    assert {m.id for m in report.clusters[0].members} == {by[A].id, by[B].id}
    ent, by = _item(db_session, A, B, provenances={A: "user_cannot_confirm"})
    assert kb_groom.groom_entity(db_session, ent.id).clusters == []


def test_one_point_item_and_no_similar_pairs_are_empty(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, _ = _item(db_session, A)
    report = kb_groom.groom_entity(db_session, ent.id)
    assert (report.active_points, report.clusters, report.compared_wording) == (1, [], True)
    ent, _ = _item(db_session, A, FAR)
    assert kb_groom.groom_entity(db_session, ent.id).clusters == []


def test_embedder_failure_sets_compared_wording_false(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    ent, _ = _item(db_session, A, B)
    report = kb_groom.groom_entity(db_session, ent.id)
    assert (report.compared_wording, report.clusters) == (False, [])


def test_member_rows_carry_usage_and_sort_keeper_first_then_by_score(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    db_session.add(KBPortLog(entity_id=ent.id, point_id=by[C].id, resume_kind="base",
                             resume_key="hybrid", section="projects", ported_text=C, direction="to_resume"))
    db_session.commit()
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    rows = {m.id: m for m in cluster.members}
    assert rows[by[C].id].usage_count == 1
    assert rows[by[A].id].usage_count == 0
    assert cluster.members[0].id == cluster.keeper_id
    assert cluster.members[0].best_score == pytest.approx(1.0)
    scores = [m.best_score for m in cluster.members[1:]]
    assert scores == sorted(scores, reverse=True)


def test_groom_never_calls_the_llm_and_writes_nothing(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("groom must not call the LLM")),
    )
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B)
    before = {(p.id, p.state, p.text, p.updated_at, p.merged_into_point_id) for p in by.values()}
    kb_groom.groom_entity(db_session, ent.id)
    db_session.expire_all()
    after = {(p.id, p.state, p.text, p.updated_at, p.merged_into_point_id) for p in db_session.query(KBPoint)}
    assert before == after
    assert db_session.query(KBPointKeptPair).count() == 0


def test_unknown_entity_raises_value_error(db_session):
    with pytest.raises(ValueError):
        kb_groom.groom_entity(db_session, uuid.uuid4())


# ---- routes ----

def test_groom_route_returns_the_report_and_404s(client, db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B)
    r = client.get(f"/api/kb/entities/{ent.id}/groom")
    assert r.status_code == 200, r.text
    assert r.json()["entity_title"] == "Orbit"
    assert r.json()["clusters"][0]["keeper_id"] in {str(by[A].id), str(by[B].id)}
    assert client.get(f"/api/kb/entities/{uuid.uuid4()}/groom").status_code == 404


def test_a_combined_cluster_is_gone_on_the_next_report(client, db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    losers = [str(m.id) for m in cluster.members if m.id != cluster.keeper_id]
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(cluster.keeper_id), "point_ids": losers}).status_code == 200
    report = kb_groom.groom_entity(db_session, ent.id)
    assert (report.active_points, report.clusters) == (1, [])


def test_keep_apart_records_every_pair_canonically_and_is_idempotent(client, db_session):
    _ent, by = _item(db_session, A, B, C)
    ids = [str(by[C].id), str(by[A].id), str(by[B].id)]
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    assert r.status_code == 200, r.text
    assert len(r.json()["pairs"]) == 3
    rows = db_session.query(KBPointKeptPair).all()
    assert len(rows) == 3
    assert all(row.point_a_id < row.point_b_id for row in rows)
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    assert r.status_code == 200
    assert db_session.query(KBPointKeptPair).count() == 3


def test_keep_apart_requires_one_item_and_known_points(client, db_session):
    _ent, by = _item(db_session, A)
    _other, by2 = _item(db_session, B)
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(by2[B].id)]}).status_code == 400
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(uuid.uuid4())]}).status_code == 404
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id)]}).status_code == 422


def test_keep_apart_delete_forgets_and_point_delete_cascades(client, db_session):
    _ent, by = _item(db_session, A, B, C)
    ids = [str(by[A].id), str(by[B].id), str(by[C].id)]
    client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    r = client.request("DELETE", "/api/kb/points/keep-apart", json={"point_ids": ids[:2]})
    assert r.status_code == 200
    assert db_session.query(KBPointKeptPair).count() == 2
    assert client.delete(f"/api/kb/points/{by[C].id}").status_code == 204
    assert db_session.query(KBPointKeptPair).count() == 0
