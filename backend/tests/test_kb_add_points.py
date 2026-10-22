"""Bullets a connected agent wrote, added to a Career KB entity as DRAFTS.

POST /api/kb/entities/{id}/drafts (MCP `kb_add_points`) is kb_capture with an
entity id and no model: the points wait for the user's approval, the dash scrub
and the resume voice rule (§6 inv-em-dash, inv-resume-voice) hold at store time,
and a bullet the entity already has is skipped.
"""

import pytest
from sqlalchemy import select

from app.models.career_kb import KBEntity, KBPoint, KBProfile
from app.services import kb_ingest

MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "Claude"}


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    def refuse(**kwargs):
        raise AssertionError("adding drafts must not call the model")

    monkeypatch.setattr(kb_ingest.llm, "call_openai", refuse)


@pytest.fixture
def entity(db_session):
    db_session.add(KBProfile(id=1, contact_json={"name": "Jane Doe", "email": "jane@example.com"}))
    row = KBEntity(kind="experience", title="Data Analyst", org="Acme")
    db_session.add(row)
    db_session.flush()
    db_session.add(KBPoint(entity_id=row.id, text="Built the KPI dashboard", state="retired", origin="ingested"))
    db_session.commit()
    return row


def _points(db_session, entity) -> list[KBPoint]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(KBPoint).where(KBPoint.entity_id == entity.id).order_by(KBPoint.created_at)
        )
    )


def test_bullets_land_as_drafts_from_the_agent_and_repeats_are_skipped(db_session, entity, client):
    response = client.post(
        f"/api/kb/entities/{entity.id}/drafts",
        json={
            "points": [
                "Cut report time 40% — from 5 days to 3",
                "  built the KPI   dashboard ",
                "Ran the 2021–2023 forecasting cycle",
                "cut report time 40% \u2014 from 5 days to 3",
            ]
        },
        headers=MCP,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entity_id"] == str(entity.id)
    assert body["entity_title"] == "Data Analyst"
    assert body["skipped"] == ["built the KPI   dashboard", "cut report time 40%, from 5 days to 3"]
    new = [p for p in _points(db_session, entity) if str(p.id) in body["point_ids"]]
    assert [p.text for p in new] == [
        "Cut report time 40%, from 5 days to 3",
        "Ran the 2021-2023 forecasting cycle",
    ]
    assert {(p.state, p.origin, p.origin_detail, p.provenance) for p in new} == {
        ("draft", "mcp", "Claude", "user_stated")
    }

    again = client.post(
        f"/api/kb/entities/{entity.id}/drafts",
        json={"points": ["Ran the 2021–2023 forecasting cycle"]},
        headers=MCP,
    )
    assert again.json()["point_ids"] == []
    assert len(_points(db_session, entity)) == 3


@pytest.mark.parametrize(
    "line",
    ["He led the migration to dbt", "I led the migration to dbt", "Jane Doe led the migration to dbt"],
)
def test_a_bullet_about_someone_else_is_a_400_that_stores_nothing(db_session, entity, client, line):
    response = client.post(
        f"/api/kb/entities/{entity.id}/drafts",
        json={"points": ["Shipped the churn model", line]},
    )
    assert response.status_code == 400
    assert line in response.json()["detail"]
    assert len(_points(db_session, entity)) == 1


def test_an_unknown_entity_is_a_404_and_an_empty_list_a_422(db_session, entity, client):
    missing = client.post(
        "/api/kb/entities/00000000-0000-4000-8000-000000000000/drafts",
        json={"points": ["Shipped the churn model"]},
    )
    assert missing.status_code == 404
    assert client.post(f"/api/kb/entities/{entity.id}/drafts", json={"points": []}).status_code == 422
    assert client.post(f"/api/kb/entities/{entity.id}/drafts", json={"points": [" "]}).status_code == 422
