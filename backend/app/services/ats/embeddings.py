"""Pinned-model text embeddings for the ATS engine's semantic layer.

Determinism: the model id comes from weights.yaml (hashed into config_version),
vectors are memoized per (model_id, text), and fastembed runs a fixed ONNX graph
on CPU — same text always yields the same vector on a given machine.

Kept import-light for spawned helpers: settings and ATS config are loaded only
in the parent, and fastembed is deferred until the chosen process embeds.
"""
import hashlib
import multiprocessing
import time
from functools import lru_cache

from app.services.embedding_worker import embed_batch


EMBEDDINGS_TIMEOUT_S: float = 60.0


def load_config():
    from app.services.ats.config import load_config as load_ats_config

    return load_ats_config()


@lru_cache(maxsize=1)
def _model(model_id: str):
    from fastembed import TextEmbedding  # deferred: heavy import, model download on first use

    return TextEmbedding(model_name=model_id)


def _receive_result(conn, timeout: float):
    if conn.poll(timeout):
        try:
            return conn.recv()
        except (EOFError, OSError):
            return "err", "helper exited without a result"
    return "err", "helper exited without a result"


def _join_worker(proc, deadline: float, timeout: float) -> None:
    proc.join(max(0.0, deadline - time.monotonic()))
    if proc.is_alive():
        proc.kill()
        proc.join()
        raise RuntimeError(
            "embeddings failed\n"
            f"embedding exceeded the {timeout:g}s time limit and was killed"
        )


def _embed_out_of_process(model_id: str, texts: list[str]) -> list[list[float]]:
    timeout = EMBEDDINGS_TIMEOUT_S
    deadline = time.monotonic() + timeout
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=embed_batch, args=(child_conn, model_id, texts), daemon=True)
    try:
        proc.start()
        child_conn.close()  # only the helper writes
        # Drain before joining: vectors can exceed pipe capacity and block send().
        status, payload = _receive_result(parent_conn, max(0.0, deadline - time.monotonic()))
        _join_worker(proc, deadline, timeout)
        if proc.exitcode != 0:
            raise RuntimeError(f"embeddings failed\nhelper exited without a result (exit {proc.exitcode})")
        if status != "ok":
            raise RuntimeError(f"embeddings failed\n{payload}")
        return payload
    finally:
        parent_conn.close()
        child_conn.close()
        if proc.pid is not None and proc.is_alive():
            proc.kill()
            proc.join()


def _embed_batch(model_id: str, texts: list[str]):
    from app.config import settings

    if settings.embeddings_out_of_process:
        return _embed_out_of_process(model_id, texts)
    return list(_model(model_id).embed(texts))


# Process-lifetime vector cache: (model_id, sha256(text)) -> tuple vector.
# Not persisted; it just spares re-embedding the same chunk within a process.
_CACHE: dict[tuple[str, str], tuple[float, ...]] = {}
# Bound the cache so a long-lived process embedding many distinct texts can't grow
# it without limit (post-review M1). Simple policy: once over the cap, drop the
# whole cache and start fresh — vectors are cheap to recompute and the working set
# of a single scoring call is tiny, so a periodic clear costs almost nothing.
_CACHE_MAX = 4096


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with the pinned model; memoized per text. Batch-embeds misses."""
    model_id = load_config().weights["semantic"]["model"]
    keys = [(model_id, hashlib.sha256(t.encode("utf-8")).hexdigest()) for t in texts]
    misses = [(i, t) for i, (t, k) in enumerate(zip(texts, keys)) if k not in _CACHE]
    if misses:
        if len(_CACHE) + len(misses) > _CACHE_MAX:
            _CACHE.clear()
        vectors = _embed_batch(model_id, [t for _, t in misses])  # ONE batch call
        for (i, _), vec in zip(misses, vectors):
            _CACHE[keys[i]] = tuple(float(x) for x in vec)
    return [list(_CACHE[k]) for k in keys]


def cosine(a: list[float], b: list[float]) -> float:
    """Plain-python cosine; clamped to [0, 1] (negative similarity is 'unrelated')."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    if norm == 0:
        return 0.0
    return max(0.0, dot / norm)
