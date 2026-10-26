# Who writes over MCP, and tailoring without Maestro's AI: implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development in this session) to implement this plan task-by-task.

**Goal:** Over MCP, exactly one side the user chose does the writing (the agent app by default); tailoring works end to end without Maestro's AI key; `quick_tailor` folds into `create_tailoring_session` and `tailor_application` leaves MCP.

**Design:** `docs/plans/2026-10-26-mcp-writer-and-tailoring-design.md` (owner-approved 2026-10-26). Read it first; this plan does not repeat its reasons.

**Architecture:** A pure ASGI middleware marks a request as an agent request when it carries `X-Maestro-CS-Origin: mcp`; the MCP client now sends that header on every request. `app/agent_writer.py` answers "may Maestro's AI write for this request?" from that mark and the saved `writer` setting. `llm.call_openai` refuses an agent request in agent mode (the backstop: every model call, including ones the design did not list, such as `kb_ingest_resume`'s matching and clustering). The five writing routes refuse first with a message naming the tool to use instead; the health check and the resume import take their no-AI path quietly.

**Found while planning (inside the approved principle):** `kb_ingest_resume` calls Maestro's AI (entity matching and bullet clustering in `kb_consolidation.consolidate`) whenever a key exists, and falls back to a deterministic path when the call fails. The backstop plus a quiet skip covers it; no new design decision.

**Tech stack:** FastAPI, SQLAlchemy, pydantic v2, FastMCP (`mcp` SDK), httpx + respx (client tests), Next.js + React Query (Settings card), pytest with xdist.

**Constraints:**
- Never start the Docker stack; never bind ports 8001 or 3000 (the live app). Live checks use a spare port and a scratch `MAESTRO_HOME`.
- The repo is public: neutral sample data only, no company names beyond the existing fixtures.
- Interpreter: `PY=/private/tmp/claude-501/-Users-ajeyds-Projects-maestro-career-studio--claude-worktrees-api-independence-no-gui-85e978/cfe7e029-00a1-45a8-8e93-1de9ac840714/scratchpad/venv/bin/python`. Run tests from `backend/` as `env -u ANTHROPIC_BASE_URL $PY -m pytest -q -p no:cacheprovider <paths>`; the full suite always with `-n auto --dist loadfile`.
- TDD: every task writes the failing test first and watches it fail for the right reason.
- Commit per task with the attribution line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push or merge.

---

### Task 1: `writer` on the saved MCP setting

**Files:**
- Modify: `backend/app/schemas/mcp_workflow.py`
- Modify: `backend/app/services/mcp_workflow.py` (add `peek_settings`)
- Modify: `frontend/lib/types.ts` (`McpWorkflowSettings`)
- Test: `backend/tests/test_settings_router.py`

**Step 1: failing tests** (next to the existing `test_mcp_workflow_*` tests, same fixtures):

```python
def test_mcp_workflow_writer_defaults_to_the_agent_app(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    assert client.get("/api/settings/mcp-workflow").json()["value"] == {"hints": True, "writer": "agent"}


def test_mcp_workflow_writer_round_trips_and_refuses_other_values(db_session, tmp_path, monkeypatch, client):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    assert client.put("/api/settings/mcp-workflow",
                      json={"value": {"hints": True, "writer": "maestro"}}).status_code == 200
    assert client.get("/api/settings/mcp-workflow").json()["value"]["writer"] == "maestro"
    assert client.put("/api/settings/mcp-workflow",
                      json={"value": {"hints": True, "writer": "someone"}}).status_code == 422
```

Update `test_mcp_workflow_defaults_to_hints_on` to expect `{"hints": True, "writer": "agent"}`.

**Step 2:** run `tests/test_settings_router.py -k mcp_workflow`; expect the new tests to FAIL (no `writer` key).

**Step 3: implement**

```python
# backend/app/schemas/mcp_workflow.py
from typing import Literal

from pydantic import BaseModel

# Who writes for a connected agent app (design 2026-10-26): "agent" = the agent app writes and Maestro's
# AI never runs for an agent request; "maestro" = Maestro's AI writes with the user's key.
Writer = Literal["agent", "maestro"]


class McpWorkflowSettings(BaseModel):
    hints: bool = True
    writer: Writer = "agent"
```

Update the module docstring ("One boolean today" is no longer true). In `services/mcp_workflow.py` add:

```python
def peek_settings(session: Session | None = None) -> McpWorkflowSettings:
    """Read without seeding a Setting row (the per-request writer check)."""
    return MCP_WORKFLOW.peek(session)
```

In `frontend/lib/types.ts`: `export interface McpWorkflowSettings { hints: boolean; writer: "agent" | "maestro"; }`. The hints card already sends `{ ...setting.data?.value, hints }`, so it keeps `writer`.

**Step 4:** run the settings tests; PASS. **Step 5:** commit `feat(settings): who writes for a connected agent app`.

---

### Task 2: `app/agent_writer.py` and the request mark

**Files:**
- Create: `backend/app/agent_writer.py`
- Modify: `backend/app/main.py` (register the middleware and the 409 handler)
- Test: `backend/tests/test_agent_writer.py` (new)

**Step 1: failing tests**

```python
"""Who writes for an agent request (design 2026-10-26): the request mark and the setting."""
from fastapi.testclient import TestClient

from app import agent_writer
from app.schemas.mcp_workflow import McpWorkflowSettings
from app.services import llm, mcp_workflow


def _writer(monkeypatch, writer):
    monkeypatch.setattr(mcp_workflow, "peek_settings", lambda session=None: McpWorkflowSettings(writer=writer))


def test_maestro_always_writes_outside_an_agent_request(monkeypatch):
    _writer(monkeypatch, "agent")
    assert agent_writer.maestro_writes() is True  # the web app and the Companion


def test_an_agent_request_in_agent_mode_gets_no_maestro_writing(monkeypatch):
    _writer(monkeypatch, "agent")
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is False
    _writer(monkeypatch, "maestro")
    with agent_writer.agent_request():
        assert agent_writer.maestro_writes() is True


def test_model_available_needs_a_key_and_maestro_writing(monkeypatch):
    _writer(monkeypatch, "agent")
    monkeypatch.setattr(llm, "any_model_key_configured", lambda: True)
    assert agent_writer.model_available() is True
    with agent_writer.agent_request():
        assert agent_writer.model_available() is False


def test_the_middleware_marks_only_requests_with_the_mcp_origin(client, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_writer, "_on_request", lambda: seen.append(agent_writer.is_agent_request()))
    client.get("/api/health", headers={"X-Maestro-CS-Origin": "mcp"})
    client.get("/api/health")
    assert seen == [True, False]
```

(Use whatever cheap GET route the app has if `/api/health` is not one; `_on_request` is a test seam called inside the marked context.)

**Step 2:** run; FAIL (module missing).

**Step 3: implement**

```python
"""Who writes for an agent request: Maestro's AI or the agent app (Settings › Agent apps).

A request is an agent request when it carries the MCP origin header (app/write_origin.py); the MCP
client sends it on every call. The mark is a ContextVar set by AgentRequestMiddleware, a pure ASGI
middleware, so it reaches sync routes on the threadpool (contextvars are copied into worker threads).
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar

from fastapi import HTTPException

_AGENT_REQUEST: ContextVar[bool] = ContextVar("maestro_agent_request", default=False)

AGENT_WRITES = ("Your settings say your agent app writes, so Maestro's AI doesn't write for agent apps "
                "(Settings › Agent apps changes it).")


class AgentWritesError(Exception):
    """A model call for an agent request while the agent app writes (llm.call_openai's backstop)."""


def is_agent_request() -> bool:
    return _AGENT_REQUEST.get()


@contextlib.contextmanager
def agent_request():
    token = _AGENT_REQUEST.set(True)
    try:
        yield
    finally:
        _AGENT_REQUEST.reset(token)


def maestro_writes() -> bool:
    """Whether Maestro's AI may write for this request: always for the web app and the Companion; for an
    agent request only when the user chose Maestro's AI."""
    if not is_agent_request():
        return True
    from app.services import mcp_workflow  # noqa: PLC0415 (settings import the DB layer)

    return mcp_workflow.peek_settings().writer == "maestro"


def model_available() -> bool:
    """A key is set and Maestro's AI may write for this request: the health check and the resume
    import ask this before calling a model, so agent mode takes their no-AI path quietly."""
    from app.services import llm  # noqa: PLC0415

    return llm.any_model_key_configured() and maestro_writes()


def refuse_unless_maestro_writes(instead: str) -> None:
    """A writing route's own refusal, naming the tool that takes the agent's text."""
    if not maestro_writes():
        raise HTTPException(status_code=409, detail=f"{AGENT_WRITES} {instead}")


def _on_request() -> None:  # test seam
    return None


class AgentRequestMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = dict(scope.get("headers") or []).get(b"x-maestro-cs-origin")
        token = _AGENT_REQUEST.set(origin == b"mcp")
        try:
            _on_request()
            await self.app(scope, receive, send)
        finally:
            _AGENT_REQUEST.reset(token)
```

In `main.py`: `app.add_middleware(AgentRequestMiddleware)` placed BEFORE the existing `add_middleware` calls (add_middleware prepends, so the earliest call is innermost; the host/origin order test must stay green), and:

```python
@app.exception_handler(AgentWritesError)
async def agent_writes_handler(request: Request, exc: AgentWritesError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})
```

**Step 4:** run `tests/test_agent_writer.py` and the middleware-order test (`-k host_check_outranks`); PASS. **Step 5:** commit `feat(agents): mark agent requests and say who writes for them`.

---

### Task 3: the backstop in `llm.call_openai`

**Files:** Modify `backend/app/services/llm.py`; Test `backend/tests/test_agent_writer.py`.

**Step 1: failing test**

```python
def test_no_model_call_runs_for_an_agent_request_in_agent_mode(monkeypatch):
    _writer(monkeypatch, "agent")
    monkeypatch.setattr(llm, "_call_model", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model reached")))
    with agent_writer.agent_request():
        with pytest.raises(agent_writer.AgentWritesError):
            llm.call_openai(prompt="p", model="m")
```

**Step 2:** FAIL (`AssertionError: model reached` or no raise). **Step 3:** first lines of `call_openai`:

```python
    from app import agent_writer  # noqa: PLC0415

    if not agent_writer.maestro_writes():
        # The backstop (design 2026-10-26): whichever route asked, an agent request never reaches
        # Maestro's model while the agent app writes.
        raise agent_writer.AgentWritesError(agent_writer.AGENT_WRITES)
```

**Step 4:** PASS; then run `tests/test_llm*.py tests/test_kb_ingest*.py` for collateral. **Step 5:** commit `feat(llm): an agent request never reaches Maestro's model in agent mode`.

---

### Task 4: the MCP client marks every request

**Files:** Modify `backend/mcp_server/client.py` (`_send`); Test `backend/mcp_server/tests/test_client_write.py` (or a new `test_client_origin.py`).

**Step 1: failing test** (respx, like the existing client tests): `get_job`, `generate_cover_letter`, `run_health_check`, `create_tailoring_session`, `tailor_session` each send `X-Maestro-CS-Origin: mcp`; a call that already passes a detail (`kb_add_points(..., origin_detail="Claude")`) still sends its `X-Maestro-CS-Origin-Detail`.

**Step 2:** FAIL for the four that send no header today. **Step 3:** in `_send`, merge a default `{"X-Maestro-CS-Origin": "mcp"}` under any caller headers (`headers = {"X-Maestro-CS-Origin": "mcp", **(kwargs.pop("headers", None) or {})}`). Every route that reads the origin (`agent_runs`, `applications`, `career_kb`, `base_resumes`, `qa`, `proposals`, `resume_lint`) already receives it from MCP today, so no behaviour changes there; say so in a comment.

**Step 4:** run `mcp_server/tests/` with xdist; PASS. **Step 5:** commit `feat(mcp): every request says it came from an agent app`.

---

### Task 5: the writing routes refuse with the tool to use instead

**Files:** Modify `backend/app/routers/qa.py` (`run_qa`), `backend/app/routers/career_kb.py` (`capture_points`), `backend/app/routers/tailoring_sessions.py` (`create_tailoring_session` with `enrich`, `tailor_session` with neither `ops` nor `no_new_text`; `no_new_text` arrives in Task 7, so this task guards "no ops" and Task 7 adds the second condition). Tests: `tests/test_qa_router.py`, a capture test file (find the existing `/api/kb/capture` tests), `tests/test_tailoring_sessions_router.py`.

**Step 1: failing tests**, one per route, each in three cases:
- MCP origin + writer agent → 409 naming the alternative (`store_cover_letter`, `store_qa_answers`, `kb_add_points`, "without enrich", "ops"), and the model is never called (`_forbid_llm`-style monkeypatch);
- no origin (the web) + writer agent → the route runs as today (model mocked);
- MCP origin + writer maestro → runs as today.

Set the writer with `client.put("/api/settings/mcp-workflow", json={"value": {"hints": True, "writer": "agent"}})` under the settings-dir monkeypatch the settings tests use.

**Step 2:** FAIL. **Step 3:** at the top of each handler (before any write):

```python
agent_writer.refuse_unless_maestro_writes(
    "Write the letter yourself and save it with store_cover_letter."  # cover_letter requests
)
# questions: "Write the answers yourself and save them with store_qa_answers."
# capture:   "Write the bullets yourself and save them with kb_add_points."
# create:    only when payload.enrich: "Start the gap analysis without enrich."
# tailor:    only when not (payload and payload.ops): "Pass your own edits as ops, or no_new_text."
```

The tailor guard must not fire for the web's `apply_profile` one-call path (no MCP origin) — covered by the "no origin" case.

**Step 4:** PASS. **Step 5:** commit `feat(agents): Maestro's writing routes point agent apps at their own tools`.

---

### Task 6: the health check and the resume import take their no-AI path

**Files:** Modify `backend/app/routers/resume_lint.py` (`_judging`, `run_lint`, `record_judgments`), `backend/app/services/kb_consolidation.py` (`consolidate`: skip `_resolve_family`'s and `_cluster_points_for_entity`'s model calls when `not agent_writer.model_available()`, taking the existing deterministic fallback without its "LLM failed" warning). Tests: `tests/test_health_keyless.py`, `tests/test_health_routes.py`, an ingest test (find the existing `/api/kb/ingest-parsed` tests).

**Step 1: failing tests**
- key configured (`monkeypatch.setattr(llm, "any_model_key_configured", lambda: True)`), writer agent, MCP origin: `POST /api/resume-lint/base/<slug>/run` returns a `judging` brief, makes no model call, and `POST .../judgments` is accepted (today it is refused while a key is set).
- the same with no origin (the web): the model judges as today and `judgments` is still refused.
- `POST /api/kb/ingest-parsed` with MCP origin, key configured, writer agent: no model call, no `entity_resolve LLM failed` warning in the report, entities created deterministically.

**Step 2:** FAIL. **Step 3:**

```python
def _judging(db: Session, resume: dict) -> dict | None:
    """The brief a connected agent judges by: whenever Maestro's own model doesn't judge this request."""
    return None if agent_writer.model_available() else resume_lint.judging_brief(db, resume)

# run_lint:
row = resume_lint.run_report(db, kind, key, resume, template_id=template_id,
                             use_llm=agent_writer.model_available())

# record_judgments: refuse only while Maestro's model judges this request
if agent_writer.model_available():
    raise HTTPException(status_code=409, detail="Maestro judges the bullets with its own model for this "
                        "request. Run the health check instead.")
```

In `consolidate`, compute `use_model = agent_writer.model_available()` once and pass it into the two helpers; when False they take the singleton / no-clustering path directly.

**Step 4:** PASS, plus `tests/test_health*.py tests/test_kb*.py` with xdist. **Step 5:** commit `feat(agents): the health check and resume import never run Maestro's AI for an agent app that writes`.

---

### Task 7: `no_new_text` on the tailor

**Files:** Modify `backend/app/schemas/tailoring_session.py` (`TailorRequest`), `backend/app/services/tailoring_session.py` (`tailor`), `backend/app/routers/tailoring_sessions.py` (pass it; tailor guard from Task 5 becomes "neither ops nor no_new_text"). Test: `backend/tests/test_tailor_ops_keywords.py` (reuse its fixtures and `_forbid_llm`).

**Step 1: failing tests**

```python
def test_no_new_text_applies_only_what_needs_no_wording(db_session, tmp_path, monkeypatch, client):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    _forbid_llm(monkeypatch)  # with a key configured it still must not call the model
    created = _open_session(client, job, slug,
                            resolutions=[SNOWFLAKE_PLACE_ONLY, SALESFORCE_WORDED, ML_MODELS_ANSWER, DOCKER_PROJECT])

    response = _tailor(client, created["id"], body={"no_new_text": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["keywords_added"]) == ["Salesforce", "Snowflake"]
    assert body["answers_left_to_ops"] == [
        {"gap_id": "coverage:0", "action": "user_input", "skill": "Build ML models"},
        {"gap_id": "skill:docker", "action": "attach_project", "skill": "Docker"},
    ]
    application = db_session.get(Application, UUID(body["session"]["application_id"]))
    assert "Snowflake" in _skills(application)["Cloud"]
    assert not any("churn" in b for b in _bullets(application))  # the typed answer needs wording


def test_no_new_text_with_ops_is_refused(...):  # 422, nothing written
def test_no_new_text_with_nothing_to_apply_says_so(...):  # only skip/user_input saved -> 400 "nothing ... without new wording"
```

Add a test that an `enable_entry` / `port_kb_point` saved answer lands with `no_new_text` (find a fixture in `tests/test_tailoring_sessions_router.py` that saves one, e.g. search `port_kb_point`).

**Step 2:** FAIL. **Step 3:**
- `TailorRequest.no_new_text: bool = False`, with a `model_validator(mode="after")` raising `ValueError("no_new_text writes nothing new, so it takes no ops")` when both are set.
- `tailor(..., no_new_text: bool = False)`: when true, after `pre_ops`, set `customized = copy.deepcopy(base)` without `_resolution_bundle`'s model call; keep `_reject_stale_placements`, the voice repair and keyword survival as they are; compute `left_to_ops` when `ops or no_new_text`; after keyword survival, if `not pre_ops and not keywords_added` raise `ValueError("There is nothing to apply without new wording: every saved answer needs text written for it.")`. Update the docstring's "Two ways" to three.
- Router passes `no_new_text=payload.no_new_text if payload else False`.

**Step 4:** PASS, plus `tests/test_tailoring*.py tests/test_tailor*.py tests/test_quick_tailor.py`. **Step 5:** commit `feat(tailor): a tailor that writes no new wording and needs no AI key`.

---

### Task 8: `unbacked_skills` on every tailor response

**Files:** `backend/app/services/tailoring_session.py`, `backend/app/schemas/tailoring_session.py` (`TailorResponse.unbacked_skills: list[str] = Field(default_factory=list)`), `backend/app/routers/tailoring_sessions.py` (`"unbacked_skills": getattr(row, "unbacked_skills", [])`). Test: `backend/tests/test_tailor_ops_keywords.py`.

**Definition:** the wording of each saved `add_keyword` resolution whose gap sits in the `missing_skills` category of `gaps_json` and whose payload carries no `provenance` (a provenance-carrying auto is backed by career history), and which is on the tailored resume's skills list after the tailor. Order as saved, no duplicates.

**Step 1: failing test:** pick a gap from `created["gaps_json"]` category `missing_skills`, save `add_keyword` with its `jd_skill` as wording to skills, tailor with `no_new_text`, assert `unbacked_skills == [that skill]`; an `adjacent` keyword (Snowflake) is not listed. Repeat on the ops path (one case is enough).

**Step 2–5:** as usual; commit `feat(tailor): name the skills career history doesn't back`.

---

### Task 9: MCP `tailor_session`: `no_new_text`, the truth about the PDF, the render hint

**Files:** `backend/mcp_server/client.py` (`tailor_session(..., no_new_text: bool = False)`, sent only when true), `backend/mcp_server/server.py` (`tailor_session` tool param + docstring), `backend/mcp_server/workflow.py` (`next_after_tailor(..., pdf_ready: bool = False)`). Tests: `mcp_server/tests/test_client_sessions.py`, `test_workflow.py`, `test_workflow_wiring.py`.

- Docstring: three ways (Maestro's AI with no ops, when the writer setting allows it; your `ops`; `no_new_text`); the writer setting (`get_setup_status.writer`); it renders the PDF (`pdf_ready`); `unbacked_skills`; drop the "same op shapes as tailor_application" reference (name `edit_application` and `edit_base_resume`).
- `next_after_tailor`: the render option only when `pdf_ready` is false; `call` is `"render_pdf"` only then. The wiring passes `result.get("pdf_ready", False)`.
- Tests first: client body carries `no_new_text: true` only when set; hint with `pdf_ready=True` names no `render_pdf`; with `False` names it; the docstring mentions `no_new_text` and `pdf_ready`.

Commit `feat(mcp): tailor_session writes no new text on request and says the PDF is made`.

---

### Task 10: `create_tailoring_session(use_presets=...)` replaces `quick_tailor`

**Files:** `backend/mcp_server/server.py` (merge; delete the `quick_tailor` tool), `backend/mcp_server/workflow.py` (`next_after_scores`: the presets option becomes `{"tool": "create_tailoring_session", "args": {..., "use_presets": True}}` labelled "Tailor <base> with the saved presets"; offer texts; `next_after_session` docstring), `backend/mcp_server/profiles.py` (drop `quick_tailor` from `TAILOR_TOOLS`), `get_tailoring_options`'s instruction text. Tests: `mcp_server/tests/test_workflow_wiring.py` (rewrite the `quick_tailor` tests for `use_presets`), `test_server.py` (tool name lists), `test_workflow.py`, `test_profiles.py` sizes (`tailor` 31), `test_orientation_tools.py`.

```python
@mcp.tool(**_write("Start Tailoring Session", destructive=True, idempotent=False, open_world=True))
@_guard
def create_tailoring_session(job_id: str, base_resume: str, enrich: bool = False,
                             use_presets: bool = False) -> Any:
    """... (existing text) ...
    use_presets=True fills every gap the user's Quick tailor presets decide (get_tailoring_options
    explains them), deterministically and with no AI; undecided gaps are saved as skip ..."""
    session = _client.create_tailoring_session(job_id, base_resume, enrich=enrich)
    if not use_presets:
        return {**session, "next": _session_hint(session)}
    try:
        filled = _client.apply_quick_tailor_profile(session["id"])
    except BackendError as exc:
        raise ToolError(
            f"The gap analysis {session['id']} was started, but filling it from the presets failed: {exc}. "
            "Save answers on it with resolve_gaps, or call create_tailoring_session again (it replaces it)."
        ) from exc
    # then the existing quick_tailor hint composition (instruction from the presets profile)
```

Tests first: `use_presets=True` creates with `enrich=False` unless asked and then fills; a fill failure's `ToolError` names the session id; `quick_tailor` is not registered in any set; `next_after_scores` offers `create_tailoring_session` with `use_presets`.

Commit `feat(mcp): presets are a switch on create_tailoring_session; quick_tailor is gone`.

---

### Task 11: `tailor_application` leaves MCP

**Files:** `backend/mcp_server/server.py` (delete the tool), `backend/mcp_server/client.py` (delete `tailor_application` if nothing else calls it), `backend/mcp_server/profiles.py` comments, `edit_application`'s docstring (no "tailor_application" contrast; it is the in-place edit). Tests: delete `test_tailor_application_*` in `test_client_write.py` and the docstring tests in `test_server.py` that only exist for it; replace `test_profiles.py::test_tailor_application_lives_only_in_full` with "not registered at all"; `tests/test_mcp_http_loopback.py` count 99; `frontend/components/settings/connected-agents-card.tsx` comment. The REST route `POST /api/applications/from-base` and its tests stay (the web uses it).

Commit `feat(mcp): remove tailor_application, which skipped the session's checks`.

---

### Task 12: `get_setup_status` and the instructions say who writes

**Files:** `backend/mcp_server/server.py` (`get_setup_status` adds `writer` from `_client.get_mcp_workflow_settings()`), `backend/mcp_server/orientation.py` (`_START` gains one sentence, tool-name-free: "Its writer says who writes: your agent app (then Maestro's own writing refuses, and you write the text and save it) or Maestro's AI (it writes with the user's key)."). Tests: `test_orientation_tools.py`, `test_orientation.py` (length under 4,096, names no tool outside the set: still true).

Commit `feat(mcp): setup status and every set's instructions say who writes`.

---

### Task 13: the Tailor run playbook

**Files:** `backend/app/automations/skills/tailor-run/SKILL.md`; tests `backend/tests/test_automations_service.py` (existing tailor-run pins; the playbook-tools-in-set scan).

Rewrite steps 1, 4, 6, 9, 10 per the design §4:
- Start: `get_setup_status` once; remember `writer` and `ai_key`.
- Step 4: `create_tailoring_session(job_id, base_resume, use_presets=true)`.
- Step 6: Maestro's AI writes → `tailor_session(tailoring_session_id=...)` with no `ops` (needs `ai_key`; without it stop and say so, as today). The agent app writes → `tailor_session(tailoring_session_id=..., no_new_text=true)`; never pass `ops` in this run.
- Digest: per job the `unbacked_skills` it added and, with `no_new_text`, the `answers_left_to_ops` as questions for the user.
- Record the run: `failed` only when Maestro's AI writes and there is no key.
- Keep "Never call `resolve_gaps` or `edit_application`" (drop `tailor_application`).

Tests first: pins for `use_presets=true`, `no_new_text=true`, `unbacked_skills`, the writer branch; the scan test passes (every named tool in the tailor set).

Commit `feat(automations): Tailor run follows who writes and works without an AI key`.

---

### Task 14: the Settings choice

**Files:**
- Create: `frontend/components/settings/agent-writer-section.tsx`
- Modify: `frontend/app/settings/page.tsx` (in `agents`, before `<McpWorkflowSection />`)

A `SettingCard` (id `agent-writer`, title "Who writes for connected agents") with a `RadioGroup` of two options, saved on pick like the Screening answers radio in `companion-fill-section.tsx` (copy its label/description pattern and `AutosaveStatus`):
- **Your agent app** — "It writes the tailored wording, letters, answers and notes with its own AI. Maestro's key isn't used for it."
- **Maestro's AI** — "Maestro writes them with your API key; your agent app steers."

When `writer === "maestro"` and the setup status (`queryKey: ["setup-status"]`, `GET /api/setup/status`, `model_key.done`) shows no key, a muted line under it: "Needs an API key: add one in Basics." PUT sends `{ ...setting.data.value, writer }` so `hints` is kept; share the query key `["settings", "mcp-workflow"]` with the hints card.

Verify with `npx tsc --noEmit`, `npm run lint`, and the backend scans that read frontend files (`tests/test_frontend_plain_words.py` and friends). Commit `feat(settings): choose who writes for connected agents`.

---

### Task 15: docs

- `SYSTEM.md`: a §6 invariant (`inv-one-writer-per-request` style: an agent request in agent mode never reaches `llm.call_openai`; the guard is `app/agent_writer.py`; the backstop is `call_openai`); §7 counts (99 tools, tailor 31); keep within the byte budget (run `python3 scripts/check_system_md.py`; groom if needed).
- `docs/agent-surfaces.md`: the writer setting, the refusal table, `no_new_text`, `unbacked_skills`, `use_presets`; remove `quick_tailor` and `tailor_application`.
- `docs/entities/tailoring-session.md`, `docs/entities/others.md` (MCP tool coverage), `backend/mcp_server/README.md` (counts, tool table), `plugins/maestro-career-studio/README.md` (counts), `backend/mcp_server/codex_config.example.toml` and `claude_desktop_config.example.json` (counts), `mcpb/manifest.json` description if it states counts.
- `CHANGELOG.md` Unreleased: **Breaking:** agent apps write by default (Maestro's AI no longer runs for MCP requests unless the user picks it in Settings › Agent apps); `quick_tailor` → `create_tailoring_session(use_presets=true)`; `tailor_application` removed (use a tailoring session, or `edit_application`). **Added:** "Who writes for connected agents"; tailoring without an AI key (`no_new_text`); `unbacked_skills`.

Commit `docs: who writes over MCP, the tailor without an AI key, the two removed tools`.

---

### Task 16: verification

1. Full backend suite: `cd backend && env -u ANTHROPIC_BASE_URL $PY -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile -p no:cacheprovider`. Zero failures.
2. Frontend: `npx tsc --noEmit`, `npm run lint` (2 known warnings on main only), `npm run build`, and every `node --test` command in `.github/workflows/ci.yml`.
3. `python3 scripts/check_system_md.py`; `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend|frontend|extension` (fix a regression before considering a re-baseline; a re-baseline needs a stated reason).
4. Live, on a scratch backend (`scratchpad/run_backend7.sh` pattern, a new scratch home, port 8797):
   - agent mode, no key: the Tailor run's calls over `/mcp/tailor` (setup status → score → `create_tailoring_session(use_presets=true)` → `tailor_session(no_new_text=true)` → `propose_application` link) end with a rendered, linked resume; `unbacked_skills` and `answers_left_to_ops` read right; `generate_cover_letter` refuses naming `store_cover_letter`.
   - agent mode with a stub key (a custom endpoint pointing at an unreachable local URL is enough): the health check returns a judging brief, `kb_ingest_resume` imports, no request reaches the stub.
   - Maestro mode: `generate_cover_letter` reaches the model path (it fails on the stub, which proves the route ran).
5. Code review by a fresh reviewer (Opus) over `git diff main...HEAD`; fix findings with tests; rerun the suite.
6. Report to the owner; merging into main only on their word.
