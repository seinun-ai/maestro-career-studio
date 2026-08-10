import uuid

from app.models.career_kb import KBEntity, KBPoint, KBProfile
from app.services import kb_resolver


RESUME = {
    "projects": [
        {
            "name": "Ingestion Pipeline",
            "enabled": False,
            "bullets": ["Streamed events with Apache Kafka into S3"],
            "tech": ["Kafka", "Spark"],
        },
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model"],
            "tech": [],
        },
    ],
    "experience": [],
    "skills": [{"category": "Data & ETL", "items": ["SQL"]}],
}

KB = {
    "profile_skills": ["Airflow", "Kafka"],
    "entities": [
        {
            "id": "e1",
            "kind": "project",
            "title": "Churn Model",
            "status": "completed",
            "tech": ["MLflow"],
            "points": [
                {"id": "p1", "state": "approved", "text": "Tracked runs in MLflow"},
                {"id": "p2", "state": "draft", "text": "Deployed with Docker"},
            ],
        }
    ],
}


def test_verified_disabled_entry_proposal_is_auto():
    proposal = {"kind": "disabled", "section": "projects", "index": 0}

    out = kb_resolver.verify_candidate(proposal, KB, RESUME, "Kafka")

    assert out["auto"] is True
    assert out["match_form"] in ("exact", "alias")
    assert out["evidence_snippet"] == "Streamed events with Apache Kafka into S3"


def test_verified_approved_point_on_enabled_entry_is_auto_port():
    proposal = {
        "kind": "kb_point",
        "point_id": "p1",
        "entity_id": "e1",
        "placement_target": {"section": "projects", "index_or_category": 1},
    }

    out = kb_resolver.verify_candidate(proposal, KB, RESUME, "MLflow")

    assert out["auto"] is True
    assert out["point_id"] == "p1"


def test_draft_point_demotes_to_suggestion():
    proposal = {
        "kind": "kb_point",
        "point_id": "p2",
        "entity_id": "e1",
        "placement_target": None,
    }

    out = kb_resolver.verify_candidate(proposal, KB, RESUME, "Docker")

    assert out["auto"] is False


def test_no_literal_containment_demotes_to_suggestion():
    proposal = {
        "kind": "kb_point",
        "point_id": "p1",
        "entity_id": "e1",
        "placement_target": {"section": "projects", "index_or_category": 1},
    }

    out = kb_resolver.verify_candidate(proposal, KB, RESUME, "experiment tracking")

    assert out["auto"] is False
    assert out["match_form"] == "semantic"


def test_hallucinated_point_id_is_dropped():
    proposal = {
        "kind": "kb_point",
        "point_id": "p999",
        "entity_id": "e1",
        "placement_target": None,
    }

    assert kb_resolver.verify_candidate(proposal, KB, RESUME, "MLflow") is None


def test_invalid_target_demotes_to_suggestion():
    proposal = {
        "kind": "kb_point",
        "point_id": "p1",
        "entity_id": "e1",
        "placement_target": {"section": "projects", "index_or_category": 99},
    }

    out = kb_resolver.verify_candidate(proposal, KB, RESUME, "MLflow")

    assert out["auto"] is False
    assert out["placement_target"] is None


def test_verified_profile_skill_is_auto():
    out = kb_resolver.verify_candidate({"kind": "profile"}, KB, RESUME, "Airflow")

    assert out == {"kind": "profile", "match_form": "exact", "auto": True}
    assert kb_resolver.verify_candidate({"kind": "profile"}, KB, RESUME, "Terraform") is None


def test_auto_resolution_prefers_disabled_then_port_then_profile():
    gap = {
        "gap_id": "skill:kafka",
        "jd_skill": "Kafka",
        "enrichment": {
            "suggested_placement": {
                "section": "skills",
                "index_or_category": "Data & ETL",
            }
        },
        "library_candidates": [
            {"kind": "profile", "match_form": "exact", "auto": True},
            {
                "kind": "kb_point",
                "entity_id": "e1",
                "point_id": "p1",
                "evidence_snippet": "Tracked runs in MLflow",
                "placement_target": {"section": "projects", "index_or_category": 1},
                "match_form": "exact",
                "auto": True,
            },
            {
                "kind": "disabled",
                "section": "projects",
                "index": 0,
                "name": "Ingestion Pipeline",
                "evidence_snippet": "Streamed events with Apache Kafka into S3",
                "match_form": "exact",
                "auto": True,
            },
        ],
    }

    resolution = kb_resolver.auto_resolution_for_gap(gap)

    assert resolution == {
        "gap_id": "skill:kafka",
        "action": "enable_entry",
        "payload": {
            "section": "projects",
            "index": 0,
            "name": "Ingestion Pipeline",
            "provenance": {"source": "library_auto"},
        },
    }


def test_auto_resolution_builds_port_and_profile_payloads():
    port_gap = {
        "gap_id": "skill:mlflow",
        "library_candidates": [
            {
                "kind": "kb_point",
                "entity_id": "e1",
                "point_id": "p1",
                "evidence_snippet": "Tracked runs in MLflow",
                "placement_target": {"section": "projects", "index_or_category": 1},
                "auto": True,
            }
        ],
    }
    profile_gap = {
        "gap_id": "skill:airflow",
        "jd_skill": "Airflow",
        "enrichment": {
            "suggested_placement": {
                "section": "skills",
                "index_or_category": "Data & ETL",
            }
        },
        "library_candidates": [{"kind": "profile", "auto": True}],
    }

    assert kb_resolver.auto_resolution_for_gap(port_gap) == {
        "gap_id": "skill:mlflow",
        "action": "port_kb_point",
        "payload": {
            "kb_point_id": "p1",
            "kb_entity_id": "e1",
            "placement_target": {"section": "projects", "index_or_category": 1},
            "wording": "Tracked runs in MLflow",
            "provenance": {
                "source": "kb_auto",
                "kb_point_id": "p1",
                "kb_entity_id": "e1",
            },
        },
    }
    assert kb_resolver.auto_resolution_for_gap(profile_gap) == {
        "gap_id": "skill:airflow",
        "action": "add_keyword",
        "payload": {
            "placement_target": {
                "section": "skills",
                "index_or_category": "Data & ETL",
            },
            "wording": "Airflow",
            "provenance": {"source": "kb_profile"},
        },
    }


def test_mirror_wording_gap_auto_adds_exact_token_to_skills():
    gap = {
        "gap_id": "skill:tensorflow",
        "jd_skill": "TensorFlow",
        "actions": ["add_keyword", "skip"],
        "diagnostic": {"fix_hint": "mirror_wording"},
        "enrichment": {
            "suggested_placement": {
                "section": "skills",
                "index_or_category": "ML & Modeling",
            }
        },
    }

    assert kb_resolver.auto_resolution_for_gap(gap) == {
        "gap_id": "skill:tensorflow",
        "action": "add_keyword",
        "payload": {
            "placement_target": {
                "section": "skills",
                "index_or_category": "ML & Modeling",
            },
            "wording": "TensorFlow",
            "provenance": {"source": "wording_auto"},
        },
    }


def test_wording_auto_falls_back_to_additional_skills_without_enrichment():
    gap = {
        "gap_id": "skill:rag",
        "jd_skill": "RAG",
        "actions": ["add_keyword", "skip"],
        "diagnostic": {"fix_hint": "mirror_wording"},
        "enrichment": None,
    }

    resolution = kb_resolver.auto_resolution_for_gap(gap)

    assert resolution["payload"]["placement_target"] == {
        "section": "skills",
        "index_or_category": "Additional Skills",
    }
    assert resolution["payload"]["provenance"] == {"source": "wording_auto"}


def test_wording_auto_not_extended_to_absent_or_dual_place():
    # absent = the honesty rule's territory (user consent required); dual_place =
    # the token is already in skills, its fix is prose corroboration.
    for hint in ("absent", "dual_place", "resurface_recent", None):
        gap = {
            "gap_id": "skill:x",
            "jd_skill": "X",
            "actions": ["add_keyword", "skip"],
            "diagnostic": {"fix_hint": hint},
        }
        assert kb_resolver.auto_resolution_for_gap(gap) is None


def test_library_auto_outranks_wording_fallback():
    gap = {
        "gap_id": "skill:kafka",
        "jd_skill": "Kafka",
        "actions": ["add_keyword", "skip"],
        "diagnostic": {"fix_hint": "mirror_wording"},
        "library_candidates": [
            {
                "kind": "disabled",
                "section": "projects",
                "index": 0,
                "name": "Ingestion Pipeline",
                "auto": True,
            }
        ],
    }

    assert kb_resolver.auto_resolution_for_gap(gap)["action"] == "enable_entry"


def test_load_kb_snapshot_filters_archived_entities_and_retired_points(db_session):
    live_entity = KBEntity(
        id=uuid.uuid4(),
        kind="project",
        title="Churn Model",
        status="completed",
        detail_json={"tech": ["MLflow"]},
    )
    archived_entity = KBEntity(
        id=uuid.uuid4(),
        kind="project",
        title="Old Project",
        status="archived",
        detail_json={"tech": ["COBOL"]},
    )
    approved = KBPoint(
        id=uuid.uuid4(),
        entity_id=live_entity.id,
        text="Tracked runs in MLflow",
        state="approved",
        origin="manual",
    )
    retired = KBPoint(
        id=uuid.uuid4(),
        entity_id=live_entity.id,
        text="Retired fact",
        state="retired",
        origin="manual",
    )
    db_session.add_all(
        [
            KBProfile(
                id=1,
                skills_json=[{"category": "Data & ETL", "items": ["Airflow", "Kafka"]}],
            ),
            live_entity,
            archived_entity,
            approved,
            retired,
        ]
    )
    db_session.flush()

    snapshot = kb_resolver.load_kb_snapshot(db_session)

    assert snapshot["profile_skills"] == ["Airflow", "Kafka"]
    assert [entity["id"] for entity in snapshot["entities"]] == [str(live_entity.id)]
    assert snapshot["entities"][0]["tech"] == ["MLflow"]
    assert snapshot["entities"][0]["points"] == [
        {"id": str(approved.id), "state": "approved", "text": "Tracked runs in MLflow"}
    ]
