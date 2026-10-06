"""Anchors on a base resume: countries, company and focus.

Metadata on the identity PATCH, like the role pair: setting them must never
touch the document, its versions or its rendered artifacts, and the role
pair must never touch them.
"""

from datetime import datetime, timezone

import pytest

from app.main import app
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.tailoring_session import TailoringSession
from app.schemas.tailoring_session import TailoringSessionRead
from app.services import base_resume_data

from tests.test_base_resume_role_category import SAMPLE, _client


@pytest.fixture
def client(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(BaseResume, slug),
    )
    return _client(db_session)


def teardown_function():
    app.dependency_overrides.clear()


def _add(db_session, slug="anchored", **kw) -> BaseResume:
    row = BaseResume(slug=slug, data_json=SAMPLE, **kw)
    db_session.add(row)
    db_session.commit()
    return row


def _identity(client, slug, body):
    return client.patch(f"/api/base-resumes/{slug}/identity", json=body)


def test_identity_sets_normalizes_and_clears_anchors(client, db_session):
    _add(db_session)

    body = _identity(
        client,
        "anchored",
        {"countries": ["in", "IN", "us"], "company": "  Infosys ", "focus": "payments"},
    ).json()
    assert body["countries"] == ["IN", "US"]
    assert body["company"] == "Infosys"
    assert body["focus"] == "payments"

    # Omitted means unchanged; an empty string clears a text anchor.
    body = _identity(client, "anchored", {"company": ""}).json()
    assert body["company"] is None
    assert body["countries"] == ["IN", "US"]
    assert body["focus"] == "payments"

    # Both an empty list and an explicit null store [] (the column is NOT NULL).
    assert _identity(client, "anchored", {"countries": []}).json()["countries"] == []
    _identity(client, "anchored", {"countries": ["GB"]})
    assert _identity(client, "anchored", {"countries": None}).json()["countries"] == []
    db_session.expire_all()
    assert db_session.get(BaseResume, "anchored").countries == []


def test_identity_accepts_names_and_uk(client, db_session):
    _add(db_session)
    body = _identity(client, "anchored", {"countries": ["UK", "india", "United States"]}).json()
    assert body["countries"] == ["GB", "IN", "US"]


def test_identity_rejects_bad_anchor_values(client, db_session):
    _add(db_session, company="Keep", focus="Keep", countries=["IN"])

    res = _identity(client, "anchored", {"countries": ["XX"]})
    assert res.status_code == 422
    assert res.json()["detail"] == "Unknown country code: XX."

    res = _identity(client, "anchored", {"company": "Fine", "focus": "x" * 81})
    assert res.status_code == 422
    assert res.json()["detail"] == "Keep the focus to 80 characters or fewer."

    res = _identity(client, "anchored", {"company": "c" * 81})
    assert res.status_code == 422
    assert res.json()["detail"] == "Keep the company to 80 characters or fewer."

    # Validate before mutating: a valid sibling in the same body is not saved.
    db_session.expire_all()
    row = db_session.get(BaseResume, "anchored")
    assert (row.company, row.focus, row.countries) == ("Keep", "Keep", ["IN"])


def test_identity_length_limit_is_after_strip(client, db_session):
    _add(db_session)
    body = _identity(client, "anchored", {"focus": "  " + "x" * 80 + "  "}).json()
    assert body["focus"] == "x" * 80


def test_anchor_patch_leaves_role_and_document_alone(client, db_session):
    stamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _add(
        db_session,
        role_category="bi_developer",
        role_label="Analytics Engineer",
        pdf_path="/kept.pdf",
        pdf_pages=2,
        pdf_rendered_at=stamp,
    )

    assert _identity(client, "anchored", {"countries": ["IN"], "company": "Acme"}).status_code == 200

    db_session.expire_all()
    row = db_session.get(BaseResume, "anchored")
    assert (row.role_category, row.role_label) == ("bi_developer", "Analytics Engineer")
    assert row.data_json == SAMPLE
    assert row.pdf_path == "/kept.pdf" and row.pdf_pages == 2
    assert row.pdf_rendered_at == stamp
    assert db_session.query(ResumeVersion).count() == 0


def test_role_patch_leaves_anchors_alone(client, db_session):
    _add(db_session, countries=["IN"], company="Acme", focus="payments")

    assert _identity(client, "anchored", {"role_category": "data_analyst"}).status_code == 200
    assert _identity(client, "anchored", {"role_label": "Analytics Engineer"}).status_code == 200
    assert _identity(client, "anchored", {"display_name": "Renamed"}).status_code == 200

    db_session.expire_all()
    row = db_session.get(BaseResume, "anchored")
    assert (row.countries, row.company, row.focus) == (["IN"], "Acme", "payments")


def test_duplicate_copies_anchors_once(client, db_session):
    _add(db_session, slug="src", countries=["IN", "US"], company="Acme", focus="payments")

    body = client.post("/api/base-resumes/src/duplicate", json={"new_slug": "clone"}).json()
    assert body["countries"] == ["IN", "US"]
    assert body["company"] == "Acme"
    assert body["focus"] == "payments"

    assert _identity(client, "clone", {"company": "Other", "countries": ["GB"]}).status_code == 200
    db_session.expire_all()
    src = db_session.get(BaseResume, "src")
    assert (src.countries, src.company, src.focus) == (["IN", "US"], "Acme", "payments")


def test_new_rows_default_to_no_anchors(db_session):
    row = _add(db_session)
    db_session.refresh(row)
    assert row.countries == []
    assert row.company is None and row.focus is None


def test_anchors_helper(db_session):
    anchors = base_resume_data.anchors

    assert anchors(None) is None
    assert anchors(_add(db_session, slug="empty")) is None

    # role 'unknown' contributes nothing; the other anchors still count.
    row = _add(db_session, slug="u", role_category="unknown", company="Acme")
    assert anchors(row) == {"countries": [], "role": None, "company": "Acme", "focus": None}

    # 'other' with no label has no role; with a label it is the label.
    assert anchors(_add(db_session, slug="o", role_category="other", company="Acme"))["role"] is None
    labelled = _add(db_session, slug="ol", role_category="other", role_label="Quant Dev")
    assert anchors(labelled)["role"] == "Quant Dev"

    # role_label wins over the category label; a catalog pick uses the label.
    both = _add(
        db_session, slug="b", role_category="bi_developer", role_label="Analytics Engineer"
    )
    assert anchors(both)["role"] == "Analytics Engineer"
    picked = _add(db_session, slug="p", role_category="data_analyst", countries=["IN"])
    assert anchors(picked) == {
        "countries": ["IN"],
        "role": "Data Analyst",
        "company": None,
        "focus": None,
    }

    # A role alone is enough to be non-empty.
    assert anchors(_add(db_session, slug="ro", role_category="data_analyst")) is not None

    # Soft-deleted: no anchors, however full the row.
    gone = _add(db_session, slug="gone", company="Acme", countries=["IN"])
    gone.deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.commit()
    assert anchors(gone) is None


def _session_for(db_session, slug) -> TailoringSession:
    job = Job(raw_text="jd", raw_text_hash=f"anchors-{slug}", extracted_json={})
    db_session.add(job)
    db_session.commit()
    row = TailoringSession(
        job_id=job.id, base_resume=slug, status="open", gaps_json={}, resolutions_json=[]
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_session_read_carries_base_anchors(db_session):
    base = _add(db_session, countries=["IN"], company="Acme", role_category="data_analyst")
    session = _session_for(db_session, "anchored")

    read = TailoringSessionRead.model_validate(session)
    assert read.base_anchors == base_resume_data.anchors(base)
    assert read.base_anchors == {
        "countries": ["IN"],
        "role": "Data Analyst",
        "company": "Acme",
        "focus": None,
    }

    base.deleted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.commit()
    db_session.expire_all()
    assert TailoringSessionRead.model_validate(session).base_anchors is None


def test_session_read_base_anchors_none_for_missing_base(db_session):
    session = _session_for(db_session, "never_existed")
    assert TailoringSessionRead.model_validate(session).base_anchors is None


def test_session_routes_serialize_base_anchors(client, db_session):
    _add(db_session, countries=["IN"], company="Acme")
    session = _session_for(db_session, "anchored")

    got = client.get(f"/api/tailoring-sessions/{session.id}").json()
    assert got["base_anchors"]["company"] == "Acme"
    listed = client.get(f"/api/tailoring-sessions?job_id={session.job_id}").json()
    assert listed[0]["base_anchors"]["countries"] == ["IN"]
    closed = client.post(f"/api/tailoring-sessions/{session.id}/close").json()
    assert closed["base_anchors"]["company"] == "Acme"


def test_summary_and_detail_carry_anchors(client, db_session):
    _add(db_session, countries=["IN", "US"], company="Acme", focus="payments")

    row = next(r for r in client.get("/api/base-resumes").json() if r["slug"] == "anchored")
    assert row["countries"] == ["IN", "US"]
    assert row["company"] == "Acme" and row["focus"] == "payments"

    detail = client.get("/api/base-resumes/anchored").json()
    assert detail["countries"] == ["IN", "US"]
    assert detail["company"] == "Acme" and detail["focus"] == "payments"
