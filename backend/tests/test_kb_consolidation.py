import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.services.career_kb import get_or_create_profile
from app.services.kb_consolidation import (
    collect_entries, consolidate, group_by_identity, parse_resume_text,
)


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _resume(**sections):
    base = {"contact": {"name":"A","email":"a@x.com"}, "summary": None, "skills": [],
            "experience": [], "projects": [], "education": [], "certifications": []}
    base.update(sections)
    return base


def _make_llm(entity_payload=None, cluster_payload=None):
    """Dispatch fake: entity-resolve contract carries `group_indices`, cluster
    contract carries `bullet_indices`. Returns empty clusters when unspecified."""
    def fake(*, prompt, model, response_format="json", **kw):
        if "group_indices" in prompt:
            return entity_payload if entity_payload is not None else {"clusters": []}
        if "bullet_indices" in prompt:
            return cluster_payload if cluster_payload is not None else {"clusters": []}
        raise AssertionError("unexpected prompt")
    return fake


def _entity_cluster(group_indices, title, existing_entity_id=None):
    return {"group_indices": group_indices, "existing_entity_id": existing_entity_id,
            "canonical": {"kind": "project", "title": title, "org": None,
                          "start_date": None, "end_date": None}}

def test_collect_flattens_all_sections_tagged():
    r1 = _resume(experience=[{"company":"Fictional Employer Legacy","role":"Analyst","start_date":"2022","bullets":["a"]}],
                 projects=[{"name":"Orbit","bullets":["p"]}],
                 certifications=["AWS SAA"])
    entries = collect_entries([("ds", r1)])
    assert {(e.section, e.index) for e in entries} == {("experience",0),("projects",0),("certifications",0)}
    assert all(e.resume_key == "ds" for e in entries)

def test_same_project_across_three_sources_one_group():
    def r():
        return _resume(projects=[{"name": "Maestro CS", "bullets": ["x"]}])
    groups = group_by_identity(collect_entries([("a",r()),("b",r()),("c",r())]))
    proj_groups = [g for g in groups if g.section=="projects"]
    assert len(proj_groups) == 1 and len(proj_groups[0].members) == 3

def test_grouping_is_case_and_space_insensitive():
    a = _resume(projects=[{"name":"Data  Scientist","bullets":[]}])
    b = _resume(projects=[{"name":"data scientist","bullets":[]}])
    groups = [g for g in group_by_identity(collect_entries([("a",a),("b",b)])) if g.section=="projects"]
    assert len(groups) == 1 and len(groups[0].members) == 2

def test_same_company_different_role_separate_groups():
    a = _resume(experience=[{"company":"Fictional Employer Legacy","role":"Analyst","start_date":"2022","bullets":[]}])
    b = _resume(experience=[{"company":"Fictional Employer Legacy","role":"Engineer","start_date":"2022","bullets":[]}])
    groups = [g for g in group_by_identity(collect_entries([("a",a),("b",b)])) if g.section=="experience"]
    assert len(groups) == 2

def test_same_company_role_different_start_date_separate():
    a = _resume(experience=[{"company":"Fictional Employer Legacy","role":"Analyst","start_date":"2020","bullets":[]}])
    b = _resume(experience=[{"company":"Fictional Employer Legacy","role":"Analyst","start_date":"2022","bullets":[]}])
    groups = [g for g in group_by_identity(collect_entries([("a",a),("b",b)])) if g.section=="experience"]
    assert len(groups) == 2

def test_cert_strings_dedupe_across_sources():
    a = _resume(certifications=["AWS SAA"])
    b = _resume(certifications=["aws saa"])
    groups = [g for g in group_by_identity(collect_entries([("a",a),("b",b)])) if g.section=="certifications"]
    assert len(groups) == 1 and len(groups[0].members) == 2

def test_missing_or_nonlist_sections_skipped():
    weird = {"experience": None, "projects": [{"name":"X","bullets":[]}]}
    entries = collect_entries([("a", weird)])
    assert [e.section for e in entries] == ["projects"]

def test_sections_do_not_cross_group():
    # a project and an education row that both normalize to "x" must not merge
    a = _resume(projects=[{"name":"X","bullets":[]}], education=[{"institution":"X","degree":"X"}])
    groups = group_by_identity(collect_entries([("a",a)]))
    assert len(groups) == 2 and {g.section for g in groups} == {"projects","education"}


# --- consolidate() : LLM stages + DB write ---------------------------------


def test_consolidate_exact_dupes_collapse_one_approved_point(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
            ]},
        ),
    )
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    report = consolidate(db_session, [("a", r1), ("b", r2)])

    ents = db_session.scalars(select(KBEntity)).all()
    assert len(ents) == 1 and ents[0].kind == "project"
    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1
    assert pts[0].state == "approved" and pts[0].origin == "consolidated"
    logs = db_session.scalars(select(KBPortLog)).all()
    assert len(logs) == 2  # one per source bullet, both -> the shared point
    assert {log.point_id for log in logs} == {pts[0].id}
    assert report.duplicates_skipped == 1
    assert report.points_approved == 1
    assert report.entities_created == 1


def test_consolidate_paraphrase_cluster_makes_draft_with_merge_sources(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0, 1], "existing_point_id": None,
                 "merged_text": "Improved retrieval recall"}
            ]},
        ),
    )
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Increased recall by 30%"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["Boosted recall substantially"]}])
    report = consolidate(db_session, [("a", r1), ("b", r2)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1
    pt = pts[0]
    assert pt.state == "draft" and pt.origin == "consolidated"
    assert pt.text == "Improved retrieval recall"
    phrasings = {m["text"] for m in pt.merge_sources_json}
    assert phrasings == {"Increased recall by 30%", "Boosted recall substantially"}
    logs = db_session.scalars(select(KBPortLog)).all()
    assert len(logs) == 2 and {log.point_id for log in logs} == {pt.id}
    assert report.points_draft == 1
    assert report.duplicates_skipped == 0


def test_consolidate_singletons_stay_verbatim_approved(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": None, "merged_text": None},
                {"bullet_indices": [1], "existing_point_id": None, "merged_text": None},
            ]},
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Bullet alpha", "Bullet beta"]}])
    report = consolidate(db_session, [("a", r)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 2
    assert all(p.state == "approved" for p in pts)
    assert {p.text for p in pts} == {"Bullet alpha", "Bullet beta"}
    assert report.points_approved == 2


def test_consolidate_under_merge_two_entities(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [
                _entity_cluster([0], "Alpha"),
                _entity_cluster([1], "Beta"),
            ]},
        ),
    )
    r = _resume(projects=[{"name": "Alpha", "bullets": []}, {"name": "Beta", "bullets": []}])
    report = consolidate(db_session, [("a", r)])

    ents = db_session.scalars(select(KBEntity)).all()
    assert len(ents) == 2
    assert {e.title for e in ents} == {"Alpha", "Beta"}
    assert report.entities_created == 2


def test_consolidate_matches_existing_entity_and_point(db_session, monkeypatch):
    ent = KBEntity(kind="project", title="Orbit", status="completed", detail_json={})
    db_session.add(ent)
    db_session.flush()
    pt = KBPoint(entity_id=ent.id, text="T", state="approved", origin="manual",
                 approved_at=datetime.now(UTC))
    db_session.add(pt)
    db_session.flush()
    eid, pid = str(ent.id), str(pt.id)

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit", existing_entity_id=eid)]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": pid, "merged_text": None}
            ]},
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["T"]}])
    report = consolidate(db_session, [("a", r)])

    ents = db_session.scalars(select(KBEntity)).all()
    assert len(ents) == 1  # no new entity
    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1 and pts[0].text == "T"  # existing point unchanged
    logs = db_session.scalars(select(KBPortLog)).all()
    assert len(logs) == 1 and logs[0].point_id == pt.id
    assert report.entities_matched == 1 and report.entities_created == 0
    assert report.points_approved == 0 and report.points_draft == 0


def test_consolidate_skills_union_and_profile(db_session, monkeypatch):
    monkeypatch.setattr("app.services.llm.call_openai", _make_llm())
    r1 = _resume(skills=[{"category": "ML Ops", "items": ["Docker"]}])
    r2 = _resume(
        skills=[{"category": "MLOps", "items": ["MLflow", "Docker"]}],
        summary="Latest summary",
    )
    report = consolidate(db_session, [("first", r1), ("latest", r2)])

    profile = get_or_create_profile(db_session)
    cats = {g["category"] for g in profile.skills_json}
    assert cats == {"ML Ops", "MLOps"}  # norm differently -> stay separate
    mlops = next(g for g in profile.skills_json if g["category"] == "MLOps")
    assert sorted(x.lower() for x in mlops["items"]) == ["docker", "mlflow"]
    assert set(report.skills_merged) == {"ML Ops", "MLOps"}
    # profile seeded from the LAST source
    assert profile.contact_json.get("name") == "A"
    assert profile.summary == "Latest summary"


def test_consolidate_education_and_certs_collapse_by_identity(db_session, monkeypatch):
    def _no_llm(*a, **k):
        raise AssertionError("LLM must not be called for education/certs without bullets")

    monkeypatch.setattr("app.services.llm.call_openai", _no_llm)
    r1 = _resume(education=[{"institution": "MIT", "degree": "BS CS"}], certifications=["AWS SAA"])
    r2 = _resume(education=[{"institution": "mit", "degree": "bs cs"}], certifications=["aws saa"])
    report = consolidate(db_session, [("a", r1), ("b", r2)])

    ents = db_session.scalars(select(KBEntity)).all()
    edu = [e for e in ents if e.kind == "education"]
    certs = [e for e in ents if e.kind == "certification"]
    assert len(edu) == 1
    assert len(certs) == 1
    assert report.entities_created == 2


def test_consolidate_llm_unusable_falls_back_no_bullet_lost(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={},  # unusable: no clusters
        ),
    )
    r = _resume(projects=[{"name": "Orbit", "bullets": ["B1", "B2"]}])
    report = consolidate(db_session, [("a", r)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 2  # no bullet lost
    assert all(p.state == "approved" for p in pts)
    assert {p.text for p in pts} == {"B1", "B2"}
    assert report.points_approved == 2
    assert report.warnings  # a warning was recorded


def test_consolidate_extends_persisted_skill_category(db_session, monkeypatch):
    # Regression: extending an ALREADY-PERSISTED skill category must UPDATE the DB.
    # A shallow copy shares the nested category dict with the committed snapshot,
    # so in-place mutation leaves has_changes() False -> merged items lost.
    monkeypatch.setattr("app.services.llm.call_openai", _make_llm())
    prof = get_or_create_profile(db_session)
    prof.skills_json = [{"category": "Cloud", "items": ["AWS"]}]
    db_session.commit()

    r = _resume(skills=[{"category": "Cloud", "items": ["GCP"]}])
    report = consolidate(db_session, [("a", r)])

    db_session.expire_all()
    prof2 = get_or_create_profile(db_session)
    cloud = [g for g in prof2.skills_json if g["category"] == "Cloud"][0]
    assert set(cloud["items"]) == {"AWS", "GCP"}  # new item actually persisted
    assert "Cloud" in report.skills_merged


def test_consolidate_idempotent_rerun(db_session, monkeypatch):
    # Re-running with IDENTICAL sources matches the existing entity/point and must
    # NOT accumulate duplicate entities, points, or port-log rows.
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built the pipeline"]}])
    sources = [("a", r)]
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
            ]},
        ),
    )
    consolidate(db_session, sources)
    ent = db_session.scalars(select(KBEntity)).one()
    pt = db_session.scalars(select(KBPoint)).one()
    n_ent = len(db_session.scalars(select(KBEntity)).all())
    n_pt = len(db_session.scalars(select(KBPoint)).all())
    n_log = len(db_session.scalars(select(KBPortLog)).all())

    # 2nd run: the fakes now resolve to the rows created on run 1.
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [
                _entity_cluster([0], "Orbit", existing_entity_id=str(ent.id))
            ]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": str(pt.id), "merged_text": None}
            ]},
        ),
    )
    consolidate(db_session, sources)

    assert len(db_session.scalars(select(KBEntity)).all()) == n_ent
    assert len(db_session.scalars(select(KBPoint)).all()) == n_pt
    assert len(db_session.scalars(select(KBPortLog)).all()) == n_log


# --- POST /api/kb/consolidate endpoint + parse_resume_text -----------------


_VALID_RESUME_DICT = {
    "contact": {"name": "A", "email": "a@x.com"}, "summary": None, "skills": [],
    "experience": [], "projects": [{"name": "P", "bullets": ["did x"]}],
    "education": [], "certifications": [],
}


def _file_llm(resume_dict, entity_payload=None, cluster_payload=None):
    """Dispatch fake spanning all three consolidate-endpoint prompts: the
    kb_resume_parse prompt (unique token "ResumeData") returns a ResumeData
    dict; entity-resolve ("group_indices") and cluster ("bullet_indices")
    return their consolidate payloads."""
    def fake(*, prompt, model, response_format="json", **kw):
        if "group_indices" in prompt:
            return entity_payload if entity_payload is not None else {"clusters": []}
        if "bullet_indices" in prompt:
            return cluster_payload if cluster_payload is not None else {"clusters": []}
        if "ResumeData" in prompt:
            return resume_dict
        raise AssertionError("unexpected prompt")
    return fake


def test_consolidate_endpoint_from_slugs(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _make_llm(
            entity_payload={"clusters": [_entity_cluster([0], "Orbit")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
            ]},
        ),
    )
    a = _resume(projects=[{"name": "Orbit", "bullets": ["Built the pipeline"]}])
    b = _resume(projects=[{"name": "Orbit", "bullets": ["Built the pipeline"]}])
    db_session.add(BaseResume(slug="a", data_json=a))
    db_session.add(BaseResume(slug="b", data_json=b))
    db_session.commit()

    r = client.post("/api/kb/consolidate", data={"slugs": json.dumps(["a", "b"])})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["entities_created"] >= 1
    ents = db_session.scalars(select(KBEntity)).all()
    assert len(ents) == 1 and ents[0].kind == "project"


def test_consolidate_endpoint_unknown_slug_404(client, db_session):
    r = client.post("/api/kb/consolidate", data={"slugs": json.dumps(["does_not_exist"])})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "raw_slugs",
    [
        json.dumps({"slug": "a"}),
        json.dumps(["a", 1]),
        json.dumps(["a", ""]),
        "not-json",
    ],
)
def test_consolidate_endpoint_rejects_malformed_slug_payload(client, raw_slugs):
    r = client.post("/api/kb/consolidate", data={"slugs": raw_slugs})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "slugs must be a JSON array of non-empty strings"


def test_consolidate_endpoint_soft_deleted_slug_404(client, db_session):
    # active_base_resume_slugs excludes soft-deleted rows -> not an allowed source.
    db_session.add(
        BaseResume(slug="retired", data_json=_resume(), deleted_at=datetime.now(UTC))
    )
    db_session.commit()
    r = client.post("/api/kb/consolidate", data={"slugs": json.dumps(["retired"])})
    assert r.status_code == 404


def test_consolidate_endpoint_from_file(client, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _file_llm(
            _VALID_RESUME_DICT,
            entity_payload={"clusters": [_entity_cluster([0], "P")]},
            cluster_payload={"clusters": [
                {"bullet_indices": [0], "existing_point_id": None, "merged_text": None}
            ]},
        ),
    )
    r = client.post(
        "/api/kb/consolidate",
        files={"files": ("r.md", b"# Resume\nProject P: did x", "text/markdown")},
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["entities_created"] >= 1
    ents = db_session.scalars(select(KBEntity)).all()
    assert [e.title for e in ents] == ["P"]


def test_consolidate_endpoint_surfaces_salvage_warnings(client, monkeypatch):
    """The router prefixes per-file salvage warnings with the filename and
    extends report.warnings — deleting that plumbing must go red here."""
    with_bad_entry = {
        **_VALID_RESUME_DICT,
        "experience": [{"company": "Bad Co"}],  # missing role -> salvage drops it
    }
    monkeypatch.setattr(
        "app.services.llm.call_openai", _file_llm(with_bad_entry)
    )
    r = client.post(
        "/api/kb/consolidate",
        files={"files": ("r.md", b"# Resume\nBad Co entry", "text/markdown")},
    )
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert any(
        w.startswith("r.md: ") and "experience" in w for w in warnings
    ), warnings


def test_consolidate_endpoint_unparseable_file_422(client, monkeypatch):
    def fake(*, prompt, model, response_format="json", **kw):
        if "ResumeData" in prompt:
            return {"summary": "no contact here"}  # missing required contact -> invalid
        raise AssertionError("unexpected prompt")

    monkeypatch.setattr("app.services.llm.call_openai", fake)
    r = client.post(
        "/api/kb/consolidate",
        files={"files": ("r.md", b"some resume text", "text/markdown")},
    )
    assert r.status_code == 422, r.text


def test_consolidate_endpoint_corrupt_supported_file_400(client):
    r = client.post(
        "/api/kb/consolidate",
        files={"files": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert r.status_code == 400, r.text
    assert "broken.pdf" in r.json()["detail"]


def test_consolidate_endpoint_llm_outage_is_502_not_422(client, monkeypatch):
    # A valid file uploaded during a provider outage must surface as retryable
    # 502, not 422 (which would tell the client its file is bad).
    def fake(*, prompt, model, response_format="json", **kw):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.llm.call_openai", fake)
    r = client.post(
        "/api/kb/consolidate",
        files={"files": ("r.md", b"# Resume\nreal content", "text/markdown")},
    )
    assert r.status_code == 502, r.text
    assert "r.md" in r.json()["detail"]


def test_consolidate_endpoint_empty_request_400(client):
    r = client.post("/api/kb/consolidate")
    assert r.status_code == 400


def test_parse_resume_text_valid(db_session, monkeypatch):
    monkeypatch.setattr("app.services.llm.call_openai", lambda **kw: dict(_VALID_RESUME_DICT))
    out, warnings = parse_resume_text(db_session, "raw resume text")
    assert out["contact"]["name"] == "A"
    assert out["projects"][0]["name"] == "P"
    assert warnings == []


def test_parse_resume_text_invalid_raises(db_session, monkeypatch):
    monkeypatch.setattr("app.services.llm.call_openai", lambda **kw: {"garbage": 1})
    with pytest.raises(ValueError):
        parse_resume_text(db_session, "text")


def test_parse_resume_text_llm_failure_raises_runtime_error(db_session, monkeypatch):
    # A transient provider outage is NOT a bad file: parse_resume_text raises
    # RuntimeError (router -> 502), reserving ValueError (-> 422) for invalid data.
    def fail(**kw):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.llm.call_openai", fail)
    with pytest.raises(RuntimeError, match="resume parse LLM call failed"):
        parse_resume_text(db_session, "text")
    # And it is NOT a ValueError (which the router would map to a misleading 422).
    with pytest.raises(RuntimeError):
        parse_resume_text(db_session, "text")
