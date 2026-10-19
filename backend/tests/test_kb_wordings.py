"""A claim's wordings: where else it was phrased, derived on read from four sources;
and the writes that move text between claim and wording (combine, unmerge, split)."""

import uuid

from sqlalchemy import select

from app.models.career_kb import KBPoint, KBPortLog


def _entity(client, title="Orbit"):
    return client.post("/api/kb/entities", json={"kind": "project", "title": title}).json()["id"]


def _point(db_session, entity_id, text, *, state="approved", provenance="user_authored",
           merged_into=None, merge_sources=None, origin="manual"):
    point = KBPoint(
        entity_id=uuid.UUID(entity_id), text=text, state=state, origin=origin,
        provenance=provenance, merged_into_point_id=merged_into, merge_sources_json=merge_sources,
    )
    db_session.add(point)
    db_session.commit()
    return point


def _log(db_session, point, *, resume_key, text, direction, source_text=None, section="projects"):
    db_session.add(KBPortLog(
        entity_id=point.entity_id, point_id=point.id, resume_kind="base", resume_key=resume_key,
        section=section, ported_text=text, source_text=source_text, direction=direction,
    ))
    db_session.commit()


def _wordings(client, point_id):
    rows = client.get("/api/kb/points?limit=500").json()
    return next(r for r in rows if r["id"] == str(point_id))["wordings"]


def test_wordings_come_from_all_four_sources_with_the_right_affordances(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching",
                   merge_sources=[{"resume_key": "imported", "section": "projects", "text": "Lowered latency 30% with a cache"}])
    _log(db_session, claim, resume_key="hybrid", text="Cut p95 latency 30% by caching hot keys", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="Cut latency 30% via caching (old copy)", direction="to_resume")
    folded = _point(db_session, eid, "Reduced latency by a third using Redis", state="retired", merged_into=claim.id)
    rows = _wordings(client, claim.id)
    assert [r["kind"] for r in rows] == ["resume", "placed", "merged", "import"]
    by_kind = {r["kind"]: r for r in rows}
    assert set(by_kind) == {"resume", "placed", "import", "merged"}
    assert by_kind["resume"] == {
        "kind": "resume", "text": "Cut p95 latency 30% by caching hot keys", "resume_keys": ["hybrid"],
        "section": "projects", "point_id": None, "adoptable": True, "splittable": True,
    }
    assert (by_kind["placed"]["adoptable"], by_kind["placed"]["splittable"]) == (False, False)
    assert (by_kind["import"]["adoptable"], by_kind["import"]["splittable"]) == (True, False)
    assert by_kind["merged"]["point_id"] == str(folded.id)
    assert (by_kind["merged"]["adoptable"], by_kind["merged"]["splittable"]) == (True, True)


def test_one_row_per_distinct_text_and_the_lines_own_text_is_never_a_wording(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching")
    _log(db_session, claim, resume_key="hybrid", text="Cut p95 latency 30%", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="cut p95   latency 30%", direction="from_source")
    _log(db_session, claim, resume_key="same", text="Cut latency 30% via caching", direction="from_source")
    _log(db_session, claim, resume_key="kept", text="Cut latency 30% via caching", direction="to_resume")
    rows = _wordings(client, claim.id)
    assert len(rows) == 1
    assert rows[0]["resume_keys"] == ["compact", "hybrid"]


def test_entity_detail_lists_the_merged_claim_under_its_keeper(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Keeper")
    folded = _point(db_session, eid, "Folded", state="retired", merged_into=keeper.id)
    detail = client.get(f"/api/kb/entities/{eid}").json()
    by_id = {p["id"]: p for p in detail["points"]}
    assert by_id[str(folded.id)]["merged_into_point_id"] == str(keeper.id)
    assert by_id[str(keeper.id)]["wordings"][0] == {
        "kind": "merged", "text": "Folded", "resume_keys": [], "section": None,
        "point_id": str(folded.id), "adoptable": True, "splittable": True,
    }
    assert by_id[str(keeper.id)]["merged_into_point_id"] is None


def test_an_adapted_placement_shows_the_old_line_it_was_adapted_from(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching hot keys")
    _log(db_session, claim, resume_key="compact", text="Cut latency 30% for Globex checkout",
         source_text="Cut latency 30% via caching", direction="to_resume")
    rows = _wordings(client, claim.id)
    assert [(r["kind"], r["text"], r["adoptable"], r["splittable"]) for r in rows] == [
        ("placed", "Cut latency 30% via caching", False, False),
    ]


def test_a_legacy_row_with_no_direction_reads_as_placed(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching")
    _log(db_session, claim, resume_key="hybrid", text="Cut latency by 30%", direction=None)
    rows = _wordings(client, claim.id)
    assert [(r["kind"], r["resume_keys"], r["adoptable"], r["splittable"]) for r in rows] == [
        ("placed", ["hybrid"], False, False),
    ]


def test_a_combined_claim_that_matches_a_resume_wording_can_still_be_split_out(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Keeper line")
    _log(db_session, keeper, resume_key="hybrid", text="same words", direction="from_source")
    folded = _point(db_session, eid, "Same  WORDS", state="retired", merged_into=keeper.id)
    rows = _wordings(client, keeper.id)
    assert len(rows) == 1
    row = rows[0]
    assert (row["kind"], row["point_id"], row["resume_keys"]) == ("merged", str(folded.id), ["hybrid"])
    assert row["text"] == "same words"
    assert (row["adoptable"], row["splittable"]) == (True, True)


def test_malformed_import_sources_are_skipped_or_read_as_blank_never_a_500(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching", merge_sources=[
        "not a dict",
        {"resume_key": "imported", "section": "projects"},
        {"text": "Lowered latency with a cache", "resume_key": 7, "section": ["projects"]},
    ])
    rows = _wordings(client, claim.id)
    assert rows == [{
        "kind": "import", "text": "Lowered latency with a cache", "resume_keys": [], "section": None,
        "point_id": None, "adoptable": True, "splittable": False,
    }]
    assert client.get(f"/api/kb/entities/{eid}").status_code == 200


def test_combine_retires_and_points_the_losers_and_leaves_the_keeper_alone(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Cleansed 2M rows nightly")
    a = _point(db_session, eid, "Cleansed and validated 2M rows", state="draft")
    b = _point(db_session, eid, "Validated 2M rows every night")
    _log(db_session, b, resume_key="hybrid", text=b.text, direction="to_resume")
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(a.id), str(b.id)]})
    assert r.status_code == 200, r.text
    assert r.json()["repointed"] == []
    body = r.json()["keeper"]
    assert body["id"] == str(keeper.id)
    assert body["text"] == "Cleansed 2M rows nightly"
    assert {w["point_id"] for w in body["wordings"]} == {str(a.id), str(b.id)}

    def assert_combined():
        for p in (a, b):
            db_session.refresh(p)
            assert (p.state, p.merged_into_point_id, p.approved_at) == ("retired", keeper.id, None)
            assert p.provenance == "user_authored"
        db_session.refresh(keeper)
        assert (keeper.state, keeper.provenance) == ("approved", "user_authored")

    assert_combined()
    # the loser's own placement history stays its own: nothing moved
    assert db_session.query(KBPortLog).filter_by(point_id=b.id).count() == 1
    # idempotent
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(a.id)]})
    assert r.status_code == 200
    assert r.json()["repointed"] == []
    assert {w["point_id"] for w in r.json()["keeper"]["wordings"]} == {str(a.id), str(b.id)}
    assert_combined()


def test_combine_refuses_mixed_items_a_retired_or_unconfirmable_keeper_and_unknown_ids(client, db_session):
    eid, other = _entity(client), _entity(client, "Elsewhere")
    keeper = _point(db_session, eid, "Keeper")
    mine = _point(db_session, eid, "Mine")
    theirs = _point(db_session, other, "Theirs")
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(theirs.id)]}).status_code == 400
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(uuid.uuid4())]}).status_code == 404
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(keeper.id)]}).status_code == 400
    keeper.state = "retired"
    db_session.commit()
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(mine.id)]}).status_code == 400
    ucc = _point(db_session, eid, "Cannot confirm", provenance="user_cannot_confirm")
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(ucc.id), "point_ids": [str(mine.id)]}).status_code == 400
    # an unconfirmed sentence is refused as a loser too: it never becomes a wording
    active = _point(db_session, eid, "Active keeper")
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(active.id), "point_ids": [str(ucc.id)]})
    assert r.status_code == 400
    db_session.refresh(ucc)
    assert (ucc.state, ucc.merged_into_point_id) == ("approved", None)
    # a keeper that still carries a pointer is refused
    folded = _point(db_session, eid, "Folded but active", merged_into=active.id)
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(folded.id), "point_ids": [str(mine.id)]}).status_code == 400


def test_unmerge_patch_clears_the_pointer_and_sets_the_state_given(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Keeper")
    folded = _point(db_session, eid, "Folded", state="retired", merged_into=keeper.id)
    r = client.patch(f"/api/kb/points/{folded.id}", json={"state": "draft", "unmerge": True})
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["merged_into_point_id"]) == ("draft", None)
    assert _wordings(client, keeper.id) == []
    # unmerge alone, no state: the pointer clears, the state stays
    folded2 = _point(db_session, eid, "Folded again", state="retired", merged_into=keeper.id)
    r = client.patch(f"/api/kb/points/{folded2.id}", json={"unmerge": True})
    assert (r.json()["state"], r.json()["merged_into_point_id"]) == ("retired", None)


def test_split_wording_makes_an_approved_claim_and_moves_the_rows(client, db_session):
    from tests.kb_vectors import OLD, REWRITE

    eid = _entity(client)
    claim = _point(db_session, eid, OLD, origin="base_sync")
    _log(db_session, claim, resume_key="hybrid", text=REWRITE, direction="from_source", source_text=REWRITE, section="experience")
    _log(db_session, claim, resume_key="compact", text=REWRITE, direction="from_source", source_text=REWRITE, section="experience")
    r = client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": REWRITE, "resume_key": None})
    assert r.status_code == 200, r.text
    new = r.json()
    assert (new["text"], new["state"], new["origin"], new["provenance"]) == (REWRITE, "approved", "base_sync", "user_authored")
    assert new["entity_id"] == eid
    moved = db_session.scalars(select(KBPortLog).where(KBPortLog.point_id == uuid.UUID(new["id"]))).all()
    assert sorted(row.resume_key for row in moved) == ["compact", "hybrid"]
    assert _wordings(client, claim.id) == []
    assert db_session.get(KBPoint, uuid.UUID(new["id"])).merged_into_point_id is None


def test_after_a_split_the_resume_bullet_reads_in_sync(client, db_session, tmp_path, monkeypatch):
    """Before the split the band places the bullet as a wording; after it, the
    exact-match rung finds the new claim first, so no embedding is needed."""
    from app.services import kb_base_sync
    from tests.kb_vectors import BAND, OLD, REWRITE, _vectors
    from tests.test_kb_base_sync_classify import _exp_entity, _one_bullet, _seed_base

    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    claim = ent.points[0]
    _log(db_session, claim, resume_key="hybrid", text=REWRITE, direction="from_source",
         source_text=REWRITE, section="experience")
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    assert kb_base_sync.classify(db_session, "hybrid")["counts"]["recorded_drift"] == 1
    assert client.post(f"/api/kb/points/{claim.id}/split-wording",
                       json={"text": REWRITE, "resume_key": None}).status_code == 200
    counts = kb_base_sync.classify(db_session, "hybrid")["counts"]
    assert (counts["in_sync"], counts["recorded_drift"], counts["new"]) == (1, 0, 0)


def test_split_wording_with_a_resume_key_moves_only_that_resumes_rows(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Line")
    _log(db_session, claim, resume_key="hybrid", text="Other words", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="Other words", direction="from_source")
    r = client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": "Other words", "resume_key": "hybrid"})
    assert r.status_code == 200
    (left,) = _wordings(client, claim.id)
    assert left["resume_keys"] == ["compact"]
    assert client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": "Never noted", "resume_key": None}).status_code == 404


def test_adoption_keeps_the_state_and_clears_the_row(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Line")
    _log(db_session, claim, resume_key="hybrid", text="Better line", direction="from_source")
    r = client.patch(f"/api/kb/points/{claim.id}", json={"text": "Better line"})
    assert (r.json()["state"], r.json()["text"], r.json()["wordings"]) == ("approved", "Better line", [])


def test_moving_a_keeper_moves_its_combined_claims(client, db_session):
    eid, other = _entity(client), _entity(client, "Elsewhere")
    keeper = _point(db_session, eid, "Keeper line")
    folded = _point(db_session, eid, "Folded line")
    assert client.post("/api/kb/points/combine",
                       json={"keeper_id": str(keeper.id), "point_ids": [str(folded.id)]}).status_code == 200
    r = client.patch(f"/api/kb/points/{keeper.id}", json={"entity_id": other})
    assert r.status_code == 200, r.text
    db_session.refresh(folded)
    assert (folded.entity_id, folded.merged_into_point_id) == (uuid.UUID(other), keeper.id)
    detail = client.get(f"/api/kb/entities/{other}").json()
    by_id = {p["id"]: p for p in detail["points"]}
    assert [(w["kind"], w["point_id"]) for w in by_id[str(keeper.id)]["wordings"]] == [("merged", str(folded.id))]
    assert client.get(f"/api/kb/entities/{eid}").json()["points"] == []


def test_combine_flattens_a_losers_own_combined_claims_onto_the_keeper(client, db_session):
    eid = _entity(client)
    k1 = _point(db_session, eid, "First keeper")
    a = _point(db_session, eid, "Folded A")
    b = _point(db_session, eid, "Folded B")
    k2 = _point(db_session, eid, "Second keeper")
    assert client.post("/api/kb/points/combine",
                       json={"keeper_id": str(k1.id), "point_ids": [str(a.id), str(b.id)]}).status_code == 200
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(k2.id), "point_ids": [str(k1.id)]})
    assert r.status_code == 200, r.text
    for p in (a, b, k1):
        db_session.refresh(p)
        assert (p.state, p.merged_into_point_id) == ("retired", k2.id)
    assert {w["point_id"] for w in r.json()["keeper"]["wordings"]} == {str(a.id), str(b.id), str(k1.id)}
    assert {(m["point_id"], m["from_id"]) for m in r.json()["repointed"]} == {
        (str(a.id), str(k1.id)), (str(b.id), str(k1.id)),
    }
    # unmerging the old keeper does not drag its former children with it
    r = client.patch(f"/api/kb/points/{k1.id}", json={"state": "approved", "unmerge": True})
    assert r.status_code == 200, r.text
    for p in (a, b):
        db_session.refresh(p)
        assert p.merged_into_point_id == k2.id
    assert {w["point_id"] for w in _wordings(client, k2.id)} == {str(a.id), str(b.id)}


def test_undo_of_a_flattening_combine_restores_the_original_shape(client, db_session):
    eid = _entity(client)
    k1 = _point(db_session, eid, "First keeper")
    a = _point(db_session, eid, "Folded A")
    b = _point(db_session, eid, "Folded B")
    k2 = _point(db_session, eid, "Second keeper")
    client.post("/api/kb/points/combine", json={"keeper_id": str(k1.id), "point_ids": [str(a.id), str(b.id)]})
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(k2.id), "point_ids": [str(k1.id)]})
    repointed = r.json()["repointed"]
    # the web's Undo: restore each loser, then combine its children back onto it
    assert client.patch(f"/api/kb/points/{k1.id}", json={"state": "approved", "unmerge": True}).status_code == 200
    from_ids = {m["from_id"] for m in repointed}
    for from_id in from_ids:
        back = [m["point_id"] for m in repointed if m["from_id"] == from_id]
        r = client.post("/api/kb/points/combine", json={"keeper_id": from_id, "point_ids": back})
        assert r.status_code == 200, r.text
    for p in (a, b):
        db_session.refresh(p)
        assert (p.state, p.merged_into_point_id) == ("retired", k1.id)
    db_session.refresh(k1)
    assert (k1.state, k1.merged_into_point_id) == ("approved", None)
    assert {w["point_id"] for w in _wordings(client, k1.id)} == {str(a.id), str(b.id)}
    assert _wordings(client, k2.id) == []


def test_use_again_clears_the_pointer_so_a_reverse_combine_makes_no_cycle(client, db_session):
    eid = _entity(client)
    left = _point(db_session, eid, "Left line")
    k = _point(db_session, eid, "K line")
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(left.id), "point_ids": [str(k.id)]}).status_code == 200
    assert client.post("/api/kb/points/bulk-state", json={"ids": [str(k.id)], "state": "approved"}).status_code == 200
    db_session.refresh(k)
    assert (k.state, k.merged_into_point_id) == ("approved", None)
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(k.id), "point_ids": [str(left.id)]})
    assert r.status_code == 200, r.text
    db_session.refresh(left)
    db_session.refresh(k)
    assert (left.merged_into_point_id, k.merged_into_point_id) == (k.id, None)


def test_split_wording_refuses_the_claims_own_line(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30%")
    _log(db_session, claim, resume_key="hybrid", text="cut  latency 30%", direction="from_source")
    r = client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": "Cut latency 30%", "resume_key": None})
    assert r.status_code == 400
    assert r.json()["detail"] == "That is already this bullet's wording."
    assert db_session.query(KBPoint).filter_by(entity_id=claim.entity_id).count() == 1


def test_moving_a_combined_claim_alone_makes_it_an_ordinary_retired_bullet(client, db_session):
    eid, other = _entity(client), _entity(client, "Elsewhere")
    keeper = _point(db_session, eid, "Keeper line")
    folded = _point(db_session, eid, "Folded line")
    client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(folded.id)]})
    r = client.patch(f"/api/kb/points/{folded.id}", json={"entity_id": other})
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["merged_into_point_id"], r.json()["entity_id"]) == ("retired", None, other)
    assert _wordings(client, keeper.id) == []
