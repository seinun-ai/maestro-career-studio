"""Exercise real spawn/pipe transport with a model loader stubbed in the child."""

import multiprocessing
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings, settings
from app.services.ats import embeddings


pytestmark = pytest.mark.embeddings_internals
BACKEND = Path(__file__).resolve().parents[2]
PINNED_MODEL = "BAAI/bge-small-en-v1.5"


class _FakeModel:
    def embed(self, texts):
        # 384 dimensions, like the pinned model; large batches fill an OS pipe.
        return [[float(len(text)), float(sum(text.encode("utf-8"))), 0.1] * 128
                for text in texts]


def _fake_model(model_id):
    assert model_id == PINNED_MODEL
    return _FakeModel()


def _write_fake_fastembed(directory: Path, *, failure: bool = False) -> None:
    init = "raise ValueError('secret-sentinel: private input')" if failure else "pass"
    source = f'''class TextEmbedding:
    def __init__(self, model_name):
        assert model_name == {PINNED_MODEL!r}
        {init}

    def embed(self, texts):
        return [[float(len(text)), float(sum(text.encode("utf-8"))), 0.1] * 128
                for text in texts]
'''
    (directory / "fastembed.py").write_text(source, encoding="utf-8")


def _dead_worker(conn, model_id, texts):
    os._exit(7)


def _stuck_worker(conn, model_id, texts):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)


def _send_then_stuck_worker(conn, model_id, texts):
    from app.services.embedding_worker import embed_batch

    embed_batch(conn, model_id, texts)
    time.sleep(30)


@pytest.fixture
def isolated_embeddings(monkeypatch):
    monkeypatch.setattr(settings, "embeddings_out_of_process", False)
    monkeypatch.setattr(embeddings, "_model", _fake_model)
    embeddings._CACHE.clear()
    yield
    embeddings._CACHE.clear()


@pytest.fixture
def spawned(monkeypatch, isolated_embeddings, tmp_path):
    context = multiprocessing.get_context("spawn")
    processes = []
    loader_dir = tmp_path / "fake_loader"
    loader_dir.mkdir()
    _write_fake_fastembed(loader_dir)
    monkeypatch.syspath_prepend(str(loader_dir))

    def create_process(**kwargs):
        process = context.Process(**kwargs)
        processes.append(process)
        return process

    spy = Mock(side_effect=create_process)
    get_context = Mock(return_value=SimpleNamespace(Pipe=context.Pipe, Process=spy))
    monkeypatch.setattr(embeddings.multiprocessing, "get_context", get_context)
    yield SimpleNamespace(
        processes=processes, create=spy, context=get_context,
        write_model=lambda failure=False: _write_fake_fastembed(loader_dir, failure=failure),
    )
    assert all(not process.is_alive() for process in processes), "embedding helper leaked"


def test_embedding_setting_defaults_off(monkeypatch):
    monkeypatch.delenv("EMBEDDINGS_OUT_OF_PROCESS", raising=False)
    assert Settings(_env_file=None).embeddings_out_of_process is False


@pytest.mark.parametrize("value,enabled", [("1", True), ("true", True), ("0", False)])
def test_embedding_setting_reads_fixed_env_name(monkeypatch, value, enabled):
    monkeypatch.setenv("EMBEDDINGS_OUT_OF_PROCESS", value)
    assert Settings(_env_file=None).embeddings_out_of_process is enabled


def test_spawned_vectors_equal_in_process_in_input_order(spawned, monkeypatch):
    texts = ["Python pipelines", "", "résumé 🧪", "Python pipelines", "SQL"]
    expected = embeddings.embed_texts(texts)
    embeddings._CACHE.clear()
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    assert embeddings.embed_texts(texts) == expected
    spawned.context.assert_called_once_with("spawn")
    args = spawned.create.call_args.kwargs["args"]
    assert args[1:] == (PINNED_MODEL, texts)
    assert spawned.processes[0].exitcode == 0


def test_only_misses_are_sent_as_one_batch_and_cache_hits_never_spawn(spawned, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    first = embeddings.embed_texts(["Python", "SQL"])
    first[0][0] = -1  # callers cannot mutate the cached vector
    assert embeddings.embed_texts(["SQL", "Python", "SQL"]) == [
        _FakeModel().embed([text])[0] for text in ["SQL", "Python", "SQL"]
    ]
    assert spawned.create.call_count == 1
    assert embeddings.embed_texts(["Python", "Spark", "SQL", "new pipeline"]) == (
        _FakeModel().embed(["Python", "Spark", "SQL", "new pipeline"])
    )
    assert spawned.create.call_count == 2
    assert spawned.create.call_args.kwargs["args"][1:] == (
        PINNED_MODEL, ["Spark", "new pipeline"],
    )


def test_setting_off_uses_parent_model_and_never_spawns(spawned):
    assert embeddings.embed_texts(["Python", "SQL"]) == _FakeModel().embed(["Python", "SQL"])
    spawned.context.assert_not_called()


def test_empty_batch_never_loads_a_model_or_spawns(spawned, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    loader = Mock(side_effect=AssertionError("empty batch loaded a model"))
    monkeypatch.setattr(embeddings, "_model", loader)
    assert embeddings.embed_texts([]) == []
    loader.assert_not_called()
    spawned.context.assert_not_called()


def test_child_death_raises_clear_error_and_keeps_existing_cache(spawned, monkeypatch):
    cached = embeddings.embed_texts(["Python"])
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    monkeypatch.setattr(embeddings, "embed_batch", _dead_worker)
    with pytest.raises(RuntimeError, match="embeddings failed.*|embeddings failed\n") as error:
        embeddings.embed_texts(["new pipeline"])
    assert "exited without a result" in str(error.value)
    assert "7" in str(error.value)
    assert len(embeddings._CACHE) == 1
    assert embeddings.embed_texts(["Python"]) == cached
    assert spawned.create.call_count == 1


def test_child_loader_error_is_clear_without_exposing_private_text(spawned, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    spawned.write_model(failure=True)
    with pytest.raises(RuntimeError, match="embeddings failed") as error:
        embeddings.embed_texts(["private resume text"])
    assert "ValueError" in str(error.value)
    assert "secret-sentinel" not in str(error.value)
    assert "private" not in str(error.value)
    assert not embeddings._CACHE


@pytest.mark.parametrize("worker", [_stuck_worker, _send_then_stuck_worker])
def test_stuck_child_is_killed_and_reaped_with_clear_timeout(spawned, monkeypatch, worker):
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    monkeypatch.setattr(embeddings, "embed_batch", worker)
    monkeypatch.setattr(embeddings, "EMBEDDINGS_TIMEOUT_S", 1.0)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="exceeded the 1s time limit"):
        embeddings.embed_texts(["Python"])
    assert time.monotonic() - started < 5
    assert not embeddings._CACHE
    assert spawned.processes[0].exitcode != 0


def test_large_vector_batch_is_drained_before_joining_the_child(spawned, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    monkeypatch.setattr(embeddings, "EMBEDDINGS_TIMEOUT_S", 5.0)
    texts = [f"pipeline chunk {index}" for index in range(128)]
    assert embeddings.embed_texts(texts) == _FakeModel().embed(texts)
    assert spawned.create.call_count == 1
    assert spawned.processes[0].exitcode == 0


class _FakeConn:
    def poll(self, timeout=None):
        return True

    def recv(self):
        return "ok", [[0.5] * 3]

    def close(self):
        pass


class _FakeHelpers:
    """Fake spawn context: counts helpers alive at once; `fail_first` makes the first start raise."""

    def __init__(self, fail_first=False):
        self.guard = threading.Lock()
        self.active = 0
        self.peak = 0
        self.starts = 0
        self.fail_first = fail_first

    def Pipe(self, duplex=False):
        return _FakeConn(), _FakeConn()

    def Process(self, **kwargs):
        return _FakeProcess(self)


class _FakeProcess:
    pid = 1
    exitcode = 0

    def __init__(self, helpers):
        self.helpers = helpers
        self.running = False

    def start(self):
        helpers = self.helpers
        with helpers.guard:
            helpers.starts += 1
            if helpers.fail_first and helpers.starts == 1:
                raise RuntimeError("helper failed to start")
            helpers.active += 1
            helpers.peak = max(helpers.peak, helpers.active)
        self.running = True
        time.sleep(0.2)  # long enough for a second thread to start unless it is serialized

    def join(self, timeout=None):
        if self.running:
            self.running = False
            with self.helpers.guard:
                self.helpers.active -= 1

    def is_alive(self):
        return False

    def kill(self):
        pass


def _fake_helpers(monkeypatch, **kwargs):
    helpers = _FakeHelpers(**kwargs)
    monkeypatch.setattr(settings, "embeddings_out_of_process", True)
    monkeypatch.setattr(embeddings.multiprocessing, "get_context", lambda name: helpers)
    return helpers


def test_concurrent_callers_never_run_two_helpers_at_once(isolated_embeddings, monkeypatch):
    helpers = _fake_helpers(monkeypatch)
    errors = []

    def call(text):
        try:
            embeddings.embed_texts([text])
        except Exception as error:  # surfaced below; a thread must not swallow it
            errors.append(error)

    threads = [threading.Thread(target=call, args=(text,)) for text in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors
    assert helpers.starts == 2  # the waiting caller still spawns its own helper
    assert helpers.peak == 1


def test_failing_helper_releases_the_lock_for_the_next_call(isolated_embeddings, monkeypatch):
    helpers = _fake_helpers(monkeypatch, fail_first=True)
    with pytest.raises(RuntimeError, match="failed to start"):
        embeddings.embed_texts(["first"])
    done = threading.Event()
    result = []

    def second():
        result.append(embeddings.embed_texts(["second"]))
        done.set()

    threading.Thread(target=second, daemon=True).start()
    assert done.wait(5), "lock was not released after the helper failed"
    assert result == [[[0.5] * 3]]
    assert helpers.starts == 2


def test_child_module_imports_only_stdlib_before_embedding(tmp_path):
    code = """
import sys
import app.services.embedding_worker
heavy = {'fastembed', 'yaml', 'sqlalchemy', 'pydantic', 'app.config',
         'app.services.ats', 'app.services.ats.config', 'app.main'}
assert not heavy & sys.modules.keys(), heavy & sys.modules.keys()
print(len(sys.modules))
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert 0 < int(result.stdout.strip()) < 100
    assert result.stderr == ""


def _free_port():
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        return available.getsockname()[1]


@pytest.mark.slow
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux resident memory measurement")
@pytest.mark.skipif(bool(os.environ.get("MAESTRO_SKIP_SLOW")), reason="MAESTRO_SKIP_SLOW is set")
def test_real_model_helper_releases_at_least_150_mb_after_profile(tmp_path, monkeypatch):
    from scripts.memory_profile import run_profile

    monkeypatch.setenv("MALLOC_ARENA_MAX", "2")
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", os.environ.get(
        "FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed_cache"),
    ))
    monkeypatch.setenv("EMBEDDINGS_OUT_OF_PROCESS", "0")
    in_process = run_profile(port=_free_port(), cycles=5)
    monkeypatch.setenv("EMBEDDINGS_OUT_OF_PROCESS", "1")
    out_of_process = run_profile(port=_free_port(), cycles=5)
    assert in_process[-1]["cycle"] == out_of_process[-1]["cycle"] == 5
    saved_mb = in_process[-1]["rss_mb"] - out_of_process[-1]["rss_mb"]
    assert saved_mb >= 150, f"helper released only {saved_mb:.1f} MB"
