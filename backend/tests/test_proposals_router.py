from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.services import auto_apply_settings
from tests.test_proposals_models import _mk_job

client = TestClient(app)


def test_create_and_get(db_session):
    job = _mk_job(db_session, company="Acme", source="agent")
    r = client.post("/api/proposals", json={
        "job_id": str(job.id),
        "fit": {"chosen_base": "hybrid", "decided_by": "auto", "scores": {"hybrid": 71}},
        "plan": {"summary": "no injection needed"},
    })
    assert r.status_code == 201
    pid = r.json()["id"]
    detail = client.get(f"/api/proposals/{pid}").json()
    assert detail["status"] == "pending_review"
    assert detail["job"]["company"] == "Acme"


def test_duplicate_open_proposal_returns_existing(db_session):
    job = _mk_job(db_session, company="BetaCo", source="agent")
    r1 = client.post("/api/proposals", json={"job_id": str(job.id)})
    assert r1.status_code == 201
    pid = r1.json()["id"]
    r2 = client.post("/api/proposals", json={"job_id": str(job.id)})
    assert r2.status_code == 200
    assert r2.json()["id"] == pid
    assert r2.json()["application_id"] is None


def test_propose_retry_late_links_application(db_session):
    job = _mk_job(db_session, company="LinkRetryCo", source="agent")
    r1 = client.post("/api/proposals", json={"job_id": str(job.id)})
    assert r1.status_code == 201
    pid = r1.json()["id"]

    app_row = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(app_row)
    db_session.commit()

    r2 = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id),
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == pid
    assert r2.json()["application_id"] == str(app_row.id)
    db_session.refresh(app_row)
    assert app_row.source == "agent"


def test_propose_retry_refuses_relink_different_application(db_session):
    job = _mk_job(db_session, company="NoRelinkCo", source="agent")
    app1 = Application(job_id=job.id, base_resume="hybrid", status="draft")
    app2 = Application(job_id=job.id, base_resume="swe", status="draft")
    db_session.add_all([app1, app2])
    db_session.commit()

    r1 = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app1.id),
    })
    assert r1.status_code == 201

    r2 = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app2.id),
    })
    assert r2.status_code == 409
    assert "already linked" in r2.json()["detail"]


def test_propose_on_accepted_proposal_is_idempotent_and_late_links(db_session):
    # First apply run (2026-08-01) regression: the router's open-proposal check
    # had its own literal status tuple missing "accepted", so a late-link
    # propose on a triaged job minted a DUPLICATE proposal instead of
    # returning the accepted one.
    job = _mk_job(db_session, company="IdemAcceptCo", source="agent")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    r = client.patch(f"/api/proposals/{pid}", json={
        "status": "accepted", "consent": {"channel": "frontend"}})
    assert r.status_code == 200

    app_row = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(app_row)
    db_session.commit()

    r2 = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id)})
    assert r2.status_code == 200          # idempotent return, not a new row
    assert r2.json()["id"] == pid          # SAME proposal
    assert r2.json()["application_id"] == str(app_row.id)  # late-linked


def test_declined_job_cannot_be_reproposed(db_session):
    # Owner decision 2026-08-01 (design G3): a decline permanently blocks
    # re-proposing THAT posting while the rejected row exists.
    job = _mk_job(db_session, company="CoolCo")
    r1 = client.post("/api/proposals", json={"job_id": str(job.id)})
    pid = r1.json()["id"]
    r_rej = client.patch(f"/api/proposals/{pid}", json={
        "status": "rejected",
        "consent": {"channel": "chat", "note": "not hiring"},
        "reason": "not hiring",
    })
    assert r_rej.status_code == 200

    r2 = client.post("/api/proposals", json={"job_id": str(job.id)})
    assert r2.status_code == 409
    assert "declined" in r2.json()["detail"]


def test_decline_does_not_cooldown_the_company(db_session):
    # Declining one posting never implicates the company (design G3): a
    # different role at the same company proposes fine the same day.
    job1 = _mk_job(db_session, company="CoolCo", title="Data Analyst")
    r1 = client.post("/api/proposals", json={"job_id": str(job1.id)})
    r_rej = client.patch(f"/api/proposals/{r1.json()['id']}", json={
        "status": "rejected",
        "consent": {"channel": "frontend"},
        "reason": "low fit",
    })
    assert r_rej.status_code == 200

    job2 = _mk_job(db_session, company="CoolCo", title="Data Scientist")
    r2 = client.post("/api/proposals", json={"job_id": str(job2.id)})
    assert r2.status_code == 201


def test_bulk_accept_mixed_results(db_session):
    job_ok = _mk_job(db_session, company="BulkOkCo")
    r_ok = client.post("/api/proposals", json={"job_id": str(job_ok.id)})
    ok_id = r_ok.json()["id"]

    job_term = _mk_job(db_session, company="BulkTermCo")
    r_term = client.post("/api/proposals", json={"job_id": str(job_term.id)})
    term_id = r_term.json()["id"]
    # Drive the second proposal to a terminal state so bulk-accept must 409 it.
    r_rej = client.patch(f"/api/proposals/{term_id}", json={
        "status": "rejected", "consent": {"channel": "chat"}, "reason": "no"})
    assert r_rej.status_code == 200

    resp = client.post("/api/proposals/bulk-transition", json={
        "ids": [ok_id, term_id],
        "status": "accepted",
        "consent": {"channel": "frontend"},
    })
    assert resp.status_code == 200
    results = {r["id"]: r for r in resp.json()["results"]}
    assert results[ok_id]["ok"] is True and results[ok_id]["status"] == "accepted"
    assert results[term_id]["ok"] is False and results[term_id]["detail"]


def test_bulk_decline_records_reason(db_session):
    job = _mk_job(db_session, company="BulkDeclineCo")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    resp = client.post("/api/proposals/bulk-transition", json={
        "ids": [pid],
        "status": "rejected",
        "consent": {"channel": "frontend"},
        "reason": "low fit",
    })
    assert resp.status_code == 200
    detail = client.get(f"/api/proposals/{pid}").json()
    assert detail["status"] == "rejected"
    assert detail["reason"] == "low fit"


def test_bulk_rejects_illegal_target_status(db_session):
    # Mass-approve/mass-submit must stay impossible (design §3b).
    resp = client.post("/api/proposals/bulk-transition", json={
        "ids": [], "status": "approved", "consent": {"channel": "frontend"}})
    assert resp.status_code == 422


def test_delete_refused_for_submitted_proposals(db_session):
    # Submitted rows ARE the audit trail of a machine submission (design §3c).
    job = _mk_job(db_session, company="DelGuardCo")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    prop = db_session.get(ApplicationProposal, pid)
    prop.status = "submitted"
    db_session.commit()
    r = client.delete(f"/api/proposals/{pid}")
    assert r.status_code == 409
    assert "audit" in r.json()["detail"]

    prop.status = "submission_uncertain"
    db_session.commit()
    assert client.delete(f"/api/proposals/{pid}").status_code == 409


def test_delete_unknown_proposal_404(db_session):
    import uuid
    assert client.delete(f"/api/proposals/{uuid.uuid4()}").status_code == 404


def test_company_blocklist_409(db_session):
    cfg = auto_apply_settings.get_settings(db_session)
    cfg.company_blocklist = ["BadCo"]
    auto_apply_settings.set_settings(cfg, db_session)

    job = _mk_job(db_session, company="BadCo")
    r = client.post("/api/proposals", json={"job_id": str(job.id)})
    assert r.status_code == 409
    assert "blocklisted" in r.json()["detail"]


def test_list_proposals_multi_status_pagination_and_total(db_session):
    pids = []
    for i in range(3):
        job = _mk_job(db_session, company=f"PageCo{i}")
        pids.append(client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"])
    # Accept two of them so the multi-status filter has two lanes to span.
    for pid in pids[:2]:
        r = client.patch(f"/api/proposals/{pid}", json={
            "status": "accepted", "consent": {"channel": "frontend"}})
        assert r.status_code == 200

    body = client.get(
        "/api/proposals?status=pending_review,accepted&limit=2&offset=0").json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    rest = client.get(
        "/api/proposals?status=pending_review,accepted&limit=2&offset=2").json()
    assert rest["total"] == 3
    assert len(rest["items"]) == 1

    only_accepted = client.get("/api/proposals?status=accepted").json()
    assert only_accepted["total"] == 2
    assert {i["status"] for i in only_accepted["items"]} == {"accepted"}


def test_funnel_reports_accepted_and_cap(db_session):
    job = _mk_job(db_session, company="FunnelCapCo")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    r = client.patch(f"/api/proposals/{pid}", json={
        "status": "accepted", "consent": {"channel": "frontend"}})
    assert r.status_code == 200

    body = client.get("/api/proposals/funnel").json()
    assert body["accepted"] == 1
    cap = body["cap"]
    assert set(cap) == {"max_per_day", "reserved_last_24h", "remaining"}
    assert cap["remaining"] == cap["max_per_day"] - cap["reserved_last_24h"]


def test_list_filters_by_status_and_lazily_expires(db_session):
    job1 = _mk_job(db_session, company="C1")
    job2 = _mk_job(db_session, company="C2")

    r1 = client.post("/api/proposals", json={"job_id": str(job1.id)})
    pid1 = r1.json()["id"]
    r2 = client.post("/api/proposals", json={"job_id": str(job2.id)})
    pid2 = r2.json()["id"]

    # Expire proposal 1 manually
    prop1 = db_session.get(ApplicationProposal, pid1)
    prop1.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    # GET list triggers lazy expiry
    r_list = client.get("/api/proposals")
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    statuses = {item["id"]: item["status"] for item in items}
    assert statuses[pid1] == "expired"
    assert statuses[pid2] == "pending_review"

    # Query with status filter
    r_pending = client.get("/api/proposals?status=pending_review")
    assert r_pending.status_code == 200
    pending_ids = [item["id"] for item in r_pending.json()["items"]]
    assert pid2 in pending_ids
    assert pid1 not in pending_ids


def test_approve_without_consent_409(db_session):
    job = _mk_job(db_session)
    r = client.post("/api/proposals", json={"job_id": str(job.id)})
    pid = r.json()["id"]

    r_app = client.patch(f"/api/proposals/{pid}", json={"status": "approved"})
    assert r_app.status_code == 409
    assert "requires consent" in r_app.json()["detail"]


def test_approve_then_submit_flow(db_session):
    from app.models.application import Application

    job = _mk_job(db_session)
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()

    r = client.post("/api/proposals", json={"job_id": str(job.id), "application_id": str(app_row.id)})
    pid = r.json()["id"]

    prop = db_session.get(ApplicationProposal, pid)
    prop.evidence_json = [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]
    db_session.commit()

    r_app = client.patch(f"/api/proposals/{pid}", json={
        "status": "approved",
        "consent": {"channel": "chat", "note": "approved via chat"},
    })
    assert r_app.status_code == 200
    assert r_app.json()["status"] == "approved"

    prop = db_session.get(ApplicationProposal, pid)
    prop.evidence_json = list(prop.evidence_json or []) + [{
        "step": 100, "label": "receipt", "path": "evidence/rcpt.png",
        "sha256": "rc", "kind": "submission_receipt",
    }]
    db_session.commit()

    r_sub = client.patch(f"/api/proposals/{pid}", json={"status": "submitted"})
    assert r_sub.status_code == 200
    assert r_sub.json()["status"] == "submitted"

    db_session.refresh(app_row)
    assert app_row.status == "applied"
    assert app_row.applied_at is not None


def test_double_approve_conflict(db_session):
    job = _mk_job(db_session)
    r = client.post("/api/proposals", json={"job_id": str(job.id)})
    pid = r.json()["id"]

    prop = db_session.get(ApplicationProposal, pid)
    prop.evidence_json = [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]
    db_session.commit()

    r1 = client.patch(f"/api/proposals/{pid}", json={
        "status": "approved",
        "consent": {"channel": "chat"},
    })
    assert r1.status_code == 200

    r2 = client.patch(f"/api/proposals/{pid}", json={
        "status": "approved",
        "consent": {"channel": "chat"},
    })
    assert r2.status_code == 409


def test_decision_resolution(db_session):
    job = _mk_job(db_session)
    app_row = Application(job_id=job.id, base_resume="backend_eng", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()
    r = client.post("/api/proposals", json={"job_id": str(job.id)})
    pid = r.json()["id"]

    # Transition to needs_decision
    r_nd = client.patch(f"/api/proposals/{pid}", json={"status": "needs_decision", "reason": "ambiguous role"})
    assert r_nd.status_code == 200
    assert r_nd.json()["status"] == "needs_decision"

    # Resolve decision back to pending_review with fit payload (auto-links app)
    r_res = client.patch(f"/api/proposals/{pid}", json={
        "status": "pending_review",
        "fit": {"chosen_base": "backend_eng"},
    })
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "pending_review"
    assert r_res.json()["fit_json"]["chosen_base"] == "backend_eng"
    assert r_res.json()["fit_json"]["decided_by"] == "user"
    assert r_res.json()["application_id"] == str(app_row.id)


def test_proposals_funnel_summary(db_session):
    _mk_job(db_session, source="user")
    job_agent1 = _mk_job(db_session, source="agent", company="A1")
    job_agent2 = _mk_job(db_session, source="agent", company="A2")
    job_agent3 = _mk_job(db_session, source="agent", company="A3")
    job_agent4 = _mk_job(db_session, source="agent", company="A4")

    # Proposal 1: pending_review
    client.post("/api/proposals", json={"job_id": str(job_agent1.id)})

    # Proposal 2: approved -> submitted
    app2 = Application(job_id=job_agent2.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app2)
    db_session.commit()
    p2 = client.post("/api/proposals", json={"job_id": str(job_agent2.id), "application_id": str(app2.id)}).json()
    prop2 = db_session.get(ApplicationProposal, p2['id'])
    prop2.evidence_json = [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]
    db_session.commit()
    client.patch(f"/api/proposals/{p2['id']}", json={"status": "approved", "consent": {"channel": "chat"}})
    prop2 = db_session.get(ApplicationProposal, p2['id'])
    prop2.evidence_json = list(prop2.evidence_json or []) + [{
        "step": 100, "label": "receipt", "path": "evidence/rcpt.png",
        "sha256": "rc", "kind": "submission_receipt",
    }]
    db_session.commit()
    client.patch(f"/api/proposals/{p2['id']}", json={"status": "submitted"})

    # Proposal 3: rejected
    p3 = client.post("/api/proposals", json={"job_id": str(job_agent3.id)}).json()
    client.patch(f"/api/proposals/{p3['id']}", json={"status": "rejected", "consent": {"channel": "chat"}})

    # App interviewing (from agent)
    app_int = Application(job_id=job_agent4.id, base_resume="hybrid", source="agent", status="interviewing")
    db_session.add(app_int)
    db_session.commit()

    res = client.get("/api/proposals/funnel")
    assert res.status_code == 200
    data = res.json()
    assert data["captured"] == 4
    assert data["proposed"] == 1
    assert data["submitted"] == 1
    assert data["rejected_proposals"] == 1
    assert data["interviewing"] == 1




def test_detail_renders_qa_entries(db_session):
    # Regression: _detail must read QAEntry.kind/.prompt (the real columns) —
    # an earlier draft used .question/.question_type and 500'd on any proposal
    # whose application had Q&A.
    from app.models.qa_entry import QAEntry

    job = _mk_job(db_session, company="QACo", source="agent")
    app_row = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(app_row)
    db_session.flush()
    db_session.add(QAEntry(application_id=app_row.id, kind="question",
                           prompt="Years of Python?", answer="6"))
    db_session.commit()

    r = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id),
    })
    assert r.status_code == 201
    detail = client.get(f"/api/proposals/{r.json()['id']}").json()
    assert detail["qa_entries"] == [
        {
            "id": detail["qa_entries"][0]["id"],
            "kind": "question",
            "prompt": "Years of Python?",
            "answer": "6",
            "created_at": detail["qa_entries"][0]["created_at"],
        }
    ]


def test_proposal_link_stamps_application_agent_source(db_session):
    # Linking at create time flips the application into the agent lane.
    job = _mk_job(db_session, company="StampCo", source="agent")
    app_row = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(app_row)
    db_session.commit()
    assert app_row.source == "user"

    r = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id),
    })
    assert r.status_code == 201
    db_session.refresh(app_row)
    assert app_row.source == "agent"


def test_late_application_link_via_decision(db_session):
    # needs_decision proposals are filed before tailoring; the decision round
    # supplies the application afterward. Relinking is refused.
    job = _mk_job(db_session, company="LateCo", source="agent")
    r = client.post("/api/proposals", json={"job_id": str(job.id)})
    pid = r.json()["id"]
    r = client.patch(f"/api/proposals/{pid}", json={"status": "needs_decision"})
    assert r.status_code == 200

    app_row = Application(job_id=job.id, base_resume="ml_eng", status="draft")
    db_session.add(app_row)
    db_session.commit()

    r = client.patch(f"/api/proposals/{pid}", json={
        "status": "pending_review",
        "fit": {"chosen_base": "ml_eng"},
        "application_id": str(app_row.id),
    })
    assert r.status_code == 200
    body = r.json()
    assert body["application_id"] == str(app_row.id)
    assert body["fit_json"]["decided_by"] == "user"
    db_session.refresh(app_row)
    assert app_row.source == "agent"

    other = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(other)
    db_session.commit()
    r = client.patch(f"/api/proposals/{pid}", json={
        "status": "approved",
        "consent": {"channel": "chat"},
        "application_id": str(other.id),
    })
    assert r.status_code == 409
    assert "already linked" in r.json()["detail"]


def _fr_evidence():
    return [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]


def test_request_decision_and_resume_endpoints(db_session):
    job = _mk_job(db_session, source="agent", company="ResumeCo")
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]

    r = client.post(f"/api/proposals/{pid}/request-decision", json={"reason": "ambiguous"})
    assert r.status_code == 200
    assert r.json()["status"] == "needs_decision"

    client.patch(f"/api/proposals/{pid}", json={
        "status": "pending_review",
        "fit": {"chosen_base": "hybrid"},
        "application_id": str(app_row.id),
    })
    client.patch(f"/api/proposals/{pid}", json={
        "status": "needs_human", "reason": "captcha",
    })
    r = client.post(f"/api/proposals/{pid}/resume")
    assert r.status_code == 200
    assert r.json()["status"] == "pending_review"


def test_report_failure_submission_uncertain(db_session):
    job = _mk_job(db_session, source="agent", company="UncertainCo")
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()
    pid = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id),
    }).json()["id"]
    prop = db_session.get(ApplicationProposal, pid)
    prop.evidence_json = _fr_evidence()
    db_session.commit()
    client.patch(f"/api/proposals/{pid}", json={
        "status": "approved", "consent": {"channel": "chat"},
    })
    r = client.post(f"/api/proposals/{pid}/report-failure", json={"reason": "submission_uncertain"})
    assert r.status_code == 200
    assert r.json()["status"] == "submission_uncertain"
    r2 = client.post(f"/api/proposals/{pid}/resume")
    assert r2.status_code == 409


def test_get_final_review_bundle(db_session):
    from app.models.qa_entry import QAEntry

    job = _mk_job(db_session, source="agent", company="ReviewCo", title="Eng")
    app_row = Application(
        job_id=job.id, base_resume="hybrid", source="agent", status="draft",
        pdf_path="/tmp/Resume.pdf",
    )
    db_session.add(app_row)
    db_session.flush()
    db_session.add(QAEntry(
        application_id=app_row.id, kind="question",
        prompt="Years of Python?", answer="6",
    ))
    db_session.commit()
    pid = client.post("/api/proposals", json={
        "job_id": str(job.id),
        "application_id": str(app_row.id),
        "fit": {"chosen_base": "hybrid", "scores": {"hybrid": 80, "ml_eng": 70}},
        "plan": {"summary": "ok", "blocked_items": ["signature"], "manual_items": ["CAPTCHA"]},
    }).json()["id"]
    prop = db_session.get(ApplicationProposal, pid)
    prop.evidence_json = _fr_evidence()
    db_session.commit()

    r = client.get(f"/api/proposals/{pid}/final-review")
    assert r.status_code == 200
    body = r.json()
    assert body["job"]["company"] == "ReviewCo"
    assert body["fit"]["chosen_base"] == "hybrid"
    assert body["pdf"]["ready"] is True
    assert body["pdf"]["filename"] == "Resume.pdf"
    assert body["qa_entries"][0]["prompt"] == "Years of Python?"
    assert "answer" in body["qa_entries"][0]
    assert body["eeo"]["consent_recorded"] is False
    assert body["blocked_items"] == ["signature"]
    assert body["manual_items"] == ["CAPTCHA"]
    assert body["evidence"][0]["kind"] == "final_review"


def test_evidence_kind_required_on_upload(db_session, tmp_path, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    job = _mk_job(db_session, source="agent", company="KindCo")
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()
    pid = client.post("/api/proposals", json={
        "job_id": str(job.id), "application_id": str(app_row.id),
    }).json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    r = client.post(
        f"/api/proposals/{pid}/evidence",
        files={"file": ("shot.png", png, "image/png")},
        data={"step": "1", "label": "contact", "kind": "step"},
    )
    assert r.status_code == 201
    assert r.json()["kind"] == "step"
    r_bad = client.post(
        f"/api/proposals/{pid}/evidence",
        files={"file": ("shot2.png", png, "image/png")},
        data={"step": "2", "label": "x", "kind": "nope"},
    )
    assert r_bad.status_code == 422
