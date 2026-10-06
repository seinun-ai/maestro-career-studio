# Full Automation Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in this session) to implement this plan task by task.

**Goal:** An opt-in Off/On setting lets the user's own agent submit an application without a
per-application yes when its final review is clean; a job-site login is kept in a local file and
handed to the agent over MCP. (The 24/7 bot-copy sync is deferred: design Part 4.)

**Owner's goal (2026-10-05), phase 4 of four:** "our application should support a fully automated
job application if that's user's wish, with appropriate settings to enable or disable." Plus:
the always-on agent app setup is deferred (design Part 4).

**Design:** `docs/plans/2026-10-05-full-automation-design.md` (approved; approach 2, the prompt
decides). It is the source of truth for scope.

**Architecture:**
- `AutoApplySettings.full_automation` (Off by default) is the one switch. The server reads it in
  three places only: the consent channel `auto` (approvals and the agent's word that a job went
  through, accepted only while On), the job-site login
  hand-off (refused while Off), and the Automations catalog (which Apply prompt it serves).
- Eligibility is stated in a new prompt, `apply-auto`, read from `get_final_review`. The server
  does not judge eligibility; it keeps enforcing the daily cap, the blocklist and the
  already-applied check on every `approved`, as today.
- The job-site login lives in `settings/secrets/job-site-login.json` (mode 0600), never in the DB.

**Tech stack:** FastAPI + Pydantic v2 + SQLAlchemy 2 (SQLite) + alembic; FastMCP + httpx (respx in
tests); Next.js 16 + React 19 + react-query; frontend pinned by `backend/tests/test_frontend_*.py`
and `node --test` for pure `lib/*.test.ts`; host scripts in Python 3 stdlib + bash.

**How this plan was checked:** Tasks 1–11 were applied to a scratch worktree (Fable 5.1, a6163e80 with Tasks 3 and 6 as amended at 0368c44e) and run: the full backend suite twice (9,202 passed, 1 skipped, with and without frontend/node_modules), every frontend ratchet (1,462), the MCP suite, `tsc`, lint, and both slop ratchets. Its eight corrections are folded in (a password echoed by a Pydantic 422, the snapshot reading the wrong DB file, one-line guardrail sentences, cache clearing, the placeholder ratchet, the settings tab anchor, the tool-count grep, the hotspot count).

**How much freedom the executor has:**

| Area | Freedom | Rule |
|---|---|---|
| Setting name `full_automation`, channel `auto`, MCP tool `get_job_site_login`, file path `settings/secrets/job-site-login.json`, the apply-auto skill id, invariant ids, every pinned UI/prompt string below | **Fixed** | Tests, docs and the owner's decisions depend on them. |
| Layout inside the design system, helper decomposition, private names, comment wording | **Moderate** | Each new function under cc 10, ≤ 50 lines, ≤ 5 params (`self`/`ctx` count). Prefer parametrized tests. Add, never replace, a pin the plan names. |
| Anything that touches the Companion (`extension/`), tailoring, filling, knock-out verdicts, or loosens a test you did not write beyond the pins named here | **Stop and report** | Prepare the patch, do not apply it. |

**Environment:** a git worktree. Read `SYSTEM.md` first (CLAUDE.md requires it).
- Python `/opt/anaconda3/bin/python3`, run from `backend/`.
- Backend suite (xdist): `/opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
- Frontend gates from `frontend/`: `npx tsc --noEmit`, `npm run lint`; pure libs `node --test lib/<x>.test.ts`.
  A pytest that runs node must use `tests/node_ts.py` (skips without node locally, fails in CI) and
  never require an npm package: CI's backend job has no `node_modules`.
- SYSTEM.md gate: `/opt/anaconda3/bin/python3 scripts/check_system_md.py` (996/1000 today; Task 12
  grooms first). Slop ratchet: `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend` (and `frontend`).
- **The repo is PUBLIC.** No competitor or real company names in code, tests, docs or commits;
  examples use Acme and Globex.

**Code facts this plan rests on (verified at 312e2f00):**
- `schemas/auto_apply.py` `AutoApplySettings` (`extra="forbid"`); `services/auto_apply_settings.py`
  `get_settings/peek_settings/set_settings` over `JsonSetting("auto_apply", ...)` (a DB `Setting`
  row is the truth; `peek` never writes); `GET/PUT /api/settings/auto-apply` in
  `routers/settings.py:243-252`; `job_search_brief._auto_apply_block` (`:84-90`).
- `services/proposals.py`: `CONSENT_REQUIRED`, `CONSENT_CHANNELS = ("chat","slack","frontend","mcp")`
  (`:51-52`); `transition()` (`:129-194`) checks the channel, `final_review` evidence, G7, reserves a
  cap slot (`_reserve_cap` → `_enforce_daily_cap`, `:122-126`, `:457-461`) and writes a
  `ConsentEvent(proposal_id, action, channel, note, evidence_manifest_json)`. `cap_status` (`:439`).
  `schemas/proposal.py:21` `ConsentPayload.channel: Literal["chat","slack","frontend","mcp"]`.
  MCP `record_consent` (`mcp_server/server.py:1878`) `channel: Literal["chat","slack","mcp"]`.
- `tests/test_proposal_state_machine.py` has `_mk_proposal`, `_final_review_evidence`,
  `_receipt_evidence`; nothing tests the cap refusing today.
- `services/automations.py`: `CARD_ORDER`, `_read_skills`, `_check_card_set` (metas must equal
  `CARD_ORDER`), `_check_no_orphans`, `load_cards()` (lru_cache), `apply_kind()` returns
  `"attended"`, `catalog()` swaps the Apply card's kind. `routers/automations.py` calls
  `automations.catalog()` with no DB. Frontend `automation-card.tsx:93` shows "Scheduled applying
  comes with full automation mode." only for the attended Apply card.
- `routers/version.py` `VersionInfo{version, git_sha, schema_revision}`; frontend
  `hooks/use-version.ts`, `components/version-banner.tsx` mounted in `app/layout.tsx:59`.
- Settings tab "agents" (`app/settings/page.tsx:81-85`): `ConnectedAgentsCard`,
  `McpWorkflowSection`, `AutoApplySection`. Copy pinned by `tests/test_frontend_agent_words.py`
  (`_CAN`, `_CANT`, `test_the_card_keeps_the_honesty_nuance`).
- `config.py`: `data_dir`, `applications_dir`, `settings_dir`, `base_resumes_dir`,
  `kb_documents_dir`; DB file `maestro_cs.sqlite3` under `data_dir`. `settings/` is gitignored.
  Exports never read `settings_dir`.
- MCP tools: `@mcp.tool(**_write(...))` + `@_guard`; the client sends `_origin_headers(origin_detail)`;
  the backend reads `WriteOrigin` (`app/write_origin.py`). Registration set and `len(tools) >= 85`
  in `mcp_server/tests/test_server.py`; profiles in `mcp_server/profiles.py`.

**Design ambiguities resolved here (do not re-decide):**
1. `get_job_site_login` takes a `proposal_id`, not a `job_id`: the audit row is a `ConsentEvent`
   (`action="login_shared"`, `channel="mcp"`, `note` = client name), which needs a proposal. It is
   refused unless full automation is On and the proposal is `accepted` or `approved`.
2. The backend route for it is `POST /api/proposals/{id}/job-site-login` (it writes an audit row)
   and requires the MCP origin header; the web app never calls it.
3. The automatic Apply prompt keeps the card id `apply-session` in the catalog (the Last ran line
   and the run log key on it); its text comes from the `apply-auto` skill file. Runs record
   `automation="apply-session"`.
4. `GET /api/automations` now reads one setting (`peek_settings`, which never writes). The
   "DB-free" wording in its docstring and in `docs/entities/others.md` becomes "reads only the
   full-automation switch".
5–7. (Removed with Tasks 7–9: snapshots and the laptop mirror are deferred.)

---

### Task 1: Pin that the server refuses past the daily cap

**Files:**
- Test: `backend/tests/test_proposal_state_machine.py` (append)

**Step 1: Write the test**

```python
def test_approve_is_refused_past_the_daily_cap(db_session):
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(AutoApplySettings(max_submissions_per_day=1), db_session)
    first, second = _mk_proposal(db_session), _mk_proposal(db_session)
    for prop in (first, second):
        prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, first, "approved", consent={"channel": "chat", "note": "yes"})
    with pytest.raises(svc.TransitionError, match="daily submission cap reached"):
        svc.transition(db_session, second, "approved", consent={"channel": "chat", "note": "yes"})
    assert second.status == "pending_review"
```

**Step 2: Run it** — `/opt/anaconda3/bin/python3 -m pytest tests/test_proposal_state_machine.py -q -k daily_cap`
Expected: PASS (it pins existing behavior; if it fails, STOP and report: the cap is broken).
If settings need `settings_dir` isolation, add the `monkeypatch.setattr(settings, "settings_dir", tmp_path)` pattern from `tests/test_filled_answers_api.py`.

**Step 3: Commit** — `git commit -m "test(proposals): pin the daily cap refusing an approval"`

---

### Task 2: The `full_automation` setting

**Files:**
- Modify: `backend/app/schemas/auto_apply.py`, `backend/app/services/job_search_brief.py:84-90`
- Modify: `frontend/lib/types.ts` (`AutoApplySettings`)
- Test: `backend/tests/test_full_automation_setting.py` (create)

**Step 1: Failing tests**

```python
"""The full-automation switch (docs/plans/2026-10-05-full-automation-design.md, Part 1)."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import job_search_brief

client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def test_full_automation_is_off_by_default_and_round_trips():
    assert client.get("/api/settings/auto-apply").json()["value"]["full_automation"] is False
    value = {**client.get("/api/settings/auto-apply").json()["value"], "full_automation": True}
    assert client.put("/api/settings/auto-apply", json={"value": value}).status_code == 200
    assert client.get("/api/settings/auto-apply").json()["value"]["full_automation"] is True


def test_the_brief_tells_agents_whether_full_automation_is_on(db_session):
    assert job_search_brief.build_brief(db_session)["auto_apply"]["full_automation"] is False
```

(If the brief's key for `_auto_apply_block` is not `"auto_apply"`, read `build_brief` and use its
real key in the test.)

**Step 2: Run** — expected FAIL (`KeyError: 'full_automation'`).

**Step 3: Implement** — in `AutoApplySettings` add, after `auto_pick_floor`:

```python
    # Phase 4 (docs/plans/2026-10-05-full-automation-design.md): when True the user's
    # agent may submit a job whose final review is clean without asking, records that yes
    # with channel "auto", and may fetch the job-site login. Off by default.
    full_automation: bool = False
```

`_auto_apply_block` adds `"full_automation": cfg.full_automation,`. `frontend/lib/types.ts`
`AutoApplySettings` adds `full_automation: boolean;`.

**Step 4: Run** the new file plus `tests/test_settings_router.py tests/test_job_search_brief*.py` — PASS.

**Step 5: Commit** — `feat(settings): the full-automation switch, off by default`

---

### Task 3: Consent channel `auto` (approve; the agent's word as proof), accepted only while On

**Files:**
- Modify: `backend/app/services/proposals.py` (`CONSENT_CHANNELS`, `transition`)
- Modify: `backend/app/schemas/proposal.py` (`ConsentPayload.channel`)
- Modify: `backend/mcp_server/server.py` (`record_consent` and `mark_submitted` channel literals + docstrings)
- Test: `backend/tests/test_proposal_state_machine.py` (append), `backend/mcp_server/tests/test_proposal_tools.py` (literal pin if one lists channels)

**Step 1: Failing tests**

```python
def _full_automation(db_session, on):
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on), db_session)


def test_auto_consent_is_refused_while_full_automation_is_off(db_session):
    _full_automation(db_session, False)
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="full automation"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})


def test_auto_consent_approves_while_on_and_is_recorded_as_auto(db_session):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "auto", "note": "clean review"})
    event = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).one()
    assert (prop.status, event.channel) == ("approved", "auto")


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_auto_consent_only_approves_or_confirms(db_session, status):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError, match="approves a job or confirms"):
        svc.transition(db_session, prop, status, consent={"channel": "auto"})


def _approved_auto(db_session):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "auto"})
    return prop


def test_in_full_automation_the_agents_word_marks_it_submitted(db_session):
    prop = _approved_auto(db_session)
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "auto", "note": "Confirmation email: application received"})
    events = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id, action="submitted").all()
    assert prop.status == "submitted" and [e.channel for e in events] == ["auto"]


def test_the_agents_word_needs_a_note_naming_the_confirmation(db_session):
    prop = _approved_auto(db_session)
    with pytest.raises(svc.TransitionError, match="what confirmed it"):
        svc.transition(db_session, prop, "submitted", attested=True,
                       consent={"channel": "auto", "note": "  "})


def test_the_agents_word_is_refused_once_full_automation_is_off(db_session):
    prop = _approved_auto(db_session)
    _full_automation(db_session, False)
    with pytest.raises(svc.TransitionError, match="full automation"):
        svc.transition(db_session, prop, "submitted", attested=True,
                       consent={"channel": "auto", "note": "Confirmation page"})
```

**Step 2: Run** — FAIL.

**Step 3: Implement** — `CONSENT_CHANNELS = ("chat", "slack", "frontend", "mcp", "auto")`; in
`transition()`, right after the channel check:

```python
    if consent and consent.get("channel") == AUTO_CHANNEL:
        _check_auto_consent(session, new_status, consent, attested)
```

with, near `CONSENT_CHANNELS`:

```python
# Full automation mode (phase 4): the agent's own yes, and its own word that a job went
# through, labelled so the ledger can tell them from the user's. The server checks only the
# switch (and that a confirmation is named); eligibility is the agent's prompt.
AUTO_CHANNEL = "auto"


def _check_auto_consent(session: Session, new_status: str, consent: dict,
                        attested: bool) -> None:
    if not (new_status == "approved" or (new_status == "submitted" and attested)):
        raise TransitionError("the auto channel only approves a job or confirms it went through")
    if new_status == "submitted" and not (consent.get("note") or "").strip():
        raise TransitionError("an automatic submit needs a note saying what confirmed it")
    if not auto_apply_settings.get_settings(session).full_automation:
        raise TransitionError("the auto channel needs full automation turned on in Settings")
```

`ConsentPayload.channel` adds `"auto"`. MCP `record_consent`: `channel: Literal["chat", "slack",
"mcp", "auto"]`; append to its docstring: "`auto` is the agent's own yes in full automation mode:
accepted only for `approved` and only while full automation is on." MCP `mark_submitted`:
`channel: Literal["chat", "slack", "mcp", "auto"]`; when `channel == "auto"` it sends
`attested=True` with the note (the agent's word, not the user's), so its body becomes
`if user_attested or channel == "auto": ...`; append to its docstring: "In full automation mode,
channel `auto` records the agent's own word that the application went through, with `note`
naming what confirmed it (the confirmation page or a confirmation email); no receipt is needed,
and it is accepted only while full automation is on." (Describe, never instruct: `_BANNED_VOICE`.)
Add MCP tests: `mark_submitted(channel="auto", note=...)` forwards `attested=True` with that
consent.

**Step 4: Run** the state-machine, proposals-router and MCP proposal-tool tests — PASS.

**Step 5: Commit** — `feat(consent): an "auto" channel, accepted only while full automation is on`

---

### Task 4: The job-site login file and its settings endpoints

**Files:**
- Create: `backend/app/services/job_site_login.py`, `backend/app/schemas/job_site_login.py`
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_job_site_login.py`

**Step 1: Failing tests**

```python
"""The job-site login: a local file, never the DB, never sent back to the web app."""

import os
import stat

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import job_site_login

client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def test_the_password_is_stored_0600_and_never_returned():
    put = client.put("/api/settings/job-site-login",
                     json={"email": "ada@example.com", "password": "s3cret-pass"})
    assert put.status_code == 200 and "s3cret-pass" not in put.text
    body = client.get("/api/settings/job-site-login").json()
    assert body == {"email": "ada@example.com", "password_set": True}
    path = job_site_login.path()
    assert path == settings.settings_dir / "secrets" / "job-site-login.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_an_email_change_keeps_the_password():
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    client.put("/api/settings/job-site-login", json={"email": "b@x.com"})
    assert job_site_login.read() == ("b@x.com", "pw-one-long")


def test_delete_clears_both():
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    assert client.delete("/api/settings/job-site-login").status_code == 204
    assert client.get("/api/settings/job-site-login").json() == {"email": None, "password_set": False}
    assert not job_site_login.path().exists()


@pytest.mark.parametrize("bad", ["short7!", "x" * 201])
def test_a_bad_password_is_refused_without_echoing_it(bad):
    put = client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": bad})
    assert put.status_code == 422 and bad not in put.text
    assert "input" not in str(put.json()["detail"])
    assert not job_site_login.path().exists()


def test_nothing_is_stored_in_the_database(db_session):
    from app.models.setting import Setting  # adjust if the model lives elsewhere
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    assert not any("pw-one-long" in (row.value or "") for row in db_session.query(Setting).all())
```

**Step 2: Run** — FAIL.

**Step 3: Implement**

`schemas/job_site_login.py`:

```python
"""The job-site login (docs/plans/2026-10-05-full-automation-design.md, Part 1)."""

from pydantic import BaseModel, ConfigDict, Field


class JobSiteLoginIn(BaseModel):
    """A PUT sets either field; a missing one keeps what is stored."""

    model_config = ConfigDict(extra="forbid")
    email: str | None = Field(default=None, max_length=320)
    # No length constraint here: a Pydantic 422 echoes the rejected input, so the password
    # would go back to the browser. The router checks the length with its own message.
    password: str | None = None


PASSWORD_MIN, PASSWORD_MAX = 8, 200


class JobSiteLoginStatus(BaseModel):
    email: str | None = None
    password_set: bool = False
```

`services/job_site_login.py`:

```python
"""The job-site login: one email and password used only for job-site accounts.

SYSTEM.md {#inv-job-site-password-local}: kept in settings/secrets/job-site-login.json (0600,
directory 0700), never in the database, exports, telemetry or logs. The web API
reports only whether a password is set; the agent gets it over MCP only while full automation is
on (routers/proposals.py job-site-login).
"""

import json
import os
from pathlib import Path

from app.config import settings

FILENAME = "job-site-login.json"


def path() -> Path:
    return Path(settings.settings_dir) / "secrets" / FILENAME


def read() -> tuple[str | None, str | None]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None
    return data.get("email"), data.get("password")


def write(email: str | None, password: str | None) -> None:
    old_email, old_password = read()
    data = {"email": email if email is not None else old_email,
            "password": password if password is not None else old_password}
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    tmp = target.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(tmp, target)


def clear() -> None:
    path().unlink(missing_ok=True)


def status() -> dict:
    email, password = read()
    return {"email": email, "password_set": bool(password)}
```

`routers/settings.py` — three routes next to `/auto-apply`:

```python
@router.get("/job-site-login", response_model=JobSiteLoginStatus)
def get_job_site_login():
    return job_site_login.status()


@router.put("/job-site-login", response_model=JobSiteLoginStatus)
def put_job_site_login(payload: JobSiteLoginIn):
    if payload.password is not None and not PASSWORD_MIN <= len(payload.password) <= PASSWORD_MAX:
        raise HTTPException(422, detail=f"The password needs {PASSWORD_MIN} to {PASSWORD_MAX} characters.")
    job_site_login.write(payload.email, payload.password)
    return job_site_login.status()


@router.delete("/job-site-login", status_code=204)
def delete_job_site_login():
    job_site_login.clear()
```

**Step 4: Run** the new tests and `tests/test_settings_router.py` — PASS. Check the request
logging middleware (if any) never logs bodies for this route; if it does, STOP and report.

**Step 5: Commit** — `feat(settings): the job-site login, a 0600 local file never in the DB`

---

### Task 5: Handing the login to the agent (MCP `get_job_site_login`)

**Files:**
- Modify: `backend/app/routers/proposals.py` (new POST route), `backend/mcp_server/client.py`,
  `backend/mcp_server/server.py`, `backend/mcp_server/profiles.py` (`APPLY_TOOLS`),
  `backend/mcp_server/tests/test_server.py` (registration set; `>= 85` → `>= 86`)
- Test: `backend/tests/test_job_site_login_handoff.py`, `backend/mcp_server/tests/test_client_job_site_login.py`

**Step 1: Failing tests** (backend)

```python
"""The agent's job-site login hand-off: full automation only, MCP only, audited."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.consent_event import ConsentEvent
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, job_site_login
from tests.test_proposal_state_machine import _mk_proposal

client = TestClient(app)
MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    job_site_login.write("ada@example.com", "pw-one-long")


def _on(db_session, on=True):
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on), db_session)


def _post(prop, headers=MCP):
    return client.post(f"/api/proposals/{prop.id}/job-site-login", headers=headers)


def test_refused_while_full_automation_is_off(db_session):
    _on(db_session, False)
    assert _post(_mk_proposal(db_session, status="accepted")).status_code == 409


def test_refused_without_the_mcp_origin(db_session):
    _on(db_session)
    assert _post(_mk_proposal(db_session, status="accepted"), headers={}).status_code == 403


def test_handed_over_and_audited_without_the_value(db_session):
    _on(db_session)
    prop = _mk_proposal(db_session, status="accepted")
    assert _post(prop).json() == {"email": "ada@example.com", "password": "pw-one-long"}
    event = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).one()
    assert (event.action, event.channel, event.note) == ("login_shared", "mcp", "claude-ai")
    assert "pw-one-long" not in (event.note or "") + str(event.evidence_manifest_json)


def test_refused_for_a_closed_proposal(db_session):
    _on(db_session)
    assert _post(_mk_proposal(db_session, status="pending_review")).status_code == 409


def test_404_when_no_password_is_set(db_session):
    _on(db_session)
    job_site_login.clear()
    assert _post(_mk_proposal(db_session, status="accepted")).status_code == 404
```

(`_mk_proposal(status=...)`: if `create_proposal` ignores `status`, set `prop.status` after
creating and commit.)

**Step 2: Run** — FAIL.

**Step 3: Implement** — in `routers/proposals.py`:

```python
@router.post("/{proposal_id}/job-site-login")
def share_job_site_login(
    proposal_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    """The job-site login for a connected agent in full automation mode. MCP only; audited."""
    if write_origin.origin != "mcp":
        raise HTTPException(403, detail="Only a connected agent can ask for the job-site login.")
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        return svc.share_job_site_login(db, prop, write_origin.detail)
    except svc.TransitionError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
```

in `services/proposals.py`:

```python
LOGIN_STATUSES = frozenset({"accepted", "approved"})


def share_job_site_login(session: Session, prop: ApplicationProposal,
                         agent: str | None) -> dict[str, str]:
    """{email, password} for an open job in full automation mode; one audit row per call
    (never the value). SYSTEM.md {#inv-job-site-password-local}."""
    if not auto_apply_settings.get_settings(session).full_automation:
        raise TransitionError("the job-site login needs full automation turned on in Settings")
    if prop.status not in LOGIN_STATUSES:
        raise TransitionError("the job-site login is for a queued or approved job")
    email, password = job_site_login.read()
    if not email or not password:
        raise LookupError("No job-site login is saved in Settings")
    session.add(ConsentEvent(proposal_id=prop.id, action="login_shared", channel="mcp", note=agent))
    session.commit()
    return {"email": email, "password": password}
```

MCP client:

```python
    def get_job_site_login(self, proposal_id: str, origin_detail: str | None = None) -> Any:
        return self._request("POST", f"/api/proposals/{proposal_id}/job-site-login",
                             headers=_origin_headers(origin_detail))
```

MCP tool (after `record_consent`):

```python
@mcp.tool(**_write("Get Job-Site Login", destructive=False, idempotent=True))
@_guard
def get_job_site_login(proposal_id: str, ctx: Context | None = None) -> Any:
    """The email and password the user saved for job-site accounts, for creating an account or
    signing in on this proposal's application site. Available only while full automation is on
    and only for a queued or approved proposal; each call is recorded (never the value). The
    value passes through the agent's AI provider, which is why it is a password the user keeps
    for job sites alone. Returns {email, password}."""
    return _client.get_job_site_login(proposal_id, origin_detail=_client_label(ctx))
```

Add `"get_job_site_login"` to `APPLY_TOOLS` and to the test registration set; `>= 86`. Client
test with respx: the POST path and the origin headers. If the tool text trips
`_BANNED_VOICE`, reword as fact.

**Step 4: Run** the new tests and `mcp_server/tests/` — PASS.

**Step 5: Commit** — `feat(mcp): get_job_site_login, full automation only, audited`

---

### Task 6: The `apply-auto` prompt and the catalog switch

**Files:**
- Create: `backend/app/automations/skills/apply-auto/SKILL.md`
- Modify: `backend/app/services/automations.py`, `backend/app/routers/automations.py`
- Modify: `backend/app/automations/skills/agent-apply-execution/SKILL.md` (one pointer line)
- Test: `backend/tests/test_automations_service.py`, `backend/tests/test_automations_router.py`

**Step 1: Failing tests** (append to `test_automations_service.py`; keep
`test_apply_is_attended_until_full_automation_exists` but rename it
`test_apply_is_attended_while_full_automation_is_off` and call `catalog(full_automation=False)`)

```python
def test_full_automation_serves_the_automatic_apply_prompt():
    cards = {c.id: c for c in automations.catalog(full_automation=True).cards}
    apply = cards["apply-session"]
    assert apply.kind == "scheduled"
    assert apply.title == "Apply automatically"
    assert apply.never == "Never submits a job whose final review shows anything to check."
    assert apply.body.startswith("# Apply automatically")
    assert "\n# Agent Apply Execution" in apply.body


@pytest.mark.parametrize("sentence", [
    "Submit without asking only when `get_final_review` shows all of these:",
    "`record_consent` with channel `auto`",
    "`mark_submitted` with channel `auto` and a `note` naming what confirmed it",
    "Work the queue the way the user has asked you to",
    "Never submit the same application twice.",
    "`request_decision` naming what blocked it",
    "Call `record_run` with automation `apply-session`",
])
def test_the_automatic_apply_guardrails(sentence):
    body = {c.id: c for c in automations.catalog(full_automation=True).cards}["apply-session"].body
    assert sentence in body
```

`test_automations_router.py`: with the auto-apply setting On (set via `set_settings` and the
`settings_dir` fixture), `GET /api/automations` returns the Apply card with `kind == "scheduled"`;
Off → `"attended"`.

Update the `skills_dir` fixture in `test_automations_service.py` to write an `apply-auto` card
too (with `include: [technique]`; it is now an expected skill), and to clear both caches
(`automations.load_cards.cache_clear()` and `automations._alternate.cache_clear()`).
Every pinned guardrail sentence sits on one line of the SKILL.md (the test does `sentence in body`).
Spell `catalog()`'s two branches out: when on, replace ONLY the `apply-session` card.

**Step 2: Run** — FAIL.

**Step 3: Implement**

`automations.py`:
- `ALTERNATES = {"apply-auto": "apply-session"}` (skill id → the card id it stands in for).
- `_check_card_set`: expected = `sorted(CARD_ORDER + tuple(ALTERNATES))`.
- `load_cards()` keeps returning the `CARD_ORDER` cards; a new cached
  `_alternate(skill_id) -> AutomationCard` builds the alternate with `id=ALTERNATES[skill_id]`.
- `apply_kind(full_automation: bool = False) -> Kind`: `"scheduled"` when on, else `"attended"`.
- `catalog(full_automation: bool = False)`: when on, replace the `apply-session` card with
  `_alternate("apply-auto")`; when off, today's behavior.

`routers/automations.py`:

```python
@router.get("", response_model=AutomationCatalog)
def get_automations(db: Annotated[Session, Depends(get_db)]) -> AutomationCatalog:
    """Reads one setting only, the full-automation switch (peek: never writes)."""
    return automations.catalog(
        full_automation=auto_apply_settings.peek_settings(db).full_automation)
```

Update its module docstring ("Read-only; reads only the full-automation switch").

`apply-auto/SKILL.md`:

```markdown
---
name: apply-auto
description: Use in Maestro CS full automation mode to work the user's queued applications in a browser and submit, without asking, each one whose final review is clean. Asks the user about everything else.
metadata:
  title: Apply automatically
  summary: Works your queued jobs and submits the ones whose final review is clean.
  kind: scheduled
  needs: [maestro, browser]
  never: Never submits a job whose final review shows anything to check.
  include: [agent-apply-execution]
---

# Apply automatically

Full automation mode is on (the brief's `auto_apply.full_automation`). If it is off, stop and say
so: this prompt is for full automation mode only.

1. **Queue.** `list_proposals(status="accepted")`.
   Work the queue the way the user has asked you to: which jobs, in what order, in batches or one by one, and how many per run.
   The daily cap in the brief is the one fixed limit; stop when it is used up.
2. **Prepare.** Tailor or render only when the linked application or its PDF is missing.
3. **Accounts.** When the site needs an account or a sign-in, `get_job_site_login(proposal_id)`
   gives the user's job-site email and password.
4. **Fill.** Answer from the user's profile, career history and saved answers. Record every page
   with `record_filled_answers`. Name the saved fact (`slot`) behind every screening answer.
5. **Check.** `get_final_review(proposal_id)`.
   Submit without asking only when `get_final_review` shows all of these:
   - the PDF is ready;
   - no knock-out conflict;
   - `flags` is empty;
   - `duplicate_submitted` is false;
   - no blocked or manual items.
6. **Submit.** Attach a screenshot of the filled form as `final_review` evidence, then
   `record_consent` with channel `auto` and action `approved`. Submit.
   Never submit the same application twice.
   Then `mark_submitted` with channel `auto` and a `note` naming what confirmed it (the confirmation page's words, or a confirmation email).
   A screenshot of the confirmation is optional. If you can't tell whether it went through, `report_failure` and
   don't submit again.
7. **Everything else.** Call `request_decision` naming what blocked it, ask the user, and move on
   to the next job. If the user says yes, record it with `record_consent` channel `chat` and
   submit as in step 6. Anything that stops you mid-form: `report_failure` with the reason, ask
   the user, and move on.
8. **Record the run.** Call `record_run` with automation `apply-session`, the outcome (`ok`;
   `partial` if a job failed; `failed` if none could be worked), and `report` with `counts`
   (`updated`: submitted; `needs_you`: parked for the user; `skipped`: declined), `digest`,
   and `job_ids` for the jobs worked.
```

`agent-apply-execution/SKILL.md`: under its opening paragraph add one line: "In full automation
mode the Apply automatically prompt (`apply-auto`) replaces the per-application yes with its own
eligibility check; everything else here still applies."

**Step 4: Run** `tests/test_automations_service.py tests/test_automations_router.py tests/test_frontend_automations.py` — PASS.

**Step 5: Commit** — `feat(automations): Apply automatically when full automation is on`

---

### Tasks 7–9: REMOVED (2026-10-05)

Snapshots, the `/api/version` mirror field and the laptop pull script are out: the owner left the
bot-copy sync mechanism undecided (design Part 4). Task numbers below are kept so the dry-run
notes still line up.

---

### Task 10: Settings — the full-automation card and the job-site login

**Files:**
- Create: `frontend/components/settings/full-automation-section.tsx`
- Modify: `frontend/app/settings/page.tsx` (mount after `ConnectedAgentsCard`), `frontend/lib/types.ts`,
  `frontend/lib/settings-tabs.ts` (`agents.anchors` gains `"full-automation"` after `"connected-agents"`;
  run `node --test lib/settings-tabs.test.ts`)
- Test: `backend/tests/test_frontend_full_automation.py`

**What it shows** (design-system components: `SettingCard`, `Switch`, `Dialog`, `Input`, `Label`,
`Button`; `GuardedLink` only; corner tokens; desktop only):
- Title **Full automation**; description: "When this is on, your connected agent submits a queued
  job without asking when its final review shows nothing to check. It asks you about the rest."
- A `Switch` labelled **Submit clean applications without asking**. Turning it On opens a
  `Dialog` titled **Turn on full automation?** with: "Your agent will submit queued jobs whose
  final review is clean, without asking each time. The daily limit still applies. You can turn
  this off at any time." and buttons **Turn on** / **Cancel**. Off needs no dialog. It PUTs
  `/api/settings/auto-apply` with the whole value and `full_automation` changed.
- While On, **Job-site login**: Email (`type="email"`, defaults to the stored email), Password
  (`type="password"`, `autoComplete="new-password"`, no placeholder: the placeholder ratchet
  forbids them; a hint between label and field, wired by `aria-describedby`:
  `password_set ? "A password is saved. Type a new one to replace it." : "At least 8 characters."`),
  **Save** (PUT; send `password` only when typed), **Clear** (DELETE). Hint:
  "Used only for job-site accounts. Your agent gets it while full automation is on, so it passes
  through your agent's AI provider. Use it for nothing else."

**Pins** (source tests, style of `test_frontend_automations.py`): the PUT path and
`full_automation`; the dialog title and **Turn on** (use the design system's `useConfirm`
dialog if it fits, else `Dialog`); `"placeholder=" not in` the card; `type="password"` and
`autoComplete="new-password"`; the password is never rendered back (no `value={...password`
from the GET); vocabulary, design-token, leave-guard and
query-error-state ratchets pass (pin any `LoadErrorState` caller in
`test_frontend_query_error_states.py`).

**Commit** — `feat(web): the full automation card and the job-site login`

---

### Task 11: The Connected agents copy

**Files:**
- Modify: `frontend/components/settings/connected-agents-card.tsx`
- Modify: `backend/tests/test_frontend_agent_words.py` (the `_CAN` item and the honesty-nuance
  pins, updated on purpose)

**Connected agents copy:**
- `_CAN` item becomes "Fill in and submit applications you queued, after your yes, or on their
  own in full automation mode."
- The paragraph becomes: "Maestro CS itself never looks for jobs or submits an application.
  Before each submit, the agent asks for your yes and records it, unless you turned on full
  automation. The daily limit below counts those yeses over the last 24 hours. The app records
  each yes but can't stop an agent, so stay with it while it applies."

Update the pins in `test_frontend_agent_words.py` to exactly these strings (and the comment above
`_CAN`).

**Commit** — `feat(web): agents can submit on their own in full automation mode`

---

### Task 12: Policy and docs

**Files:** `CONTRIBUTING.md`, `SYSTEM.md`, `SECURITY.md`, `PRIVACY.md`,
`docs/playbooks/agent-apply.md`, `docs/entities/others.md` (auto-apply, consent, Automations
paragraph), `CHANGELOG.md`, tool count 85 → 86 everywhere it is
stated (`git grep -n "85 tools\|all 85\|Every tool (85)"` outside `docs/plans` must come back
empty). Known mentions: KNOWN_ISSUES.md:29, README.md:52/130/453, SYSTEM.md:118,
backend/mcp_server/README.md:24/144, backend/mcp_server/codex_config.example.toml:27,
mcpb/manifest.json:53.

- **CONTRIBUTING #1** → "**Unchecked volume auto-apply or bulk blast.**" plus one sentence: full
  automation mode is opt-in, capped, limited to jobs the user queued and to answers that pass every
  check; unscored, uncapped or unqueued applying stays refused. Keep the rest of the paragraph.
- **SYSTEM.md** (groom first, moving verbatim detail that already has a home in `docs/entities/*`,
  never dropping a rule-bearing clause; gate must pass at ≤ 1000):
  - §6 new `{#inv-job-site-password-local}` and `{#inv-auto-consent-gated}` (with their pinning
    tests named).
  - §7 MCP bullet: `record_consent` stores the user's yes/no, or in full automation mode the
    agent's automatic yes (channel `auto`); `get_job_site_login`.
- **SECURITY.md / PRIVACY.md:** where the job-site login lives, how it reaches the agent (through
  its AI provider).
- **Playbook:** an "Unattended (full automation)" section pointing to `apply-auto`.
- **CHANGELOG** under Unreleased, user-facing.

**Commit** — `docs: full automation mode and the job-site login`

---

### Task 13: Full verification

1. Backend suite (xdist) — all pass. **Also run it once in the main checkout without
   `frontend/node_modules`** (the phase-3 lesson).
2. Frontend: `node --test` for touched libs, `npx tsc --noEmit`, `npm run lint`, `npm run build`
   (`--webpack` if a symlinked `node_modules` breaks Turbopack).
3. SYSTEM.md gate; slop ratchet backend and frontend. The dry run saw backend
   `complexity_hotspots` 586 → 589 (three new functions over threshold; `transition` cc 33 → 34).
   Split the new functions until the count is back at 586 (the `transition` +1 is not a new
   hotspot). Re-baseline only if a split would hurt clarity, with the reason in the commit.
4. Live check on a throwaway stack (spare ports, never 8001/3000):
   - Settings: switch On → dialog → On; save a job-site login; the password never appears in the
     page or any GET response; Off again.
   - `/automations`: Off → Apply session (Attended); On → **Apply automatically** (Scheduled).
   - With On, via curl as MCP: `record_consent` `auto` approves a proposal with `final_review`
     evidence; with Off it 409s. `POST /api/proposals/{id}/job-site-login` with MCP headers
     returns the login and writes a `login_shared` event; without the header 403.
   - With On, `mark_submitted` channel `auto` with a note marks an approved job submitted; with
     Off it 409s; without a note it 409s.
   - Screenshots at 1280 and 1024, light and dark.
5. Scope: `git diff <base>..HEAD --stat` shows nothing under `extension/`.
