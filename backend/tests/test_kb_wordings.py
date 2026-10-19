"""A claim's wordings: where else it was phrased, derived on read from four sources;
and the writes that move text between claim and wording (combine, unmerge, split)."""

import uuid

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
