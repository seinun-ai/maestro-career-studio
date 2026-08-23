"""Read-only base→KB classification ladder (no writes)."""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.services import kb_base_sync


def _resume(**sections):
    base = {
        "contact": {"name": "A", "email": "a@x.com"},
        "summary": "A professional summary that must be ignored.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    base.update(sections)
    return base


def _seed_base(db_session, tmp_path, monkeypatch, data, slug="hybrid"):
    monkeypatch.setattr("app.services.base_resume_data.settings.base_resumes_dir", tmp_path)
    row = BaseResume(slug=slug, data_json=data)
    db_session.add(row)
    db_session.flush()
    (tmp_path / f"{slug}.json").write_text(json.dumps(data), encoding="utf-8")
    return row


def _exp_entity(db_session, *, org="Acme", title="Engineer", start="2021", text=None):
    ent = KBEntity(
        kind="experience", title=title, org=org, start_date=start, status="completed"
    )
    db_session.add(ent)
    db_session.flush()
    if text is not None:
        db_session.add(
            KBPoint(
                entity_id=ent.id,
                text=text,
                state="approved",
                origin="manual",
                provenance="user_authored",
            )
        )
        db_session.flush()
    return ent


def test_typo_variant_is_in_sync(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="Built the ingestion pipeline")
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["built  the ingestion pipeline"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "experience"]
    assert len(items) == 1
    assert items[0].tier == "in_sync"
    assert report["counts"]["in_sync"] >= 1
    assert report["counts"]["drift"] == 0
    assert report["counts"]["new"] == 0


def test_mild_rephrase_is_drift_not_new(db_session, tmp_path, monkeypatch):
    # Reuse the hermetic embedder's 0.96 pair so this stays model-free.
    _exp_entity(db_session, text="machine learning")
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["shipped ml models to production"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "experience"]
    assert len(items) == 1
    assert items[0].tier == "drift"
    assert items[0].matched_point_id is not None
    assert report["counts"]["new"] == 0


def test_new_claim_is_new(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="Built the ingestion pipeline")
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["Negotiated a net-new vendor contract worth two million"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "experience"]
    assert len(items) == 1
    assert items[0].tier == "new"
    assert items[0].entity_id is not None
    assert items[0].matched_point_id is None


def test_entry_without_entity_is_new_with_entity_proposal(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="Built the ingestion pipeline")
    data = _resume(
        experience=[
            {
                "company": "OtherCo",
                "role": "Lead",
                "start_date": "2024",
                "bullets": ["Stood up a greenfield billing service"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "experience"]
    assert len(items) == 1
    assert items[0].tier == "new"
    assert items[0].entity_id is None
    assert items[0].entity_proposal == {
        "kind": "experience",
        "title": "Lead",
        "org": "OtherCo",
        "start_date": "2024",
        "end_date": None,
    }


def test_education_cert_extra_match_by_identity_key(db_session, tmp_path, monkeypatch):
    edu = KBEntity(
        kind="education", title="BS CS", org="State U", status="completed"
    )
    cert = KBEntity(kind="certification", title="AWS SAA", status="completed")
    extra = KBEntity(
        kind="extra",
        title="Paper One",
        status="completed",
        detail_json={
            "section_key": "publications",
            "section_type": "entries",
            "section_title": "Publications",
        },
    )
    db_session.add_all([edu, cert, extra])
    db_session.flush()
    data = _resume(
        education=[{"institution": "State U", "degree": "BS CS"}],
        certifications=["AWS SAA"],
        extra_sections=[
            {
                "key": "publications",
                "title": "Publications",
                "type": "entries",
                "enabled": True,
                "entries": [{"heading": "Paper One", "bullets": ["Cited 12 times"]}],
            }
        ],
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    by_section = {i.section: i for i in report["items"]}
    assert by_section["education"].tier == "in_sync"
    assert by_section["certifications"].tier == "in_sync"
    assert by_section["extra"].tier == "in_sync"
    assert report["counts"]["new"] == 0


def test_new_skills_are_additive_diff_against_profile(db_session, tmp_path, monkeypatch):
    db_session.add(
        KBProfile(
            id=1,
            skills_json=[{"category": "Languages", "items": ["Python"]}],
        )
    )
    db_session.flush()
    data = _resume(
        skills=[
            {"category": "Languages", "items": ["Python", "Rust"]},
            {"category": "Cloud", "items": ["AWS"]},
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    assert set(report["skills_new"]) == {"Rust", "AWS"}
    assert report["counts"]["skills_new"] == 2


def _drifting_resume(bullet="shipped ml models to production"):
    # Reuse the hermetic embedder's 0.96-vs-"machine learning" bullets so this
    # stays model-free. "ml systems in production" carries the same vector, so
    # it is a second, differently-worded drift against the same point.
    return _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": [bullet],
            }
        ]
    )


def _rewrite_base(db_session, tmp_path, data, slug="hybrid"):
    """Swap a seeded base's contents in place (both the file and the row)."""
    (tmp_path / f"{slug}.json").write_text(json.dumps(data), encoding="utf-8")
    row = db_session.get(BaseResume, slug)
    row.data_json = data
    db_session.flush()
    return row


def _port_log(db_session, entity, point, *, direction, slug="hybrid"):
    """A port-log row asserting one association, as another writer would leave it."""
    db_session.add(
        KBPortLog(
            entity_id=entity.id,
            point_id=point.id,
            resume_kind="base",
            resume_key=slug,
            section="experience",
            ported_text="shipped ml models to production",
            direction=direction,
        )
    )
    db_session.flush()


def test_recorded_drift_stops_counting(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    kb_base_sync.apply(db_session, "hybrid")

    report = kb_base_sync.classify(db_session, "hybrid")
    assert report["counts"]["drift"] == 0
    assert report["counts"]["recorded_drift"] == 1
    assert [i for i in report["items"] if i.tier == "drift"] == []
    recorded = [i for i in report["items"] if i.tier == "recorded"]
    assert len(recorded) == 1
    assert recorded[0].matched_point_id is not None
    assert recorded[0].section == "experience"


def test_sync_then_reclassify_is_fully_quiet(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="machine learning")
    data = _drifting_resume()
    data["experience"][0]["bullets"].append("Negotiated a net-new vendor contract")
    data["skills"] = [{"category": "Cloud", "items": ["AWS"]}]
    _seed_base(db_session, tmp_path, monkeypatch, data)
    kb_base_sync.apply(db_session, "hybrid")

    report = kb_base_sync.classify(db_session, "hybrid")
    assert report["counts"]["new"] == 0
    assert report["counts"]["drift"] == 0
    assert report["counts"]["skills_new"] == 0


def test_classify_payload_carries_last_synced_at(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    assert kb_base_sync.classify(db_session, "hybrid")["last_kb_synced_at"] is None

    before = datetime.now(UTC)
    kb_base_sync.apply(db_session, "hybrid")
    stamped = kb_base_sync.classify(db_session, "hybrid")["last_kb_synced_at"]
    assert stamped is not None
    assert stamped >= before

    kb_base_sync.apply(db_session, "hybrid")
    assert kb_base_sync.classify(db_session, "hybrid")["last_kb_synced_at"] > stamped


def test_import_provenance_is_recorded_before_any_sync(db_session, tmp_path, monkeypatch):
    """A port log from import — not from sync — already documents the wording."""
    ent = _exp_entity(db_session, text="machine learning")
    point = db_session.scalars(select(KBPoint)).one()
    _port_log(db_session, ent, point, direction="from_source")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())

    report = kb_base_sync.classify(db_session, "hybrid")
    assert report["last_kb_synced_at"] is None  # never synced, still recorded
    assert report["counts"]["drift"] == 0
    assert report["counts"]["recorded_drift"] == 1


def test_rewording_a_recorded_bullet_re_reports_drift(db_session, tmp_path, monkeypatch):
    """Memory is keyed by text: new wording is new, unrecorded drift."""
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    kb_base_sync.apply(db_session, "hybrid")
    assert kb_base_sync.classify(db_session, "hybrid")["counts"]["recorded_drift"] == 1

    _rewrite_base(db_session, tmp_path, _drifting_resume("ml systems in production"))
    report = kb_base_sync.classify(db_session, "hybrid")
    assert report["counts"]["drift"] == 1
    assert report["counts"]["recorded_drift"] == 0


def test_recorded_drift_is_scoped_to_one_base_resume(db_session, tmp_path, monkeypatch):
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume(), slug="compact")
    kb_base_sync.apply(db_session, "hybrid")

    assert kb_base_sync.classify(db_session, "hybrid")["counts"]["recorded_drift"] == 1
    other = kb_base_sync.classify(db_session, "compact")
    assert other["counts"]["drift"] == 1
    assert other["counts"]["recorded_drift"] == 0


def test_summary_and_contact_are_ignored(db_session, tmp_path, monkeypatch):
    data = _resume(summary="Brand-new summary that is not evidence.", contact={"name": "Z"})
    _seed_base(db_session, tmp_path, monkeypatch, data)
    report = kb_base_sync.classify(db_session, "hybrid")
    assert report["items"] == []
    assert report["skills_new"] == []
    assert report["counts"]["new"] == 0
    assert report["counts"]["drift"] == 0
