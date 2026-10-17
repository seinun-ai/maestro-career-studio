# Career history stale wording Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (a fresh Opus 5.5
> subagent per task, review between tasks: the owner's routing rule) or superpowers:executing-plans
> (one session, checkpoints) to implement this plan task-by-task. Every task is TDD: the failing test
> first, then the smallest code that passes it, then a commit.

Design: `docs/plans/2026-10-17-career-history-stale-wording-design.md` (owner-approved 2026-10-17).
Read it in full before Task 1; its "Owner decisions" and "Principles" are not reopened here.

## Where this plan departs from the design

Nothing in the behaviour departs. Four mechanics are decided here because the design left them to
the plan; each is named so a reviewer can object before code lands.

1. **Frontend tests run on pure modules, as the design asks; the component wiring is pinned by
   source tests.** `node --test` has no DOM, so the inbox, groom and drift decisions move into three
   small pure modules (`frontend/lib/kb-replaces.ts`, `kb-groom.ts`, `kb-drift.ts`) that the design's
   frontend tests exercise directly. That the components call them is pinned the way
   `backend/tests/test_kb_sync_frontend.py` already pins the sync pill: by reading the source.
2. **The "Approve all shown" confirm becomes a local dialog in `inbox-panel.tsx`.** `useConfirm`
   resolves to a boolean and has no slot for the design's checkbox. A small `Dialog` with a
   `Checkbox` inside the panel keeps the confirm's focus rules and adds the one control.
3. **Embedder failure is a per-item flag folded by `classify`.** `_best_cosine` returns a third
   value, `compared`, `SyncItem` carries it, and `classify` reports `compared_wording = all(...)`.
   Nothing module-global: the route runs in threads.
4. **`usage_count` on a replaced bullet counts distinct resumes from `kb_port_log` rows whose
   `direction` is not `from_source`** (placements, as the points list's "On N resumes" chip counts
   them). The design names the number and not the query.

One process note: the design commit lived on branch `claude/loving-bose-f09764`; it was cherry-picked
onto this branch (`12057bc7`) so the plan and design travel together.

## Goal Card

**Goal:** Base-resume sync into career history stops piling up a second bullet for every rewrite, and
the user gets a deterministic way to shrink the pile that is already there, without any LLM call,
without anything retired or rewritten silently, and without touching a bullet's provenance.

**Principles** (how to decide when the plan is ambiguous or wrong):
- Zero LLM calls in sync and groom. `services/ats/embeddings` is the only comparison seam.
- Nothing applied silently: sync links, the user retires; groom proposes, the user retires; adoption
  of a resume's wording is one click.
- `KBPoint.provenance` is never read to decide and never written (`inv-provenance-no-decay`).
- Retiring never edits a resume; the copy says so wherever a retire is offered.
- When the embedder is unavailable, say so; never read as "all new" or "nothing similar".

**Non-goals:** the tailoring write-back's dedup, a KB-wide groom count, near-identity fixes for
dash variants (all listed as follow-ups in the design).

**Autonomy:** peer (adapt-and-advise). Opus 5.5 may adapt *how* when the plan meets repo reality
it did not foresee, logs every deviation in the commit body with a one-line reason, and raises
anything touching scope, a wire shape another task depends on, or a Goal Card line as a deviation
note before building it. Scope is never self-expanded.

---

**Goal:** Build the design's eight steps: the schema, the sync rung, the inbox's retire-on-approve,
the read-only groom service with its endpoints and dialog, the actionable drift popover, two MCP
tools, and the docs.

**Architecture:** One Alembic revision adds `kb_points.replaces_point_id` (self-referencing, SET
NULL) and `kb_point_kept_pairs`. `kb_base_sync._ladder_bullet` gains one rung between drift and new
that sets the link on the `SyncItem`, and `_apply_new` copies it onto the draft. `PATCH
/api/kb/points/{id}` and `POST /api/kb/points/bulk-state` honour `retire_replaced`. A new
`services/kb_groom.py` embeds an item's active bullets once, clusters single-link components at
0.80 minus kept pairs, proposes a keeper and returns a `GroomReport`; three routes expose it and the
kept pairs. The web gets a Replaces block in the draft inbox, a Tidy bullets dialog on the entity
page, and a popover behind the Drifted badge. MCP gets `kb_groom_entity` (read) and
`kb_retire_points` (write, the twin of `kb_approve_points`).

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic (SQLite only, `app/models/types.py` for column
types), pydantic v2, fastembed through `services/ats/embeddings` (memoized, out-of-process on small
machines), Next.js 16 with Base UI primitives under `frontend/components/ui`, TanStack Query,
sonner toasts, FastMCP tools in `backend/mcp_server`.

---

## Setup and commands

Run everything from the worktree. Never verify against the compose stack or the live uv install.

```bash
# backend venv from the lock (about a minute); `uv` is at ~/.langflow/uv/uv
cd backend && ~/.langflow/uv/uv venv -p 3.12 .venv && VIRTUAL_ENV=.venv ~/.langflow/uv/uv pip install -r requirements.lock && VIRTUAL_ENV=.venv ~/.langflow/uv/uv pip install -e ".[dev,mcp]"
```

```bash
# one backend test file while building a task
cd backend && .venv/bin/python -m pytest tests/test_kb_groom.py -q
```

```bash
# the backend suite, always with xdist (owner rule); run before every commit that touches backend/
cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile
```

```bash
# frontend gates; a worktree has no node_modules, so `npm ci` once
cd frontend && npm ci && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint
```

```bash
# the SYSTEM.md gate (docs task) and the slop ratchet per surface touched
python3 scripts/check_system_md.py && python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend && python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend
```

Commit message style follows `git log`: `feat(kb): …`, `test(kb): …`, `docs: …`, lowercase clause
after the colon, body in prose, and the attribution line the session's reminder gives.

## Rules that do not move (restate them in every builder prompt)

- **Sync and groom make zero LLM calls.** `app.services.llm.call_openai` is monkeypatched to raise
  in the pins; keep it that way.
- **Nothing touches `KBPoint.provenance`.** No read of it to decide (except excluding
  `user_cannot_confirm` from candidates, which the design allows), no write of it anywhere.
- **Nothing is applied silently.** Sync writes a link on a draft and retires nothing. Groom returns
  a report and writes nothing. Every retire and every adoption is a user gesture or an agent call
  the user said yes to.
- **Retiring never edits a resume.** Resumes that used the old bullet keep their text.
- **`SYNC_REPLACES_COSINE = 0.80` is one constant in `kb_base_sync`**, imported by groom. Drift
  stays `SYNC_DRIFT_COSINE = 0.90`.
- **Public repo:** fixtures use made-up names (Acme, Orbit). Never a real employer or person.
- **Frontend copy:** the word is **bullet**, resumes are named through `useResumeKeyLabel` /
  `useBaseResumeLabel`, retire reads "Won't be offered again" only in the points list where it
  already lives; the inbox says "Retire the old bullet".
- **Tests pin wire shapes and behaviour, not implementation**; existing tests in the four files the
  design names must pass unchanged unless a task says which assertion moves and why.

## The hermetic embedder in tests

`backend/tests/conftest.py` patches `app.services.ats.embeddings.embed_texts` with a fake whose
known strings have hand-built vectors (`tests/ats/fixtures.py`); nothing there scores in the
0.80 to 0.90 band. The sync and groom tests therefore install their own table of unit vectors
through the same seam. `kb_base_sync._best_cosine` imports `embed_texts` from the module at call
time, so a per-test `monkeypatch.setattr(embeddings, "embed_texts", fake)` wins over the autouse
fixture. Vectors are 3-D: a unit vector at cosine `c` to `(1, 0, 0)` is `(c, sqrt(1 - c*c), 0)`,
and a text unrelated to everything sits on the third axis, `(0, 0, 1)`, so it scores 0 against
all of them (two vectors in the same plane are never "far" from each other: `(0.85, 0.53, 0)`
against `(0.79, 0.61, 0)` is 0.99).

| cosine wanted to `(1, 0, 0)` | vector |
|---|---|
| 1.00 | `(1.0, 0.0, 0.0)` |
| 0.92 | `(0.92, 0.39192, 0.0)` |
| 0.85 | `(0.85, 0.52678, 0.0)` |
| 0.79 | `(0.79, 0.61311, 0.0)` |
| unrelated | `(0.0, 0.0, 1.0)` |

Do not test the exact 0.90 boundary with vectors: the fake's norm is off by about 1e-7 and the
comparison is `>=`, so 0.90 lands on either side by machine. The constants' values are pinned
by equality; drift is tested at 0.92.

Add this helper to `backend/tests/test_kb_base_sync_classify.py` (Task 2) and import it from the
groom tests (Task 6):

```python
def _vectors(monkeypatch, table: dict[str, tuple[float, ...]]):
    """Fixed unit vectors by text; any text outside the table is a test bug."""
    from app.services.ats import embeddings

    def fake(texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in table]
        assert not missing, f"no vector for {missing!r}"
        return [list(table[t]) for t in texts]

    monkeypatch.setattr(embeddings, "embed_texts", fake)


def _embedder_down(monkeypatch):
    from app.services.ats import embeddings

    def boom(texts: list[str]):
        raise RuntimeError("embeddings failed\nno model")

    monkeypatch.setattr(embeddings, "embed_texts", boom)
```

---

### Task 1: Migration and models

**Files:**
- Create: `backend/migrations/versions/<rev>_kb_points_replaces_and_kept_pairs.py`
- Modify: `backend/app/models/career_kb.py` (KBPoint, new `KBPointKeptPair`, `kept_pair_key`)
- Modify: `backend/app/models/__init__.py` (register `KBPointKeptPair`)
- Test: `backend/tests/test_career_kb_models.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_career_kb_models.py`:

```python
import pytest

from app.models.career_kb import KBPointKeptPair, kept_pair_key


def _two_points(db_session, state_a="approved", state_b="draft"):
    entity = KBEntity(kind="project", title="Orbit")
    db_session.add(entity)
    db_session.flush()
    a = KBPoint(entity_id=entity.id, text="old wording", state=state_a, origin="manual")
    db_session.add(a)
    db_session.flush()
    b = KBPoint(entity_id=entity.id, text="new wording", state=state_b, origin="base_sync")
    db_session.add(b)
    db_session.flush()
    return entity, a, b


def test_point_replaces_link_round_trips_and_nulls_when_the_target_goes(db_session):
    _entity, old, new = _two_points(db_session)
    new.replaces_point_id = old.id
    db_session.commit()
    assert db_session.get(KBPoint, new.id).replaces.text == "old wording"

    db_session.delete(old)
    db_session.commit()
    db_session.expire_all()
    survivor = db_session.get(KBPoint, new.id)
    assert survivor is not None
    assert survivor.replaces_point_id is None
    assert survivor.replaces is None


def test_kept_pair_key_is_canonical_and_rejects_a_self_pair(db_session):
    _entity, a, b = _two_points(db_session)
    assert kept_pair_key(a.id, b.id) == kept_pair_key(b.id, a.id)
    assert kept_pair_key(a.id, b.id)[0] < kept_pair_key(a.id, b.id)[1]
    with pytest.raises(ValueError):
        kept_pair_key(a.id, a.id)


def test_kept_pairs_cascade_with_either_point(db_session):
    _entity, a, b = _two_points(db_session)
    lo, hi = kept_pair_key(a.id, b.id)
    db_session.add(KBPointKeptPair(point_a_id=lo, point_b_id=hi))
    db_session.commit()
    assert db_session.query(KBPointKeptPair).count() == 1
    db_session.delete(a)
    db_session.commit()
    assert db_session.query(KBPointKeptPair).count() == 0
```

**Step 2: Run them to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_career_kb_models.py -q`
Expected: FAIL, `ImportError: cannot import name 'KBPointKeptPair'`.

**Step 3: Model changes**

In `backend/app/models/career_kb.py`, inside `KBPoint` after `source_document_id`:

```python
    # The bullet this one rewrites. Set only by base sync, when the best
    # same-item match scores in the replaces band (0.80 to under 0.90; the
    # constant lives in services/kb_base_sync). SET NULL when the target is
    # deleted; the router nulls it when the draft moves to another item. One
    # direction only: the old bullet never lists its replacements.
    replaces_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("kb_points.id", ondelete="SET NULL"), index=True
    )
```

and after `entity: Mapped[KBEntity] = relationship(back_populates="points")`:

```python
    replaces: Mapped["KBPoint | None"] = relationship(
        "KBPoint", remote_side=[id], foreign_keys=[replaces_point_id]
    )
```

Add after `KBPortLog`:

```python
class KBPointKeptPair(Base):
    """'Not the same': two bullets groom stops pairing. Stored once per pair,
    with point_a_id < point_b_id (see kept_pair_key); both columns cascade
    with their point, so a deleted bullet takes its kept pairs with it."""

    __tablename__ = "kb_point_kept_pairs"

    point_a_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("kb_points.id", ondelete="CASCADE"), primary_key=True
    )
    point_b_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("kb_points.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )


def kept_pair_key(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """The one stored order of a pair: lower id first. A point is never kept
    apart from itself."""
    if a == b:
        raise ValueError("a kept pair needs two different points")
    return (a, b) if a < b else (b, a)
```

In `backend/app/models/__init__.py` add `KBPointKeptPair` to the `career_kb` import and to
`__all__` (alphabetical, beside `KBPoint`). `tests/test_db_portability.py::test_every_model_module_is_registered`
only checks the module import line, but `test_migration_model_parity` needs the table in
`Base.metadata`, which the import gives.

**Step 4: The migration**

Generate the id and check the head first:

```bash
cd backend && .venv/bin/python -c "import uuid; print(uuid.uuid4().hex[:12])" && .venv/bin/python -m alembic heads
```

Expected head today: `e5a1c2d77b04` (re-read it; another branch may have landed). Create
`backend/migrations/versions/<rev>_kb_points_replaces_and_kept_pairs.py`:

```python
"""kb_points.replaces_point_id and kb_point_kept_pairs

The link base sync writes from a rewrite draft to the bullet it rewrites, and the
pairs the user marked "Not the same" so groom stops proposing them. Impl types only
(sa.Uuid / sa.DateTime), like the baseline: a revision never imports app code.

Adding a foreign key makes batch mode recreate kb_points (SQLite's move-and-copy).
migrations/env.py runs with foreign_keys OFF on purpose, so dropping the old table
fires no CASCADE into kb_port_log. Never run this chain through app.db.make_engine.

Revision ID: <rev>
Revises: e5a1c2d77b04
"""
from alembic import op
import sqlalchemy as sa

revision = "<rev>"
down_revision = "e5a1c2d77b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kb_points", schema=None) as batch_op:
        batch_op.add_column(sa.Column("replaces_point_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_kb_points_replaces_point_id",
            "kb_points",
            ["replaces_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_kb_points_replaces_point_id", ["replaces_point_id"], unique=False)
    op.create_table(
        "kb_point_kept_pairs",
        sa.Column("point_a_id", sa.Uuid(), nullable=False),
        sa.Column("point_b_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.ForeignKeyConstraint(["point_a_id"], ["kb_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["point_b_id"], ["kb_points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("point_a_id", "point_b_id"),
    )


def downgrade() -> None:
    op.drop_table("kb_point_kept_pairs")
    with op.batch_alter_table("kb_points", schema=None) as batch_op:
        batch_op.drop_index("ix_kb_points_replaces_point_id")
        batch_op.drop_constraint("fk_kb_points_replaces_point_id", type_="foreignkey")
        batch_op.drop_column("replaces_point_id")
```

**Step 5: Run the model, parity and portability tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_career_kb_models.py tests/test_migration_model_parity.py tests/test_db_portability.py -q`
Expected: PASS. If parity reports an `add_fk`/`remove_fk` pair for `kb_points`, name the model's
foreign key to match (`ForeignKey("kb_points.id", ondelete="SET NULL", name="fk_kb_points_replaces_point_id")`)
and log that in the commit body.

**Step 6: Commit**

```bash
git add backend/migrations/versions/*_kb_points_replaces_and_kept_pairs.py backend/app/models/career_kb.py backend/app/models/__init__.py backend/tests/test_career_kb_models.py
git commit -m "feat(kb): a bullet can name the bullet it replaces; kept pairs table"
```

---

### Task 2: The sync rung

**Files:**
- Modify: `backend/app/services/kb_base_sync.py`
- Modify: `backend/app/schemas/kb_sync.py`
- Modify: `backend/app/routers/base_resumes.py:939-971` (`kb_sync_status`, `kb_sync_apply`)
- Test: `backend/tests/test_kb_base_sync_classify.py`, `backend/tests/test_kb_base_sync_apply.py`,
  `backend/tests/test_kb_sync_router.py`

**Step 1: Write the failing classify tests**

Add `_vectors` and `_embedder_down` (from "The hermetic embedder in tests" above) to
`backend/tests/test_kb_base_sync_classify.py`, then these tests. `_exp_entity` seeds one approved
point; the helper below adds a second point in any state or provenance.

```python
def _point(db_session, entity, text, *, state="approved", provenance="user_authored"):
    point = KBPoint(
        entity_id=entity.id, text=text, state=state, origin="manual", provenance=provenance
    )
    db_session.add(point)
    db_session.flush()
    return point


OLD = "Built the ingestion pipeline"
REWRITE = "Built and ran the ingestion pipeline for finance"      # 0.85 to OLD: the band
UNDER = "Built the ingestion pipeline and its dashboards"        # 0.79 to OLD: just under
DRIFT = "Built the ingestion pipelines"                          # 0.92 to OLD: drift
FAR = "Negotiated a net-new vendor contract"                     # unrelated to all

BAND = {
    OLD: (1.0, 0.0, 0.0),
    REWRITE: (0.85, 0.52678, 0.0),
    UNDER: (0.79, 0.61311, 0.0),
    DRIFT: (0.92, 0.39192, 0.0),
    FAR: (0.0, 0.0, 1.0),
}


def test_the_two_bands_are_the_designed_constants():
    assert kb_base_sync.SYNC_DRIFT_COSINE == 0.90
    assert kb_base_sync.SYNC_REPLACES_COSINE == 0.80
    assert kb_base_sync.SYNC_REPLACES_COSINE < kb_base_sync.SYNC_DRIFT_COSINE


def _one_bullet(bullet):
    return _resume(
        experience=[{"company": "Acme", "role": "Engineer", "start_date": "2021", "bullets": [bullet]}]
    )


def _classified(db_session, tmp_path, monkeypatch, bullet):
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(bullet))
    report = kb_base_sync.classify(db_session, "hybrid")
    (item,) = [i for i in report["items"] if i.section == "experience"]
    return report, item


def test_rewrite_in_the_band_is_new_with_a_replaces_link(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    old = ent.points[0]
    report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert item.tier == "new"
    assert item.replaces_point_id == old.id
    assert item.replaces_score == pytest.approx(0.85, abs=0.01)
    assert item.matched_point_id is None
    assert report["counts"]["new"] == 1  # a linked draft still counts as new
    assert report["compared_wording"] is True


def test_under_the_band_is_new_with_no_link(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    _exp_entity(db_session, text=OLD)
    _report, item = _classified(db_session, tmp_path, monkeypatch, UNDER)
    assert item.tier == "new"
    assert item.replaces_point_id is None
    assert item.replaces_score is None


def test_above_the_band_is_still_drift_without_a_link(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    _report, item = _classified(db_session, tmp_path, monkeypatch, DRIFT)
    assert item.tier == "drift"
    assert item.matched_point_id == ent.points[0].id
    assert item.replaces_point_id is None
    assert item.replaces_score is None


@pytest.mark.parametrize("state,provenance", [("retired", "user_authored"), ("approved", "user_cannot_confirm")])
def test_a_retired_or_unconfirmable_point_is_never_the_target(
    db_session, tmp_path, monkeypatch, state, provenance
):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=FAR)  # the only live point is unrelated
    _point(db_session, ent, OLD, state=state, provenance=provenance)
    _report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert item.tier == "new"
    assert item.replaces_point_id is None  # OLD would have matched at 0.85; it is not a candidate


def test_embedder_failure_reports_itself_and_links_nothing(db_session, tmp_path, monkeypatch):
    _embedder_down(monkeypatch)
    _exp_entity(db_session, text=OLD)
    report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert report["compared_wording"] is False
    assert item.tier == "new"
    assert item.replaces_point_id is None
    assert item.compared_wording is False


def test_sync_never_calls_the_llm(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("sync must not call the LLM")),
    )
    _vectors(monkeypatch, BAND)
    _exp_entity(db_session, text=OLD)
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    kb_base_sync.classify(db_session, "hybrid")
    kb_base_sync.apply(db_session, "hybrid")
```

Add `import pytest` at the top of the file.

**Step 2: Write the failing apply tests**

In `backend/tests/test_kb_base_sync_apply.py` import `BAND, OLD, REWRITE, _one_bullet, _vectors`
from the classify module and add:

```python
def test_apply_writes_the_link_onto_the_draft_and_twice_is_a_noop(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    old = ent.points[0]
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    first = kb_base_sync.apply(db_session, "hybrid")
    assert first["created"] == 1
    assert first["compared_wording"] is True
    draft = db_session.scalars(select(KBPoint).where(KBPoint.origin == "base_sync")).one()
    assert draft.state == "draft"
    assert draft.replaces_point_id == old.id
    assert draft.entity_id == old.entity_id  # the link stays on the draft's own item
    db_session.refresh(old)
    assert old.state == "approved"  # sync retires nothing

    second = kb_base_sync.apply(db_session, "hybrid")
    assert second["created"] == 0
    assert db_session.query(KBPoint).count() == 2


def test_link_target_is_always_on_the_drafts_own_item(db_session, tmp_path, monkeypatch):
    """Two items each hold a near-identical bullet; the draft on Acme links Acme's."""
    _vectors(monkeypatch, BAND)
    acme = _exp_entity(db_session, text=OLD)
    other = _exp_entity(db_session, org="Globex", title="Analyst", start="2019", text=OLD)
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    kb_base_sync.apply(db_session, "hybrid")
    draft = db_session.scalars(select(KBPoint).where(KBPoint.origin == "base_sync")).one()
    assert draft.entity_id == acme.id
    assert draft.replaces_point_id == acme.points[0].id
    assert draft.replaces_point_id != other.points[0].id
```

**Step 3: Write the failing wire test**

In `backend/tests/test_kb_sync_router.py` add:

```python
def test_kb_sync_status_and_apply_carry_the_link_and_the_compared_flag(
    db_session, tmp_path, monkeypatch
):
    from tests.test_kb_base_sync_classify import BAND, OLD, REWRITE, _one_bullet, _vectors

    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        status = TestClient(app).get("/api/base-resumes/hybrid/kb-sync-status").json()
        assert status["compared_wording"] is True
        (item,) = [i for i in status["items"] if i["section"] == "experience"]
        assert item["replaces_point_id"] == str(ent.points[0].id)
        assert 0.80 <= item["replaces_score"] < 0.90
        result = TestClient(app).post("/api/base-resumes/hybrid/kb-sync").json()
        assert result["compared_wording"] is True
    finally:
        app.dependency_overrides.clear()
```

**Step 4: Run the three files to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_base_sync_classify.py tests/test_kb_base_sync_apply.py tests/test_kb_sync_router.py -q`
Expected: the new tests FAIL (`SyncItem` has no `replaces_point_id`, `compared_wording` KeyError);
every pre-existing test still passes.

**Step 5: Implement the rung**

In `backend/app/services/kb_base_sync.py`:

```python
SYNC_DRIFT_COSINE = 0.90  # conservative; borderline rephrasing -> "new"
# A "new" bullet whose best same-item match scores here is a REWRITE: the draft
# carries replaces_point_id so the inbox can offer to retire the old one. Shared
# with services/kb_groom so "similar" means one thing. Owner decision 2026-10-17:
# not 0.75 (half the extra hits are distinct claims), not 0.85 (misses half the
# real rewrites).
SYNC_REPLACES_COSINE = 0.80
```

`SyncItem` gains three fields with defaults:

```python
    # The bullet a "new" item rewrites (same item, best cosine in the replaces
    # band) and that score; None outside the band. apply() copies the id onto
    # the draft. A linked item is still "new": counts do not change.
    replaces_point_id: UUID | None = None
    replaces_score: float | None = None
    # False when this item could not be compared because the embedder raised.
    # It then reads as "new" without a link, which is what the user asked for
    # (an add), and the report says so instead of hiding it.
    compared_wording: bool = True
```

`_best_cosine` returns a triple and names failure:

```python
def _best_cosine(text: str, points: list[KBPoint]) -> tuple[float, KBPoint | None, bool]:
    """(best cosine, its point, compared). compared is False when the embedder
    raised; the caller must not read a (0, None) as 'nothing similar' then."""
    if not points:
        return 0.0, None, True
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([text] + [p.text for p in points])
    except Exception:
        return 0.0, None, False
    best_point = None
    best_score = -1.0
    query = vectors[0]
    for point, vector in zip(points, vectors[1:], strict=True):
        score = cosine(query, vector)
        if score > best_score:
            best_score = score
            best_point = point
    return best_score, best_point, True
```

Candidates exclude `user_cannot_confirm` (belt and braces; they are retired anyway):

```python
def _replace_candidates(points: list[KBPoint]) -> list[KBPoint]:
    """Active points a bullet may match. user_cannot_confirm is never a drift or
    replaces target (it is retired already; this guards the invariant on its own)."""
    return [p for p in points if p.provenance != "user_cannot_confirm"]
```

`_ladder_bullet` becomes:

```python
def _ladder_bullet(text: str, entity: KBEntity) -> SyncItem:
    points = _active_points(entity)
    section = entity.kind if entity.kind != "project" else "projects"
    key = point_text_key(text)
    for point in points:
        if point_text_key(point.text) == key:
            return SyncItem(tier="in_sync", section=section, entity_id=entity.id,
                            entity_proposal=None, matched_point_id=point.id, text=text)
    score, matched, compared = _best_cosine(text, _replace_candidates(points))
    if matched is not None and score >= SYNC_DRIFT_COSINE:
        return SyncItem(tier="drift", section=section, entity_id=entity.id,
                        entity_proposal=None, matched_point_id=matched.id, text=text)
    item = SyncItem(tier="new", section=section, entity_id=entity.id, entity_proposal=None,
                    matched_point_id=None, text=text, compared_wording=compared)
    if matched is not None and score >= SYNC_REPLACES_COSINE:
        item.replaces_point_id = matched.id
        item.replaces_score = round(score, 4)
    return item
```

`classify` adds to its return dict:

```python
        "compared_wording": all(i.compared_wording for i in items),
```

`_apply_new` passes the link when building the draft:

```python
    db.add(
        KBPoint(
            entity_id=entity.id,
            text=item.text,
            state="draft",
            origin="base_sync",
            provenance="user_authored",
            replaces_point_id=item.replaces_point_id,
        )
    )
```

`apply` adds `"compared_wording": report["compared_wording"],` to its return dict, with the
comment "False when the embedder raised during classify: every bullet then read as new, unlinked".

**Step 6: Schemas and the route**

`backend/app/schemas/kb_sync.py`:

```python
class SyncItemOut(BaseModel):
    tier: str
    section: str
    entity_id: UUID | None = None
    entity_proposal: dict[str, Any] | None = None
    matched_point_id: UUID | None = None
    text: str
    # A "new" bullet that rewrites an existing one: that bullet and the cosine
    # (0.80 to under 0.90). The draft apply() writes carries the id.
    replaces_point_id: UUID | None = None
    replaces_score: float | None = None
```

`SyncStatus` and `SyncResult` each gain:

```python
    # False when the embedder raised: every bullet then read as "new" with no
    # link, and the UI says "Couldn't compare wording" instead of "all new".
    compared_wording: bool = True
```

In `backend/app/routers/base_resumes.py` `kb_sync_status`, add `"replaces_point_id":
item.replaces_point_id, "replaces_score": item.replaces_score,` to each item dict and
`compared_wording=report["compared_wording"],` to the `SyncStatus(...)` call. `kb_sync_apply`
returns the service dict unchanged, so `compared_wording` rides through.

**Step 7: Run the three files, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_base_sync_classify.py tests/test_kb_base_sync_apply.py tests/test_kb_sync_router.py -q`
Expected: PASS, all existing tests unchanged.

Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
Expected: PASS. `tests/test_kb_sync_frontend.py` and `mcp_server/tests` are untouched by this task.

**Step 8: Commit**

```bash
git add backend/app/services/kb_base_sync.py backend/app/schemas/kb_sync.py backend/app/routers/base_resumes.py backend/tests/test_kb_base_sync_classify.py backend/tests/test_kb_base_sync_apply.py backend/tests/test_kb_sync_router.py
git commit -m "feat(kb): base sync links a rewrite draft to the bullet it replaces, and says when it could not compare"
```

---

### Task 3: The inbox, backend side

**Files:**
- Modify: `backend/app/schemas/career_kb.py` (`KBReplacedOut`, `KBPointOut.replaces`,
  `KBPointPatch.retire_replaced`, `KBPointBulkState.retire_replaced`, `KBPointBulkResult.retired_replaced`)
- Modify: `backend/app/services/career_kb.py` (`replaced_out`, `_to_point_out`)
- Modify: `backend/app/routers/career_kb.py` (`list_points`, `bulk_point_state`, `patch_point`)
- Create: `backend/tests/test_kb_replaces.py`
- Modify: `backend/tests/test_kb_provenance_stamping.py` (`test_no_writer_flips_user_cannot_confirm`)

**Step 1: Write the failing router tests**

Create `backend/tests/test_kb_replaces.py`:

```python
"""The replaces link over the wire: the inbox resolves it, Approve may retire it."""

import uuid

from app.models.career_kb import KBPoint, KBPortLog


def _entity(client, title="Orbit"):
    return client.post("/api/kb/entities", json={"kind": "project", "title": title}).json()["id"]


def _point(db_session, entity_id, text, *, state="approved", replaces=None, provenance="user_authored"):
    point = KBPoint(
        entity_id=uuid.UUID(entity_id), text=text, state=state, origin="base_sync",
        provenance=provenance, replaces_point_id=replaces,
    )
    db_session.add(point)
    db_session.commit()
    return point


def _placed_on(db_session, point, *resume_keys):
    for key in resume_keys:
        db_session.add(KBPortLog(
            entity_id=point.entity_id, point_id=point.id, resume_kind="base", resume_key=key,
            section="projects", ported_text=point.text, direction="to_resume",
        ))
    # a from_source note is not a placement and must not count
    db_session.add(KBPortLog(
        entity_id=point.entity_id, point_id=point.id, resume_kind="base", resume_key="noted",
        section="projects", ported_text="other words", direction="from_source",
    ))
    db_session.commit()


def _linked_pair(client, db_session):
    eid = _entity(client)
    old = _point(db_session, eid, "Cut latency 30% via caching")
    new = _point(db_session, eid, "Cut p95 latency 30% by caching hot keys", state="draft", replaces=old.id)
    return eid, old, new


def test_inbox_resolves_the_replaced_bullet(client, db_session):
    _eid, old, new = _linked_pair(client, db_session)
    _placed_on(db_session, old, "hybrid", "compact")
    (row,) = client.get("/api/kb/points?state=draft").json()
    assert row["id"] == str(new.id)
    assert row["replaces"] == {
        "id": str(old.id), "text": old.text, "state": "approved", "usage_count": 2,
    }
    detail = client.get(f"/api/kb/entities/{_eid}").json()
    by_id = {p["id"]: p for p in detail["points"]}
    assert by_id[str(new.id)]["replaces"]["id"] == str(old.id)
    assert by_id[str(old.id)]["replaces"] is None


def test_approve_with_retire_replaced_retires_the_target_and_reports_it(client, db_session):
    _eid, old, new = _linked_pair(client, db_session)
    r = client.patch(f"/api/kb/points/{new.id}", json={"state": "approved", "retire_replaced": True})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "approved"
    assert r.json()["replaces"]["state"] == "retired"
    db_session.refresh(old)
    db_session.refresh(new)
    assert (new.state, old.state) == ("approved", "retired")
    assert old.approved_at is None
    assert old.provenance == "user_authored"  # untouched


def test_approve_without_the_switch_leaves_the_target_alone(client, db_session):
    _eid, old, new = _linked_pair(client, db_session)
    client.patch(f"/api/kb/points/{new.id}", json={"state": "approved"})
    db_session.refresh(old)
    assert old.state == "approved"


def test_retire_replaced_is_ignored_when_not_approving_or_without_a_live_link(client, db_session):
    eid, old, new = _linked_pair(client, db_session)
    # editing text, not approving
    client.patch(f"/api/kb/points/{new.id}", json={"text": "edited", "retire_replaced": True})
    db_session.refresh(old)
    assert old.state == "approved"
    # no link at all
    lone = _point(db_session, eid, "Shipped the pipeline", state="draft")
    r = client.patch(f"/api/kb/points/{lone.id}", json={"state": "approved", "retire_replaced": True})
    assert r.status_code == 200 and r.json()["replaces"] is None
    # target already retired: no error, nothing to do
    old.state = "retired"
    db_session.commit()
    r = client.patch(f"/api/kb/points/{new.id}", json={"state": "approved", "retire_replaced": True})
    assert r.status_code == 200
    assert r.json()["replaces"] is None  # a retired target hides the block


def test_moving_the_draft_to_another_item_clears_the_link(client, db_session):
    _eid, _old, new = _linked_pair(client, db_session)
    other = _entity(client, "Elsewhere")
    r = client.patch(f"/api/kb/points/{new.id}", json={"entity_id": other})
    assert r.status_code == 200
    assert r.json()["replaces"] is None
    db_session.refresh(new)
    assert new.replaces_point_id is None


def test_deleting_the_target_nulls_the_link(client, db_session):
    _eid, old, new = _linked_pair(client, db_session)
    assert client.delete(f"/api/kb/points/{old.id}").status_code == 204
    db_session.expire_all()
    assert db_session.get(KBPoint, new.id).replaces_point_id is None
    (row,) = client.get("/api/kb/points?state=draft").json()
    assert row["replaces"] is None


def test_bulk_state_with_retire_replaced_reports_each_retired_target(client, db_session):
    eid, old, new = _linked_pair(client, db_session)
    lone = _point(db_session, eid, "Shipped the pipeline", state="draft")
    r = client.post("/api/kb/points/bulk-state", json={
        "ids": [str(new.id), str(lone.id)], "state": "approved", "retire_replaced": True,
    })
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()["results"]}
    assert rows[str(new.id)]["retired_replaced"] == str(old.id)
    assert rows[str(lone.id)]["retired_replaced"] is None
    db_session.refresh(old)
    assert old.state == "retired"


def test_bulk_state_without_the_flag_keeps_todays_shape(client, db_session):
    _eid, old, new = _linked_pair(client, db_session)
    r = client.post("/api/kb/points/bulk-state", json={"ids": [str(new.id)], "state": "approved"})
    assert r.json()["results"][0]["retired_replaced"] is None
    db_session.refresh(old)
    assert old.state == "approved"
```

**Step 2: Extend the provenance pin**

In `backend/tests/test_kb_provenance_stamping.py::test_no_writer_flips_user_cannot_confirm`, after
the `kb_ingest.capture` block, add the three new writers. They run through the HTTP routes with
the same dependency override `_drive_manual_point` uses:

```python
    # The three writers this design adds: retire-on-approve, groom's retire
    # (bulk-state), and wording adoption (PATCH text). None reads or writes
    # provenance; the record stays user_cannot_confirm whatever they do.
    from app.db import get_db
    from app.main import app

    draft = KBPoint(
        entity_id=ent.id, text="A rewrite that points at the record", state="draft",
        origin="base_sync", provenance="user_authored", replaces_point_id=point_id,
    )
    db_session.add(draft)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        assert client.patch(
            f"/api/kb/points/{draft.id}", json={"state": "approved", "retire_replaced": True}
        ).status_code == 200
        assert client.post(
            "/api/kb/points/bulk-state", json={"ids": [str(point_id)], "state": "retired"}
        ).status_code == 200
        assert client.patch(
            f"/api/kb/points/{point_id}", json={"text": "Adopted wording from a resume"}
        ).status_code == 200
    finally:
        app.dependency_overrides.clear()
    db_session.expire_all()
    assert db_session.get(KBPoint, point_id).provenance == "user_cannot_confirm"
```

**Step 3: Run both files to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_replaces.py tests/test_kb_provenance_stamping.py -q`
Expected: `test_kb_replaces.py` FAILS (no `replaces` key; 422 on `retire_replaced` is not expected
because pydantic ignores unknown fields by default, so the failures are assertion failures); the
provenance pin passes already (nothing writes provenance). Keep it: it is the guard for the code
you are about to add.

**Step 4: Schemas**

In `backend/app/schemas/career_kb.py`:

```python
class KBPointPatch(BaseModel):
    text: str | None = None
    state: str | None = None
    tags: list[str] | None = None
    entity_id: UUID | None = None
    # Honoured only when this patch sets state="approved", the point has a live
    # replaces link and the target is not retired; otherwise ignored, never an
    # error. The response is the approved point; the retired one is in
    # `replaces.state`.
    retire_replaced: bool = False
```

```python
class KBPointBulkState(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    state: Literal["approved", "retired"]
    # Same rule as KBPointPatch.retire_replaced, applied per id.
    retire_replaced: bool = False


class KBPointBulkResult(BaseModel):
    id: UUID
    ok: bool
    state: str | None = None
    detail: str | None = None
    # The replaced bullet this row retired, when retire_replaced applied.
    retired_replaced: UUID | None = None
```

Before `KBPointOut`:

```python
class KBReplacedOut(BaseModel):
    """The bullet a draft rewrites (KBPoint.replaces_point_id), enough for the
    inbox to show it and offer to retire it. usage_count is distinct resumes the
    old bullet is placed on (port-log rows that are not from_source notes)."""

    id: UUID
    text: str
    state: str
    usage_count: int
```

and in `KBPointOut`: `replaces: KBReplacedOut | None = None` after `usage`.

**Step 5: Service**

In `backend/app/services/career_kb.py`, next to `_to_point_out`:

```python
def replaced_out(session: Session, point: KBPoint) -> KBReplacedOut | None:
    """The bullet `point` replaces, or None when the link is null or its target
    is gone or retired (a retired target is an ordinary draft's row again)."""
    if point.replaces_point_id is None:
        return None
    target = point.replaces
    if target is None or target.state == "retired":
        return None
    used = session.scalar(
        select(func.count(distinct(KBPortLog.resume_key))).where(
            KBPortLog.point_id == target.id,
            or_(KBPortLog.direction.is_(None), KBPortLog.direction != "from_source"),
        )
    )
    return KBReplacedOut(id=target.id, text=target.text, state=target.state, usage_count=int(used or 0))
```

(`from sqlalchemy import distinct, func, or_` and import `KBReplacedOut`.) `_to_point_out` gains
`replaces=replaced_out(session, point),`. One small query per linked point is fine: drafts with a
live link are a handful, and the list is capped at 500.

**Step 6: Router**

In `backend/app/routers/career_kb.py`:

`list_points`: `.options(selectinload(KBPoint.entity), selectinload(KBPoint.replaces))`.

A helper above `bulk_point_state`:

```python
def _retire_replaced(db: Session, point: KBPoint) -> UUID | None:
    """Retire the bullet `point` replaces, when the user asked and it is live.
    Only state and approved_at move; provenance is never read or written here.
    Returns the retired id, or None when there was nothing to do."""
    if point.replaces_point_id is None:
        return None
    target = db.get(KBPoint, point.replaces_point_id)
    if target is None or target.state == "retired":
        return None
    _apply_point_state(target, "retired")
    return target.id
```

`bulk_point_state`, inside the loop after `_apply_point_state(point, payload.state)`:

```python
        retired = None
        if payload.state == "approved" and payload.retire_replaced:
            retired = _retire_replaced(db, point)
        results.append({"id": pid, "ok": True, "state": point.state, "detail": None,
                        "retired_replaced": retired})
```

(and the not-found row gains `"retired_replaced": None`).

`patch_point`:

```python
    if data.get("entity_id") is not None:
        target = db.get(KBEntity, data["entity_id"])
        if target is None:
            raise HTTPException(status_code=404, detail="That item no longer exists.")
        if data["entity_id"] != point.entity_id:
            # A bullet on another item cannot be the one this draft replaces.
            point.replaces_point_id = None
        point.entity_id = data["entity_id"]
    if data.get("state") is not None:
        _apply_point_state(point, data["state"])
        if data["state"] == "approved" and payload.retire_replaced:
            _retire_replaced(db, point)
```

Nothing else in `patch_point` changes; `retire_replaced` is read from `payload`, never written to
the point (it is not a column).

**Step 7: Run the files, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_replaces.py tests/test_kb_provenance_stamping.py tests/test_kb_points_bulk_state.py tests/test_career_kb_router.py -q`
Expected: PASS. `test_kb_points_bulk_state.py` is unchanged and still passes: the new result field
defaults to null.

Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
Expected: PASS. `tests/test_kb_sync_frontend.py::test_point_out_schema_declares_provenance` reads
the schema source; it still passes.

**Step 8: Commit**

```bash
git add backend/app/schemas/career_kb.py backend/app/services/career_kb.py backend/app/routers/career_kb.py backend/tests/test_kb_replaces.py backend/tests/test_kb_provenance_stamping.py
git commit -m "feat(kb): the inbox resolves the replaced bullet, and Approve can retire it in the same request"
```

---

### Task 4: Frontend plumbing: types, fetchers and the sync words

**Files:**
- Modify: `frontend/lib/types.ts` (`KBPointPatch`, `KBPointOut`, `SyncItemOut`, `SyncStatus`, `SyncResult`)
- Modify: `frontend/lib/api.ts` (`bulkKbPointState`)
- Modify: `frontend/lib/kb-sync-words.ts`
- Test: `frontend/lib/kb-sync-words.test.ts`
- Test: `backend/tests/test_kb_sync_frontend.py`

**Step 1: Write the failing word tests**

In `frontend/lib/kb-sync-words.test.ts`, give the `result` builder `compared_wording: true` as a
default and the `status` builder a third parameter:

```ts
const status = (
  items: [string, string][],
  counts: Partial<SyncStatus["counts"]>,
  compared_wording = true,
): SyncStatus => ({
  items: items.map(([tier, section]) => ({ tier, section, text: "x" }) as SyncStatus["items"][number]),
  skills_new: [],
  counts: { in_sync: 0, drift: 0, recorded_drift: 0, new: 0, skills_new: 0, ...counts },
  last_kb_synced_at: null,
  compared_wording,
});
```

then add:

```ts
test("when the embedder could not run, the popover and the toast say so, once", () => {
  const lines = syncBreakdownLines(status([["new", "experience"]], { new: 1 }, false));
  assert.equal(lines.at(-1), "Couldn't compare wording, so everything here reads as new.");
  assert.equal(lines.filter((l) => l.startsWith("Couldn't")).length, 1);
  assert.equal(
    syncResultSentence(result({ created: 2, compared_wording: false })),
    "Added 2 draft bullets to your career history. Couldn't compare wording.",
  );
  assert.equal(syncResultSentence(result({ compared_wording: false })), "Couldn't compare wording.");
});

test("when wording was compared, nothing is said about it", () => {
  assert.ok(!syncBreakdownLines(status([["new", "experience"]], { new: 1 })).some((l) => l.startsWith("Couldn't")));
  assert.doesNotMatch(syncResultSentence(result({ created: 1 })), /compare/);
});
```

**Step 2: Write the failing source pins**

In `backend/tests/test_kb_sync_frontend.py` add:

```python
def test_types_carry_the_replaces_link_and_the_compared_flag():
    source = (_FRONTEND / "lib/types.ts").read_text()
    point_block = source.split("export interface KBPointOut")[1].split("export interface")[0]
    assert "replaces: KBReplacedOut | null" in point_block
    patch_block = source.split("export interface KBPointPatch")[1].split("export interface")[0]
    assert "retire_replaced?: boolean" in patch_block
    for name in ("SyncStatus", "SyncResult"):
        block = source.split(f"export interface {name}")[1].split("export interface")[0]
        assert "compared_wording: boolean" in block, name
    item_block = source.split("export interface SyncItemOut")[1].split("export interface")[0]
    assert "replaces_point_id: UUID | null" in item_block


def test_bulk_state_fetcher_sends_retire_replaced_only_when_asked():
    source = (_FRONTEND / "lib/api.ts").read_text()
    block = source.split("export function bulkKbPointState")[1].split("export function")[0]
    assert "retire_replaced" in block
    assert "retired_replaced" in block
```

**Step 3: Run both to verify they fail**

Run: `cd frontend && node --test lib/kb-sync-words.test.ts` → FAIL (no "Couldn't" line).
Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_sync_frontend.py -q` → FAIL on the two new pins.

**Step 4: Types**

In `frontend/lib/types.ts`:

```ts
export interface KBPointPatch {
  text?: string | null;
  state?: KBPointState | null;
  tags?: string[] | null;
  entity_id?: UUID | null;
  /** With `state: "approved"` on a draft that replaces a bullet: retire that bullet too. Ignored otherwise. */
  retire_replaced?: boolean;
}

/** The bullet a draft rewrites, as the inbox shows it. `usage_count` is resumes it is placed on. */
export interface KBReplacedOut {
  id: UUID;
  text: string;
  state: KBPointState;
  usage_count: number;
}
```

`KBPointOut` gains `replaces: KBReplacedOut | null;` after `usage`. `SyncItemOut` gains
`replaces_point_id: UUID | null;` and `replaces_score: number | null;`. `SyncStatus` and `SyncResult`
each gain:

```ts
  /** False when the embedder could not run: every bullet then reads as new with no link. */
  compared_wording: boolean;
```

**Step 5: Fetcher**

```ts
export function bulkKbPointState(
  ids: UUID[],
  state: "approved" | "retired",
  options: { retireReplaced?: boolean } = {},
) {
  return apiFetch<{
    results: {
      id: UUID;
      ok: boolean;
      state: string | null;
      detail: string | null;
      retired_replaced: UUID | null;
    }[];
  }>("/api/kb/points/bulk-state", {
    method: "POST",
    body: JSON.stringify({
      ids,
      state,
      ...(options.retireReplaced ? { retire_replaced: true } : {}),
    }),
  });
}
```

**Step 6: Words**

In `frontend/lib/kb-sync-words.ts`, at the end of `syncBreakdownLines` before `return lines`:

```ts
  // Honest when it cannot compare: without the embedder every bullet reads as new.
  if (!status.compared_wording) lines.push("Couldn't compare wording, so everything here reads as new.");
```

and in `syncResultSentence`, add to the `sentences` array after the drift sentence:

```ts
    result.compared_wording ? null : "Couldn't compare wording.",
```

Check the "nothing new" fallback: with `compared_wording: false` and no adds the sentence is
"Couldn't compare wording." alone, which is right.

**Step 7: Run the gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint`
Expected: PASS. `tsc` will name every place that builds a `SyncStatus`, `SyncResult` or `KBPointOut`
literal without the new required fields (test builders, fixtures); add the fields there.

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_sync_frontend.py tests/test_frontend_kb_editors.py -q`
Expected: PASS.

**Step 8: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts frontend/lib/kb-sync-words.ts frontend/lib/kb-sync-words.test.ts backend/tests/test_kb_sync_frontend.py
git commit -m "feat(web): sync words say when wording could not be compared; types carry the replaces link"
```

---

### Task 5: The inbox, web side

**Files:**
- Create: `frontend/lib/kb-replaces.ts`, `frontend/lib/kb-replaces.test.ts`
- Modify: `frontend/components/career/inbox-panel.tsx`
- Create: `backend/tests/test_frontend_kb_stale_wording.py`

**Step 1: Write the failing pure-module tests**

`frontend/lib/kb-replaces.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { approvePatch, linkedDraftCount, replacesBlock, retireAllLine } from "./kb-replaces.ts";
import type { KBInboxPoint, KBReplacedOut } from "./types.ts";

const replaced = (over: Partial<KBReplacedOut> = {}): KBReplacedOut => ({
  id: "old", text: "Cut latency 30% via caching", state: "approved", usage_count: 0, ...over,
});
const draft = (replaces: KBReplacedOut | null): KBInboxPoint =>
  ({ id: "new", text: "Cut p95 latency 30%", state: "draft", replaces }) as unknown as KBInboxPoint;

test("the Replaces block shows only for a live link, with the state word and the usage line", () => {
  assert.equal(replacesBlock(draft(null)), null);
  assert.equal(replacesBlock(draft(replaced({ state: "retired" }))), null);
  assert.deepEqual(replacesBlock(draft(replaced())), {
    text: "Cut latency 30% via caching", stateWord: "Approved", usageLine: null,
  });
  assert.equal(replacesBlock(draft(replaced({ usage_count: 1 })))?.usageLine, "used on 1 resume");
  assert.equal(replacesBlock(draft(replaced({ usage_count: 2 })))?.usageLine, "used on 2 resumes");
  assert.equal(replacesBlock(draft(replaced({ state: "draft" })))?.stateWord, "Draft");
});

test("Approve sends retire_replaced from the switch, and only with a live link", () => {
  assert.deepEqual(approvePatch(draft(replaced()), "Cut p95 latency 30%", true), {
    state: "approved", retire_replaced: true,
  });
  assert.deepEqual(approvePatch(draft(replaced()), "Cut p95 latency 30%", false), { state: "approved" });
  assert.deepEqual(approvePatch(draft(null), "Cut p95 latency 30%", true), { state: "approved" });
  // an edited text rides along, as today
  assert.deepEqual(approvePatch(draft(null), "Edited", true), { state: "approved", text: "Edited" });
});

test("Approve all counts the drafts with a live link and omits the line at zero", () => {
  const drafts = [draft(replaced()), draft(null), draft(replaced({ state: "retired" })), draft(replaced())];
  assert.equal(linkedDraftCount(drafts), 2);
  assert.equal(retireAllLine(2), "Also retire the 2 bullets they replace");
  assert.equal(retireAllLine(1), "Also retire the 1 bullet it replaces");
  assert.equal(retireAllLine(0), null);
});
```

**Step 2: Run it to verify it fails**

Run: `cd frontend && node --test lib/kb-replaces.test.ts`
Expected: FAIL, cannot find module `./kb-replaces.ts`.

**Step 3: The pure module**

`frontend/lib/kb-replaces.ts`:

```ts
/**
 * The draft inbox's Replaces block in words and payloads: whether a draft has a live link to the
 * bullet it rewrites, what Approve sends, and what Approve all offers. Pure, so `node --test` runs
 * it (`kb-replaces.test.ts`).
 */
import type { KBInboxPoint, KBPointOut, KBPointPatch, KBPointState } from "./types";

const STATE_WORDS: Record<KBPointState, string> = { draft: "Draft", approved: "Approved", retired: "Not used" };

/** A link is live when it resolved and its target is not retired. */
export function hasLiveReplaces(point: Pick<KBPointOut, "replaces">): boolean {
  return point.replaces !== null && point.replaces.state !== "retired";
}

export function replacesBlock(
  point: Pick<KBPointOut, "replaces">,
): { text: string; stateWord: string; usageLine: string | null } | null {
  if (!hasLiveReplaces(point) || point.replaces === null) return null;
  const n = point.replaces.usage_count;
  return {
    text: point.replaces.text,
    stateWord: STATE_WORDS[point.replaces.state],
    usageLine: n > 0 ? `used on ${n} ${n === 1 ? "resume" : "resumes"}` : null,
  };
}

/** The PATCH an Approve sends: the state, the edited text when it changed, and the switch. */
export function approvePatch(
  point: Pick<KBPointOut, "text" | "replaces">,
  text: string,
  retireOld: boolean,
): KBPointPatch {
  const value = text.trim();
  return {
    state: "approved",
    ...(value && value !== point.text ? { text: value } : {}),
    ...(retireOld && hasLiveReplaces(point) ? { retire_replaced: true } : {}),
  };
}

export function linkedDraftCount(drafts: readonly Pick<KBInboxPoint, "replaces">[]): number {
  return drafts.filter(hasLiveReplaces).length;
}

/** The checkbox label in the Approve all confirm; absent when no listed draft has a link. */
export function retireAllLine(linked: number): string | null {
  if (linked === 0) return null;
  return linked === 1
    ? "Also retire the 1 bullet it replaces"
    : `Also retire the ${linked} bullets they replace`;
}
```

**Step 4: Run it to verify it passes**

Run: `cd frontend && node --test lib/kb-replaces.test.ts` → PASS.

**Step 5: Write the failing source pins for the wiring**

Create `backend/tests/test_frontend_kb_stale_wording.py`:

```python
"""Source pins for the stale-wording surfaces: the inbox's Replaces block, the
Tidy bullets dialog and the drift popover call their pure modules and say the
designed words. Behaviour lives in frontend/lib/*.test.ts (node --test)."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_inbox_row_renders_the_replaces_block_from_the_pure_module():
    src = _read("components/career/inbox-panel.tsx")
    row = src[src.index("function DraftRow(") :]
    assert "replacesBlock(point)" in row
    assert "approvePatch(point, text, retireOld)" in row
    assert "Replaces this bullet" in row
    assert "Retire the old bullet" in row
    assert "useState(true)" in row, "the switch defaults on"
    assert "Bullet approved. Retired the old wording." in row


def test_approve_all_offers_to_retire_the_replaced_bullets():
    src = _read("components/career/inbox-panel.tsx")
    assert "linkedDraftCount(" in src
    assert "retireAllLine(" in src
    assert "retireReplaced:" in src
    assert "won't be" in src  # the unsaved-edits sentence survives the dialog move
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py -q` → FAIL.

**Step 6: The inbox panel**

In `frontend/components/career/inbox-panel.tsx`:

1. Imports: `Switch` from `@/components/ui/switch`, `Checkbox` from `@/components/ui/checkbox`,
   `Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle` from
   `@/components/ui/dialog`, and `approvePatch, linkedDraftCount, replacesBlock, retireAllLine`
   from `@/lib/kb-replaces`. Keep `useConfirm` only if something else in the file still uses it
   (nothing does after this step; remove the import then).

2. **Approve all.** Replace the `confirm({...})` call inside `approveAll.mutationFn` with a local
   dialog. Add state in `InboxPanel`:

   ```tsx
   const linked = useMemo(() => linkedDraftCount(drafts.filter((d) => approvableIds.includes(d.id))), [drafts, approvableIds]);
   const [approveAllOpen, setApproveAllOpen] = useState(false);
   const [retireAll, setRetireAll] = useState(true);
   ```

   `approveAll.mutationFn` becomes `(ids: UUID[]) => bulkKbPointState(ids, "approved", { retireReplaced: retireAll && linked > 0 })`.
   The button opens the dialog (`setRetireAll(true); setApproveAllOpen(true)`); the dialog's
   primary button closes it and calls `approveAll.mutate(approvableIds)`. The dialog copy is the
   old confirm's: title `Approve N bullet(s)?`, description "They'll be added to your career
   history. You can still edit them later." or the unsaved-edits sentence (`skipped > 0`), and,
   when `retireAllLine(linked)` is not null, a `Checkbox` labelled with that line, checked by
   default, bound to `retireAll`. Focus: `initialFocus` on the Approve button (not destructive),
   as the provider did; `finalFocus` back to the Approve all button.

   The success toast adds `Retired the old wording.` when the response has any
   `retired_replaced` set: `const retired = body.results.filter((r) => r.retired_replaced).length;`
   then `Approved N bullets. Retired N old.` only when `retired > 0`.

3. **The row.** In `DraftRow`, add `const [retireOld, setRetireOld] = useState(true);` and
   `const block = replacesBlock(point);`. `approve` becomes:

   ```tsx
   const approve = () => {
     const retiring = retireOld && block !== null;
     updateOnce({
       payload: approvePatch(point, text, retireOld),
       success: retiring ? "Bullet approved. Retired the old wording." : "Bullet approved",
       undoable: true,
       // Undo puts the old bullet back where it was and the new one back in drafts.
       undo: retiring && point.replaces ? { oldId: point.replaces.id, oldState: point.replaces.state } : undefined,
     });
   };
   ```

   Extend the mutation variables with `undo?: { oldId: UUID; oldState: KBPointState }` and the
   Undo handler to `Promise.all([patchKbPoint(updated.id, { state: "draft" }), undo ? patchKbPoint(undo.oldId, { state: undo.oldState }) : Promise.resolve()])`
   before invalidating. (`patchKbPoint` with `state: "draft"` is legal on the single PATCH.)

   Render the block after the actor chip, in the same muted block style the merge-sources block
   uses, only when `block !== null`:

   ```tsx
   {block ? (
     <div className="mt-3 rounded-corner-md bg-surface-container-high p-3">
       <p className="mb-1 text-label-medium">Replaces this bullet</p>
       <p className="text-body-small">{block.text}</p>
       <p className="text-muted-foreground mt-1 text-label-small">
         {block.stateWord}
         {block.usageLine ? ` · ${block.usageLine}` : null}
       </p>
       <div className="mt-2 flex items-center gap-2">
         <Switch id={`retire-old-${point.id}`} checked={retireOld} onCheckedChange={setRetireOld} disabled={pending} />
         <Label htmlFor={`retire-old-${point.id}`}>Retire the old bullet</Label>
       </div>
     </div>
   ) : null}
   ```

   Check `Switch`'s prop names in `frontend/components/ui/switch.tsx` (Base UI uses
   `checked`/`onCheckedChange`); adapt if they differ.

   Edit keeps the link (nothing to do: the PATCH carries no `entity_id`). Move clears it
   server-side; the block disappears on the refetch (nothing to do). Discard: nothing.

**Step 7: Gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py tests/test_frontend_kb_editors.py tests/test_kb_sync_frontend.py tests/test_frontend_plain_words.py -q` → PASS.
`test_frontend_kb_editors.py` pins the draft editor's discard question; its `_DRAFT_ROW` slice
still finds `function DraftRow(`. Keep that function name.

**Step 8: Commit**

```bash
git add frontend/lib/kb-replaces.ts frontend/lib/kb-replaces.test.ts frontend/components/career/inbox-panel.tsx backend/tests/test_frontend_kb_stale_wording.py
git commit -m "feat(web): the draft inbox shows the bullet a rewrite replaces and retires it on Approve"
```

---

### Task 6: Groom service and endpoints

**Files:**
- Create: `backend/app/services/kb_groom.py`
- Modify: `backend/app/schemas/career_kb.py` (`GroomMember`, `GroomCluster`, `GroomReport`,
  `KBKeepApartRequest`, `KBKeepApartResponse`)
- Modify: `backend/app/routers/career_kb.py` (three routes)
- Create: `backend/tests/test_kb_groom.py`

**Step 1: Write the failing service tests**

`backend/tests/test_kb_groom.py`:

```python
"""Read-only per-item groom: clusters of similar bullets, a proposed keeper, kept pairs."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.services import kb_groom
from tests.test_kb_base_sync_classify import _embedder_down, _vectors

A = "Cleansed and validated 2M rows nightly"
B = "Cleansed, standardized and validated 2M rows"
C = "Validated two million rows every night"
FAR = "Mentored two interns"

# A~B 0.85, B~C 0.85, A~C 0.445 (a chain: A and C meet only through B); FAR on its own axis, 0 to all.
# cos(A,B) = 0.85; cos(B,C) = 0.85*0.445 + 0.52678*0.8955 = 0.85; cos(A,C) = 0.445
VEC = {
    A: (1.0, 0.0, 0.0),
    B: (0.85, 0.52678, 0.0),
    C: (0.445, 0.8955, 0.0),
    FAR: (0.0, 0.0, 1.0),
}


def _item(db_session, *texts, states=None, provenances=None, updated=None):
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    points = []
    for i, text in enumerate(texts):
        p = KBPoint(
            entity_id=ent.id, text=text, origin="manual",
            state=(states or {}).get(text, "approved"),
            provenance=(provenances or {}).get(text, "user_authored"),
        )
        db_session.add(p)
        db_session.flush()
        if updated and text in updated:
            p.updated_at = updated[text]
            db_session.flush()
        points.append(p)
    db_session.commit()
    return ent, {p.text: p for p in points}


def test_fixed_vectors_give_deterministic_clusters_and_single_link_joins_a_chain(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C, FAR)
    first = kb_groom.groom_entity(db_session, ent.id)
    second = kb_groom.groom_entity(db_session, ent.id)
    assert first == second
    assert first.compared_wording is True
    assert first.active_points == 4
    (cluster,) = first.clusters
    assert {m.id for m in cluster.members} == {by[A].id, by[B].id, by[C].id}
    assert cluster.score == pytest.approx(0.85, abs=0.01)
    assert sorted(len(p) for p in cluster.pairs) == [3, 3]
    assert len(cluster.pairs) == 2  # A-B and B-C; A-C is under the band
    assert cluster.members[0].id == cluster.keeper_id


def test_keeper_rule_in_each_tiebreak_order(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    now = datetime.now(UTC)
    # approved beats draft
    ent, by = _item(db_session, A, B, states={A: "draft", B: "approved"})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id
    # then most recently updated
    ent, by = _item(db_session, A, B, updated={A: now - timedelta(days=2), B: now - timedelta(days=1)})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id
    # then the longer text (same updated_at)
    same = now - timedelta(days=3)
    ent, by = _item(db_session, A, B, updated={A: same, B: same})
    assert kb_groom.groom_entity(db_session, ent.id).clusters[0].keeper_id == by[B].id  # B is longer
    # then the id (same state, same updated_at, same length: 38 characters each)
    twin = "Cleansed and validated 2M rows weekly."
    assert len(twin) == len(A)
    _vectors(monkeypatch, {**VEC, twin: (1.0, 0.0, 0.0)})
    ent, by = _item(db_session, A, twin, updated={A: same, twin: same})
    report = kb_groom.groom_entity(db_session, ent.id)
    assert report.clusters[0].keeper_id == min(p.id for p in by.values())


def test_kept_pairs_break_an_edge(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    lo, hi = kept_pair_key(by[A].id, by[B].id)
    db_session.add(KBPointKeptPair(point_a_id=lo, point_b_id=hi))
    db_session.commit()
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    assert {m.id for m in cluster.members} == {by[B].id, by[C].id}  # A fell out with its only edge


def test_drafts_included_retired_and_unconfirmable_excluded(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(
        db_session, A, B, C,
        states={A: "draft", C: "retired"},
    )
    report = kb_groom.groom_entity(db_session, ent.id)
    assert report.active_points == 2
    assert {m.id for m in report.clusters[0].members} == {by[A].id, by[B].id}
    ent, by = _item(db_session, A, B, provenances={A: "user_cannot_confirm"})
    assert kb_groom.groom_entity(db_session, ent.id).clusters == []


def test_one_point_item_and_no_similar_pairs_are_empty(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, _ = _item(db_session, A)
    report = kb_groom.groom_entity(db_session, ent.id)
    assert (report.active_points, report.clusters, report.compared_wording) == (1, [], True)
    ent, _ = _item(db_session, A, FAR)
    assert kb_groom.groom_entity(db_session, ent.id).clusters == []


def test_embedder_failure_sets_compared_wording_false(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    ent, _ = _item(db_session, A, B)
    report = kb_groom.groom_entity(db_session, ent.id)
    assert report.compared_wording is False
    assert report.clusters == []


def test_member_rows_carry_usage_and_sort_keeper_first_then_by_score(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    db_session.add(KBPortLog(entity_id=ent.id, point_id=by[C].id, resume_kind="base",
                             resume_key="hybrid", section="projects", ported_text=C, direction="to_resume"))
    db_session.commit()
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    rows = {m.id: m for m in cluster.members}
    assert rows[by[C].id].usage_count == 1
    assert rows[by[A].id].usage_count == 0
    assert cluster.members[0].id == cluster.keeper_id
    assert cluster.members[0].best_score == pytest.approx(1.0)
    scores = [m.best_score for m in cluster.members[1:]]
    assert scores == sorted(scores, reverse=True)


def test_groom_never_calls_the_llm(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("groom must not call the LLM")),
    )
    _vectors(monkeypatch, VEC)
    ent, _ = _item(db_session, A, B)
    kb_groom.groom_entity(db_session, ent.id)


def test_groom_writes_nothing(db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B)
    before = {(p.id, p.state, p.text, p.updated_at) for p in by.values()}
    kb_groom.groom_entity(db_session, ent.id)
    db_session.expire_all()
    after = {(p.id, p.state, p.text, p.updated_at) for p in db_session.query(KBPoint)}
    assert before == after
    assert db_session.query(KBPointKeptPair).count() == 0


def test_unknown_entity_raises_value_error(db_session):
    with pytest.raises(ValueError):
        kb_groom.groom_entity(db_session, uuid.uuid4())


# ---- routes ----

def test_groom_route_returns_the_report_and_404s(client, db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B)
    r = client.get(f"/api/kb/entities/{ent.id}/groom")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entity_title"] == "Orbit"
    assert body["clusters"][0]["keeper_id"] in {str(by[A].id), str(by[B].id)}
    assert client.get(f"/api/kb/entities/{uuid.uuid4()}/groom").status_code == 404


def test_keep_apart_records_every_pair_canonically_and_is_idempotent(client, db_session):
    _ent, by = _item(db_session, A, B, C)
    ids = [str(by[C].id), str(by[A].id), str(by[B].id)]
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    assert r.status_code == 200, r.text
    assert len(r.json()["pairs"]) == 3
    rows = db_session.query(KBPointKeptPair).all()
    assert len(rows) == 3
    assert all(row.point_a_id < row.point_b_id for row in rows)
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    assert r.status_code == 200
    assert db_session.query(KBPointKeptPair).count() == 3


def test_keep_apart_requires_one_item_and_known_points(client, db_session):
    _ent, by = _item(db_session, A)
    _other, by2 = _item(db_session, B)
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(by2[B].id)]})
    assert r.status_code == 400
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(uuid.uuid4())]})
    assert r.status_code == 404
    r = client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id)]})
    assert r.status_code == 422


def test_keep_apart_delete_forgets_and_point_delete_cascades(client, db_session):
    _ent, by = _item(db_session, A, B, C)
    ids = [str(by[A].id), str(by[B].id), str(by[C].id)]
    client.post("/api/kb/points/keep-apart", json={"point_ids": ids})
    r = client.request("DELETE", "/api/kb/points/keep-apart", json={"point_ids": ids[:2]})
    assert r.status_code == 200
    assert db_session.query(KBPointKeptPair).count() == 2
    assert client.delete(f"/api/kb/points/{by[C].id}").status_code == 204
    assert db_session.query(KBPointKeptPair).count() == 0
```

**Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_groom.py -q`
Expected: FAIL, `ImportError: cannot import name 'kb_groom'`.

**Step 3: Schemas**

In `backend/app/schemas/career_kb.py`, after the bulk models:

```python
class GroomMember(BaseModel):
    id: UUID
    text: str
    state: str
    origin: str
    provenance: str | None = None
    usage_count: int
    # Cosine to the proposed keeper (1.0 for the keeper itself).
    best_score: float


class GroomCluster(BaseModel):
    # The highest pair score in the cluster.
    score: float
    keeper_id: UUID
    # Keeper first, then by best_score descending.
    members: list[GroomMember]
    # Every edge at or above the band, as [id, id, score].
    pairs: list[tuple[UUID, UUID, float]]


class GroomReport(BaseModel):
    """Read-only: similar bullets on one item, clustered, with a proposed keeper.
    Nothing is written; retiring goes through POST /api/kb/points/bulk-state."""

    entity_id: UUID
    entity_title: str
    # False when the embedder raised; clusters is then [].
    compared_wording: bool
    active_points: int
    clusters: list[GroomCluster] = Field(default_factory=list)


class KBKeepApartRequest(BaseModel):
    """'Not the same': every unordered pair among these ids is remembered, so
    groom stops proposing them. Same item required."""

    point_ids: list[UUID] = Field(min_length=2, max_length=50)


class KBKeepApartResponse(BaseModel):
    # The canonical pairs this call recorded or forgot, lower id first.
    pairs: list[tuple[UUID, UUID]]
```

**Step 4: The service**

`backend/app/services/kb_groom.py`:

```python
"""Per-item groom: similar bullets on one Career KB item, read-only.

Zero LLM calls and zero writes. Embeds the item's active bullets once through
the pinned local embedder, joins pairs at SYNC_REPLACES_COSINE and above (minus
the pairs the user marked "Not the same"), takes single-link components as
clusters and proposes a keeper. The user retires the rest through the bulk-state
endpoint; nothing here changes a row. Re-run safe by construction.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.schemas.career_kb import GroomCluster, GroomMember, GroomReport
from app.services.kb_base_sync import SYNC_REPLACES_COSINE


def _candidates(entity: KBEntity) -> list[KBPoint]:
    """Drafts included (they are part of the pile); retired and user_cannot_confirm
    out. Provenance is read only to exclude, never to rank or write."""
    return [
        p for p in entity.points
        if p.state != "retired" and p.provenance != "user_cannot_confirm"
    ]


def _usage_counts(db: Session, ids: list[UUID]) -> dict[UUID, int]:
    if not ids:
        return {}
    rows = db.execute(
        select(KBPortLog.point_id, func.count(distinct(KBPortLog.resume_key)))
        .where(
            KBPortLog.point_id.in_(ids),
            or_(KBPortLog.direction.is_(None), KBPortLog.direction != "from_source"),
        )
        .group_by(KBPortLog.point_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def _kept(db: Session, ids: list[UUID]) -> set[tuple[UUID, UUID]]:
    if not ids:
        return set()
    rows = db.scalars(
        select(KBPointKeptPair).where(
            KBPointKeptPair.point_a_id.in_(ids), KBPointKeptPair.point_b_id.in_(ids)
        )
    ).all()
    return {(r.point_a_id, r.point_b_id) for r in rows}


def _components(ids: list[UUID], edges: list[tuple[UUID, UUID, float]]) -> list[list[UUID]]:
    """Single link on purpose: a chain of rewrites (A→B→C) is one claim even
    when A and C fall under the band."""
    parent = {i: i for i in ids}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    groups: dict[UUID, list[UUID]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return [g for g in groups.values() if len(g) >= 2]


def _keeper(points: list[KBPoint]) -> KBPoint:
    """Approved over draft, then most recently updated, then longest text, then id.
    Stated in the panel, so the proposal is explainable."""
    return min(
        points,
        key=lambda p: (p.state != "approved", -p.updated_at.timestamp(), -len(p.text), str(p.id)),
    )


def groom_entity(db: Session, entity_id: UUID) -> GroomReport:
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise ValueError("Entity not found")
    points = _candidates(entity)
    base = dict(entity_id=entity.id, entity_title=entity.title, active_points=len(points))
    if len(points) < 2:
        return GroomReport(**base, compared_wording=True, clusters=[])
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([p.text for p in points])
    except Exception:
        return GroomReport(**base, compared_wording=False, clusters=[])

    by_id = {p.id: p for p in points}
    ids = [p.id for p in points]
    kept = _kept(db, ids)
    score: dict[tuple[UUID, UUID], float] = {}
    edges: list[tuple[UUID, UUID, float]] = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            s = cosine(vectors[i], vectors[j])
            key = kept_pair_key(ids[i], ids[j])
            score[key] = s
            if s >= SYNC_REPLACES_COSINE and key not in kept:
                edges.append((key[0], key[1], round(s, 4)))

    usage = _usage_counts(db, ids)
    clusters: list[GroomCluster] = []
    for group in _components(ids, edges):
        members = [by_id[i] for i in group]
        keeper = _keeper(members)
        pairs = [e for e in edges if e[0] in group and e[1] in group]

        def best(p: KBPoint) -> float:
            return 1.0 if p.id == keeper.id else round(score[kept_pair_key(p.id, keeper.id)], 4)

        ordered = sorted(members, key=lambda p: (p.id != keeper.id, -best(p), str(p.id)))
        clusters.append(
            GroomCluster(
                score=max(e[2] for e in pairs),
                keeper_id=keeper.id,
                members=[
                    GroomMember(
                        id=p.id, text=p.text, state=p.state, origin=p.origin,
                        provenance=p.provenance, usage_count=usage.get(p.id, 0), best_score=best(p),
                    )
                    for p in ordered
                ],
                pairs=pairs,
            )
        )
    clusters.sort(key=lambda c: (-c.score, str(c.keeper_id)))
    return GroomReport(**base, compared_wording=True, clusters=clusters)
```

**Step 5: Routes**

In `backend/app/routers/career_kb.py` (import `kb_groom`, `KBPointKeptPair`, `kept_pair_key`,
the new schemas):

```python
@router.get("/entities/{entity_id}/groom", response_model=GroomReport)
def groom_entity(entity_id: UUID, db: Annotated[Session, Depends(get_db)]):
    """Similar bullets on one item, read-only; a sync def because it embeds on CPU."""
    try:
        return kb_groom.groom_entity(db, entity_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _keep_apart_pairs(db: Session, payload: KBKeepApartRequest) -> list[tuple[UUID, UUID]]:
    points = [db.get(KBPoint, pid) for pid in dict.fromkeys(payload.point_ids)]
    if any(p is None for p in points):
        raise HTTPException(status_code=404, detail="Point not found")
    if len({p.entity_id for p in points}) != 1:
        raise HTTPException(status_code=400, detail="These bullets are on different items.")
    ids = [p.id for p in points]
    return sorted({kept_pair_key(a, b) for i, a in enumerate(ids) for b in ids[i + 1 :]})


@router.post("/points/keep-apart", response_model=KBKeepApartResponse)
def keep_apart(payload: KBKeepApartRequest, db: Annotated[Session, Depends(get_db)]):
    """'Not the same': remember every pair among these ids so groom stops
    proposing them. Idempotent; same item required."""
    pairs = _keep_apart_pairs(db, payload)
    have = {
        (r.point_a_id, r.point_b_id)
        for r in db.scalars(select(KBPointKeptPair).where(
            KBPointKeptPair.point_a_id.in_([a for a, _ in pairs])
        )).all()
    }
    for a, b in pairs:
        if (a, b) not in have:
            db.add(KBPointKeptPair(point_a_id=a, point_b_id=b))
    db.commit()
    return KBKeepApartResponse(pairs=pairs)


@router.delete("/points/keep-apart", response_model=KBKeepApartResponse)
def forget_keep_apart(payload: KBKeepApartRequest, db: Annotated[Session, Depends(get_db)]):
    """The Undo of "Not the same": forget these pairs."""
    pairs = _keep_apart_pairs(db, payload)
    for a, b in pairs:
        row = db.get(KBPointKeptPair, (a, b))
        if row is not None:
            db.delete(row)
    db.commit()
    return KBKeepApartResponse(pairs=pairs)
```

Route order matters: both `/points/keep-apart` routes must be declared BEFORE
`@router.patch("/points/{point_id}")` and `@router.delete("/points/{point_id}")`, or
`keep-apart` is parsed as a point id and 422s. Place them right after `bulk_point_state`.

**Step 6: Run the file, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_groom.py -q` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 7: Commit**

```bash
git add backend/app/services/kb_groom.py backend/app/schemas/career_kb.py backend/app/routers/career_kb.py backend/tests/test_kb_groom.py
git commit -m "feat(kb): read-only groom report per item, and kept pairs for 'Not the same'"
```

---

### Task 7: The Tidy bullets dialog

**Files:**
- Create: `frontend/lib/kb-groom.ts`, `frontend/lib/kb-groom.test.ts`
- Modify: `frontend/lib/types.ts` (`GroomMember`, `GroomCluster`, `GroomReport`)
- Modify: `frontend/lib/api.ts` (`getKbGroom`, `keepApartKbPoints`, `forgetKeepApartKbPoints`)
- Create: `frontend/components/career/groom-dialog.tsx`
- Modify: `frontend/components/career/points-list.tsx` (the header button)
- Modify: `backend/tests/test_frontend_kb_stale_wording.py`

**Step 1: Write the failing pure-module tests**

`frontend/lib/kb-groom.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { groomState, pairsOf, retireIds, retiredToast } from "./kb-groom.ts";
import type { GroomCluster, GroomReport } from "./types.ts";

const member = (id: string, text = id) =>
  ({ id, text, state: "approved", origin: "manual", provenance: null, usage_count: 0, best_score: 1 }) as GroomCluster["members"][number];
const cluster: GroomCluster = {
  score: 0.93, keeper_id: "a", members: [member("a"), member("b"), member("c")],
  pairs: [["a", "b", 0.93], ["b", "c", 0.85]],
};
const report = (over: Partial<GroomReport>): GroomReport => ({
  entity_id: "e", entity_title: "Orbit", compared_wording: true, active_points: 3, clusters: [cluster], ...over,
});

test("Retire the others sends every member but the selected keeper", () => {
  assert.deepEqual(retireIds(cluster, "a"), ["b", "c"]);
  assert.deepEqual(retireIds(cluster, "c"), ["a", "b"]);
});

test("Not the same sends every pair among the members, once", () => {
  assert.deepEqual(pairsOf(cluster), ["a", "b", "c"]);
});

test("the dialog's state: clusters, empty, or could not compare", () => {
  assert.equal(groomState(report({})), "clusters");
  assert.equal(groomState(report({ clusters: [] })), "empty");
  assert.equal(groomState(report({ clusters: [], compared_wording: false })), "failed");
});

test("the toast names the keeper and counts the retired", () => {
  assert.equal(retiredToast(2, "Cleansed 2M rows"), "Retired 2 bullets. Cleansed 2M rows stays.");
  assert.equal(retiredToast(1, "Cleansed 2M rows"), "Retired 1 bullet. Cleansed 2M rows stays.");
});
```

Run: `cd frontend && node --test lib/kb-groom.test.ts` → FAIL (no module).

**Step 2: Types, fetchers, the pure module**

`frontend/lib/types.ts`:

```ts
export interface GroomMember {
  id: UUID;
  text: string;
  state: KBPointState;
  origin: KBPointOrigin;
  provenance: KBPointProvenance | null;
  usage_count: number;
  best_score: number;
}

export interface GroomCluster {
  score: number;
  keeper_id: UUID;
  members: GroomMember[];
  pairs: [UUID, UUID, number][];
}

/** Similar bullets on one item, read-only. `compared_wording` false means the embedder could not run. */
export interface GroomReport {
  entity_id: UUID;
  entity_title: string;
  compared_wording: boolean;
  active_points: number;
  clusters: GroomCluster[];
}
```

`frontend/lib/api.ts`:

```ts
export function getKbGroom(entityId: UUID) {
  return apiFetch<GroomReport>(`/api/kb/entities/${entityId}/groom`);
}

export function keepApartKbPoints(pointIds: UUID[]) {
  return apiFetch<{ pairs: [UUID, UUID][] }>("/api/kb/points/keep-apart", {
    method: "POST",
    body: JSON.stringify({ point_ids: pointIds }),
  });
}

export function forgetKeepApartKbPoints(pointIds: UUID[]) {
  return apiFetch<{ pairs: [UUID, UUID][] }>("/api/kb/points/keep-apart", {
    method: "DELETE",
    body: JSON.stringify({ point_ids: pointIds }),
  });
}
```

`frontend/lib/kb-groom.ts`:

```ts
/**
 * The Tidy bullets dialog's decisions in one pure module (`kb-groom.test.ts`): which ids a
 * "Retire the other(s)" sends, which a "Not the same" sends, which state the dialog is in, and
 * the toast.
 */
import type { GroomCluster, GroomReport, UUID } from "./types";

/** Every member except the one the user keeps. */
export function retireIds(cluster: GroomCluster, keeperId: UUID): UUID[] {
  return cluster.members.filter((m) => m.id !== keeperId).map((m) => m.id);
}

/** The ids the keep-apart endpoint pairs among itself (a cluster of three records three pairs). */
export function pairsOf(cluster: GroomCluster): UUID[] {
  return cluster.members.map((m) => m.id);
}

export type GroomState = "clusters" | "empty" | "failed";

export function groomState(report: GroomReport): GroomState {
  if (!report.compared_wording) return "failed";
  return report.clusters.length === 0 ? "empty" : "clusters";
}

export function retiredToast(n: number, keeperText: string): string {
  return `Retired ${n} ${n === 1 ? "bullet" : "bullets"}. ${keeperText} stays.`;
}

/** The keeper rule, stated so the proposal is explainable. */
export const KEEPER_RULE =
  "We suggest keeping the approved one, then the most recently edited, then the longest.";
```

Run: `cd frontend && node --test lib/kb-groom.test.ts` → PASS.

**Step 3: Write the failing source pins**

Append to `backend/tests/test_frontend_kb_stale_wording.py`:

```python
def test_tidy_bullets_button_opens_the_groom_dialog_when_two_or_more_are_active():
    src = _read("components/career/points-list.tsx")
    assert "Tidy bullets" in src
    assert 'state !== "retired"' in src and ">= 2" in src
    assert "GroomDialog" in src


def test_groom_dialog_uses_the_pure_module_and_says_the_designed_words():
    src = _read("components/career/groom-dialog.tsx")
    for needle in (
        "retireIds(", "pairsOf(", "groomState(", "retiredToast(", "KEEPER_RULE",
        "Similar bullets on", "Keep one and retire the rest.",
        "Retired bullets stay on resumes that already use them.",
        "Keep this one", "Not the same", "Won't suggest these again",
        "No similar bullets here.", "Couldn't compare wording right now.",
        "forgetKeepApartKbPoints(", 'bulkKbPointState(', '"retired"',
    ):
        assert needle in src, needle
    assert "Retire all" not in src, "each cluster is one decision"
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py -q` → FAIL.

**Step 4: The dialog**

`frontend/components/career/groom-dialog.tsx`, a client component:

- Props: `{ entityId: UUID; entityTitle: string; open: boolean; onOpenChange: (open: boolean) => void }`.
- `useQuery({ queryKey: ["kb", "groom", entityId], queryFn: () => getKbGroom(entityId), enabled: open })`.
- Title "Similar bullets on {entityTitle}"; description "These say nearly the same thing. Keep one
  and retire the rest. Retired bullets stay on resumes that already use them." then `KEEPER_RULE`
  in muted text.
- States from `groomState(report)`: loading → two `Skeleton` cluster cards; `failed` → "Couldn't
  compare wording right now." with a Retry button (`refetch`); `empty` → "No similar bullets
  here."; `clusters` → one card per cluster.
- Each cluster card: header `{Math.round(score * 100)}% similar`; a `RadioGroup` of members,
  value defaulting to `cluster.keeper_id` (local state per cluster, keyed by keeper id), each
  radio labelled "Keep this one" for the selected one and the member text beside, with a muted
  line of its state word and `used on N resumes` when `usage_count > 0`; footer buttons
  **Retire the other(s)** (count-aware label) and **Not the same** (variant ghost).
- Retire: `bulkKbPointState(retireIds(cluster, selected), "retired")`; on success toast
  `retiredToast(n, keeperText)` with Undo. Undo puts each retired member back in its prior state
  with one single PATCH per member (`Promise.all(members.map((m) => patchKbPoint(m.id, { state: m.state })))`;
  the single PATCH accepts `draft`, bulk-state does not). Then invalidate
  `["kb","groom",entityId]`, `["kb","entity",entityId]`, `["kb","entities"]`, `["kb","drafts"]`
  so the list behind the dialog refetches while it stays open. The cluster leaves the list on the
  refetch.
- Not the same: `keepApartKbPoints(pairsOf(cluster))`; toast "Won't suggest these again" with
  Undo → `forgetKeepApartKbPoints(pairsOf(cluster))`; invalidate the groom query.
- Footer: one button, **Done**, which closes. No "Retire all suggestions".
- Pending: disable the cluster's two buttons while its mutation runs; a `useSingleFlight` on each.

Check `RadioGroup`/`Radio` prop names in `frontend/components/ui/radio-group.tsx` before writing.

**Step 5: The button**

In `frontend/components/career/points-list.tsx`, `PointsList` gains `entityTitle: string` (pass
`entity.data.title` from `entity-detail.tsx`) and state `const [tidyOpen, setTidyOpen] = useState(false)`.
In the `CardHeader`, next to the title, when `points.filter((p) => p.state !== "retired").length >= 2`:

```tsx
<Button size="sm" variant="outline" onClick={() => setTidyOpen(true)}>
  <Sparkles aria-hidden="true" /> Tidy bullets
</Button>
```

(use whichever lucide icon the concept icons already map for "tidy" or "merge"; `Sparkles` is a
placeholder, and `CONCEPT_ICONS` wins if it has a fitting entry.) Render
`<GroomDialog entityId={entityId} entityTitle={entityTitle} open={tidyOpen} onOpenChange={setTidyOpen} />`
after the card.

**Step 6: Gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py tests/test_frontend_plain_words.py tests/test_frontend_kb_editors.py -q` → PASS.
`test_frontend_plain_words.py` refuses pipeline words in user-facing strings; "cluster", "cosine"
and "embedder" must not appear in rendered copy (the percentage is fine).

**Step 7: Commit**

```bash
git add frontend/lib/kb-groom.ts frontend/lib/kb-groom.test.ts frontend/lib/types.ts frontend/lib/api.ts frontend/components/career/groom-dialog.tsx frontend/components/career/points-list.tsx frontend/components/career/entity-detail.tsx backend/tests/test_frontend_kb_stale_wording.py
git commit -m "feat(web): Tidy bullets, a per-item review of similar bullets that retires only on a click"
```

---

### Task 8: The drift popover

**Files:**
- Create: `frontend/lib/kb-drift.ts`, `frontend/lib/kb-drift.test.ts`
- Modify: `frontend/components/career/points-list.tsx` (the "Wording differs" chip)
- Modify: `backend/tests/test_frontend_kb_stale_wording.py`

**Step 1: Write the failing pure-module tests**

`frontend/lib/kb-drift.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { driftRows } from "./kb-drift.ts";
import type { KBPointOut } from "./types.ts";

type Usage = KBPointOut["usage"][number];
const usage = (over: Partial<Usage>): Usage =>
  ({ resume_key: "hybrid", section: "experience", ported_text: "x", ported_at: "2026-10-01T00:00:00Z", drifted: true, direction: "from_source", ...over });
const point = (rows: Usage[]): Pick<KBPointOut, "usage"> => ({ usage: rows });

test("only drifted from_source rows get Use this wording; to_resume rows get the hint", () => {
  const rows = driftRows(point([
    usage({ ported_text: "resume words", direction: "from_source" }),
    usage({ resume_key: "compact", ported_text: "older words", direction: "to_resume" }),
    usage({ resume_key: "legacy", ported_text: "legacy words", direction: null }),
    usage({ resume_key: "same", ported_text: "the point's words", drifted: false }),
  ]));
  assert.deepEqual(rows, [
    { resumeKey: "hybrid", section: "experience", text: "resume words", adoptable: true },
    { resumeKey: "compact", section: "experience", text: "older words", adoptable: false },
    { resumeKey: "legacy", section: "experience", text: "legacy words", adoptable: false },
  ]);
});

test("two resumes with the same differing wording list once per resume", () => {
  const rows = driftRows(point([
    usage({ resume_key: "a", ported_text: "w" }),
    usage({ resume_key: "b", ported_text: "w" }),
    usage({ resume_key: "a", ported_text: "w" }),
  ]));
  assert.deepEqual(rows.map((r) => r.resumeKey), ["a", "b"]);
});
```

Run: `cd frontend && node --test lib/kb-drift.test.ts` → FAIL.

**Step 2: The pure module**

`frontend/lib/kb-drift.ts`:

```ts
/**
 * The Drifted badge's popover rows: each resume wording that differs from the bullet, and whether
 * it can be adopted. Pure (`kb-drift.test.ts`).
 */
import type { KBPointOut } from "./types";

export interface DriftRow {
  resumeKey: string;
  section: string;
  text: string;
  /** A from_source note is the user's own base wording: one click adopts it. A to_resume port
   *  (or a legacy row) means the bullet was edited after it was sent; adopting would revert that. */
  adoptable: boolean;
}

export function driftRows(point: Pick<KBPointOut, "usage">): DriftRow[] {
  const seen = new Set<string>();
  const rows: DriftRow[] = [];
  for (const u of point.usage) {
    if (!u.drifted) continue;
    const key = `${u.resume_key}\u0000${u.section}\u0000${u.ported_text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      resumeKey: u.resume_key,
      section: u.section,
      text: u.ported_text,
      adoptable: u.direction === "from_source",
    });
  }
  return rows;
}
```

Run: `cd frontend && node --test lib/kb-drift.test.ts` → PASS.

**Step 3: Write the failing source pin**

Append to `backend/tests/test_frontend_kb_stale_wording.py`:

```python
def test_drifted_badge_is_a_popover_with_use_this_wording_on_source_rows_only():
    src = _read("components/career/points-list.tsx")
    row = src[src.index("function PointRow(") :]
    assert "driftRows(point)" in row
    assert "Reworded on a resume" in row
    assert "Use this wording" in row
    assert "Send to resume to update it" in row
    assert "row.adoptable ?" in row or "adoptable ?" in row
    assert '"Bullet updated"' in row
    assert "PopoverTrigger" in row
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py -q` → FAIL.

**Step 4: The popover**

In `frontend/components/career/points-list.tsx` `PointRow`:

- `const rows = driftRows(point);` replaces `hasDrift`; the chip renders when `rows.length > 0`.
- Wrap the chip in `Popover` / `PopoverTrigger` (the chip becomes the trigger button, keep its
  words "Wording differs" and the warning icon) with `PopoverContent`:
  - `PopoverTitle` "Reworded on a resume".
  - One block per row: a muted line `{resumeName(row.resumeKey)} · {sectionWord(row.section)}`
    (import `SECTION_ORDER_LABELS` or reuse the inbox's `sectionWord`; move `sectionWord` into
    `frontend/lib/formatting.ts` if both files need it), the quoted wording, then either a
    **Use this wording** button (`row.adoptable`) or the hint line "Send to resume to update it".
  - `useResumeKeyLabel` already covers these keys: pass `[...usageKeys]`.
- Use this wording: `updateOnce({ payload: { text: row.text }, message: "Bullet updated", undoable: false })`,
  then a toast Undo that PATCHes the old text back: extend the `update` mutation's variables with
  `undoText?: string` and the Undo handler to `patchKbPoint(updated.id, { text: undoText })` when
  present (today's Undo only knows `state: "draft"`; branch on which was given).
- The web PATCH keeps the state, so an approved point stays approved. After adoption the badge
  clears on the refetch (the note now equals the text).

**Step 5: Gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py tests/test_frontend_kb_editors.py tests/test_frontend_plain_words.py -q` → PASS.

**Step 6: Commit**

```bash
git add frontend/lib/kb-drift.ts frontend/lib/kb-drift.test.ts frontend/components/career/points-list.tsx frontend/lib/formatting.ts frontend/components/career/inbox-panel.tsx backend/tests/test_frontend_kb_stale_wording.py
git commit -m "feat(web): the Drifted badge opens the resume wordings, with Use this wording for the base's own"
```

(Include `formatting.ts` and `inbox-panel.tsx` only if `sectionWord` moved.)

---

### Task 9: MCP tools

**Files:**
- Modify: `backend/mcp_server/client.py` (`get_kb_groom`)
- Modify: `backend/mcp_server/server.py` (`kb_groom_entity`, `kb_retire_points`, `kb_sync_base` docstring)
- Modify: `backend/mcp_server/profiles.py` (`CAREER_TOOLS`)
- Modify: `plugins/maestro-career-studio/README.md:79` (the approval list)
- Test: `backend/mcp_server/tests/test_server.py`, `backend/mcp_server/tests/test_profiles.py`,
  `backend/mcp_server/tests/test_client_onboarding.py`

**Step 1: Write the failing tests**

`backend/mcp_server/tests/test_client_onboarding.py`:

```python
@respx.mock
def test_get_kb_groom_reads_the_entity_report():
    route = respx.get(f"{BASE}/api/kb/entities/e1/groom").mock(
        return_value=httpx.Response(200, json={"entity_id": "e1", "entity_title": "Orbit",
                                               "compared_wording": True, "active_points": 2, "clusters": []})
    )
    out = BackendClient(BASE).get_kb_groom("e1")
    assert out["clusters"] == []
    assert route.called


@respx.mock
def test_kb_sync_base_passes_compared_wording_through():
    respx.post(f"{BASE}/api/base-resumes/hybrid/kb-sync").mock(
        return_value=httpx.Response(200, json={"created": 0, "items_added": 0, "drifted": 0, "renamed": [],
                                               "skipped": [], "skills": [], "skills_added": [],
                                               "last_kb_synced_at": None, "compared_wording": False})
    )
    assert BackendClient(BASE).kb_sync_base("hybrid")["compared_wording"] is False
```

`backend/mcp_server/tests/test_server.py`: add `"kb_groom_entity"` and `"kb_retire_points"` to
`KB_TOOL_NAMES`; add to `_PINNED_HINTS`:

```python
    # Read-only report; proposes, writes nothing.
    "kb_groom_entity": (True, False, True, False),
    # Reversible from /career (Use again), so not destructive; the same ids twice is a no-op.
    "kb_retire_points": (False, False, True, False),
```

and three tests near `test_kb_sync_base_docstring_is_draft_only_and_deterministic`:

```python
def test_kb_sync_base_docstring_names_the_compared_flag():
    doc = (srv.kb_sync_base.__doc__ or "").lower()
    assert "compared_wording" in doc


def test_kb_groom_entity_is_read_only_and_wires_to_the_report(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "get_kb_groom", lambda entity_id: seen.update(id=entity_id) or {"clusters": []})
    assert srv.kb_groom_entity("e1") == {"clusters": []}
    assert seen == {"id": "e1"}
    doc = (srv.kb_groom_entity.__doc__ or "").lower()
    assert "deterministic" in doc and "zero llm" in doc.replace("-", " ")
    assert "kb_retire_points" in doc


def test_kb_retire_points_is_the_consent_gated_retire_twin(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        srv._client, "kb_approve_points",
        lambda ids, state="approved": seen.update(ids=ids, state=state) or {"results": [{"id": i, "ok": True, "state": "retired"} for i in ids]},
    )
    _SettingsDown.install(monkeypatch)  # the hint is best-effort, as for kb_approve_points
    out = srv.kb_retire_points(["p1", "p2"])
    assert seen == {"ids": ["p1", "p2"], "state": "retired"}
    assert [r["state"] for r in out["results"]] == ["retired", "retired"]
    assert out["next"] is None
    approve_doc = srv.kb_approve_points.__doc__ or ""
    retire_doc = srv.kb_retire_points.__doc__ or ""
    # The same gate, stated the same way: the state written is the user's decision.
    assert "user's decision" in approve_doc and "user's decision" in retire_doc
    assert "reversible" in retire_doc.lower()
```

`backend/mcp_server/tests/test_profiles.py`, in
`test_career_profile_registers_onboarding_tools_and_hunt_does_not`, add `"kb_groom_entity"` and
`"kb_retire_points"` to `new_tools`.

Run: `cd backend && .venv/bin/python -m pytest mcp_server/tests/test_server.py mcp_server/tests/test_profiles.py mcp_server/tests/test_client_onboarding.py -q` → FAIL.

**Step 2: Client**

In `backend/mcp_server/client.py` after `kb_sync_base`:

```python
    def get_kb_groom(self, entity_id: str) -> Any:
        return self._request("GET", f"/api/kb/entities/{entity_id}/groom")
```

**Step 3: Server**

In `backend/mcp_server/server.py`, after `kb_list_points` (the read block):

```python
@mcp.tool(**_read("Find Similar Career Points"))
@_guard
def kb_groom_entity(entity_id: str) -> Any:
    """Similar bullets on one Career KB entity, clustered, with a proposed keeper.
    Deterministic and zero LLM calls: the pinned local embedder scores every pair of
    the entity's active points (drafts included, retired and user_cannot_confirm
    excluded) and joins pairs at 0.80 cosine and above, minus pairs the user marked
    "Not the same" at /career. Proposes only; nothing is written. Each cluster
    carries score, keeper_id, members [{id, text, state, origin, provenance,
    usage_count, best_score}] and pairs. The keeper rule is approved over draft,
    then most recently updated, then longest text. compared_wording is false when
    the embedder could not run; clusters is then empty. Acting on a cluster is
    kb_retire_points with the ids the user drops."""
    return _client.get_kb_groom(entity_id)
```

After `kb_approve_points` (the write block):

```python
@mcp.tool(**_write("Retire Career Points", destructive=False, idempotent=True))
@_guard
def kb_retire_points(point_ids: list[str]) -> Any:
    """Batch-retire Career KB points: they stop being offered to resumes and the
    career export; resumes that already use them keep their text. Reversible
    from /career (Use again). The state written is the user's decision about
    the listed points; the server does not check that the user reviewed them
    (a convention, not enforcement, the same gate as kb_approve_points).

    1-500 ids; repeats collapse to one result row. Per-id results are honest:
    unknown ids return ok=false detail="not found" and the rest still proceed.
    Response is {results: [{id, ok, state, detail}], next}; next is a hint
    (null when suppressed or unavailable).
    """
    body = _client.kb_approve_points(point_ids, state="retired")
    results = body.get("results") or [] if isinstance(body, dict) else []
    return {
        "results": results,
        "next": _best_effort_hint(
            lambda: workflow.next_after_bulk_state(
                results,
                requested_state="retired",
                allowed_tools=_active_allowed_tools(),
                hints_enabled=_hints_enabled(),
            )
        ),
    }
```

`kb_sync_base`'s docstring gains: "Returns compared_wording: false means the embedder could not
run, so every bullet was added as new with no link to the bullet it may rewrite; the result then
reads 'Couldn't compare wording'." Keep the words `deterministic`, `draft`, `never edits`,
`safe to rerun` that the existing pin reads. Mind `_BANNED_VOICE` in `test_server.py`: no "call
only", "tell the user", "prefer", "never call" in either docstring; state facts.

`backend/mcp_server/profiles.py`: add `"kb_groom_entity"` and `"kb_retire_points"` to
`CAREER_TOOLS`. `full` is `None` and registers everything.

`plugins/maestro-career-studio/README.md` line 79: add `kb_retire_points` after
`kb_approve_points` in the Codex approval list; if `.codex-plugin`/`.claude-plugin` JSON carries
a tool approval list, add it there too (grep `kb_approve_points` under `plugins/`;
`tests/test_plugin_declarations.py` pins what exists).

**Step 4: Run the MCP tests, then the suite**

Run: `cd backend && .venv/bin/python -m pytest mcp_server/tests/ -q -n auto --dist loadfile` → PASS.
`test_every_tool_carries_a_title_and_explicit_hints`, `test_only_llm_and_sync_tools_are_open_world`
and the docstring budget test cover the new tools automatically.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 5: Commit**

```bash
git add backend/mcp_server/client.py backend/mcp_server/server.py backend/mcp_server/profiles.py backend/mcp_server/tests/test_server.py backend/mcp_server/tests/test_profiles.py backend/mcp_server/tests/test_client_onboarding.py plugins/maestro-career-studio/README.md
git commit -m "feat(mcp): kb_groom_entity reads similar bullets; kb_retire_points is the consent-gated retire twin"
```

---

### Task 10: Docs, changelog and the gates

**Files:**
- Modify: `docs/entities/others.md` (the Career KB paragraph, "Base→KB sync" sentence onward)
- Modify: `docs/agent-surfaces.md` (the MCP server bullet that names `kb_sync_base` and `kb_approve_points`)
- Modify: `docs/frontend-conventions.md` (Career history section)
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Modify: `SYSTEM.md` only where it describes sync tiers or the KB write surface (grep
  `base_sync`, `kb_approve_points`); no new §6 invariant, no dated line in §1–§10.

**Step 1: `docs/entities/others.md`**

In the Career KB paragraph, after the "Base→KB sync" sentences, rewrite in present tense:

> **Base→KB sync** classifies without an LLM: exact normalized match → `in_sync`; best same-item
> cosine ≥ 0.90 (`SYNC_DRIFT_COSINE`) → `drift` (a `from_source` note, never a point); 0.80 ≤
> cosine < 0.90 (`SYNC_REPLACES_COSINE`) → `new` with `replaces_point_id` set on the draft it
> writes; else `new`. Candidates are the item's active points minus `user_cannot_confirm`. A
> linked draft still counts as `new`. `classify`/`apply` return `compared_wording`, false when the
> embedder raised (every bullet then reads as new, unlinked, and the UI says so). The draft inbox
> shows the replaced bullet; `PATCH /api/kb/points/{id}` and `POST /api/kb/points/bulk-state`
> take `retire_replaced` (honoured only on an approve with a live, unretired target; each bulk
> row reports `retired_replaced`). Moving a draft to another item nulls the link; deleting the
> target SET NULLs it. **Groom** (`services/kb_groom.py`, `GET /api/kb/entities/{id}/groom`) is
> read-only and LLM-free: one `embed_texts` call over the item's active points (drafts in,
> retired and `user_cannot_confirm` out), edges at `SYNC_REPLACES_COSINE` minus
> `kb_point_kept_pairs`, single-link components of two or more, keeper = approved > most recently
> updated > longest > id; retiring is the bulk-state endpoint. `POST`/`DELETE
> /api/kb/points/keep-apart {point_ids}` records/forgets every pair among same-item ids
> (canonical `point_a_id < point_b_id`, cascade with either point). The Drifted badge's popover
> offers "Use this wording" on `from_source` rows only (`PATCH {text}`, state unchanged).
> Provenance is never read to rank or written by any of these paths (`inv-provenance-no-decay`,
> pinned by the three new writers in `test_no_writer_flips_user_cannot_confirm`).

Keep the existing sentences about `recorded` and the pill's N.

**Step 2: `docs/agent-surfaces.md`**

In the MCP server bullet that lists the KB tools, after `kb_approve_points`: "`kb_groom_entity`
(read-only similar-bullet report per entity, zero LLM calls) and `kb_retire_points` (the retire
twin of `kb_approve_points`, same convention gate, `destructive=False` because Use again reverses
it); both in the `career` and `full` profiles. `kb_sync_base` returns `compared_wording`."

**Step 3: `docs/frontend-conventions.md`**

In the Career history section, add two sentences: the draft inbox's **Replaces this bullet**
block (shown only for a live link; a switch **Retire the old bullet**, on by default; Approve
sends `retire_replaced`; Approve all's dialog carries one checkbox "Also retire the N bullets
they replace", absent at zero; decisions in `lib/kb-replaces.ts`); the entity page's **Tidy
bullets** dialog (`career/groom-dialog.tsx`, shown with two or more active bullets; one decision
per cluster, "Keep this one" radio with the proposed keeper, **Retire the other(s)** and **Not the
same**, no retire-all; decisions in `lib/kb-groom.ts`); and the **Wording differs** chip as a
popover (`lib/kb-drift.ts`; "Use this wording" on the base's own rows, "Send to resume to update
it" on ported rows).

**Step 4: `CHANGELOG.md`**

Under `## [Unreleased]`, in the owner's voice for the opener (one or two sentences, plain), then
`### Added` bullets: the replaces link and retire-on-approve; Tidy bullets; the drift popover;
the two MCP tools. `### Changed`: sync says when it could not compare wording. `### Fixed`
(if the owner agrees it reads as a fix): a sync that could not load the embedder no longer reads
every bullet as new silently. One schema migration, noted.

**Step 5: SYSTEM.md**

Grep SYSTEM.md for `base_sync`, `kb_approve_points`, `kb_sync_base`; where a sentence describes
the sync ladder or the KB tool list, integrate (rewrite in present tense, no dated paragraph).
Add nothing to §6; `inv-provenance-no-decay`'s pin test grew instead. Then:

```bash
python3 scripts/check_system_md.py
```

Expected: clean. If the byte cap trips, the new sentence belongs in `docs/entities/others.md`
(already written) and SYSTEM.md keeps one clause pointing there.

**Step 6: The full gates**

```bash
cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile
```

```bash
cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint && npm run build
```

```bash
python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend && python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend
```

Expected: all pass. `complexity_hotspots` is a count; if it is the only regressing metric,
re-baseline with `baseline <surface>` and say so in the commit body. Name each surface scanned in
the claim.

**Step 7: Commit**

```bash
git add docs/entities/others.md docs/agent-surfaces.md docs/frontend-conventions.md CHANGELOG.md SYSTEM.md backend/.slop-baseline.json frontend/.slop-baseline.json
git commit -m "docs: career history stops collecting stale wording (sync link, retire on approve, Tidy bullets, drift popover, two MCP tools)"
```

(Include the baseline files only if re-baselined.)

---

## Design §7 test list, mapped to tasks

| Design §7 item | Task | Test |
|---|---|---|
| classify: 0.80–0.90 is `new` with link and score | 2 | `test_rewrite_in_the_band_is_new_with_a_replaces_link` |
| classify: 0.79 has none | 2 | `test_under_the_band_is_new_with_no_link` |
| classify: 0.90 is still `drift` | 2 | `test_above_the_band_is_still_drift_without_a_link` (at 0.92; the 0.90 value itself is pinned by `test_the_two_bands_are_the_designed_constants`, see "The hermetic embedder in tests") |
| classify: retired or `user_cannot_confirm` never the target | 2 | `test_a_retired_or_unconfirmable_point_is_never_the_target` |
| classify: `compared_wording` false, no links when `embed_texts` raises | 2 | `test_embedder_failure_reports_itself_and_links_nothing` |
| classify: existing tests unchanged | 2 | the file's pre-existing tests, unedited |
| apply: draft carries the link; twice is a no-op | 2 | `test_apply_writes_the_link_onto_the_draft_and_twice_is_a_noop` |
| apply: link always on the draft's own item | 2 | `test_link_target_is_always_on_the_drafts_own_item` |
| router: inbox resolves `replaces` | 3 | `test_inbox_resolves_the_replaced_bullet` |
| router: `retire_replaced` on approve retires and reports | 3 | `test_approve_with_retire_replaced_retires_the_target_and_reports_it` |
| router: ignored when not approving / no link / target retired | 3 | `test_retire_replaced_is_ignored_when_not_approving_or_without_a_live_link` |
| router: moving the draft clears the link | 3 | `test_moving_the_draft_to_another_item_clears_the_link` |
| router: deleting the target nulls it (SET NULL) | 1, 3 | `test_point_replaces_link_round_trips_and_nulls_when_the_target_goes`, `test_deleting_the_target_nulls_the_link` |
| router: bulk-state with `retire_replaced` | 3 | `test_bulk_state_with_retire_replaced_reports_each_retired_target` |
| groom: fixed vectors → deterministic clusters | 6 | `test_fixed_vectors_give_deterministic_clusters_and_single_link_joins_a_chain` |
| groom: single link joins a chain | 6 | same |
| groom: keeper rule in each tiebreak order | 6 | `test_keeper_rule_in_each_tiebreak_order` |
| groom: kept pairs break an edge | 6 | `test_kept_pairs_break_an_edge` |
| groom: drafts included, retired and UCC excluded | 6 | `test_drafts_included_retired_and_unconfirmable_excluded` |
| groom: one-point item is empty | 6 | `test_one_point_item_and_no_similar_pairs_are_empty` |
| groom: embedder failure sets `compared_wording` false | 6 | `test_embedder_failure_sets_compared_wording_false` |
| keep-apart: canonical order, idempotent | 6 | `test_keep_apart_records_every_pair_canonically_and_is_idempotent` |
| keep-apart: same-item 400 | 6 | `test_keep_apart_requires_one_item_and_known_points` |
| keep-apart: cascade on point delete; DELETE forgets | 1, 6 | `test_kept_pairs_cascade_with_either_point`, `test_keep_apart_delete_forgets_and_point_delete_cascades` |
| provenance pin gains the three new writers | 3 | `test_no_writer_flips_user_cannot_confirm` (extended) |
| no-LLM pin for sync and groom | 2, 6 | `test_sync_never_calls_the_llm`, `test_groom_never_calls_the_llm` |
| `test_db_portability.py` picks up the column and table | 1 | runs unchanged; `test_migration_model_parity.py` is the one that fails without the migration |
| MCP: `kb_groom_entity` wires to the GET | 9 | `test_kb_groom_entity_is_read_only_and_wires_to_the_report`, `test_get_kb_groom_reads_the_entity_report` |
| MCP: `kb_retire_points` honours the gate and forwards ids | 9 | `test_kb_retire_points_is_the_consent_gated_retire_twin` |
| MCP: `kb_sync_base` passes `compared_wording` through | 9 | `test_kb_sync_base_passes_compared_wording_through`, `test_kb_sync_base_docstring_names_the_compared_flag` |
| web: sync words gain the line only when false | 4 | the two tests in `kb-sync-words.test.ts` |
| web: Replaces block only with a live link; switch defaults on; Approve sends `retire_replaced`; Approve-all count, absent at zero | 5 | `kb-replaces.test.ts` + `test_inbox_row_renders_the_replaces_block_from_the_pure_module`, `test_approve_all_offers_to_retire_the_replaced_bullets` |
| web: groom dialog keeper preselected; Retire the other(s) sends non-selected; Not the same sends every pair; empty and failed states | 7 | `kb-groom.test.ts` + the two groom pins |
| web: drift popover, button on `from_source` only, hint on `to_resume` | 8 | `kb-drift.test.ts` + `test_drifted_badge_is_a_popover_with_use_this_wording_on_source_rows_only` |

## After the last task

Run the goal-critique against the Goal Card, not against this plan: open `/career` on a fresh
stack (recipe in the owner's `worktree-verification-recipe` memory), sync a base whose bullet was
reworded, approve the draft with the switch on, open Tidy bullets on an item with two near
bullets, and click one Drifted badge. Each of those five principles should be visible on screen:
no LLM spinner, nothing changed before a click, provenance chips unchanged, the retire copy
naming resumes, and an honest line when the embedder is off (`EMBEDDINGS_OUT_OF_PROCESS` with a
broken model path simulates it). Then `superpowers:finishing-a-development-branch`.
