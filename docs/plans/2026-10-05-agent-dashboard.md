# Agent Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in this session) to implement this plan task by task.

**Goal:** The Agent inbox (`/proposals`) shows what the user's own agent runs did and what is
ready to send, without opening each job: readiness marks on each row, a run log ("Recent
runs" plus a "Last ran" line on each Automations card), and an arrivals strip.

**Owner's goal (2026-10-05), phase 3 of the automation roadmap:** "Our agentic application can
be a dashboard area where the new jobs come in." End state across all four phases: "our
application should support a fully automated job application if that's user's wish, with
appropriate settings to enable or disable." **Scope rule from the owner: this phase touches
only the dashboard, not tailoring or any other workflow.** Phase 4 (auto-submit) will read the
readiness rule (`inbox_readiness.is_ready`) and the run log, so both must be exactly right.

**Design:** `docs/plans/2026-10-05-agent-dashboard-design.md` (approved, approach 1). It is the
source of truth for scope.

**Architecture:**
- Readiness is computed when `GET /api/proposals` is read, for open-lane rows only, by one new
  service `services/inbox_readiness.py`. Nothing is stored. The profile is read once per batch.
- One new table, `agent_runs`, written only by `POST /api/agent-runs` (MCP `record_run`), read by
  `GET /api/agent-runs` and `GET /api/agent-runs/latest`. Newest 200 kept.
- One new read, `GET /api/proposals/summary?since=`, feeds the arrivals strip.
- Frontend: a client wrapper `components/proposals/inbox-dashboard.tsx` holds the last-visit
  time and renders the strip, the Recent runs panel and the existing `ProposalsSection`.
  Pure helpers in `lib/inbox-readiness.ts` and `lib/agent-runs.ts`.

**Tech stack:** FastAPI + Pydantic v2 + SQLAlchemy 2 (SQLite) + alembic; FastMCP + httpx (respx
in tests); Next.js 16 + React 19 + react-query; frontend pinned by
`backend/tests/test_frontend_*.py` source tests and `node --test` for pure `lib/*.test.ts`.

**How much freedom the executor has:**

| Area | Freedom | Rule |
|---|---|---|
| Table/column names, endpoint paths, MCP tool name `record_run` and its params, count keys (`found` `proposed` `skipped` `tailored` `updated` `needs_you`), outcomes (`ok` `partial` `failed`), the readiness rule, every pinned UI string below | **Fixed** | Tests, the design and phase 4 depend on them. |
| Layout inside the design system (`docs/design-system/`, `docs/frontend-conventions.md`), helper decomposition, private names, comment wording | **Moderate** | Each new function under cc 10, ≤ 50 lines, ≤ 5 params (the slop ratchet counts `self` and `ctx`). Prefer parametrized tests. |
| Anything that touches tailoring, filling, knock-out verdicts, submit rules or the proposal state machine; anything contradicting the design, a SYSTEM.md §6 invariant, or a test you did not write (beyond the pin updates named here) | **Stop and report** | Say what and why; propose the change. Never loosen a test to get green. |

**Environment:** a git worktree. Read `SYSTEM.md` first (CLAUDE.md requires it).
- **Python:** `/opt/anaconda3/bin/python3` (editable install; run from the worktree's
  `backend/` so cwd wins on `sys.path`).
- **Backend suite (always xdist):** from `backend/`:
  `/opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
- **Single test:** from `backend/`: `/opt/anaconda3/bin/python3 -m pytest tests/<file>::<test> -q`
- **Frontend:** `npm ci` once in `frontend/` (a worktree has no `node_modules`). Gates:
  `npx tsc --noEmit`, `npm run lint`, `npm run build`. Pure lib tests:
  `node --test lib/<name>.test.ts` from `frontend/` (node 26 strips types; a lib loaded this
  way imports nothing but `import type`).
- **SYSTEM.md gate:** from the repo root: `/opt/anaconda3/bin/python3 scripts/check_system_md.py`.
  SYSTEM.md is at **995/1000** lines; Task 12 grooms before it adds.
- **Slop ratchet:** from the repo root:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend` (and
  `frontend`). Name every surface you ran in your report.

**Code facts this plan rests on (verified at b7e0999e):**
- Alembic head is `2ae2fc560139` (`migrations/versions/2ae2fc560139_filled_answers.py`).
  Revisions use impl types only (`sa.Uuid`, `sa.JSON`, `sa.DateTime`, `sa.Text`) and
  `batch_alter_table` for indexes. `tests/test_migration_model_parity.py` compares model to
  migrated schema, server defaults included. Column types come only from `app/models/types.py`
  (`JSONDoc`, `UUIDType`, `UTCDateTime`, `utcnow`). Models are exported from
  `app/models/__init__.py` (import + `__all__`).
- `knockout.scan_job(job, work_auth, preferences, years_experience=None, personal=None)`
  (`services/knockout.py:366`) returns `{"status": "conflict"|"incomplete_profile"|"clear"|
  "unstated", "checks": [{"kind", "result", ...}]}`; kinds are `work_authorization`, `opt`,
  `salary`, `experience`, `on_site`. `scan_for(session, job)` (`:399`) reads the profile per call
  with a function-local import of `autofill_profile` and `job_preferences`.
- `services/filled_answers.py`: `flag_context(session, job)` (`:99`), `_rows(session, job_id)`
  (`:157`), `latest_fields(rows)` → `[(row, field)]` (`:176`), `receipt()` (`:229`) whose
  `flag_count` counts fields with any flag; `answer_flags.flags_for(field, facts, saved_eeo)`.
- `services/proposals.py`: `OPEN_STATUSES` (`:64`) = pending_review, needs_decision, accepted,
  approved, needs_human. `routers/applications.py:~392` closes open proposals with the literal
  reason `"applied manually"` when the user marks an application applied or later.
- `routers/proposals.py`: `_read_fields(prop, job)` is shared by list and detail; `list_proposals`
  (`:199`) builds `ProposalRead(**_read_fields(prop, job))` from `(prop, job)` rows; `/funnel`
  is at `:240`, before `@router.get("/{proposal_id}")` at `:276` (new static GETs must sit
  before it). `ProposalRead` is in `schemas/proposal.py:77`.
- Writer identity: `app/write_origin.py` `get_write_origin` → `WriteOrigin(origin, detail)`;
  `origin == "mcp"` only when the MCP client sent `X-Maestro-CS-Origin`. MCP side:
  `_origin_headers(origin_detail)` in `mcp_server/client.py:64`, `_client_label(ctx)` in
  `mcp_server/server.py:184`. `proposed_by` stores the raw client name; the frontend words it
  with `lib/agent-name.ts` (`agentDisplayName`).
- MCP: tools are `@mcp.tool(**_read(...)|**_write(...))` + `@_guard`; the registration subset
  is `mcp_server/tests/test_server.py:~21-77`; `assert len(tools) >= 83` (`:1148`); tool text
  must not instruct (`_BANNED_VOICE`, `:1222`); profiles in `mcp_server/profiles.py`
  (`HUNT_TOOLS`, `APPLY_TOOLS`). Client tests use `respx` against `BackendClient("http://test-backend")`.
- Automations: `services/automations.catalog()` → `.cards` with `.id`, `.title`, `.kind`,
  `.body`; guardrail sentences are pinned in `tests/test_automations_service.py:55-71`.
- Frontend: `PROPOSALS_KEY = ["proposals"]` (`components/proposals/proposals-section.tsx:82`
  and `triage-actions.tsx:28`), so any key starting with `"proposals"` refetches after triage.
  `lib/inbox-lanes.ts` is the lane table; `STATUS_LABELS` (`proposals-section.tsx:98`).
  `formatTimeAgo` in `lib/format-date.ts`. The vocabulary ratchet
  (`tests/test_frontend_vocabulary.py`) bans a capitalized **Submitted** (say Applied),
  "triage", "session", "evidence", "entry", "posting", an em-dash joiner and `e.g.`.
  A `LoadErrorState` caller must be pinned in `tests/test_frontend_query_error_states.py`;
  this plan uses none (the new panels fail quietly with a muted line).

**How this plan was checked:** Tasks 1–11 were applied to a scratch worktree at 25bceb86 and
run (Fable 5.1): the full backend suite (9,063 passed, 1 skipped, xdist), the MCP suite (85
tools), the node lib tests, `tsc --noEmit`, `npm run lint`, and the slop ratchet on backend and
frontend (both OK). Its seven corrections are folded in below (the models-metadata pin, two
verbatim prompt pins, lane attribute order, the corner token, `GuardedLink`, and the apostrophe
pin). `npm run build`, Task 12 and the live check were not run.

**Design ambiguities resolved in this plan (do not re-decide them):**
1. `agent_runs` has no `started_at` and no `created_at`: the panel shows when a run finished,
   `finished_at` is set when the record is written, and the MCP tool stays at 4 params (the
   ratchet's ≤ 5). Everything a run reports beyond its name and outcome travels in one
   `report` object: `{counts?, digest?, job_ids?}`.
2. Over-long input is trimmed, not refused, so a run is never lost: `digest` keeps its first
   2,000 characters (ending in "…"), `job_ids` its first 50; unknown job ids are dropped.
   Unknown count keys and negative counts ARE refused (422): they are a caller bug.
3. The run's `title` is resolved at read time: the card title for a known card id, else the
   automation name as given.
4. "Applied this week" counts proposals now `submitted`, or `rejected` with reason
   `"applied manually"`, whose `updated_at` falls in the last 7 days (proposals have no
   submitted-at column; `updated_at` is when they reached that terminal state). The reason
   string becomes a constant, `proposals.APPLIED_MANUALLY`, used by the applications router.
5. Readiness `tailored` is `null` when no application is linked OR the linked one is gone.
6. The strip's "new" window: the browser's stored last visit, else the last 24 hours. The page
   reads the old value once on mount and then stores now; a ref keeps React's dev double-effect
   from reading its own write.
7. The vocabulary ratchet wins over the design's literal tile name: "Applied this week", not
   "Submitted this week".
8. `record_run` is in the `hunt` and `apply` MCP profiles (and `full`).

---

### Task 1: The `agent_runs` table

**Files:**
- Create: `backend/app/models/agent_run.py`
- Create: `backend/migrations/versions/7d3c1a9e5b20_agent_runs.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/test_models_metadata.py` (`test_all_planned_tables_are_registered` pins every table)
- Test: `backend/tests/test_agent_runs_model.py`

**Step 1: Write the failing test**

```python
"""The run log's table (docs/plans/2026-10-05-agent-dashboard-design.md, Part 2)."""

from app.models.agent_run import AgentRun


def test_a_run_round_trips_with_its_defaults(db_session):
    run = AgentRun(automation="job-hunt", outcome="ok")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    assert run.finished_at is not None
    assert (run.counts, run.digest, run.job_ids, run.agent) == ({}, "", [], None)
```

**Step 2: Run it to verify it fails**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_model.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.agent_run'`

**Step 3: Write the model, the migration and the export**

`backend/app/models/agent_run.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import JSONDoc, UTCDateTime, UUIDType, utcnow


class AgentRun(Base):
    """One automation run an agent reported (MCP `record_run`): what it was, how it ended, its
    counts, its digest and the jobs it touched. Read by the Agent inbox's Recent runs panel and
    the Automations page's Last ran line. Only the newest `services/agent_runs.MAX_RUNS` rows
    are kept. The digest is the agent's own text: Maestro cannot check what it holds
    (docs/entities/agent-runs.md)."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_finished_at", "finished_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    automation: Mapped[str] = mapped_column(Text, nullable=False)  # card id or a custom name
    outcome: Mapped[str] = mapped_column(Text, nullable=False)  # "ok" | "partial" | "failed"
    agent: Mapped[str | None] = mapped_column(Text)  # the MCP client's name, raw
    finished_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    counts: Mapped[dict] = mapped_column(JSONDoc, nullable=False, default=dict)
    digest: Mapped[str] = mapped_column(Text, nullable=False, default="")
    job_ids: Mapped[list] = mapped_column(JSONDoc, nullable=False, default=list)
```

`backend/migrations/versions/7d3c1a9e5b20_agent_runs.py`:

```python
"""The run log: one row per automation run an agent reported (MCP `record_run`).

Impl types only (sa.Uuid / sa.JSON / sa.DateTime), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12).
"""
from alembic import op
import sqlalchemy as sa

revision = "7d3c1a9e5b20"
down_revision = "2ae2fc560139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("automation", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"),
                  nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("job_ids", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index("ix_agent_runs_finished_at", ["finished_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_runs_finished_at")
    op.drop_table("agent_runs")
```

`backend/app/models/__init__.py`: add `from app.models.agent_run import AgentRun` in import
order and `"AgentRun",` to `__all__`.

`backend/tests/test_models_metadata.py`: add `"agent_runs",` to the table set in
`test_all_planned_tables_are_registered` (otherwise: `Extra items in the left set: 'agent_runs'`).

**Step 4: Run the test and the parity check**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_model.py tests/test_migration_model_parity.py -q`
Expected: PASS. If parity reports a server-default mismatch on `finished_at`, copy the exact
`server_default` spelling from `2ae2fc560139_filled_answers.py` (it passes today).

**Step 5: Commit**

```bash
git add backend/app/models/agent_run.py backend/app/models/__init__.py \
  backend/migrations/versions/7d3c1a9e5b20_agent_runs.py backend/tests/test_agent_runs_model.py
git commit -m "feat(runs): the agent_runs table"
```

---

### Task 2: Run-log shapes and the service

**Files:**
- Create: `backend/app/schemas/agent_runs.py`
- Create: `backend/app/services/agent_runs.py`
- Test: `backend/tests/test_agent_runs_service.py`

**Step 1: Write the failing tests**

```python
"""The run log's service: trim, drop, prune, latest per automation."""

import uuid

import pytest
from pydantic import ValidationError

from app.models.agent_run import AgentRun
from app.schemas.agent_runs import AgentRunCreate
from app.services import agent_runs
from tests.test_proposals_models import _mk_job


def _run(db_session, automation="job-hunt", **report):
    return agent_runs.record(db_session, AgentRunCreate(automation=automation, outcome="ok",
                                                        **report), agent="claude-ai")


def test_a_long_digest_and_job_list_are_trimmed_not_refused(db_session):
    jobs = [_mk_job(db_session) for _ in range(3)]
    run = _run(db_session, digest="x" * 2500,
               job_ids=[j.id for j in jobs] + [uuid.uuid4() for _ in range(60)])
    assert len(run.digest) == agent_runs.MAX_DIGEST and run.digest.endswith("…")
    assert run.job_ids == [str(j.id) for j in jobs]  # first 50 kept, unknown ids dropped


@pytest.mark.parametrize("counts", [{"found": -1}, {"applied": 3}], ids=["negative", "unknown-key"])
def test_bad_counts_are_refused(counts):
    with pytest.raises(ValidationError):
        AgentRunCreate(automation="job-hunt", outcome="ok", counts=counts)


@pytest.mark.parametrize("automation", ["", "   ", "x" * 41], ids=["empty", "blank", "too-long"])
def test_the_automation_has_a_name_of_at_most_40_characters(automation):
    with pytest.raises(ValidationError):
        AgentRunCreate(automation=automation, outcome="ok")


def test_only_the_newest_runs_are_kept(db_session, monkeypatch):
    monkeypatch.setattr(agent_runs, "MAX_RUNS", 3)
    for n in range(5):
        _run(db_session, digest=str(n))
    kept = db_session.query(AgentRun).order_by(AgentRun.finished_at).all()
    assert [r.digest for r in kept] == ["2", "3", "4"]


def test_latest_is_one_run_per_automation_with_titles_and_jobs(db_session):
    job = _mk_job(db_session, title="Data Scientist", company="Acme")
    _run(db_session, digest="old")
    _run(db_session, digest="new", job_ids=[job.id])
    _run(db_session, automation="weekly-pipeline")
    latest = {r["automation"]: r for r in agent_runs.latest(db_session)}
    assert latest["job-hunt"]["digest"] == "new"
    assert latest["job-hunt"]["title"] == "Job hunt"
    assert latest["job-hunt"]["jobs"] == [{"id": job.id, "title": "Data Scientist",
                                           "company": "Acme"}]
    assert latest["weekly-pipeline"]["title"] == "weekly-pipeline"
```

Note: `_mk_job` passes `**kw` to `Job(...)`; if `Job` has no `title`/`company` columns by those
names, read `app/models/job.py` and use its names (do not change the model).

**Step 2: Run them to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.agent_runs'`

**Step 3: Write the schemas and the service**

`backend/app/schemas/agent_runs.py`:

```python
"""The run log's wire shapes (MCP `record_run`, the Agent inbox's Recent runs panel).

Count keys and outcomes are a frozen vocabulary: the panel words them and phase 4 reads them.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunOutcome = Literal["ok", "partial", "failed"]
RunCountKey = Literal["found", "proposed", "skipped", "tailored", "updated", "needs_you"]
MAX_DIGEST = 2000
MAX_JOB_IDS = 50


class AgentRunCreate(BaseModel):
    """One finished run. A long digest or job list is trimmed, never refused."""

    model_config = ConfigDict(extra="forbid")

    automation: str = Field(min_length=1, max_length=40)
    outcome: RunOutcome
    counts: dict[RunCountKey, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    digest: str = ""
    job_ids: list[UUID] = Field(default_factory=list)

    @field_validator("automation")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an automation has a name")
        return value.strip()

    @field_validator("digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        value = value.strip()
        return value if len(value) <= MAX_DIGEST else value[: MAX_DIGEST - 1] + "…"

    @field_validator("job_ids")
    @classmethod
    def _jobs(cls, value: list[UUID]) -> list[UUID]:
        return value[:MAX_JOB_IDS]


class AgentRunJob(BaseModel):
    id: UUID
    title: str | None = None
    company: str | None = None


class AgentRunRead(BaseModel):
    id: UUID
    automation: str
    title: str
    outcome: RunOutcome
    agent: str | None = None
    finished_at: datetime
    counts: dict[str, int]
    digest: str
    jobs: list[AgentRunJob]


class AgentRunList(BaseModel):
    items: list[AgentRunRead]
```

> The `_jobs` trim runs after UUID parsing. Unknown ids are dropped by the service, so the
> trim is "the first 50 given", then "of those, the ones Maestro knows". The test above sends 3
> known ids first, then 60 unknown: the first 50 are 3 known + 47 unknown, so 3 survive.

`backend/app/services/agent_runs.py`:

```python
"""The run log: what each automation run reported (MCP `record_run`), for the Agent inbox's
Recent runs panel and the Automations page's Last ran line.

Maestro runs no scheduler and cannot tell a late run from a skipped one, so nothing here says
"overdue". The digest is the agent's own text: Maestro cannot check it holds no email text
(docs/entities/agent-runs.md).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.job import Job
from app.models.types import utcnow
from app.schemas.agent_runs import MAX_DIGEST, AgentRunCreate
from app.services import automations

MAX_RUNS = 200
__all__ = ["MAX_DIGEST", "MAX_RUNS", "latest", "recent", "record"]


def _known(session: Session, ids: list[UUID]) -> set[UUID]:
    if not ids:
        return set()
    return set(session.scalars(select(Job.id).where(Job.id.in_(ids))))


def _prune(session: Session) -> None:
    keep = (select(AgentRun.id)
            .order_by(AgentRun.finished_at.desc(), AgentRun.id.desc()).limit(MAX_RUNS))
    session.execute(delete(AgentRun).where(AgentRun.id.not_in(keep)))


def record(session: Session, payload: AgentRunCreate, agent: str | None) -> AgentRun:
    known = _known(session, payload.job_ids)
    run = AgentRun(automation=payload.automation, outcome=payload.outcome, agent=agent,
                   finished_at=utcnow(), counts=dict(payload.counts), digest=payload.digest,
                   job_ids=[str(i) for i in payload.job_ids if i in known])
    session.add(run)
    session.flush()
    _prune(session)
    session.commit()
    session.refresh(run)
    return run


def _newest(session: Session, limit: int) -> list[AgentRun]:
    return list(session.scalars(
        select(AgentRun).order_by(AgentRun.finished_at.desc(), AgentRun.id.desc()).limit(limit)))


def _read(runs: list[AgentRun], session: Session) -> list[dict[str, Any]]:
    titles = {card.id: card.title for card in automations.catalog().cards}
    ids = {UUID(i) for run in runs for i in run.job_ids}
    jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(ids)))} if ids else {}
    return [{"id": run.id, "automation": run.automation,
             "title": titles.get(run.automation, run.automation), "outcome": run.outcome,
             "agent": run.agent, "finished_at": run.finished_at, "counts": run.counts,
             "digest": run.digest,
             "jobs": [{"id": job.id, "title": job.title, "company": job.company}
                      for job in (jobs.get(UUID(i)) for i in run.job_ids) if job is not None]}
            for run in runs]


def recent(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    return _read(_newest(session, limit), session)


def latest(session: Session) -> list[dict[str, Any]]:
    """The newest run of each automation, newest first (the table holds at most MAX_RUNS)."""
    seen: dict[str, AgentRun] = {}
    for run in _newest(session, MAX_RUNS):
        seen.setdefault(run.automation, run)
    return _read(list(seen.values()), session)


def read_one(session: Session, run: AgentRun) -> dict[str, Any]:
    return _read([run], session)[0]
```

Add `"read_one"` to `__all__`. `_prune` reads `MAX_RUNS` at call time, so the test's
`monkeypatch.setattr(agent_runs, "MAX_RUNS", 3)` takes effect.

**Step 4: Run the tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_service.py -q`
Expected: PASS (8 tests). If `_read` is over cc 10 or 50 lines, split the job lookup into a
`_jobs_by_id(session, runs)` helper.

**Step 5: Commit**

```bash
git add backend/app/schemas/agent_runs.py backend/app/services/agent_runs.py \
  backend/tests/test_agent_runs_service.py
git commit -m "feat(runs): record, trim, prune and read the run log"
```

---

### Task 3: `/api/agent-runs`

**Files:**
- Create: `backend/app/routers/agent_runs.py`
- Modify: `backend/app/main.py` (import list `:15-35`, `include_router` block `:200-211`)
- Test: `backend/tests/test_agent_runs_router.py`

**Step 1: Write the failing tests**

```python
"""The run log over HTTP."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}


def _post(json, headers=MCP):
    return client.post("/api/agent-runs", json=json, headers=headers)


def test_an_agent_records_a_run_and_its_name_is_kept():
    body = _post({"automation": "mail-status", "outcome": "partial",
                  "counts": {"updated": 2}, "digest": "Acme: interview"}).json()
    assert (body["agent"], body["title"], body["counts"]) == ("claude-ai", "Mail status",
                                                              {"updated": 2})


def test_a_run_without_mcp_headers_has_no_agent_name():
    assert _post({"automation": "job-hunt", "outcome": "ok"}, headers={}).json()["agent"] is None


def test_unknown_count_keys_are_refused():
    assert _post({"automation": "job-hunt", "outcome": "ok", "counts": {"x": 1}}).status_code == 422


def test_latest_and_recent_read_back():
    _post({"automation": "tailor-run", "outcome": "failed", "digest": "no AI key"})
    latest = client.get("/api/agent-runs/latest").json()["items"]
    assert any(r["automation"] == "tailor-run" and r["outcome"] == "failed" for r in latest)
    recent = client.get("/api/agent-runs", params={"limit": 1}).json()["items"]
    assert len(recent) == 1
```

**Step 2: Run them to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_router.py -q`
Expected: FAIL with 404s.

**Step 3: Write the router and register it**

```python
"""The run log over HTTP (`services/agent_runs.py`). Written by MCP `record_run`; read by the
Agent inbox's Recent runs panel and the Automations page's Last ran line. No edit, no delete."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.agent_runs import AgentRunCreate, AgentRunList, AgentRunRead
from app.services import agent_runs
from app.write_origin import WriteOrigin, get_write_origin

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


@router.post("", response_model=AgentRunRead, status_code=201)
def post_agent_run(
    payload: AgentRunCreate,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    agent = write_origin.detail if write_origin.origin == "mcp" else None
    return agent_runs.read_one(db, agent_runs.record(db, payload, agent))


@router.get("/latest", response_model=AgentRunList)
def get_latest_runs(db: Annotated[Session, Depends(get_db)]):
    return {"items": agent_runs.latest(db)}


@router.get("", response_model=AgentRunList)
def list_agent_runs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
):
    return {"items": agent_runs.recent(db, limit)}
```

In `app/main.py` add `agent_runs,` to the `from app.routers import (...)` list (it is not alphabetical: put it after `role_categories,`) and
`app.include_router(agent_runs.router)` after `app.include_router(filled_answers.router)`.

**Step 4: Run the tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_agent_runs_router.py -q`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add backend/app/routers/agent_runs.py backend/app/main.py backend/tests/test_agent_runs_router.py
git commit -m "feat(runs): /api/agent-runs (record, latest, recent)"
```

---

### Task 4: MCP `record_run`

**Files:**
- Modify: `backend/mcp_server/client.py` (next to `record_filled_answers`, `:~1326`)
- Modify: `backend/mcp_server/server.py` (TypedDicts near `FilledFieldInput` `:87`; tool after
  `record_filled_answers` `:~1823`)
- Modify: `backend/mcp_server/profiles.py` (`HUNT_TOOLS`, `APPLY_TOOLS`)
- Modify: `backend/mcp_server/tests/test_server.py` (registration set `:~75`; `>= 83` → `>= 85`)
- Create: `backend/mcp_server/tests/test_client_agent_runs.py`

**Step 1: Write the failing tests**

`backend/mcp_server/tests/test_client_agent_runs.py`:

```python
"""record_run's request shape: the report is flattened, the client name rides the headers."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_record_run_posts_the_report_and_names_the_client():
    route = respx.post(f"{BASE}/api/agent-runs").mock(
        return_value=httpx.Response(201, json={"id": "r1"}))
    BackendClient(BASE).record_run("job-hunt", "ok", {"counts": {"found": 3}, "digest": "d"},
                                   origin_detail="claude-ai")
    request = route.calls.last.request
    assert json.loads(request.read()) == {"automation": "job-hunt", "outcome": "ok",
                                          "counts": {"found": 3}, "digest": "d"}
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "claude-ai"
```

In `test_server.py`: add `"record_run",` to the expected registration set after
`"record_filled_answers",`, change `assert len(tools) >= 83` to `>= 85`, and add:

```python
def test_record_run_forwards_to_client(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client, "record_run",
        lambda automation, outcome, report, origin_detail=None: seen.update(
            automation=automation, outcome=outcome, report=report) or {"id": "r1"},
    )
    assert srv.record_run("mail-status", "ok", {"counts": {"updated": 1}}) == {"id": "r1"}
    assert seen == {"automation": "mail-status", "outcome": "ok",
                    "report": {"counts": {"updated": 1}}}
```

**Step 2: Run them to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest mcp_server/tests/test_client_agent_runs.py mcp_server/tests/test_server.py -q`
Expected: FAIL (`AttributeError: ... 'record_run'`, and the registration subset).

**Step 3: Write the client method, the tool and the profiles**

`client.py`, after `record_filled_answers`:

```python
    def record_run(
        self, automation: str, outcome: str, report: dict[str, Any] | None,
        origin_detail: str | None = None,
    ) -> Any:
        """`report` is the run's optional counts, digest and job_ids, sent flat."""
        body = {"automation": automation, "outcome": outcome, **_drop_none(**(report or {}))}
        return self._request("POST", "/api/agent-runs", json=body,
                             headers=_origin_headers(origin_detail))
```

`server.py`, next to `FilledFieldInput`:

```python
class RunCounts(TypedDict, total=False):
    """What a run did, as whole numbers."""

    found: int
    proposed: int
    skipped: int
    tailored: int
    updated: int
    needs_you: int


class RunReport(TypedDict, total=False):
    """What record_run stores beyond the automation and its outcome."""

    counts: RunCounts
    digest: str
    job_ids: list[str]


_RUN_REPORT_FIELD = Field(
    description=(
        "{counts?, digest?, job_ids?}. counts: whole numbers for found, proposed, skipped, "
        "tailored, updated and needs_you; other keys are refused. digest: the run's plain-text "
        "summary, kept to its first 2000 characters; it holds counts and title-and-company lines, "
        "not email text. job_ids: the jobs the run touched, the first 50 kept; ids Maestro does "
        "not know are dropped."
    )
)
RunReportArg = Annotated[RunReport | None, _RUN_REPORT_FIELD]
```

Tool, after `record_filled_answers`:

```python
@mcp.tool(**_write("Record Automation Run", destructive=False, idempotent=False))
@_guard
def record_run(
    automation: str,
    outcome: Literal["ok", "partial", "failed"],
    report: RunReportArg = None,
    ctx: Context | None = None,
) -> Any:
    """Record one finished automation run. The Agent inbox lists the newest run of each
    automation under Recent runs (its counts, digest and job links), and each Automations card
    shows when its automation last ran. automation is the card id (mail-status, job-hunt,
    referral-pages, tailor-run, apply-session) or a custom automation's own name, 40 characters
    at most. outcome: ok, partial (some of the work failed) or failed (none of it was done).
    The newest 200 runs are kept. Returns the stored run."""
    return _client.record_run(automation, outcome, report, origin_detail=_client_label(ctx))
```

`profiles.py`: add `"record_run",` to `HUNT_TOOLS` (after `"get_proposal",`) and to
`APPLY_TOOLS` (after `"record_filled_answers",`).

**Step 4: Run the MCP tests**

Run: `/opt/anaconda3/bin/python3 -m pytest mcp_server/tests/ -q -n auto --dist loadfile`
Expected: PASS, including the banned-voice, truncation-budget and profile tests. If the
docstring trips `_BANNED_VOICE`, reword it as a fact, never loosen the test.

**Step 5: Commit**

```bash
git add backend/mcp_server/ 
git commit -m "feat(mcp): record_run, the agent's own run record"
```

---

### Task 5: Every automation prompt records its run; job-hunt marks its jobs as an agent's

**Files:**
- Modify: `backend/app/automations/skills/{mail-status,job-hunt,referral-pages,tailor-run,apply-session}/SKILL.md`
- Modify: `backend/app/automations/skills/customize-job-skills/SKILL.md` (§4 "Build it")
- Modify: `backend/tests/test_automations_service.py` (the guardrail parametrize `:55-71`)

**Step 1: Write the failing tests** — add these params to `test_guardrails_survive_rewording`:

```python
    *[pytest.param(card, f"Call `record_run` with automation `{card}`", id=f"{card}-records")
      for card in ("mail-status", "job-hunt", "referral-pages", "tailor-run", "apply-session")],
    pytest.param("mail-status", "never email text", id="mail-digest-no-email-text"),
    pytest.param("job-hunt", '`store_extracted_jd` with `source="agent"`', id="hunt-marks-agent"),
    pytest.param("customize-job-skills", "call `record_run` with the automation's own name",
                 id="custom-records"),
```

**Step 2: Run to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_service.py -q`
Expected: 8 new FAILs.

**Step 3: Edit the prompts**

Append one numbered step after each prompt's last (Digest) step, numbered next in sequence:

- **mail-status** (after step 7):
  ```
  8. **Record the run.** Call `record_run` with automation `mail-status`, the outcome (`ok`;
     `partial` if some mail could not be read; `failed` if none could), counts (`updated`:
     applications moved, `skipped`: emails left unmatched), the digest and the ids of the
     jobs whose applications moved. The digest holds counts and company-and-role lines only,
     never email text: no subjects, senders or bodies.
  ```
- **job-hunt** — step 4 becomes (keep `` `store_extracted_jd` with `source="agent"` `` on ONE
  line; the pin is verbatim):
  ```
  4. **Capture and score** each survivor: `store_extracted_jd` with `source="agent"`
     and the posting's `source_url`, then `score_ats`. Extract only what the posting states.
  ```
  and add after step 6:
  ```
  7. **Record the run.** Call `record_run` with automation `job-hunt`, the outcome (`ok`;
     `partial` if a source failed; `failed` if none could be read), counts (`found`,
     `proposed`, `skipped`), the digest and the ids of the jobs you proposed.
  ```
- **referral-pages** (after step 7): same shape, automation `referral-pages`, counts `found`,
  `proposed`, `skipped`; `partial` if a careers page failed.
- **tailor-run** (after step 9): automation `tailor-run`, counts `tailored`, `needs_you`
  (jobs left for the user's answers), `skipped`; `failed` when the app has no AI key; job ids of
  the jobs tailored or left for the user.
- **apply-session** (after step 6): automation `apply-session`, counts `updated`
  (applications submitted), `needs_you` and `skipped` (declined); job ids of the jobs worked.
- **customize-job-skills**, §4 "Build it", a new bullet before "Finish by telling…":
  ```
  - End every automation with one step: call `record_run` with the automation's own name
    (40 characters at most), its outcome, counts and digest, so its runs show in Maestro's
    Agent inbox.
  ```

Keep each line ≤ 90 characters like the surrounding text. Wording may differ, but every pinned
sentence must appear verbatim.

**Step 4: Run the tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_service.py tests/test_automations_router.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/automations/skills backend/tests/test_automations_service.py
git commit -m "feat(automations): every run records itself; job-hunt saves its jobs as an agent's"
```

---

### Task 6: Readiness, computed in one batch

**Files:**
- Modify: `backend/app/services/knockout.py` (`scan_for`, `:399-410`)
- Modify: `backend/app/services/filled_answers.py` (`flag_context` `:99`; new `flag_count`)
- Create: `backend/app/services/inbox_readiness.py`
- Test: `backend/tests/test_inbox_readiness.py`

**Step 1: Write the failing tests**

```python
"""Readiness on the Agent inbox's rows (docs/plans/2026-10-05-agent-dashboard-design.md, Part 1)."""

import pytest

from app.config import settings
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.filled_answer import FilledAnswer
from app.services import filled_answers, inbox_readiness, knockout
from tests.test_proposals_models import _mk_job

TICKED_ALL = {"question": "Which languages?", "answer": ["a", "b", "c"], "options_count": 3,
              "source": "inferred"}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _proposal(db_session, status="accepted", pdf=None, **job):
    job_row = _mk_job(db_session, **job)
    app_id = None
    if pdf is not None:
        app_row = Application(job_id=job_row.id, base_resume="swe", pdf_path=pdf)
        db_session.add(app_row)
        db_session.flush()
        app_id = app_row.id
    prop = ApplicationProposal(job_id=job_row.id, status=status, application_id=app_id)
    db_session.add(prop)
    db_session.commit()
    return prop, job_row


def test_tailored_follows_the_linked_application_pdf(db_session):
    rows = [_proposal(db_session, pdf="/x.pdf"), _proposal(db_session, pdf=""),
            _proposal(db_session)]
    got = inbox_readiness.for_proposals(db_session, rows)
    assert [got[p.id]["tailored"] for p, _ in rows] == [True, False, None]


def test_history_rows_get_no_readiness(db_session):
    rows = [_proposal(db_session, status=s) for s in ("submitted", "rejected", "expired")]
    assert inbox_readiness.for_proposals(db_session, rows) == {}


def test_to_check_counts_the_flagged_answers(db_session):
    prop, job = _proposal(db_session, status="approved")
    db_session.add(FilledAnswer(job_id=job.id, channel="agent", fields=[TICKED_ALL]))
    db_session.commit()
    got = inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]
    assert got["to_check"] == 1 == filled_answers.receipt(db_session, job)["flag_count"]


def test_a_conflicting_knockout_names_its_kind(db_session, monkeypatch):
    monkeypatch.setattr(knockout, "scan_job", lambda job, **_: {
        "status": "conflict", "checks": [{"kind": "salary", "result": "pass"},
                                         {"kind": "on_site", "result": "conflict"}]})
    prop, job = _proposal(db_session)
    assert inbox_readiness.for_proposals(db_session, [(prop, job)])[prop.id]["knockout"] == "on_site"


def test_the_profile_is_read_once_per_batch(db_session, monkeypatch):
    calls = []
    real = knockout.scan_args
    monkeypatch.setattr(knockout, "scan_args", lambda s: calls.append(1) or real(s))
    rows = [_proposal(db_session) for _ in range(3)]
    inbox_readiness.for_proposals(db_session, rows)
    assert calls == [1]


def test_a_row_that_fails_gets_null_and_the_rest_still_read(db_session, monkeypatch):
    rows = [_proposal(db_session), _proposal(db_session)]
    bad_job = rows[0][1]
    real = knockout.scan_job
    monkeypatch.setattr(knockout, "scan_job", lambda job, **kw: (
        (_ for _ in ()).throw(RuntimeError("boom")) if job.id == bad_job.id else real(job, **kw)))
    got = inbox_readiness.for_proposals(db_session, rows)
    assert got[rows[0][0].id] is None and got[rows[1][0].id] is not None


@pytest.mark.parametrize("readiness, ready", [
    ({"tailored": True, "knockout": None, "to_check": 0}, True),
    ({"tailored": False, "knockout": None, "to_check": 0}, False),
    ({"tailored": None, "knockout": None, "to_check": 0}, False),
    ({"tailored": True, "knockout": "opt", "to_check": 0}, False),
    ({"tailored": True, "knockout": None, "to_check": 2}, False),
    (None, False),
])
def test_ready_means_tailored_no_knockout_nothing_to_check(readiness, ready):
    assert inbox_readiness.is_ready(readiness) is ready
```

If `ApplicationProposal(...)` needs more required columns, copy the minimal constructor from
`tests/test_proposals_models.py::test_proposal_row_roundtrip_with_consent`. If the rule for a
"flagged" multi-select needs more than `options_count: 3` + three ticks, read
`answer_flags.py` and pick a field it flags (the assertion compares against `receipt()`, so the
two must agree whatever the field is).

**Step 2: Run them to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_inbox_readiness.py -q`
Expected: FAIL with `ImportError: cannot import name 'inbox_readiness'`

**Step 3: Write the code**

`knockout.py` — split the profile read out of `scan_for`, behavior unchanged:

```python
def scan_args(session: Session) -> dict[str, Any]:
    """The stored profile as `scan_job`'s keyword arguments, read once: a batch reuses it."""
    from app.services import autofill_profile, job_preferences

    profile = autofill_profile.get_profile(session)
    return {
        "work_auth": autofill_profile.work_auth_from_profile(profile),
        "preferences": profile.get("preferences"),
        "years_experience": job_preferences.get_preferences(session).years_experience,
        "personal": profile.get("personal"),
    }


def scan_for(session: Session, job: Job) -> dict[str, Any]:
    """`scan_job` over the stored profile: the ONE reader behind the job page, the agent's final
    review and the Companion's `/api/jobs/match`. The profile is read once."""
    return scan_job(job, **scan_args(session))
```

`filled_answers.py` — let a batch pass the profile in, and add the count:

```python
def flag_context(session: Session, job: Job,
                 profile: dict[str, Any] | None = None) -> tuple[dict[str, Fact], set[str]]:
    """What the flags compare against: the profile as the fill would serve it. A batch passes
    `profile` (`eeo_consent.disclosable_profile`) so it is read once."""
    profile = eeo_consent.disclosable_profile(session) if profile is None else profile
    facts = autofill_catalog.build(profile, [], [], company=job.company)
    return facts, answer_flags.saved_eeo(profile)


def flag_count(session: Session, job: Job, profile: dict[str, Any] | None = None) -> int:
    """How many of the job's latest answers carry a flag: the receipt's `flag_count`."""
    rows = _rows(session, job.id)
    if not rows:
        return 0
    context = flag_context(session, job, profile)
    return sum(bool(answer_flags.flags_for(field, *context)) for _row, field in latest_fields(rows))
```

(`flag_count` must sit below `_rows` and `latest_fields` or anywhere — Python resolves at call
time; put it after `has_any`.)

`backend/app/services/inbox_readiness.py`:

```python
"""Is a job in the Agent inbox ready to send? Read-only: worked out when the inbox list is read,
never stored, so a profile edit or a new receipt shows at once.

Ready means tailored (the linked application has a PDF), no knock-out conflict, and nothing to
check in the recorded answers. Phase 4's auto-submit reads `is_ready`, so the rule lives here
once. Only open-lane rows get readiness; History rows get none.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.filled_answer import FilledAnswer
from app.models.job import Job
from app.services import eeo_consent, filled_answers, knockout
from app.services.proposals import OPEN_STATUSES

logger = logging.getLogger(__name__)
Pair = tuple[ApplicationProposal, Job]


def is_ready(readiness: dict[str, Any] | None) -> bool:
    if not readiness:
        return False
    return (readiness["tailored"] is True and readiness["knockout"] is None
            and readiness["to_check"] == 0)


def _pdf_ready(session: Session, pairs: list[Pair]) -> dict[UUID, bool]:
    ids = [p.application_id for p, _ in pairs if p.application_id is not None]
    if not ids:
        return {}
    rows = session.execute(select(Application.id, Application.pdf_path)
                           .where(Application.id.in_(ids))).all()
    return {app_id: bool(path) for app_id, path in rows}


def _answered(session: Session, pairs: list[Pair]) -> set[UUID]:
    ids = [job.id for _, job in pairs]
    return set(session.scalars(select(FilledAnswer.job_id)
                               .where(FilledAnswer.job_id.in_(ids)).distinct()))


def _knockout(job: Job, args: dict[str, Any]) -> str | None:
    scan = knockout.scan_job(job, **args)
    if scan["status"] != "conflict":
        return None
    return next((c["kind"] for c in scan["checks"] if c["result"] == "conflict"), None)


class _Batch:
    """What every row's readiness reads, loaded once."""

    def __init__(self, session: Session, pairs: list[Pair]):
        self.session = session
        self.scan = knockout.scan_args(session)
        self.pdfs = _pdf_ready(session, pairs)
        self.answered = _answered(session, pairs)
        self.profile = eeo_consent.disclosable_profile(session) if self.answered else None

    def row(self, prop: ApplicationProposal, job: Job) -> dict[str, Any]:
        to_check = (filled_answers.flag_count(self.session, job, self.profile)
                    if job.id in self.answered else 0)
        return {"tailored": self.pdfs.get(prop.application_id) if prop.application_id else None,
                "knockout": _knockout(job, self.scan), "to_check": to_check}


def for_proposals(session: Session, pairs: list[Pair]) -> dict[UUID, dict[str, Any] | None]:
    """Readiness per open proposal id. A row that fails is None (logged); the rest still read."""
    pairs = [(p, j) for p, j in pairs if p.status in OPEN_STATUSES]
    if not pairs:
        return {}
    batch = _Batch(session, pairs)
    out: dict[UUID, dict[str, Any] | None] = {}
    for prop, job in pairs:
        try:
            out[prop.id] = batch.row(prop, job)
        except Exception:  # noqa: BLE001 - one bad row must not blank the inbox
            logger.warning("readiness skipped for proposal %s", prop.id, exc_info=True)
            out[prop.id] = None
    return out
```

Note `_knockout` calls `knockout.scan_job` through the module so the tests' monkeypatch takes
effect.

**Step 4: Run the tests and the knock-out and receipt suites**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_inbox_readiness.py tests/test_knockout.py tests/test_filled_answers_api.py tests/test_filled_answers_agent.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/knockout.py backend/app/services/filled_answers.py \
  backend/app/services/inbox_readiness.py backend/tests/test_inbox_readiness.py
git commit -m "feat(inbox): readiness per open proposal, the profile read once per batch"
```

---

### Task 7: Readiness on the list, and `/api/proposals/summary`

**Files:**
- Modify: `backend/app/schemas/proposal.py` (`ProposalRead` `:77`; new `ProposalReadiness`,
  `ProposalSummaryResponse`)
- Modify: `backend/app/routers/proposals.py` (`list_proposals` `:199`; new route after `/funnel`)
- Modify: `backend/app/services/proposals.py` (constant `APPLIED_MANUALLY`)
- Modify: `backend/app/routers/applications.py` (`reason="applied manually"` → the constant)
- Modify: `backend/app/services/inbox_readiness.py` (new `summary`)
- Test: `backend/tests/test_inbox_summary.py`

**Step 1: Write the failing tests**

```python
"""Readiness on the inbox list and the arrivals strip's counts."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.models.types import utcnow
from app.services import proposals
from tests.test_proposals_models import _mk_job

client = TestClient(app)


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _prop(db_session, status, **cols):
    prop = ApplicationProposal(job_id=_mk_job(db_session).id, status=status, **cols)
    db_session.add(prop)
    db_session.commit()
    return prop


def test_the_list_carries_readiness_for_open_rows_only(db_session):
    open_id = _prop(db_session, "accepted").id
    done_id = _prop(db_session, "submitted").id
    items = {i["id"]: i for i in client.get("/api/proposals").json()["items"]}
    assert items[str(open_id)]["readiness"] == {"tailored": None, "knockout": None, "to_check": 0}
    assert items[str(done_id)]["readiness"] is None


def _summary(since):
    body = client.get("/api/proposals/summary", params={"since": since.isoformat()}).json()
    return {k: body[k] for k in ("new", "ready", "needs_you", "applied_this_week")}


def test_the_summary_counts_new_needs_you_and_applied_this_week(db_session):
    since = utcnow() - timedelta(minutes=5)
    before = _summary(since)
    _prop(db_session, "pending_review")
    _prop(db_session, "needs_human")
    _prop(db_session, "accepted")  # queued, not tailored: not ready
    _prop(db_session, "submitted")
    _prop(db_session, "rejected", reason=proposals.APPLIED_MANUALLY)
    _prop(db_session, "rejected", reason="not a fit")
    _prop(db_session, "submitted", updated_at=utcnow() - timedelta(days=8))
    after = _summary(since)
    assert {k: after[k] - before[k] for k in after} == {
        "new": 7, "ready": 0, "needs_you": 1, "applied_this_week": 2}


def test_the_summary_defaults_to_the_last_day():
    body = client.get("/api/proposals/summary").json()
    assert set(body) == {"since", "new", "ready", "needs_you", "applied_this_week"}
```

The before/after difference keeps the test exact whatever rows other tests left behind (the
TestClient shares the test DB). If `updated_at` has an `onupdate` that overwrites the explicit
value on insert, set it with a second `UPDATE` after the commit.

**Step 2: Run to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_inbox_summary.py -q`
Expected: FAIL (`readiness` missing; `/summary` routes to `/{proposal_id}` and 422s).

**Step 3: Write the code**

`schemas/proposal.py`:

```python
class ProposalReadiness(BaseModel):
    """Is this job ready to send? Open-lane rows only (services/inbox_readiness.py)."""

    tailored: bool | None = None
    knockout: str | None = None
    to_check: int = 0
```

`ProposalRead` (defined below `ProposalReadiness`) gains
`readiness: ProposalReadiness | None = None` after `job: JobSummary`. And:

```python
class ProposalSummaryResponse(BaseModel):
    since: datetime
    new: int = 0
    ready: int = 0
    needs_you: int = 0
    applied_this_week: int = 0
```

`services/proposals.py`, next to `FILED_BY_YOU`:

```python
# The reason a proposal closes with when the user applied to its job themselves
# (routers/applications.py); the inbox's History shows it as Applied yourself.
APPLIED_MANUALLY = "applied manually"
```

`routers/applications.py`: `reason="applied manually",` → `reason=proposal_svc.APPLIED_MANUALLY,`.

`inbox_readiness.py`, add:

```python
NEW_WINDOW = timedelta(hours=24)
WEEK = timedelta(days=7)


def _count(session: Session, *where) -> int:
    return session.scalar(select(func.count(ApplicationProposal.id)).where(*where)) or 0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def summary(session: Session, since: datetime | None = None) -> dict[str, Any]:
    """The arrivals strip: new since `since` (default the last day), ready to apply, needs you,
    applied this week (submitted by an agent or applied by the user)."""
    now = utcnow()
    since = _as_utc(since) if since else now - NEW_WINDOW
    queued = session.execute(select(ApplicationProposal, Job)
                             .join(Job, Job.id == ApplicationProposal.job_id)
                             .where(ApplicationProposal.status == "accepted")).all()
    applied = or_(ApplicationProposal.status == "submitted",
                  and_(ApplicationProposal.status == "rejected",
                       ApplicationProposal.reason == APPLIED_MANUALLY))
    return {
        "since": since,
        "new": _count(session, ApplicationProposal.created_at > since),
        "ready": sum(is_ready(r) for r in for_proposals(session, [tuple(r) for r in queued]).values()),
        "needs_you": _count(session, ApplicationProposal.status.in_(NEEDS_YOU)),
        "applied_this_week": _count(session, applied, ApplicationProposal.updated_at >= now - WEEK),
    }
```

with imports `from datetime import datetime, timedelta, timezone`,
`from sqlalchemy import and_, func, or_, select`, `from app.models.types import utcnow`,
`from app.services.proposals import APPLIED_MANUALLY, OPEN_STATUSES`, and
`NEEDS_YOU = ("needs_decision", "needs_human")` (the frontend's `NEEDS_YOU_STATUSES`; the
sidebar badge counts the same two).

`routers/proposals.py` — in `list_proposals`, replace the `items = [...]` line:

```python
    readiness = inbox_readiness.for_proposals(db, [(prop, job) for prop, job in results])
    items = [ProposalRead(**_read_fields(prop, job), readiness=readiness.get(prop.id))
             for prop, job in results]
```

and after `get_proposals_funnel` (before `@router.get("/{proposal_id}")`):

```python
@router.get("/summary", response_model=ProposalSummaryResponse)
def get_proposals_summary(
    db: Annotated[Session, Depends(get_db)],
    since: Annotated[datetime | None, Query()] = None,
):
    """The Agent inbox's arrivals strip. Read-only."""
    svc.expire_stale(db)
    return inbox_readiness.summary(db, since)
```

(import `datetime`, `ProposalSummaryResponse`, `inbox_readiness`).

**Step 4: Run the tests and the proposals suites**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_inbox_summary.py tests/test_proposals_router.py tests/test_proposal_state_machine.py tests/test_applications_router.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/schemas/proposal.py backend/app/routers/proposals.py \
  backend/app/services/proposals.py backend/app/routers/applications.py \
  backend/app/services/inbox_readiness.py backend/tests/test_inbox_summary.py
git commit -m "feat(inbox): readiness on the list, and the arrivals summary"
```

---

### Task 8: Frontend types and pure helpers

**Files:**
- Modify: `frontend/lib/types.ts` (`Proposal` `:1922`; new run and summary types)
- Create: `frontend/lib/inbox-readiness.ts`, `frontend/lib/inbox-readiness.test.ts`
- Create: `frontend/lib/agent-runs.ts`, `frontend/lib/agent-runs.test.ts`

**Step 1: Write the failing tests**

`frontend/lib/inbox-readiness.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { historyLabel, isNew, isReady, readinessMarks, readyFirst } from "./inbox-readiness.ts";

const ready = { tailored: true, knockout: null, to_check: 0 };

test("ready is tailored, no knock-out, nothing to check", () => {
  assert.equal(isReady(ready), true);
  assert.equal(isReady({ ...ready, tailored: null }), false);
  assert.equal(isReady({ ...ready, knockout: "opt" }), false);
  assert.equal(isReady({ ...ready, to_check: 1 }), false);
  assert.equal(isReady(null), false);
});

test("marks say tailored, the knock-out and what to check", () => {
  assert.deepEqual(readinessMarks({ tailored: false, knockout: "on_site", to_check: 3 }), [
    { text: "Not tailored", tone: "muted" },
    { text: "Knock-out: on-site", tone: "warning" },
    { text: "3 to check", tone: "warning" },
  ]);
  assert.deepEqual(readinessMarks(ready), [{ text: "Tailored", tone: "muted" }]);
  assert.deepEqual(readinessMarks({ tailored: null, knockout: "new_kind", to_check: 0 }), [
    { text: "Knock-out", tone: "warning" },
  ]);
  assert.deepEqual(readinessMarks(undefined), []);
});

test("ready rows come first and keep their order", () => {
  const rows = [
    { id: "a", readiness: { ...ready, tailored: false } },
    { id: "b", readiness: ready },
    { id: "c", readiness: null },
    { id: "d", readiness: ready },
  ];
  assert.deepEqual(readyFirst(rows).map((r) => r.id), ["b", "d", "a", "c"]);
});

test("a job the user applied to themselves reads Applied yourself", () => {
  assert.equal(historyLabel("rejected", "applied manually", "Skipped"), "Applied yourself");
  assert.equal(historyLabel("rejected", "not a fit", "Skipped"), "Skipped");
  assert.equal(historyLabel("submitted", null, "Applied"), "Applied");
});

test("new means created after the last visit", () => {
  assert.equal(isNew("2026-10-05T10:00:00Z", "2026-10-05T09:00:00Z"), true);
  assert.equal(isNew("2026-10-05T08:00:00Z", "2026-10-05T09:00:00Z"), false);
  assert.equal(isNew("2026-10-05T10:00:00Z", null), false);
});
```

`frontend/lib/agent-runs.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { countsLine, lastRanLine, latestByAutomation, outcomeWord } from "./agent-runs.ts";

test("counts read in a fixed order, zeros left out", () => {
  assert.equal(countsLine({ skipped: 8, found: 12, proposed: 4, updated: 0 }),
    "Found 12 · proposed 4 · skipped 8");
  assert.equal(countsLine({ needs_you: 1 }), "1 needs you");
  assert.equal(countsLine({ needs_you: 2, tailored: 3 }), "Tailored 3 · 2 need you");
  assert.equal(countsLine({}), "Nothing to report");
});

test("outcomes in words", () => {
  assert.equal(outcomeWord("ok"), "Done");
  assert.equal(outcomeWord("partial"), "Partly done");
  assert.equal(outcomeWord("failed"), "Failed");
});

test("the newest run per automation, and the card's line", () => {
  const map = latestByAutomation([
    { automation: "job-hunt", finished_at: "2026-10-05T10:00:00Z" },
    { automation: "mail-status", finished_at: "2026-10-04T10:00:00Z" },
  ]);
  assert.equal(map.get("job-hunt"), "2026-10-05T10:00:00Z");
  assert.equal(lastRanLine(undefined, (x) => x), null); // unknown yet: no line
  assert.equal(lastRanLine(null, (x) => x), "Not run yet");
  assert.equal(lastRanLine("t", () => "2 hours ago"), "Last ran 2 hours ago");
});
```

**Step 2: Run to verify they fail**

Run (from `frontend/`): `node --test lib/inbox-readiness.test.ts lib/agent-runs.test.ts`
Expected: FAIL (`Cannot find module`).

**Step 3: Write the helpers and types**

`frontend/lib/inbox-readiness.ts`:

```ts
// Readiness on the Agent inbox's rows (backend services/inbox_readiness.py owns the rule; this is
// its twin for sorting and words). Pure: `node --test` loads it, so it imports nothing.

export type Readiness = { tailored: boolean | null; knockout: string | null; to_check: number };
export type ReadinessMark = { text: string; tone: "muted" | "warning" };

const KNOCKOUT_WORDS: Record<string, string> = {
  work_authorization: "work authorization",
  opt: "OPT",
  salary: "salary",
  experience: "experience",
  on_site: "on-site",
};

/** The reason the backend closes a proposal with when you applied yourself (services/proposals.py). */
export const APPLIED_MANUALLY = "applied manually";

export function isReady(r: Readiness | null | undefined): boolean {
  return !!r && r.tailored === true && r.knockout == null && r.to_check === 0;
}

export function readinessMarks(r: Readiness | null | undefined): ReadinessMark[] {
  if (!r) return [];
  const marks: ReadinessMark[] = [];
  if (r.tailored != null) marks.push({ text: r.tailored ? "Tailored" : "Not tailored", tone: "muted" });
  if (r.knockout) {
    const word = KNOCKOUT_WORDS[r.knockout];
    marks.push({ text: word ? `Knock-out: ${word}` : "Knock-out", tone: "warning" });
  }
  if (r.to_check > 0) marks.push({ text: `${r.to_check} to check`, tone: "warning" });
  return marks;
}

/** Ready rows first; each group keeps the order it came in (the user's chosen sort). */
export function readyFirst<T extends { readiness?: Readiness | null }>(items: readonly T[]): T[] {
  return [...items.filter((i) => isReady(i.readiness)), ...items.filter((i) => !isReady(i.readiness))];
}

/** History's chip: Applied yourself for a job you applied to outside the agent. */
export function historyLabel(status: string, reason: string | null | undefined, fallback: string): string {
  return status === "rejected" && reason === APPLIED_MANUALLY ? "Applied yourself" : fallback;
}

/** Created after the last visit. No visit time known yet: nothing is marked new. */
export function isNew(createdAt: string, since: string | null): boolean {
  return since != null && Date.parse(createdAt) > Date.parse(since);
}
```

`frontend/lib/agent-runs.ts`:

```ts
// The run log's words (backend services/agent_runs.py). Pure: `node --test` loads it.

export type RunOutcome = "ok" | "partial" | "failed";

const COUNT_ORDER = ["found", "proposed", "tailored", "updated", "skipped", "needs_you"] as const;

function countWords(key: (typeof COUNT_ORDER)[number], n: number): string {
  if (key === "needs_you") return `${n} ${n === 1 ? "needs" : "need"} you`;
  return `${key} ${n}`;
}

/** "Found 12 · proposed 4 · skipped 8": fixed order, zeros left out, first word capitalized. */
export function countsLine(counts: Record<string, number>): string {
  const parts = COUNT_ORDER.filter((k) => (counts[k] ?? 0) > 0).map((k) => countWords(k, counts[k]));
  if (parts.length === 0) return "Nothing to report";
  const line = parts.join(" · ");
  return line[0].toUpperCase() + line.slice(1);
}

const OUTCOME_WORDS: Record<RunOutcome, string> = { ok: "Done", partial: "Partly done", failed: "Failed" };

export function outcomeWord(outcome: RunOutcome): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

/** automation → when its newest run finished (the list comes newest first). */
export function latestByAutomation(runs: readonly { automation: string; finished_at: string }[]) {
  const map = new Map<string, string>();
  for (const run of runs) if (!map.has(run.automation)) map.set(run.automation, run.finished_at);
  return map;
}

/** An Automations card's line. `undefined` while unknown (loading or failed): no line. */
export function lastRanLine(finishedAt: string | null | undefined, ago: (iso: string) => string): string | null {
  if (finishedAt === undefined) return null;
  return finishedAt === null ? "Not run yet" : `Last ran ${ago(finishedAt)}`;
}

export const AGENT_RUNS_LATEST_KEY = ["agent-runs", "latest"] as const;
```

`frontend/lib/types.ts`: `Proposal` gains

```ts
  /** Open-lane rows only (backend services/inbox_readiness.py); null in History. Optional: an
   *  older backend does not send it. */
  readiness?: { tailored: boolean | null; knockout: string | null; to_check: number } | null;
```

and add near `ProposalListResponse`:

```ts
export interface ProposalSummary {
  since: string;
  new: number;
  ready: number;
  needs_you: number;
  applied_this_week: number;
}

export interface AgentRun {
  id: UUID;
  automation: string;
  title: string;
  outcome: "ok" | "partial" | "failed";
  agent: string | null;
  finished_at: string;
  counts: Record<string, number>;
  digest: string;
  jobs: { id: UUID; title: string | null; company: string | null }[];
}

export interface AgentRunList {
  items: AgentRun[];
}
```

**Step 4: Run the tests and the type check**

Run (from `frontend/`): `node --test lib/inbox-readiness.test.ts lib/agent-runs.test.ts && npx tsc --noEmit`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/inbox-readiness.ts frontend/lib/inbox-readiness.test.ts \
  frontend/lib/agent-runs.ts frontend/lib/agent-runs.test.ts
git commit -m "feat(web): readiness and run-log words, pure and tested"
```

---

### Task 9: Rows — readiness marks, ready first in Queued, Applied yourself, New dot

**Files:**
- Create: `frontend/components/proposals/readiness-marks.tsx`
- Modify: `frontend/components/proposals/proposals-section.tsx`
- Modify: `backend/tests/test_frontend_agent_inbox.py`

**Step 1: Write the failing pins** (append to `test_frontend_agent_inbox.py`; reuse its
`_read`-style loader and file constants):

```python
_MARKS = _read("components/proposals/readiness-marks.tsx")


def test_rows_show_readiness_marks_and_queued_puts_ready_first():
    assert "<ReadinessMarks readiness={proposal.readiness} />" in _SECTION
    assert "readyFirst(sortProposals(inLane(filtered, \"queued\"), sort))" in _SECTION
    assert "readinessMarks(readiness)" in _MARKS


def test_history_says_applied_yourself_and_new_rows_are_marked():
    assert "historyLabel(proposal.status, proposal.reason, STATUS_LABELS[proposal.status])" in _SECTION
    assert "isNew(proposal.created_at, since)" in _SECTION
```

(`_SECTION` is the existing constant holding `proposals-section.tsx`; if it is named
differently, use that name.)

**Step 2: Run to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_agent_inbox.py -q`
Expected: FAIL (file missing).

**Step 3: Write the component and wire the rows**

`frontend/components/proposals/readiness-marks.tsx`:

```tsx
import { readinessMarks, type Readiness } from "@/lib/inbox-readiness";
import { cn } from "@/lib/utils";

const TONE = {
  muted: "bg-surface-container-high text-muted-foreground dark:bg-surface-container-highest",
  warning: "bg-warning-container text-on-warning-container",
} as const;

/** A row's readiness: Tailored or Not tailored, a knock-out, answers to check. Nothing when unknown. */
export function ReadinessMarks({ readiness }: { readiness: Readiness | null | undefined }) {
  const marks = readinessMarks(readiness);
  if (marks.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {marks.map((mark) => (
        <span key={mark.text} className={cn("rounded-full px-2 py-0.5 text-label-small", TONE[mark.tone])}>
          {mark.text}
        </span>
      ))}
    </span>
  );
}
```

`proposals-section.tsx`:
1. `export function ProposalsSection({ since = null }: { since?: string | null } = {})` and pass
   `since` into `rowProps`; `ProposalRow` takes `since: string | null`.
2. `queued`: `readyFirst(sortProposals(inLane(filtered, "queued"), sort))`.
3. In `ProposalRow`, in the title's `flex flex-wrap` line, after the "Possible duplicate" span:
   ```tsx
   {isNew(proposal.created_at, since) ? (
     <span className="inline-flex items-center gap-1 text-label-small text-primary">
       <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
       New
     </span>
   ) : null}
   <ReadinessMarks readiness={proposal.readiness} />
   ```
4. The status `Badge` text: `{historyLabel(proposal.status, proposal.reason, STATUS_LABELS[proposal.status])}`.
5. `Lane` takes an optional `anchor?: string`, rendered as `id={anchor}` placed AFTER
   `aria-labelledby={headingId}` on the `<section>`; pass `anchor=` as the LAST prop on each
   `<Lane>` (after `title`): `"inbox-needs-you"`, `"inbox-to-review"`, `"inbox-queued"`. The
   History `<section>` gets `id="inbox-history"` after `aria-labelledby={historyId}`. Existing
   pins in `test_frontend_agent_inbox.py` quote the attribute order (`<Lane ref={toReview}
   title=…`, `<section ref={ref} tabIndex={-1} aria-labelledby={headingId}`).

Imports: `isNew`, `historyLabel`, `readyFirst` from `@/lib/inbox-readiness`; `ReadinessMarks`.
Do not rename lane titles (existing pins).

**Step 4: Run the pins, the type check and lint**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_agent_inbox.py tests/test_frontend_vocabulary.py -q`
and (from `frontend/`) `npx tsc --noEmit && npx eslint components/proposals`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/components/proposals backend/tests/test_frontend_agent_inbox.py
git commit -m "feat(web): readiness marks, ready first in Queued, Applied yourself, New"
```

---

### Task 10: The dashboard — last visit, arrivals strip, Recent runs

**Files:**
- Create: `frontend/hooks/use-inbox-visit.ts`
- Create: `frontend/components/proposals/inbox-dashboard.tsx`
- Create: `frontend/components/proposals/arrivals-strip.tsx`
- Create: `frontend/components/proposals/recent-runs.tsx`
- Modify: `frontend/app/proposals/page.tsx`
- Test: `backend/tests/test_frontend_agent_dashboard.py`

**Step 1: Write the failing pins** — new file, same style as `test_frontend_automations.py`:

```python
"""Pins: the Agent inbox's dashboard (docs/plans/2026-10-05-agent-dashboard-design.md).

Read-only: the strip and the Recent runs panel only read. The last visit lives in this browser
and a blocked storage still renders the page. There is no frontend test runner, so the branches
that matter are pinned here from the source."""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/proposals/page.tsx")
_DASH = _read("components/proposals/inbox-dashboard.tsx")
_STRIP = _read("components/proposals/arrivals-strip.tsx")
_RUNS = _read("components/proposals/recent-runs.tsx")
_VISIT = _read("hooks/use-inbox-visit.ts")


def test_the_page_renders_the_dashboard_in_order():
    assert "<InboxDashboard />" in _PAGE
    assert _DASH.index("<ArrivalsStrip") < _DASH.index("<RecentRuns") < _DASH.index("<ProposalsSection")
    assert "<ProposalsSection since={since} />" in _DASH


def test_the_strip_reads_the_summary_and_names_its_tiles():
    assert "/api/proposals/summary" in _STRIP
    assert '["proposals", "summary", since]' in _STRIP  # refetches with every triage
    for words in ("New since your last visit", "Ready to apply", "Needs you", "Applied this week"):
        assert words in _STRIP
    assert "scrollIntoView" in _STRIP


def test_recent_runs_reads_latest_and_fails_quietly():
    assert "/api/agent-runs/latest" in _RUNS
    assert "AGENT_RUNS_LATEST_KEY" in _RUNS
    assert "No runs yet. Set one up on Automations." in _RUNS
    assert "Couldn't load recent runs." in _RUNS
    assert "LoadErrorState" not in _RUNS
    assert "countsLine(" in _RUNS and "outcomeWord(" in _RUNS and "agentDisplayName(" in _RUNS


def test_the_last_visit_survives_blocked_storage_and_reads_once():
    assert _VISIT.count("try {") >= 2  # the read and the write
    assert "useRef(false)" in _VISIT  # dev double-effect never reads its own write
    assert "24 * 60 * 60 * 1000" in _VISIT
```

**Step 2: Run to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_agent_dashboard.py -q`
Expected: FAIL (files missing).

**Step 3: Write the hook and components**

`frontend/hooks/use-inbox-visit.ts`:

```ts
"use client";

import { useEffect, useRef, useState } from "react";

const KEY = "cs-inbox-last-visit";
const DAY_MS = 24 * 60 * 60 * 1000;

/** When you last opened the Agent inbox, as an ISO time; the last day when this browser never
 *  stored one (or storage is blocked). Read once on mount, then now is stored. Null until mounted. */
export function useInboxVisit(): string | null {
  const [since, setSince] = useState<string | null>(null);
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(KEY);
    } catch {
      // Storage blocked: fall back to the last day.
    }
    const valid = stored && !Number.isNaN(Date.parse(stored)) ? stored : null;
    setSince(valid ?? new Date(Date.now() - DAY_MS).toISOString());
    try {
      window.localStorage.setItem(KEY, new Date().toISOString());
    } catch {
      // A convenience only: the page works without it.
    }
  }, []);
  return since;
}
```

`frontend/components/proposals/inbox-dashboard.tsx`:

```tsx
"use client";

import { useInboxVisit } from "@/hooks/use-inbox-visit";

import { ArrivalsStrip } from "./arrivals-strip";
import { ProposalsSection } from "./proposals-section";
import { RecentRuns } from "./recent-runs";

/** The Agent inbox: what came in, what your agent runs did, then the lanes. */
export function InboxDashboard() {
  const since = useInboxVisit();
  return (
    <div className="flex flex-col gap-6">
      <ArrivalsStrip since={since} />
      <RecentRuns />
      <ProposalsSection since={since} />
    </div>
  );
}
```

`frontend/components/proposals/arrivals-strip.tsx`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { ProposalSummary } from "@/lib/types";

const TILES = [
  { key: "new", label: "New since your last visit", anchor: "inbox-to-review" },
  { key: "ready", label: "Ready to apply", anchor: "inbox-queued" },
  { key: "needs_you", label: "Needs you", anchor: "inbox-needs-you" },
  { key: "applied_this_week", label: "Applied this week", anchor: "inbox-history" },
] as const;

function jumpTo(anchor: string) {
  const lane = document.getElementById(anchor);
  lane?.scrollIntoView({ block: "start", behavior: "smooth" });
  lane?.focus({ preventScroll: true });
}

/** Four counts over the lanes. A tile with nothing in it, or a lane not on screen, does not jump. */
export function ArrivalsStrip({ since }: { since: string | null }) {
  const { data } = useQuery({
    queryKey: ["proposals", "summary", since],
    queryFn: () => apiFetch<ProposalSummary>(`/api/proposals/summary?since=${encodeURIComponent(since ?? "")}`),
    enabled: since != null,
  });
  return (
    <div className="grid grid-cols-4 gap-3" aria-label="Agent inbox summary" role="group">
      {TILES.map((tile) => {
        const count = data?.[tile.key];
        return (
          <button
            key={tile.key}
            type="button"
            disabled={!count}
            onClick={() => jumpTo(tile.anchor)}
            className="flex flex-col items-start gap-1 rounded-corner-md border bg-card p-4 text-left disabled:cursor-default enabled:hover:bg-surface-container-high"
          >
            <span className="text-headline-small tabular-nums">{count ?? "–"}</span>
            <span className="text-muted-foreground text-body-medium">{tile.label}</span>
          </button>
        );
      })}
    </div>
  );
}
```

Follow the design system: if `docs/design-system/` names a stat-tile component or tokens
different from these classes, use those (moderate freedom). An empty `since` never fetches
(`enabled`).

`frontend/components/proposals/recent-runs.tsx`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { GuardedLink as Link } from "@/components/guarded-link";
import { apiFetch } from "@/lib/api";
import { agentDisplayName } from "@/lib/agent-name";
import { AGENT_RUNS_LATEST_KEY, countsLine, outcomeWord } from "@/lib/agent-runs";
import { formatTimeAgo } from "@/lib/format-date";
import type { AgentRun, AgentRunList } from "@/lib/types";

function RunLine({ run }: { run: AgentRun }) {
  const who = agentDisplayName(run.agent);
  return (
    <details className="group rounded-corner-md border px-4 py-3">
      <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-title-small">{run.title}</span>
        <span className="text-muted-foreground text-body-small">
          {formatTimeAgo(run.finished_at)}
          {who ? ` · ${who}` : ""} · {outcomeWord(run.outcome)}
        </span>
        <span className="text-body-small">{countsLine(run.counts)}</span>
      </summary>
      {run.digest ? <p className="mt-2 max-w-[65ch] whitespace-pre-wrap text-body-medium">{run.digest}</p> : null}
      {run.jobs.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1 text-body-medium">
          {run.jobs.map((job) => (
            <li key={job.id}>
              <Link href={`/jobs/${job.id}?from=proposals`} className="text-primary">
                {[job.title ?? "Untitled role", job.company].filter(Boolean).join(", ")}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}

/** The newest run of each automation your agent recorded (MCP record_run). Read-only. */
export function RecentRuns() {
  const { data, isError } = useQuery({
    queryKey: AGENT_RUNS_LATEST_KEY,
    queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
  });
  return (
    <section aria-labelledby="recent-runs" className="flex flex-col gap-2">
      <h2 id="recent-runs" className="text-muted-foreground text-title-small">Recent runs</h2>
      {isError ? (
        <p className="text-muted-foreground">{"Couldn't load recent runs."}</p>
      ) : !data ? null : data.items.length === 0 ? (
        <p className="text-muted-foreground">
          No runs yet. Set one up on Automations.{" "}
          <Link href="/automations" className="text-primary">Open Automations</Link>
        </p>
      ) : (
        data.items.map((run) => <RunLine key={run.id} run={run} />)
      )}
    </section>
  );
}
```

Verify `agentDisplayName` is the export name in `lib/agent-name.ts` (it is the twin of
`agent_names.agent_display_name`); if it differs, use the real name in code and pin.

`frontend/app/proposals/page.tsx`: replace `<ProposalsSection />` with `<InboxDashboard />` and
its import.

**Step 4: Run the pins, the type check, lint and the ratchets**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_agent_dashboard.py tests/test_frontend_agent_inbox.py tests/test_frontend_vocabulary.py tests/test_frontend_query_error_states.py tests/test_frontend_design_tokens.py -q`
and (from `frontend/`) `npx tsc --noEmit && npm run lint`
Expected: PASS. If a design-token ratchet refuses a class used above, use the token it names.

**Step 5: Commit**

```bash
git add frontend/hooks/use-inbox-visit.ts frontend/components/proposals frontend/app/proposals/page.tsx \
  backend/tests/test_frontend_agent_dashboard.py
git commit -m "feat(web): the Agent inbox dashboard: arrivals strip and Recent runs"
```

---

### Task 11: "Last ran" on each Automations card

**Files:**
- Modify: `frontend/components/automations/automation-card.tsx`
- Modify: `frontend/app/automations/page.tsx`
- Modify: `backend/tests/test_frontend_automations.py`

**Step 1: Write the failing pins**

```python
def test_each_card_says_when_it_last_ran():
    assert "AGENT_RUNS_LATEST_KEY" in _PAGE
    assert 'apiFetch<AgentRunList>("/api/agent-runs/latest")' in _PAGE
    assert "lastRanLine(lastRun, formatTimeAgo)" in _CARD


def test_the_catalog_stays_db_free():
    # The Last ran line comes from its own read; GET /api/automations reads no table.
    assert "agent-runs" not in _LIB
```

**Step 2: Run to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_automations.py -q`
Expected: the first FAILs.

**Step 3: Wire it**

`automation-card.tsx`: a new optional prop
`lastRun?: string | null` (undefined = unknown, no line; null = Not run yet), rendered under
the summary:

```tsx
const ranLine = lastRanLine(lastRun, formatTimeAgo);
…
{ranLine ? <p className="text-muted-foreground text-body-small">{ranLine}</p> : null}
```

`page.tsx`: a second query

```tsx
const runs = useQuery({
  queryKey: AGENT_RUNS_LATEST_KEY,
  queryFn: () => apiFetch<AgentRunList>("/api/agent-runs/latest"),
});
const ran = runs.data ? latestByAutomation(runs.data.items) : null;
```

and on each scheduled/attended card `lastRun={ran ? (ran.get(card.id) ?? null) : undefined}`.
The custom card gets no `lastRun` (custom runs carry their own names).

**Step 4: Run the pins, the type check and lint**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_automations.py tests/test_frontend_vocabulary.py -q`
and `npx tsc --noEmit && npm run lint` from `frontend/`.
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/components/automations frontend/app/automations/page.tsx backend/tests/test_frontend_automations.py
git commit -m "feat(web): each Automations card says when it last ran"
```

---

### Task 12: Docs

**Files:**
- Create: `docs/entities/agent-runs.md`
- Modify: `docs/entities/others.md` (the proposals section, `:487-595`)
- Modify: `SYSTEM.md` (§2 layout, §3 diagram tool count, §5 inbox sentence, §7 Automations
  bullet and MCP tool list), `CHANGELOG.md`
- Modify: tool count 84 → 85 in `README.md` (`:52`, `:130`, `:453`), `KNOWN_ISSUES.md:29`,
  `backend/mcp_server/README.md:24`, `mcpb/manifest.json:53`,
  `plugins/maestro-career-studio/README.md:84`, `SYSTEM.md:118`
  (`git grep -n "84 tools\|(84\b\|all 84"` must come back empty afterwards).

**Step 1: `docs/entities/agent-runs.md`** — fields (the Task 1 table), who writes (MCP
`record_run` only; no edit or delete tool, no web write), who reads (Recent runs, Last ran),
retention (newest 200), trimming (digest 2,000 characters, 50 job ids, unknown ids dropped),
and **Limits**: the digest is the agent's own text, and Maestro cannot verify it holds no email
text (the mail-status prompt forbids it); there is no "overdue" because Maestro does not know the
user's schedule; a run that crashes before recording leaves the previous time.

**Step 2: `others.md` proposals section** — add: readiness on the list (rule, open lanes
only, computed at read, `inbox_readiness.is_ready` is phase 4's rule), `GET
/api/proposals/summary` (four counts and their windows), History's "Applied yourself" label for
`reason == "applied manually"` (label only).

**Step 3: SYSTEM.md** — it is at 995/1000. First groom: move one verbatim paragraph of
§7 or §11 detail that already has a home in `docs/entities/*` (check with grep that the
destination holds the same rule, or move it there verbatim), so every rule-bearing clause
survives. Then add, in the fewest lines:
- §5 (the `/proposals` mention at `:162-163`): "…lanes are one table: `lib/inbox-lanes.ts`;
  above them an arrivals strip (`/api/proposals/summary`) and Recent runs (`agent_runs`,
  docs/entities/agent-runs.md); open rows carry read-time readiness
  (`services/inbox_readiness.py`)."
- §7 Automations bullet: "Each prompt ends with MCP `record_run`; cards show Last ran."
- §3 diagram: 84 → 85 tools.
Run `/opt/anaconda3/bin/python3 scripts/check_system_md.py`: it must pass at ≤ 1000 lines.

**Step 4: CHANGELOG** — under Unreleased: Agent inbox shows readiness marks, an arrivals strip,
Recent runs; Automations cards say when they last ran; new MCP tool `record_run`; job-hunt
saves its jobs as found by an agent; History says Applied yourself for jobs you applied to.

**Step 5: Run the doc gates and commit**

Run: `/opt/anaconda3/bin/python3 scripts/check_system_md.py && git grep -n "84 tools\|all 84"`
Expected: gate passes; grep prints nothing.

```bash
git add docs SYSTEM.md CHANGELOG.md README.md KNOWN_ISSUES.md backend/mcp_server/README.md \
  mcpb/manifest.json plugins/maestro-career-studio/README.md
git commit -m "docs: the run log, inbox readiness and summary, record_run (85 tools)"
```

---

### Task 13: Full verification

1. Backend suite, from `backend/`:
   `/opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
   Expected: all pass (a known-flaky Typst test under xdist load may fail; rerun it alone and
   report both runs).
2. Frontend, from `frontend/`: `node --test lib/inbox-readiness.test.ts lib/agent-runs.test.ts
   lib/inbox-lanes.test.ts`, `npx tsc --noEmit`, `npm run lint`, `npm run build`.
3. SYSTEM.md gate and the slop ratchet on `backend` and `frontend` (name both).
4. Live check on a fresh stack on spare ports (not 8001/3000: those are the owner's live app):
   migrate a throwaway DB, start uvicorn and `next dev`, then:
   - `curl -X POST /api/agent-runs` with MCP headers for `job-hunt` (with a real job id) and
     `mail-status`; open `/proposals`: the strip shows four counts, Recent runs shows two
     lines, expanding one shows its digest and job link.
   - Queue a job with a tailored application: it shows **Tailored** and sorts first in Queued;
     the Ready to apply tile counts it; clicking the tile scrolls to Queued.
   - Mark an application applied on the Jobs page: History shows **Applied yourself** and
     Applied this week goes up.
   - `/automations`: Job hunt and Mail status say "Last ran …"; the others "Not run yet".
   - Screenshot each at 1280 and 1024 (desktop only).
5. Report: commands run, counts, anything skipped and why.
