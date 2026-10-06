"""sync.sh --pair obtains a missing key without putting it in shell output."""

import json

import pytest

from tests import test_native_scripts as native_tests
from tests.test_native_scripts import (
    FAKE_HTTP, SYNC_KEY, assert_sync_safe, posted_round, run_sync, setup_home,
)

native_home = native_tests.native_home


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


def test_pair_enrolls_then_runs_pairing_round(native_home):
    ctx = native_home
    prepare(ctx)
    result = run_sync(ctx, "--pair")
    assert result.returncode == 0, result.stderr
    assert order(ctx) == ["sync-setup/enroll", "sync/round"]
    assert (ctx.home / "sync-key").stat().st_mode & 0o777 == 0o600
    assert posted_round(ctx)["body"]["pair"] is True
    assert_sync_safe(result, ctx)


def test_manual_key_skips_enrollment(native_home):
    ctx = native_home
    prepare(ctx)
    (ctx.home / "sync-key").write_text(SYNC_KEY)
    result = run_sync(ctx, "--pair", "--accept-profile-overwrite")
    assert result.returncode == 0
    assert order(ctx) == ["sync/round"]
    assert posted_round(ctx)["body"]["accept_profile_overwrite"] is True
    assert_sync_safe(result, ctx)


@pytest.mark.parametrize("outcome", ["needs_person", "transient"])
def test_failed_enrollment_does_not_pair_or_print_secrets(native_home, outcome):
    ctx = native_home
    prepare(ctx)
    sentence = "Pairing isn't open on your laptop. Click Allow pairing for 10 minutes there."
    ctx.env["NATIVE_TEST_ENROLL"] = json.dumps({
        "ok": False, "outcome": outcome, "detail": sentence, "key": SYNC_KEY})
    result = run_sync(ctx, "--pair")
    assert result.returncode == 1
    assert sentence in result.stderr
    assert order(ctx) == ["sync-setup/enroll"]
    assert not (ctx.records / "round.json").exists()
    assert_sync_safe(result, ctx)
