"""With sync on, a capture with `update` corrects only a job this copy owns; a replica refuses it
before any write, while a repeat capture without `update` still answers it."""

import uuid

from app.models.job import Job
from app.models.job_skill import JobSkill

TEXT = "Warehouse Supervisor at Kestrel Logistics, Lyon."
FIRST = {"title": "Warehouse Supervisor", "company": "Kestrel Logistics", "city": "Lyon",
         "skills": [{"skill_name": "WMS", "skill_category": "tool", "requirement_level": "required"}]}
FIXED = {**FIRST, "title": "Senior Warehouse Supervisor",
         "skills": [{"skill_name": "Forklift", "skill_category": "domain", "requirement_level": "required"}]}


def _replica(db, job_id):
    """The way a sync apply leaves a job the other copy owns."""
    db.info["sync_apply"] = True
    try:
        db.get(Job, uuid.UUID(job_id)).owner_machine = "other-copy"
        db.commit()
    finally:
        db.info.pop("sync_apply", None)


def test_an_owned_job_takes_the_correction(client, db_session, sync_on):
    first = client.post("/api/jobs/ingest", json={"extracted_json": FIRST, "raw_text": TEXT}).json()

    fixed = client.post("/api/jobs/ingest", json={"extracted_json": FIXED, "raw_text": TEXT, "update": True})

    assert fixed.status_code == 200
    assert (fixed.json()["id"], fixed.json()["title"]) == (first["id"], "Senior Warehouse Supervisor")


def test_a_replica_refuses_a_correction_and_keeps_its_fields(client, db_session, sync_on):
    first = client.post("/api/jobs/ingest", json={"extracted_json": FIRST, "raw_text": TEXT}).json()
    _replica(db_session, first["id"])

    refused = client.post("/api/jobs/ingest", json={"extracted_json": FIXED, "raw_text": TEXT, "update": True})
    plain = client.post("/api/jobs/ingest", json={"extracted_json": FIXED, "raw_text": TEXT})

    assert refused.status_code == 409
    assert plain.status_code == 200 and plain.json()["already_existed"] is True
    db_session.expire_all()
    job = db_session.get(Job, uuid.UUID(first["id"]))
    assert job.title == "Warehouse Supervisor"
    skills = db_session.query(JobSkill).filter(JobSkill.job_id == job.id).all()
    assert [s.skill_name for s in skills] == ["wms"]
