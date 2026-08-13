import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.job_preferences import FavoredRole, JobPreferences
from app.services import job_preferences


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_empty_preferences_are_valid_and_not_set():
    prefs = JobPreferences()
    assert prefs.role_categories == []
    assert not job_preferences.is_set(prefs)


def test_years_experience_bounds():
    assert JobPreferences(years_experience=6).years_experience == 6
    with pytest.raises(ValidationError):
        JobPreferences(years_experience=-1)
    with pytest.raises(ValidationError):
        JobPreferences(years_experience=61)


def test_stored_levels_key_is_ignored_not_fatal(db_session):
    from app.services import text_settings

    text_settings.set_text(
        job_preferences.JOB_PREFERENCES_KEY,
        job_preferences.JOB_PREFERENCES_FILE,
        '{"role_categories": ["data_scientist"], "levels": ["senior"]}',
        db_session,
    )
    prefs = job_preferences.get_preferences(db_session)
    assert prefs.role_categories == ["data_scientist"]
    assert not hasattr(prefs, "levels")


def test_unknown_role_category_is_rejected_never_normalized():
    # "Data Science" is an ALIAS that normalize() would accept — a typed PUT
    # must reject it: human input is validated, never coerced.
    with pytest.raises(ValidationError):
        JobPreferences(role_categories=["Data Science"])
    with pytest.raises(ValidationError):
        JobPreferences(role_categories=["definitely_not_a_role"])


def test_declared_and_reserved_keys_are_accepted():
    prefs = JobPreferences(role_categories=["data_scientist", "other"])
    assert job_preferences.is_set(prefs)


def test_round_trip_through_setting(db_session):
    saved = job_preferences.set_preferences(
        JobPreferences(role_categories=["data_engineer"], remote="remote"), db_session
    )
    assert saved.remote == "remote"
    loaded = job_preferences.get_preferences(db_session)
    assert loaded.role_categories == ["data_engineer"]
    assert loaded.remote == "remote"


def test_corrupt_stored_json_reads_as_defaults(db_session):
    from app.services import text_settings

    text_settings.set_text(
        job_preferences.JOB_PREFERENCES_KEY,
        job_preferences.JOB_PREFERENCES_FILE,
        "not json{",
        db_session,
    )
    assert job_preferences.get_preferences(db_session) == JobPreferences()


def test_get_returns_defaults_then_put_round_trips(client):
    r = client.get("/api/settings/job-preferences")
    assert r.status_code == 200
    assert r.json()["value"]["role_categories"] == []

    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"role_categories": ["ai_ml_engineer"], "remote": "hybrid"}},
    )
    assert r.status_code == 200
    assert client.get("/api/settings/job-preferences").json()["value"]["remote"] == "hybrid"


def test_put_bad_role_key_is_422(client):
    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"role_categories": ["nope_not_real"]}},
    )
    assert r.status_code == 422


def test_put_favored_roles_returns_the_projection(client):
    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"favored_roles": [
            {"role": "product_data_scientist"},
            {"label": "Quant Researcher"},
        ]}},
    )
    assert r.status_code == 200
    value = client.get("/api/settings/job-preferences").json()["value"]
    assert value["role_categories"] == ["data_scientist"]
    assert [f["label"] for f in value["favored_roles"]] == [
        "Product Data Scientist", "Quant Researcher",
    ]


def test_put_bad_favored_role_is_422(client):
    r = client.put(
        "/api/settings/job-preferences",
        json={"value": {"favored_roles": [{"role": "nope_not_real"}]}},
    )
    assert r.status_code == 422


def test_specific_role_projects_to_its_coarse_category():
    prefs = JobPreferences(favored_roles=[FavoredRole(role="product_data_scientist")])
    assert prefs.role_categories == ["data_scientist"]
    assert prefs.favored_roles[0].category == "data_scientist"


def test_a_catalog_label_is_derived_not_trusted():
    # The catalog owns display names. A client-supplied label for a catalog role
    # is overwritten, so editing the YAML can never leave a stale copy behind.
    prefs = JobPreferences(
        favored_roles=[FavoredRole(role="llmops_engineer", label="whatever the client sent")]
    )
    assert prefs.favored_roles[0].label == "LLMOps Engineer"


def test_legacy_role_categories_only_payload_upgrades():
    prefs = JobPreferences(role_categories=["data_engineer", "other"])
    assert [f.role for f in prefs.favored_roles] == ["data_engineer", "other"]
    assert prefs.role_categories == ["data_engineer", "other"]
    # Reserved keys are catalog keys too, so the upgrade must label them.
    assert [f.label for f in prefs.favored_roles] == ["Data Engineer", "Other"]


def test_a_stale_role_categories_alongside_favored_roles_is_recomputed():
    # Autosave can PUT back a `role_categories` the client computed before its
    # last edit. It is a projection, so whatever arrives is discarded.
    prefs = JobPreferences(
        favored_roles=[FavoredRole(role="data_engineer")],
        role_categories=["data_scientist", "other"],
    )
    assert prefs.role_categories == ["data_engineer"]


def test_custom_role_may_stay_unmapped():
    prefs = JobPreferences(favored_roles=[FavoredRole(label="Underwater Basket Weaver")])
    assert prefs.favored_roles[0].role is None
    assert prefs.role_categories == []
    # No projected category, but the user has answered the question — the
    # setup-status step must not read as untouched.
    assert job_preferences.is_set(prefs)


def test_custom_role_may_be_mapped_by_the_user():
    prefs = JobPreferences(
        favored_roles=[FavoredRole(label="Quant Researcher", category="research_scientist")]
    )
    assert prefs.role_categories == ["research_scientist"]


def test_custom_role_label_is_trimmed_and_collapsed():
    role = FavoredRole(label="  Quant   Researcher \n")
    assert role.label == "Quant Researcher"


def test_unknown_role_is_rejected():
    with pytest.raises(ValidationError):
        JobPreferences(favored_roles=[FavoredRole(role="not_a_role", label="Nope")])


def test_unknown_category_on_a_custom_role_is_rejected():
    with pytest.raises(ValidationError):
        FavoredRole(label="Quant Researcher", category="Data Science")


def test_contradicting_category_is_rejected_not_corrected():
    with pytest.raises(ValidationError):
        JobPreferences(favored_roles=[
            FavoredRole(role="product_data_scientist", category="software_engineer")
        ])


def test_a_custom_role_needs_words():
    with pytest.raises(ValidationError):
        FavoredRole(label="   ")
    with pytest.raises(ValidationError):
        FavoredRole(label="x" * 81)


def test_duplicates_collapse_case_insensitively():
    prefs = JobPreferences(favored_roles=[
        FavoredRole(label="Quant Researcher"),
        FavoredRole(label="quant researcher"),
        FavoredRole(role="data_scientist"),
        FavoredRole(role="data_scientist"),
    ])
    assert len(prefs.favored_roles) == 2


def test_the_list_is_capped():
    with pytest.raises(ValidationError):
        JobPreferences(favored_roles=[FavoredRole(label=f"Role {i}") for i in range(26)])


def test_the_cap_counts_what_survives_dedupe():
    # A cap is a real limit; dedupe is cleanup. Twenty-six entries that collapse
    # to one must save, or an autosave duplicate could strand the whole edit.
    prefs = JobPreferences(favored_roles=[FavoredRole(role="data_scientist")] * 26)
    assert len(prefs.favored_roles) == 1


def test_projection_dedupes_categories_in_first_seen_order():
    prefs = JobPreferences(favored_roles=[
        FavoredRole(role="deep_learning_engineer"),
        FavoredRole(role="data_scientist"),
        FavoredRole(role="generative_ai_engineer"),
    ])
    assert prefs.role_categories == ["ai_ml_engineer", "data_scientist"]


def test_favored_roles_round_trip_through_the_file_mirror(db_session):
    job_preferences.set_preferences(
        JobPreferences(favored_roles=[
            FavoredRole(role="product_data_scientist"),
            FavoredRole(label="Quant Researcher", category="research_scientist"),
            FavoredRole(label="Underwater Basket Weaver"),
        ]),
        db_session,
    )
    loaded = job_preferences.get_preferences(db_session)
    assert [(f.role, f.label, f.category) for f in loaded.favored_roles] == [
        ("product_data_scientist", "Product Data Scientist", "data_scientist"),
        (None, "Quant Researcher", "research_scientist"),
        (None, "Underwater Basket Weaver", None),
    ]
    assert loaded.role_categories == ["data_scientist", "research_scientist"]


def test_stale_stored_favored_role_degrades_per_item_without_blanket_data_loss(
    db_session,
):
    from app.services import text_settings

    text_settings.set_text(
        job_preferences.JOB_PREFERENCES_KEY,
        job_preferences.JOB_PREFERENCES_FILE,
        """{
          "favored_roles": [
            {"role": "retired_role", "label": "Legacy Data Wizard", "category": "retired_family"},
            {"role": "data_engineer", "label": "Stale Client Label", "category": "data_engineer"}
          ],
          "role_categories": ["retired_family", "data_engineer"],
          "years_experience": 9,
          "employment_types": ["full_time"],
          "locations": ["Chicago", "Remote"],
          "remote": "hybrid",
          "min_salary": "150000",
          "notes": "Keep every unrelated preference."
        }""",
        db_session,
    )

    prefs = job_preferences.get_preferences(db_session)

    assert [(role.role, role.label, role.category) for role in prefs.favored_roles] == [
        (None, "Legacy Data Wizard", None),
        ("data_engineer", "Data Engineer", "data_engineer"),
    ]
    assert prefs.role_categories == ["data_engineer"]
    assert prefs.years_experience == 9
    assert prefs.employment_types == ["full_time"]
    assert prefs.locations == ["Chicago", "Remote"]
    assert prefs.remote == "hybrid"
    assert prefs.min_salary == "150000"
    assert prefs.notes == "Keep every unrelated preference."
