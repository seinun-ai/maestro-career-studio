"""Coherence lint (design §4.4, 2026-08-12): flags + hygiene + gates.

Read-only, best-effort, defensively coerced. `flags` tests stub `llm.call_openai`
and `model_settings.get_fast_model`; hygiene/gates tests stub `structure_gates`
(via an autouse fixture) so no test needs a real template render or the network.
"""
from copy import deepcopy

import pytest

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


@pytest.fixture(autouse=True)
def _no_real_gates(monkeypatch):
    """Every test gets cheap, deterministic structure_gates unless it overrides
    this itself — a real call would need a certified template + PDF render."""
    monkeypatch.setattr(coherence_check.resume_lint, "structure_gates", lambda *a, **k: [])


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


# --------------------------------------------------------------------------- #
# flags (LLM half) — regression guard: shape/behavior unchanged by this round.

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
    assert out["flags"] == [_VALID_FLAG]


def test_llm_failure_degrades_to_no_flags(db_session, monkeypatch):
    _patch_llm(monkeypatch, RuntimeError("model down"))
    assert coherence_check.run(_BASE, _CUSTOMIZED, db_session)["flags"] == []


def test_malformed_response_degrades_to_no_flags(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": {"not": "a list"}})
    assert coherence_check.run(_BASE, _CUSTOMIZED, db_session)["flags"] == []


def test_no_changed_loci_skips_the_llm_entirely(db_session, monkeypatch):
    calls = _patch_llm(monkeypatch, {"flags": [_VALID_FLAG]})
    out = coherence_check.run(_BASE, _BASE, db_session)
    assert out["flags"] == []
    assert out["hygiene"] == []
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


def test_response_shape_always_has_the_three_keys(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": []})
    out = coherence_check.run(_BASE, _CUSTOMIZED, db_session)
    assert set(out) == {"flags", "hygiene", "gates"}
    assert isinstance(out["flags"], list)
    assert isinstance(out["hygiene"], list)
    assert isinstance(out["gates"], list)


# --------------------------------------------------------------------------- #
# hygiene (deterministic resume_lint rules, scoped + inherited-defect suppressed)

def _clean_resume(**overrides):
    resume = {
        "contact": {"email": "a@b.com"},
        "summary": "Data engineer with five years building ETL systems.",
        "skills": [{"category": "Languages", "items": ["Python", "SQL"]}],
        "experience": [
            {
                "company": "Acme", "role": "Engineer", "enabled": True,
                "start_date": "Jan 2020", "end_date": "Present",
                "bullets": ["Built the initial pipeline using Python and SQL end to end"],
            },
        ],
        "projects": [],
        "certifications": [],
    }
    resume.update(overrides)
    return resume


def test_hygiene_reports_a_defect_in_a_section_the_tailoring_changed(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": []})
    base = _clean_resume()
    tailored = deepcopy(base)
    # Tailoring injects a keyword with trailing punctuation into skills — the
    # exact failure mode this round is aimed at.
    tailored["skills"][0]["items"] = ["Python.", "SQL"]

    out = coherence_check.run(base, tailored, db_session)

    assert len(out["hygiene"]) == 1
    entry = out["hygiene"][0]
    assert entry["rule"] == "skills.trailing_punct"
    assert entry["locus"]["after"] == "Python."
    assert entry["locus"]["section"] == "skills"


def test_trailing_punctuation_gets_a_mechanical_proposal_and_raw_subject(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": []})
    base = _clean_resume()
    tailored = deepcopy(base)
    tailored["skills"][0]["items"] = ["Python.", "SQL"]

    out = coherence_check.run(base, tailored, db_session)

    entry = out["hygiene"][0]
    assert entry["proposal"] == "Python"
    assert entry["locus"]["after"] == "Python."
    # Exactly one skills group, and it contains "Python." — resolvable.
    assert entry["locus"]["index"] == 0


def test_judgment_rule_gets_no_proposal(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": []})
    base = _clean_resume()
    tailored = deepcopy(base)
    # Sentence-like injected skill: judgment call (which words to keep), so
    # read-only.
    tailored["skills"][0]["items"] = [
        "Python", "SQL", "Built scalable data pipelines using Airflow and Spark",
    ]

    out = coherence_check.run(base, tailored, db_session)

    sentence_notes = [e for e in out["hygiene"] if e["rule"] == "skills.sentence_like"]
    assert len(sentence_notes) == 1
    assert sentence_notes[0]["proposal"] is None


def test_hygiene_does_not_report_a_defect_inherited_unchanged_from_the_base(
    db_session, monkeypatch
):
    _patch_llm(monkeypatch, {"flags": []})
    # A pre-existing duplicate certification, unchanged by tailoring — but an
    # unrelated cert is added, so "certifications" IS a changed section. The
    # duplicate must still be suppressed: it isn't the tailoring's doing.
    base = _clean_resume(certifications=["AWS CCP", "AWS CCP", "GCP ACE"])
    tailored = deepcopy(base)
    tailored["certifications"].append("Azure Fundamentals")

    out = coherence_check.run(base, tailored, db_session)

    assert out["hygiene"] == []


def test_bullet_level_notes_match_by_entry_index(db_session, monkeypatch):
    """A note fabricated only for entry[1] must not surface when the diff only
    touched entry[0] — pins the scope filter itself, independent of whatever
    resume_lint currently flags (which would also suppress an unchanged
    defect via the base-identity check)."""
    _patch_llm(monkeypatch, {"flags": []})
    base = _clean_resume(
        experience=[
            {
                "company": "Acme", "role": "Engineer", "enabled": True,
                "start_date": "Jan 2020", "end_date": "Present",
                "bullets": ["Built the initial pipeline architecture"],
            },
            {
                "company": "Globex", "role": "Analyst", "enabled": True,
                "start_date": "Jan 2018", "end_date": "Dec 2019",
                "bullets": ["Did stuff"],
            },
        ]
    )
    tailored = deepcopy(base)
    tailored["experience"][0]["bullets"] = [
        "Built the initial pipeline architecture end to end"
    ]
    # entry[1] is byte-identical to base — untouched by the diff.

    fake_note_at_entry1 = {
        "id": "fake-entry1-defect",
        "rule": "bullet.too_short",
        "location": {"section": "experience", "index": 1, "bullet_index": 0},
        "issue": "Very short bullet.",
        "why": "why", "how": "how", "label": "Globex — Analyst · bullet 1",
        "subject": "Did stuff",
    }

    def fake_rule_notes(resume):
        # Fabricate a "new" defect (not present for `base`) at entry[1] so this
        # test exercises `_in_scope`/`_changed`, not the inherited-defect check.
        return [] if resume is base else [fake_note_at_entry1]

    monkeypatch.setattr(coherence_check.resume_lint, "rule_notes", fake_rule_notes)

    out = coherence_check.run(base, tailored, db_session)

    assert out["hygiene"] == []


# --------------------------------------------------------------------------- #
# gates

def test_gates_degrade_to_empty_when_structure_gates_raises(db_session, monkeypatch):
    _patch_llm(monkeypatch, {"flags": [_VALID_FLAG]})

    def boom(*a, **k):
        raise RuntimeError("no pdflatex")

    monkeypatch.setattr(coherence_check.resume_lint, "structure_gates", boom)

    base = _clean_resume()
    tailored = deepcopy(base)
    tailored["skills"][0]["items"] = ["Python.", "SQL"]

    out = coherence_check.run(base, tailored, db_session)

    assert out["gates"] == []
    # The other two groups must survive a gates failure untouched.
    assert out["flags"] == [_VALID_FLAG]
    assert len(out["hygiene"]) == 1
