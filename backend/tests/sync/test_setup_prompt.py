"""GET /api/settings/second-copy/setup-prompt: the laptop's bot prompt.

The public host is filled in. The sync key and the pairing code are not.
"""

import hashlib

import pytest

from app.config import settings
from app.models.setting import Setting
from app.services.sync import pairing, status
from tests.sync import test_home_endpoints as home_tests

client = home_tests.client
sync_off = home_tests.sync_off

PROMPT = "/api/settings/second-copy/setup-prompt"
PLACEHOLDER = "<your laptop's address — I'll give it to you>"
HOME_ONLY = "Show a pairing code on your laptop, not on the always-on copy."
HOST = "laptop.example.test"
KEY = "SENTINEL-SYNC-KEY-DO-NOT-LEAK"


def filled(client, monkeypatch, configured):
    monkeypatch.setattr(settings, "sync_public_host", configured)
    response = client.get(PROMPT)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"prompt"}
    return body["prompt"]


def assert_url(prompt, url):
    """Both insertions, and nothing glued on from a scheme, path, query or user."""
    assert "{laptop_url}" not in prompt
    assert "%{http_code}" in prompt
    assert f"SYNC_REMOTE_URL={url}." in prompt
    assert f"{url}/api/sync/hello" in prompt
    assert prompt.count(f"SYNC_REMOTE_URL={url}.") == 1
    assert prompt.count(f"{url}/api/sync/hello") == 1


@pytest.mark.parametrize(("configured", "url"), [
    ("", PLACEHOLDER),
    ("   ", PLACEHOLDER),
    ("https://", PLACEHOLDER),
    (HOST, f"https://{HOST}"),
    (f"  {HOST}  ", f"https://{HOST}"),
    (f"https://{HOST}", f"https://{HOST}"),
    (f"https://{HOST}/", f"https://{HOST}"),
    (f"https://{HOST}/api/sync", f"https://{HOST}"),
    (f"HTTPS://{HOST}/api/sync/", f"https://{HOST}"),
    (f"{HOST}/api/sync", f"https://{HOST}"),
    (f"https://{HOST}?cursor=1", f"https://{HOST}"),
    (f"https://{HOST}#frag", f"https://{HOST}"),
    (f"https://bot:s3cret@{HOST}/api/sync", f"https://{HOST}"),
    ("HTTPS://Laptop.Example.Test/Api", "https://Laptop.Example.Test"),
])
def test_setup_prompt_fills_only_the_public_host(client, sync_off, monkeypatch, configured, url):
    prompt = filled(client, monkeypatch, configured)
    assert_url(prompt, url)
    assert "s3cret" not in prompt
    assert "bot:" not in prompt
    if url == PLACEHOLDER:
        assert "https://laptop" not in prompt
    else:
        assert PLACEHOLDER not in prompt


def test_setup_prompt_keeps_the_rules_and_the_curl_braces(client, sync_off, monkeypatch):
    prompt = filled(client, monkeypatch, f"https://{HOST}/api/sync")
    assert_url(prompt, f"https://{HOST}")
    assert "https://{HOST}/api/sync/api/sync".format(HOST=HOST) not in prompt
    for line in (
        "Set up an always-on copy of Maestro Career Studio",
        "Use a fresh install; don't copy my laptop's database here.",
        "Never run start.sh from inside one of your own tool calls",
        "stop.sh --no-pause",
        "SSL_CERT_FILE",
        "should print 404",
        "--pair --code -",
        "--accept-profile-overwrite",
        "Don't join this machine to my tailnet",
        "20 minutes",
        "Never open, print or send the sync key",
    ):
        assert line in prompt


def test_setup_prompt_omits_the_sync_key_and_the_pairing_code(client, sync_on, db_session):
    sync_on.write_text(KEY + "\n", encoding="utf-8")
    opened = client.post("/api/settings/second-copy", headers={"Origin": home_tests.ALLOWED_ORIGIN})
    assert opened.status_code == 200, opened.text
    code = opened.json()["code"]
    secret = hashlib.sha256(pairing.normalize_code(code).encode()).hexdigest()
    response = client.get(PROMPT)
    assert response.status_code == 200, response.text
    text = response.text
    assert KEY not in text
    assert code not in text
    assert code.replace("-", "") not in text
    assert secret not in text
    assert str(sync_on) not in text
    assert status.read_key() == KEY
    db_session.expire_all()
    for row in db_session.query(Setting).all():
        if row.value:
            assert row.value not in text


def test_the_always_on_copy_refuses_the_setup_prompt(client, sync_off, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    monkeypatch.setattr(settings, "sync_public_host", f"https://{HOST}/api/sync")
    response = client.get(PROMPT)
    assert response.status_code == 409
    assert response.json() == {"detail": HOME_ONLY}
    assert HOST not in response.text
    assert "maestro.env" not in response.text
    assert PLACEHOLDER not in response.text
