# Career history stale wording Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (a fresh Opus 5.5
> subagent per task, review between tasks: the owner's routing rule) or superpowers:executing-plans
> (one session, checkpoints) to implement this plan task-by-task. Every task is TDD: the failing test
> first, then the smallest code that passes it, then a commit.

Design: `docs/plans/2026-10-17-career-history-stale-wording-design.md`, the **claims with
wordings** form revised with the owner on 2026-10-19. Read it in full before Task 1; its "Owner
decisions" and the three rules under "The model" are not reopened here.

## Where this plan departs from the design

Nothing in the behaviour departs. Three mechanics are decided here because the design left them to
the plan; each is named so a reviewer can object before code lands.

1. **Frontend tests run on pure modules, as the design asks; the component wiring is pinned by
   source tests.** `node --test` has no DOM, so the wordings and groom decisions live in two small
   pure modules (`frontend/lib/kb-wordings.ts`, `frontend/lib/kb-groom.ts`) that the design's
   frontend tests exercise directly. That the components call them is pinned the way
   `backend/tests/test_kb_sync_frontend.py` already pins the sync pill: by reading the source.
2. **Embedder failure is a flag on `Placement`, folded by `classify`.** `kb_claims.place` returns
   `compared`, the `SyncItem` carries it, and `classify` reports `compared_wording = all(...)`.
   Nothing module-global: the route runs in threads.
3. **`usage_count` on a groom member counts distinct resumes from `kb_port_log` rows whose
   `direction` is not `from_source`** (placements, as the points list's "On N resumes" chip counts
   them). The design names the number and not the query.

Process notes: the design commit was cherry-picked onto this branch (`12057bc7`); the first-form
plan (f47e9d73) is replaced by this file in full.

## Goal Card

**Goal:** Clicking Add on an edited base resume must not grow career history by a row per rewrite.
A rewrite folds into the claim it rewrites as a wording; only a genuinely new claim asks for
review; each claim reads as one line with every resume's phrasing underneath; and the user can
combine, split, adopt a wording or retire with one click, never by surprise.

**Principles** (how to decide when the plan is ambiguous or wrong):
- Zero LLM calls in intake and groom. `services/ats/embeddings` is the only comparison seam.
- One notion of "the same claim": `kb_claims.place` is the only place the band is applied.
- Nothing combined, retired, split or rewritten without a click. Intake only attaches wordings.
- A wording is never offered to a resume; only a claim's main line is.
- `KBPoint.provenance` is never read to rank and never written (`inv-provenance-no-decay`).
- Retiring and combining never edit a resume; the copy says so wherever either is offered.
- When the embedder is unavailable, say so; never read as "all new" or "nothing similar".

**Non-goals:** routing import, document mint or the write-backs through `place` (follow-ups);
an LLM "neutral version"; a KB-wide groom count; the dash-variant near-identity miss.

**Autonomy:** peer (adapt-and-advise). Opus 5.5 may adapt *how* when the plan meets repo reality
it did not foresee, logs every deviation in the commit body with a one-line reason, and raises
anything touching scope, a wire shape another task depends on, or a Goal Card line as a deviation
note before building it. Scope is never self-expanded.

---

**Goal:** Build the design's ten steps: the schema, the intake function and the sync rung, the
wordings read model, combine/unmerge/split, the groom service and endpoints, the sync words, the
wordings popover, the Tidy bullets dialog, three MCP tools, and the docs.

**Architecture:** One Alembic revision adds `kb_points.merged_into_point_id` (self-referencing,
SET NULL) and `kb_point_kept_pairs`. A new `services/kb_claims.py` holds `place(text, points)`,
the one band; `kb_base_sync._ladder_bullet` calls it and maps `wording` to today's wire tier
`drift`, so a rewrite writes one `from_source` note and no point. `_to_point_out` derives a
`wordings` list from four sources. Three new routes (`combine`, `split-wording`, `groom`) plus
`keep-apart` and a PATCH flag `unmerge`. The web replaces the Drifted badge with a wordings
popover and adds a Tidy bullets dialog whose primary action is Combine. MCP gets
`kb_groom_entity` (read), `kb_combine_points` and `kb_retire_points` (write, the
`kb_approve_points` convention).

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

- **Intake and groom make zero LLM calls.** `app.services.llm.call_openai` is monkeypatched to
  raise in the pins; keep it that way.
- **Nothing touches `KBPoint.provenance`.** No read of it to rank (excluding `user_cannot_confirm`
  from candidates is allowed), no write of it anywhere. Split creates a NEW point stamped
  `user_authored` because the text is the user's own resume sentence.
- **Nothing is applied silently.** Intake writes a `from_source` note (what drift always did) and
  retires, combines or rewrites nothing. Groom returns a report and writes nothing. Combine,
  retire, split and adoption are user gestures or an agent call the user said yes to.
- **Retiring and combining never edit a resume.**
- **`SYNC_WORDING_COSINE = 0.80` is one constant in `kb_claims`**, read by sync and groom. The old
  `SYNC_DRIFT_COSINE` name goes away (its only reader is `kb_base_sync` itself).
- **The wire tier for a wording is still `drift`** (`counts.drift`, `counts.recorded_drift`,
  `SyncResult.drifted`): the frontend types, MCP callers and the recorded seen-set all keep
  working; only the words change.
- **Public repo:** fixtures use made-up names (Acme, Globex, Orbit). Never a real employer or person.
- **Frontend copy:** the word is **bullet**, resumes are named through `useResumeKeyLabel` /
  `useBaseResumeLabel`, retire reads "Won't be offered again" / "Stop using" as the points list
  already does. `test_frontend_plain_words.py` refuses pipeline words ("cluster", "cosine",
  "embedder", "claim") in rendered copy; the percentage is fine.
- **Tests pin wire shapes and behaviour, not implementation**; existing tests in the files the
  design names pass unchanged unless a task says which assertion moves and why.

## The hermetic embedder in tests

`backend/tests/conftest.py` patches `app.services.ats.embeddings.embed_texts` with a fake whose
known strings have hand-built vectors (`tests/ats/fixtures.py`); nothing there scores between
0.80 and 0.90. The intake and groom tests therefore install their own table of unit vectors
through the same seam. `kb_claims.place` imports `embed_texts` from the module at call time, so a
per-test `monkeypatch.setattr(embeddings, "embed_texts", fake)` wins over the autouse fixture.
Vectors are 3-D: a unit vector at cosine `c` to `(1, 0, 0)` is `(c, sqrt(1 - c*c), 0)`, and a
text unrelated to everything sits on the third axis, `(0, 0, 1)`, so it scores 0 against all of
them (two vectors in the same plane are never "far" from each other: `(0.85, 0.53, 0)` against
`(0.79, 0.61, 0)` is 0.99).

| cosine wanted to `(1, 0, 0)` | vector |
|---|---|
| 1.00 | `(1.0, 0.0, 0.0)` |
| 0.92 | `(0.92, 0.39192, 0.0)` |
| 0.85 | `(0.85, 0.52678, 0.0)` |
| 0.79 | `(0.79, 0.61311, 0.0)` |
| unrelated | `(0.0, 0.0, 1.0)` |

Do not test the exact 0.80 boundary with vectors: the fake's norm is off by about 1e-7 and the
comparison is `>=`, so 0.80 lands on either side by machine. The constant's value is pinned by
equality; the band is tested at 0.85 (in) and 0.79 (out).

Put these helpers in a new `backend/tests/kb_vectors.py` (importable by every KB test; not a
test module itself):

```python
"""Fixed unit vectors for the Career KB intake and groom tests (see the plan's
"The hermetic embedder in tests"). 3-D so an unrelated text can sit on its own axis."""


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


OLD = "Built the ingestion pipeline"
REWRITE = "Built and ran the ingestion pipeline for finance"      # 0.85 to OLD: a wording
UNDER = "Built the ingestion pipeline and its dashboards"        # 0.79 to OLD: just under, new
CLOSE = "Built the ingestion pipelines"                          # 0.92 to OLD: a wording
FAR = "Negotiated a net-new vendor contract"                     # unrelated to all

BAND = {
    OLD: (1.0, 0.0, 0.0),
    REWRITE: (0.85, 0.52678, 0.0),
    UNDER: (0.79, 0.61311, 0.0),
    CLOSE: (0.92, 0.39192, 0.0),
    FAR: (0.0, 0.0, 1.0),
}
```

---

### Task 1: Migration and models

**Files:**
- Create: `backend/migrations/versions/<rev>_kb_points_merged_into_and_kept_pairs.py`
- Modify: `backend/app/models/career_kb.py` (KBPoint, new `KBPointKeptPair`, `kept_pair_key`)
- Modify: `backend/app/models/__init__.py` (register `KBPointKeptPair`)
- Test: `backend/tests/test_career_kb_models.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_career_kb_models.py`:

```python
import pytest

from app.models.career_kb import KBPointKeptPair, kept_pair_key


def _two_points(db_session, state_a="approved", state_b="approved"):
    entity = KBEntity(kind="project", title="Orbit")
    db_session.add(entity)
    db_session.flush()
    a = KBPoint(entity_id=entity.id, text="keeper wording", state=state_a, origin="manual")
    db_session.add(a)
    db_session.flush()
    b = KBPoint(entity_id=entity.id, text="other wording", state=state_b, origin="base_sync")
    db_session.add(b)
    db_session.flush()
    return entity, a, b


def test_merged_into_round_trips_and_nulls_when_the_keeper_goes(db_session):
    _entity, keeper, loser = _two_points(db_session)
    loser.state = "retired"
    loser.merged_into_point_id = keeper.id
    db_session.commit()
    assert db_session.get(KBPoint, loser.id).merged_into.text == "keeper wording"

    db_session.delete(keeper)
    db_session.commit()
    db_session.expire_all()
    survivor = db_session.get(KBPoint, loser.id)
    assert survivor is not None
    assert survivor.merged_into_point_id is None
    assert survivor.merged_into is None


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
    # The claim this one was combined into (Tidy bullets → Combine). A merged
    # point is retired and shown as a WORDING of its keeper, not in the retired
    # group. SET NULL when the keeper is deleted; cleared by PATCH unmerge (the
    # split, and Combine's Undo). One direction only.
    merged_into_point_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(as_uuid=True), ForeignKey("kb_points.id", ondelete="SET NULL"), index=True
    )
```

and after `entity: Mapped[KBEntity] = relationship(back_populates="points")`:

```python
    merged_into: Mapped["KBPoint | None"] = relationship(
        "KBPoint", remote_side=[id], foreign_keys=[merged_into_point_id]
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
`__all__` (alphabetical, beside `KBPoint`).

**Step 4: The migration**

Generate the id and check the head first:

```bash
cd backend && .venv/bin/python -c "import uuid; print(uuid.uuid4().hex[:12])" && .venv/bin/python -m alembic heads
```

Expected head today: `e5a1c2d77b04` (re-read it; another branch may have landed). Create
`backend/migrations/versions/<rev>_kb_points_merged_into_and_kept_pairs.py`:

```python
"""kb_points.merged_into_point_id and kb_point_kept_pairs

The pointer Combine writes from a folded claim to the one it was folded into, and the pairs
the user marked "Not the same" so groom stops proposing them. Impl types only (sa.Uuid /
sa.DateTime), like the baseline: a revision never imports app code.

Adding a foreign key makes batch mode recreate kb_points (SQLite's move-and-copy).
migrations/env.py runs with foreign_keys OFF on purpose, so dropping the old table fires no
CASCADE into kb_port_log. Never run this chain through app.db.make_engine.

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
        batch_op.add_column(sa.Column("merged_into_point_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_kb_points_merged_into_point_id",
            "kb_points",
            ["merged_into_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_kb_points_merged_into_point_id", ["merged_into_point_id"], unique=False
        )
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
        batch_op.drop_index("ix_kb_points_merged_into_point_id")
        batch_op.drop_constraint("fk_kb_points_merged_into_point_id", type_="foreignkey")
        batch_op.drop_column("merged_into_point_id")
```

**Step 5: Run the model, parity and portability tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_career_kb_models.py tests/test_migration_model_parity.py tests/test_db_portability.py -q`
Expected: PASS. If parity reports an `add_fk`/`remove_fk` pair for `kb_points`, name the model's
foreign key to match (`ForeignKey("kb_points.id", ondelete="SET NULL", name="fk_kb_points_merged_into_point_id")`)
and log that in the commit body.

**Step 6: Commit**

```bash
git add backend/migrations/versions/*_kb_points_merged_into_and_kept_pairs.py backend/app/models/career_kb.py backend/app/models/__init__.py backend/tests/test_career_kb_models.py
git commit -m "feat(kb): a claim can be combined into another; kept pairs table"
```

---

### Task 2: `kb_claims.place` and the sync rung

**Files:**
- Create: `backend/app/services/kb_claims.py`
- Modify: `backend/app/services/kb_base_sync.py`
- Modify: `backend/app/schemas/kb_sync.py`
- Modify: `backend/app/routers/base_resumes.py:939-971` (`kb_sync_status`)
- Create: `backend/tests/kb_vectors.py` (from "The hermetic embedder in tests")
- Create: `backend/tests/test_kb_claims.py`
- Test: `backend/tests/test_kb_base_sync_classify.py`, `backend/tests/test_kb_base_sync_apply.py`,
  `backend/tests/test_kb_sync_router.py`

**Step 1: Write the failing `place` tests**

`backend/tests/test_kb_claims.py`:

```python
"""kb_claims.place: the one decision 'does this text restate a claim on this item?'"""

import pytest

from app.models.career_kb import KBEntity, KBPoint
from app.services import kb_claims
from tests.kb_vectors import BAND, CLOSE, FAR, OLD, REWRITE, UNDER, _embedder_down, _vectors


def _points(db_session, *specs):
    """specs: (text, state, provenance)."""
    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    out = []
    for text, state, provenance in specs:
        p = KBPoint(entity_id=ent.id, text=text, state=state, origin="manual", provenance=provenance)
        db_session.add(p)
        db_session.flush()
        out.append(p)
    return out


def test_the_band_is_the_designed_constant():
    assert kb_claims.SYNC_WORDING_COSINE == 0.80


def test_exact_match_is_in_sync_before_any_embedding(db_session, monkeypatch):
    _embedder_down(monkeypatch)  # must not even be consulted
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place("  built THE ingestion   pipeline ", [old])
    assert (placed.kind, placed.point, placed.compared) == ("in_sync", old, True)


def test_in_band_is_a_wording_with_the_point_and_score(db_session, monkeypatch):
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(REWRITE, [old])
    assert placed.kind == "wording"
    assert placed.point == old
    assert placed.score == pytest.approx(0.85, abs=0.01)
    assert kb_claims.place(CLOSE, [old]).kind == "wording"


def test_under_the_band_is_new(db_session, monkeypatch):
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(UNDER, [old])
    assert (placed.kind, placed.point, placed.score) == ("new", None, None)


@pytest.mark.parametrize("state,provenance", [("retired", "user_authored"), ("approved", "user_cannot_confirm")])
def test_retired_and_unconfirmable_points_are_never_targets(db_session, monkeypatch, state, provenance):
    _vectors(monkeypatch, BAND)
    far, old = _points(db_session, (FAR, "approved", "user_authored"), (OLD, state, provenance))
    assert kb_claims.candidates([far, old]) == [far]
    placed = kb_claims.place(REWRITE, kb_claims.candidates([far, old]))
    assert placed.kind == "new"


def test_embedder_failure_is_reported_not_hidden(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    placed = kb_claims.place(REWRITE, [old])
    assert (placed.kind, placed.point, placed.compared) == ("new", None, False)


def test_no_points_means_new_and_compared(db_session, monkeypatch):
    _embedder_down(monkeypatch)
    placed = kb_claims.place(REWRITE, [])
    assert (placed.kind, placed.compared) == ("new", True)


def test_place_never_calls_the_llm(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("intake must not call the LLM")),
    )
    _vectors(monkeypatch, BAND)
    (old,) = _points(db_session, (OLD, "approved", "user_authored"))
    kb_claims.place(REWRITE, [old])
```

**Step 2: Write the failing sync tests**

Append to `backend/tests/test_kb_base_sync_classify.py` (import `pytest` and
`from tests.kb_vectors import BAND, CLOSE, OLD, REWRITE, UNDER, _embedder_down, _vectors`):

```python
def _point(db_session, entity, text, *, state="approved", provenance="user_authored"):
    point = KBPoint(entity_id=entity.id, text=text, state=state, origin="manual", provenance=provenance)
    db_session.add(point)
    db_session.flush()
    return point


def _one_bullet(bullet):
    return _resume(
        experience=[{"company": "Acme", "role": "Engineer", "start_date": "2021", "bullets": [bullet]}]
    )


def _classified(db_session, tmp_path, monkeypatch, bullet):
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(bullet))
    report = kb_base_sync.classify(db_session, "hybrid")
    (item,) = [i for i in report["items"] if i.section == "experience"]
    return report, item


def test_a_rewrite_in_the_band_is_a_wording_not_a_new_bullet(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert item.tier == "drift"  # the wire tier for a wording
    assert item.matched_point_id == ent.points[0].id
    assert report["counts"] == {"in_sync": 0, "drift": 1, "recorded_drift": 0, "new": 0, "skills_new": 0}
    assert report["compared_wording"] is True


def test_under_the_band_is_new(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    _exp_entity(db_session, text=OLD)
    report, item = _classified(db_session, tmp_path, monkeypatch, UNDER)
    assert item.tier == "new"
    assert item.matched_point_id is None
    assert report["counts"]["new"] == 1


def test_a_close_rewrite_is_still_a_wording(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    _report, item = _classified(db_session, tmp_path, monkeypatch, CLOSE)
    assert item.tier == "drift"
    assert item.matched_point_id == ent.points[0].id


@pytest.mark.parametrize("state,provenance", [("retired", "user_authored"), ("approved", "user_cannot_confirm")])
def test_a_retired_or_unconfirmable_point_is_never_the_target(
    db_session, tmp_path, monkeypatch, state, provenance
):
    from tests.kb_vectors import FAR

    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=FAR)  # the only live point is unrelated
    _point(db_session, ent, OLD, state=state, provenance=provenance)
    _report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert item.tier == "new"
    assert item.matched_point_id is None  # OLD would have matched at 0.85; it is not a candidate


def test_embedder_failure_reports_itself(db_session, tmp_path, monkeypatch):
    _embedder_down(monkeypatch)
    _exp_entity(db_session, text=OLD)
    report, item = _classified(db_session, tmp_path, monkeypatch, REWRITE)
    assert report["compared_wording"] is False
    assert item.tier == "new"
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

Append to `backend/tests/test_kb_base_sync_apply.py` (import `BAND, OLD, REWRITE, _vectors`
from `tests.kb_vectors` and `_one_bullet` from the classify module):

```python
def test_a_rewrite_writes_one_wording_note_and_no_point(db_session, tmp_path, monkeypatch):
    _vectors(monkeypatch, BAND)
    ent = _exp_entity(db_session, text=OLD)
    old = ent.points[0]
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    first = kb_base_sync.apply(db_session, "hybrid")
    assert (first["created"], first["drifted"], first["compared_wording"]) == (0, 1, True)
    assert db_session.query(KBPoint).count() == 1  # no second bullet
    log = db_session.scalars(select(KBPortLog)).one()
    assert (log.point_id, log.direction, log.ported_text) == (old.id, "from_source", REWRITE)
    db_session.refresh(old)
    assert (old.text, old.state) == (OLD, "approved")  # the claim itself is untouched

    second = kb_base_sync.apply(db_session, "hybrid")
    assert (second["created"], second["drifted"]) == (0, 0)
    assert db_session.query(KBPortLog).count() == 1
```

Append to `backend/tests/test_kb_sync_router.py`:

```python
def test_kb_sync_status_and_apply_carry_the_compared_flag(db_session, tmp_path, monkeypatch):
    from tests.kb_vectors import BAND, OLD, REWRITE, _vectors
    from tests.test_kb_base_sync_classify import _one_bullet

    _vectors(monkeypatch, BAND)
    _exp_entity(db_session, text=OLD)
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        status = TestClient(app).get("/api/base-resumes/hybrid/kb-sync-status").json()
        assert status["compared_wording"] is True
        assert status["counts"]["drift"] == 1
        result = TestClient(app).post("/api/base-resumes/hybrid/kb-sync").json()
        assert result["compared_wording"] is True
    finally:
        app.dependency_overrides.clear()
```

**Step 3: Run the four files to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_claims.py tests/test_kb_base_sync_classify.py tests/test_kb_base_sync_apply.py tests/test_kb_sync_router.py -q`
Expected: `test_kb_claims.py` FAILS on import; the new sync tests FAIL (`compared_wording`
KeyError, 0.85 reads as `new`); every pre-existing test still passes.

**Step 4: The intake function**

`backend/app/services/kb_claims.py`:

```python
"""The one decision behind every Career KB intake: does this text restate a claim
already on this item (in sync), rephrase one (a wording), or say something new?

Deterministic and LLM-free: an exact normalized match, else the pinned local
embedder (services/ats/embeddings) against the item's active claims. Base sync
calls it today; import, the document mint and the write-backs are follow-ups,
so "the same claim" comes to mean one thing everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.career_kb import KBPoint
from app.services.kb_consolidation import point_text_key

# A bullet whose best same-item match scores here or above is a WORDING of that
# claim, never a second bullet. Shared with services/kb_groom so "similar" means
# one thing. Owner decision 2026-10-17/19: not 0.75 (half the extra hits are
# distinct claims), not 0.85 (misses half the real rewrites).
SYNC_WORDING_COSINE = 0.80


@dataclass(frozen=True)
class Placement:
    kind: str  # "in_sync" | "wording" | "new"
    point: KBPoint | None
    score: float | None
    # False when the embedder raised: kind is then "new" with no point, and the
    # caller must say so instead of reading it as "nothing similar".
    compared: bool = True


def candidates(points: list[KBPoint]) -> list[KBPoint]:
    """Claims a text may match: active, and never user_cannot_confirm (retired
    anyway; this guards the invariant on its own). Provenance is read only to
    exclude, never to rank or write."""
    return [p for p in points if p.state != "retired" and p.provenance != "user_cannot_confirm"]


def place(text: str, points: list[KBPoint]) -> Placement:
    key = point_text_key(text)
    for point in points:
        if point_text_key(point.text) == key:
            return Placement("in_sync", point, None)
    if not points:
        return Placement("new", None, None)
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([text] + [p.text for p in points])
    except Exception:
        return Placement("new", None, None, compared=False)
    best_point: KBPoint | None = None
    best_score = -1.0
    for point, vector in zip(points, vectors[1:], strict=True):
        score = cosine(vectors[0], vector)
        if score > best_score:
            best_score, best_point = score, point
    if best_point is not None and best_score >= SYNC_WORDING_COSINE:
        return Placement("wording", best_point, round(best_score, 4))
    return Placement("new", None, None)
```

**Step 5: The sync rung**

In `backend/app/services/kb_base_sync.py`:

- Delete `SYNC_DRIFT_COSINE` and `_best_cosine`. Import `from app.services.kb_claims import candidates, place`.
- `SyncItem` gains `compared_wording: bool = True` with the comment "False when this item could not
  be compared because the embedder raised; it then reads as new, and the report says so."
- `_ladder_bullet` becomes:

```python
def _ladder_bullet(text: str, entity: KBEntity) -> SyncItem:
    section = entity.kind if entity.kind != "project" else "projects"
    placed = place(text, candidates(_active_points(entity)))
    # "wording" rides the wire as today's "drift" tier: one from_source note on
    # the matched claim, no point (see _apply_drift). Counts, the recorded
    # seen-set and every reader keep their meaning.
    tier = {"in_sync": "in_sync", "wording": "drift", "new": "new"}[placed.kind]
    return SyncItem(
        tier=tier,
        section=section,
        entity_id=entity.id,
        entity_proposal=None,
        matched_point_id=placed.point.id if placed.point is not None else None,
        text=text,
        compared_wording=placed.compared,
    )
```

- `classify` adds `"compared_wording": all(i.compared_wording for i in items),` to its return dict.
- `apply` adds `"compared_wording": report["compared_wording"],` to its return dict.
- Update the module docstring: "Per bullet: exact match → in sync; a match at or above
  `kb_claims.SYNC_WORDING_COSINE` → a wording note (tier `drift`); else a new draft."

**Step 6: Schema and route**

`backend/app/schemas/kb_sync.py`: `SyncStatus` and `SyncResult` each gain

```python
    # False when the embedder raised: every bullet then read as "new" with no
    # match, and the UI says "Couldn't compare wording" instead of "all new".
    compared_wording: bool = True
```

`backend/app/routers/base_resumes.py` `kb_sync_status`: add
`compared_wording=report["compared_wording"],` to the `SyncStatus(...)` call. `kb_sync_apply`
returns the service dict unchanged, so the flag rides through.

**Step 7: Run the files, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_claims.py tests/test_kb_base_sync_classify.py tests/test_kb_base_sync_apply.py tests/test_kb_sync_router.py -q`
Expected: PASS, all pre-existing tests unchanged (the hermetic 0.96 pair is still drift, 0.28 is
still new).

Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
Expected: PASS.

**Step 8: Commit**

```bash
git add backend/app/services/kb_claims.py backend/app/services/kb_base_sync.py backend/app/schemas/kb_sync.py backend/app/routers/base_resumes.py backend/tests/kb_vectors.py backend/tests/test_kb_claims.py backend/tests/test_kb_base_sync_classify.py backend/tests/test_kb_base_sync_apply.py backend/tests/test_kb_sync_router.py
git commit -m "feat(kb): one place() decides in-sync, wording or new; sync keeps a rewrite as a wording at 0.80"
```

---

### Task 3: The wordings read model

**Files:**
- Modify: `backend/app/schemas/career_kb.py` (`KBWordingOut`, `KBPointOut.wordings`,
  `KBPointOut.merged_into_point_id`)
- Modify: `backend/app/services/career_kb.py` (`wordings_of`, `_to_point_out`, `entity_detail`)
- Modify: `backend/app/routers/career_kb.py` (`list_points`)
- Create: `backend/tests/test_kb_wordings.py`

**Step 1: Write the failing tests**

`backend/tests/test_kb_wordings.py`:

```python
"""A claim's wordings: where else it was phrased, derived on read from four sources;
and the writes that move text between claim and wording (combine, unmerge, split)."""

import uuid

from app.models.career_kb import KBPoint, KBPortLog


def _entity(client, title="Orbit"):
    return client.post("/api/kb/entities", json={"kind": "project", "title": title}).json()["id"]


def _point(db_session, entity_id, text, *, state="approved", provenance="user_authored",
           merged_into=None, merge_sources=None, origin="manual"):
    point = KBPoint(
        entity_id=uuid.UUID(entity_id), text=text, state=state, origin=origin,
        provenance=provenance, merged_into_point_id=merged_into, merge_sources_json=merge_sources,
    )
    db_session.add(point)
    db_session.commit()
    return point


def _log(db_session, point, *, resume_key, text, direction, source_text=None, section="projects"):
    db_session.add(KBPortLog(
        entity_id=point.entity_id, point_id=point.id, resume_kind="base", resume_key=resume_key,
        section=section, ported_text=text, source_text=source_text, direction=direction,
    ))
    db_session.commit()


def _wordings(client, point_id):
    rows = client.get("/api/kb/points?limit=500").json()
    return next(r for r in rows if r["id"] == str(point_id))["wordings"]


def test_wordings_come_from_all_four_sources_with_the_right_affordances(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching",
                   merge_sources=[{"resume_key": "imported", "section": "projects", "text": "Lowered latency 30% with a cache"}])
    _log(db_session, claim, resume_key="hybrid", text="Cut p95 latency 30% by caching hot keys", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="Cut latency 30% via caching (old copy)", direction="to_resume")
    folded = _point(db_session, eid, "Reduced latency by a third using Redis", state="retired", merged_into=claim.id)
    rows = _wordings(client, claim.id)
    by_kind = {r["kind"]: r for r in rows}
    assert set(by_kind) == {"resume", "placed", "import", "merged"}
    assert by_kind["resume"] == {
        "kind": "resume", "text": "Cut p95 latency 30% by caching hot keys", "resume_keys": ["hybrid"],
        "section": "projects", "point_id": None, "adoptable": True, "splittable": True,
    }
    assert (by_kind["placed"]["adoptable"], by_kind["placed"]["splittable"]) == (False, False)
    assert (by_kind["import"]["adoptable"], by_kind["import"]["splittable"]) == (True, False)
    assert by_kind["merged"]["point_id"] == str(folded.id)
    assert (by_kind["merged"]["adoptable"], by_kind["merged"]["splittable"]) == (True, True)


def test_one_row_per_distinct_text_and_the_lines_own_text_is_never_a_wording(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Cut latency 30% via caching")
    _log(db_session, claim, resume_key="hybrid", text="Cut p95 latency 30%", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="cut p95   latency 30%", direction="from_source")
    _log(db_session, claim, resume_key="same", text="Cut latency 30% via caching", direction="from_source")
    _log(db_session, claim, resume_key="kept", text="Cut latency 30% via caching", direction="to_resume")
    rows = _wordings(client, claim.id)
    assert len(rows) == 1
    assert rows[0]["resume_keys"] == ["compact", "hybrid"]


def test_entity_detail_lists_the_merged_claim_under_its_keeper(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Keeper")
    folded = _point(db_session, eid, "Folded", state="retired", merged_into=keeper.id)
    detail = client.get(f"/api/kb/entities/{eid}").json()
    by_id = {p["id"]: p for p in detail["points"]}
    assert by_id[str(folded.id)]["merged_into_point_id"] == str(keeper.id)
    assert by_id[str(keeper.id)]["wordings"][0] == {
        "kind": "merged", "text": "Folded", "resume_keys": [], "section": None,
        "point_id": str(folded.id), "adoptable": True, "splittable": True,
    }
    assert by_id[str(keeper.id)]["merged_into_point_id"] is None
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_wordings.py -q` → FAIL (`KeyError: 'wordings'`).

**Step 2: Schema**

In `backend/app/schemas/career_kb.py`, before `KBPointOut`:

```python
class KBWordingOut(BaseModel):
    """One other phrasing of a claim and what the user may do with it.

    resume:  a resume's rewording (a from_source port-log row); adopt or split.
    placed:  an older copy a resume still carries (a to_resume or legacy row whose
             snapshot differs); neither, with the hint "Send to resume to update it",
             because adopting it would revert a KB edit.
    merged:  a claim combined into this one (its retired point); adopt or split.
    import:  an imported resume's text (merge_sources_json); adopt only.
    One row per distinct normalized text; a text equal to the claim's own line is
    never a wording."""

    kind: Literal["resume", "placed", "merged", "import"]
    text: str
    resume_keys: list[str] = Field(default_factory=list)
    section: str | None = None
    point_id: UUID | None = None
    adoptable: bool
    splittable: bool
```

`KBPointOut` gains, after `usage`:

```python
    wordings: list[KBWordingOut] = Field(default_factory=list)
    # Set on a retired claim that was combined into another; the points list
    # shows it under its keeper, not in the retired group.
    merged_into_point_id: UUID | None = None
```

**Step 3: Service**

In `backend/app/services/career_kb.py`, next to `_usage_from_logs`:

```python
def wordings_of(
    point: KBPoint, port_logs: Sequence[KBPortLog], merged: Sequence[KBPoint]
) -> list[KBWordingOut]:
    """The claim's other phrasings, one row per distinct normalized text, in the
    order: resume rewordings, older placed copies, combined claims, imported text."""
    own = point_text_key(point.text)
    rows: dict[str, KBWordingOut] = {}

    def add(kind: str, text: str, *, resume_key: str | None = None, section: str | None = None,
            point_id=None, adoptable: bool, splittable: bool) -> None:
        key = point_text_key(text)
        if not key or key == own:
            return
        row = rows.get(key)
        if row is None:
            rows[key] = KBWordingOut(kind=kind, text=text.strip(), resume_keys=[], section=section,
                                     point_id=point_id, adoptable=adoptable, splittable=splittable)
            row = rows[key]
        if resume_key and resume_key not in row.resume_keys:
            row.resume_keys.append(resume_key)
            row.resume_keys.sort()

    for log in port_logs:
        if log.direction == "from_source":
            add("resume", log.ported_text, resume_key=log.resume_key, section=log.section,
                adoptable=True, splittable=True)
        else:
            snapshot = log.source_text if log.source_text is not None else log.ported_text
            add("placed", snapshot or "", resume_key=log.resume_key, section=log.section,
                adoptable=False, splittable=False)
    for other in merged:
        add("merged", other.text, point_id=other.id, adoptable=True, splittable=True)
    for src in point.merge_sources_json or []:
        if isinstance(src, dict) and isinstance(src.get("text"), str):
            add("import", src["text"], resume_key=src.get("resume_key"), section=src.get("section"),
                adoptable=True, splittable=False)
    return list(rows.values())
```

(`from app.services.kb_consolidation import point_text_key`; import `KBWordingOut`.) A `placed`
row only appears when the snapshot differs from the line, which `add` already enforces through
`key == own`.

`_to_point_out` gains a `merged: Sequence[KBPoint] | None = None` parameter; when `None` it
queries `select(KBPoint).where(KBPoint.merged_into_point_id == point.id)` itself, and when
`port_logs` is `None` it loads them as `point_usage` does. It passes
`wordings=wordings_of(point, logs, merged)` and `merged_into_point_id=point.merged_into_point_id`.

`entity_detail` already has every point of the item, so `merged` for point `p` is
`[q for q in points if q.merged_into_point_id == p.id]`: no extra query.

**Step 4: Router**

`list_points`: after collecting `logs_by_point`, one query for merged children:

```python
    merged_by_keeper = defaultdict(list)
    if ids:
        for child in db.scalars(select(KBPoint).where(KBPoint.merged_into_point_id.in_(ids))).all():
            merged_by_keeper[child.merged_into_point_id].append(child)
```

and pass `merged=merged_by_keeper.get(point.id, [])` to `_to_point_out`.

**Step 5: Run the file, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_wordings.py tests/test_career_kb_router.py tests/test_kb_port.py -q` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 6: Commit**

```bash
git add backend/app/schemas/career_kb.py backend/app/services/career_kb.py backend/app/routers/career_kb.py backend/tests/test_kb_wordings.py
git commit -m "feat(kb): every claim lists its wordings, derived from notes, placements, combined claims and imports"
```

---

### Task 4: Combine, unmerge and split

**Files:**
- Modify: `backend/app/services/kb_claims.py` (`combine`, `split_wording`)
- Modify: `backend/app/schemas/career_kb.py` (`KBPointPatch.unmerge`, `KBCombineRequest`,
  `KBSplitWordingRequest`)
- Modify: `backend/app/routers/career_kb.py` (`combine_points`, `split_wording`, `patch_point`)
- Test: `backend/tests/test_kb_wordings.py`, `backend/tests/test_kb_provenance_stamping.py`

**Step 1: Write the failing route tests**

Append to `backend/tests/test_kb_wordings.py`:

```python
def test_combine_retires_and_points_the_losers_and_leaves_the_keeper_alone(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Cleansed 2M rows nightly")
    a = _point(db_session, eid, "Cleansed and validated 2M rows", state="draft")
    b = _point(db_session, eid, "Validated 2M rows every night")
    _log(db_session, b, resume_key="hybrid", text=b.text, direction="to_resume")
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(a.id), str(b.id)]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(keeper.id)
    assert body["text"] == "Cleansed 2M rows nightly"
    assert {w["point_id"] for w in body["wordings"]} == {str(a.id), str(b.id)}
    for p in (a, b):
        db_session.refresh(p)
        assert (p.state, p.merged_into_point_id, p.approved_at) == ("retired", keeper.id, None)
        assert p.provenance == "user_authored"
    db_session.refresh(keeper)
    assert (keeper.state, keeper.provenance) == ("approved", "user_authored")
    # the loser's own placement history stays its own: nothing moved
    assert db_session.query(KBPortLog).filter_by(point_id=b.id).count() == 1
    # idempotent
    r = client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(a.id)]})
    assert r.status_code == 200


def test_combine_refuses_mixed_items_a_retired_or_unconfirmable_keeper_and_unknown_ids(client, db_session):
    eid, other = _entity(client), _entity(client, "Elsewhere")
    keeper = _point(db_session, eid, "Keeper")
    mine = _point(db_session, eid, "Mine")
    theirs = _point(db_session, other, "Theirs")
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(theirs.id)]}).status_code == 400
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(uuid.uuid4())]}).status_code == 404
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(keeper.id)]}).status_code == 400
    keeper.state = "retired"
    db_session.commit()
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(mine.id)]}).status_code == 400
    ucc = _point(db_session, eid, "Cannot confirm", provenance="user_cannot_confirm")
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(ucc.id), "point_ids": [str(mine.id)]}).status_code == 400


def test_unmerge_patch_clears_the_pointer_and_sets_the_state_given(client, db_session):
    eid = _entity(client)
    keeper = _point(db_session, eid, "Keeper")
    folded = _point(db_session, eid, "Folded", state="retired", merged_into=keeper.id)
    r = client.patch(f"/api/kb/points/{folded.id}", json={"state": "draft", "unmerge": True})
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["merged_into_point_id"]) == ("draft", None)
    assert _wordings(client, keeper.id) == []
    # unmerge alone, no state: the pointer clears, the state stays
    folded2 = _point(db_session, eid, "Folded again", state="retired", merged_into=keeper.id)
    r = client.patch(f"/api/kb/points/{folded2.id}", json={"unmerge": True})
    assert (r.json()["state"], r.json()["merged_into_point_id"]) == ("retired", None)


def test_split_wording_makes_an_approved_claim_and_moves_the_rows(client, db_session):
    from tests.kb_vectors import OLD, REWRITE

    eid = _entity(client)
    claim = _point(db_session, eid, OLD, origin="base_sync")
    _log(db_session, claim, resume_key="hybrid", text=REWRITE, direction="from_source", source_text=REWRITE, section="experience")
    _log(db_session, claim, resume_key="compact", text=REWRITE, direction="from_source", source_text=REWRITE, section="experience")
    r = client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": REWRITE, "resume_key": None})
    assert r.status_code == 200, r.text
    new = r.json()
    assert (new["text"], new["state"], new["origin"], new["provenance"]) == (REWRITE, "approved", "base_sync", "user_authored")
    assert new["entity_id"] == eid
    moved = db_session.scalars(select(KBPortLog).where(KBPortLog.point_id == uuid.UUID(new["id"]))).all()
    assert sorted(l.resume_key for l in moved) == ["compact", "hybrid"]
    assert _wordings(client, claim.id) == []
    assert db_session.get(KBPoint, uuid.UUID(new["id"])).merged_into_point_id is None


def test_after_a_split_the_resume_bullet_reads_in_sync(client, db_session, tmp_path, monkeypatch):
    """The exact-match rung finds the new claim first, so no embedding is needed."""
    from app.services import kb_base_sync
    from tests.kb_vectors import OLD, REWRITE
    from tests.test_kb_base_sync_classify import _exp_entity, _one_bullet, _seed_base

    ent = _exp_entity(db_session, text=OLD)
    claim = ent.points[0]
    _log(db_session, claim, resume_key="hybrid", text=REWRITE, direction="from_source",
         source_text=REWRITE, section="experience")
    _seed_base(db_session, tmp_path, monkeypatch, _one_bullet(REWRITE))
    assert kb_base_sync.classify(db_session, "hybrid")["counts"]["recorded_drift"] == 1
    assert client.post(f"/api/kb/points/{claim.id}/split-wording",
                       json={"text": REWRITE, "resume_key": None}).status_code == 200
    counts = kb_base_sync.classify(db_session, "hybrid")["counts"]
    assert (counts["in_sync"], counts["recorded_drift"], counts["new"]) == (1, 0, 0)


def test_split_wording_with_a_resume_key_moves_only_that_resumes_rows(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Line")
    _log(db_session, claim, resume_key="hybrid", text="Other words", direction="from_source")
    _log(db_session, claim, resume_key="compact", text="Other words", direction="from_source")
    r = client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": "Other words", "resume_key": "hybrid"})
    assert r.status_code == 200
    (left,) = _wordings(client, claim.id)
    assert left["resume_keys"] == ["compact"]
    assert client.post(f"/api/kb/points/{claim.id}/split-wording", json={"text": "Never noted", "resume_key": None}).status_code == 404


def test_adoption_keeps_the_state_and_clears_the_row(client, db_session):
    eid = _entity(client)
    claim = _point(db_session, eid, "Line")
    _log(db_session, claim, resume_key="hybrid", text="Better line", direction="from_source")
    r = client.patch(f"/api/kb/points/{claim.id}", json={"text": "Better line"})
    assert (r.json()["state"], r.json()["text"], r.json()["wordings"]) == ("approved", "Better line", [])
```

(`from sqlalchemy import select` at the top.) The "in sync afterwards" test seeds an experience
item through `_exp_entity` because sync only ladders experience and project bullets; the
`recorded_drift` → `in_sync` flip is the whole point of re-pointing the rows.

**Step 2: Extend the provenance pins**

In `backend/tests/test_kb_provenance_stamping.py`:

- Add a site driver for split-wording and register it in `SITE_DRIVERS` as
  `"split_wording": (_drive_split_wording, "user_authored")`, so the existing parametrized
  `test_every_point_creation_site_stamps_provenance` gains the `[split_wording]` case:

```python
def _drive_split_wording(db_session, monkeypatch, tmp_path):
    from app.db import get_db
    from app.main import app
    from app.models.career_kb import KBPortLog

    ent = KBEntity(kind="project", title="Orbit")
    db_session.add(ent)
    db_session.flush()
    claim = KBPoint(entity_id=ent.id, text="Shipped the pipeline", state="approved", origin="manual", provenance="user_stated")
    db_session.add(claim)
    db_session.flush()
    db_session.add(KBPortLog(entity_id=ent.id, point_id=claim.id, resume_kind="base", resume_key="hybrid",
                             section="projects", ported_text="Shipped the data pipeline to prod", direction="from_source"))
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        body = TestClient(app).post(
            f"/api/kb/points/{claim.id}/split-wording",
            json={"text": "Shipped the data pipeline to prod", "resume_key": None},
        ).json()
    finally:
        app.dependency_overrides.clear()
    return db_session.get(KBPoint, UUID(body["id"]))
```

(the file already imports `uuid4` from `uuid`; widen that line to `from uuid import UUID, uuid4`.)

- In `test_no_writer_flips_user_cannot_confirm`, after the `kb_ingest.capture` block, drive the
  new writers against the record and assert its provenance is unchanged:

```python
    # The writers this design adds: combine (as a loser and as a refused keeper),
    # bulk retire, split-wording and adoption. None reads or writes provenance.
    from app.db import get_db
    from app.main import app

    keeper = KBPoint(entity_id=ent.id, text="A keeper claim", state="approved", origin="manual", provenance="user_stated")
    db_session.add(keeper)
    db_session.flush()
    db_session.add(KBPortLog(entity_id=ent.id, point_id=point_id, resume_kind="base", resume_key="hybrid",
                             section="projects", ported_text="A resume phrasing", direction="from_source"))
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        assert client.post("/api/kb/points/combine", json={"keeper_id": str(keeper.id), "point_ids": [str(point_id)]}).status_code == 200
        assert client.patch(f"/api/kb/points/{point_id}", json={"state": "approved", "unmerge": True}).status_code == 200
        assert client.post("/api/kb/points/bulk-state", json={"ids": [str(point_id)], "state": "retired"}).status_code == 200
        assert client.post(f"/api/kb/points/{point_id}/split-wording", json={"text": "A resume phrasing", "resume_key": None}).status_code == 200
        assert client.patch(f"/api/kb/points/{point_id}", json={"text": "Adopted wording from a resume"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
    db_session.expire_all()
    assert db_session.get(KBPoint, point_id).provenance == "user_cannot_confirm"
```

(`KBPortLog` import at the top of the file.)

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_wordings.py tests/test_kb_provenance_stamping.py -q` → FAIL on the new tests.

**Step 3: Schemas**

```python
class KBPointPatch(BaseModel):
    text: str | None = None
    state: str | None = None
    tags: list[str] | None = None
    entity_id: UUID | None = None
    # Clears merged_into_point_id. With state in the same PATCH it is the split
    # of a combined claim and the Undo of a combine; alone it only clears.
    unmerge: bool = False
    ...


class KBCombineRequest(BaseModel):
    """Tidy bullets → Combine: the keeper stays the claim; every other point is
    retired and pointed at it, so it reads as one of the keeper's wordings."""

    keeper_id: UUID
    point_ids: list[UUID] = Field(min_length=1, max_length=50)


class KBSplitWordingRequest(BaseModel):
    """Make a resume wording its own bullet: a new approved claim on the same
    item with this text, and the matching from_source rows re-pointed to it.
    resume_key narrows to one resume's rows; None moves every row with this text."""

    text: str
    resume_key: str | None = None

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must be non-empty")
        return stripped
```

**Step 4: Service**

Append to `backend/app/services/kb_claims.py`:

```python
from datetime import UTC, datetime  # top of file

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career_kb import KBPortLog


class CombineError(ValueError):
    """A combine the server refuses; the message is the user's sentence."""


def combine(db: Session, keeper: KBPoint, others: list[KBPoint]) -> None:
    """Retire `others` and point them at `keeper`. Only state, approved_at and
    merged_into_point_id move; text, provenance and the losers' own placement
    history stay where they are. Reversible with PATCH unmerge."""
    if keeper.state == "retired" or keeper.provenance == "user_cannot_confirm":
        raise CombineError("That bullet can't be the one to keep.")
    for other in others:
        if other.id == keeper.id:
            raise CombineError("A bullet can't be combined into itself.")
        if other.entity_id != keeper.entity_id:
            raise CombineError("These bullets are on different items.")
    for other in others:
        other.state = "retired"
        other.approved_at = None
        other.merged_into_point_id = keeper.id


def split_wording(db: Session, claim: KBPoint, text: str, resume_key: str | None) -> KBPoint:
    """A resume wording becomes its own approved claim on the same item, and the
    from_source rows that carried it follow the words. Raises LookupError when no
    row matches (the wording is not one the KB noted)."""
    key = point_text_key(text)
    stmt = select(KBPortLog).where(KBPortLog.point_id == claim.id, KBPortLog.direction == "from_source")
    if resume_key is not None:
        stmt = stmt.where(KBPortLog.resume_key == resume_key)
    rows = [r for r in db.scalars(stmt).all() if point_text_key(r.ported_text) == key]
    if not rows:
        raise LookupError("That wording isn't one your resumes noted.")
    new = KBPoint(
        entity_id=claim.entity_id,
        text=text,
        state="approved",
        approved_at=datetime.now(UTC),
        origin="base_sync",
        provenance="user_authored",  # the user's own resume sentence
    )
    db.add(new)
    db.flush()
    for row in rows:
        row.point_id = new.id
    return new
```

**Step 5: Router**

In `backend/app/routers/career_kb.py`, declared right after `bulk_point_state` and BEFORE the
`/points/{point_id}` routes:

```python
@router.post("/points/combine", response_model=KBPointOut)
def combine_points(payload: KBCombineRequest, db: Annotated[Session, Depends(get_db)]):
    """Tidy bullets → Combine. The keeper is returned with its new wordings."""
    keeper = db.get(KBPoint, payload.keeper_id)
    others = [db.get(KBPoint, pid) for pid in dict.fromkeys(payload.point_ids)]
    if keeper is None or any(p is None for p in others):
        raise HTTPException(status_code=404, detail="Point not found")
    try:
        kb_claims.combine(db, keeper, others)
    except kb_claims.CombineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(keeper)
    career_exports.best_effort_refresh(db)
    return svc._to_point_out(db, keeper)


@router.post("/points/{point_id}/split-wording", response_model=KBPointOut)
def split_wording(point_id: UUID, payload: KBSplitWordingRequest, db: Annotated[Session, Depends(get_db)]):
    """Make a resume wording its own bullet."""
    claim = db.get(KBPoint, point_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Point not found")
    try:
        new = kb_claims.split_wording(db, claim, payload.text, payload.resume_key)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    db.commit()
    db.refresh(new)
    career_exports.best_effort_refresh(db)
    return svc._to_point_out(db, new)
```

`patch_point`: after the `state` block add

```python
    if payload.unmerge:
        point.merged_into_point_id = None
```

The `/points/{point_id}/split-wording` path has a literal tail, so it cannot collide with the
PATCH/DELETE on `/points/{point_id}`; `/points/combine` must still come before them.

**Step 6: Run the files, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_wordings.py tests/test_kb_provenance_stamping.py tests/test_kb_points_bulk_state.py tests/test_career_kb_router.py -q` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 7: Commit**

```bash
git add backend/app/services/kb_claims.py backend/app/schemas/career_kb.py backend/app/routers/career_kb.py backend/tests/test_kb_wordings.py backend/tests/test_kb_provenance_stamping.py
git commit -m "feat(kb): combine two claims into one, split a wording back out, unmerge; all on a click"
```

---

### Task 5: Groom service and endpoints

**Files:**
- Create: `backend/app/services/kb_groom.py`
- Modify: `backend/app/schemas/career_kb.py` (`GroomMember`, `GroomCluster`, `GroomReport`,
  `KBKeepApartRequest`, `KBKeepApartResponse`)
- Modify: `backend/app/routers/career_kb.py` (three routes)
- Create: `backend/tests/test_kb_groom.py`

**Step 1: Write the failing tests**

`backend/tests/test_kb_groom.py`:

```python
"""Read-only per-item groom: clusters of similar bullets, a proposed keeper, kept pairs."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.services import kb_groom
from tests.kb_vectors import _embedder_down, _vectors

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
    for text in texts:
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
    ent, by = _item(db_session, A, B, C, states={A: "draft", C: "retired"})
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
    assert (report.compared_wording, report.clusters) == (False, [])


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


def test_groom_never_calls_the_llm_and_writes_nothing(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kw: (_ for _ in ()).throw(AssertionError("groom must not call the LLM")),
    )
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B)
    before = {(p.id, p.state, p.text, p.updated_at, p.merged_into_point_id) for p in by.values()}
    kb_groom.groom_entity(db_session, ent.id)
    db_session.expire_all()
    after = {(p.id, p.state, p.text, p.updated_at, p.merged_into_point_id) for p in db_session.query(KBPoint)}
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
    assert r.json()["entity_title"] == "Orbit"
    assert r.json()["clusters"][0]["keeper_id"] in {str(by[A].id), str(by[B].id)}
    assert client.get(f"/api/kb/entities/{uuid.uuid4()}/groom").status_code == 404


def test_a_combined_cluster_is_gone_on_the_next_report(client, db_session, monkeypatch):
    _vectors(monkeypatch, VEC)
    ent, by = _item(db_session, A, B, C)
    (cluster,) = kb_groom.groom_entity(db_session, ent.id).clusters
    losers = [str(m.id) for m in cluster.members if m.id != cluster.keeper_id]
    assert client.post("/api/kb/points/combine", json={"keeper_id": str(cluster.keeper_id), "point_ids": losers}).status_code == 200
    report = kb_groom.groom_entity(db_session, ent.id)
    assert (report.active_points, report.clusters) == (1, [])


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
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(by2[B].id)]}).status_code == 400
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id), str(uuid.uuid4())]}).status_code == 404
    assert client.post("/api/kb/points/keep-apart", json={"point_ids": [str(by[A].id)]}).status_code == 422


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

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_groom.py -q` → FAIL on import.

**Step 2: Schemas**

In `backend/app/schemas/career_kb.py`, after the combine/split models:

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
    Nothing is written; acting is POST /api/kb/points/combine (one claim in other
    words) or POST /api/kb/points/bulk-state retired (a stale one)."""

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

**Step 3: The service**

`backend/app/services/kb_groom.py`:

```python
"""Per-item groom: similar bullets on one Career KB item, read-only.

Zero LLM calls and zero writes. Embeds the item's active bullets once through
the pinned local embedder, joins pairs at kb_claims.SYNC_WORDING_COSINE and above
(minus the pairs the user marked "Not the same"), takes single-link components
as clusters and proposes a keeper. The user combines or retires through their
own endpoints; nothing here changes a row. Re-run safe by construction.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity, KBPoint, KBPointKeptPair, KBPortLog, kept_pair_key
from app.schemas.career_kb import GroomCluster, GroomMember, GroomReport
from app.services.kb_claims import SYNC_WORDING_COSINE, candidates


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
    Stated in the dialog, so the proposal is explainable."""
    return min(
        points,
        key=lambda p: (p.state != "approved", -p.updated_at.timestamp(), -len(p.text), str(p.id)),
    )


def groom_entity(db: Session, entity_id: UUID) -> GroomReport:
    entity = db.get(KBEntity, entity_id)
    if entity is None:
        raise ValueError("Entity not found")
    points = candidates(list(entity.points))  # drafts in; retired and user_cannot_confirm out
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
            if s >= SYNC_WORDING_COSINE and key not in kept:
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

**Step 4: Routes**

In `backend/app/routers/career_kb.py` (import `kb_groom`, `KBPointKeptPair`, `kept_pair_key`,
the new schemas). The groom GET goes with the other entity routes; the keep-apart pair goes
BEFORE the `/points/{point_id}` routes, next to `combine_points`:

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

**Step 5: Run the file, then the suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_groom.py -q` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 6: Commit**

```bash
git add backend/app/services/kb_groom.py backend/app/schemas/career_kb.py backend/app/routers/career_kb.py backend/tests/test_kb_groom.py
git commit -m "feat(kb): read-only groom report per item, and kept pairs for 'Not the same'"
```

---

### Task 6: Frontend plumbing: types, fetchers and the sync words

**Files:**
- Modify: `frontend/lib/types.ts` (`KBWordingOut`, `KBPointOut`, `KBPointPatch`, `SyncStatus`,
  `SyncResult`, `GroomMember`, `GroomCluster`, `GroomReport`)
- Modify: `frontend/lib/api.ts` (`combineKbPoints`, `splitKbWording`, `getKbGroom`,
  `keepApartKbPoints`, `forgetKeepApartKbPoints`)
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

Two existing assertions move, because the words change (a rewording is kept, not noted):

- `"Added 6 draft bullets, 1 item and 1 skill to your career history. Noted 2 wording changes."`
  becomes `"… to your career history. Kept 2 rewordings."`
- `"Noted 1 wording change."` becomes `"Kept 1 rewording."`
- `"1 reworded bullet (we'll note the change)"` becomes `"1 reworded bullet (kept as a wording)"`.

Then add:

```ts
test("the reworded line says the wording is kept, in the plural too", () => {
  const lines = syncBreakdownLines(status([["drift", "experience"], ["drift", "experience"]], { drift: 2 }));
  assert.deepEqual(lines, ["2 reworded bullets (kept as wordings)"]);
});

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
def test_types_carry_wordings_and_the_compared_flag():
    source = (_FRONTEND / "lib/types.ts").read_text()
    point_block = source.split("export interface KBPointOut")[1].split("export interface")[0]
    assert "wordings: KBWordingOut[]" in point_block
    assert "merged_into_point_id: UUID | null" in point_block
    patch_block = source.split("export interface KBPointPatch")[1].split("export interface")[0]
    assert "unmerge?: boolean" in patch_block
    for name in ("SyncStatus", "SyncResult"):
        block = source.split(f"export interface {name}")[1].split("export interface")[0]
        assert "compared_wording: boolean" in block, name
    assert "export interface GroomReport" in source


def test_api_exposes_the_combine_split_groom_and_keep_apart_fetchers():
    source = (_FRONTEND / "lib/api.ts").read_text()
    for needle in ("/api/kb/points/combine", "split-wording", "/groom", "keep-apart",
                   "combineKbPoints", "splitKbWording", "getKbGroom", "keepApartKbPoints", "forgetKeepApartKbPoints"):
        assert needle in source, needle
```

Run: `cd frontend && node --test lib/kb-sync-words.test.ts` → FAIL.
Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_sync_frontend.py -q` → FAIL on the two new pins.

**Step 3: Types**

In `frontend/lib/types.ts`:

```ts
export interface KBPointPatch {
  text?: string | null;
  state?: KBPointState | null;
  tags?: string[] | null;
  entity_id?: UUID | null;
  /** Clears the "combined into" pointer. With `state` it is the split of a combined bullet. */
  unmerge?: boolean;
}

/** One other phrasing of a bullet and what can be done with it (see the backend's KBWordingOut). */
export interface KBWordingOut {
  kind: "resume" | "placed" | "merged" | "import";
  text: string;
  resume_keys: string[];
  section: string | null;
  point_id: UUID | null;
  adoptable: boolean;
  splittable: boolean;
}
```

`KBPointOut` gains `wordings: KBWordingOut[];` and `merged_into_point_id: UUID | null;` after
`usage`. `SyncStatus` and `SyncResult` each gain:

```ts
  /** False when the embedder could not run: every bullet then reads as new, nothing was matched. */
  compared_wording: boolean;
```

And the groom shapes:

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

**Step 4: Fetchers**

In `frontend/lib/api.ts` (add `GroomReport` to the types import):

```ts
export function combineKbPoints(keeperId: UUID, pointIds: UUID[]) {
  return apiFetch<KBPointOut>("/api/kb/points/combine", {
    method: "POST",
    body: JSON.stringify({ keeper_id: keeperId, point_ids: pointIds }),
  });
}

export function splitKbWording(pointId: UUID, text: string, resumeKey: string | null) {
  return apiFetch<KBPointOut>(`/api/kb/points/${pointId}/split-wording`, {
    method: "POST",
    body: JSON.stringify({ text, resume_key: resumeKey }),
  });
}

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

**Step 5: Words**

In `frontend/lib/kb-sync-words.ts`:

- The drift line: `` `${plural(drift, "reworded bullet", "reworded bullets")} (kept as ${drift === 1 ? "a wording" : "wordings"})` ``
  with the comment "Says what adding will DO: the rewording is kept under the bullet it rewrites."
- At the end of `syncBreakdownLines` before `return lines`:
  `if (!status.compared_wording) lines.push("Couldn't compare wording, so everything here reads as new.");`
- In `syncResultSentence`: the drift sentence becomes `` `Kept ${plural(result.drifted, "rewording", "rewordings")}.` ``
  and the `sentences` array gains `result.compared_wording ? null : "Couldn't compare wording.",` after it.

**Step 6: Run the gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint`
Expected: PASS. `tsc` names every place that builds a `SyncStatus`, `SyncResult` or `KBPointOut`
literal without the new required fields; add the fields there.

Run: `cd backend && .venv/bin/python -m pytest tests/test_kb_sync_frontend.py tests/test_frontend_kb_editors.py tests/test_frontend_plain_words.py -q`
Expected: PASS. If `test_kb_sync_frontend.py` pins the old "we'll note the change" words, move
that assertion with the copy and say so in the commit body.

**Step 7: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts frontend/lib/kb-sync-words.ts frontend/lib/kb-sync-words.test.ts backend/tests/test_kb_sync_frontend.py
git commit -m "feat(web): sync says a rewording is kept, and when wording could not be compared; types for wordings and groom"
```

---

### Task 7: The wordings popover

**Files:**
- Create: `frontend/lib/kb-wordings.ts`, `frontend/lib/kb-wordings.test.ts`
- Modify: `frontend/components/career/points-list.tsx` (the "Wording differs" chip and the retired group)
- Create: `backend/tests/test_frontend_kb_stale_wording.py`

**Step 1: Write the failing pure-module tests**

`frontend/lib/kb-wordings.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { splitRequest, visibleClaims, wordingActions, wordingsChip } from "./kb-wordings.ts";
import type { KBPointOut, KBWordingOut } from "./types.ts";

const w = (over: Partial<KBWordingOut>): KBWordingOut => ({
  kind: "resume", text: "x", resume_keys: ["hybrid"], section: "experience", point_id: null,
  adoptable: true, splittable: true, ...over,
});

test("the chip counts wordings and is absent at zero", () => {
  assert.equal(wordingsChip([]), null);
  assert.equal(wordingsChip([w({})]), "1 wording");
  assert.equal(wordingsChip([w({}), w({ kind: "merged", text: "y" })]), "2 wordings");
});

test("each kind gets its actions: adopt and split, adopt only, or the hint", () => {
  assert.deepEqual(wordingActions(w({ kind: "resume" })), { adopt: true, split: true, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "merged", point_id: "p2" })), { adopt: true, split: true, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "import", adoptable: true, splittable: false })), { adopt: true, split: false, hint: null });
  assert.deepEqual(wordingActions(w({ kind: "placed", adoptable: false, splittable: false })), {
    adopt: false, split: false, hint: "Send to resume to update it",
  });
});

test("split sends the right request per kind", () => {
  assert.deepEqual(splitRequest("p1", w({ kind: "resume", text: "T", resume_keys: ["hybrid"] })), {
    kind: "split-wording", pointId: "p1", text: "T", resumeKey: null,
  });
  assert.deepEqual(splitRequest("p1", w({ kind: "merged", point_id: "p2" })), {
    kind: "unmerge", pointId: "p2",
  });
  assert.equal(splitRequest("p1", w({ kind: "placed", splittable: false })), null);
});

test("a combined bullet is hidden from the list; it shows under its keeper", () => {
  const points = [
    { id: "a", state: "approved", merged_into_point_id: null },
    { id: "b", state: "retired", merged_into_point_id: "a" },
    { id: "c", state: "retired", merged_into_point_id: null },
  ] as unknown as KBPointOut[];
  assert.deepEqual(visibleClaims(points).map((p) => p.id), ["a", "c"]);
});
```

Run: `cd frontend && node --test lib/kb-wordings.test.ts` → FAIL (no module).

**Step 2: The pure module**

`frontend/lib/kb-wordings.ts`:

```ts
/**
 * A bullet's wordings on the entity page: the chip, what each wording offers, the split request
 * and which bullets the list shows at all. Pure (`kb-wordings.test.ts`).
 */
import type { KBPointOut, KBWordingOut, UUID } from "./types";

export function wordingsChip(wordings: readonly KBWordingOut[]): string | null {
  const n = wordings.length;
  return n === 0 ? null : `${n} ${n === 1 ? "wording" : "wordings"}`;
}

/** An older copy a resume still carries cannot be adopted: it would revert a KB edit. */
export const PLACED_HINT = "Send to resume to update it";

export function wordingActions(w: KBWordingOut): { adopt: boolean; split: boolean; hint: string | null } {
  return { adopt: w.adoptable, split: w.splittable, hint: w.kind === "placed" ? PLACED_HINT : null };
}

export type SplitRequest =
  | { kind: "split-wording"; pointId: UUID; text: string; resumeKey: string | null }
  | { kind: "unmerge"; pointId: UUID };

/** Make its own bullet: a resume wording splits off the claim; a combined claim comes back. */
export function splitRequest(claimId: UUID, w: KBWordingOut): SplitRequest | null {
  if (!w.splittable) return null;
  if (w.kind === "merged" && w.point_id) return { kind: "unmerge", pointId: w.point_id };
  // Every row with this text follows the words, whichever resume carried it: one row per text
  // is what the popover shows, so one click moves the whole row.
  return { kind: "split-wording", pointId: claimId, text: w.text, resumeKey: null };
}

/** The list hides a retired bullet that was combined into another: it is that bullet's wording. */
export function visibleClaims<T extends Pick<KBPointOut, "merged_into_point_id">>(points: readonly T[]): T[] {
  return points.filter((p) => p.merged_into_point_id === null);
}
```

Run: `cd frontend && node --test lib/kb-wordings.test.ts` → PASS.

**Step 3: Write the failing source pins**

Create `backend/tests/test_frontend_kb_stale_wording.py`:

```python
"""Source pins for the claims-with-wordings surfaces: the wordings popover and
the Tidy bullets dialog call their pure modules and say the designed words.
Behaviour lives in frontend/lib/*.test.ts (node --test)."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_points_list_hides_combined_bullets_and_opens_the_wordings_popover():
    src = _read("components/career/points-list.tsx")
    assert "visibleClaims(" in src
    row = src[src.index("function PointRow(") :]
    for needle in ("wordingsChip(", "wordingActions(", "splitRequest(",
                   "Wordings of this bullet", "Use as the main wording", "Make its own bullet",
                   "Combined from another bullet", "PopoverTrigger", '"Bullet updated"', "Now its own bullet",
                   "splitKbWording(", "unmerge: true"):
        assert needle in row, needle
    assert "Wording differs" not in src, "the Drifted badge is now the wordings chip"
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py -q` → FAIL.

**Step 4: The popover and the list**

In `frontend/components/career/points-list.tsx`:

- `PointsList`: `const ordered = [...visibleClaims(points)].sort(...)`. The header badge keeps
  counting `points.length`? No: count `visibleClaims(points).length`, so a combined bullet is not
  double-counted against its keeper's wording.
- `PointRow`: replace `hasDrift` and the "Wording differs" chip with:

  ```tsx
  const chip = wordingsChip(point.wordings);
  const resumeName = useResumeKeyLabel([...usageKeys, ...point.wordings.flatMap((w) => w.resume_keys)]);
  ```

  and, where the chip was, a `Popover` whose trigger is the same pill style with the text `chip`
  (only when `chip !== null`), and whose `PopoverContent` has `PopoverTitle` "Wordings of this
  bullet" and one block per wording:
  - a muted line: `resume`/`placed`/`import` → `{w.resume_keys.map(resumeName).join(", ")} · {sectionWord(w.section)}`
    (move the inbox's `sectionWord` into `frontend/lib/formatting.ts` and import it from both files);
    `merged` → "Combined from another bullet";
  - the wording text, quoted;
  - from `wordingActions(w)`: a **Use as the main wording** button when `adopt`, a **Make its own
    bullet** button when `split`, and the `hint` as muted text when set.
- **Use as the main wording**: `updateOnce({ payload: { text: w.text }, message: "Bullet updated", undoText: point.text })`.
  Extend the `update` mutation's variables with `undoText?: string`; its Undo handler PATCHes
  `{ text: undoText }` when given (today's Undo only knows `state: "draft"`; branch on which was given).
- **Make its own bullet**: `const req = splitRequest(point.id, w)`; `split-wording` →
  `splitKbWording(req.pointId, req.text, req.resumeKey)`; `unmerge` →
  `patchKbPoint(req.pointId, { state: "approved", unmerge: true })`. Toast "Now its own bullet"
  with Undo: for `split-wording`, `deleteKbPoint(newId)` is NOT a faithful undo (the rows moved),
  so the Undo for that path is `combineKbPoints(point.id, [newId])` (it becomes a `merged`
  wording of the claim, which the user can split again; the from_source rows stay on the new
  point, which is correct history); for `unmerge`, `combineKbPoints(point.id, [req.pointId])`.
  Then `invalidate()`.
- The retired group: `visibleClaims` already drops combined bullets, so nothing else changes.

Check `Popover`/`PopoverTrigger`/`PopoverContent`/`PopoverTitle` prop names in
`frontend/components/ui/popover.tsx` before writing; `POPUP_SURFACE` is its surface class.

**Step 5: Gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py tests/test_frontend_kb_editors.py tests/test_frontend_plain_words.py tests/test_kb_sync_frontend.py -q` → PASS.
`test_kb_sync_frontend.py::test_points_list_null_provenance_renders_unlabeled` reads this file;
keep `PointActorChip` as it is.

**Step 6: Commit**

```bash
git add frontend/lib/kb-wordings.ts frontend/lib/kb-wordings.test.ts frontend/lib/formatting.ts frontend/components/career/points-list.tsx frontend/components/career/inbox-panel.tsx backend/tests/test_frontend_kb_stale_wording.py
git commit -m "feat(web): every bullet opens its wordings; adopt one as the line or make it its own bullet"
```

(`inbox-panel.tsx` only for the `sectionWord` import move.)

---

### Task 8: The Tidy bullets dialog

**Files:**
- Create: `frontend/lib/kb-groom.ts`, `frontend/lib/kb-groom.test.ts`
- Create: `frontend/components/career/groom-dialog.tsx`
- Modify: `frontend/components/career/points-list.tsx` (the header button)
- Modify: `frontend/components/career/entity-detail.tsx` (pass `entityTitle`)
- Modify: `backend/tests/test_frontend_kb_stale_wording.py`

**Step 1: Write the failing pure-module tests**

`frontend/lib/kb-groom.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { combinedToast, groomState, otherIds, pairsOf } from "./kb-groom.ts";
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

test("Combine sends every member but the selected keeper", () => {
  assert.deepEqual(otherIds(cluster, "a"), ["b", "c"]);
  assert.deepEqual(otherIds(cluster, "c"), ["a", "b"]);
});

test("Not the same sends every member, once", () => {
  assert.deepEqual(pairsOf(cluster), ["a", "b", "c"]);
});

test("the dialog's state: clusters, empty, or could not compare", () => {
  assert.equal(groomState(report({})), "clusters");
  assert.equal(groomState(report({ clusters: [] })), "empty");
  assert.equal(groomState(report({ clusters: [], compared_wording: false })), "failed");
});

test("the toast counts the folded bullets and names the keeper", () => {
  assert.equal(combinedToast(2, "Cleansed 2M rows"), "Combined 3 bullets into one. Cleansed 2M rows stays.");
  assert.equal(combinedToast(1, "Cleansed 2M rows"), "Combined 2 bullets into one. Cleansed 2M rows stays.");
});
```

Run: `cd frontend && node --test lib/kb-groom.test.ts` → FAIL.

**Step 2: The pure module**

`frontend/lib/kb-groom.ts`:

```ts
/**
 * The Tidy bullets dialog's decisions (`kb-groom.test.ts`): which ids Combine sends, which Not the
 * same sends, which state the dialog is in, and the toast.
 */
import type { GroomCluster, GroomReport, UUID } from "./types";

/** Every member except the one the user keeps. */
export function otherIds(cluster: GroomCluster, keeperId: UUID): UUID[] {
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

/** `folded` is how many were combined INTO the keeper; the sentence counts the keeper too. */
export function combinedToast(folded: number, keeperText: string): string {
  return `Combined ${folded + 1} bullets into one. ${keeperText} stays.`;
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
        "otherIds(", "pairsOf(", "groomState(", "combinedToast(", "KEEPER_RULE",
        "Similar bullets on", "Keep one as the bullet and fold the others into it as wordings.",
        "Nothing changes on your resumes.",
        "Keep this one", "Combine into one", "Stop using", "Not the same",
        "Won't suggest these again", "Won't be offered again",
        "No similar bullets here.", "Couldn't compare wording right now.",
        "combineKbPoints(", "forgetKeepApartKbPoints(", "bulkKbPointState(", "unmerge: true",
    ):
        assert needle in src, needle
    assert "Combine all" not in src, "each cluster is one decision"
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py -q` → FAIL.

**Step 4: The dialog**

`frontend/components/career/groom-dialog.tsx`, a client component:

- Props: `{ entityId: UUID; entityTitle: string; open: boolean; onOpenChange: (open: boolean) => void }`.
- `useQuery({ queryKey: ["kb", "groom", entityId], queryFn: () => getKbGroom(entityId), enabled: open })`.
- Title "Similar bullets on {entityTitle}"; description "These say nearly the same thing. Keep one
  as the bullet and fold the others into it as wordings. Nothing changes on your resumes." then
  `KEEPER_RULE` in muted text.
- States from `groomState(report)`: loading → two `Skeleton` cluster cards; `failed` → "Couldn't
  compare wording right now." with a Retry button (`refetch`); `empty` → "No similar bullets
  here."; `clusters` → one card per cluster.
- Each cluster card: header `{Math.round(score * 100)}% similar`; a `RadioGroup` of members, value
  defaulting to `cluster.keeper_id` (local state keyed by keeper id), the selected radio labelled
  "Keep this one", each member's text beside it, a muted line of its state word and
  `used on N resumes` when `usage_count > 0`, and on every non-selected member a small ghost
  **Stop using** button. Footer buttons: **Combine into one** (primary) and **Not the same** (ghost).
- Combine: `combineKbPoints(selected, otherIds(cluster, selected))`; toast
  `combinedToast(others.length, keeperText)` with Undo = `Promise.all(others.map((m) => patchKbPoint(m.id, { state: m.state, unmerge: true })))`
  (members carry their prior `state`). Then invalidate `["kb","groom",entityId]`,
  `["kb","entity",entityId]`, `["kb","entities"]`, `["kb","drafts"]` so the list behind the dialog
  refetches while it stays open. The cluster leaves the list on the refetch.
- Stop using on a member: `bulkKbPointState([m.id], "retired")`; toast "Won't be offered again"
  with Undo = `patchKbPoint(m.id, { state: m.state })`; invalidate the same keys. The cluster
  re-forms from the rest on the refetch, which is right.
- Not the same: `keepApartKbPoints(pairsOf(cluster))`; toast "Won't suggest these again" with Undo
  → `forgetKeepApartKbPoints(pairsOf(cluster))`; invalidate the groom query.
- Footer: one button, **Done**, which closes. No "Combine all".
- Pending: disable the cluster's buttons while its mutation runs; `useSingleFlight` on each.

Check `RadioGroup`/`Radio` prop names in `frontend/components/ui/radio-group.tsx` before writing.

**Step 5: The button**

In `frontend/components/career/points-list.tsx`, `PointsList` gains `entityTitle: string` (pass
`entity.data.title` from `entity-detail.tsx`) and `const [tidyOpen, setTidyOpen] = useState(false)`.
In the `CardHeader`, next to the title, when `points.filter((p) => p.state !== "retired").length >= 2`:

```tsx
<Button size="sm" variant="outline" onClick={() => setTidyOpen(true)}>
  <TidyIcon aria-hidden="true" /> Tidy bullets
</Button>
```

(`TidyIcon` = whichever `CONCEPT_ICONS` entry fits "merge"/"tidy"; a lucide `Combine` or
`Sparkles` if none does.) Render `<GroomDialog entityId={entityId} entityTitle={entityTitle} open={tidyOpen} onOpenChange={setTidyOpen} />`
after the card.

**Step 6: Gates**

Run: `cd frontend && node --test lib/*.test.ts && npx tsc --noEmit && npm run lint` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/test_frontend_kb_stale_wording.py tests/test_frontend_plain_words.py tests/test_frontend_kb_editors.py -q` → PASS.

**Step 7: Commit**

```bash
git add frontend/lib/kb-groom.ts frontend/lib/kb-groom.test.ts frontend/components/career/groom-dialog.tsx frontend/components/career/points-list.tsx frontend/components/career/entity-detail.tsx backend/tests/test_frontend_kb_stale_wording.py
git commit -m "feat(web): Tidy bullets, a per-item review that combines similar bullets into one on a click"
```

---

### Task 9: MCP tools

**Files:**
- Modify: `backend/mcp_server/client.py` (`get_kb_groom`, `kb_combine_points`)
- Modify: `backend/mcp_server/server.py` (`kb_groom_entity`, `kb_combine_points`, `kb_retire_points`,
  the `kb_sync_base` docstring)
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
def test_kb_combine_points_posts_the_keeper_and_the_others():
    route = respx.post(f"{BASE}/api/kb/points/combine").mock(
        return_value=httpx.Response(200, json={"id": "k", "wordings": []})
    )
    BackendClient(BASE).kb_combine_points("k", ["a", "b"])
    assert json.loads(route.calls.last.request.read()) == {"keeper_id": "k", "point_ids": ["a", "b"]}


@respx.mock
def test_kb_sync_base_passes_compared_wording_through():
    respx.post(f"{BASE}/api/base-resumes/hybrid/kb-sync").mock(
        return_value=httpx.Response(200, json={"created": 0, "items_added": 0, "drifted": 0, "renamed": [],
                                               "skipped": [], "skills": [], "skills_added": [],
                                               "last_kb_synced_at": None, "compared_wording": False})
    )
    assert BackendClient(BASE).kb_sync_base("hybrid")["compared_wording"] is False
```

`backend/mcp_server/tests/test_server.py`: add `"kb_groom_entity"`, `"kb_combine_points"` and
`"kb_retire_points"` to `KB_TOOL_NAMES`; add to `_PINNED_HINTS`:

```python
    # Read-only report; proposes, writes nothing.
    "kb_groom_entity": (True, False, True, False),
    # Reversible from /career (unmerge / Use again), so not destructive; the same ids twice is a no-op.
    "kb_combine_points": (False, False, True, False),
    "kb_retire_points": (False, False, True, False),
```

and these tests near `test_kb_sync_base_docstring_is_draft_only_and_deterministic`:

```python
def test_kb_sync_base_docstring_names_the_compared_flag_and_the_wording_rule():
    doc = (srv.kb_sync_base.__doc__ or "").lower()
    assert "compared_wording" in doc
    assert "wording" in doc and "0.80" in doc


def test_kb_groom_entity_is_read_only_and_wires_to_the_report(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "get_kb_groom", lambda entity_id: seen.update(id=entity_id) or {"clusters": []})
    assert srv.kb_groom_entity("e1") == {"clusters": []}
    assert seen == {"id": "e1"}
    doc = (srv.kb_groom_entity.__doc__ or "").lower()
    assert "deterministic" in doc and "zero llm" in doc.replace("-", " ")
    assert "kb_combine_points" in doc and "kb_retire_points" in doc


def test_kb_combine_points_states_the_gate_and_forwards_ids(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "kb_combine_points",
                        lambda keeper_id, point_ids: seen.update(k=keeper_id, ids=point_ids) or {"id": keeper_id, "wordings": []})
    out = srv.kb_combine_points("k", ["a", "b"])
    assert seen == {"k": "k", "ids": ["a", "b"]}
    assert out["id"] == "k"
    doc = srv.kb_combine_points.__doc__ or ""
    assert "user's decision" in doc and "reversible" in doc.lower()
    assert "never" in doc.lower() and "resume" in doc.lower()  # retiring/combining never edits a resume


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
    assert "user's decision" in approve_doc and "user's decision" in retire_doc
    assert "reversible" in retire_doc.lower()
```

`backend/mcp_server/tests/test_profiles.py`, in
`test_career_profile_registers_onboarding_tools_and_hunt_does_not`, add the three names to
`new_tools`.

Run: `cd backend && .venv/bin/python -m pytest mcp_server/tests/test_server.py mcp_server/tests/test_profiles.py mcp_server/tests/test_client_onboarding.py -q` → FAIL.

**Step 2: Client**

In `backend/mcp_server/client.py` after `kb_sync_base`:

```python
    def get_kb_groom(self, entity_id: str) -> Any:
        return self._request("GET", f"/api/kb/entities/{entity_id}/groom")

    def kb_combine_points(self, keeper_id: str, point_ids: list[str]) -> Any:
        return self._request(
            "POST", "/api/kb/points/combine", json={"keeper_id": keeper_id, "point_ids": point_ids}
        )
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
    kb_combine_points (one claim in other words: the others become the keeper's
    wordings) or kb_retire_points (a similar but stale one)."""
    return _client.get_kb_groom(entity_id)
```

After `kb_approve_points` (the write block):

```python
@mcp.tool(**_write("Combine Career Points", destructive=False, idempotent=True))
@_guard
def kb_combine_points(keeper_id: str, point_ids: list[str]) -> Any:
    """Fold Career KB points into one: the keeper stays the bullet, every other
    listed point is retired and recorded as one of the keeper's wordings. Resumes
    that use any of them keep their text; combining never edits a resume.
    Reversible from /career (Make its own bullet). The grouping written is the
    user's decision about the listed points; the server does not check that the
    user reviewed them (a convention, not enforcement, the same gate as
    kb_approve_points). Same entity required (400); a retired or
    user_cannot_confirm keeper is refused (400). Returns the keeper with its
    wordings. 1-50 ids."""
    return _client.kb_combine_points(keeper_id, point_ids)


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

`kb_sync_base`'s docstring gains: "A bullet that rephrases an existing point on the same item
(0.80 cosine and above) is kept as that point's wording, not added as a second point; only a new
claim lands as a draft. Returns compared_wording: false means the embedder could not run, so every
bullet was added as new and nothing was matched." Keep the words `deterministic`, `draft`,
`never edits`, `safe to rerun` that the existing pin reads. Mind `_BANNED_VOICE` in
`test_server.py`: no "call only", "tell the user", "prefer", "never call" in any docstring; state
facts.

`backend/mcp_server/profiles.py`: add the three names to `CAREER_TOOLS`. `full` is `None` and
registers everything.

`plugins/maestro-career-studio/README.md` line 79: add `kb_combine_points` and `kb_retire_points`
after `kb_approve_points` in the Codex approval list; if `.codex-plugin`/`.claude-plugin` JSON
carries a tool approval list, add them there too (grep `kb_approve_points` under `plugins/`;
`tests/test_plugin_declarations.py` pins what exists).

**Step 4: Run the MCP tests, then the suite**

Run: `cd backend && .venv/bin/python -m pytest mcp_server/tests/ -q -n auto --dist loadfile` → PASS.
Run: `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → PASS.

**Step 5: Commit**

```bash
git add backend/mcp_server/client.py backend/mcp_server/server.py backend/mcp_server/profiles.py backend/mcp_server/tests/test_server.py backend/mcp_server/tests/test_profiles.py backend/mcp_server/tests/test_client_onboarding.py plugins/maestro-career-studio/README.md
git commit -m "feat(mcp): kb_groom_entity reads similar bullets; kb_combine_points and kb_retire_points act on the user's yes"
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

> **Claims and wordings.** A point is a claim; its text is the one line resumes are offered. A
> claim's **wordings** are derived on read (`career_kb.wordings_of`, `KBPointOut.wordings`) from
> four sources: a resume's rewording (`from_source` port-log rows, adopt or split), an older copy
> a resume still carries (`to_resume`/legacy rows whose snapshot differs: neither, "Send to
> resume to update it"), a claim combined into it (a retired point whose `merged_into_point_id`
> is this one: adopt or split) and imported text (`merge_sources_json`: adopt). One row per
> distinct normalized text; a wording is never offered to a resume. **Intake**
> (`services/kb_claims.place`) is the one band: exact normalized match → in sync; best same-item
> cosine ≥ 0.80 (`SYNC_WORDING_COSINE`) → a wording; else new. Candidates exclude retired and
> `user_cannot_confirm`. Base sync maps `wording` to the wire tier `drift` (one `from_source`
> note, no point; `recorded` and the pill's N unchanged); only a new claim becomes a draft.
> `classify`/`apply` return `compared_wording`, false when the embedder raised (every bullet then
> reads as new and the UI says so). **Combine** (`POST /api/kb/points/combine {keeper_id,
> point_ids}`) retires the others and points them at the keeper (same item; keeper not retired
> or `user_cannot_confirm`); `PATCH {unmerge: true}` clears the pointer (with `state` it is the
> split). **Split a resume wording** (`POST /api/kb/points/{id}/split-wording {text, resume_key}`)
> creates an approved `user_authored` claim and re-points the matching `from_source` rows.
> Adoption is `PATCH {text}`, state unchanged. **Groom** (`services/kb_groom.py`,
> `GET /api/kb/entities/{id}/groom`) is read-only and LLM-free: one `embed_texts` call over the
> item's active points, edges at the band minus `kb_point_kept_pairs`, single-link components,
> keeper = approved > most recently updated > longest > id. `POST`/`DELETE
> /api/kb/points/keep-apart {point_ids}` records/forgets every pair among same-item ids
> (canonical `point_a_id < point_b_id`, cascade with either point). No path reads provenance to
> rank or writes it (`inv-provenance-no-decay`, pinned by the new writers in
> `test_no_writer_flips_user_cannot_confirm`).

Keep the existing sentences about `recorded` and the pill's N; delete "drafts new/drifted"
wording that no longer holds.

**Step 2: `docs/agent-surfaces.md`**

In the MCP server bullet that lists the KB tools, after `kb_approve_points`: "`kb_groom_entity`
(read-only similar-bullet report per entity, zero LLM calls), `kb_combine_points` (fold points
into one keeper; the others become its wordings) and `kb_retire_points` (the retire twin of
`kb_approve_points`); the two writes share `kb_approve_points`' convention gate and are
`destructive=False` because `/career` reverses them; all three in the `career` and `full`
profiles. `kb_sync_base` keeps a rephrasing as a wording (0.80+) and returns `compared_wording`."

**Step 3: `docs/frontend-conventions.md`**

In the Career history section, add: the points list hides a combined bullet and shows it under
its keeper (`lib/kb-wordings.ts` `visibleClaims`); the **N wordings** chip (the old "Wording
differs" badge, now on every bullet with wordings) opens "Wordings of this bullet" with **Use as
the main wording**, **Make its own bullet** and the hint "Send to resume to update it" by kind;
the entity page's **Tidy bullets** dialog (`career/groom-dialog.tsx`, shown with two or more
active bullets; one decision per cluster: "Keep this one" radio with the proposed keeper,
**Combine into one** primary, **Stop using** per other row, **Not the same**; no combine-all;
decisions in `lib/kb-groom.ts`); and the sync pill's words ("kept as wordings", "Kept N
rewordings.", "Couldn't compare wording").

**Step 4: `CHANGELOG.md`**

Under `## [Unreleased]`, in the owner's voice for the opener (one or two sentences, plain: syncing
an edited resume no longer piles up a second bullet for every rewrite), then `### Added`: wordings
on every bullet with adopt and split; Tidy bullets with Combine; the three MCP tools.
`### Changed`: a rephrasing at 0.80+ is kept as a wording, not drafted (was 0.90 for the note,
and a draft below); sync says when it could not compare wording. `### Fixed`: a sync that could
not load the embedder no longer reads every bullet as new silently. One schema migration, noted.

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
git commit -m "docs: career history keeps rewrites as wordings (one band, combine, split, Tidy bullets, three MCP tools)"
```

(Include the baseline files only if re-baselined.)

---

## Design §6 test list, mapped to tasks

| Design §6 item | Task | Test |
|---|---|---|
| classify: a 0.85 rewrite is `drift` with `matched_point_id` | 2 | `test_a_rewrite_in_the_band_is_a_wording_not_a_new_bullet` |
| classify: 0.79 is `new` | 2 | `test_under_the_band_is_new` |
| classify: 0.92 is `drift` | 2 | `test_a_close_rewrite_is_still_a_wording` |
| classify: retired or `user_cannot_confirm` never the target | 2 | `test_a_retired_or_unconfirmable_point_is_never_the_target` |
| classify: `compared_wording` false, no matches on failure | 2 | `test_embedder_failure_reports_itself` |
| classify: the band constant is 0.80 | 2 | `test_the_band_is_the_designed_constant` |
| classify: existing tests unchanged | 2 | the file's pre-existing tests, unedited |
| apply: one note, no point; twice no-op; `compared_wording` | 2 | `test_a_rewrite_writes_one_wording_note_and_no_point` |
| router: both routes carry `compared_wording` | 2 | `test_kb_sync_status_and_apply_carry_the_compared_flag` |
| `place`: each kind with point and score; exclusions; `compared=False` | 2 | `test_kb_claims.py` (seven tests) |
| models: `merged_into` round-trips and nulls | 1 | `test_merged_into_round_trips_and_nulls_when_the_keeper_goes` |
| models: `kept_pair_key` canonical; cascade | 1 | `test_kept_pair_key_is_canonical_and_rejects_a_self_pair`, `test_kept_pairs_cascade_with_either_point` |
| wordings: four sources, affordances | 3 | `test_wordings_come_from_all_four_sources_with_the_right_affordances` |
| wordings: one row per text; own line excluded | 3 | `test_one_row_per_distinct_text_and_the_lines_own_text_is_never_a_wording` |
| wordings: entity detail lists a merged claim under its keeper | 3 | `test_entity_detail_lists_the_merged_claim_under_its_keeper` |
| combine: retires and points losers; keeper untouched; idempotent | 4 | `test_combine_retires_and_points_the_losers_and_leaves_the_keeper_alone` |
| combine: 400 mixed items / retired or UCC keeper; 404 unknown | 4 | `test_combine_refuses_mixed_items_a_retired_or_unconfirmable_keeper_and_unknown_ids` |
| `unmerge` PATCH clears pointer, sets state given | 4 | `test_unmerge_patch_clears_the_pointer_and_sets_the_state_given` |
| split-wording: approved claim, rows re-pointed, in sync after | 4 | `test_split_wording_makes_an_approved_claim_and_moves_the_rows`, `test_after_a_split_the_resume_bullet_reads_in_sync`, `test_split_wording_with_a_resume_key_moves_only_that_resumes_rows` |
| adoption keeps the state | 4 | `test_adoption_keeps_the_state_and_clears_the_row` |
| points list hides a merged claim (source pin) | 7 | `test_points_list_hides_combined_bullets_and_opens_the_wordings_popover`, `kb-wordings.test.ts` |
| groom: deterministic clusters; single link joins a chain | 5 | `test_fixed_vectors_give_deterministic_clusters_and_single_link_joins_a_chain` |
| groom: keeper rule in each tiebreak order | 5 | `test_keeper_rule_in_each_tiebreak_order` |
| groom: kept pairs break an edge | 5 | `test_kept_pairs_break_an_edge` |
| groom: drafts in, retired and UCC out | 5 | `test_drafts_included_retired_and_unconfirmable_excluded` |
| groom: one-point item is empty | 5 | `test_one_point_item_and_no_similar_pairs_are_empty` |
| groom: embedder failure → `compared_wording` false | 5 | `test_embedder_failure_sets_compared_wording_false` |
| groom: a combined cluster is gone on the next report | 5 | `test_a_combined_cluster_is_gone_on_the_next_report` |
| keep-apart: canonical, idempotent; same-item 400; cascade; DELETE forgets | 5, 1 | `test_keep_apart_records_every_pair_canonically_and_is_idempotent`, `test_keep_apart_requires_one_item_and_known_points`, `test_keep_apart_delete_forgets_and_point_delete_cascades`, `test_kept_pairs_cascade_with_either_point` |
| provenance pin: new writers; split-wording creation site | 4 | `test_no_writer_flips_user_cannot_confirm` (extended), `test_every_point_creation_site_stamps_provenance[split_wording]` |
| no-LLM pins for `place`, sync, groom | 2, 5 | `test_place_never_calls_the_llm`, `test_sync_never_calls_the_llm`, `test_groom_never_calls_the_llm_and_writes_nothing` |
| portability and parity pick up the column and table | 1 | run unchanged in Task 1 Step 5 |
| MCP: `kb_groom_entity` wires to the GET | 9 | `test_kb_groom_entity_is_read_only_and_wires_to_the_report`, `test_get_kb_groom_reads_the_entity_report` |
| MCP: `kb_combine_points` and `kb_retire_points` state the gate, forward ids | 9 | `test_kb_combine_points_states_the_gate_and_forwards_ids`, `test_kb_retire_points_is_the_consent_gated_retire_twin`, `test_kb_combine_points_posts_the_keeper_and_the_others` |
| MCP: `kb_sync_base` passes `compared_wording` through | 9 | `test_kb_sync_base_passes_compared_wording_through`, `test_kb_sync_base_docstring_names_the_compared_flag_and_the_wording_rule` |
| web: sync words ("kept as wordings", "Kept N rewordings.", the compared line) | 6 | the three new tests plus the moved assertions in `kb-sync-words.test.ts` |
| web: wordings chip, actions per kind, split request, hidden merged | 7 | `kb-wordings.test.ts` + the points-list pin |
| web: groom keeper preselected, Combine ids, Stop using one id, Not the same pairs, states, toasts | 8 | `kb-groom.test.ts` + the two groom pins |

## After the last task

Run the goal-critique against the Goal Card, not against this plan: on a fresh stack (recipe in
the owner's `worktree-verification-recipe` memory), reword two bullets in a base and add one new
one, click Add, and check that the inbox shows one draft and the two claims each show "1 wording";
adopt one wording, split the other; open Tidy bullets on an item with two near bullets and
Combine; open the keeper's wordings and split it back out. Each Goal Card principle should be
visible: no LLM spinner, nothing changed before a click, provenance chips unchanged, the combine
and retire copy naming resumes, and an honest line when the embedder is off
(`EMBEDDINGS_OUT_OF_PROCESS` with a broken model path simulates it). Then
`superpowers:finishing-a-development-branch`.
