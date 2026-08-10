from app.services import llm, tracing


def test_generation_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_disabled", False)
    monkeypatch.setattr(tracing.settings, "langfuse_public_key", "")
    monkeypatch.setattr(tracing.settings, "langfuse_secret_key", "")

    with tracing.generation("test", model="gpt-4o", prompt="hi") as record:
        record("output", {"input": 1, "output": 2})
        record("output")  # usage optional

    assert tracing._get_client() is None
    assert tracing._disabled is True


def test_generation_survives_broken_client(monkeypatch):
    class ExplodingClient:
        def start_observation(self, **kwargs):
            raise RuntimeError("boom")

        def shutdown(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(tracing, "_client", ExplodingClient())
    monkeypatch.setattr(tracing, "_disabled", False)

    # Tracing failures must never propagate into the LLM call path.
    with tracing.generation("test", model="gpt-4o", prompt="hi") as record:
        record("output")
    tracing.shutdown()


def test_generation_records_error_and_reraises(monkeypatch):
    events: list[tuple] = []

    class FakeGen:
        def update(self, **kwargs):
            events.append(("update", kwargs))

        def end(self):
            events.append(("end", {}))

    class FakeClient:
        def start_observation(self, **kwargs):
            events.append(("start", kwargs))
            return FakeGen()

    monkeypatch.setattr(tracing, "_client", FakeClient())
    monkeypatch.setattr(tracing, "_disabled", False)

    try:
        with tracing.generation("test", model="gpt-4o", prompt="hi"):
            raise ValueError("model exploded")
    except ValueError:
        pass
    else:
        raise AssertionError("exception should propagate")

    kinds = [kind for kind, _ in events]
    assert kinds == ["start", "update", "end"]
    assert events[1][1]["level"] == "ERROR"


def test_usage_details_requires_ints():
    assert llm._usage_details(3, 5) == {"input": 3, "output": 5}
    assert llm._usage_details(None, 5) is None
    assert llm._usage_details(object(), object()) is None  # MagicMock-safe


def test_tracing_requires_an_explicit_host(monkeypatch):
    """Keys alone must not enable tracing.

    No Langfuse stack ships here anymore, and the repo historically carried
    placeholder keys (`pk-lf-resume-tailor-local`). With those present and no
    host, the SDK falls back to Langfuse CLOUD — so stale local placeholders
    would ship prompts and completions to a third party. Requiring an explicit
    host makes tracing opt-in by destination, not merely by credential.
    """
    from app.services import tracing

    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_disabled", False)
    monkeypatch.setattr(tracing.settings, "langfuse_public_key", "pk-lf-stale")
    monkeypatch.setattr(tracing.settings, "langfuse_secret_key", "sk-lf-stale")
    monkeypatch.setattr(tracing.settings, "langfuse_host", None)

    assert tracing._get_client() is None
