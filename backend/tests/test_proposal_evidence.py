from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.main import app
from app.models.application import Application
from app.services import application_artifacts, proposal_evidence
from tests.test_proposal_state_machine import _mk_proposal

client = TestClient(app)


def test_upload_appends_manifest_and_serves_back(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    prop = _mk_proposal(db_session)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    r = client.post(
        f"/api/proposals/{prop.id}/evidence",
        files={"file": ("shot.png", png, "image/png")},
        data={"step": "1", "label": "contact page", "kind": "step"},
    )
    assert r.status_code == 201
    manifest = client.get(f"/api/proposals/{prop.id}").json()["evidence_json"]
    assert len(manifest) == 1
    assert manifest[0]["label"] == "contact page"
    assert manifest[0]["sha256"]
    assert manifest[0]["path"].startswith("evidence/")
    name = manifest[0]["path"].rsplit("/", 1)[-1]
    app_row = db_session.get(Application, prop.application_id)
    assert app_row.artifact_dir
    assert (Path(app_row.artifact_dir) / "evidence" / name).is_file()
    served = client.get(f"/api/proposals/{prop.id}/evidence/{name}")
    assert served.status_code == 200 and served.content == png


def test_upload_evidence_requires_linked_application(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    prop = _mk_proposal(db_session, with_app=False)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    r = client.post(
        f"/api/proposals/{prop.id}/evidence",
        files={"file": ("shot.png", png, "image/png")},
        data={"step": "1", "label": "contact page", "kind": "step"},
    )
    assert r.status_code == 409
    assert "application" in r.json()["detail"].lower()


def test_serve_rejects_path_traversal(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    prop = _mk_proposal(db_session)
    assert client.get(
        f"/api/proposals/{prop.id}/evidence/..%2F..%2Fsecrets.png"
    ).status_code in (400, 404)


def test_delete_removes_row_consent_events_and_evidence_files(db_session, tmp_path, monkeypatch):
    from app.models.application_proposal import ApplicationProposal
    from app.models.consent_event import ConsentEvent
    from app.services import proposals as svc

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    prop = _mk_proposal(db_session)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    r = client.post(
        f"/api/proposals/{prop.id}/evidence",
        files={"file": ("shot.png", png, "image/png")},
        data={"step": "1", "label": "step one", "kind": "step"},
    )
    assert r.status_code == 201
    db_session.refresh(prop)
    name = prop.evidence_json[0]["path"].rsplit("/", 1)[-1]
    app_row = db_session.get(Application, prop.application_id)
    evidence_path = Path(app_row.artifact_dir) / "evidence" / name
    assert evidence_path.is_file()
    # A consent event to prove the FK cascade clears the ledger rows too.
    svc.transition(db_session, prop, "rejected",
                   consent={"channel": "frontend"}, reason="duplicate")
    prop_id = prop.id

    resp = client.delete(f"/api/proposals/{prop_id}")
    assert resp.status_code == 204
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, prop_id) is None
    assert db_session.query(ConsentEvent).filter_by(proposal_id=prop_id).count() == 0
    assert not evidence_path.exists()
    # The application and its artifact dir stay — only the proposal record goes.
    assert db_session.get(Application, app_row.id) is not None


def test_save_evidence_migrates_legacy_dirs(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    prop = _mk_proposal(db_session)
    app_row = db_session.get(Application, prop.application_id)
    artifact = application_artifacts.get_dir(
        db_session, app_row, company="Acme", role_label="Role"
    )

    legacy_app = tmp_path / str(app_row.id) / "evidence"
    legacy_app.mkdir(parents=True)
    (legacy_app / "step-01-old.png").write_bytes(b"\x89PNG\r\nold")

    legacy_prop = tmp_path / str(prop.id) / "evidence"
    legacy_prop.mkdir(parents=True)
    (legacy_prop / "step-01-old.png").write_bytes(b"\x89PNG\r\nprop")

    prop.evidence_json = [
        {
            "step": 1,
            "label": "old",
            "path": "evidence/step-01-old.png",
            "sha256": "aaa",
            "captured_at": "2026-07-01T00:00:00+00:00",
        },
        {
            "step": 1,
            "label": "prop",
            "path": "evidence/step-01-old.png",
            "sha256": "bbb",
            "captured_at": "2026-07-02T00:00:00+00:00",
        },
    ]
    db_session.commit()

    proposal_evidence.migrate_legacy_evidence(db_session, prop)

    dest = artifact / "evidence"
    assert (dest / "step-01-old.png").read_bytes() == b"\x89PNG\r\nold"
    migrated = list(dest.glob("step-01-old*.png"))
    assert len(migrated) == 2
    db_session.refresh(prop)
    paths = {item["path"] for item in prop.evidence_json}
    assert all(p.startswith("evidence/") for p in paths)
    assert len(paths) == 2
