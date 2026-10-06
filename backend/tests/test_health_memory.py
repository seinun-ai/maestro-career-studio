import resource

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_memory_reports_current_and_peak_megabytes():
    body = client.get("/health/memory").json()
    assert set(body) == {"rss_mb", "peak_mb", "platform"}
    assert body["rss_mb"] > 0 and body["peak_mb"] > 0  # ru_maxrss can lag VmRSS on Linux


def test_health_stays_tiny_for_container_healthchecks():
    assert client.get("/health").json() == {"status": "ok"}


@pytest.fixture
def memory_sources(monkeypatch, tmp_path):
    from app.services import memory

    status = tmp_path / "status"
    usage = resource.struct_rusage((0, 0, 131584) + (0,) * 13)
    monkeypatch.setattr(memory, "Path", lambda _path: status)
    monkeypatch.setattr(memory.sys, "platform", "linux")
    monkeypatch.setattr(memory.resource, "getrusage", lambda _who: usage)
    return memory, status


def test_health_memory_never_reports_a_peak_below_the_current_rss(memory_sources):
    _, status = memory_sources
    status.write_text("Name:\tpython\nVmPeak:\t2097152 kB\nVmRSS:\t  157337 kB\n")

    response = client.get("/health/memory")

    assert response.status_code == 200
    assert response.json() == {"rss_mb": 153.6, "peak_mb": 153.6, "platform": "linux"}


@pytest.mark.parametrize("contents", [None, "Name:\tpython\nVmSize:\t2097152 kB\n"])
def test_current_rss_falls_back_to_peak_without_a_proc_reading(memory_sources, contents):
    memory, status = memory_sources
    if contents is not None:
        status.write_text(contents)

    assert memory.rss_mb() == 128.5


@pytest.mark.parametrize(
    ("platform", "ru_maxrss"),
    [("linux", 157337), ("darwin", 161113088)],
)
def test_peak_memory_converts_platform_units_and_rounds(monkeypatch, platform, ru_maxrss):
    from app.services import memory

    usage = resource.struct_rusage((0, 0, ru_maxrss) + (0,) * 13)
    monkeypatch.setattr(memory.sys, "platform", platform)
    monkeypatch.setattr(memory.resource, "getrusage", lambda _who: usage)

    assert memory.peak_mb() == 153.6
