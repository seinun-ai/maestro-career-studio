"""Building an httpx client must survive a malformed proxy environment.

httpx reads NO_PROXY / HTTP(S)_PROXY when a Client is built. A bracketed IPv6
literal in NO_PROXY (`[fd8b:1234::1]`, as some VM images set) makes it raise
InvalidURL, which used to kill the backend at import.
"""

import logging
import os
import subprocess
import sys

import httpx
import pytest

from app.services import http_client, jev

BAD = "localhost,127.0.0.1,::1,[fd8b:1234::1]"
CLEAN = "localhost,127.0.0.1,::1"
SECRET_PROXY = "http://user:hunter2@proxy.example:3128"
_VARS = ("NO_PROXY", "no_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
         "ALL_PROXY", "all_proxy")


@pytest.fixture(autouse=True)
def _clean_proxy_env(monkeypatch):
    for name in _VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(http_client, "_warned", set())


def _run(code: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _VARS}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)


def test_the_premise_httpx_itself_rejects_the_bad_entry(monkeypatch):
    monkeypatch.setenv("NO_PROXY", BAD)
    with pytest.raises(httpx.InvalidURL):
        httpx.Client()


def test_importing_the_app_survives_a_bracketed_ipv6_no_proxy():
    result = _run("import app.main, mcp_server.client", {"NO_PROXY": BAD, "no_proxy": BAD})
    assert result.returncode == 0, result.stderr[-800:]


def test_importing_jev_builds_no_client():
    result = _run(
        "from app.services import jev; assert jev._CLIENT is None, jev._CLIENT",
        {"NO_PROXY": BAD})
    assert result.returncode == 0, result.stderr[-800:]


def test_jev_builds_its_client_once_on_first_use_and_shares_it(monkeypatch):
    monkeypatch.setattr(jev, "_CLIENT", None)
    first = jev._client()
    try:
        assert isinstance(first, httpx.Client)
        assert jev._client() is first
    finally:
        first.close()
        monkeypatch.setattr(jev, "_CLIENT", None)


def test_jev_client_builds_under_the_bad_env(monkeypatch):
    monkeypatch.setattr(jev, "_CLIENT", None)
    monkeypatch.setenv("NO_PROXY", BAD)
    client = jev._client()
    client.close()
    monkeypatch.setattr(jev, "_CLIENT", None)


def test_a_clean_env_builds_the_client_without_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=http_client.logger.name):
        client = http_client.new_client(timeout=5)
    client.close()
    assert caplog.records == []
    assert client.timeout == httpx.Timeout(5)


def _no_proxy_hosts(client: httpx.Client) -> set[str]:
    return {pattern.pattern for pattern, transport in client._mounts.items() if transport is None}


def test_the_bad_env_still_yields_a_client_with_the_valid_entries_excluded(monkeypatch):
    monkeypatch.setenv("NO_PROXY", BAD)
    with http_client.new_client() as client:
        hosts = _no_proxy_hosts(client)
    assert {"all://localhost", "all://127.0.0.1", "all://[::1]"} <= hosts
    assert "all://[fd8b:1234::1]" in hosts  # unbracketed, so it parses and stays excluded


def test_a_clean_env_excludes_exactly_what_httpx_alone_would(monkeypatch):
    monkeypatch.setenv("NO_PROXY", CLEAN)
    with httpx.Client() as plain, http_client.new_client() as ours:
        assert _no_proxy_hosts(ours) == _no_proxy_hosts(plain)


def test_proxy_settings_survive_the_retry_and_the_env_is_restored(monkeypatch):
    monkeypatch.setenv("NO_PROXY", BAD)
    monkeypatch.setenv("HTTPS_PROXY", SECRET_PROXY)
    with http_client.new_client() as client:
        proxied = [p.pattern for p, t in client._mounts.items() if t is not None]
    assert "https://" in proxied
    assert os.environ["NO_PROXY"] == BAD  # the repair never rewrites the user's environment
    assert os.environ["HTTPS_PROXY"] == SECRET_PROXY


def test_the_warning_names_the_variable_but_leaks_no_proxy_value(monkeypatch, caplog):
    monkeypatch.setenv("NO_PROXY", BAD)
    monkeypatch.setenv("HTTPS_PROXY", SECRET_PROXY)
    with caplog.at_level(logging.WARNING, logger=http_client.logger.name):
        http_client.new_client().close()
        http_client.new_client().close()  # a per-request caller must not spam
    warnings = [r.getMessage() for r in caplog.records]
    assert len(warnings) == 1
    assert "NO_PROXY" in warnings[0]
    assert "hunter2" not in warnings[0] and "proxy.example" not in warnings[0]


def test_both_spellings_of_the_variable_are_repaired(monkeypatch):
    monkeypatch.setenv("no_proxy", BAD)
    with http_client.new_client() as client:
        assert "all://localhost" in _no_proxy_hosts(client)


def test_an_entry_that_cannot_be_repaired_is_dropped(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,[[bad:1]x,[::1]:99999999")
    with http_client.new_client() as client:
        assert "all://localhost" in _no_proxy_hosts(client)


def test_an_invalid_url_not_caused_by_no_proxy_still_raises(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://bad host:notaport")
    with pytest.raises(httpx.InvalidURL):
        http_client.new_client()
