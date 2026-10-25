import base64
import json
import urllib.parse

import pytest

from app.config import settings


def _cursor_config(value):
    link = urllib.parse.urlparse(value)
    config = urllib.parse.parse_qs(link.query)["config"][0]
    return json.loads(base64.b64decode(config))


def _vscode_config(value):
    return json.loads(urllib.parse.unquote(value.split("?", 1)[1]))


def test_connect_composes_every_client_for_the_full_profile(client, monkeypatch):
    monkeypatch.setattr(settings, "maestro_cs_public_backend_url", "http://localhost:8001")
    response = client.get("/api/setup/connect")
    assert response.status_code == 200
    body = response.json()
    url = "http://localhost:8001/mcp"
    assert body["backend_url"] == "http://localhost:8001"
    assert body["mcp_url"] == url
    by_id = {c["id"]: c for c in body["clients"]}
    assert set(by_id) == {
        "claude-code", "codex", "codex-app", "cursor", "vscode", "claude-desktop", "other",
    }
    assert by_id["claude-code"]["value"] == (
        f"claude mcp add --scope user --transport http maestro-career-studio {url}"
    )
    assert by_id["codex"]["value"] == f"codex mcp add maestro-career-studio --url {url}"
    cursor = urllib.parse.urlparse(by_id["cursor"]["value"])
    assert cursor.scheme == "cursor"
    assert cursor.netloc == "anysphere.cursor-deeplink"
    assert cursor.path == "/mcp/install"
    assert urllib.parse.parse_qs(cursor.query)["name"] == ["maestro-career-studio"]
    assert _cursor_config(by_id["cursor"]["value"]) == {"url": url}
    vs = by_id["vscode"]["value"]
    assert vs.startswith("vscode:mcp/install?")
    assert _vscode_config(vs) == {
        "name": "maestro-career-studio", "type": "http", "url": url,
    }
    assert by_id["other"]["value"] == url
    assert by_id["other"]["label"] == "Any MCP agent"
    assert by_id["claude-desktop"]["kind"] == "download"
    assert by_id["claude-desktop"]["value"] == "/api/setup/connect/bundle"
    assert [p["name"] for p in body["profiles"]] == [
        "full", "profile", "hunt", "tailor", "apply", "track", "templates",
    ]
    for profile in body["profiles"]:
        suffix = "" if profile["name"] == "full" else f"/{profile['name']}"
        assert profile["url"] == f"{url}{suffix}"


@pytest.mark.parametrize("old, new", [("career", "profile"), ("explore", "track")])
def test_an_old_set_name_gets_the_new_sets_url(client, old, new):
    body = client.get("/api/setup/connect", params={"profile": old}).json()
    assert body["mcp_url"].endswith(f"/mcp/{new}")


@pytest.mark.parametrize("profile", ["profile", "hunt", "tailor", "apply", "track", "templates"])
def test_a_profile_rewrites_every_value(client, profile):
    response = client.get("/api/setup/connect", params={"profile": profile})
    assert response.status_code == 200
    body = response.json()
    assert body["mcp_url"].endswith(f"/mcp/{profile}")
    for entry in body["clients"]:
        if entry["id"] == "cursor":
            assert _cursor_config(entry["value"]) == {"url": body["mcp_url"]}
        elif entry["id"] == "vscode":
            assert _vscode_config(entry["value"])["url"] == body["mcp_url"]
        elif entry["kind"] != "download":
            assert body["mcp_url"] in entry["value"]


def test_codex_app_carries_the_profiles_url(client):
    body = client.get("/api/setup/connect", params={"profile": "hunt"}).json()
    row = next(c for c in body["clients"] if c["id"] == "codex-app")
    assert row == {
        "id": "codex-app", "label": "Codex app", "kind": "steps", "value": body["mcp_url"],
    }
    assert row["value"].endswith("/mcp/hunt")


def test_an_unknown_profile_is_a_422(client):
    assert client.get("/api/setup/connect", params={"profile": "nope"}).status_code == 422


def test_the_public_backend_url_strips_trailing_slashes(client, monkeypatch):
    monkeypatch.setattr(settings, "maestro_cs_public_backend_url", "http://localhost:8123///")
    body = client.get("/api/setup/connect").json()
    assert body["backend_url"] == "http://localhost:8123"
    assert body["mcp_url"] == "http://localhost:8123/mcp"


def test_the_bundle_downloads_when_present_and_404s_with_a_hint_when_not(
    client, tmp_path, monkeypatch,
):
    bundle = tmp_path / "b.mcpb"
    monkeypatch.setattr(settings, "mcpb_bundle_path", bundle)
    response = client.get("/api/setup/connect/bundle")
    assert response.status_code == 404
    assert response.json()["detail"] == (
        "The Claude Desktop bundle (mcpb/maestro-career-studio.mcpb) "
        "is not available on this install."
    )
    assert client.get("/api/setup/connect").json()["bundle_available"] is False
    bundle.write_bytes(b"PK\x03\x04fake")
    response = client.get("/api/setup/connect/bundle")
    assert response.status_code == 200
    assert response.content == b"PK\x03\x04fake"
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="maestro-career-studio.mcpb"'
    )
    assert client.get("/api/setup/connect").json()["bundle_available"] is True


def test_a_directory_is_not_an_available_bundle(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mcpb_bundle_path", tmp_path)
    assert client.get("/api/setup/connect").json()["bundle_available"] is False
    assert client.get("/api/setup/connect/bundle").status_code == 404


def test_a_uv_install_shows_the_connect_command_for_claude_desktop(client, monkeypatch):
    monkeypatch.setattr(settings, "maestro_install", "uv")
    body = client.get("/api/setup/connect").json()
    desktop = next(c for c in body["clients"] if c["id"] == "claude-desktop")
    assert desktop == {
        "id": "claude-desktop", "label": "Claude Desktop", "kind": "command",
        "value": "maestro connect claude-desktop",
    }
    others = {c["id"]: c for c in body["clients"] if c["id"] != "claude-desktop"}
    assert others["claude-code"]["value"].startswith("claude mcp add --scope user --transport http ")
    assert others["cursor"]["kind"] == "deeplink"


@pytest.mark.parametrize("install", ["", "docker", "UV "])
def test_any_other_install_keeps_the_claude_desktop_bundle_download(client, monkeypatch, install):
    monkeypatch.setattr(settings, "maestro_install", install)
    body = client.get("/api/setup/connect").json()
    desktop = next(c for c in body["clients"] if c["id"] == "claude-desktop")
    assert desktop["kind"] == "download"
    assert desktop["value"] == "/api/setup/connect/bundle"


def test_the_claude_code_command_carries_the_user_scope_in_every_profile(client):
    for profile in ("full", "hunt"):
        body = client.get("/api/setup/connect", params={"profile": profile}).json()
        row = next(c for c in body["clients"] if c["id"] == "claude-code")
        assert row["value"] == (
            f"claude mcp add --scope user --transport http maestro-career-studio {body['mcp_url']}"
        )
