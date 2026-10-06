# Split-Ownership Sync (Phase 4b) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A second, always-on Maestro copy hunts and applies while the laptop is off. The laptop
keeps the profile and works fully offline, and every job has exactly one owner at a time.

**Design:** `docs/plans/2026-10-06-split-ownership-sync-design.md`. Read it whole, including
**"Amendments from planning"**, which overrides Parts B and D where they differ.

**Architecture:**
- Each install gets a machine id. `jobs` gains `owner_machine`, `sync_rev` and `handover`.
- A `before_flush` hook does two things: it refuses writes to rows this machine doesn't own, and it
  bumps a per-job revision (plus a profile revision) from a local clock.
- The laptop ("home") exposes key-guarded `/api/sync/*` endpoints on its loopback. The always-on
  copy ("remote") reaches them through an SSH-forwarded port.
- The remote's backend runs a round in-process when asked. The steps are: hello and version check,
  ownership reconcile, profile pull, own jobs push, home jobs pull, requests both ways, handovers,
  then run-log push.
- Bundles are JSON: rows per table, plus files as base64 with paths relative to their root. A job
  is applied as upsert-by-primary-key, then delete what's missing within that job's subtree.

**Tech Stack:**
- Backend: FastAPI, SQLAlchemy 2 ORM events, SQLite (WAL), alembic, httpx (`http_client.new_client`).
- Agent side: FastMCP.
- Native scripts: bash.
- Frontend: Next.js 16 / React 19.
- Tests: pytest + xdist, and a real uvicorn subprocess for the home side.

**Ground rules (every task):**
- **Before you start:** read `SYSTEM.md` and the design doc.
- **Commits:** none. The session commits after each task's review.
- **Public repo:** no product names for the always-on machine's agent app, no real company names,
  no real application questions. Write "your bot" or "the always-on copy" instead.
- **Sync off must change nothing.** "Sync off" means no key file. In that state:
  - every job counts as owned here, and no write is refused;
  - every `/api/sync/*` route returns 404;
  - `sync_now` says "Sync isn't set up."
  - The full suite must pass unchanged (`MAESTRO_SKIP_SLOW=1 … -n auto --dist loadfile`).
- **Secrets:**
  - Never log a bundle, a key or a request body.
  - Sync endpoints refuse any request carrying an `Origin` header, before reading the body.
  - Compare keys with `hmac.compare_digest`.
- **Terms:** "home" is the copy that owns the profile (the laptop). "Remote" is the always-on copy,
  which has `SYNC_REMOTE_URL` set.
- **Prerequisite:** the application-preferences plan lands first. It adds a migration and a tool,
  so take the alembic head and tool count from the code, not from this doc.

---

## Stage 1: Ownership, revisions and the guard (works with sync off; no network)

### Task 1: Config, machine id and sync status

**Files:**
- Modify: `backend/app/config.py`. Add `sync_key_file: Path | None = None` and
  `sync_remote_url: str = ""`, following the existing field patterns (`embeddings_out_of_process`, ~line 65).
- Create: `backend/app/services/sync/__init__.py` (empty), `backend/app/services/sync/status.py`,
  `backend/tests/sync/__init__.py` (tests are packages) and `backend/tests/sync/conftest.py`.
- Test: `backend/tests/sync/test_status.py`.

**`status.py`:**

```python
"""Is sync set up, and which side is this? (split-ownership design, Part B)."""

import secrets
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.setting import Setting

MACHINE_ID_KEY = "sync.machine_id"
SYNC_PROTOCOL = 1


def key_path() -> Path:
    return settings.sync_key_file or settings.settings_dir / "secrets" / "sync-key"


def read_key() -> str | None:
    """The shared key, or None when sync isn't set up. Never logged."""
    path = key_path()
    if not path.is_file() or path.is_symlink():
        return None
    key = path.read_text(encoding="utf-8").strip()
    return key or None


def enabled() -> bool:
    return read_key() is not None


def is_remote() -> bool:
    return enabled() and bool(settings.sync_remote_url)


def machine_id(db: Session) -> str:
    """This install's id, created on first use; local, never synced."""
    row = db.get(Setting, MACHINE_ID_KEY)
    if row is None:
        row = Setting(key=MACHINE_ID_KEY, value=uuid.uuid4().hex)
        db.add(row)
        db.flush()
    return row.value


def create_key() -> Path:
    """Write a fresh key, 0600 in a 0700 directory, refusing to overwrite (the CLI's job)."""
    path = key_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secrets.token_urlsafe(32) + "\n")
    return path
```

(Add `import os`.) `machine_id` must be safe if two requests race: catch `IntegrityError`, roll
back and re-read.

**Tests (fail first):**
- With no key file, sync is off and `is_remote()` is False.
- A key file turns it on. A symlinked or empty file stays off.
- `machine_id` is stable across calls and sessions.
- `create_key` writes mode 0600 inside a 0700 directory and refuses a second time.
- Add a `sync_on(tmp_path, monkeypatch, remote_url="")` fixture in `tests/sync/conftest.py` that
  writes a key and patches `settings`. Later tasks reuse it.

### Task 2: The migration

**Files:**
- Create: `backend/migrations/versions/<12hex>_split_ownership_sync.py`, with down_revision set to
  the current `alembic heads`.
- Modify: `backend/app/models/job.py` and `backend/app/models/agent_run.py`.
- Create: `backend/app/models/sync.py` (`SyncState`, `SyncTombstone`, `SyncRequest`) and register
  it wherever models are imported for metadata (follow how `agent_run` was added in 7d3c1a9e5b20).
- Test: `backend/tests/sync/test_migration.py`.

**Schema:**
- `jobs`:
  - `owner_machine` String(32) NULL. NULL means owned here.
  - `sync_rev` Integer NOT NULL server_default "0".
  - `handover` String(16) NULL. Values: `offered` (home→remote) or `returning` (remote→home).
- `agent_runs`: `machine` String(32) NULL. NULL means it ran here.
- `sync_state`: `name` String PK, `value` Integer NOT NULL. Rows `clock` and `profile_rev`.
- `sync_tombstones`: `job_id` Uuid PK, `rev` Integer NOT NULL, `deleted_at` DateTime(tz).
- `sync_requests`:
  - `id` Uuid PK, `job_id` Uuid NULL (no FK, since the job may be a replica that gets replaced),
    `kind` String(32), `payload_json` JSON;
  - `status` String(16): `pending`, `sent`, `applied` or `refused`;
  - `reason` Text NULL, `created_at`, `answered_at` NULL;
  - `origin` String(8): `local` (made here, for the other side) or `incoming`.

Models use `UUIDType` and `UTCDateTime` from `app.models.types` for every UUID and datetime column
(the single-dialect invariant; `tests/test_db_portability.py` fails a plain `sa.DateTime`). Use
`op.batch_alter_table` for the two altered tables. Tests: upgrade, downgrade, then upgrade
again on a scratch DB file. Existing rows read `owner_machine IS NULL` and `sync_rev == 0`.

### Task 3: The table registry, one place that says what everything is

**Files:**
- Create: `backend/app/services/sync/registry.py`.
- Test: `backend/tests/sync/test_registry.py`.

```python
"""Every table's sync class (design Part A + amendments). A new table MUST be added here:
test_every_table_is_classified fails otherwise."""

PROFILE = "profile"; JOB = "job"; RUN_LOG = "run_log"; LOCAL = "local"; SYNC = "sync"

TABLES = {
    "jobs": JOB, "job_skills": JOB, "applications": JOB, "application_proposals": JOB,
    "consent_events": JOB, "ats_scores": JOB, "tailoring_sessions": JOB, "qa_entries": JOB,
    "filled_answers": JOB,
    "base_resumes": PROFILE, "templates": PROFILE, "referrals": PROFILE, "kb_entities": PROFILE,
    "kb_points": PROFILE, "kb_documents": PROFILE, "kb_profile": PROFILE, "settings": PROFILE,
    # split by resume_kind: 'base' rows are profile, 'application' rows follow their application
    "resume_versions": "by_kind", "resume_lint_reports": "by_kind",
    "health_ask_answers": "by_kind", "health_gate_waivers": "by_kind", "kb_port_log": "by_kind",
    "agent_runs": RUN_LOG,
    "bullet_classifications": LOCAL, "bullet_rewrites": LOCAL, "bullet_disputes": LOCAL,
    "chat_sessions": LOCAL, "chat_messages": LOCAL, "chat_attachments": LOCAL,
    "autofill_runs": LOCAL, "autofill_field_observations": LOCAL, "autofill_mechanism_stats": LOCAL,
    "sync_state": SYNC, "sync_tombstones": SYNC, "sync_requests": SYNC, "alembic_version": SYNC,
}

LOCAL_SETTING_PREFIXES = ("sync.", "llm.capabilities.", "kb.seeded", "llm_library_proposals")
```

Also implement two functions:
- `job_id_of(session, obj) -> UUID | None`: the job a job-class or `by_kind=application` row
  belongs to. Use the parent `job_id`. For `consent_events`, go through the proposal. For
  `qa_entries`, go through the application. For by_kind application rows, the application id is
  `resume_key` (a UUID string); load it with `session.no_autoflush`.
- `is_profile_row(obj) -> bool`: true for profile tables, `by_kind` rows with kind `base`, and
  settings rows whose key has no `LOCAL_SETTING_PREFIXES` prefix.

**Tests:**
- Every table in `Base.metadata.sorted_tables` is in `TABLES`.
- `job_id_of` resolves each job-class model.
- `is_profile_row` covers settings keys both ways.
- `bullet_*` caches are LOCAL. They are content-addressed, so each copy recomputes its own; say
  that in a comment.

### Task 4: The hook (revisions, and the guard off by default)

**Files:**
- Create: `backend/app/services/sync/hooks.py`.
- Modify: `backend/app/db.py`. Install the hook once on the `Session` class, so every session is
  covered, including the services that call `SessionLocal()` directly.
- Test: `backend/tests/sync/test_hooks.py`.

Behavior of the `before_flush` handler (`event.listen(Session, "before_flush", _before_flush)`):

1. **Imports:** if `session.info.get("sync_apply")` is set, skip the guard but still bump: the
   receiver restamps every row it writes from ITS OWN clock. `sync_rev` is always this machine's
   clock, never the sender's; bundles carry no `sync_rev`, `owner_machine` or `handover` as row
   data (those travel as bundle fields and are set by the importer).
2. **Collect touched rows:** for each object in `new`, `deleted`, and `dirty` with
   `session.is_modified(obj)`, find its class through the registry (`obj.__table__.name`). Then:
   - JOB or by_kind application rows → `touched_jobs.add(job_id_of(...))`;
   - profile rows → `touched_profile = True`;
   - LOCAL, SYNC and RUN_LOG rows → ignore.
3. **Guard:** see Task 5. Off until Task 5.
4. **Bump revisions:**
   - one `UPDATE sync_state SET value = value + 1 WHERE name='clock' RETURNING value` per flush,
     inserting the row on first use;
   - set `sync_rev` on each touched job that still exists to that value. Find the `Job` object in
     `session.new` / `session.dirty` by id first (`session.get` does not see a pending job); fall
     back to `session.get` under `no_autoflush` only for ids with no pending object, and treat
     `obj in session.deleted` as deleted (no rev, a tombstone instead);
   - bump `profile_rev` to the same value when the profile was touched;
   - for a deleted `Job`, add `SyncTombstone(job_id, rev)`.

**Tests (with sync OFF, so the hook must not change behavior):**
- Creating a job, adding a skill, an application, a proposal transition, a consent event, a QA
  entry and a filled answer each raises that job's `sync_rev` above its previous value.
- A base resume edit and an `autofill_profile` setting raise `profile_rev` and no job.
- A `sync.*` or `llm.capabilities.*` setting raises nothing.
- Deleting a job leaves a tombstone.
- A flush with nothing modified bumps nothing.
- The full backend suite passes. Measure that the suite's wall time doesn't grow more than about
  5% and note the number in the task report.

**Known Core write:** `template_registry.py:743` (`update(Template)…is_default=False`) bypasses the
hook, so set-default never bumps the profile. Add `hooks.touch_profile(session)` there (and, from
Task 5, `hooks.require_profile_writable(session)`). The other Core writes found at planning
(`autofill.py:184-185`, `autofill_trace.py:186`, `agent_runs.py:35`) are LOCAL/RUN_LOG.

**Also audit Core writes.** `grep -rn "session.execute(update\|delete(\|insert(" backend/app`, and
the `db.execute(` variants. Any bulk Core write to a job-class or profile table bypasses ORM
events. Either convert it to ORM, or call `hooks.touch_job(session, job_id)` /
`hooks.touch_profile(session)` explicitly next to it, and list each site in the task report.

### Task 5: The guard

**Files:**
- Modify: `backend/app/services/sync/hooks.py`.
- Modify: `backend/app/main.py`. Add an exception handler for `NotOwnedHere`: 409 with
  `{"detail": message, "owner": "laptop"|"bot"}`.
- Modify `backend/app/services/proposals.py`: `expire_stale` must filter to owned jobs.
- Modify `backend/app/services/filled_answers.py`: `clear_eeo_answers` must do the same.
- Modify `backend/app/services/template_validation.py` and `template_registry.py` for the
  profile prechecks below; modify the file-writing routers covered by the rule below.
- Test: `backend/tests/sync/test_guard.py`.

**The rule, applied only when `status.enabled()`:**
- **Job rows** of a job whose `owner_machine` is set and isn't this machine's id are refused. On
  home, so are rows of a job with `handover == "offered"`, except a flush whose only change is
  clearing `handover` (that's Keep it here).
- **Unresolved links:** refuse when the CURRENT job cannot be resolved, using
  `NotOwnedHere("Maestro couldn't tell which job this change belongs to, so it wasn't saved.")`.
  An unresolvable previous link does not block a repair; every resolvable current or previous
  job must still be owned here. Clear `sync_touch_*`, `sync_unresolved` and guard state on soft
  rollback and on root `after_transaction_end`, including close-and-reuse.
- **Profile rows on the remote:** UPDATE and DELETE are refused. INSERTs are refused too, except:
  - A `Setting` INSERT made by a lazy first read: `text_settings.get_text` and `prompts.get_prompt`
    set `session.info["setting_seed"] = True` around their add + commit (try/finally), and only
    those INSERTs pass; home's value wins at the next profile apply. Every other `Setting` INSERT
    is refused (a remote `PUT` of a never-seeded setting would otherwise slip through until the next
    apply).
  - Rows written by startup seeding. `seeding.run_startup()` (`seed_base_resumes`, `seed_prompts`,
    `seed_templates`, `ensure_persona`) and the re-seed inside `GET /api/templates`
    (`routers/templates.py:49`) run with `session.info["sync_apply"] = True`, set and cleared
    (try/finally) around the seeding call only, never for the whole request.
    `_bootstrap_default` (`template_registry.py:231`) may then update `is_default`; home's flags
    return at the next apply. The next profile apply upserts over all of it by primary key and
    deletes the rest.
  - `seed_career_kb` is skipped entirely when `status.is_remote()`: its `kb.seeded` gate is a
    local setting and the remote's base resumes are replicas, so it would run the LLM
    consolidation on every boot.
  - A new `KBPoint` with `provenance == "user_cannot_confirm"`, plus the archived "Unconfirmed
    claims" `KBEntity` holder that `_record_cannot_confirm` creates when absent
    (`tailoring_session.py:721`). Add one `SyncRequest(kind="profile_addition",
    payload_json={"claim": text, "holder": {...} or None}, origin="local")` in the same flush; home
    applies it idempotently by claim text, creating the holder if it lacks one.
- **Tailoring on the remote** must not write draft career-history points: `tailor()`'s
  gap-elicitation write-back (`KBPoint` with `origin="gap_elicitation"`,
  `tailoring_session.py:725/781/1090`) is skipped when `status.is_remote()`, and reported in
  `kb_writeback_skips` with reason `profile_owned_elsewhere`. Add that value to the
  `KBWritebackSkip.reason` Literal (`schemas/tailoring_session.py:87`) and its TypeScript mirror
  (`frontend/lib/types.ts:1534`), with a toast sentence: "Your laptop keeps your career history, so
  this wasn't added to it here." Test that a remote tailor completes
  and reports the skip.
- **Message:** `NotOwnedHere("This job is with your bot. Your change will be sent to it at the
  next sync." | "This job is on your laptop. …" | "Your laptop keeps your profile. Change it there.")`.
  Use the first two wordings only where Task 6 converts the write into a request. Elsewhere the
  message says what to do instead, e.g. "Ask for it back with Work on it here." Keep each message
  to one plain sentence.

**Every route with file side effects before its commit** calls `hooks.require_owned(session, job_id)`
first, so a refusal can't leave a half-done change on disk: `PATCH /api/qa/{id}` (deletes the PDF at
`routers/qa.py:151-153` before committing), `DELETE /api/qa/{id}` (deletes files at `qa.py:164`
before its commit), `POST /api/qa/{id}/render`, application render, and proposal evidence upload.
`hooks.require_profile_writable(session)` does the same for profile routes with file side effects:
`POST /api/kb/entities/{entity_id}/documents`, `POST /api/kb/documents/ingest`,
`DELETE /api/kb/documents/{document_id}` and the base
resume routes `POST ""`, `PUT`, `PATCH /{slug}/edits`, `/from-kb`, `/import`, `/duplicate`,
`/render`, plus `resume_versions` restore for kind `base` (`resume_versions.py:122`). The
post-commit `remove_files` sites are already safe: a refused commit raises before them.
Template preview validation checks in the shared `template_validation.validate_template`
helper before compilation, covering HTTP and Assistant callers;
`PUT /api/templates/{template_id}/default-formatting` checks before its preview compile too.
`template_registry.set_default` checks before its Core update and `touch_profile` call.
Audit router file writes/deletes again and guard any other site under applications, base resumes,
KB documents or template previews before its commit.

`NotOwnedHere` subclasses `Exception` directly, not `ValueError` (several routers map `ValueError`
to 400).

**Tests (sync on; mark a job as a replica by setting `owner_machine` to another id):**
- A replica job cannot be written through any of these:
  - `PATCH /api/jobs/{id}`;
  - re-extract, quick tailor, from-base, application edits and render;
  - QA create, PATCH and render;
  - filled answers;
  - `POST /api/ats-scores`, tailoring sessions, resume_versions restore, resume_lint run and waive;
  - proposal evidence and job-site-login share;
  - the Assistant's `tool_edit_resume` on an application of that job.

  Parametrize over the routes listed in the write-paths inventory (design amendments).
- Listing proposals with a stale replica proposal does not raise and does not expire it.
- Changing EEO consent clears answers only on owned jobs.
- On the remote, a base resume edit is refused while a cannot-confirm point (and its holder entity,
  when absent) is accepted and queues one addition.
- A refused QA PATCH on a replica leaves the replica's PDF on disk.
- Refused document deletion, template validation and template formatting preserve their files;
  set-default refuses before its Core update. Document-first ingest checks before its LLM call.
- A version whose previous application was deleted can move to an owned job; a resolvable
  previous replica still blocks the move. Touch, close and reuse carries no hook/guard state.
- A dedicated Core-write audit test scans `backend/app` using registry classifications and
  requires an explicit allowlist with nearby `touch_job`/`touch_profile` calls, exempting
  LOCAL/RUN_LOG/SYNC tables; do not install an autouse execution listener.
- **The remote boots with sync on** (the lifespan's seeding succeeds), and a never-seeded setting
  key reads its default without a 409.
- With sync OFF the same routes all succeed (the parametrized twin).

### Task 6: Requests through the routes the user already uses

**Files:**
- Create: `backend/app/services/sync/requests.py`.
- Modify `backend/app/routers/proposals.py`: PATCH `/{id}` and POST `/bulk-transition`.
- Modify `backend/app/routers/applications.py`: PATCH `/{id}`, for the `status` and `notes` fields only.
- Test: `backend/tests/sync/test_requests_local.py`.

**Before the service call,** if sync is on and the job isn't owned here, `requests.enqueue(...)`
stores `SyncRequest(origin="local", status="pending", kind=…, payload=…)` and returns
`202 {"queued": true, "detail": "Sent at the next sync."}`. The kinds are:
- `proposal_transition{proposal_id, to, reason}`, used for queue (accepted), skip (rejected) and
  the other user transitions;
- `application_patch{application_id, fields}`, with fields limited to `status` and `notes`;
- `take_over{}`, created by Task 13's button.

Any other write on a non-owned job still gets the guard's 409.

**Tests:**
- Each kind is queued, not applied, and the 202 body is as above.
- A field outside the allowlist in the same PATCH gets a 409 and queues nothing.
- With sync off, behavior is unchanged.
- MCP's `transition_proposal`-style tools go through the same routes, so assert one MCP client
  call gets the 202 text through unchanged (mcp_server/tests, fake transport).

---

## Stage 2: Bundles (pure functions over one database; still no network)

### Task 7: Paths and files

**Files:**
- Create: `backend/app/services/sync/files.py`.
- Test: `backend/tests/sync/test_files.py`.

```python
ROOTS = {"applications": lambda: settings.applications_dir,
         "base_resumes": lambda: settings.base_resumes_dir,
         "kb_documents": lambda: settings.kb_documents_dir}

def to_portable(path: str | None) -> str | None:
    """'/app/applications/X/y.pdf' -> 'applications:X/y.pdf'. A path under no root -> None (dropped,
    never sent: it would leak a machine path and point nowhere on the other side)."""

def from_portable(value: str | None) -> str | None:
    """Inverse, joined onto THIS machine's root, refusing '..' and absolute parts."""

def pack_dir(root_name: str, rel_dir: str, *, max_bytes: int) -> list[dict]:
    """[{path: 'applications:X/evidence/a.png', sha256, b64}] for every regular file
    (no symlinks, skip page-preview PNGs, which are regenerated), total under max_bytes or raise."""

def unpack(files: list[dict]) -> None:
    """Write each atomically (mkstemp + fsync + os.replace) under its root, verifying sha256 first."""
```

**Tests:**
- A round trip between two tmp roots.
- `..`, absolute paths, symlinks and a bad sha256 are each refused.
- A path outside every root becomes None.
- A size over the limit raises.

`ROOTS` reads the process-global `settings.*_dir`, so round-trip tests monkeypatch the dirs between
pack and unpack. The per-job default is 25 MB. Evidence is at most 5 MB a file.

### Task 8: Export and apply a job bundle

**Files:**
- Create: `backend/app/services/sync/jobs_bundle.py`.
- Test: `backend/tests/sync/test_jobs_bundle.py`.

**`export_job(db, job_id) -> dict`:**
- the job, its job-class rows and its by_kind application rows, each as
  `{table, row: {col: json-safe value}}` (UUID → hex, datetime → isoformat, JSON as-is);
- path columns made portable: `applications.artifact_dir`, `pdf_path`, `tex_path`,
  `qa_entries.pdf_path` (`evidence_json` paths are already relative);
- `files` = `pack_dir("applications", <artifact dir relative>)`;
- `owner`, `sync_rev` and `handover`.

**`apply_job(db, bundle, *, sender_machine)`**, inside one transaction with
`session.info["sync_apply"] = True`:
- **Upsert** every row by primary key, rewriting path columns with `from_portable`.
- **Delete** this job's subtree rows on the receiver that the bundle doesn't list, including the
  split rows keyed by its applications. These have no FK.
- **Set** `owner_machine = sender_machine`.
- **Write** the files.
- **Tombstones:** `apply_tombstone(db, job_id)` deletes the replica, its subtree and its artifact dir.

**Raw-text duplicates:** a job id that isn't present, whose `raw_text_hash` matches a different
local job, is handled by Task 10's rule. Here, raise `DuplicateJob(local_id)`.

**Tests:**
- (Row comparisons below exclude `sync_rev`, `owner_machine` and `handover`: the receiver restamps them.)
- Export then apply into a second, empty schema (a second SQLite file through `make_engine` and its
  own `sessionmaker`; models are shared, so this works in-process) gives row-for-row equality,
  except the rewritten paths.
- Re-applying the same bundle changes nothing (idempotent).
- A row removed at the sender is removed at the receiver.
- A referral that the receiver lacks is set to NULL, not failed. Profile replicas come first in
  real rounds, but test the gap.
- Files arrive and their paths resolve.
- `DuplicateJob` is raised on a hash clash.

### Task 9: Export and apply the profile bundle

**Files:**
- Create: `backend/app/services/sync/profile_bundle.py`.
- Test: `backend/tests/sync/test_profile_bundle.py`.

**`export_profile(db) -> dict`** contains:
- all profile rows, with paths made portable (`base_resumes.pdf_path`, `tex_path`,
  `kb_documents.file_path`);
- settings rows, except local prefixes;
- `files`: `base_resumes/*.json` (the content source: `load_base_resume` reads the file, not
  `data_json`), base resume PDFs and TeX, and kb document files;
- `job_site_login`: `job_site_login.read()` or None (the service has `read()`, `write(email,
  password)` and `clear()`). This is a secret, so it only ever travels in
  this bundle;
- `profile_rev`.

Check `templates` storage: if template content lives in files, add its root to `ROOTS`.

**`apply_profile(db, bundle)`**, remote only, under `sync_apply`:
- upsert and delete-missing for the profile tables;
- settings with a file mirror go through their service's `set` (the `JsonSetting` instances and
  `text_settings`), so the mirror files stay in step;
- write the files;
- `job_site_login.write(email, password)` or `.clear()`;
- never touch local-prefixed settings.

**Tests** (monkeypatch `settings_dir` and the file roots between export and apply; mirrors and
roots are process-global):
- A round trip into a second schema.
- A setting's mirror file is rewritten.
- The base resume JSON file arrives, and `load_base_resume` returns the new content.
- Local keys survive on the receiver.
- The login file arrives with mode 0600 and the bundle is never logged. Use a caplog assertion
  with a sentinel password.

---

## Stage 3: The channel and the round

### Task 10: Home's sync endpoints

**Files:**
- Create: `backend/app/routers/sync.py`, mounted always, but every route 404s unless `status.enabled()`.
- Test: `backend/tests/sync/test_home_endpoints.py`.

**Common dependency (`_require_sync`), in this order:**
1. 404 when sync is off.
2. 403 when an `Origin` header is present. This check happens before anything else is read.
3. 401 unless `Authorization: Bearer <key>` passes `compare_digest`.
4. On home, refuse (409) a request from a remote whose protocol or schema differs. Every request
   carries `X-Maestro-Sync: <protocol>:<schema_revision>:<machine_id>`.
5. A module-level `threading.Lock` acquired non-blocking (single-flight). Busy → 409 "A sync is
   already running."

Cap every request body at 100 MB before parsing (413 with a fixed sentence; read the stream with
a running count, don't trust Content-Length alone), and pass `max_bytes` to `files.unpack` for the
sum of a request's files (Task 7 review).

An `OSError` from `apply_job` → `files.unpack` (disk full, permissions) carries a local path and may
leave earlier files of that bundle on disk: map it to a fixed 500 sentence ("Maestro couldn't save
the files it received.") and never put `str(exc)` in a response or a log line (Task 7 review).

Give the router a sanitized validation error, like `_JobSiteLoginRoute` (`routers/settings.py:146`):
FastAPI's default 422 echoes the request `input`, which here would be bundle contents.

**Routes (home):**
- `GET /api/sync/hello` → `{protocol, schema_revision, machine_id, profile_rev}`.
- `GET /api/sync/profile?since=N` → `{unchanged: true}` or the profile bundle.
- `GET /api/sync/jobs?since=N&limit=20` → `{bundles: [...], tombstones: [...], next_since, more}`.
  Jobs owned here with `sync_rev > since`, ordered by `sync_rev`.
- `POST /api/sync/jobs` with `{bundles, tombstones}` from the remote → apply each as a replica
  owned by the sender. Returns `{applied: [ids], duplicates: [{job_id, kept: "laptop"|"both", local_id}]}`.
  **Duplicate rule (design Part A):** if the remote's job has no proposal past `pending_review` and
  no application, answer `kept: "laptop"` and store nothing; the remote then drops its job
  (Task 11). Otherwise store the replica with
  `raw_text_hash = sha256("replica:" + job_id)` and answer `kept: "both"`.
  `apply_job` raises `DuplicateJob` again on every later re-apply of a kept-both replica (the hash
  column is unique), so rewrite the bundle's hash the same way before every apply of a job already
  stored with a rewritten hash (Task 8 review).
- `POST /api/sync/ownership` with `{job_ids}` → `{job_id: owner_label}` for reconcile, where
  owner_label is "home", "remote" or "gone".
- `GET /api/sync/requests` → home's `origin="local"` pending requests for jobs the remote owns.
  Mark them `sent`.
- `POST /api/sync/requests` with the remote's pending requests:
  - **Profile additions:** apply idempotently by claim text.
  - **Job requests:** apply through the normal service functions (`proposals.transition`, the
    application status and notes update) under the normal rules.
  - **Returns** `[{id, status: applied|refused, reason}]`.
  - **Applying an application status change** has no service function today: applied_at stamping,
    `link_unlinked` and closing open proposals with `APPLIED_MANUALLY` live inside the
    `PATCH /api/applications/{id}` route (`routers/applications.py:356-405`). Extract them into one
    service function both the route and the applier call (Task 6 review).
  - **Order:** apply requests in `created_at` order (pending requests are merged per target before
    they're sent, so the last decision wins).
- `POST /api/sync/request-results` → mark home's sent requests `applied` or `refused`.
- `GET /api/sync/handover/offers` → bundles of home jobs with `handover == "offered"`.
- `POST /api/sync/handover/commit` with `{job_ids}` → for each still `offered`, set
  `owner_machine = remote id` and `handover = None` (bump rev). Return the committed ids.
- `POST /api/sync/handover/return` with `{bundles}` → apply each as owned here
  (`owner_machine = None`). Return the ids.
- `POST /api/sync/runs` with `{runs}` → upsert `agent_runs` by id with `machine = remote id`.
  Add-only per round: never delete. Home's normal `agent_runs` retention still prunes old rows,
  remote ones included; that's intended.

**Tests:** one per route, plus all of these:
- the 404 with sync off;
- the Origin 403, checked before the key;
- the 401 with a wrong key, without the key or the body echoed;
- the version 409;
- the busy 409;
- no log line containing a body. Use caplog with a sentinel inside a bundle.

### Task 11: The round (remote side)

**Files:**
- Create: `backend/app/services/sync/round.py`.
- Modify: `backend/app/routers/sync.py`. Add `POST /api/sync/round`. It is remote only, refuses an
  Origin header, and needs no key (its own loopback).
- Modify: `backend/app/services/sync/status.py`. Add round state in the setting `sync.state`
  (local): `{paired, last_ok, last_error, failures, next_attempt_at, since_home, acked_own,
  profile_rev}`.
- Test: `backend/tests/sync/test_round.py`. Home is a hand-written fake behind an
  `httpx.MockTransport`: it calls the `jobs_bundle` / `profile_bundle` functions against a second
  session on a second SQLite file, never the FastAPI app (whose `get_db`, `status.enabled()`,
  `is_remote()` and module lock are process-global). Task 12 tests the real thing.

**`run_round(db, *, force=False, pair=False, accept_profile_overwrite=False) -> dict`:**

1. **Backoff:** unless `force` (`sync_now` passes it), skip when `now < next_attempt_at` and
   return `{skipped: "Laptop unreachable; next try at …"}`.
2. **Hello:** a protocol or schema mismatch stops the round, reported as "Update Maestro on both
   machines to the same version." Nothing is changed.
3. **Pairing:** when not yet paired, see Task 12.
4. **Reconcile ownership** of every local job whose `owner_machine` is home's id or
   `handover == "returning"`:
   - "remote" → own it;
   - "home" with `returning` → become a replica;
   - "gone" → delete the replica.
5. **Profile:** `GET profile?since=profile_rev`, then `apply_profile` if it changed.
6. **Push own jobs:** owned here with `sync_rev > acked_own`, in pages, then `POST jobs`. On
   `kept: "laptop"` duplicates, delete the local job and its files. `acked_own` becomes the highest
   local `sync_rev` among the bundles pushed, read before the POST, and is saved only after a 2xx.
7. **Pull home jobs** (a `DuplicateJob` on pull — a home job whose hash matches a remote-owned
   job — follows the same rule from the remote's side: the laptop's job wins unless the remote's has
   progressed, then keep both with the replica's hash rewritten; a job too large to export or apply
   (over 25 MB) is skipped with a counted reason and never stops the round; Task 8 review): `GET jobs?since=since_home` in pages, then `apply_job` as replicas, then
   advance `since_home`.
8. **Requests both ways** (Task 6 review: a local pending request for a job that became owned here,
   e.g. after a take-over, is applied locally instead of sent; a request on a job the laptop has
   offered is refused by its guard in this step and the handover then completes in step 9, so the
   refusal reason says the job moved to the bot and the user can repeat the change there): `GET requests` → apply locally → `POST request-results`.
   Then local pending → `POST requests` → store results.
9. **Handovers:**
   - **Offers:** `GET offers` → `apply_job` (still home's) → `POST commit` → own the committed jobs.
   - **Returns:** for each own job with a `take_over` request applied in step 8, check that it
     isn't mid-application. ("Mid-application" is a proposal in `approved` or `submission_uncertain`;
     `autofill_runs` holds finished traces only, so there is no "unfinished run" to check.) Then set
     `handover = "returning"`, `POST return` with its bundle, and become a
     replica on success. Busy → refuse the request with "Your bot is applying to this one; try
     again after its run."
10. **Runs:** `POST runs` with run rows since the last push.
11. **State:** on success, `failures = 0` and `next_attempt_at = None`. On a connection error,
    `failures += 1` and
    `next_attempt_at = now + min(30, 5 * 2 ** (failures - 1))` minutes. Return a per-step summary
    of counts. It never includes contents. A local `OSError` from `apply_job` in steps 7 and 9 is
    stored the same way as a connection error, as a fixed sentence (Task 7 review). `last_error` is a status code plus a fixed sentence,
    never a response body (a 422 body would carry bundle contents into a setting).

Each step commits on its own. A failed step stops the round, and the next round resumes.

**Tests:**
- A full happy round.
- The second round sends nothing.
- A failure in step 7 leaves step 6's ack advanced and step 7's not.
- Backoff timing (5, 10, 20, 30, 30).
- `force` ignores backoff.
- Version-mismatch skip.
- Both duplicate outcomes.
- An offer then commit, then a crash before the local flip, healed by the next round's reconcile.
- A return refused while approved; a return granted.

### Task 12: Real two-process tests and pairing

**Files:**
- Modify: `backend/tests/sync/conftest.py` (from Task 1). Add the fixture `home_backend` (module scope):
  - temp `DATA_DIR`, `SETTINGS_DIR`, `APPLICATIONS_DIR`, `BASE_RESUMES_DIR` and `KB_DOCUMENTS_DIR`;
  - a key file and `DATABASE_URL` pointing at the home file. **Pop `TEST_DATABASE_URL`** from the
    subprocess env and from the `alembic upgrade head` env: `tests/conftest.py` sets it and
    `app/db.py` prefers it, so the subprocess would otherwise open the test worker's database;
  - `alembic upgrade head`, then `uvicorn app.main:app --port <free>` as a subprocess, waiting on
    `/health`;
  - teardown kills it.

  Reuse what `tests/test_native_scripts.py`'s slow lifecycle test does. The in-process app plays
  the remote: patch `settings.sync_remote_url` and the key.
- Pairing goes in `round.py`.
- Create: `backend/tests/sync/test_two_machines.py`.

**Pairing (first round, `pair=True` required):**
- Compare the remote's profile rows with home's (per-row hashes).
- Differences other than cannot-confirm additions → refuse with the list of table names and keys,
  never values, unless `accept_profile_overwrite`.
- Job ids on both sides → home's (the remote's copy becomes a replica at step 7).
- Base resumes only the remote has (seeds or pre-pairing rows) are deleted by the first profile
  apply; list them by slug in the refusal, and list remote-owned applications built from them (their
  rebuild and Q&A routes will answer "Unknown base resume" afterwards; Task 9 review).
- Remote-only jobs → stay the remote's.
- Then set `paired`.

**Tests against the real home process:**
- Pairing refuses on a profile difference and passes with the flag.
- A remote-found job appears on home as a replica, and home's PATCH on it returns the 202 request.
- The request is applied on the remote next round, and home sees the result.
- A home job queued with full automation on is offered, committed and owned by the remote.
  "Keep it here" before the round cancels it.
- "Work on it here" returns a job.
- A deleted job is deleted on the other side.
- Files arrive and render: GET the application PDF on home.
- The daily cap counts both sides' reserved slots. Reserve one on each side and read `cap_status`
  after a round.
- A wrong key is a 401, and the remote reports "Sync key doesn't match".
- Killing home mid-round leaves both databases consistent, and the next round finishes.

These run in CI on purpose, not marked `slow`: they download nothing, and they are the contract.
Record that exception next to the `slow` convention in SYSTEM.md (Task 16). Keep the module to one
home process and under ~60 s.

---

## Stage 4: The user-facing pieces

### Task 13: Ownership in the API and the marks in the web app

**Files:**
- Backend: add `ownership: {owned_here: bool, owner: "laptop"|"bot"|null, handover: str|null,
  pending_requests: int}` to the job list and detail schemas (`schemas/job.py`,
  `schemas/job_detail.py`). Add `POST /api/jobs/{id}/keep-here` (home, clears `offered`) and
  `POST /api/jobs/{id}/work-here` (home, enqueues `take_over` on a remote-owned job). The labels
  are relative to the viewer: on home, a remote job is "bot".
- Frontend: job cards and the job detail header show a small mark: "With your bot" / "On your
  laptop", "Going to your bot" with a **Keep it here** button, or **Work on it here**. Controls that
  write are disabled on a non-owned job with one line naming the owner. Actions that became
  requests show "Sent at the next sync". Follow the design system in `docs/design-system`.
- Recent runs: the remote's runs show "on your bot", and refused requests show with their reason.
- Tests: schema fields over HTTP, each button's route, frontend parity tests, and a browser check
  with a seeded replica, an offered job and a pending request. Desktop widths only.

### Task 14: MCP

**Files:** `backend/mcp_server/server.py`, `client.py`, `profiles.py`, and the tool-count places
listed in the preferences plan's Task 8.

- `sync_now()` → `POST /api/sync/round {force: true}`. It returns the round summary, or "Sync isn't
  set up" / "This is your laptop's copy; your bot runs the sync" when called on home. Annotate it
  `_write("Sync Now", destructive=False, idempotent=True, open_world=True)`. Add it to the
  hunt and apply profiles.
- `get_job` and `list_jobs` pass `ownership` through, so an agent can tell a replica apart.
- `apply-auto` and `apply-session` SKILL.md:
  - "Call `sync_now` at the start and end of a run when the brief's `sync.enabled` is true."
  - "Only work jobs whose `ownership.owned_here` is true."

  Add `sync: {enabled, role}` to the brief, declared in its schema and tested over HTTP. Pin the
  sentences in `test_automations_service.py`.

### Task 15: Native scripts, setup and the tunnel

**Files:**
- Create: `backend/scripts/native/sync.sh`. It loads the env like `start.sh`, then
  `native_get`-style POSTs `/api/sync/round` to the local backend and prints the summary.
  - `--pair [--accept-profile-overwrite]` passes through.
  - It exits 0 on success, on a skip and on backoff, and exits 1 on any other failure.
  - It declines while the maintenance marker exists, like `start.sh --watchdog`.
- Create a key CLI: `backend/scripts/sync_key.py`, run as `python -m scripts.sync_key create|show|path`:
  - `create` writes the key and prints only its path;
  - `show` prints the key, for the user's own terminal, to copy into their vault once. Say so in
    its help text.
  - For Docker: `docker compose exec backend python -m scripts.sync_key create`.
- Modify `backend/scripts/native/common.sh`: export `SYNC_KEY_FILE` when `$MAESTRO_HOME/sync-key`
  exists. Setup writes no key.
- Modify `backend/scripts/native/maestro.env.example`: `SYNC_REMOTE_URL=http://127.0.0.1:8101` (commented), with the
  key-file note.
- Tests: extend `tests/test_native_scripts.py` with the fake-uvicorn style:
  - `sync.sh` POSTs the round, passes `--pair` through and declines while paused;
  - shellcheck-clean (CI shellcheck job: add `backend/scripts/native/*.sh` if it's not in the glob).

### Task 16: Docs and invariants

**Files:**
- Create: `docs/sync-setup.md`. The setup guide, with one worked example of an always-on agent VM
  with a cron watchdog and a vault. No product names. It covers:
  - the laptop: Remote Login, a restricted `authorized_keys` line
    (`restrict,port-forwarding,permitopen="127.0.0.1:8001" ssh-ed25519 …`), Tailscale, and
    `sync_key create`;
  - the always-on machine: the vault → `$MAESTRO_HOME/sync-key`, `SYNC_REMOTE_URL`, and the tunnel
    (`ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 127.0.0.1:8101:127.0.0.1:8001 laptop`,
    kept up by the watchdog);
  - cron lines: `*/5 sync.sh`, and the watchdog lines;
  - first pairing;
  - what "With your bot" means;
  - backups with Litestream to a synced folder;
  - troubleshooting: version mismatch, wrong key, a laptop asleep for days.
- Modify `docs/native-install.md`: a pointer to the guide.
- Modify `SECURITY.md` and `PRIVACY.md`. The always-on copy holds a read-only copy of the profile,
  including the AI key and the job-site login, carried only inside the SSH channel and never logged.
- Modify `SYSTEM.md`. Add §6 invariants for one-writer ownership, the guard, and the sync
  channel's refusals. Pin them in `.system_md_enforcement.json` to `tests/sync/test_guard.py` and
  `test_home_endpoints.py`, and trim to stay at 1000 lines (`python3 scripts/check_system_md.py`).
- Modify `CHANGELOG.md` and `docs/entities/job.md` (the three new columns).

### Task 17: Final verification

1. **Tests:** run the full backend suite twice, once as-is (sync off) and once with
   `tests/sync/` only.
2. **Lint and checks:** ruff; the slop ratchet for backend and frontend (name both);
   `check_system_md`; `check_mcpb_bundle`; frontend `tsc` and `build`.
3. **A real two-machine rehearsal** in Docker, as the pilot did:
   - two `python:3.12-slim` containers;
   - home native-installed, remote native-installed with `SYNC_REMOTE_URL`;
   - an `ssh -L` tunnel between them;
   - run pairing, a remote hunt-save, a round, home PATCH → request → round, an offer and commit,
     and a return;
   - kill the tunnel mid-round, then confirm the backoff and the recovery.
4. **Review:** Opus final review of the whole diff, with a security pass on `routers/sync.py`,
   `files.py` and the guard.
