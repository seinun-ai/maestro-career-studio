"""Coherence lint (design §4.4): read-only, best-effort, defensively coerced."""

from app.services import coherence_check

_BASE = {
    "summary": "Data engineer.",
    "skills": [{"category": "Data & ETL", "items": ["SQL"]}],
    "experience": [],
    "projects": [
        {"name": "Churn Model", "enabled": True, "bullets": ["Trained XGBoost model"]},
    ],
}

_CUSTOMIZED = {
    "summary": "Data engineer.",
    "skills": [{"category": "Data & ETL", "items": ["SQL", "Airflow"]}],
    "experience": [],
    "projects": [
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model", "Tracked runs in MLflow"],
        },
    ],
}

_VALID_FLAG = {
    "locus": {
        "kind": "bullet_added",
        "section": "projects",
        "index": 0,
        "after": "Tracked runs in MLflow",
    },
    "issue": "fragment",
    "proposal": "Tracked training runs in MLflow with versioned metrics",
}


def _patch_llm(monkeypatch, response):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(coherence_check.llm, "call_openai", fake)
    monkeypatch.setattr(
        coherence_check.model_settings, "get_fast_model", lambda session=None: "fast"
    )
    return calls


def test_valid_flags_pass_through_and_junk_is_dropped(db_session, monkeypatch):
    _patch_llm(
        monkeypatch,
        {
            "flags": [
                _VALID_FLAG,
                {"locus": "not a dict", "issue": "fragment", "proposal": "x"},
                {"locus": {}, "issue": "not_an_issue", "proposal": "x"},
                {"locus": {}, "issue": "tense", "proposal": "   "},
                "not a dict",
            ]
        },
    )
    out = coherence_check.run(_BASE, _CUSTOMIZED, db_session)
    assert out == {"flags": [_VALID_FLAG]}


def test_llm_failure_degrades_to_no_flags(db_session, monkeypatch):
    _patch_llm(monkeypatch, RuntimeError("model down"))
    assert coherence_check.run(_BASE, _CUSTOMIZED, db_session) == {"flags": []}


def test_malformed_response_degrades_to_no_flags(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": {"not": "a list"}})
    assert coherence_check.run(_BASE, _CUSTOMIZED, db_session) == {"flags": []}


def test_no_changed_loci_skips_the_llm_entirely(db_session, monkeypatch):
    calls = _patch_llm(monkeypatch, {"flags": [_VALID_FLAG]})
    assert coherence_check.run(_BASE, _BASE, db_session) == {"flags": []}
    assert calls == []


def test_missing_after_is_backfilled_from_the_diff_hunk(db_session, monkeypatch):
    # Model echoes kind/section/index but drops `after` (observed live) —
    # the needle must come back deterministically from the diff.
    flag_without_after = {
        "locus": {"kind": "bullet_added", "section": "projects", "index": 0},
        "issue": "fragment",
        "proposal": "Tracked training runs in MLflow with versioned metrics",
    }
    _patch_llm(monkeypatch, {"flags": [flag_without_after]})
    out = coherence_check.run(_BASE, _CUSTOMIZED, db_session)
    assert out["flags"][0]["locus"]["after"] == "Tracked runs in MLflow"
