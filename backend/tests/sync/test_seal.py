"""Seal round trips and every rejection. Failures carry an empty Broken."""

import base64
import hashlib
import hmac
import threading

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.services.sync.seal import (
    ENROLL_TO_HOME,
    ENROLL_TO_REMOTE,
    HEADER,
    REPLAY_SECONDS,
    SKEW_SECONDS,
    TO_HOME,
    TO_REMOTE,
    VERSION,
    Broken,
    ReplayCache,
    canonical_query,
    check_header,
    derive,
    open_request,
    open_response,
    request_aad,
    seal_request,
    seal_response,
)

SECRET = "sync-key-example"
PEER = "2:7:machine-a"
PATH = "/api/sync/pull"
NOW = 1_700_000_000.0
# Independent of derive(): HKDF-SHA256, salt b"maestro-sync", info TO_HOME, secret above.
_DERIVE_VECTOR = bytes.fromhex(
    "d801cdca7a167dc102d3f47e8e31f9675f49448063c9699749a5f6856a650a6d")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(secret: str, label: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"maestro-sync", info=label).derive(
        secret.encode("utf-8"))


def _broken(call) -> Broken:
    with pytest.raises(Broken) as caught:
        call()
    assert caught.value.args == ()
    assert str(caught.value) == ""
    assert caught.value.__cause__ is None
    return caught.value


def _flip_field(header: str, index: int) -> str:
    parts = header.split(".")
    raw = bytearray(_unb64(parts[index]))
    raw[0] ^= 0x01
    parts[index] = _b64(bytes(raw))
    return ".".join(parts)


def _flip_byte(wire: bytes) -> bytes:
    raw = bytearray(wire)
    raw[0] ^= 0x01
    return bytes(raw)


def _seal(body: bytes, **kwargs):
    args = {"method": "POST", "path": PATH, "query": "", "peer": PEER, "label": TO_HOME,
            "now": NOW, "secret": SECRET}
    args.update(kwargs)
    return seal_request(args.pop("secret"), args.pop("method"), args.pop("path"), args.pop("query"),
                        body, args.pop("peer"), label=args.pop("label"), now=args.pop("now"))


def _check(header: str, **kwargs):
    args = {"method": "POST", "path": PATH, "query": "", "peer": PEER, "label": TO_HOME,
            "now": NOW, "replay": None, "secret": SECRET}
    args.update(kwargs)
    passed = {}
    if "not_before" in kwargs:
        passed["not_before"] = args.pop("not_before")
    return check_header(args.pop("secret"), args.pop("method"), args.pop("path"), args.pop("query"),
                        header, args.pop("peer"), label=args.pop("label"), now=args.pop("now"),
                        replay=args.pop("replay"), **passed)


def test_labels_skew_and_header_name_are_fixed():
    assert VERSION == "2"
    assert HEADER == "X-Maestro-Seal"
    assert SKEW_SECONDS == 300
    assert REPLAY_SECONDS == 600
    assert TO_HOME == b"maestro-sync v2 remote->home"
    assert TO_REMOTE == b"maestro-sync v2 home->remote"
    assert ENROLL_TO_HOME == b"maestro-sync v2 enroll remote->home"
    assert ENROLL_TO_REMOTE == b"maestro-sync v2 enroll home->remote"


def test_derive_is_deterministic_hkdf_and_labels_differ():
    assert derive(SECRET, TO_HOME) == derive(SECRET, TO_HOME)
    assert derive(SECRET, b"maestro-sync v2 remote->home") == _DERIVE_VECTOR
    assert len(derive(SECRET, TO_HOME)) == 32
    assert derive(SECRET, TO_HOME) != derive(SECRET, TO_REMOTE)
    assert derive(SECRET, TO_HOME) != derive("other-secret", TO_HOME)
    assert derive(SECRET, ENROLL_TO_HOME) != derive(SECRET, ENROLL_TO_REMOTE)
    assert derive(SECRET, ENROLL_TO_HOME) != derive(SECRET, TO_HOME)


def test_canonical_query_sorts_keys_keeps_blanks_and_is_value_sensitive():
    assert canonical_query("b=2&a=1") == "a=1&b=2"
    assert canonical_query("b=&a=1") == "a=1&b="
    assert canonical_query("a=2&a=1") == canonical_query("a=1&a=2") == "a=1&a=2"
    assert canonical_query("a=1") != canonical_query("a=2")
    assert canonical_query("") == ""


def test_request_aad_binds_each_component_in_order():
    assert request_aad("post", PATH, "b=2&a=1", "1700000000", "rid", PEER) == (
        b"POST\n/api/sync/pull\na=1&b=2\n1700000000\nrid\n2:7:machine-a")


def test_header_mac_and_ciphertext_use_the_spec_aad_and_keys():
    body = b'{"title":"SENTINEL-TITLE"}'
    header, wire, rid = seal_request(SECRET, "Post", PATH, "b=2&a=1", body, PEER, now=NOW)

    assert header.startswith("2.")
    assert header.count(".") == 5
    assert "=" not in header
    assert b"SENTINEL" not in header.encode() + wire
    parts = header.split(".")
    assert parts[5] == ""
    assert parts[2] == rid
    aad = "\n".join(["POST", PATH, "a=1&b=2", "1700000000", rid, PEER]).encode()
    mac = hmac.new(_hkdf(SECRET, TO_HOME + b" header"), aad, hashlib.sha256).digest()[:16]
    assert _unb64(parts[4]) == mac
    assert AESGCM(_hkdf(SECRET, TO_HOME)).decrypt(_unb64(parts[3]), wire, aad) == body


def test_empty_plaintext_keeps_the_tag_in_the_header_and_round_trips():
    header, wire, rid = _seal(b"")

    assert wire == b""
    parts = header.split(".")
    assert parts[5] != ""
    aad = "\n".join(["POST", PATH, "", "1700000000", rid, PEER]).encode()
    assert AESGCM(_hkdf(SECRET, TO_HOME)).decrypt(_unb64(parts[3]), _unb64(parts[5]), aad) == b""
    opened = open_request(SECRET, _check(header), b"")
    assert opened == b""
    _broken(lambda: open_request(SECRET, _check(header), b"\x00"))


def test_nonempty_plaintext_round_trips_only_from_the_body():
    body = b'{"ok":true}'
    header, wire, rid = _seal(body)

    assert header.endswith(".")
    assert body not in wire
    ok = _check(header)
    assert open_request(SECRET, ok, wire) == body
    _broken(lambda: open_request(SECRET, ok, b""))


def test_method_case_path_peer_and_query_are_bound_and_query_order_is_not():
    body = b"bound"
    header, wire, _rid = _seal(body, method="post", query="b=&a=1&a=2")

    ok = _check(header, method="POST", query="a=2&a=1&b=")
    assert open_request(SECRET, ok, wire) == body
    _broken(lambda: _check(header, method="PUT"))
    _broken(lambda: _check(header, path="/api/sync/push"))
    _broken(lambda: _check(header, peer="2:7:other"))
    _broken(lambda: _check(header, query="a=2&a=9&b="))
    _broken(lambda: _check(header, peer=""))


def test_an_empty_peer_is_still_bound():
    header, wire, _rid = _seal(b"p", peer="")

    assert open_request(SECRET, _check(header, peer=""), wire) == b"p"
    _broken(lambda: _check(header, peer=PEER))


@pytest.mark.parametrize("delta", [300, -300])
def test_a_timestamp_three_hundred_seconds_off_is_accepted(delta):
    body = b"edge"
    header, wire, _rid = _seal(body, now=NOW + delta)

    assert open_request(SECRET, _check(header), wire) == body


@pytest.mark.parametrize("delta", [301, -301])
def test_a_timestamp_three_hundred_one_seconds_off_is_broken(delta):
    header, _wire, rid = _seal(b"stale", now=NOW + delta)
    cache = ReplayCache()

    _broken(lambda: _check(header, replay=cache))
    assert cache.seen(rid, NOW) is False


def test_a_tampered_timestamp_inside_the_window_is_broken():
    header, _wire, _rid = _seal(b"ts")
    parts = header.split(".")
    parts[1] = str(int(parts[1]) + 1)

    _broken(lambda: _check(".".join(parts)))


def test_a_tampered_request_id_or_mac_is_broken():
    header, _wire, _rid = _seal(b"fields")

    _broken(lambda: _check(_flip_field(header, 2)))
    _broken(lambda: _check(_flip_field(header, 4)))


def test_a_tampered_nonce_passes_the_mac_and_fails_open():
    header, wire, _rid = _seal(b"nonce-bound")

    ok = _check(_flip_field(header, 3))
    _broken(lambda: open_request(SECRET, ok, wire))


def test_a_tampered_header_tag_fails_open_for_an_empty_body():
    header, _wire, _rid = _seal(b"")

    ok = _check(_flip_field(header, 5))
    _broken(lambda: open_request(SECRET, ok, b""))


def test_a_tampered_body_is_broken():
    header, wire, _rid = _seal(b'{"ok":1}')
    ok = _check(header)

    _broken(lambda: open_request(SECRET, ok, _flip_byte(wire)))


def test_wrong_secret_or_direction_is_broken():
    header, wire, _rid = _seal(b"dirs")

    _broken(lambda: _check(header, secret="other-secret"))
    _broken(lambda: _check(header, label=TO_REMOTE))
    _broken(lambda: _check(header, label=ENROLL_TO_HOME))
    ok = _check(header)
    _broken(lambda: open_request(SECRET, ok, wire, label=TO_REMOTE))


def test_version_one_and_malformed_base64_are_broken():
    header, _wire, rid = _seal(b"ver")
    cache = ReplayCache()
    parts = header.split(".")
    parts[3] = "@@@@"

    _broken(lambda: _check("1" + header[1:], replay=cache))
    assert cache.seen(rid, NOW) is False
    _broken(lambda: _check(".".join(parts)))
    _broken(lambda: _check(""))
    _broken(lambda: _check("2.1.2.3.4"))
    _broken(lambda: _check(header + ".extra"))


def test_bad_or_absent_mac_does_not_open_a_body(monkeypatch):
    header, _wire, _rid = _seal(b"unread-body")
    opened = []

    def decrypt(self, nonce, data, associated_data):
        opened.append(data)
        raise AssertionError("ciphertext was opened")

    monkeypatch.setattr(AESGCM, "decrypt", decrypt)
    _broken(lambda: _check(_flip_field(header, 4)))
    _broken(lambda: _check(""))
    _broken(lambda: _check("not-a-seal"))
    assert opened == []


def test_unreadable_headers_still_compare_a_mac(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(left, right):
        calls.append((bytes(left), bytes(right)))
        return real(left, right)

    monkeypatch.setattr("app.services.sync.seal.hmac.compare_digest", spy)
    samples = ["", "not-a-seal", "1.1.2.3.4.5", "2.@@@.@@@.@@@.@@@."]
    for sample in samples:
        before = len(calls)
        _broken(lambda sample=sample: _check(sample))
        assert len(calls) == before + 1
        assert calls[-1][0] != calls[-1][1]
    stale, _wire, _rid = _seal(b"stale", now=NOW + 301)
    before = len(calls)
    _broken(lambda: _check(stale))
    assert len(calls) == before + 1


def test_a_valid_mac_is_checked_with_compare_digest(monkeypatch):
    header, wire, _rid = _seal(b"abc")
    calls = []
    real = hmac.compare_digest

    def spy(left, right):
        calls.append((bytes(left), bytes(right)))
        return real(left, right)

    monkeypatch.setattr("app.services.sync.seal.hmac.compare_digest", spy)
    ok = _check(header)

    assert len(calls) == 1
    assert calls[0][0] == calls[0][1]
    assert len(calls[0][0]) == 16
    assert open_request(SECRET, ok, wire) == b"abc"


def test_a_bad_mac_does_not_register_the_request_id():
    cache = ReplayCache()
    header, wire, rid = _seal(b"keep")

    _broken(lambda: _check(_flip_field(header, 4), replay=cache))
    assert open_request(SECRET, _check(header, replay=cache), wire) == b"keep"
    assert cache.seen(rid, NOW) is True


def test_the_request_id_is_registered_when_the_mac_verifies_before_open():
    cache = ReplayCache()
    header, wire, rid = _seal(b"spent")

    ok = _check(header, replay=cache)
    assert cache.seen(rid, NOW) is True
    _broken(lambda: open_request(SECRET, ok, _flip_byte(wire)))
    _broken(lambda: _check(header, replay=cache))


def test_replay_window_starts_at_check_time_not_the_sealed_timestamp():
    cache = ReplayCache()
    header, _wire, rid = _seal(b"clock", now=NOW - SKEW_SECONDS)

    _check(header, replay=cache)
    assert cache.seen(rid, NOW + REPLAY_SECONDS - 0.001) is True
    assert cache.seen(rid, NOW + REPLAY_SECONDS) is False


def test_a_stamp_earlier_than_not_before_is_broken_and_leaves_the_rid_free():
    """Registering the rid before the start check would make the retry a replay."""
    cache = ReplayCache()
    header, wire, _rid = _seal(b"early", now=NOW - 1)

    _broken(lambda: _check(header, replay=cache, not_before=float(NOW)))
    ok = _check(header, replay=cache, not_before=float(NOW - 1))
    assert open_request(SECRET, ok, wire) == b"early"
    _broken(lambda: _check(header, replay=cache, not_before=float(NOW - 1)))


def test_a_stamp_equal_to_not_before_is_accepted():
    header, wire, _rid = _seal(b"same", now=NOW)

    ok = _check(header, replay=None, not_before=float(NOW))
    assert open_request(SECRET, ok, wire) == b"same"


def test_a_fractional_start_rejects_a_stamp_from_that_second():
    """Truncating the start to a whole second would accept an earlier stamp."""
    header, _wire, _rid = _seal(b"part", now=NOW)
    later, later_wire, _rid = _seal(b"next", now=NOW + 1)

    _broken(lambda: _check(header, not_before=NOW + 0.5))
    ok = _check(later, not_before=NOW + 0.5, now=NOW + 1)
    assert open_request(SECRET, ok, later_wire) == b"next"


def test_not_before_rejects_an_enroll_stamp_the_same_way():
    header, wire, _rid = _seal(b"", label=ENROLL_TO_HOME, now=NOW - 1)

    _broken(lambda: _check(header, label=ENROLL_TO_HOME, not_before=float(NOW)))
    ok = _check(header, label=ENROLL_TO_HOME, not_before=float(NOW - 1))
    assert open_request(SECRET, ok, wire, label=ENROLL_TO_HOME) == b""


def test_a_replayed_request_id_is_broken_and_a_new_one_is_not():
    cache = ReplayCache()
    first = _seal(b"once")
    second = _seal(b"twice")

    assert first[2] != second[2]
    assert open_request(SECRET, _check(first[0], replay=cache), first[1]) == b"once"
    _broken(lambda: _check(first[0], replay=cache))
    assert open_request(SECRET, _check(second[0], replay=cache), second[1]) == b"twice"


def test_omitted_now_seals_for_the_current_time():
    import time

    before = time.time()
    header, wire, _rid = seal_request(SECRET, "POST", PATH, "", b"hi", PEER)
    after = time.time()
    ts = int(header.split(".")[1])

    assert before - 1 <= ts <= after + 1
    ok = check_header(SECRET, "POST", PATH, "", header, PEER, replay=None)
    assert open_request(SECRET, ok, wire) == b"hi"


def test_response_ciphertext_binds_request_id_and_status():
    body = b'{"password":"SENTINEL-BODY"}'
    header, wire = seal_response(SECRET, "rid-1", 409, body)

    assert header.startswith("2.")
    assert len(header.split(".")) == 2
    assert "=" not in header
    assert b"SENTINEL" not in header.encode() + wire
    nonce = _unb64(header.split(".")[1])
    plain = AESGCM(_hkdf(SECRET, TO_REMOTE)).decrypt(nonce, wire, b"rid-1\n409")
    assert plain == body
    assert open_response(SECRET, "rid-1", 409, header, wire) == body


def test_response_round_trip_includes_an_empty_body():
    header, wire = seal_response(SECRET, "rid-1", 204, b"")

    assert wire
    assert open_response(SECRET, "rid-1", 204, header, wire) == b""


def test_a_response_with_another_rid_status_or_label_is_broken():
    header, wire = seal_response(SECRET, "rid-1", 200, b"{}")

    _broken(lambda: open_response(SECRET, "rid-2", 200, header, wire))
    _broken(lambda: open_response(SECRET, "rid-1", 201, header, wire))
    _broken(lambda: open_response(SECRET, "rid-1", 200, header, _flip_byte(wire)))
    _broken(lambda: open_response(SECRET, "rid-1", 200, "1." + header.split(".", 1)[1], wire))
    _broken(lambda: open_response(SECRET, "rid-1", 200, "2.!!!!", b"abc"))
    _broken(lambda: open_response(SECRET, "rid-1", 200, header, wire, label=TO_HOME))
    _broken(lambda: open_response("other-secret", "rid-1", 200, header, wire))


def test_enroll_labels_round_trip_and_reject_the_sync_labels():
    header, wire, rid = _seal(b"enroll", label=ENROLL_TO_HOME)

    ok = _check(header, label=ENROLL_TO_HOME)
    assert open_request(SECRET, ok, wire, label=ENROLL_TO_HOME) == b"enroll"
    _broken(lambda: _check(header, label=TO_HOME))
    _broken(lambda: _check(header, label=ENROLL_TO_REMOTE))
    resp_header, resp_wire = seal_response(SECRET, rid, 200, b"payload", label=ENROLL_TO_REMOTE)
    assert open_response(SECRET, rid, 200, resp_header, resp_wire, label=ENROLL_TO_REMOTE) == (
        b"payload")
    _broken(lambda: open_response(SECRET, rid, 200, resp_header, resp_wire, label=TO_REMOTE))


def test_broken_str_and_repr_omit_the_secret_and_plaintext(caplog):
    secret = "SENTINEL-KEY-9f3a"
    body = b"SENTINEL-PLAINTEXT"
    header, wire, rid = seal_request(secret, "POST", PATH, "a=1", body, PEER, now=NOW)
    caplog.set_level(0)
    failures = []

    def collect(call):
        failures.append(_broken(call))

    collect(lambda: check_header("nope", "POST", PATH, "a=1", header, PEER, now=NOW, replay=None))
    ok = check_header(secret, "POST", PATH, "a=1", header, PEER, now=NOW, replay=None)
    collect(lambda: open_request(secret, ok, _flip_byte(wire)))
    collect(lambda: open_response(secret, rid, 200, "2.!!!!", wire))
    for exc in failures:
        assert "SENTINEL" not in str(exc)
        assert "SENTINEL" not in repr(exc)
        if exc.__context__ is not None:
            assert "SENTINEL" not in str(exc.__context__)
            assert "SENTINEL" not in repr(exc.__context__)
    assert "SENTINEL" not in caplog.text


def test_a_checked_header_does_not_carry_the_secret():
    header, _wire, _rid = seal_request("SENTINEL-KEY-9f3a", "POST", PATH, "", b"x", PEER, now=NOW)

    ok = check_header("SENTINEL-KEY-9f3a", "POST", PATH, "", header, PEER, now=NOW, replay=None)
    assert "SENTINEL" not in repr(ok)


def test_replay_cache_prunes_at_ten_minutes_without_extending_the_window():
    cache = ReplayCache()

    assert cache.seen("rid", 0.0) is False
    assert cache.seen("rid", 599.999) is True
    assert cache.seen("rid", 600.0) is False


def test_replay_cache_caps_at_one_hundred_thousand_by_dropping_the_oldest():
    cache = ReplayCache()

    assert cache.seen("zzz", 50.0) is False
    assert cache.seen("aaa", 50.0) is False
    for i in range(100_000 - 2):
        assert cache.seen(f"{i:05d}", 50.0) is False
    assert cache.seen("zzz", 50.0) is True
    assert cache.seen("overflow", 50.0) is False
    assert cache.seen("aaa", 50.0) is True
    assert cache.seen("zzz", 50.0) is False


def test_replay_cache_counts_one_first_sight_under_contention():
    misses = 0
    for trial in range(20):
        cache = ReplayCache()
        barrier = threading.Barrier(8)
        found = []
        guard = threading.Lock()

        def worker(stamp=float(trial)):
            barrier.wait()
            result = cache.seen("same-rid", stamp)
            with guard:
                found.append(result)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        misses += found.count(False)
    assert misses == 20


def test_check_header_requires_replay():
    header, _wire, _rid = _seal(b"explicit")

    with pytest.raises(TypeError, match="replay"):
        check_header(SECRET, "POST", PATH, "", header, PEER, now=NOW)


def test_two_request_seals_of_one_body_use_different_nonces_and_ciphertexts():
    body = b'{"same":true}'
    first, second = _seal(body), _seal(body)

    assert first[0].split(".")[3] != second[0].split(".")[3]
    assert first[1] != second[1]
    assert first[1]


def test_two_response_seals_of_one_body_use_different_nonces_and_ciphertexts():
    body = b'{"same":true}'
    one_header, one_wire = seal_response(SECRET, "rid-1", 200, body)
    two_header, two_wire = seal_response(SECRET, "rid-1", 200, body)

    assert one_header.split(".")[1] != two_header.split(".")[1]
    assert one_wire != two_wire


def test_a_future_skewed_seal_cannot_be_replayed_at_the_far_edge():
    body = b"ahead"
    header, wire, _rid = _seal(body, now=NOW + SKEW_SECONDS)
    far = NOW + SKEW_SECONDS + SKEW_SECONDS
    fresh = ReplayCache()

    assert open_request(SECRET, _check(header, now=far, replay=fresh), wire) == body
    spent = ReplayCache()
    _check(header, replay=spent)
    _broken(lambda: _check(header, now=far, replay=spent))


@pytest.mark.parametrize(
    "stamp",
    ["²²²", "9" * 400, "9" * 5000],
    ids=["superscript-digits", "four-hundred-digits", "five-thousand-digits"],
)
def test_a_bad_timestamp_is_broken_before_any_echo(stamp, monkeypatch):
    header, _wire, rid = _seal(b"digits")
    parts = header.split(".")
    parts[1] = stamp
    bad = ".".join(parts)
    cache = ReplayCache()
    calls = []
    real = hmac.compare_digest

    def spy(left, right):
        calls.append((bytes(left), bytes(right)))
        return real(left, right)

    monkeypatch.setattr("app.services.sync.seal.hmac.compare_digest", spy)
    exc = _broken(lambda: _check(bad, replay=cache))

    assert exc.__context__ is None
    assert stamp not in repr(exc)
    assert len(calls) == 1
    assert calls[0][0] != calls[0][1]
    assert cache.seen(rid, NOW) is False


def test_an_unexpected_parser_error_is_broken(monkeypatch):
    header, wire, rid = _seal(b"plain")
    ok = _check(header)
    response_header, response_wire = seal_response(SECRET, rid, 200, b"{}")

    def boom(*_args, **_kwargs):
        raise RuntimeError("SENTINEL-PARSE")

    def expect(call):
        exc = _broken(call)
        assert exc.__context__ is None
        assert "SENTINEL" not in repr(exc)

    monkeypatch.setattr("app.services.sync.seal._parsed_header", boom)
    expect(lambda: _check(header))
    monkeypatch.setattr("app.services.sync.seal._decrypt", boom)
    expect(lambda: open_request(SECRET, ok, wire))
    monkeypatch.setattr("app.services.sync.seal._response_nonce", boom)
    expect(lambda: open_response(SECRET, rid, 200, response_header, response_wire))


def test_the_derived_key_cache_keeps_sixteen_and_drops_the_oldest():
    import app.services.sync.seal as seal_mod

    with seal_mod._KEYS_LOCK:
        saved = dict(seal_mod._KEYS)
        seal_mod._KEYS.clear()
    try:
        for i in range(16):
            seal_mod._key(f"pairing-{i}", TO_HOME)
        assert len(seal_mod._KEYS) == 16
        assert ("pairing-0", TO_HOME) in seal_mod._KEYS
        seal_mod._key("pairing-16", TO_HOME)
        assert len(seal_mod._KEYS) == 16
        assert ("pairing-0", TO_HOME) not in seal_mod._KEYS
        assert ("pairing-1", TO_HOME) in seal_mod._KEYS
        assert ("pairing-16", TO_HOME) in seal_mod._KEYS
        seal_mod._key("pairing-1", TO_HOME)
        assert ("pairing-2", TO_HOME) in seal_mod._KEYS
        assert len(seal_mod._KEYS) == 16
    finally:
        with seal_mod._KEYS_LOCK:
            seal_mod._KEYS.clear()
            seal_mod._KEYS.update(saved)
