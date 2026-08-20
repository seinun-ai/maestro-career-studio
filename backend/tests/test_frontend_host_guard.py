"""The frontend's half of the DNS-rebinding defence.

The backend has rejected a forged Host since the 2026-08-04 review, and
SECURITY.md called that "the DNS-rebinding defence". It defended the backend's
own port only. Users open Next on :3000, whose catch-all `/api` route proxies
to the zero-auth backend and REBUILDS the outbound request — deleting the
inbound Host and letting the runtime set a trusted one. So the backend could
never see the attacker's authority, and a hostile domain rebound to 127.0.0.1
was same-origin with the entire career record. These tests pin the missing half.

Two things are checked here and they fail differently:

1. **The comparison is executed**, not read. `frontend/lib/allowed-hosts.mjs`
   is dependency-free ESM precisely so `node` can run it, because the bugs that
   matter in a host allowlist are logic bugs — a `startsWith` that admits
   `localhost.evil.example`, a port split that mishandles IPv6. A source-text
   test cannot see any of them.
2. **The file conventions are named correctly.** Next 16 renamed the
   `middleware` file convention to `proxy`, so a `frontend/middleware.ts` is
   silently ignored — a security control that looks present and never runs.
   That one IS a source-text check, because the failure is a filename.

The module is plain `.mjs` rather than `.mts` on purpose: type stripping would
tie this test to a Node version, and a security test that skips on an older
runtime is a security test that is not running.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
HOST_MODULE = FRONTEND / "lib" / "allowed-hosts.mjs"


pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to execute the host guard"
)


def _run_guard(cases: list[tuple[str | None, str]]) -> list[bool]:
    """Execute isAllowedHost() in Node against the DEFAULT allowlist."""
    script = f"""
    import {{ isAllowedHost, DEFAULT_ALLOWED_HOSTS }} from {json.dumps(str(HOST_MODULE))};
    const cases = {json.dumps([c[0] for c in cases])};
    console.log(JSON.stringify(cases.map((h) => isAllowedHost(h, DEFAULT_ALLOWED_HOSTS))));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"node failed:\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


# (host header, why it is in the list)
ALLOWED_CASES = [
    ("localhost", "the documented dev host"),
    ("localhost:3000", "the port varies and is not the thing being lied about"),
    ("127.0.0.1", "the other documented host"),
    ("127.0.0.1:3000", "same, with the published port"),
    ("[::1]", "IPv6 loopback keeps its brackets"),
    ("[::1]:3000", "IPv6 loopback with a port"),
    ("LOCALHOST", "the Host header is case-insensitive"),
    ("  localhost  ", "surrounding whitespace is not a different host"),
]

REFUSED_CASES = [
    ("evil.example", "the plain rebinding case"),
    ("localhost.evil.example", "a SUFFIX attack — `startsWith` would admit it"),
    ("evil-localhost", "a PREFIX attack — `endsWith` would admit it"),
    ("notlocalhost", "`includes` would admit it"),
    ("localhost:3000.evil.example", "the port position is not a free-text field"),
    ("", "an empty Host names nothing"),
    (None, "a missing Host names nothing"),
    ("localhost:abc", "a non-numeric port is a malformed authority"),
    ("a:b:c", "two colons without brackets is malformed, not IPv6"),
    ("[::1", "an unterminated IPv6 literal is malformed"),
]


@pytest.mark.parametrize("host,why", ALLOWED_CASES)
def test_hosts_we_serve_on_are_allowed(host, why):
    assert _run_guard([(host, why)]) == [True], why


@pytest.mark.parametrize("host,why", REFUSED_CASES)
def test_every_other_host_is_refused(host, why):
    assert _run_guard([(host, why)]) == [False], why


def test_the_allowlist_is_configurable_for_a_reverse_proxy():
    """`ALLOWED_HOSTS` has always been configurable; its frontend twin must be too.

    Without this a reverse-proxy user follows the documented backend setup and
    then gets a 400 from Next on every request, with nothing naming the cause.
    """
    script = f"""
    import {{ allowedHostsFromEnv, isAllowedHost }} from {json.dumps(str(HOST_MODULE))};
    const allowed = allowedHostsFromEnv({{ FRONTEND_ALLOWED_HOSTS: "studio.lan, localhost" }});
    console.log(JSON.stringify({{
      configured: isAllowedHost("studio.lan:8080", allowed),
      stillDefault: isAllowedHost("localhost", allowed),
      notListed: isAllowedHost("127.0.0.1", allowed),
    }}));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout.strip().splitlines()[-1])

    assert got["configured"] is True
    assert got["stillDefault"] is True
    # Setting the var REPLACES the defaults rather than extending them, matching
    # how maestro_cs_extension_ids behaves on the backend.
    assert got["notListed"] is False


def test_an_empty_env_value_falls_back_instead_of_locking_everyone_out():
    """`VAR: ${VAR:-}` in compose injects an empty string, not an omission.

    The backend learned this the hard way (config.scrub_empty_env). Here the
    failure would be a frontend that refuses every request it receives.
    """
    script = f"""
    import {{ allowedHostsFromEnv }} from {json.dumps(str(HOST_MODULE))};
    console.log(JSON.stringify(allowedHostsFromEnv({{ FRONTEND_ALLOWED_HOSTS: "   " }})));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr

    assert json.loads(result.stdout.strip().splitlines()[-1]) == [
        "localhost", "127.0.0.1", "[::1]",
    ]


# --- the file-convention half ----------------------------------------------


def test_the_host_check_lives_in_proxy_ts_not_middleware_ts():
    """Next 16 renamed `middleware` to `proxy`; the old name is silently ignored.

    This is the whole reason the check is duplicated into the API route below:
    a control whose entire existence depends on a framework filename fails
    silently when the framework renames it, and this repo's AGENTS.md exists
    because that has already happened here more than once.
    """
    assert (FRONTEND / "proxy.ts").exists(), (
        "frontend/proxy.ts is missing — the Host check is not running"
    )
    assert not (FRONTEND / "middleware.ts").exists(), (
        "frontend/middleware.ts is the Next 15 name and does nothing in Next 16"
    )


def test_proxy_declares_no_matcher_that_could_exclude_the_api_route():
    """Proxy runs on every route by default; the docs' example matcher drops /api.

    `/api/*` is the path that reaches the zero-auth backend, so a matcher here
    would have to be read very carefully. Absent is the safe state.
    """
    source = (FRONTEND / "proxy.ts").read_text()

    # Keyed on the DECLARATION, not the word: a matcher only takes effect via an
    # exported `config` object, and the word itself appears in this file's own
    # comment explaining why there isn't one.
    assert "export const config" not in source, (
        "proxy.ts grew a config export — verify its matcher still covers "
        "/api/:path* before deleting this assertion"
    )


def test_the_api_route_checks_the_host_itself():
    """Defence in depth: this handler deletes the inbound Host before forwarding.

    Keyed on the CALL EXPRESSION, not the identifier. `assert "isAllowedHost" in
    source` was the first version of this test and it was vacuous: the import
    line satisfies it, so deleting the entire check from the handler body left
    the test green. The mutation pass is what found that — the import survives
    every deletion of the code that uses it.
    """
    source = (FRONTEND / "app" / "api" / "[...path]" / "route.ts").read_text()

    call = 'isAllowedHost(req.headers.get("host")'
    assert call in source, (
        "the /api route no longer checks the inbound Host itself; proxy.ts "
        "alone is one framework rename away from silence"
    )
    # The check must precede the header rebuild, or it is guarding nothing.
    assert source.index(call) < source.index('headers.delete("host")')


def test_both_readers_share_one_definition():
    """Two copies of an allowlist drift; one of them then admits what the other refuses."""
    for relpath in ("proxy.ts", "app/api/[...path]/route.ts"):
        source = (FRONTEND / relpath).read_text()
        assert "lib/allowed-hosts.mjs" in source, relpath
