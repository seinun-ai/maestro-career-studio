"""sync.sh --pair --code obtains a missing key without putting the code in shell output."""

import json
import subprocess

import pytest

from tests import test_native_scripts as native_tests
from tests.test_native_scripts import (
    FAKE_HTTP, SYNC_KEY, assert_sync_safe, posted_round, run_sync, setup_home,
)

native_home = native_tests.native_home

CODE = "0123-4567-89AB-CDEF"
USAGE = "Usage: sync.sh [--now | --pair [--code <code>] [--accept-profile-overwrite]]"


PAIR_HTTP = '''
original_post = Opener.post
def pairing_post(self, request, url):
    records = Path(os.environ["NATIVE_TEST_RECORDS"])
    order = records / "pair-order.json"
    paths = json.loads(order.read_text()) if order.exists() else []
    paths.append(url.rsplit("/api/", 1)[1])
    order.write_text(json.dumps(paths))
    if url.endswith("/api/sync-setup/enroll"):
        assert request.get_method() == "POST" and not request.has_header("Authorization")
        sent = json.loads(request.data.decode())
        (records / "enroll.json").write_text(json.dumps(sent))
        import sys
        (records / "helper-argv.json").write_text(json.dumps(sys.argv))
        body = json.loads(os.environ.get("NATIVE_TEST_ENROLL", '{"ok": true}'))
        if body.get("ok") is True:
            key = Path(os.environ["SYNC_KEY_FILE"])
            key.write_text("synthetic-sync-key-do-not-print\\n")
            key.chmod(0o600)
        return Response(json.dumps(body).encode())
    return original_post(self, request, url)
Opener.post = pairing_post
'''


def prepare(ctx):
    setup_home(ctx)
    modules = ctx.records.parent / "modules"
    (modules / "sitecustomize.py").write_text(FAKE_HTTP + PAIR_HTTP)


def order(ctx):
    return json.loads((ctx.records / "pair-order.json").read_text())


def enrolled(ctx):
    return json.loads((ctx.records / "enroll.json").read_text())


def run_with(ctx, *args, stdin=None):
    return subprocess.run(
        ["bash", str(native_tests.NATIVE / "sync.sh"), *args], cwd="/", env=dict(ctx.env),
        capture_output=True, text=True, timeout=45, input=stdin)


def test_pair_enrolls_then_runs_pairing_round(native_home):
    ctx = native_home
    prepare(ctx)
    result = run_with(ctx, "--pair", "--code", CODE)
    assert result.returncode == 0, result.stderr
    assert order(ctx) == ["sync-setup/enroll", "sync/round"]
    assert enrolled(ctx) == {"code": CODE}
    assert (ctx.home / "sync-key").stat().st_mode & 0o777 == 0o600
    assert posted_round(ctx)["body"]["pair"] is True
    assert CODE not in result.stdout + result.stderr
    assert_sync_safe(result, ctx)


def test_code_from_stdin_is_posted_and_not_printed(native_home):
    ctx = native_home
    prepare(ctx)
    result = run_with(ctx, "--pair", "--code", "-", stdin=CODE + "\n")
    assert result.returncode == 0, result.stderr
    assert enrolled(ctx) == {"code": CODE}
    assert CODE not in result.stdout + result.stderr
    assert_sync_safe(result, ctx)


def test_the_helper_argv_does_not_contain_a_stdin_code(native_home):
    ctx = native_home
    prepare(ctx)
    result = run_with(ctx, "--pair", "--code", "-", stdin=CODE + "\n")
    assert result.returncode == 0, result.stderr
    recorded = json.loads((ctx.records / "helper-argv.json").read_text())
    assert recorded
    assert CODE not in json.dumps(recorded)
    assert enrolled(ctx) == {"code": CODE}


@pytest.mark.parametrize("args", [
    ("--code", CODE),
    ("--pair", "--code"),
    ("--now", "--code", CODE),
    ("--code",),
])
def test_code_without_pair_or_a_value_is_a_usage_error(native_home, args):
    ctx = native_home
    prepare(ctx)
    result = run_with(ctx, *args)
    assert result.returncode == 1
    assert USAGE in result.stderr
    assert CODE not in result.stdout + result.stderr
    assert not (ctx.records / "enroll.json").exists()
    assert not (ctx.records / "round.json").exists()


def test_manual_key_skips_enrollment(native_home):
    ctx = native_home
    prepare(ctx)
    (ctx.home / "sync-key").write_text(SYNC_KEY)
    result = run_sync(ctx, "--pair", "--accept-profile-overwrite")
    assert result.returncode == 0
    assert order(ctx) == ["sync/round"]
    assert posted_round(ctx)["body"]["accept_profile_overwrite"] is True
    assert_sync_safe(result, ctx)


def test_a_key_already_present_does_not_post_the_code(native_home):
    ctx = native_home
    prepare(ctx)
    (ctx.home / "sync-key").write_text(SYNC_KEY)
    result = run_with(ctx, "--pair", "--code", CODE)
    assert result.returncode == 0, result.stderr
    assert order(ctx) == ["sync/round"]
    assert not (ctx.records / "enroll.json").exists()
    assert CODE not in result.stdout + result.stderr
    assert_sync_safe(result, ctx)


@pytest.mark.parametrize("outcome", ["needs_person", "transient"])
def test_failed_enrollment_does_not_pair_or_print_secrets(native_home, outcome):
    ctx = native_home
    prepare(ctx)
    sentence = "Pairing didn't work. Show a pairing code on your laptop and try again."
    ctx.env["NATIVE_TEST_ENROLL"] = json.dumps({
        "ok": False, "outcome": outcome, "detail": sentence, "key": SYNC_KEY, "code": CODE})
    result = run_with(ctx, "--pair", "--code", CODE)
    assert result.returncode == 1
    assert sentence in result.stderr
    assert order(ctx) == ["sync-setup/enroll"]
    assert not (ctx.records / "round.json").exists()
    assert CODE not in result.stdout + result.stderr
    assert_sync_safe(result, ctx)
