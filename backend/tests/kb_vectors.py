"""Fixed unit vectors for the Career KB intake and groom tests (see the plan's
"The hermetic embedder in tests"). 3-D so an unrelated text can sit on its own axis."""


def _vectors(monkeypatch, table: dict[str, tuple[float, ...]]):
    """Fixed unit vectors by text; any text outside the table is a test bug."""
    from app.services.ats import embeddings

    def fake(texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in table]
        assert not missing, f"no vector for {missing!r}"
        return [list(table[t]) for t in texts]

    monkeypatch.setattr(embeddings, "embed_texts", fake)


def _embedder_down(monkeypatch):
    from app.services.ats import embeddings

    def boom(texts: list[str]):
        raise RuntimeError("embeddings failed\nno model")

    monkeypatch.setattr(embeddings, "embed_texts", boom)


OLD = "Built the ingestion pipeline"
REWRITE = "Built and ran the ingestion pipeline for finance"      # 0.85 to OLD: a wording
UNDER = "Built the ingestion pipeline and its dashboards"        # 0.79 to OLD: just under, new
CLOSE = "Built the ingestion pipelines"                          # 0.92 to OLD: a wording
FAR = "Negotiated a net-new vendor contract"                     # unrelated to all

BAND = {
    OLD: (1.0, 0.0, 0.0),
    REWRITE: (0.85, 0.52678, 0.0),
    UNDER: (0.79, 0.61311, 0.0),
    CLOSE: (0.92, 0.39192, 0.0),
    FAR: (0.0, 0.0, 1.0),
}
