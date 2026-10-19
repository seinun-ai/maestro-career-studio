"""kb_claims.place: the one decision 'does this text restate a claim on this item?'"""

import pytest

from app.models.career_kb import KBEntity, KBPoint
from app.services import kb_claims
from tests.kb_vectors import BAND, CLOSE, FAR, OLD, REWRITE, UNDER, _embedder_down, _vectors


def _points(db_session, *specs):
    """specs: (text, state, provenance)."""
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    out = []
    for text, state, provenance in specs:
        p = KBPoint(entity_id=ent.id, text=text, state=state, origin="manual", provenance=provenance)
        db_session.add(p)
        db_session.flush()
        out.append(p)
    return out


def test_the_band_is_the_designed_constant():
    assert kb_claims.SYNC_WORDING_COSINE == 0.80


def test_exact_match_is_in_sync_before_any_embedding(db_session, monkeypatch):
    _embedder_down(monkeypatch)  # must not even be consulted
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place("  built THE ingestion   pipeline ", [old])
    assert (placed.kind, placed.point, placed.compared) == ("in_sync", old, True)


def test_in_band_is_a_wording_with_the_point_and_score(db_session, monkeypatch):
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(REWRITE, [old])
    assert placed.kind == "wording"
    assert placed.point == old
    assert placed.score == pytest.approx(0.85, abs=0.01)
    assert kb_claims.place(CLOSE, [old]).kind == "wording"


def test_under_the_band_is_new(db_session, monkeypatch):
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(UNDER, [old])
    assert (placed.kind, placed.point, placed.score) == ("new", None, None)


@pytest.mark.parametrize("state,provenance", [("retired", "user_authored"), ("approved", "user_cannot_confirm")])
def test_retired_and_unconfirmable_points_are_never_targets(db_session, monkeypatch, state, provenance):
    _vectors(monkeypatch, BAND)
    far, old = _points(db_session, (FAR, "approved", "user_authored"), (OLD, state, provenance))
    assert kb_claims.candidates([far, old]) == [far]
    placed = kb_claims.place(REWRITE, kb_claims.candidates([far, old]))
    assert placed.kind == "new"


def test_embedder_failure_is_reported_not_hidden(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(REWRITE, [old])
    assert (placed.kind, placed.point, placed.compared) == ("new", None, False)


def test_no_points_means_new_and_compared(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    placed = kb_claims.place(REWRITE, [])
    assert (placed.kind, placed.compared) == ("new", True)


def test_place_never_calls_the_llm(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("intake must not call the LLM")),
    )
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    kb_claims.place(REWRITE, [old])
