# Jev Autofill Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the Companion's AI fill pass (`POST /api/autofill/choose`) use Jev (TypeSafe AI's
System One decision model, via OpenRouter or TypeSafe) as an optional engine chosen in
Settings › AI & models, with the fast LLM as default and fallback.

**Architecture:** An engine switch inside `autofill_choose.choose`. With engine `jev`, one Jev
call maps each field's LABEL to an autofill-profile slot (no values sent), code reads the value
from the consent-gated profile, and a second Jev call picks the page option that states that
value; a per-slot policy turns the pick's probability into `matched`, `closest` or `abstained`.
Anything Jev cannot place — free-text questions, unmapped or low-confidence fields, and every
field of a Jev call that errors — goes to the existing fast-model path unchanged.

**Tech stack:** FastAPI + SQLAlchemy (backend), httpx (Jev client), respx (tests), Next.js 16 +
react-query (settings UI), plain-JS extension with Python/node test harness.

**Design doc:** `docs/plans/2026-09-25-jev-autofill-design.md` — read it first. Read
`SYSTEM.md` (repo root) before anything, per CLAUDE.md.

**Environment (from SYSTEM.md §9):**
- Backend tests run from `backend/`: single test `python3 -m pytest tests/<file>.py::<test> -q`;
  full gate `python3 -m pytest tests/ mcp_server/tests/ -q` (~5 min).
- Frontend gates, from `frontend/`: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
- **Owner's laptop:** the interpreter is `/opt/anaconda3/bin/python3` (editable install; cwd
  `backend/` makes `app` resolve to the worktree). Never touch the live compose stack or `data/`.
- **Claude Code on the web (cloud):** Tasks 1–9 and Task 10 Step 1 run there; Task 10 Step 2
  (live check) is the owner's, locally — no Jev key goes into the cloud environment. Setup:
  Python 3.12, `pip install -e "backend[dev,mcp]"`, node 24 (the extension tests shell out to
  node), `cd frontend && npm ci`. **Before Task 1, run the full backend gate once and record any
  failures** — the cloud image has no TeX/typst, so render tests may already fail there. The
  bar for every task is: its own tests pass and no test that passed at baseline fails. If the
  superpowers skills are not installed, follow this plan directly; it is self-contained.
  Commit after each task and push the branch at the end.

**Jev API (verified 2026-09-25):** `POST {base}/v1/systemone`, header
`Authorization: Bearer <key>`, body `{"model", "state", "questions"}` where `questions` is a map
`{id: {"type": "choice", "instructions": str, "criteria": {option_key: description}}}` (also
`"noul"` and `"score"` types). Response `{"model", "answers": {id: {"choice", "probabilities":
{option_key: p}, "confidence"}}, "usage"}`. Errors: 401 bad key, 422 invalid request, 429 rate
limit, 529 overloaded. Base URLs: OpenRouter `https://openrouter.ai/api` (model
`typesafe/jev-1.13` or `~typesafe/jev-latest`), TypeSafe direct `https://api.typesafe.ai`
(model `jev-latest`). ≤255 options per Choice.

---

### Task 1: Jev settings storage

**Files:**
- Modify: `backend/app/services/model_settings.py` (after `set_json_mode`, ~line 176)
- Test: `backend/tests/test_model_settings_jev.py` (create)

**Step 1: Write the failing tests**

```python
import pytest

from app.services import model_settings


def test_defaults_point_at_openrouter_and_the_fast_engine(db_session):
    assert model_settings.get_jev_api_key(db_session) is None
    assert model_settings.get_jev_base_url(db_session) == "https://openrouter.ai/api"
    assert model_settings.get_jev_model(db_session) == "typesafe/jev-1.13"
    assert model_settings.get_autofill_engine(db_session) == "fast"


def test_jev_settings_round_trip(db_session):
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_jev_base_url(db_session, "https://api.typesafe.ai")
    model_settings.set_jev_model(db_session, "jev-latest")
    model_settings.set_autofill_engine(db_session, "jev")
    assert model_settings.get_jev_api_key(db_session) == "sk-or-test"
    assert model_settings.get_jev_base_url(db_session) == "https://api.typesafe.ai"
    assert model_settings.get_jev_model(db_session) == "jev-latest"
    assert model_settings.get_autofill_engine(db_session) == "jev"


def test_the_jev_base_url_must_be_http(db_session):
    """It decides where the key is sent — the set_base_url rule (§6)."""
    with pytest.raises(ValueError):
        model_settings.set_jev_base_url(db_session, "file:///etc/passwd")


def test_jev_cannot_be_the_engine_without_a_key(db_session):
    with pytest.raises(ValueError, match="key"):
        model_settings.set_autofill_engine(db_session, "jev")


def test_an_unknown_engine_is_refused(db_session):
    with pytest.raises(ValueError):
        model_settings.set_autofill_engine(db_session, "gpt")


def test_clearing_the_key_falls_back_to_the_fast_engine(db_session):
    """A stored `jev` engine with no key would fail every fill; the read says fast."""
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")
    model_settings.set_jev_api_key(db_session, None)
    assert model_settings.get_autofill_engine(db_session) == "fast"
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_model_settings_jev.py -q`
Expected: FAIL — `AttributeError: module 'app.services.model_settings' has no attribute 'get_jev_api_key'`.

**Step 3: Implement**

In `model_settings.py`, first extract the scheme check out of `set_base_url` so both setters
share it (behaviour of `set_base_url` unchanged):

```python
def _checked_http_url(value: str | None) -> str | None:
    cleaned = (value or "").strip() or None
    if cleaned is not None:
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Enter a full address that starts with http:// or https://.")
    return cleaned
```

and make `set_base_url` `return _set_raw_value(session, BASE_URL_KEY, _checked_http_url(value))`
(keep its docstring). Then add, after `set_json_mode`:

```python
# Jev (TypeSafe AI) — the optional decision engine for the Companion's fill pass.
# Its own key: an OpenRouter or TypeSafe key is not the OpenAI key above.
JEV_API_KEY_KEY = "llm.jev_api_key"
JEV_BASE_URL_KEY = "llm.jev_base_url"
JEV_MODEL_KEY = "llm.jev_model"
AUTOFILL_ENGINE_KEY = "llm.autofill_engine"

JEV_DEFAULT_BASE_URL = "https://openrouter.ai/api"
# Pinned, not -latest: a model that changes under the user changes their fills.
JEV_DEFAULT_MODEL = "typesafe/jev-1.13"
AUTOFILL_ENGINES = ("fast", "jev")


def _read(session: Session | None, key: str) -> str | None:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, key)
    return _get_raw_value(session, key)


def get_jev_api_key(session: Session | None = None) -> str | None:
    return _read(session, JEV_API_KEY_KEY)


def get_jev_base_url(session: Session | None = None) -> str:
    return _read(session, JEV_BASE_URL_KEY) or JEV_DEFAULT_BASE_URL


def get_jev_model(session: Session | None = None) -> str:
    return _read(session, JEV_MODEL_KEY) or JEV_DEFAULT_MODEL


def get_autofill_engine(session: Session | None = None) -> str:
    """`jev` only while a key exists: a keyless Jev engine would fail every fill."""
    if _read(session, AUTOFILL_ENGINE_KEY) == "jev" and get_jev_api_key(session):
        return "jev"
    return "fast"


def set_jev_api_key(session: Session, value: str | None) -> str | None:
    return _set_raw_value(session, JEV_API_KEY_KEY, (value or "").strip() or None)


def set_jev_base_url(session: Session, value: str | None) -> str | None:
    """Same scheme rule as `set_base_url`, for the same reason: it decides where the key goes."""
    return _set_raw_value(session, JEV_BASE_URL_KEY, _checked_http_url(value))


def set_jev_model(session: Session, value: str | None) -> str | None:
    return _set_raw_value(session, JEV_MODEL_KEY, (value or "").strip() or None)


def set_autofill_engine(session: Session, value: str) -> str:
    if value not in AUTOFILL_ENGINES:
        raise ValueError(f"engine must be one of {', '.join(AUTOFILL_ENGINES)}")
    if value == "jev" and not get_jev_api_key(session):
        raise ValueError("Add a Jev API key before switching form filling to Jev.")
    # "fast" is the default, so store nothing rather than a redundant row.
    _set_raw_value(session, AUTOFILL_ENGINE_KEY, None if value == "fast" else value)
    return value
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_model_settings_jev.py tests/ -q -k "model_settings or base_url"`
Expected: PASS (the `-k` run also covers the existing `set_base_url` tests you refactored).

**Step 5: Commit**

```bash
git add backend/app/services/model_settings.py backend/tests/test_model_settings_jev.py
git commit -m "feat(settings): store the Jev key, endpoint, model and autofill engine"
```

---

### Task 2: The Jev client

**Files:**
- Create: `backend/app/services/jev.py`
- Modify: `backend/pyproject.toml` — add `"httpx>=0.27",` to `[project] dependencies` (it is
  only in the `dev`/`mcp` extras today; the runtime has it transitively via `openai`, but the
  backend now imports it directly, so declare it)
- Test: `backend/tests/test_jev_client.py` (create)

**Step 1: Write the failing tests**

```python
import json

import httpx
import pytest
import respx

from app.config import settings
from app.services import jev, model_settings
from app.services.llm import LLMProviderError

URL = "https://openrouter.ai/api/v1/systemone"
QUESTIONS = {"q1": jev.choice_question("Which?", {"a": "A", "b": "B"})}
ANSWER = {"q1": {"choice": "a", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.8}}


@pytest.fixture(autouse=True)
def _keyed(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "logs_dir", tmp_path)
    monkeypatch.setattr(jev, "_BACKOFF_S", 0)
    model_settings.set_jev_api_key(db_session, "sk-or-test")


@respx.mock
def test_it_posts_model_state_and_questions_with_the_bearer_key(db_session):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": ANSWER}))
    assert jev.decide(QUESTIONS, {"x": 1}, db_session) == ANSWER
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer sk-or-test"
    assert json.loads(sent.content) == {
        "model": "typesafe/jev-1.13", "state": {"x": 1}, "questions": QUESTIONS}


def test_no_key_is_a_provider_error_and_no_request(db_session):
    model_settings.set_jev_api_key(db_session, None)
    with pytest.raises(LLMProviderError, match="Jev"):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_refused_key_says_so(db_session):
    respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(LLMProviderError, match="refused"):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_rate_limit_is_retried_once(db_session):
    route = respx.post(URL).mock(side_effect=[
        httpx.Response(429), httpx.Response(200, json={"answers": ANSWER})])
    assert jev.decide(QUESTIONS, "s", db_session) == ANSWER
    assert route.call_count == 2


@respx.mock
def test_a_second_overload_gives_up(db_session):
    respx.post(URL).mock(side_effect=[httpx.Response(529), httpx.Response(529)])
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_a_network_failure_is_a_provider_error(db_session):
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


@respx.mock
def test_an_unreadable_body_is_a_provider_error(db_session):
    respx.post(URL).mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(LLMProviderError):
        jev.decide(QUESTIONS, "s", db_session)


def test_choice_of_reads_the_chosen_options_probability():
    picked = jev.choice_of(ANSWER["q1"])
    assert (picked.choice, picked.probability, picked.confidence) == ("a", 0.9, 0.8)


def test_choice_of_falls_back_to_confidence_and_refuses_junk():
    assert jev.choice_of({"choice": "a", "confidence": 0.7}).probability == 0.7
    assert jev.choice_of(None) is None
    assert jev.choice_of({"choice": 3}) is None


@respx.mock
def test_the_call_log_keeps_metadata_only(db_session, tmp_path):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": ANSWER}))
    jev.decide(QUESTIONS, {"secret": "Ada Lovelace"}, db_session)
    [logged] = list((tmp_path / "llm_calls").iterdir())
    assert "Ada Lovelace" not in logged.read_text()
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_jev_client.py -q`
Expected: FAIL — `ImportError: cannot import name 'jev'`.

**Step 3: Implement `backend/app/services/jev.py`**

```python
"""Jev (TypeSafe AI's System One model): typed decisions, never generated text.

A call sends a STATE and a map of typed questions and gets back, per question, a
chosen option with calibrated probabilities. It cannot write, extract or look
anything up — code gathers what a question needs into the state and acts on the
answer. Served by TypeSafe directly or by OpenRouter's passthrough; both speak
`POST {base}/v1/systemone`, so the base URL setting is the only difference.

Failures are `LLMProviderError`, the one provider-outage type (§12), so callers
fall back to the fast model exactly as they would on an OpenAI outage.
"""

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services import model_settings
from app.services.llm import LLMProviderError, _log_call

# The fill pass's whole point is speed: a Jev call that takes longer than this
# is slower than the fast model it replaces, so give up and let it answer.
TIMEOUT_S = 2.0
_RETRY_STATUSES = frozenset({429, 529})
_BACKOFF_S = 0.3

NO_JEV_KEY_MESSAGE = "No Jev API key is set. Add one in Settings › AI & models › Form filling."


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probability: float  # of the chosen option
    confidence: float


def choice_question(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def choice_of(answer: object) -> ChoiceAnswer | None:
    """One Choice answer, or None when the shape is not one."""
    if not isinstance(answer, dict) or not isinstance(answer.get("choice"), str):
        return None
    confidence = answer.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    probabilities = answer.get("probabilities")
    p = probabilities.get(answer["choice"]) if isinstance(probabilities, dict) else None
    probability = float(p) if isinstance(p, (int, float)) else confidence
    return ChoiceAnswer(answer["choice"], probability, confidence)


def decide(
    questions: dict[str, dict[str, Any]],
    state: Any,
    session: Session | None = None,
) -> dict[str, Any]:
    """POST one System One request; return its `answers` map."""
    key = model_settings.get_jev_api_key(session)
    if not key:
        raise LLMProviderError(NO_JEV_KEY_MESSAGE)
    body = {"model": model_settings.get_jev_model(session), "state": state, "questions": questions}
    url = f"{model_settings.get_jev_base_url(session).rstrip('/')}/v1/systemone"
    deadline = time.monotonic() + TIMEOUT_S

    attempt = 0
    while True:
        attempt += 1
        try:
            response = httpx.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except httpx.HTTPError as exc:
            raise LLMProviderError("Jev could not be reached.", str(exc)) from exc
        retry = (
            response.status_code in _RETRY_STATUSES
            and attempt == 1
            and deadline - time.monotonic() > _BACKOFF_S
        )
        if not retry:
            break
        time.sleep(_BACKOFF_S)

    _log_call(json.dumps(body, sort_keys=True), body["model"], response.text, attempt)
    detail = response.text[:300]
    if response.status_code == 401:
        raise LLMProviderError(
            "Jev refused your API key. Check it in Settings › AI & models.", detail)
    if response.status_code >= 400:
        raise LLMProviderError(f"Jev couldn't answer (error {response.status_code}).", detail)
    try:
        answers = response.json()["answers"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMProviderError("Jev sent an answer we couldn't read.", detail) from exc
    if not isinstance(answers, dict):
        raise LLMProviderError("Jev sent an answer we couldn't read.", detail)
    return answers


def probe(session: Session | None = None) -> None:
    """One tiny Noul call; raises LLMProviderError when the key or endpoint is wrong."""
    decide(
        {"ok": {"type": "noul", "instructions": "Is the state the word yes?"}},
        "yes",
        session,
    )
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_jev_client.py -q`
Expected: PASS (10 tests).

**Step 5: Commit**

```bash
git add backend/app/services/jev.py backend/tests/test_jev_client.py backend/pyproject.toml
git commit -m "feat(jev): System One client with retry, error mapping and metadata-only log"
```

---

### Task 3: Settings endpoints

**Files:**
- Modify: `backend/app/routers/settings.py` (new models near `OpenAIInfo`; endpoints after
  `add_catalog_model`)
- Test: `backend/tests/test_settings_jev_router.py` (create)

**Step 1: Write the failing tests**

```python
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import jev
from app.services.llm import LLMProviderError


@pytest.fixture
def client(db_session):
    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_reports_defaults_and_never_the_key(client):
    body = client.get("/api/settings/jev").json()
    assert body == {"api_key_configured": False, "base_url": "https://openrouter.ai/api",
                    "model": "typesafe/jev-1.13", "engine": "fast"}


def test_put_is_a_patch_and_the_key_is_write_only(client):
    body = client.put("/api/settings/jev", json={"api_key": "sk-or-test"}).json()
    assert body["api_key_configured"] is True
    assert "sk-or-test" not in str(body)
    body = client.put("/api/settings/jev", json={"engine": "jev"}).json()
    assert body["engine"] == "jev" and body["api_key_configured"] is True


def test_switching_to_jev_without_a_key_is_a_400(client):
    assert client.put("/api/settings/jev", json={"engine": "jev"}).status_code == 400


def test_a_non_http_base_url_is_a_400(client):
    assert client.put("/api/settings/jev", json={"base_url": "ftp://x"}).status_code == 400


def test_probe_reports_ok(client, monkeypatch):
    monkeypatch.setattr(jev, "probe", lambda session=None: None)
    assert client.post("/api/settings/jev/probe").json() == {"ok": True, "error": None}


def test_probe_reports_failure_without_a_502(client, monkeypatch):
    def refused(session=None):
        raise LLMProviderError("Jev refused your API key.")

    monkeypatch.setattr(jev, "probe", refused)
    resp = client.post("/api/settings/jev/probe")
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "Jev refused your API key."}
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_settings_jev_router.py -q`
Expected: FAIL — 404/405 on `/api/settings/jev`.

**Step 3: Implement**

Add `jev` to the `from app.services import (...)` list. Near `OpenAIInfo`:

```python
class JevInfo(BaseModel):
    """GET/PUT /api/settings/jev. Like OpenAIInfo: a `*_configured` flag, never the key."""

    api_key_configured: bool
    base_url: str
    model: str
    engine: Literal["fast", "jev"]


class JevSettingsPayload(BaseModel):
    """A patch, as ModelSettingsPayload: absent = leave alone; null/"" = clear."""

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    engine: Literal["fast", "jev"] | None = None


class JevProbeResult(BaseModel):
    ok: bool
    error: str | None = None
```

After `add_catalog_model`:

```python
@router.get("/jev", response_model=JevInfo)
def get_jev_info(db: Annotated[Session, Depends(get_db)]):
    return JevInfo(
        api_key_configured=bool(model_settings.get_jev_api_key(db)),
        base_url=model_settings.get_jev_base_url(db),
        model=model_settings.get_jev_model(db),
        engine=model_settings.get_autofill_engine(db),
    )


@router.put("/jev", response_model=JevInfo)
def put_jev_info(payload: JevSettingsPayload, db: Annotated[Session, Depends(get_db)]):
    sent = payload.model_fields_set
    try:
        # Key and endpoint first: the engine check reads the key.
        if "api_key" in sent:
            model_settings.set_jev_api_key(db, payload.api_key)
        if "base_url" in sent:
            model_settings.set_jev_base_url(db, payload.base_url)
        if "model" in sent:
            model_settings.set_jev_model(db, payload.model)
        if "engine" in sent and payload.engine is not None:
            model_settings.set_autofill_engine(db, payload.engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_jev_info(db)


@router.post("/jev/probe", response_model=JevProbeResult)
def probe_jev(db: Annotated[Session, Depends(get_db)]):
    """Never 502s: a refused key is a result the Settings card shows, like /openai/probe."""
    try:
        jev.probe(db)
    except LLMProviderError as exc:
        return JevProbeResult(ok=False, error=str(exc))
    return JevProbeResult(ok=True)
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_settings_jev_router.py -q`
Expected: PASS (6 tests).

**Step 5: Commit**

```bash
git add backend/app/routers/settings.py backend/tests/test_settings_jev_router.py
git commit -m "feat(settings): GET/PUT /api/settings/jev and a Jev key probe"
```

---

### Task 4: Slot catalog and substitution policy

**Files:**
- Create: `backend/app/services/autofill_slots.py`
- Test: `backend/tests/test_autofill_slots.py` (create)

**Step 1: Write the failing tests**

```python
from app.services import autofill_slots as slots


def test_flatten_keeps_answered_leaves_as_text():
    profile = {
        "personal": {"first_name": "Ada", "phone": ""},
        "work_auth": {"sponsorship_now": False, "countries_authorized": ["US", "CA"]},
        "preferences": {"notice_period": "0"},
        "note": "not a section",
    }
    assert slots.flatten(profile) == {
        "personal.first_name": "Ada",
        "work_auth.sponsorship_now": "No",
        "work_auth.countries_authorized": "US, CA",
        "preferences.notice_period": "0",
    }


def test_the_policy_is_by_section():
    assert slots.policy_for("work_auth.sponsorship_now") == "exact"
    assert slots.policy_for("eligibility.over_18") == "exact"
    assert slots.policy_for("eeo.gender") == "exact"
    assert slots.policy_for("education.discipline") == "flag"
    assert slots.policy_for("personal.country") == "flag"
    assert slots.policy_for("preferences.how_heard") == "any"
    # A known_value field arrives without a slot: treated as a factual claim.
    assert slots.policy_for(None) == "flag"


def test_criteria_offer_every_slot_plus_free_text_and_none():
    criteria = slots.slot_criteria({"education.discipline": "Business analytics"})
    assert set(criteria) == {"education.discipline", slots.FREE_TEXT, slots.NO_SLOT}
    # Labels only — the VALUE never appears in the slot question.
    assert "Business analytics" not in str(criteria)
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_autofill_slots.py -q`
Expected: FAIL — `ImportError`.

**Step 3: Implement `backend/app/services/autofill_slots.py`**

```python
"""The Jev fill path's slot catalog and substitution policy.

A SLOT is one answered leaf of the autofill profile ("education.discipline").
Jev maps a form field to a slot from its label alone; code reads the value, so
the slot question never carries one. The POLICY says how far a picked option may
drift from that value before we refuse to write it:

- exact: legal and protected answers — a near miss is a false statement.
- flag:  facts about the applicant — a near miss only with the user told.
- any:   preferences — the best available option is the answer.
"""

from typing import Any, Literal

Policy = Literal["any", "flag", "exact"]

FREE_TEXT = "free_text"
NO_SLOT = "none"

_EXACT_SECTIONS = frozenset({"work_auth", "eligibility", "eeo"})
_FLAG_SECTIONS = frozenset({"education", "personal"})


def policy_for(slot: str | None) -> Policy:
    if slot is None:
        return "flag"
    section = slot.split(".", 1)[0]
    if section in _EXACT_SECTIONS:
        return "exact"
    if section in _FLAG_SECTIONS:
        return "flag"
    return "any"


def _as_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        joined = ", ".join(str(item).strip() for item in value if str(item).strip())
        return joined or None
    return None


def flatten(profile: dict[str, Any]) -> dict[str, str]:
    """slot → value text, for every answered leaf of every section."""
    out: dict[str, str] = {}
    for section, values in (profile or {}).items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            text = _as_text(value)
            if text is not None:
                out[f"{section}.{key}"] = text
    return out


def slot_criteria(slots: dict[str, str]) -> dict[str, str]:
    """The Choice criteria for "which slot does this field ask for" — names, no values."""
    criteria = {slot: slot.replace(".", ": ").replace("_", " ") for slot in slots}
    criteria[FREE_TEXT] = (
        "A question that needs a written answer in the applicant's own words, "
        "such as why this company or describe a project"
    )
    criteria[NO_SLOT] = "None of the listed applicant facts answers this field"
    return criteria
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_autofill_slots.py -q`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add backend/app/services/autofill_slots.py backend/tests/test_autofill_slots.py
git commit -m "feat(autofill): slot catalog and substitution policy for the Jev path"
```

---

### Task 5: `closest` in the choose contract

**Files:**
- Modify: `backend/app/schemas/autofill_choose.py:46-48`
- Test: `backend/tests/test_autofill_choose_schema.py` (append)

**Step 1: Write the failing test** (append)

```python
def test_closest_is_a_reason():
    from app.schemas.autofill_choose import Choice

    assert Choice(answer="Information Systems", reason="closest").reason == "closest"
```

**Step 2: Run** `python3 -m pytest tests/test_autofill_choose_schema.py -q` — Expected: FAIL (validation error).

**Step 3: Implement**

```python
class Choice(BaseModel):
    answer: str | None
    # closest: written, but the page had no exact option for the profile's value
    # (Jev path, `flag` slots only) — the Fill report tells the user to check it.
    reason: Literal["matched", "closest", "abstained"]
```

**Step 4: Run** the same command — Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/schemas/autofill_choose.py backend/tests/test_autofill_choose_schema.py
git commit -m "feat(autofill): a closest-match reason on /choose answers"
```

---

### Task 6: The Jev route through `autofill_choose.choose`

**Files:**
- Modify: `backend/app/services/autofill_choose.py`
- Test: `backend/tests/test_autofill_choose_jev.py` (create)

**Step 1: Write the failing tests**

```python
import json

import pytest

from app.schemas.autofill_choose import ChooseField
from app.services import autofill_choose, autofill_profile, autofill_slots, model_settings
from app.services.llm import LLMProviderError

PROFILE = {
    "personal": {"first_name": "Ada"},
    "education": {"discipline": "Business analytics"},
    "work_auth": {"sponsorship_now": False},
    "preferences": {"how_heard": "Job board"},
    "eeo": {"gender": "Woman"},
}


@pytest.fixture
def jev_on(db_session, monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile(PROFILE, db_session)
    model_settings.set_jev_api_key(db_session, "sk-or-test")
    model_settings.set_autofill_engine(db_session, "jev")


def _fake_jev(monkeypatch, slot_for=None, option_for=None):
    """Fake the MODEL, never the gate (§12). Slot questions are recognised by
    their FREE_TEXT criterion; everything else is an option question."""
    calls = []

    def decide(questions, state, session=None):
        calls.append({"questions": questions, "state": state})
        out = {}
        for qid, q in questions.items():
            if autofill_slots.FREE_TEXT in q["criteria"]:
                choice, p = (slot_for or {}).get(qid, (autofill_slots.NO_SLOT, 0.95))
            else:
                choice, p = (option_for or {}).get(qid, (autofill_choose.NO_OPTION, 0.9))
            out[qid] = {"choice": choice, "probabilities": {choice: p}, "confidence": p}
        return out

    monkeypatch.setattr(autofill_choose.jev, "decide", decide)
    return calls


def _fake_llm(monkeypatch, answers=None):
    prompts = []

    def call_openai(**kwargs):
        prompts.append(kwargs["prompt"])
        return {"choices": {q: {"answer": a} for q, a in (answers or {}).items()}}

    monkeypatch.setattr(autofill_choose.llm, "call_openai", call_openai)
    return prompts


def _field(qid, label, kind="text", options=(), known_value=None):
    return ChooseField(qid=qid, label=label, kind=kind, options=list(options),
                       known_value=known_value)


def test_the_fast_engine_never_calls_jev(db_session, monkeypatch):
    calls = _fake_jev(monkeypatch)
    _fake_llm(monkeypatch)
    autofill_choose.choose([_field("a", "First name")], None, db_session)
    assert calls == []


def test_a_text_field_gets_its_slot_value_without_the_llm(db_session, monkeypatch, jev_on):
    _fake_jev(monkeypatch, slot_for={"a": ("personal.first_name", 0.97)})
    prompts = _fake_llm(monkeypatch)
    out = autofill_choose.choose([_field("a", "Legal first name")], None, db_session)
    assert (out["a"].answer, out["a"].reason) == ("Ada", "matched")
    assert prompts == []


def test_the_slot_question_carries_no_profile_values(db_session, monkeypatch, jev_on):
    calls = _fake_jev(monkeypatch, slot_for={"a": ("personal.first_name", 0.97)})
    _fake_llm(monkeypatch)
    autofill_choose.choose([_field("a", "Legal first name")], None, db_session)
    assert "Ada" not in json.dumps(calls[0])


def test_an_exact_slot_writes_only_a_confident_option(db_session, monkeypatch, jev_on):
    field = _field("s", "Do you need sponsorship?", "select", ["Yes", "No"])
    _fake_jev(monkeypatch, slot_for={"s": ("work_auth.sponsorship_now", 0.95)},
              option_for={"s": ("No", 0.97)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["s"].answer == "No"

    _fake_jev(monkeypatch, slot_for={"s": ("work_auth.sponsorship_now", 0.95)},
              option_for={"s": ("No", 0.7)})
    assert autofill_choose.choose([field], None, db_session)["s"].reason == "abstained"


def test_a_flag_slot_writes_a_near_miss_as_closest(db_session, monkeypatch, jev_on):
    field = _field("m", "Major", "select", ["Information Systems", "Marketing"])
    _fake_jev(monkeypatch, slot_for={"m": ("education.discipline", 0.93)},
              option_for={"m": ("Information Systems", 0.6)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    assert (out["m"].answer, out["m"].reason) == ("Information Systems", "closest")


def test_a_flag_slot_below_the_closest_floor_abstains(db_session, monkeypatch, jev_on):
    field = _field("m", "Major", "select", ["Information Systems", "Marketing"])
    _fake_jev(monkeypatch, slot_for={"m": ("education.discipline", 0.93)},
              option_for={"m": ("Marketing", 0.3)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["m"].reason == "abstained"


def test_no_suitable_option_abstains(db_session, monkeypatch, jev_on):
    field = _field("h", "How did you hear?", "select", ["LinkedIn", "A friend"])
    _fake_jev(monkeypatch, slot_for={"h": ("preferences.how_heard", 0.9)})
    _fake_llm(monkeypatch)
    assert autofill_choose.choose([field], None, db_session)["h"].reason == "abstained"


def test_free_text_and_unmapped_fields_go_to_the_fast_model(db_session, monkeypatch, jev_on):
    _fake_jev(monkeypatch, slot_for={
        "w": (autofill_slots.FREE_TEXT, 0.9),
        "n": (autofill_slots.NO_SLOT, 0.9),
        "l": ("personal.first_name", 0.4),  # below the slot floor
    })
    prompts = _fake_llm(monkeypatch, answers={"w": "Because", "n": "2 weeks", "l": "Ada"})
    out = autofill_choose.choose(
        [_field("w", "Why us?"), _field("n", "Notice"), _field("l", "Name?")], None, db_session)
    assert len(prompts) == 1
    assert {q: c.answer for q, c in out.items()} == {"w": "Because", "n": "2 weeks", "l": "Ada"}


def test_a_known_value_skips_slot_mapping(db_session, monkeypatch, jev_on):
    field = _field("c", "Country", "combobox", ["United States of America", "Canada"],
                   known_value="United States")
    calls = _fake_jev(monkeypatch, option_for={"c": ("United States of America", 0.96)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    assert out["c"].answer == "United States of America"
    assert len(calls) == 1  # the option call only


def test_eeo_values_never_reach_jev_without_consent(db_session, monkeypatch, jev_on):
    from app.schemas.eeo_consent import EeoConsent
    from app.services import eeo_consent

    eeo_consent.set_consent(EeoConsent(enabled=False, policy_version="1"), db_session)
    field = _field("g", "Gender", "select", ["Woman", "Man"])
    calls = _fake_jev(monkeypatch, slot_for={"g": ("eeo.gender", 0.95)},
                      option_for={"g": ("Woman", 0.99)})
    _fake_llm(monkeypatch)
    out = autofill_choose.choose([field], None, db_session)
    # Without consent `eeo` is not a slot: the slot question cannot offer it,
    # so no option question (the only one carrying a value) is ever asked.
    assert "eeo.gender" not in json.dumps(calls[0]["questions"])
    assert len(calls) == 1
    assert out["g"].answer is None


def test_a_failed_slot_call_sends_the_whole_batch_to_the_fast_model(db_session, monkeypatch, jev_on):
    def down(*a, **k):
        raise LLMProviderError("Jev couldn't answer (error 529).")

    monkeypatch.setattr(autofill_choose.jev, "decide", down)
    prompts = _fake_llm(monkeypatch, answers={"a": "Ada"})
    out = autofill_choose.choose([_field("a", "First name")], None, db_session)
    assert out["a"].answer == "Ada" and len(prompts) == 1


def test_a_failed_option_call_sends_only_option_fields_to_the_fast_model(
        db_session, monkeypatch, jev_on):
    real = _fake_jev(monkeypatch, slot_for={
        "a": ("personal.first_name", 0.97), "h": ("preferences.how_heard", 0.9)})
    fake_decide = autofill_choose.jev.decide

    def slot_ok_then_down(questions, state, session=None):
        if any(autofill_slots.FREE_TEXT in q["criteria"] for q in questions.values()):
            return fake_decide(questions, state, session)
        raise LLMProviderError("Jev couldn't answer (error 529).")

    monkeypatch.setattr(autofill_choose.jev, "decide", slot_ok_then_down)
    prompts = _fake_llm(monkeypatch, answers={"h": "LinkedIn"})
    out = autofill_choose.choose(
        [_field("a", "First name"),
         _field("h", "How did you hear?", "select", ["LinkedIn", "A friend"])],
        None, db_session)
    assert out["a"].answer == "Ada" and out["h"].answer == "LinkedIn"
    assert '"h"' in prompts[0] and '"a"' not in prompts[0]
```

Note on the EEO test: without consent `disclosable_profile` drops the `eeo` section, so
`eeo.gender` is not a slot, the fake's pick of it is not in `slots`, and the field falls
through to the (faked) fast model, which answers nothing. The page's own option text
("Woman", "Man") does travel in the slot question's state — that is page content, not the
applicant's answer.

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_autofill_choose_jev.py -q`
Expected: FAIL — `AttributeError: module 'app.services.autofill_choose' has no attribute 'jev'`.

**Step 3: Implement** — in `autofill_choose.py`:

1. Rename the existing `choose` body to `_choose_with_llm(fields, application_id, session)`,
   unchanged. Update the module docstring with one paragraph on the engine switch.
2. Add imports: `import logging`, `from app.services import autofill_slots, jev, model_settings`
   (merge with the existing `from app.services import …` line), `logger = logging.getLogger(__name__)`.
3. Add:

```python
# Jev path thresholds, on the chosen option's probability. Starting values —
# tune them from real fills, not from argument.
SLOT_FLOOR = 0.6
MATCH_FLOOR: dict[autofill_slots.Policy, float] = {"any": 0.5, "flag": 0.85, "exact": 0.9}
CLOSEST_FLOOR = 0.5
NO_OPTION = "(no suitable option)"


def choose(
    fields: list[ChooseField],
    application_id: UUID | None,
    session: Session,
) -> dict[str, Choice]:
    if model_settings.get_autofill_engine(session) == "jev":
        return _choose_with_jev(fields, application_id, session)
    return _choose_with_llm(fields, application_id, session)


def _map_slots(
    fields: list[ChooseField], slots: dict[str, str], session: Session
) -> dict[str, str]:
    """qid → slot, for every field Jev placed with confidence. Labels only."""
    if not fields:
        return {}
    criteria = autofill_slots.slot_criteria(slots)
    state = {"form_fields": [
        {"id": f.qid, "label": f.label, "control": f.kind, "options": f.options}
        for f in fields
    ]}
    questions = {
        f.qid: jev.choice_question(
            f'Which applicant fact does form field {f.qid} ("{f.label}") ask for?', criteria)
        for f in fields
    }
    answers = jev.decide(questions, state, session)
    mapped: dict[str, str] = {}
    for f in fields:
        picked = jev.choice_of(answers.get(f.qid))
        # FREE_TEXT / NO_SLOT are not in `slots`, so they fall through with the rest.
        if picked and picked.choice in slots and picked.probability >= SLOT_FLOOR:
            mapped[f.qid] = picked.choice
    return mapped


def _verdict(
    field: ChooseField, picked: jev.ChoiceAnswer | None, policy: autofill_slots.Policy
) -> Choice:
    # The option guard, as `_answer_for`: only a rendered option is ever written.
    if picked is None or picked.choice not in field.options:
        return Choice(answer=None, reason="abstained")
    if picked.probability >= MATCH_FLOOR[policy]:
        return Choice(answer=picked.choice, reason="matched")
    if policy == "flag" and picked.probability >= CLOSEST_FLOOR:
        return Choice(answer=picked.choice, reason="closest")
    return Choice(answer=None, reason="abstained")


def _pick_options(
    items: list[tuple[ChooseField, str, autofill_slots.Policy]], session: Session
) -> dict[str, Choice]:
    """One Jev call: which rendered option states each field's value."""
    if not items:
        return {}
    state = {"fields": [
        {"id": f.qid, "label": f.label, "applicant_value": value} for f, value, _ in items
    ]}
    questions = {}
    for f, value, _ in items:
        criteria = {option: option for option in f.options}
        criteria[NO_OPTION] = "No option states this value"
        questions[f.qid] = jev.choice_question(
            f'Which option of form field {f.qid} ("{f.label}") states the applicant '
            f'value "{value}"?',
            criteria,
        )
    answers = jev.decide(questions, state, session)
    return {
        f.qid: _verdict(f, jev.choice_of(answers.get(f.qid)), policy)
        for f, _value, policy in items
    }


def _choose_with_jev(
    fields: list[ChooseField], application_id: UUID | None, session: Session
) -> dict[str, Choice]:
    """Jev places what it can; the fast model answers the rest, as it always did.

    Consent-gated like the LLM path: slots come from `disclosable_profile`, so an
    EEO answer without standing consent is not a slot and never reaches Jev."""
    slots = autofill_slots.flatten(eeo_consent.disclosable_profile(session))
    try:
        mapped = _map_slots([f for f in fields if not f.known_value], slots, session)
    except llm.LLMProviderError:
        logger.warning("jev slot mapping failed; the fast model answers this batch")
        return _choose_with_llm(fields, application_id, session)

    out: dict[str, Choice] = {}
    to_pick: list[tuple[ChooseField, str, autofill_slots.Policy]] = []
    fallback: list[ChooseField] = []
    for f in fields:
        slot = mapped.get(f.qid)
        value = f.known_value or (slots[slot] if slot else None)
        if value is None:
            fallback.append(f)
        elif not f.options:
            out[f.qid] = Choice(answer=value, reason="matched")
        else:
            to_pick.append((f, value, autofill_slots.policy_for(slot)))
    try:
        out.update(_pick_options(to_pick, session))
    except llm.LLMProviderError:
        logger.warning("jev option pick failed; the fast model answers those fields")
        fallback.extend(f for f, _value, _policy in to_pick)
    if fallback:
        out.update(_choose_with_llm(fallback, application_id, session))
    return out
```

`eeo_consent` is already imported (it is used by the LLM path's prompt); if not, import it.

**Step 4: Run to verify they pass — and the old suite still does**

Run: `python3 -m pytest tests/test_autofill_choose_jev.py tests/test_autofill_choose.py tests/test_autofill_router.py -q`
Expected: PASS. The existing consent tests must pass untouched — they run with the default
`fast` engine.

**Step 5: Commit**

```bash
git add backend/app/services/autofill_choose.py backend/tests/test_autofill_choose_jev.py
git commit -m "feat(autofill): Jev maps fields to profile slots and picks options, fast model answers the rest"
```

---

### Task 7: Extension — write `closest` answers and list them for checking

**Files:**
- Modify: `extension/shared/guided-run.js` (the `toWrite` filter ~line 243; the return ~line 297)
- Modify: `extension/panel/actions/fill.js` (the per-run clear ~line 336; the result write ~line 413)
- Modify: `extension/panel/panel.js` (store defaults near `residue`/`essays`; add a doc comment)
- Modify: `extension/panel/stages/fill.js` (a `checkList` beside `needsList`, attached at ~line 704)
- Test: `backend/tests/test_extension_guided_fill.py`, `backend/tests/test_extension_panel_fill.py`

**Step 1: Write the failing tests**

In `test_extension_guided_fill.py`, make the driver's `api` fake honour a `closest` spec — inside
the `for (const field of …)` loop:

```js
      choices[field.qid] = spec.abstainAll
        ? { answer: null, reason: "abstained" }
        : (spec.closest ?? []).includes(field.qid)
          ? { answer: "Closest", reason: "closest" }
          : { answer: "Yes", reason: "matched" };
```

and add:

```python
def test_a_closest_answer_is_written_and_reported_for_checking(tmp_path):
    """`closest` is an ANSWER — the model found no exact option and picked the
    nearest one a factual slot allows — so it is written like `matched`, and
    handed back separately so the Fill report can ask the user to check it."""
    out = _run_guided(tmp_path, questions=_open_questions(2), closest=["q1"])

    pairs = {pair["qid"]: pair["answer"] for pair in _writes(out)[0]["pairs"]}
    assert pairs == {"q0": "Yes", "q1": "Closest"}
    assert [(row["qid"], row["answer"]) for row in out["result"]["closest"]] == [
        ("q1", "Closest")]
    assert out["result"]["residue"] == []


def test_a_closest_answer_that_did_not_stick_is_residue_not_a_check(tmp_path):
    out = _run_guided(tmp_path, questions=_open_questions(1), closest=["q0"],
                      writeOutcomes={"q0": "not_stuck"})
    assert out["result"]["closest"] == []
    assert [row["qid"] for row in out["result"]["residue"]] == ["q0"]
```

In `test_extension_panel_fill.py`, add (use the file's existing `_fill`, `_by_class`, `_text`
helpers; read `test_the_progress_rows_are_the_runs_own_report` for how the output tree is read,
and match its `out[...]` access for the rail region):

```python
def test_a_closest_pick_is_listed_for_the_user_to_check(tmp_path):
    out = _fill(tmp_path, start=True, api={"/api/autofill/choose": _reply({"choices": {
        "q1": {"answer": "Night", "reason": "closest"},
        "q2": {"answer": "LinkedIn", "reason": "matched"},
    }})})
    [check] = [node for node in _by_class(out["regions"]["rail"], "resid")
               if node.get("aria-label") == "Closest matches to check"]
    assert "preferred shift" in _text(check) and "Night" in _text(check)
```

(If the harness exposes attributes differently, find the list by its `checklist` class instead.)

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_extension_guided_fill.py tests/test_extension_panel_fill.py -q -k closest`
Expected: FAIL — `closest` missing from the result / no such list.

**Step 3: Implement**

`guided-run.js`, the `toWrite` filter:

```js
          return choice && (choice.reason === "matched" || choice.reason === "closest")
            && choice.answer;
```

After `residue` is computed (before `onProgress({ phase: "residue", … })`):

```js
    // Written, but on the page's nearest option rather than the profile's own
    // value (a `closest` answer): the report asks the user to check these. A
    // closest pick that did not stick is residue like any other write.
    const closest = routed.chooseFields
      .filter((field) => choices[field.qid]?.reason === "closest"
        && writtenQids.has(field.qid) && !residueQids.has(field.qid))
      .map((field) => ({ ...field, answer: choices[field.qid].answer }));
```

and add `closest` to the returned object:
`return { essays: routed.essays, residue, closest, writeResults, blank, aiFailure: failure };`.
Update the JSDoc for the return value if one lists its keys.

`panel/actions/fill.js`: add `closest: null` to the per-run clear at ~line 336 and
`closest: out.closest ?? []` to the `store.write` at ~line 413.

`panel/panel.js`: add a `closest: null` default next to `residue`, with a doc comment in the
file's style ("The runner's closest-match writes, `{qid, label, answer, …}`, or null until a
fill has run. Written fields, not open ones — they never count toward `open`."). If
`sessionEntryFrom` carries `residue`, carry `closest` the same way; if it does not, do not.

`panel/stages/fill.js`, beside `needsList`:

```js
  /** Fields the run WROTE on the page's nearest option, not the profile's own
   * value — "Information Systems" for a Business Analytics major. Filled, so
   * they are not in the still-open list and never hold the stage open; listed
   * so the user can check each one before submitting. A jump per row, as
   * `needsList`. */
  function checkList(ctx, { closest }) {
    const { build, act } = ctx;
    if (!closest?.length) return null;
    const list = build.node("ul", "resid checklist");
    list.setAttribute("aria-label", "Closest matches to check");
    for (const row of closest) {
      const button = build.node("button", null, fieldName(row));
      button.type = "button";
      button.addEventListener("click", () => act.scrollToField(row.qid));
      build.attach(list, build.attach(build.node("li"), button,
        build.node("span", "kindmark", ` · closest match: ${row.answer} `)));
    }
    return list;
  }
```

and in the body at ~line 704: `attach(body, attachRow(ctx), needsList(ctx, run), checkList(ctx, { closest: facts.closest }), qnaDrawer(ctx));`
(match how `run` is built at ~line 693 — if `run` is the object passed to `needsList`, add
`closest: facts.closest ?? []` to it and pass `run` instead).

**Step 4: Run to verify they pass — and the whole extension suite still does**

Run: `python3 -m pytest tests/ -q -k extension`
Expected: PASS.

**Step 5: Commit**

```bash
git add extension/ backend/tests/test_extension_guided_fill.py backend/tests/test_extension_panel_fill.py
git commit -m "feat(companion): write closest-match answers and list them for checking"
```

---

### Task 8: Settings › AI & models — the Form filling card

**Files:**
- Modify: `frontend/lib/types.ts` (next to `OpenAIInfo`)
- Create: `frontend/components/settings/form-filling-section.tsx`
- Modify: `frontend/components/settings/models-section.tsx` — export `KeyField` (add `export`)
- Modify: `frontend/app/settings/page.tsx:71-72` — render `<FormFillingSection />` after `<ModelsSection />`

**Step 1: Types** (`lib/types.ts`)

```ts
/** GET/PUT /api/settings/jev. The key is write-only: only `api_key_configured` comes back. */
export type JevInfo = {
  api_key_configured: boolean;
  base_url: string;
  model: string;
  engine: "fast" | "jev";
};
```

**Step 2: The card** (`components/settings/form-filling-section.tsx`). Follow `ApiKeysSection`
exactly for the key input (null = untouched, `useLeaveGuard`, `useSingleFlight`, `readOnly`
while saving) and `SettingCard` for loading/error states:

```tsx
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { NewTabLink } from "@/components/new-tab-link";
import { KeyField } from "@/components/settings/models-section";
import { SettingCard } from "@/components/settings/setting-card";
import { ACTION_ROW } from "@/components/settings/setting-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useLeaveGuard } from "@/hooks/use-leave-guard";
import { useSingleFlight } from "@/hooks/use-single-flight";
import { apiFetch } from "@/lib/api";
import { couldnt } from "@/lib/error-text";
import type { JevInfo } from "@/lib/types";

type JevPatch = Partial<Pick<JevInfo, "base_url" | "model" | "engine">> & {
  api_key?: string | null;
};

const PROVIDERS = [
  { url: "https://openrouter.ai/api", label: "OpenRouter", model: "typesafe/jev-1.13" },
  { url: "https://api.typesafe.ai", label: "TypeSafe", model: "jev-latest" },
] as const;

function useJevInfo() {
  return useQuery({
    queryKey: ["settings", "jev"],
    queryFn: () => apiFetch<JevInfo>("/api/settings/jev"),
  });
}

export function FormFillingSection() {
  const info = useJevInfo();
  const qc = useQueryClient();
  const [key, setKey] = useState<string | null>(null);
  useLeaveGuard(key !== null);

  const save = useMutation({
    mutationFn: (patch: JevPatch) =>
      apiFetch<JevInfo>("/api/settings/jev", { method: "PUT", body: JSON.stringify(patch) }),
    onSuccess: (result) => {
      qc.setQueryData(["settings", "jev"], result);
      setKey(null);
    },
    onError: (err: Error) => toast.error(couldnt("save your form filling settings", err)),
  });
  const saveOnce = useSingleFlight(save.mutate);

  const probe = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; error: string | null }>("/api/settings/jev/probe", {
        method: "POST",
      }),
    onSuccess: (r) => (r.ok ? toast.success("Jev answered.") : toast.error(r.error ?? "Jev didn't answer.")),
    onError: (err: Error) => toast.error(couldnt("test your Jev key", err)),
  });

  return (
    <SettingCard
      id="form-filling"
      title="Form filling"
      description="Jev picks answers for application forms in about a tenth of a second. Questions that need a written answer still go to your fast model."
      errorTitle="Couldn't load your form filling settings."
      skeleton="h-32 w-full"
      query={info}
    >
      {(data) => (
        <div className="grid gap-6">
          <div className="grid items-end gap-4 @lg/setting:grid-cols-2">
            <KeyField
              label="Jev API key"
              hintUnset={
                <>
                  An <NewTabLink href="https://openrouter.ai/keys">OpenRouter</NewTabLink> key
                  works, or one from typesafe.ai.
                </>
              }
              configured={data.api_key_configured}
              source={data.api_key_configured ? "settings" : "none"}
              value={key}
              saving={save.isPending}
              onChange={setKey}
            />
            <div className="grid gap-1.5">
              <Label className="text-xs">Provider</Label>
              <Select
                value={data.base_url}
                onValueChange={(url) => {
                  const provider = PROVIDERS.find((p) => p.url === url);
                  if (provider) saveOnce({ base_url: provider.url, model: provider.model });
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p.url} value={p.url}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Form filling decisions</Label>
            <Select
              value={data.engine}
              disabled={!data.api_key_configured}
              onValueChange={(engine) => saveOnce({ engine: engine as JevInfo["engine"] })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">Fast model</SelectItem>
                <SelectItem value="jev">Jev</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className={ACTION_ROW}>
            <Button
              size="sm"
              disabled={save.isPending || key === null}
              onClick={() => saveOnce({ api_key: key?.trim() || null })}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data.api_key_configured || probe.isPending}
              onClick={() => probe.mutate()}
            >
              {probe.isPending ? "Testing…" : "Test"}
            </Button>
          </div>
        </div>
      )}
    </SettingCard>
  );
}
```

Before finalising the copy, read `docs/frontend-conventions.md`'s copy rules and run
`python3 -m pytest tests/test_frontend_vocabulary.py -q` from `backend/` — it enforces the
canonical terms and may reject a word above. `KeyField`'s `source` prop is typed from
`OpenAIInfo["openai_key_source"]`; `"settings" | "none"` fits it.

**Step 3: Gates** (from `frontend/`)

Run: `npx tsc --noEmit && npm run lint && npm run build`
Expected: all three clean.

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(settings): Form filling card — Jev key, provider, test and engine choice"
```

---

### Task 9: Docs

**Files:**
- Modify: `SYSTEM.md` — §6 `inv-eeo-standing-consent` (Jev, and OpenRouter when used, are
  model-provider recipients; the Jev path reads slots from `disclosable_profile`; name
  `test_autofill_choose_jev.py::test_eeo_values_never_reach_jev_without_consent` as an
  enforcement point); §7 Guided fill (engine switch, two Jev calls, `closest`, the fallback
  rule, the Form filling card); §2 services list (`jev`, `autofill_slots`). Rewrite in present
  tense — no dated paragraphs outside §11–§13 (header contract).
- Modify: `.system_md_enforcement.json` if the gate requires the new enforcement point pinned.
- Modify: `extension/INTERNALS.md` — `/choose` reasons now include `closest`; the Fill report's
  "Closest matches to check" list.
- Modify: `docs/plans/2026-09-25-jev-autofill-design.md` — already records the `none` →
  fast-model rule; mark status "implemented".

**Step 1:** Make the edits.
**Step 2:** Run `python3 scripts/check_system_md.py` from the repo root (and
`python3 -m pytest tests/ -q -k "system_md or slop"` from `backend/` if such tests exist).
Expected: clean.
**Step 3: Commit**

```bash
git add SYSTEM.md .system_md_enforcement.json extension/INTERNALS.md docs/plans/
git commit -m "docs: Jev as the optional form-filling engine (SYSTEM.md §6/§7, INTERNALS)"
```

---

### Task 10: Full gate and live check

**Step 1:** From `backend/`: `python3 -m pytest tests/ mcp_server/tests/ -q` — Expected: all green.

**Step 2: Live check (needs the owner).** Start a worktree stack per the worktree
verification recipe (uvicorn on a spare port with a scratch SQLite DB, frontend via
`preview_start`) — never the live compose stack. In Settings › AI & models › Form filling,
the owner pastes their OpenRouter key, presses **Test** (expect "Jev answered."), and switches
**Form filling decisions** to **Jev**. Point the unpacked extension at that backend and run
**Fill this form** on a real Greenhouse or Workday posting. Check:
- a Major/Discipline select without "Business Analytics" lands on its nearest option and
  appears under **Closest matches to check**;
- sponsorship / work-authorization selects are either exact or left open, never "closest";
- an essay question still reaches the fast model / QnA drawer;
- `logs/llm_calls/` holds metadata-only rows for the Jev calls.

Report what happened, with the field labels, to the owner before any merge.
