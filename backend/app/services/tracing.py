"""Optional Langfuse tracing for LLM calls.

A thin, failure-proof wrapper around the Langfuse SDK: when the keys are not
configured (the default) everything is a no-op, and no Langfuse failure —
missing package, unreachable host, SDK API drift — may ever break or block an
LLM call. All calls funnel through `generation()`, used by
`app.services.llm.call_openai`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any | None = None
_disabled = False

Recorder = Callable[..., None]


def _get_client() -> Any | None:
    global _client, _disabled
    if _disabled or _client is not None:
        return _client
    # Keys alone are NOT enough: tracing requires an explicit host. No Langfuse
    # stack ships here anymore, and the repo historically carried placeholder
    # keys (`pk-lf-resume-tailor-local`). With those present and no host, the SDK
    # falls back to Langfuse CLOUD — so a stale placeholder left in someone's
    # .env would ship their prompts and completions to a third party. Opt-in must
    # be by DESTINATION, not merely by credential.
    if not (
        settings.langfuse_public_key
        and settings.langfuse_secret_key
        and settings.langfuse_host
    ):
        _disabled = True
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse tracing enabled (%s)", settings.langfuse_host)
    except Exception as exc:
        logger.warning("Langfuse tracing disabled: %s", exc)
        _disabled = True
    return _client


def _noop_record(output: str, usage: dict[str, int] | None = None) -> None:
    return None


@contextmanager
def generation(
    name: str,
    *,
    model: str,
    prompt: str,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Recorder]:
    """Record one LLM generation in Langfuse, if tracing is configured.

    Yields a `record(output, usage)` callable; usage is Langfuse
    `usage_details` shaped ({"input": …, "output": …}). Exceptions raised in
    the block are recorded as ERROR generations and re-raised.
    """
    client = _get_client()
    if client is None:
        yield _noop_record
        return

    try:
        gen = client.start_observation(
            name=name, as_type="generation", model=model, input=prompt, metadata=metadata
        )
    except Exception as exc:
        logger.debug("Langfuse start_observation failed: %s", exc)
        yield _noop_record
        return

    def record(output: str, usage: dict[str, int] | None = None) -> None:
        try:
            gen.update(output=output, usage_details=usage)
        except Exception as exc:
            logger.debug("Langfuse generation update failed: %s", exc)

    try:
        yield record
    except Exception as exc:
        try:
            gen.update(level="ERROR", status_message=str(exc)[:500])
        except Exception:
            pass
        raise
    finally:
        try:
            gen.end()
        except Exception as exc:
            logger.debug("Langfuse generation end failed: %s", exc)


def shutdown() -> None:
    """Flush pending events; called from the FastAPI lifespan teardown."""
    if _client is None:
        return
    try:
        _client.shutdown()
    except Exception as exc:
        logger.debug("Langfuse shutdown failed: %s", exc)
