# Application Preferences Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Agents stop asking mid-form about cover letters and low-stakes questions (text-message
consent, how the user heard): a typed cover-letter preference, the existing low-stakes switch
exposed through the brief, a tool that writes, renders and stages a cover letter, and explicit
skill rules.

**Design:** `docs/plans/2026-10-06-application-preferences-design.md` (approved 2026-10-06).

**Architecture:** One new JSON setting (`application_preferences`, the `JsonSetting` pattern
`auto_apply_settings.py` uses) with its own GET/PUT route. The brief gains an `applying` block
built from that setting, `model_settings.get_autofill_low_stakes` and the low-stakes sentences
`autofill_map` already gives the Companion's fill. A new MCP tool composes existing routes (list,
generate, render, fetch the cover letter) and stages the PDF the way
`prepare_application_pdf_upload` stages the resume. `qa_entries` gains `edited_at` so the final
review can say whose letter went.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite + alembic; pydantic v2; FastMCP; Next.js 16 /
React 19 + react-query; pytest (+ xdist), node type-stripping for frontend parity tests.

**Ground rules (every task):**
- Read `SYSTEM.md` first. Backend tests: `cd backend && python -m pytest <paths> -q -n auto --dist loadfile`.
- Don't commit (the session commits). No real company names, people or application questions in
  code, tests or docs: the repo is public.
- Never change `prepare_application_pdf_upload`'s behavior; the new tool mirrors it.
- An already-shipped fix to know about: `BriefAutoApply` now declares `full_automation`
  (c93c837c). A brief field must be declared in `app/schemas/job_search_brief.py` or the
  response model drops it; test every new brief field over HTTP, not only through `build_brief`.

---

### Task 1: The setting

**Files:**
- Create: `backend/app/schemas/application_preferences.py`
- Create: `backend/app/services/application_preferences.py`
- Modify: `backend/app/routers/settings.py` (next to the auto-apply routes, ~line 278)
- Test: `backend/tests/test_application_preferences_setting.py`

**Step 1: Write the failing tests**

```python
"""The application preferences setting (docs/plans/2026-10-06-application-preferences-design.md)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.setting import Setting

client = TestClient(app)
DEFAULTS = {"cover_letter": "skip_unless_required", "cover_letter_tone": "balanced"}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch, db_session):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def test_defaults_change_nothing_until_the_user_picks():
    response = client.get("/api/settings/application-preferences")
    assert response.status_code == 200
    assert response.json() == {"key": "application_preferences", "value": DEFAULTS}


def test_round_trip():
    value = {"cover_letter": "always", "cover_letter_tone": "concise"}
    put = client.put("/api/settings/application-preferences", json={"value": value})
    assert put.status_code == 200 and put.json()["value"] == value
    assert client.get("/api/settings/application-preferences").json()["value"] == value


@pytest.mark.parametrize("value", [
    {"cover_letter": "sometimes", "cover_letter_tone": "balanced"},
    {"cover_letter": "always", "cover_letter_tone": "sarcastic"},
    {"cover_letter": "always", "cover_letter_tone": "balanced", "extra": 1},
])
def test_rejects_unknown_values(value):
    assert client.put("/api/settings/application-preferences", json={"value": value}).status_code == 422


@pytest.mark.parametrize("source", ["database", "file"])
def test_an_invalid_stored_value_reads_as_the_defaults(db_session, tmp_path, source):
    bad = json.dumps({"cover_letter": "sometimes"})
    if source == "database":
        db_session.add(Setting(key="application_preferences", value=bad))
        db_session.commit()
    else:
        (tmp_path / "application_preferences.json").write_text(bad, encoding="utf-8")
    assert client.get("/api/settings/application-preferences").json()["value"] == DEFAULTS
```

Check how `JsonSetting` treats a partially valid blob (`app/services/json_settings.py`) and match
the assertion to it: `test_full_automation_setting.py::test_invalid_stored_full_automation_degrades_to_off`
is the precedent.

**Step 2:** Run: `python -m pytest tests/test_application_preferences_setting.py -q` → FAIL (404).

**Step 3: Implement**

```python
# app/schemas/application_preferences.py
"""What the user's agents do with cover letters (docs/plans/2026-10-06-application-preferences-design.md)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

CoverLetterChoice = Literal["skip_unless_required", "always", "never"]
CoverLetterTone = Literal["balanced", "enthusiastic", "formal", "concise"]


class ApplicationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cover_letter: CoverLetterChoice = "skip_unless_required"
    cover_letter_tone: CoverLetterTone = "balanced"
```

```python
# app/services/application_preferences.py
"""Application preferences storage."""

from sqlalchemy.orm import Session

from app.schemas.application_preferences import ApplicationPreferences
from app.services.json_settings import JsonSetting

APPLICATION_PREFERENCES = JsonSetting(
    "application_preferences", "application_preferences.json", ApplicationPreferences)


def get_preferences(session: Session | None = None) -> ApplicationPreferences:
    return APPLICATION_PREFERENCES.get(session)


def set_preferences(value: ApplicationPreferences, session: Session | None = None) -> ApplicationPreferences:
    return APPLICATION_PREFERENCES.set(value, session)
```

Routes in `routers/settings.py`, shaped like `GET/PUT /auto-apply`:

```python
@router.get("/application-preferences", response_model=SettingEnvelope[ApplicationPreferences])
def get_application_preferences(db: Annotated[Session, Depends(get_db)]):
    return {"key": "application_preferences", "value": application_preferences.get_preferences(db)}


@router.put("/application-preferences", response_model=SettingEnvelope[ApplicationPreferences])
def put_application_preferences(
    payload: SettingValueIn[ApplicationPreferences], db: Annotated[Session, Depends(get_db)]
):
    return {"key": "application_preferences",
            "value": application_preferences.set_preferences(payload.value, db)}
```

**Step 4:** Run the test file → PASS.

**Step 5:** Stop for review (no commit).

---

### Task 2: The brief's `applying` block

**Files:**
- Modify: `backend/app/services/job_search_brief.py` (`build_brief`, next to `_auto_apply_block` ~line 84)
- Modify: `backend/app/schemas/job_search_brief.py` (new `BriefApplying`, field on `JobSearchBriefResponse`)
- Modify: `backend/app/services/autofill_map.py` only if a public name is needed (see Step 3)
- Test: `backend/tests/test_application_preferences_setting.py` (append)

**Step 1: Write the failing tests** (append)

```python
from app.services import autofill_map


def _brief():
    response = client.get("/api/jobs/search-brief")
    assert response.status_code == 200
    return response.json()["applying"]


def test_the_brief_carries_the_preferences_over_http():
    client.put("/api/settings/application-preferences",
               json={"value": {"cover_letter": "never", "cover_letter_tone": "formal"}})
    applying = _brief()
    assert applying["cover_letter"] == "never"
    assert applying["cover_letter_tone"] == "formal"


def test_the_brief_follows_the_one_low_stakes_switch():
    for enabled in (True, False):
        assert client.put("/api/settings/autofill-options", json={"low_stakes": enabled}).status_code == 200
        assert _brief()["answer_low_stakes"] is enabled


def test_agents_get_the_same_low_stakes_words_as_the_companion():
    scope, never = autofill_map.low_stakes_scope({})
    applying = _brief()
    assert applying["low_stakes_topics"] == scope
    assert applying["never_low_stakes"] == never
    assert "SMS" in scope  # text-message consent is on the list
```

**Step 2:** Run → FAIL (`KeyError: 'applying'`).

**Step 3: Implement**

```python
# app/schemas/job_search_brief.py
class BriefApplying(BaseModel):
    """What the user's agents answer without asking (application preferences + the
    Companion's low-stakes switch, one switch for both)."""

    cover_letter: CoverLetterChoice
    cover_letter_tone: CoverLetterTone
    answer_low_stakes: bool
    low_stakes_topics: str
    never_low_stakes: str
```

Add `applying: BriefApplying` to `JobSearchBriefResponse`, and in `job_search_brief.py`:

```python
def _applying_block(db: Session) -> dict[str, Any]:
    prefs = application_preferences.get_preferences(db)
    scope, never = autofill_map.low_stakes_scope({})
    return {
        "cover_letter": prefs.cover_letter,
        "cover_letter_tone": prefs.cover_letter_tone,
        "answer_low_stakes": model_settings.get_autofill_low_stakes(db),
        "low_stakes_topics": scope,
        "never_low_stakes": never,
    }
```

`low_stakes_scope({})` is the generic wording (`_LOW_STAKES`, `_NEVER_LOW_STAKES` at module level
are exactly that). If importing `autofill_map` into the brief pulls a heavy import chain, measure
with `python -X importtime -c "import app.services.job_search_brief"` and, if it does, move the two
templates and `low_stakes_scope` into a small `app/services/low_stakes.py` that both import.

**Step 4:** Run the file plus `tests/test_job_search_brief.py` → PASS.

**Step 5:** Stop for review.

---

### Task 3: Who wrote the letter (`qa_entries.edited_at`)

**Files:**
- Create: `backend/migrations/versions/<12hex>_qa_entry_edited_at.py` (down_revision = current head;
  run `cd backend && alembic heads` to read it — `7d3c1a9e5b20` at planning time)
- Modify: `backend/app/models/qa_entry.py`, `backend/app/schemas/qa.py` (`QAEntryRead.edited_at`)
- Modify: `backend/app/routers/qa.py` PATCH `/{entry_id}` (~line 141): set `edited_at = utcnow()`
  when `answer` changes
- Test: `backend/tests/test_qa_router.py` (append)

**Step 1: Failing tests:** a generated letter has `edited_at is None`; a PATCH that changes the
answer sets it; a PATCH with the same answer leaves it; `POST /api/qa` (regenerate/replace) gives a
fresh entry with `edited_at is None`. Use the existing fixtures in `test_qa_router.py` for creating
an application and stubbing the LLM.

**Step 2:** Run → FAIL. **Step 3:** Add the nullable `DateTime(timezone=True)` column with
`op.batch_alter_table`, the model field, the schema field, the PATCH line. **Step 4:** PASS, and
`alembic upgrade head` then `alembic downgrade -1` then `upgrade head` on a scratch copy of the
test DB. **Step 5:** Stop for review.

---

### Task 4: `prepare_cover_letter_upload`

**Files:**
- Modify: `backend/mcp_server/client.py` (new method next to `prepare_application_pdf_upload`, ~line 962)
- Modify: `backend/mcp_server/server.py` (new tool next to `prepare_application_pdf_upload`, ~line 1177)
- Modify: `backend/mcp_server/profiles.py` (`APPLY_TOOLS`)
- Test: `backend/mcp_server/tests/test_client_cover_letter_upload.py` (model it on
  `test_client_pdf_delivery.py`, which fakes the backend transport)

**Behavior (client method `prepare_cover_letter_upload(application_id)`):**
1. Validate `application_id` as a safe path component (reuse the PDF tool's check).
2. `POST /api/applications/{id}/assert-open-proposal {"op": "prepare"}` (same gate as the PDF tool).
3. `GET /api/qa?application_id=…`; take the newest `kind == "cover_letter"` entry with a non-empty
   answer.
4. None → `GET /api/settings/application-preferences`, then
   `POST /api/qa {"application_id": …, "cover_letter": {"tone": <cover_letter_tone>}}`;
   `written = "maestro"`. Found → `written = "edited" if entry["edited_at"] else "maestro"`,
   `reused = True`.
5. No `pdf_path` → `POST /api/qa/{entry_id}/render`.
6. `GET /api/qa/{entry_id}/pdf`; stage to `<upload root>/<application_id>/<filename from
   content-disposition>` with the existing `_atomic_write_bytes` and `_host_visible`.
7. Return `{application_id, entry_id, written, reused, canonical_filename, upload_path,
   size_bytes, sha256}`.

A backend error at step 4 (no AI key, model error) surfaces as the backend's message (the existing
`BackendError` → `ToolError` mapping); the skill decides what to do (Task 6).

**Tests (all failing first):** writes a letter in the saved tone when none exists (assert the POST
body carries the tone); reuses an existing letter without a POST (and reports `edited` when
`edited_at` is set); renders only when `pdf_path` is missing; stages atomically under the
application's folder with the served filename; refuses an unsafe id before any request; the
assert-open-proposal 409 stops it before any write.

**Tool:**

```python
@mcp.tool(**_write("Stage Cover Letter for Upload", destructive=False, idempotent=True))
@_guard
def prepare_cover_letter_upload(application_id: str) -> Any:
    """Stage the application's cover letter PDF for a browser file upload. Writes the letter in
    the user's saved tone when the application has none (an existing or edited letter is kept),
    renders its PDF if needed, and stages a copy exactly like prepare_application_pdf_upload.
    Returns upload_path and `written` ("maestro" or "edited"). Does not authorize or submit."""
    return _client.prepare_cover_letter_upload(application_id)
```

Add it to `APPLY_TOOLS` in `profiles.py`. **Step 5:** Stop for review.

---

### Task 5: The final review says which letter went

**Files:**
- Modify: `backend/app/services/proposals.py` `get_final_review` (~line 412-503)
- Test: `backend/tests/test_proposals_router.py` (append)

Add `cover_letter: {"status": "none" | "maestro" | "edited", "entry_id": str | None, "uploaded": bool}`:
status from the linked application's newest cover-letter entry (`edited` when `edited_at` is set);
`uploaded` true when the job's filled answers hold an `upload` row with slot `cover_letter`. If
`get_final_review` has a response model, declare the field there too, and assert it over HTTP.
Tests: none / maestro / edited / uploaded, each failing first.

---

### Task 6: The skill rules

**Files:**
- Modify: `backend/app/automations/skills/agent-apply-execution/SKILL.md` (new section after
  "Form and evidence discipline", ~line 63)
- Modify: `backend/app/automations/skills/apply-auto/SKILL.md` (step 7, add the two reasons)
- Test: `backend/tests/test_automations_service.py` (pin each sentence, the existing
  `assert sentence in body` style)

New section, word for word:

```markdown
## Cover letters and low-stakes questions

Read `applying` in the brief before the first form, and never ask the user anything it answers.

- **Cover letter field.** When `cover_letter` is `skip_unless_required`, leave an optional field empty.
  When the field is required, or `cover_letter` is `always`, call `prepare_cover_letter_upload` and attach its `upload_path`.
  When `cover_letter` is `never` and the field is required, call `report_failure` with reason `needs_cover_letter`.
- **No letter.** If `prepare_cover_letter_upload` fails, a required field means `report_failure` with reason `cover_letter_unavailable`; an optional one stays empty and the run digest says so.
- **Record it.** Record an attached letter with `record_filled_answers`, source `upload`, slot `cover_letter`.
- **Low-stakes questions.** When `answer_low_stakes` is true, answer the questions `low_stakes_topics` describes in the job's favor, and never the ones `never_low_stakes` describes.
  When it is false, leave optional ones empty; a required one goes to the user, or in full automation mode to `report_failure` with reason `needs_answer`.
```

In `apply-auto` step 7, after "Call `report_failure` with the reason", nothing new is needed if the
section above is included (it is: `include: [agent-apply-execution]`); only add a test that the
apply card body contains the section heading.

---

### Task 7: The card (Profile → Autofill, "Answers for job forms")

**Files:**
- Modify: `frontend/components/settings/autofill-section.tsx` (`LowStakesSwitch` ~line 1245,
  `CompanionPermissions` ~1187)
- Test: `backend/tests/test_frontend_settings_cards.py` (or the autofill frontend test file that
  already covers `LowStakesSwitch`; follow its parsing style)

1. `LowStakesSwitch` copy: "When none of your answers covers a question, the Companion answers it
   in the job's favor." → "When none of your answers covers a question, the Companion and your
   agents answer it in the job's favor." Toast copy likewise ("The Companion and your agents now
   answer low-stakes questions" / "won't answer").
2. A `CoverLetterPreferences` group below it: label "Cover letters"; a select "When to include one"
   with "Skip unless required" / "Always write one" / "Never — hand the job back if it's required"
   (values `skip_unless_required` / `always` / `never`); a select "Tone" with Balanced /
   Enthusiastic / Formal / Concise. One hint line: "Your agents follow this when a form has a
   cover letter field. Maestro writes each letter from your resume and career history."
   `useQuery(["settings","application-preferences"])`, PUT on change with `useSingleFlight`,
   `qc.setQueryData`, `toast.error(couldnt("save this setting", err))` — the `LowStakesSwitch`
   pattern.
3. Tests (failing first): the new copy; both selects with their four/three labels; the PUT URL.
4. `cd frontend && npx tsc --noEmit && npm run build`.
5. Browser check (fresh stack per `docs` / the worktree verification recipe): change both selects,
   reload, the values persist; the toast on a forced 500. Screenshot at 1280 wide only (desktop-only app).

---

### Task 8: Counts and docs

**Files:** `backend/mcp_server/README.md` (count + tool list entry near the PDF group ~line 257 and
the apply-profile count in the table ~line 144), root `README.md` (lines ~52, 130, 453),
`codex_config.example.toml:27`, `KNOWN_ISSUES.md:29`, `plugins/maestro-career-studio/README.md:84`,
`mcpb/manifest.json:53` (description text → then re-pack the committed `.mcpb` and run
`python3 scripts/check_mcpb_bundle.py`), `docs/entities/others.md` (settings section ~595: the new
setting and `autofill.low_stakes` now read by agents; QAEntry `edited_at` ~147), `SYSTEM.md` (one
line beside the brief line ~485; trim another line so the file stays at 1000 —
`python3 scripts/check_system_md.py` must pass), `CHANGELOG.md` (Unreleased).

Change "86" → "87" everywhere it counts MCP tools; the apply profile count +1. Then
`mcp_server/tests/test_server.py:1150` stays `>= 86`, so add an exact check that
`prepare_cover_letter_upload` is registered and in the apply profile.

---

### Task 9: Final verification

1. Full backend suite: `cd backend && MAESTRO_SKIP_SLOW=1 python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile --ignore=tests/ats/test_golden.py`.
2. `ruff check .`; slop ratchet for `backend` and `frontend` (name both in the claim).
3. `python3 scripts/check_system_md.py`, `python3 scripts/check_mcpb_bundle.py`.
4. An MCP smoke run over stdio against a fresh backend: `get_job_search_brief` shows `applying`;
   `prepare_cover_letter_upload` on a seeded application with an open proposal returns a staged
   PDF (stub the LLM with a local fake OpenAI endpoint, as the proxy re-review did).
5. Opus final review of the whole diff.
