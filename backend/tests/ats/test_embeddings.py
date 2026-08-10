"""Unit tests for the pinned-model embeddings seam.

No model download: `_model` is stubbed and `load_config` is stubbed (the
`semantic` weights block lands in a later commit; these tests must not depend
on it).
"""
import pytest

from app.services.ats import embeddings

# This file tests the embed_texts seam itself (memoization/batching, with _model
# stubbed) — the hermetic autouse fake would replace embed_texts and defeat that.
pytestmark = pytest.mark.embeddings_internals


class _StubModel:
    """Counts .embed calls and records the batches it was asked to embed."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        # deterministic per-text vector: length-3, keyed off the text itself
        return [[float(len(t)), 1.0, 0.0] for t in batch]


@pytest.fixture()
def stub_model(monkeypatch):
    stub = _StubModel()
    monkeypatch.setattr(embeddings, "_model", lambda model_id: stub)

    class _Cfg:
        weights = {"semantic": {"model": "stub-model-v1"}}

    monkeypatch.setattr(embeddings, "load_config", lambda: _Cfg())
    embeddings._CACHE.clear()
    yield stub
    embeddings._CACHE.clear()


def test_embed_texts_returns_one_vector_per_text(stub_model):
    vectors = embeddings.embed_texts(["alpha", "be"])
    assert vectors == [[5.0, 1.0, 0.0], [2.0, 1.0, 0.0]]


def test_embed_texts_memoizes_repeat_texts(stub_model):
    first = embeddings.embed_texts(["alpha"])
    second = embeddings.embed_texts(["alpha"])
    assert first == second
    assert len(stub_model.calls) == 1  # second call served from cache


def test_embed_texts_batches_misses_in_one_call(stub_model):
    embeddings.embed_texts(["alpha", "beta"])
    assert stub_model.calls == [["alpha", "beta"]]  # ONE batch call for both misses


def test_embed_texts_only_embeds_new_misses(stub_model):
    embeddings.embed_texts(["alpha"])
    embeddings.embed_texts(["alpha", "beta", "gamma"])
    assert stub_model.calls == [["alpha"], ["beta", "gamma"]]


def test_embed_texts_cache_is_bounded(stub_model, monkeypatch):
    # post-review M1: the process-lifetime cache must not grow without limit.
    monkeypatch.setattr(embeddings, "_CACHE_MAX", 3)
    embeddings.embed_texts(["a", "b", "c"])
    assert len(embeddings._CACHE) == 3
    # adding a 4th distinct text would exceed the cap -> cache clears first
    embeddings.embed_texts(["d"])
    assert len(embeddings._CACHE) == 1
    assert embeddings.embed_texts(["d"]) == [[1.0, 1.0, 0.0]]  # still serves correctly


def test_cosine_identical_vectors():
    assert embeddings.cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    assert embeddings.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_negative_similarity_clamped_to_zero():
    # raw cosine of opposite vectors is -1.0; "unrelated" floors at 0
    assert embeddings.cosine([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_cosine_zero_vector_guard():
    assert embeddings.cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert embeddings.cosine([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_known_value():
    # cos between (1,0) and (1,1) = 1/sqrt(2)
    assert embeddings.cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(0.7071067811865475)
