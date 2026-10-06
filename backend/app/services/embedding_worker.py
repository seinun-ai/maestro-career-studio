"""Import-light child target for one pinned-model embedding batch."""

from functools import lru_cache


@lru_cache(maxsize=1)
def _model(model_id: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_id)


def embed_batch(conn, model_id: str, texts: list[str]) -> None:
    """Load fastembed only in the spawned child and return serializable vectors."""
    try:
        vectors = [[float(value) for value in vector] for vector in _model(model_id).embed(texts)]
        conn.send(("ok", vectors))
    except BaseException as exc:  # noqa: BLE001 -- return a safe failure to the parent
        # Exception messages can contain private input or environment values.
        conn.send(("err", f"model embedding failed ({type(exc).__name__})"))
    finally:
        conn.close()
