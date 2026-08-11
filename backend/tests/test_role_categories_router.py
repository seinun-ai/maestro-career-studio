"""The HTTP surface of the role vocabulary.

Two things are load-bearing here and neither is obvious from the handlers. The
catalog response is ADDITIVE because `RoleCategoryPicker` sets the base-resume
role, which must stay coarse. And `/match` distinguishes `exact` from `alias`
by whose words come back in `label` — the catalog's or the user's — which is
what tells the picker whether to ask for confirmation.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.schemas.job_preferences import MAX_LABEL_CHARS


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_catalog_is_additive_for_existing_consumers(client):
    # RoleCategoryPicker (base resumes) reads key/label/reserved and must keep
    # seeing ONLY storable categories. `roles` rides along for the new picker.
    body = client.get("/api/role-categories").json()
    keys = [row["key"] for row in body]
    assert "data_scientist" in keys
    assert "product_data_scientist" not in keys
    # Both reserved entries carry `roles: []`, never null — so Task 5's TS type
    # needs no optionality and no null-guard at every use site.
    assert body[-2] == {"key": "other", "label": "Other", "reserved": True, "roles": []}
    assert body[-1] == {"key": "unknown", "label": "Unknown", "reserved": True, "roles": []}


def test_catalog_nests_roles(client):
    body = client.get("/api/role-categories").json()
    ds = next(row for row in body if row["key"] == "data_scientist")
    assert {"key": "decision_scientist", "label": "Decision Scientist"} in ds["roles"]


def test_match_endpoint(client):
    body = client.get("/api/role-categories/match", params={"q": "Quant"}).json()
    assert body["category"] == "research_scientist"
    assert body["confidence"] == "alias"


def test_match_endpoint_on_novel_text(client):
    # A miss is a successful answer, not an error: 200 with confidence "none".
    # A 4xx here would push the client toward inventing a mapping.
    response = client.get("/api/role-categories/match", params={"q": "Sommelier"})
    assert response.status_code == 200
    assert response.json() == {
        "role": None, "category": None, "label": "Sommelier", "confidence": "none",
    }


def test_match_endpoint_rejects_an_overlong_query(client):
    # Bounded at the SAME constant the preference label is capped at. A custom
    # role's label is exactly this text, and that schema rejects over-cap rather
    # than truncating — so a looser bound here would return 200 for text that
    # cannot then be saved.
    assert client.get(
        "/api/role-categories/match", params={"q": "x" * MAX_LABEL_CHARS}
    ).status_code == 200
    assert client.get(
        "/api/role-categories/match", params={"q": "x" * (MAX_LABEL_CHARS + 1)}
    ).status_code == 422


@pytest.mark.parametrize(
    "typed,role,category",
    [
        ("Data Scientist", "data_scientist", "data_scientist"),
        ("Product Data Scientist", "product_data_scientist", "data_scientist"),
    ],
)
def test_match_endpoint_on_an_exact_hit(client, typed, role, category):
    # The `exact` tier is the common path AND the only one where `label` is the
    # CATALOG's wording rather than the user's. The picker reads that difference
    # to decide whether to show the "Count X as Y?" confirmation row, so both a
    # coarse key and a specific role key need pinning here.
    body = client.get("/api/role-categories/match", params={"q": typed}).json()
    assert body == {
        "role": role, "category": category, "label": typed, "confidence": "exact",
    }


def test_match_endpoint_on_absent_or_blank_input(client):
    # `q` is optional, so a mis-spelled param name yields a plausible "no match"
    # rather than an error. Pinned because a silently-wrong answer is the exact
    # failure mode this endpoint exists to avoid.
    blank = {"role": None, "category": None, "label": "", "confidence": "none"}
    assert client.get("/api/role-categories/match").json() == blank
    assert client.get("/api/role-categories/match", params={"q": "   "}).json() == blank


def test_match_endpoint_keeps_the_role_on_an_alias_hit(client):
    # `cv engineer` is an alias declared FOR computer_vision_engineer, so the
    # suggestion must name that role and not just its coarse parent — otherwise
    # the picker offers "AI/ML Engineer" for a term that names a specific job.
    body = client.get("/api/role-categories/match", params={"q": "cv engineer"}).json()
    assert body["role"] == "computer_vision_engineer"
    assert body["category"] == "ai_ml_engineer"
    assert body["label"] == "cv engineer"
