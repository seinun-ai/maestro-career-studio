"""find_near_identity() wired into the three consumers that resolve entities.

Unit contracts for the matcher itself live in test_kb_near_identity.py. This
file only asks whether the ingest and sync paths actually CALL it, and what
they do with a hit — the near-match is a second pass on an exact-identity-key
miss, so every case here is built so the exact key cannot match.

The load-bearing test is ``test_az900_dp900_never_merge_at_consolidate_level``:
the matcher's meanest rule, asserted end to end through a real write path.
"""

import pytest
from sqlalchemy import select

from app.models.career_kb import KBEntity, KBPoint
from app.services import kb_base_sync
from app.services.kb_consolidation import consolidate, consolidate_deterministic
from tests.test_kb_base_sync_classify import _resume, _seed_base


def _boom(*_a, **_k):
    raise AssertionError("no LLM call belongs on this path")


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr("app.services.llm.call_openai", _boom)


# Local, not the classify file's: these cases need a company/start the base
# entries can near-miss on, not that file's Acme/Engineer/2021 default.
def _exp_entity(db_session, *, org="TCS", title="Data Analyst", start="2022-07"):
    ent = KBEntity(
        kind="experience", title=title, org=org, start_date=start, status="completed"
    )
    db_session.add(ent)
    db_session.flush()
    return ent


def _certs(db_session):
    return db_session.scalars(select(KBEntity).where(KBEntity.kind == "certification")).all()


# --- consumer 1: consolidate() (LLM path, certs resolve by identity) -------
#
# Experience never reaches the near matcher here — it resolves in
# `_resolve_family`, whose docstring carries the invariant and the reason. So
# every rename case in this file lives under consumer 2 below.


def test_reimport_cert_with_exam_code_creates_no_new_entity(db_session, no_llm):
    consolidate(db_session, [("a", _resume(certifications=["AWS Certified AI Practitioner"]))])
    assert len(_certs(db_session)) == 1

    report = consolidate(
        db_session,
        [("b", _resume(certifications=["AWS Certified AI Practitioner (AIF-C01)"]))],
    )
    assert len(_certs(db_session)) == 1
    assert report.entities_created == 0
    assert report.entities_matched == 1


def test_az900_dp900_never_merge_at_consolidate_level(db_session, no_llm):
    consolidate(db_session, [("a", _resume(certifications=["Microsoft Certified: Azure Fundamentals"]))])
    consolidate(
        db_session,
        [("b", _resume(certifications=["Microsoft Certified: Azure Data Fundamentals"]))],
    )
    titles = {e.title for e in _certs(db_session)}
    assert len(titles) == 2


# --- consumer 2: consolidate_deterministic() -------------------------------


def test_deterministic_ingest_matches_near_cert(db_session, no_llm):
    consolidate_deterministic(
        db_session, [("a", _resume(certifications=["AWS Certified AI Practitioner"]))]
    )
    assert len(_certs(db_session)) == 1

    report = consolidate_deterministic(
        db_session,
        [("b", _resume(certifications=["AWS Certified AI Practitioner (AIF-C01)"]))],
    )
    assert len(_certs(db_session)) == 1
    assert [e.created for e in report.entities] == [False]


def test_deterministic_experience_near_hit_upgrades_to_richer_title(db_session, no_llm):
    ent = _exp_entity(db_session, title="Data Analyst")
    report = consolidate_deterministic(
        db_session,
        [("a", _resume(experience=[{
            "company": "TCS", "role": "Data Analyst, British Airways Account",
            "start_date": "2022-07", "bullets": ["Built the reporting pipeline"],
        }]))],
    )
    db_session.refresh(ent)
    assert ent.title == "Data Analyst, British Airways Account"
    assert len(db_session.scalars(select(KBEntity).where(KBEntity.kind == "experience")).all()) == 1
    # Renaming an entity the user already has is not something ingest may do
    # silently — the report names it, same principle as sync's `renamed`.
    assert report.titles_upgraded == ["Data Analyst, British Airways Account"]


def test_deterministic_never_renames_on_poorer_variant(db_session, no_llm):
    ent = _exp_entity(db_session, title="Data Analyst, British Airways Account")
    report = consolidate_deterministic(
        db_session,
        [("a", _resume(experience=[{
            "company": "TCS", "role": "Data Analyst", "start_date": "2022-07",
            "bullets": ["Built the reporting pipeline"],
        }]))],
    )
    db_session.refresh(ent)
    assert ent.title == "Data Analyst, British Airways Account"
    assert len(db_session.scalars(select(KBEntity).where(KBEntity.kind == "experience")).all()) == 1
    assert report.titles_upgraded == []


def test_two_incoming_siblings_converge_on_one_entity_and_rename_once(
    db_session, no_llm
):
    """The ambiguity gate is one-directional; this pins what that means live.

    The gate refuses when many CANDIDATES match one incoming entry. Two
    incoming engagements that both near-hit the SAME stored entity is the
    mirror case and is not refused — both land on it. The first in group order
    wins the rename, and the re-verification inside `upgrade_experience_title`
    is what stops the second from thrashing the title back and forth.
    """
    ent = _exp_entity(db_session, title="Data Analyst")
    report = consolidate_deterministic(
        db_session,
        [("a", _resume(experience=[
            {"company": "TCS", "role": "Data Analyst, British Airways Account",
             "start_date": "2022-07", "bullets": ["Built the reporting pipeline"]},
            {"company": "TCS", "role": "Data Analyst, Retail Account",
             "start_date": "2022-07", "bullets": ["Owned the retail dashboards"]},
        ]))],
    )
    exps = db_session.scalars(select(KBEntity).where(KBEntity.kind == "experience")).all()
    assert len(exps) == 1
    db_session.refresh(ent)
    assert ent.title == "Data Analyst, British Airways Account"  # first seen wins
    assert report.titles_upgraded == ["Data Analyst, British Airways Account"]
    assert len(db_session.scalars(select(KBPoint)).all()) == 2


def test_deterministic_ingest_matches_near_project(db_session, no_llm):
    """Projects reach the matcher too — and the section string is load-bearing.

    ``find_near_identity`` is keyed by SOURCE section ("projects"), while the
    entity kind is "project". Passing the kind at the call site silently
    disables near matching for the whole section, with no error anywhere; this
    test is what notices.
    """
    consolidate_deterministic(
        db_session, [("a", _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}]))]
    )
    report = consolidate_deterministic(
        db_session,
        [("b", _resume(projects=[
            {"name": "Orbit Telemetry Dashboard", "bullets": ["Shipped the dashboard"]}
        ]))],
    )
    projects = db_session.scalars(select(KBEntity).where(KBEntity.kind == "project")).all()
    assert len(projects) == 1
    assert [e.created for e in report.entities] == [False]
    # A project near-hit never renames: the name is the only signal it has.
    assert projects[0].title == "Orbit"
    assert report.titles_upgraded == []


def test_dateless_experience_forks(db_session, no_llm):
    _exp_entity(db_session, title="Data Analyst, British Airways Account", start="")
    consolidate_deterministic(
        db_session,
        [("a", _resume(experience=[{
            "company": "TCS", "role": "Data Analyst", "start_date": "",
            "bullets": ["Built the reporting pipeline"],
        }]))],
    )
    exps = db_session.scalars(select(KBEntity).where(KBEntity.kind == "experience")).all()
    assert len(exps) == 2


# --- consumer 3: base sync classify (read-only) + apply (writes) -----------


def test_sync_classify_matches_near_experience_entity(db_session, tmp_path, monkeypatch):
    ent = _exp_entity(db_session, title="Data Analyst")
    data = _resume(experience=[{
        "company": "TCS", "role": "Data Analyst, British Airways Account",
        "start_date": "2022-07", "bullets": ["Built the reporting pipeline"],
    }])
    _seed_base(db_session, tmp_path, monkeypatch, data)

    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "experience"]
    assert len(items) == 1
    assert items[0].entity_id == ent.id
    assert items[0].entity_proposal is None
    assert items[0].tier == "new"
    # classify is read-only: no rename before apply()
    db_session.refresh(ent)
    assert ent.title == "Data Analyst"


def test_sync_classify_flips_near_cert_to_in_sync(db_session, tmp_path, monkeypatch):
    """A re-imported cert that grew an exam code is in_sync, not a proposal.

    Certs classify on identity-key presence alone (`_classify_identity_only`),
    so without the near-match fallback in `classify` this base would report a
    brand-new certification and offer to create a second entity for it.
    """
    cert = KBEntity(
        kind="certification", title="AWS Certified AI Practitioner", status="completed"
    )
    db_session.add(cert)
    db_session.flush()
    data = _resume(certifications=["AWS Certified AI Practitioner (AIF-C01)"])
    _seed_base(db_session, tmp_path, monkeypatch, data)

    report = kb_base_sync.classify(db_session, "hybrid")
    items = [i for i in report["items"] if i.section == "certifications"]
    assert len(items) == 1
    assert items[0].tier == "in_sync"
    assert items[0].entity_id == cert.id
    assert items[0].entity_proposal is None
    # A cert near-hit never renames, on any path.
    db_session.refresh(cert)
    assert cert.title == "AWS Certified AI Practitioner"


def test_sync_apply_upgrades_title_to_richer_variant(db_session, tmp_path, monkeypatch):
    ent = _exp_entity(db_session, title="Data Analyst")
    data = _resume(experience=[{
        "company": "TCS", "role": "Data Analyst, British Airways Account",
        "start_date": "2022-07", "bullets": ["Built the reporting pipeline"],
    }])
    _seed_base(db_session, tmp_path, monkeypatch, data)

    out = kb_base_sync.apply(db_session, "hybrid")
    assert out["created"] == 1
    db_session.refresh(ent)
    assert ent.title == "Data Analyst, British Airways Account"
    assert len(db_session.scalars(select(KBEntity).where(KBEntity.kind == "experience")).all()) == 1
    pts = db_session.scalars(select(KBPoint)).all()
    assert [p.entity_id for p in pts] == [ent.id]


def test_sync_apply_never_renames_on_poorer_variant(db_session, tmp_path, monkeypatch):
    ent = _exp_entity(db_session, title="Data Analyst, British Airways Account")
    data = _resume(experience=[{
        "company": "TCS", "role": "Data Analyst", "start_date": "2022-07",
        "bullets": ["Built the reporting pipeline"],
    }])
    _seed_base(db_session, tmp_path, monkeypatch, data)

    kb_base_sync.apply(db_session, "hybrid")
    db_session.refresh(ent)
    assert ent.title == "Data Analyst, British Airways Account"
