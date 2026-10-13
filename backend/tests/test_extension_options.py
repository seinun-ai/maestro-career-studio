"""Companion address settings and the store upload archive."""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "extension"
PACK_SCRIPT = ROOT / "scripts/pack_extension.py"


@pytest.fixture
def pack_tree(tmp_path):
    assert PACK_SCRIPT.is_file(), "extension pack script is missing"
    (tmp_path / "scripts").mkdir()
    shutil.copy2(PACK_SCRIPT, tmp_path / "scripts/pack_extension.py")
    shutil.copytree(EXTENSION, tmp_path / "extension")
    (tmp_path / "backend").mkdir()
    shutil.copy2(ROOT / "backend/pyproject.toml", tmp_path / "backend/pyproject.toml")
    return tmp_path


def pack(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/pack_extension.py"), *args],
        cwd=root / "backend", capture_output=True, text=True, check=False,
    )


def test_pack_refuses_version_mismatch_before_writing_zip(pack_tree):
    path = pack_tree / "extension/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["version"] = "99.0.0"
    path.write_text(json.dumps(manifest))
    done = pack(pack_tree)
    assert done.returncode != 0
    assert "version mismatch" in done.stderr.lower()
    assert not list(pack_tree.glob("dist/*.zip"))


@pytest.mark.parametrize("first_upload", [False, True])
def test_pack_key_changes_only_in_first_upload_archive(pack_tree, first_upload):
    path = pack_tree / "extension/manifest.json"
    original = path.read_bytes()
    manifest = json.loads(original)
    done = pack(pack_tree, *(["--first-upload"] if first_upload else []))
    assert done.returncode == 0, done.stderr
    archive = pack_tree / f"dist/maestro-cs-companion-{manifest['version']}.zip"
    with zipfile.ZipFile(archive) as zipped:
        bundled = json.loads(zipped.read("manifest.json"))
    assert ("key" in bundled) is not first_upload
    if not first_upload:
        assert bundled["key"] == manifest["key"]
    assert path.read_bytes() == original
    assert manifest["key"]


def test_pack_excludes_development_files_but_keeps_runtime_assets(pack_tree):
    excluded = {
        "README.md", "INTERNALS.md", "STORE_LISTING.md", ".slopconfig.json",
        ".slop-baseline.json", ".hidden", ".cache/leak.js", "tests/options.test.js",
        "shared/tests/helper.js", "shared/.hidden", "test_options.py", "options.test.js",
    }
    for relative in excluded:
        path = pack_tree / "extension" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("development only")
    done = pack(pack_tree)
    assert done.returncode == 0, done.stderr
    with zipfile.ZipFile(next(pack_tree.glob("dist/*.zip"))) as zipped:
        names = set(zipped.namelist())
        assert names.isdisjoint(excluded)
        assert {"manifest.json", "sw.js", "options.html", "options.js", "icons/128.png"} <= names
        manifest = json.loads(zipped.read("manifest.json"))
        for entry in manifest["content_scripts"]:
            assert set(entry["js"]) <= names
        assert manifest["side_panel"]["default_path"] in names


@pytest.mark.parametrize("first_upload", [False, True])
def test_two_packs_are_byte_identical_despite_source_metadata_changes(pack_tree, first_upload):
    args = ["--first-upload"] if first_upload else []
    assert pack(pack_tree, *args).returncode == 0
    archive = next(pack_tree.glob("dist/*.zip"))
    first = archive.read_bytes()
    for path in (pack_tree / "extension").rglob("*"):
        if path.is_file():
            os.utime(path, (1700000000, 1700000000))
            path.chmod(0o600)
    assert pack(pack_tree, *args).returncode == 0
    assert archive.read_bytes() == first
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            assert entry.date_time == (1980, 1, 1, 0, 0, 0)
            assert entry.external_attr == 0o644 << 16


def test_options_page_registration_and_safe_source():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest.get("options_ui") == {"page": "options.html", "open_in_tab": False}
    assert set(manifest["permissions"]) == {
        "storage", "tabs", "webNavigation", "scripting", "sidePanel",
    }
    html = (EXTENSION / "options.html").read_text()
    source = (EXTENSION / "options.js").read_text()
    assert "innerHTML" not in html + source
    # The panel's icon rule forbids decorative symbols, not copy punctuation such as ellipses.
    assert not re.search(r"[\u2190-\u21ff\u25a0-\u27bf\U0001f000-\U0001faff]", html + source)
    assert '<script src="options.js"></script>' in html
    assert "aria-live=\"polite\"" in html
    assert "backendUrl" in source and "appUrl" in source
    assert "http://localhost" not in source, "defaults must come from read_settings"
    assert "sw.js" not in source


_OPTIONS_DRIVER = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const spec = JSON.parse(fs.readFileSync(0, "utf8"));
const elements = {};
for (const id of ["settings", "backendUrl", "appUrl", "save", "test", "note", "fillLog"]) {
  elements[id] = {
    value: "", textContent: "", disabled: true, checked: false, listeners: {}, focused: false,
    addEventListener(type, handler) { this.listeners[type] = handler; },
    focus() { this.focused = true; },
  };
}
global.document = { getElementById: (id) => elements[id] };
const messages = [], writes = [], requests = [], connectingNotes = [];
const requestOptions = [], timeouts = [];
const timeout = AbortSignal.timeout.bind(AbortSignal);
AbortSignal.timeout = (milliseconds) => {
  timeouts.push(milliseconds);
  return timeout(milliseconds);
};
global.chrome = {
  runtime: { sendMessage: async (message) => {
    messages.push(message);
    if (spec.readReject) throw new Error("private runtime error");
    return spec.readRefused ? { ok: false, error: "private runtime error" }
      : { ok: true, data: spec.settings };
  } },
  storage: { sync: { set: async (values) => {
    if (spec.saveReject) throw new Error("private storage error");
    writes.push(values);
  } } },
};
global.fetch = async (url, options = {}) => {
  requests.push(url);
  requestOptions.push({
    method: options.method, headers: options.headers, body: options.body,
    hasSignal: options.signal instanceof AbortSignal,
  });
  connectingNotes.push(elements.note.textContent);
  if (spec.fetchReject) throw new Error("private network error");
  if (spec.fetchTimeout) throw new DOMException("private timeout", "TimeoutError");
  const status = spec.healthStatus ?? (spec.healthOk === false ? 503 : 200);
  return { ok: status >= 200 && status < 300, status };
};
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
(async () => {
  await new Promise(setImmediate);
  const initial = { backendUrl: elements.backendUrl.value, appUrl: elements.appUrl.value };
  for (const [key, value] of Object.entries(spec.edit || {})) elements[key].value = value;
  const initialFillLog = { checked: elements.fillLog.checked, disabled: elements.fillLog.disabled };
  if (spec.action === "toggle") {
    elements.fillLog.checked = !elements.fillLog.checked;
    await elements.fillLog.listeners.change?.({ preventDefault() {} });
    await new Promise(setImmediate);
  } else if (spec.action) {
    const [id, type] = spec.action === "save" ? ["settings", "submit"] : ["test", "click"];
    await elements[id].listeners[type]({ preventDefault() {} });
    await new Promise(setImmediate);
  }
  for (const id of spec.input || []) elements[id].listeners.input?.();
  process.stdout.write(JSON.stringify({
    initial, messages, writes, requests, requestOptions, timeouts, connectingNotes,
    note: elements.note.textContent,
    disabled: { save: elements.save.disabled, test: elements.test.disabled },
    initialFillLog,
    fillLog: { checked: elements.fillLog.checked, disabled: elements.fillLog.disabled },
  }));
})().catch((err) => { console.error(err); process.exitCode = 1; });
"""


def run_options(**overrides):
    path = EXTENSION / "options.js"
    assert path.is_file(), "options page script is missing"
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    spec = {
        "settings": {"backendUrl": "http://localhost:9123", "appUrl": "https://localhost:3123",
                     "telemetryEnabled": False, "fillMode": "rules"},
        **overrides,
    }
    done = subprocess.run([node, "-e", _OPTIONS_DRIVER, str(path)], input=json.dumps(spec),
                          capture_output=True, text=True, check=False, timeout=10)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_options_load_through_settings_message_and_save_only_address_keys():
    out = run_options(action="save", edit={"backendUrl": " https://localhost:9443/ "})
    assert out["messages"] == [{"type": "read_settings"}]
    assert out["initial"] == {
        "backendUrl": "http://localhost:9123", "appUrl": "https://localhost:3123",
    }
    assert out["writes"] == [{"backendUrl": "https://localhost:9443", "appUrl": "https://localhost:3123"}]
    assert out["note"] == "Saved."
    assert out["disabled"] == {"save": False, "test": False}


@pytest.mark.parametrize("address, expected", [
    ("https://maestro.example:9443", "Saved. The Companion now sends job pages and your answers to maestro.example."),
    ("http://100.64.0.10:8001", "Saved. The Companion now sends job pages and your answers to 100.64.0.10. This address is not encrypted."),
    ("http://localhost.example", "Saved. The Companion now sends job pages and your answers to localhost.example. This address is not encrypted."),
    ("https://xlocalhost", "Saved. The Companion now sends job pages and your answers to xlocalhost."),
])
def test_nonlocal_backend_saves_with_destination_and_encryption_notice(address, expected):
    out = run_options(action="save", edit={"backendUrl": address})
    assert out["writes"][0]["backendUrl"] == address
    assert out["note"] == expected


@pytest.mark.parametrize("address", [
    "http://localhost:8001", "http://studio.localhost:8001", "https://deep.studio.localhost",
    "http://127.0.0.1:8001", "http://[::1]:8001", "https://LOCALHOST",
])
def test_local_backend_saves_without_destination_warning(address):
    out = run_options(action="save", edit={"backendUrl": address})
    assert len(out["writes"]) == 1
    assert out["note"] == "Saved."


@pytest.mark.parametrize("address", [
    "", "localhost:8001", "ftp://localhost", "javascript:alert(1)", "http://",
    "http://localhost/api", "http://localhost/../", "http://localhost?", "http://localhost#",
    "http://user:password@localhost", "http://@localhost", "http://localhost\\api", "http://local host",
])
@pytest.mark.parametrize("key", ["backendUrl", "appUrl"])
def test_options_refuse_invalid_or_non_host_addresses(address, key):
    out = run_options(action="save", edit={key: address})
    assert out["writes"] == []
    assert "http:// or https://" in out["note"]


@pytest.mark.parametrize("address", ["http://localhost:8001", "https://example.com", "http://[::1]:8001/"])
def test_options_accept_http_hosts_and_ports(address):
    out = run_options(action="save", edit={"backendUrl": address})
    assert out["writes"][0]["backendUrl"] == address.rstrip("/")


@pytest.mark.parametrize("health", [{}, {"healthOk": False}, {"fetchReject": True}])
def test_connection_checks_current_unsaved_backend_address(health):
    out = run_options(action="test", edit={"backendUrl": "http://127.0.0.1:9001/"}, **health)
    assert out["requests"] == ["http://127.0.0.1:9001/health"]
    assert out["writes"] == []
    expected = (
        "Can't reach Maestro at http://127.0.0.1:9001." if health.get("fetchReject")
        else "Connected."
    )
    assert out["note"] == expected
    assert out["disabled"] == {"save": False, "test": False}


def test_connection_posts_json_once_to_check_extension_origin_with_five_second_timeout():
    out = run_options(action="test", healthStatus=405)
    assert out["requests"] == ["http://localhost:9123/health"]
    assert out["requestOptions"] == [{
        "method": "POST", "headers": {"Content-Type": "application/json"},
        "body": "{}", "hasSignal": True,
    }]
    assert out["timeouts"] == [5000]
    assert out["writes"] == []


@pytest.mark.parametrize("status", [200, 400, 404, 405, 500, 503])
def test_connection_accepts_any_http_status_except_extension_refusal(status):
    out = run_options(action="test", healthStatus=status)
    assert out["note"] == "Connected."
    assert out["disabled"] == {"save": False, "test": False}


def test_connection_distinguishes_extension_refusal_from_network_failure():
    out = run_options(action="test", healthStatus=403)
    assert out["note"] == (
        "Maestro at http://localhost:9123 refused this extension. "
        "Update Maestro or add this extension's ID."
    )
    assert out["disabled"] == {"save": False, "test": False}


def test_connection_timeout_keeps_unreachable_message():
    out = run_options(action="test", fetchTimeout=True)
    assert out["note"] == "Can't reach Maestro at http://localhost:9123."


def test_connecting_copy_uses_ellipsis_punctuation():
    out = run_options(action="test")
    assert out["connectingNotes"] == ["Connecting…"]


@pytest.mark.parametrize("field", ["backendUrl", "appUrl"])
@pytest.mark.parametrize("action", ["save", "test"])
def test_input_clears_previous_save_or_connection_status(field, action):
    out = run_options(action=action, input=[field])
    assert out["note"] == ""


def test_connection_never_fetches_invalid_backend_address():
    out = run_options(action="test", edit={"backendUrl": "http://localhost/api"})
    assert out["requests"] == []
    assert "http:// or https://" in out["note"]


@pytest.mark.parametrize("failure", [{"readReject": True}, {"readRefused": True}])
def test_settings_read_failure_keeps_save_disabled(failure):
    out = run_options(**failure)
    assert out["writes"] == []
    assert out["disabled"] == {"save": True, "test": True}
    assert out["note"] == "Couldn't load settings. Reopen this page to try again."


def test_settings_save_failure_is_visible():
    out = run_options(action="save", saveReject=True)
    assert out["writes"] == []
    assert out["note"] == "Couldn't save settings. Try again."
    assert out["disabled"] == {"save": False, "test": False}


@pytest.mark.parametrize("stored, checked", [(False, False), (True, True), (None, False)])
def test_fill_log_switch_shows_the_stored_choice(stored, checked):
    """The switch reflects the setting the service worker reports: on only when the
    user turned it on. The default (never chosen) reads as off."""
    settings = {"backendUrl": "http://localhost:9123", "appUrl": "https://localhost:3123",
                "telemetryEnabled": stored, "fillMode": "rules"}
    out = run_options(settings=settings)
    assert out["initialFillLog"] == {"checked": checked, "disabled": False}


@pytest.mark.parametrize("stored", [False, True])
def test_fill_log_switch_saves_only_its_own_key_at_once(stored):
    """Turning the log on or off is saved on the change itself, with no Save press,
    and writes nothing but `telemetryEnabled`: the address keys are the form's."""
    settings = {"backendUrl": "http://localhost:9123", "appUrl": "https://localhost:3123",
                "telemetryEnabled": stored, "fillMode": "rules"}
    out = run_options(settings=settings, action="toggle")
    assert out["writes"] == [{"telemetryEnabled": not stored}]
    assert out["fillLog"]["checked"] is (not stored)
    assert out["note"] == ("Fill log on." if not stored else "Fill log off.")


def test_fill_log_switch_reverts_when_the_save_fails():
    """A failed write leaves the switch showing what is actually stored."""
    out = run_options(action="toggle", saveReject=True)
    assert out["writes"] == []
    assert out["fillLog"]["checked"] is False
    assert out["note"] == "Couldn't save settings. Try again."


def test_fill_log_switch_stays_disabled_when_settings_fail_to_load():
    out = run_options(readReject=True)
    assert out["fillLog"]["disabled"] is True


def test_options_page_explains_the_fill_log_in_plain_words():
    """The disclosure sits next to the switch, in the extension's own UI: what is
    kept, where, why, and what never is."""
    html = (EXTENSION / "options.html").read_text()
    assert 'id="fillLog"' in html and 'type="checkbox"' in html
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    for phrase in ("Keep a fill log", "inside your own Maestro", "never what you type"):
        assert phrase in text, phrase

