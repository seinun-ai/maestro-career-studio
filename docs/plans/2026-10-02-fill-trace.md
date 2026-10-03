# Fill Trace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Record a value-free, per-run trace of every Autofill decision: what was read, how each
model decided and how sure it was, every move with its time and effect, and the outcome. Keep the last
50 runs plus never-expiring value-free counters. Add a script that reads one run and reports wasted
moves and confidence calibration.

**Architecture:** Design doc `docs/plans/2026-10-02-fill-trace-design.md`, approach A:

- The backend returns a small value-free `trace` (engine, confidence, floor, second opinion,
  polarity) beside each `/map`, `/pick` and `/step` answer.
- The fill loop (`extension/shared/fill-loop.js`) records each field's steps and returns a run trace
  in its report.
- The panel sends it as one `fill_trace` message. The service worker scrubs it against a whitelist
  and posts it to `POST /api/autofill/runs`.
- The backend keeps 50 runs and folds the run into counters.
- `backend/scripts/fill_trace.py` reads a database copy.

**Tech Stack:**
- FastAPI and Pydantic v2 (`extra="forbid"` schemas), SQLAlchemy 2 + Alembic on SQLite.
- MV3 extension JS, tested in real Chromium through Playwright (`backend/tests/browser/`) and in node
  for the panel and service worker (`backend/tests/test_extension_*`).

**Ground rules (read before Task 1):**
- Read `SYSTEM.md` first; CLAUDE.md requires it. The `inv-autofill-telemetry-no-values` invariant
  governs this work: **no answer value, typed text, prompt or profile word may enter a trace.** Every
  task that adds data to the trace adds a test proving that.
- Worktree recipe: run Python as `/opt/anaconda3/bin/python -m pytest …` from `backend/`. The cwd
  makes `app` resolve to this worktree. There is no xdist, so don't pass `-n`.
- Slop ratchet:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check extension|backend` from the
  repo root. Backend is already at 580 against 571 on origin/main; that predates this work, so don't
  let it grow. `extension/content/agent.js` must stay under 700 lines
  (`test_agent_is_only_the_page_rpc_front_door`).
- Never stage `docs/reports/`.
- Commit after every task, ending the message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Match the surrounding comment style: comments explain *why*, in full sentences, and cite the live
  case that motivated the code.

**Shared vocabulary (used by several tasks; define each once where its task says):**

| Name | Values | Defined in |
|---|---|---|
| Engine | `"jev"`, `"fast"` | `app/schemas/autofill_fill.py` (Task 1) |
| Second | `"asked"` (asked, did not change it), `"decided"` (its answer stands) | same |
| PolarityWay | `"same"`, `"opposite"`, `"neither"`, `"unsure"` | same |
| Step kind | `map`, `polarity`, `pick`, `explore`, `apply`, `step`, `sweep`, `recipe` | `app/schemas/autofill_trace.py` (Task 5); mirrored in fill-loop.js (Task 10) |
| Effect | `progress`, `no_effect`, `reverted`, `refused`, `error` | same |
| Band | `floor(p * 10) / 10`, clamped to 0.0–0.9; e.g. 0.93 → "0.9", 0.5 → "0.5" | `app/services/autofill_trace.py` (Task 6) |

---

### Task 1: Decision-trace schemas on the /map, /pick and /step responses

**Files:**
- Modify: `backend/app/schemas/autofill_fill.py` (after `Reason`, L25; `Mapped` L77-82; `Picked` L117-119; `StepResponse` L170-175)
- Test: `backend/tests/test_autofill_decision_trace.py` (create)

**Step 1: Write the failing test**

```python
"""The decision traces /map, /pick and /step return beside each answer: value-free by
construction (enums and numbers only), and optional, so an answer without one is unchanged."""
import pytest
from pydantic import ValidationError

from app.schemas.autofill_fill import DecisionTrace, Mapped, Picked, PolarityTrace, StepResponse


def test_a_decision_trace_holds_only_enums_and_numbers():
    t = DecisionTrace(engine="jev", p=0.93, floor=0.9, second="asked")
    assert t.model_dump() == {"engine": "jev", "p": 0.93, "floor": 0.9, "second": "asked"}
    for bad in ({"engine": "gpt"}, {"second": "maybe"}, {"p": 1.5}, {"note": "x"}):
        with pytest.raises(ValidationError):
            DecisionTrace(**bad)


def test_answers_carry_an_optional_trace():
    assert Mapped(route="none").trace is None
    assert Picked(oids=[], reason="abstained").trace is None
    assert Picked(oids=[], reason="abstained").polarity is None
    assert StepResponse(mid=None, reason="abstained").trace is None
    assert PolarityTrace(way="unsure").model_dump() == {"way": "unsure", "engine": None, "p": None}
```

**Step 2: Run it and check it fails**

Run: `/opt/anaconda3/bin/python -m pytest -q tests/test_autofill_decision_trace.py`
Expected: ImportError (`DecisionTrace`).

**Step 3: Implement**

In `autofill_fill.py`, after `Reason`:

```python
# How a model decided an answer: value-free by construction (enums and numbers), returned
# beside /map, /pick and /step answers for the run trace (docs/plans/2026-10-02-fill-trace-design.md).
Engine = Literal["jev", "fast"]
Second = Literal["asked", "decided"]   # asked: it did not change the answer; decided: its answer stands
PolarityWay = Literal["same", "opposite", "neither", "unsure"]


class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Engine | None = None   # None: no model was asked (a code path)
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None


class PolarityTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    way: PolarityWay
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
```

Add `trace: DecisionTrace | None = None` to `Mapped`, `Picked` and `StepResponse`, and
`polarity: PolarityTrace | None = None` to `Picked`. `Mapped` and `Picked` have no `extra="forbid"`;
leave them as they are.

**Step 4: Run it and check it passes**

Run the same command; expect PASS. Then run
`-m pytest -q tests/test_autofill_fill_router.py tests/test_autofill_pick.py tests/test_autofill_map.py tests/test_autofill_step.py`
and expect everything to pass. Defaults are None, so nothing else changes.

**Step 5: Commit** `feat(autofill): value-free decision traces on map, pick and step answers`

---

### Task 2: /map returns its decision trace

**Files:**
- Modify: `backend/app/services/autofill_map.py` (`map_fields` L518-557, `_second_opinion` L492-504, `_floor` L182)
- Test: `backend/tests/test_autofill_map.py` (use its `fake_jev`, `fake_llm` and `run` helpers, L27-69)

**What to record:**
- `engine`: `"jev"` when Jev's answer stands (`picked` came from `_with_jev`); `"fast"` when the fast
  model mapped the batch (Jev off or failed) or the second opinion decided the field.
- `p`: the probability or confidence of the answer that stands.
- `floor`: `_floor(facts[key])` when the answer names a fact (`key in facts`), else `SLOT_FLOOR`.
- `second`:
  - `"asked"` for fids sent to `_second_opinion` that it did not decide;
  - `"decided"` for fids in the local `decided` dict (L537);
  - None for everything else.
- Low-stakes and reasoned fields (L551-556): `trace=DecisionTrace(engine=None)`, since the pass is
  recorded by the route itself.

**Step 1: Write failing tests**
- With Jev answering slot X at 0.97: `got[fid].trace == DecisionTrace(engine="jev", p=0.97, floor=<floor of X>, second=None)`.
- With Jev unsure (under floor) and the fast second opinion deciding: `trace.engine == "fast"`,
  `trace.second == "decided"`, `p` is the fast confidence.
- With Jev unsure and the second opinion not deciding: `trace.engine == "jev"`, `trace.second == "asked"`.
- With the engine set to fast: `trace.engine == "fast"`, `second is None`.
- Privacy: `json.dumps(Mapped.model_dump())` for a field whose fact value is `"555-0100"` must not
  contain the value inside `trace`. Assert `set(m.trace.model_dump()) == {"engine","p","floor","second"}`.

**Step 2:** Run `-m pytest -q tests/test_autofill_map.py -k trace` and expect FAIL.

**Step 3: Implement**
- Keep the `(key, p)` per fid and which dict it came from: `jev_answers = picked` when Jev ran, and
  `second` from `_second_opinion`.
- After `out` is final (after `_one_job_per_entry`), attach a trace with `model_copy(update={"trace": …})`.
- Never mutate a shared `Mapped` constant.

**Step 4:** Run `-m pytest -q tests/test_autofill_map.py tests/test_autofill_fill_router.py` and expect PASS.

**Step 5: Commit** `feat(autofill): /map says which engine decided, how sure, and against what floor`

---

### Task 3: /pick returns its decision trace and polarity

**Files:**
- Modify:
  - `backend/app/services/autofill_polarity.py`: `Polarity` L96-99, add `p: float | None = None`; set it where `Polarity(way, "jev")` and `Polarity(way, "fast")` are built in `decide` L212-251; `UNSURE` keeps `p=None`
  - `backend/app/services/autofill_pick.py`: `verdict` L94-107, `_with_jev` L207, `_with_llm` L227, `_second_opinion` L254-267, `pick` L270-311, `polarity_answers` L160-181
- Test: `backend/tests/test_autofill_pick.py` (its `fake_jev(…, ways=…)`, `fake_llm`, `pf`, `pick` helpers, L43-78)

**What to record:**
- **Pick.** `verdict(field, oid, p, policy, *, complete, engine)` gains `engine` (callers:
  `_with_jev` passes `"jev"`, `_with_llm` passes `"fast"`). Every return carries
  `trace=DecisionTrace(engine=engine, p=p, floor=<the floor it was judged against>)`:
  - `ASSUMED_FLOOR` for low_stakes;
  - `MATCH_FLOOR[policy]` otherwise;
  - `CLOSEST_FLOOR` when the result is "closest".

  Return a fresh `Picked` instead of the shared `ABSTAIN` (`Picked(oids=[], reason="abstained", trace=…)`).
- **Second opinion.** In `pick`, the fids in `unsure` that `decided` covers get `second="decided"`
  (their trace is the fast one). The rest of `unsure` get `second="asked"` on the Jev trace.
- **Polarity.** `polarity_answers` also returns the `Polarity` per fid. Change it to return
  `(computed, ways)`, or add a sibling `polarity_of`; keep its `/step` caller working. `pick` attaches
  `polarity=PolarityTrace(way=w.way or "unsure", engine=w.engine, p=w.p)` to every slot field that
  went through polarity, including the ones it abstains on at L285. Those are the CC-305 case from
  2026-10-02.
- **Not askable** (L280): leave `trace=None`; nothing was asked.

**Step 1: Write failing tests**
- Jev picks o2 at 0.95 (`policy exact`): `trace == DecisionTrace(engine="jev", p=0.95, floor=0.9, second=None)`.
- Jev abstains at 0.82 and the fast second opinion decides: `trace.engine == "fast"`, `trace.second == "decided"`.
- Polarity unsure → abstained: `got[fid].polarity.way == "unsure"` and `got[fid].trace is None` (no pick was asked).
- Polarity same by Jev at 0.97: `got[fid].polarity == PolarityTrace(way="same", engine="jev", p=0.97)`.
- Privacy: for a fact value `"No, I do not have a disability"`, `json.dumps({fid: p.model_dump() for …})`
  has the value nowhere inside `trace` or `polarity` (compare only those sub-dicts).

**Step 2:** Run `-m pytest -q tests/test_autofill_pick.py -k "trace or polarity_trace"` and expect FAIL.

**Step 3:** Implement as above.

**Step 4:** Run `-m pytest -q tests/test_autofill_pick.py tests/test_autofill_polarity.py tests/test_autofill_step.py tests/test_autofill_fill_router.py` and expect PASS.

**Step 5: Commit** `feat(autofill): /pick says how it decided, and the polarity verdict behind it`

---

### Task 4: /step returns its decision trace

**Files:**
- Modify: `backend/app/services/autofill_step.py` (`_decide` L58-64, `_with_llm` L92-99, `_second_opinion` L102-118, `step` L121-160)
- Test: `backend/tests/test_autofill_step.py`

**What to record:**
- `_decide(req, mid, p, policy, *, engine)` returns its answer with `trace=DecisionTrace(engine, p, floor)`.
  The floor is `PROGRESS_FLOOR` for a progress move, else the verdict's floor (from Task 3's `Picked.trace`).
- The second opinion's answer gets `second="decided"` when it is not ABSTAIN. When it is ABSTAIN,
  return Jev's trace with `second="asked"`.
- The early `ABSTAIN` returns (L127, L133, L140) keep `trace=None`, except L140 (polarity unsure),
  which has no field for polarity here; leave it None.
- Return fresh `StepResponse` objects, never the shared `ABSTAIN` with a trace attached.

**Step 1: Failing tests:**
- a progress move at 0.6 by Jev: `trace == DecisionTrace(engine="jev", p=0.6, floor=0.5, second=None)`
- a Jev give-up overturned by the fast model with an answer click: `engine="fast", second="decided"`
- the fast engine: `engine="fast"`

**Step 2–4:** Run `-m pytest -q tests/test_autofill_step.py`: FAIL, then implement, then PASS.

**Step 5: Commit** `feat(autofill): /step says how each move was chosen`

---

### Task 5: The run-trace schema, models and migration

**Files:**
- Create: `backend/app/schemas/autofill_trace.py`
- Create: `backend/app/models/autofill_run.py`, `backend/app/models/autofill_mechanism_stat.py`
- Modify: `backend/app/models/__init__.py` (one import line each, alphabetical, plus `__all__`)
- Create: `backend/migrations/versions/<12-hex>_fill_trace.py`, with `down_revision = "643ba5470e73"`.
  Write the id by hand (for example `python -c "import uuid;print(uuid.uuid4().hex[:12])"`).
  Use impl types only (`sa.JSON`, `sa.DateTime`, `sa.Uuid`, `sa.Text`, `sa.Integer`), like
  `980498217fe6_health_evaluations.py`. It never imports app code.
- Test: `backend/tests/test_autofill_trace_schema.py`

**Schema** (`extra="forbid"` on every model; the caps are the design's):

```python
StepKind = Literal["map", "polarity", "pick", "explore", "apply", "step", "sweep", "recipe"]
Effect = Literal["progress", "no_effect", "reverted", "refused", "error"]
MAX_RUN_FIELDS, MAX_FIELD_STEPS, LABEL_MAX = 200, 40, 200


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: StepKind
    ms: int | None = Field(default=None, ge=0, le=600_000)
    effect: Effect | None = None
    route: Route | None = None                    # map
    slot: str | None = Field(default=None, max_length=120)   # a fact NAME, never its value
    why: Why | None = None
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None
    way: PolarityWay | None = None                # polarity
    option: int | None = Field(default=None, ge=0, le=MAX_PICK_OPTIONS)   # index into the field's options
    reason: StepReason | None = None              # pick/step
    move: str | None = Field(default=None, max_length=40, pattern=MOVE_ID)   # step/recipe: a move id
    outcome: str | None = Field(default=None, max_length=40, pattern=r"^[a-z_]+$")   # the page's word


class TraceField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(max_length=64, pattern=FID)
    label: str = Field(default="", max_length=LABEL_MAX)
    label_source: str | None = Field(default=None, max_length=40, pattern=r"^[a-z-]+$")
    shape: Shape | Literal["unknown"]
    section: str | None = Field(default=None, max_length=LABEL_MAX)
    required: bool = False
    options: list[Annotated[str, Field(max_length=LABEL_MAX)]] | None = Field(default=None, max_length=30)
    option_count: int = Field(default=0, ge=0)
    family: str | None = Field(default=None, max_length=32, pattern=r"^f:[0-9a-z]{1,24}$")
    steps: list[TraceStep] = Field(default_factory=list, max_length=MAX_FIELD_STEPS)
    outcome: str = Field(max_length=40, pattern=r"^[a-z_]+$")
    round: int = Field(default=0, ge=0, le=10)


class RunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9A-Za-z-]+$")
    host: str = Field(max_length=255)
    started_at: datetime
    ended_at: datetime
    mode: Literal["assist"] = "assist"   # only "Saved answers + AI" runs the loop today
    halted: Literal["stopped", "timeout"] | None = None
    rounds: int = Field(default=0, ge=0, le=10)
    fields: list[TraceField] = Field(max_length=MAX_RUN_FIELDS)
```

Import `Route`, `Why`, `Engine`, `Second`, `PolarityWay`, `StepReason`, `Shape`, `FID`, `MOVE_ID`
and `MAX_PICK_OPTIONS` from `app.schemas.autofill_fill`. Don't redefine them.

**Models:**
- `AutofillRun`:
  - `id` UUID pk (as `AutofillFieldObservation`)
  - `run_id` String(64), unique (`uq_autofill_runs_run_id`)
  - `host` Text
  - `started_at` and `created_at` UTCDateTime
  - `trace` JSONDoc not null
- `AutofillMechanismStat`:
  - `key` Text primary key
  - `counts` JSONDoc not null default=dict
  - `updated_at` UTCDateTime, onupdate=utcnow

Docstrings say why: value-free; the counters hold no host and no label.

**Step 1: Failing tests:**
- a valid RunTrace round-trips;
- unknown keys at every level raise;
- a label of 201 characters raises;
- 41 steps raise;
- `option` > 250 raises;
- `slot` accepts `"eeo.disability_status"`;
- `outcome` rejects `"No, I do not"` (the pattern blocks spaces and capitals, so a value can't
  hide there).

**Step 2–4:**
- Run `-m pytest -q tests/test_autofill_trace_schema.py`: FAIL, then implement, then PASS.
- Then run `-m pytest -q tests/test_migrations*.py` if present, else
  `-m pytest -q tests/ -k "migration or alembic"`, to confirm the chain upgrades.

**Step 5: Commit** `feat(autofill): the run-trace schema, its two tables and their migration`

---

### Task 6: Store a run, prune to 50, fold the counters, and clear

**Files:**
- Create: `backend/app/services/autofill_trace.py`
- Modify: `backend/app/routers/autofill.py`
  - add `POST /runs` beside `POST /telemetry` (L71)
  - extend `DELETE /telemetry` (L152-173)
- Test: `backend/tests/test_autofill_trace_router.py`. Copy the `_client(db_session)` pattern from
  `tests/test_autofill_telemetry_router.py`.

**Service:**

```python
RUNS_KEPT = 50

def band(p: float | None) -> str | None:
    """The confidence band a decision is counted in: 0.93 is "0.9", 0.5 is "0.5"."""

def store_run(db: Session, trace: RunTrace) -> None:
    """Insert the run (a re-post of the same run_id replaces it and is not counted twice),
    prune to the newest RUNS_KEPT by started_at, and fold a NEW run into the counters."""

def fold(trace: RunTrace) -> dict[str, dict[str, int]]:
    """The counter increments one run adds, keyed without host or label."""
```

**Counter keys and fields:** only these. The keys hold enums and ids, never text from a page.
- `move|<family or "-">|<move kind>`: `tries`, `progress`, `no_effect`, `reverted`, `refused`,
  `error`, `ms`. "Move kind" is the move id up to its first `:` (`search:value` gives `search`), so
  the key space stays bounded.
- `decision|<kind>|<engine or "-">|<band or "-">`: `n`, `kept`, `left`, `failed`.
  - kind is one of map, polarity, pick or step.
  - The field's final outcome gives the column: `kept` for verified, closest_filled,
    assumed_filled or prefilled; `failed` for unconfirmed, cannot_operate or unsupported; `left`
    for anything else.
- `second|<kind>`: `asked`, `decided`, `decided_kept`.

Update with read-modify-write: reassign `counts`, never mutate the JSON (the telemetry route does
the same; see its comment).

**Routes:**
- `POST /api/autofill/runs`: body `RunTrace`, returns 204.
- `DELETE /api/autofill/telemetry`: also deletes every `AutofillRun`, and returns
  `{"deleted": n, "runs_deleted": m}`. Counters stay. If an existing test pins the exact response
  dict, update that test and say so in the commit.

**Step 1: Failing tests:**
- POST stores one row; a second POST with the same `run_id` keeps one row and does not double the
  counters.
- 52 posts keep the 50 newest by `started_at`.
- `fold` is right for a hand-built two-field run: move tries and ms, a decision band, and second
  opinions decided and kept.
- `band(0.93) == "0.9"`, `band(1.0) == "0.9"`, `band(0.5) == "0.5"`, `band(None) is None`.
- No counter key contains the host or any label: build a run whose host and label are
  `"secret.example"` and `"Secret label"`, then assert that neither appears in `json.dumps` of all
  `AutofillMechanismStat` rows.
- DELETE removes runs, keeps counters, and returns both counts.
- An unknown key in the body returns 422.

**Step 2–4:** Run `-m pytest -q tests/test_autofill_trace_router.py tests/test_autofill_telemetry_router.py`: FAIL, then implement, then PASS.

**Step 5: Commit** `feat(autofill): keep the last 50 run traces and count what each mechanism did`

---

### Task 7: One copy-only database guard for the scripts

**Files:**
- Create: `backend/scripts/db_copy.py`. Move `refused_dirs`, `_identity`, `refusal` and
  `bind_read_only` here unchanged from `backend/scripts/eval_fill_decisions.py` (L132-210), together
  with the env setup `main` does before app imports (L826-832), as a function
  `open_copy(db: Path) -> None` that sets `DATABASE_URL`, pops `TEST_DATABASE_URL`, defaults
  `SETTINGS_DIR`/`LOGS_DIR` to a temp dir, and calls `bind_read_only`.
- Modify: `backend/scripts/eval_fill_decisions.py` to import these from `db_copy`. It runs as a
  script, so `sys.path[0]` is `scripts/` and `import db_copy` works. Check the tests' import path
  too (tests import `eval_fill_decisions` as `ev`; find how and mirror it).
- Test: the existing eval guard tests must still pass. Find them with `grep -rn "refusal\|bind_read_only" backend/tests`.

**Steps:** Move the code. Run `-m pytest -q tests/ -k "eval_fill or refusal or read_only"` and expect PASS. Commit:
`refactor(scripts): one copy-only database guard, shared by the eval and the trace reader`

---

### Task 8: `fill_trace.py last`

**Files:**
- Create: `backend/scripts/fill_trace.py`
- Test: `backend/tests/test_fill_trace_script.py`

**Behaviour:**
- `fill_trace.py --db COPY last [--host H] [--n 1]` prints the newest run, or the newest run on host
  H.
- It calls `db_copy.refusal`; when that returns a reason, it prints it and exits with code 2. Then
  `db_copy.open_copy`.
- One block per field. The top line is `[status]  "label"  shape  label←source  family`; the
  following lines hold one step each, for example:
  - `map → eeo.disability_status (jev 0.97 ≥0.90)`
  - `polarity → unsure (fast 0.61; second asked)`
  - `step open → no_effect 412ms`
- A first line per run: host, time, fields, filled, left, prefilled, halted.

**Test:**
- Build a temp SQLite file with `alembic upgrade head` (see conftest `_test_database_ready` for how),
  insert one `AutofillRun` with a hand-built trace, and run the script via
  `subprocess.run([sys.executable, "scripts/fill_trace.py", "--db", path, "last"], cwd=backend)`.
- Assert the lines above appear.
- Assert that a path under this checkout's `data/` is refused with exit code 2: create a temp file
  there and remove it after.

**Steps:** Write the test, see it FAIL, implement, see it PASS. Commit:
`feat(scripts): fill_trace last — one run's decision path, field by field`

---

### Task 9: `fill_trace.py report`

**Files:** `backend/scripts/fill_trace.py`, `backend/tests/test_fill_trace_script.py`

**Report sections** (plain text, from `AutofillMechanismStat` and the stored runs):
1. **Wasted moves:** per move kind × family, `tries`, the `no_effect` share and the average ms,
   sorted by wasted ms (`no_effect + reverted` tries × average ms), top 15.
2. **Calibration:** per decision kind × engine × band, `n` and the `kept`, `left` and `failed`
   shares.
3. **Second opinion:** per kind, `asked`, `decided` and the `decided_kept` share.
4. **Slowest fields:** from the stored runs, the 10 fields with the most steps (host, label, steps,
   outcome).
5. **Suggestions:** for each kind and engine, a band below the current floor whose `kept` share is
   at least 0.95 over at least 20 decisions:
   `pick/jev 0.8–0.9: 41/42 kept, floor 0.90 could be 0.80`. Name the floor from the traces (the
   `floor` value recorded on those steps). Print nothing when no band qualifies, and say so.

**Test:** seed counters and runs that produce one suggestion and one that falls short (19
decisions), and assert the suggestion line and the absence of the other.

**Commit:** `feat(scripts): fill_trace report — wasted moves, calibration, second-opinion value`

---

### Task 10: The fill loop records each field's path

**Files:**
- Modify: `extension/shared/fill-loop.js`
- Test: `backend/tests/browser/test_fill_loop.py`. Use the existing `run(page, load, **spec)`
  harness (L146-154) and helpers (`f`, `opt`, `row`); the DRIVER's fake api must return the new
  `trace` and `polarity` keys where a test needs them.

**Recorder:**
- Each row gets `steps: []`.
- Add `note(fid, step)`, which appends `{kind, …}` while `steps.length < 40`.
- Time a move with `const t0 = Date.now()` and `ms: Date.now() - t0`.

**Where to note (anchors from the exploration):**

| Where | Note |
|---|---|
| `mapFields` apply (L1131-1138) | `{kind:"map", route, slot, why, ...pickTrace(m.trace)}` |
| `pickOf` callers (`pick` L653-659, `pickBatch` L669-683) | `{kind:"polarity", way, engine, p}` when `got.polarity`, then `{kind:"pick", reason, option: <index of the chosen oid in offered>, ...pickTrace(got.trace)}` |
| `act` callers in `commitOne` / `commitSet` / `fillText` | `{kind:"apply", ms, effect: EFFECT_OF[got.outcome] ?? "error", outcome: got.outcome}` |
| `explore` (L520-531) | `{kind:"explore", ms, effect: options.length ? "progress" : "no_effect"}` |
| `adapt` per /step (L735-778) | `{kind:"step", move: chosen.mid, reason, ...pickTrace(res.trace)}`, then after `act`: `{kind:"apply", move: chosen.mid, ms, effect, outcome}` |
| `sweep` re-open (L1151-1174) | `{kind:"sweep", effect:"reverted"}` |
| `lookUp` hit (L559-573) | `{kind:"recipe", move: recipe.variant}`, only when it is a valid move id; else `{kind:"recipe"}` |

- `pickTrace(t)` copies only `engine`, `p`, `floor` and `second`, and only when present.
- `EFFECT_OF` is a total table over the page outcomes the header lists (L109-140):
  - verified, landed, committed → progress
  - no_effect, unchanged, stale, missing → no_effect
  - reverted, unexpected → reverted
  - refused, blocked, halted → refused
  - late → error
  - anything else → error

  Read the header and list every word; a test pins the table against the header's list.

**The run trace:** `buildRunTrace(report, rows, meta)`, published on `ns.fillLoop` beside
`buildLoopObservations`, and its result is returned as `report.trace`. Per field:
- `label`: blank when `holdsValue(label, answer)` (L1694), as telemetry does;
- `label_source`: `field.source` from the inventory;
- `shape`, `section`, `required`;
- `options`: the page's texts, capped at 30 × 200, and `option_count`;
- `family`: `field.recipe?.family` when it matches `^f:[0-9a-z]{1,24}$`;
- `steps`, `outcome` (the final status), `round`.

Per run:
- `run_id`, `host`;
- `started_at` / `ended_at`: ISO strings, taken at the start and end of `runFill`;
- `halted`: `"stopped"` or `"timeout"` from the report's `stopped` / `timedOut`;
- `rounds`.

**Never** copy `row.value`, `row.answer`, `row.wrote`, `row.wroteAs` or a pick's chosen text into a
step. A step names the option's **index** only.

**Steps:**
1. Write failing Playwright tests:
   - a two-field run (one select picked by Jev at 0.95, one text mapped) has
     `report.trace.fields[*].steps` kinds in order `map, pick, apply` and `map, apply`, with `ms`
     numbers and `effect` set;
   - a pick with `polarity` from the fake api records a polarity step;
   - a stopped run has `halted == "stopped"`;
   - privacy: the fake profile answers (for example `"555-0100"` and
     `"No, I do not have a disability"`) appear nowhere in `JSON.stringify(report.trace)`;
   - the step count caps at 40.
2. Run `-m pytest -q tests/browser/test_fill_loop.py -k trace` and expect FAIL.
3. Implement.
4. Run `-m pytest -q tests/browser/test_fill_loop.py` (about 1–2 minutes) and expect PASS. Then the
   whole browser suite, `-m pytest -q tests/browser` (about 11 minutes); run it in the background
   and wait for the notification, never a polling loop.
5. Commit: `feat(companion): the fill loop records each field's decision path`

---

### Task 11: The panel sends the trace; the service worker scrubs and posts it

**Files:**
- Modify:
  - `extension/panel/actions/fill.js`, `startLoopFill` (L328-392): after `store.telemetry(…)` at L374,
    `if (loop?.trace) store.trace(loop.trace);`
  - `extension/panel/panel.js`, `actionStore()` (L4280): add
    `trace: (trace) => { ask("fill_trace", { trace }).catch((err) => console.warn("[maestro-cs] trace failed:", err)); }`
  - `extension/sw.js`: add `fill_trace` to HANDLERS beside `telemetry` (L545). It returns
    `{posted: 0}` when `telemetryEnabled === false`; otherwise it posts `scrubTrace(msg.trace)` to
    `/api/autofill/runs`.
- Test:
  - `backend/tests/test_extension_sw_router.py`: mirror the telemetry tests around L612-640;
  - `backend/tests/test_extension_panel_fill.py`: mirror `test_loop_telemetry_is_one_value_free_observation_per_field`
    (L3882) with the `_loop` harness; give `LOOP_REPORT` a small `trace`.

**`scrubTrace`:**
- A whitelist at three levels: run keys, field keys and step keys, exactly the Task 5 schema's names.
- Strings are cut: labels and sections 160, options 30 × 160.
- Numbers are coerced, with non-finite numbers dropped.
- A step whose `kind` is not in the step-kind list is dropped.
- More than 200 fields or 40 steps are cut, not rejected.

Keep it near `scrubObservation` and give it the same comment voice.

**Tests:**
- Opted out → nothing posted.
- A trace with injected `value`, `answer`, `wrote` and `prompt` keys at all three levels posts none
  of them; grep the posted body for the injected strings.
- The posted body's top-level keys equal the schema's.
- The panel sends exactly one `fill_trace` after a loop run, and none when the report has no trace.

**Steps:** Write the tests, see them FAIL, implement, see them PASS. Then run
`-m pytest -q tests/ -k extension --ignore=tests/browser`. Commit:
`feat(companion): send each run's trace, scrubbed, behind the telemetry switch`

---

### Task 12: Docs, gates and full suites

**Files:**
- `SYSTEM.md`, invariant `inv-autofill-telemetry-no-values` (around L336-343). Rewrite it in place to
  cover traces too: what a trace holds, the 50-run retention, counters with no host or label, and
  that Clear deletes runs. The file is at its 1000/1000-line cap: integrate, don't append.
  `/opt/anaconda3/bin/python scripts/check_system_md.py` must pass.
- `extension/INTERNALS.md`: a short "Run trace" paragraph beside the telemetry section (around L1223).
- `CHANGELOG.md` under `## [Unreleased]` → `### Added`: one entry in user terms (Autofill keeps a
  private record of how it decided each field, for diagnosing and tuning).

**Gates:**
- `-m pytest -q tests/ mcp_server/tests/` (about 15 minutes, in the background).
- `-m pytest -q tests/browser` (about 11 minutes, in the background).
- The slop ratchet: extension must be OK; backend must not exceed 580.
- `check_system_md`.

**Commit:** `docs: the run trace in SYSTEM.md, INTERNALS and the changelog`

---

### Task 13: Live check (the owner runs Docker)

1. Fast-forward local main to the branch, then hand the owner the commands, in their own blocks:
   `docker compose build backend` and `docker compose up -d backend` (the migration runs at startup).
2. The owner reloads the extension and runs Autofill on any application form.
3. Copy the database read-only to the scratchpad:
   `sqlite3 "file:<main>/data/maestro_cs.sqlite3?mode=ro" ".backup <scratch>/copy.sqlite3"`.
   Then run `scripts/fill_trace.py --db <copy> last` and `… report`.
4. Check:
   - every field has steps;
   - map and pick lines show an engine and p;
   - ms are realistic;
   - no answer value appears anywhere. Grep the copy's `autofill_runs.trace` for the owner's name,
     email and phone, checking that each is absent without printing them.
5. Delete the copy. Report the run's summary to the owner.
