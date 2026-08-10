import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.autofill_field_observation import AutofillFieldObservation
from app.services import autofill_telemetry
from tests.extension_harness import extension_source


def _client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _obs(**overrides):
    base = {
        "label": "How did you hear about us?",
        "kind": "select",
        "host": "boards.greenhouse.io",
        "outcome": "no_rule",
        "rule_id": None,
        "options": ["LinkedIn", "Referral", "Other"],
    }
    base.update(overrides)
    return base


def _batch(observations, action="profile_fill"):
    return {
        "page_host": "boards.greenhouse.io",
        "action": action,
        "observations": observations,
    }


def _rows(db_session):
    return db_session.scalars(select(AutofillFieldObservation)).all()


def test_batch_insert_creates_one_row_per_signature(db_session):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="First Name",
                        kind="text",
                        rule_id="first_name",
                        options=None,
                        outcome="filled",
                    ),
                    _obs(),
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204
    rows = _rows(db_session)
    assert len(rows) == 2
    by_label = {r.label: r for r in rows}
    name = by_label["First Name"]
    assert name.kind == "text"
    assert name.host == "boards.greenhouse.io"
    assert name.rule_id == "first_name"
    assert name.seen_count == 1
    assert name.outcomes == {"filled": 1}
    assert len(name.signature_hash) == 64
    assert [m["new"] for m in name.session_marks] == [True]
    select_row = by_label["How did you hear about us?"]
    assert select_row.options == ["LinkedIn", "Referral", "Other"]
    assert select_row.rule_id is None


def test_same_signature_twice_in_one_batch_collapses_to_one_row(db_session):
    # Python-side dedupe BEFORE upsert — with autoflush=False two adds for the
    # same unique key in one flush would both INSERT (SYSTEM.md §12).
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="Email", kind="text", options=None, outcome="filled"),
                    _obs(
                        label="  email ",
                        kind="text",
                        options=None,
                        outcome="corrected",
                    ),
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204
    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].seen_count == 2
    assert rows[0].outcomes == {"filled": 1, "corrected": 1}
    assert len(rows[0].session_marks) == 1  # one mark per BATCH, not per observation


def test_repost_same_batch_bumps_counters_not_rows(db_session):
    client = _client(db_session)
    batch = _batch([_obs()])
    try:
        client.post("/api/autofill/telemetry", json=batch)
        client.post("/api/autofill/telemetry", json=batch)
    finally:
        app.dependency_overrides.clear()

    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].seen_count == 2
    assert rows[0].outcomes == {"no_rule": 2}
    assert [m["new"] for m in rows[0].session_marks] == [True, False]


def test_outcome_counter_merge_across_batches(db_session):
    client = _client(db_session)
    try:
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [_obs(label="Phone", kind="text", options=None, outcome="filled")]
            ),
        )
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="Phone",
                        kind="text",
                        options=None,
                        outcome="corrected",
                    )
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].outcomes == {"filled": 1, "corrected": 1}


def test_missing_source_is_an_accepted_outcome(db_session):
    """A field we have a rule for but no profile answer is NOT a coverage gap.

    Before this outcome existed the extension deleted valueless rules from its
    table, so the field fell through to `no_rule` and looked identical to a
    label nothing matched. That collapse is what made it impossible to tell
    whether expanding the profile would help.
    """
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="Desired salary",
                        kind="text",
                        options=None,
                        outcome="missing_source",
                        rule_id="salary",
                    )
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    row = _rows(db_session)[0]
    assert row.outcomes == {"missing_source": 1}
    assert row.rule_id == "salary"


def _payload_of_every_send_telemetry_call(src: str) -> list[str]:
    """The OBSERVATIONS argument of every `sendTelemetry(action, obs)` call.

    Paren-balanced rather than regex, because the calls this exists to read span
    several lines and nest three deep:

        sendTelemetry("ai_fill",
          batch.map((question) => observationFor(question,
            produced ? "ai_unaligned" : "ai_unanswered")));

    The first argument is dropped, and that is not cosmetic: it holds the ACTION
    (`"ai_fill"`, `"profile_fill"`, `"applied_detection"`), which is a different
    vocabulary — `TelemetryBatch.action` — and would be posted as an outcome by
    the test below and 422.
    """
    payloads = []
    for match in re.finditer(r"\bsendTelemetry\(", src):
        depth, i = 1, match.end()
        while i < len(src) and depth:
            depth += (src[i] == "(") - (src[i] == ")")
            i += 1
        # Everything after the first TOP-LEVEL comma: the observations argument
        # and any that follow it.
        args, comma = src[match.end() : i - 1], None
        depth = 0
        for j, ch in enumerate(args):
            depth += (ch in "([{") - (ch in ")]}")
            if ch == "," and depth == 0:
                comma = j
                break
        if comma is not None:
            payloads.append(args[comma + 1 :])
    return payloads


def _outcomes_emitted_by_the_extension() -> set[str]:
    """String literals the extension source can actually put in an observation.

    SCANNED, not listed. A hand-maintained list is exactly how `eeo_disabled`
    stayed missing from the contract: someone adds an emitter, nobody
    remembers the roster. Four emission shapes, because there are four:

      1. `observe(input, kind, label, rule, <expr>)` — a literal or a ternary.
      2. The value that BECOMES an observation's outcome, whether written as an
         object key (`outcome: <expr>,`) or bound to a name first
         (`const outcome = <expr>;`). Both forms, because the AI path shares one
         observation builder between its two call sites and passes the outcome
         in as an argument — with only the `outcome:` form scanned, this
         function silently went from 14 literals to 12 and the floor below is
         what caught it. Matching the NAME rather than the syntax is what keeps
         the roster honest across that kind of refactor.
      3. `valueHolds`, whose resolved string is passed straight to `observe`
         as a variable, so site 1 sees no literal for it at all.
      4. The observations argument of a `sendTelemetry(...)` call. Added at Task
         19 and MEASURED there: the widget's builder takes the outcome as a
         parameter and stores it with shorthand (`outcome,`), and its four call
         sites pass a ternary inline without ever binding a name — so shapes 1-3
         see nothing at all in `content/widget.js`. Scanning the payload finds
         them wherever inside it they are written, which is the property that
         survives the next refactor of the same kind. It is also the shape that
         found `applied_detected`/`applied_dismissed` while the applied-
         detection watcher lived, invisible to every earlier scan.

    Shapes 1-3 are kept rather than replaced: `agent.js` builds observations and
    RETURNS them to the widget, so its emitters never appear inside a
    `sendTelemetry(` call at all.
    """
    src = extension_source()
    regions = [
        *re.findall(r"\bobserve\([^()]*?,\s*([^()]*?)\)", src),
        *re.findall(r"\boutcome\s*[:=]\s*(.*?)(?:;\n|,\n|\n\s*\})", src, re.S),
        *re.findall(r"const valueHolds = .*?\n  \}\);", src, re.S),
        *_payload_of_every_send_telemetry_call(src),
    ]
    return {lit for region in regions for lit in re.findall(r'"([a-z_]+)"', region)}


def test_outcomes_the_extension_already_emits_are_all_accepted(db_session):
    """Every outcome string reachable in the extension source must be in the Literal.

    `extra="forbid"` plus a Literal means ONE unlisted outcome 422s the whole
    batch, and sendTelemetry swallows the error — so an outcome the extension
    emits but the contract does not know silently destroys every observation
    from that page, not just its own. `eeo_disabled` was exactly that: emitted
    since the EEO opt-in landed, never listed, and the opt-in is OFF by
    default, so any page with an EEO section reported nothing at all.
    """
    client = _client(db_session)
    emitted = sorted(_outcomes_emitted_by_the_extension())
    # The scan is the test, so it gets its own floor: a regex that silently
    # stops matching would otherwise turn this green by finding nothing. Zero
    # slack, deliberately — raise it whenever a real emitter is added, never to
    # accommodate one the scan stopped seeing.
    #
    # 16 before Task 19, when the AI vocabulary was read out of `sidepanel.js`.
    # Deleting the panel took those four away and adding `content/widget.js` to
    # EXTENSION_SOURCES did NOT bring them back — measured, 12 either way —
    # because the widget writes them in a shape shapes 1-3 cannot see. Shape 4
    # restored the four and found the applied-detection pair on top: 18.
    # Retiring the applied-detection watcher took its pair back out: 16.
    assert len(emitted) >= 16, emitted
    assert {
        "eeo_disabled",
        "missing_source",
        "filled_normalized",
        "ai_no_stick",
        # The misalignment guard, emitted ONLY from `content/widget.js`, whose
        # emitters are the ones shapes 1-3 are blind to — so this membership
        # check is what keeps shape 4 from being quietly deleted as redundant.
        "ai_unaligned",
    } <= set(emitted), emitted
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label=f"Field {outcome}", options=None, outcome=outcome)
                    for outcome in emitted
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    assert len(_rows(db_session)) == len(emitted)


def test_policy_blocked_is_emitted_by_the_extension_and_accepted(db_session):
    """Was forward-declared; the deny-list that emits it has since landed.

    Both halves are asserted here because they were added a round apart and
    only the pair is meaningful. The contract listing an outcome nothing sends
    reads like a leftover someone deletes; the extension sending one the
    contract does not list is worse than a dropped row — extra="forbid" plus a
    Literal 422s the WHOLE batch, and sendTelemetry swallows the error, so
    every observation from that page dies with it.
    """
    assert "policy_blocked" in _outcomes_emitted_by_the_extension()
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="Electronic signature",
                        kind="text",
                        options=None,
                        outcome="policy_blocked",
                    )
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    assert _rows(db_session)[0].outcomes == {"policy_blocked": 1}


def test_applied_detection_batch_is_accepted(db_session):
    """Declared BEFORE any client emitted it — and kept after the emitter went.

    The applied-detection watcher was retired 2026-07-28, but this contract is
    frozen additive-only (see the schema module docstring): an extension
    installed out-of-band may still carry the emitter, and stored rows carry
    the vocabulary either way, so the backend keeps accepting it.

    `extra="forbid"` plus two Literals means one unlisted action or outcome
    422s the WHOLE batch, and sendTelemetry swallows the error unconditionally
    — so dropping the vocabulary would silently destroy every observation
    from an older client's page, not just these rows.
    `eeo_disabled` is the precedent: emitted for a whole round, never listed,
    and the pages carrying it reported nothing at all.
    """
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="Did you apply?",
                        kind="text",
                        options=None,
                        outcome="applied_detected",
                    ),
                    _obs(
                        label="Did you apply? (dismissed)",
                        kind="text",
                        options=None,
                        outcome="applied_dismissed",
                    ),
                ],
                action="applied_detection",
            ),
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    assert {row.label: row.outcomes for row in _rows(db_session)} == {
        "Did you apply?": {"applied_detected": 1},
        "Did you apply? (dismissed)": {"applied_dismissed": 1},
    }


def test_applied_detection_outcomes_do_not_move_the_fill_success_rate(db_session):
    """Neutral by DERIVATION — and the derivation is what has to hold.

    NEUTRAL_OUTCOMES is computed as the Literal minus the success and failure
    sets, so adding these two to the contract and to neither set is what makes
    them neutral. Pinned rather than trusted: an edit to either set would
    otherwise silently reclassify "the user confirmed they applied" as a fill
    success or a rule failure. The per-kind rate on the Analytics coverage card
    is a rate over ATTEMPTED WRITES, and neither of these is a write at all —
    counting them either way corrupts a figure already recorded.
    """
    assert {"applied_detected", "applied_dismissed"} <= autofill_telemetry.NEUTRAL_OUTCOMES

    client = _client(db_session)
    try:
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="First Name", kind="text", options=None, outcome="filled"),
                    _obs(label="Desired salary", kind="text", options=None, outcome="no_rule"),
                ]
            ),
        )
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="Applied?", kind="text", options=None, outcome="applied_detected"),
                    _obs(label="Not applied?", kind="text", options=None, outcome="applied_dismissed"),
                ],
                action="applied_detection",
            ),
        )
        summary = client.get("/api/autofill/telemetry/summary").json()
    finally:
        app.dependency_overrides.clear()

    text = next(entry for entry in summary["by_kind"] if entry["kind"] == "text")
    # Four observations stored, two counted: the rate is over the fill attempts.
    assert summary["totals"]["observations"] == 4
    assert (text["success"], text["failure"], text["success_rate"]) == (1, 1, 0.5)
    # ...and neither shows up as a top failure to go write a rule for.
    assert [failure["label"] for failure in summary["top_failures"]] == ["Desired salary"]


def test_ai_unaligned_is_accepted_and_does_not_score_as_a_fill_failure(db_session):
    """The AI batch came back unsplittable, so nothing was written.

    Declared before the emitter for the reason at the top of the schema: a value
    the extension sends and the Literal does not know 422s the WHOLE batch, and
    sendTelemetry swallows it.

    Neutral by DERIVATION, and pinned so an edit to either set cannot reclassify
    it. This one matters more than most: the alternative the extension used to
    have was to report the other N-1 questions `ai_unanswered`, which IS in
    FAILURE_OUTCOMES — so a splitting bug in the model's reply charged up to
    seven rule failures per click and dragged a per-kind rate the module header
    declares frozen. The fill path did nothing wrong here; it declined to write.
    """
    assert "ai_unaligned" in autofill_telemetry.NEUTRAL_OUTCOMES

    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="Why us?", kind="textarea", options=None, outcome="ai_unaligned"),
                    _obs(label="Why now?", kind="textarea", options=None, outcome="ai_unaligned"),
                ],
                action="ai_fill",
            ),
        )
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="Cover letter", kind="textarea", options=None, outcome="filled"),
                    _obs(label="Salary", kind="textarea", options=None, outcome="no_rule"),
                ]
            ),
        )
        summary = client.get("/api/autofill/telemetry/summary").json()
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    textarea = next(e for e in summary["by_kind"] if e["kind"] == "textarea")
    assert summary["totals"]["observations"] == 4
    assert (textarea["success"], textarea["failure"], textarea["success_rate"]) == (1, 1, 0.5)
    # ...and an unaligned batch never becomes a "go write a rule" recommendation.
    assert [failure["label"] for failure in summary["top_failures"]] == ["Salary"]


def test_a_signal_row_is_stored_and_changes_nothing_in_the_summary(db_session):
    """The other half of the applied-detection decision: `kind: "signal"`.

    An applied-detection event is not a form field, and before this kind
    existed there was no way for it to say so — it would have had to arrive as
    `text`, becoming a field signature on the coverage card: another signature,
    another observation, possibly another host, a `by_kind` entry, and a
    novelty mark feeding the "coverage saturated — you can turn it off"
    recommendation.

    Both halves are asserted here because both have to hold at once: the row
    IS stored (the detection channel is not silently dropped), and the summary
    is byte-identical to the one taken before it arrived.
    """
    client = _client(db_session)
    try:
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="First Name", kind="text", options=None, outcome="filled"),
                    _obs(label="Desired salary", kind="text", options=None, outcome="no_rule"),
                ]
            ),
        )
        before = client.get("/api/autofill/telemetry/summary").json()

        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="applied detection",
                        kind="signal",
                        host="jobs.lever.co",
                        options=None,
                        outcome="applied_detected",
                    )
                ],
                action="applied_detection",
            ),
        )
        after = client.get("/api/autofill/telemetry/summary").json()
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 204, resp.text
    stored = {row.label: row.kind for row in _rows(db_session)}
    assert stored["applied detection"] == "signal"
    assert after == before


def test_unknown_observation_key_is_rejected_422(db_session):
    # Privacy backstop: a stray value/answer key must never be accepted.
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch([{**_obs(), "value": "typed user data"}]),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _rows(db_session) == []


def test_unknown_outcome_and_kind_rejected_422(db_session):
    client = _client(db_session)
    try:
        bad_outcome = client.post(
            "/api/autofill/telemetry",
            json=_batch([_obs(outcome="exploded")]),
        )
        bad_kind = client.post(
            "/api/autofill/telemetry",
            json=_batch([_obs(kind="canvas")]),
        )
    finally:
        app.dependency_overrides.clear()
    assert bad_outcome.status_code == 422
    assert bad_kind.status_code == 422


def test_concurrent_first_sighting_merges_instead_of_500(db_session, monkeypatch):
    # A concurrent request inserts the same signature between our SELECT (which
    # misses) and our flush. Simulate by creating the row first, then forcing
    # only the next request's INITIAL signature lookup to miss so it takes the
    # INSERT path and hits the unique constraint. It must recover and merge into
    # the winner's row — not raise IntegrityError / 500 and lose the batch.
    client = _client(db_session)
    try:
        first = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [_obs(label="Race", kind="text", options=None, outcome="filled")]
            ),
        )
        assert first.status_code == 204

        real_scalar = db_session.scalar
        state = {"forced": False}

        def flaky_scalar(*args, **kwargs):
            if not state["forced"]:
                state["forced"] = True
                return None  # pretend the row is not visible to us yet
            return real_scalar(*args, **kwargs)

        monkeypatch.setattr(db_session, "scalar", flaky_scalar)

        second = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [_obs(label="Race", kind="text", options=None, outcome="corrected")]
            ),
        )
        assert second.status_code == 204
    finally:
        app.dependency_overrides.clear()

    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].seen_count == 2
    assert rows[0].outcomes == {"filled": 1, "corrected": 1}
    assert [m["new"] for m in rows[0].session_marks] == [True, False]


def test_oversize_option_text_rejected_422(db_session):
    # A single option string over the cap 422s at the schema — not stored capped.
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch([_obs(options=["LinkedIn", "x" * 201])]),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _rows(db_session) == []


def test_too_many_options_rejected_422(db_session):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch([_obs(options=[f"opt{i}" for i in range(31)])]),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _rows(db_session) == []


def test_oversize_label_rejected_422(db_session):
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch([_obs(label="L" * 201)]),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _rows(db_session) == []


def test_oversize_batch_rejected_422(db_session):
    # More than 200 observations in one batch 422s — no silent truncation.
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [_obs(label=f"F{i:03d}", options=None, outcome="filled") for i in range(201)]
            ),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _rows(db_session) == []


def test_host_and_option_texts_stored_stripped(db_session):
    # Server-side belt over the schema: host + each option text are stripped.
    client = _client(db_session)
    try:
        resp = client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(
                        label="Strip Me",
                        kind="select",
                        host="  boards.greenhouse.io  ",
                        options=["  LinkedIn  ", "Referral"],
                        outcome="no_rule",
                    )
                ]
            ),
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 204
    row = _rows(db_session)[0]
    assert row.host == "boards.greenhouse.io"
    assert row.options == ["LinkedIn", "Referral"]


def test_session_marks_capped_at_50(db_session):
    client = _client(db_session)
    batch = _batch(
        [_obs(label="Cap Test", kind="text", options=None, outcome="filled")]
    )
    try:
        client.post("/api/autofill/telemetry", json=batch)
        row = _rows(db_session)[0]
        row.session_marks = [
            {"at": f"2026-07-01T00:00:{i:02d}+00:00", "new": False}
            for i in range(50)
        ]
        db_session.commit()
        client.post("/api/autofill/telemetry", json=batch)
    finally:
        app.dependency_overrides.clear()

    row = _rows(db_session)[0]
    assert len(row.session_marks) == 50
    assert row.session_marks[0]["at"] == "2026-07-01T00:00:01+00:00"  # oldest dropped


# --- DELETE /api/autofill/telemetry -------------------------------------
#
# Capture could be stopped but never undone: POST and GET /summary were the
# whole surface. The stored rows carry `host` and `first_seen_at`, so what
# accumulates is a record of WHICH COMPANIES were applied to and WHEN -- value
# -free, still personal. Stopping capture does not remove that; this does.


def test_clear_deletes_every_row_and_reports_the_count(db_session):
    client = _client(db_session)
    try:
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [
                    _obs(label="First Name", kind="text", options=None, outcome="filled"),
                    _obs(),
                ]
            ),
        )
        client.post(
            "/api/autofill/telemetry",
            json=_batch(
                [_obs(label="Phone", kind="text", options=None, outcome="filled")],
            ),
        )
        assert len(_rows(db_session)) == 3

        resp = client.delete("/api/autofill/telemetry")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    # The count is the point of the body: a destructive control that cannot say
    # what it destroyed is one the user has to take on faith.
    assert resp.json() == {"deleted": 3}
    assert _rows(db_session) == []


def test_clear_leaves_the_summary_genuinely_empty(db_session):
    # Not just row-free: the summary is what the Analytics card reads, so a
    # clear that left totals standing would read as "nothing was deleted".
    client = _client(db_session)
    try:
        client.post("/api/autofill/telemetry", json=_batch([_obs()]))
        assert client.get("/api/autofill/telemetry/summary").json()["totals"][
            "signatures"
        ] == 1

        client.delete("/api/autofill/telemetry")
        summary = client.get("/api/autofill/telemetry/summary").json()
    finally:
        app.dependency_overrides.clear()

    assert summary["totals"] == {"signatures": 0, "observations": 0, "hosts": 0}


def test_clear_on_an_empty_table_is_a_no_op_not_an_error(db_session):
    # The button is reachable when there is nothing to clear, and double-clicking
    # it must not 404 or 500.
    client = _client(db_session)
    try:
        resp = client.delete("/api/autofill/telemetry")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}


def test_clear_does_not_disable_capture(db_session):
    # Deleting history is not the same decision as opting out, and conflating
    # them would silently answer a question the user did not ask. The toggle
    # lives in the extension; a clear must leave the next batch storing again.
    client = _client(db_session)
    try:
        client.post("/api/autofill/telemetry", json=_batch([_obs()]))
        client.delete("/api/autofill/telemetry")
        client.post("/api/autofill/telemetry", json=_batch([_obs()]))
    finally:
        app.dependency_overrides.clear()

    rows = _rows(db_session)
    assert len(rows) == 1
    # A fresh first sighting, not a resurrected counter.
    assert rows[0].seen_count == 1
    assert [m["new"] for m in rows[0].session_marks] == [True]
