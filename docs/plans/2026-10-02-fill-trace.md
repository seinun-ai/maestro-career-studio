# Fill Trace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Final counter keys (Task 6 review, 2026-10-03; authoritative over the Task 6 text below):**
- `action|<family>|<kind>`: tries, one count per effect, `effect_unknown`, `ms`, `timed`.
- `decision|<op>|<engine>|<by first|second>|<floor>|<band>|<choice>`. `choice` is answer, none
  or unknown; for polarity it is the `way`.
- `first|<op>|<floor>|<band(first_p)>|<agree same|other|unknown>`, for every step the second
  opinion decided (Task 9 review: the denominator needs the disagreements too).
- `AutofillMechanismStat.created_at` gives the report's "counters since" date. It was added to the
  unreleased migration in place.
- **The report's suggestion rule (Task 9 review):** for each band B below the floor,
  D = all `first` n + Jev's undecided below-floor `answer` decisions, and K = the `same`-kept count.
  A band qualifies when D ≥ 20 and the Wilson 95% lower bound of K/D is ≥ 0.85. The candidate is
  the lowest band reached by walking down from the floor with every band qualifying. The output
  is key=value, with a legend (kept is an outcome proxy) and a data-window line.
- `second|<op>`: asked (ran, unchanged), decided, decided_kept.

`autofill_trace.py` owns the key builders, `KEY_PARTS`, `parse_key`, `NONE_PART` and the frozen
op and effect sets. Task 9 imports them.

**Execution notes (2026-10-03, from the Task 1-4 reviews).**
- `DecisionTrace` gained `first_same` and `chose_none`.
- Code decisions carry no trace on every endpoint.
- Second-opinion bookkeeping lives in `autofill_map.second_decided` / `second_asked`.
- An `ABSTAIN` equality pin covers all of backend/app and backend/scripts.
- Tasks 5, 6, 9 and 10 below reflect this.

**Revision 2.1 (2026-10-02).** The re-check found five small fixes; they are applied: the eval
and the merges accept a second opinion that didn't run (`None`); the router pins also drop
`polarity`; the explore table gets a catch-all row; `act()` notes on every return path; the sw
drops a pattern-breaking value.

**Revision 2 (2026-10-02).** A Fable 5.1 review against the code found four blockers and several
important gaps in revision 1; all are folded in here:

- abstain equality;
- pinned response shapes;
- the scripts' import model;
- trace-schema mismatches;
- privacy allowlist;
- `first_p`;
- model-call time;
- rounds;
- rejected picks.

**Goal:** Record a value-free, per-run trace of every Autofill decision: what was read, how each
model decided and how sure it was, every action with its time and effect, and the outcome. Keep
the last 50 runs plus never-expiring value-free counters. Add a script that reads one run and
reports wasted actions and confidence calibration.

**Architecture:** Design doc `docs/plans/2026-10-02-fill-trace-design.md`, approach A.

- The backend returns a value-free `trace` (engine, confidence, floor, second opinion, the first
  engine's confidence, polarity) beside each `/map`, `/pick` and `/step` answer.
- The fill loop (`extension/shared/fill-loop.js`) records each field's steps from an explicit
  allowlist and returns `report.trace`.
- The panel sends one `fill_trace` message. The service worker scrubs it and posts it to
  `POST /api/autofill/runs`.
- The backend keeps 50 runs and folds each run into counters.
- `python -m scripts.fill_trace` reads a database copy.

**Tech Stack:**
- FastAPI and Pydantic v2 (`extra="forbid"` request schemas), SQLAlchemy 2 + Alembic on SQLite.
- The MV3 extension, tested two ways:
  - the real fill loop in Chromium through Playwright (`backend/tests/browser/`);
  - the panel and service worker in node (`backend/tests/test_extension_*`).

**Ground rules (read before Task 1):**
- Read `SYSTEM.md` first; CLAUDE.md requires it. Invariant `inv-autofill-telemetry-no-values`
  governs this work: **no answer value, typed text, prompt or profile word may enter a trace or a
  counter.** Every task that adds data adds a test proving it.
- Run Python as `/opt/anaconda3/bin/python -m pytest …` from `backend/`. The cwd makes `app`
  resolve to this worktree. There is no xdist, so don't pass `-n`.
- Long suites (the browser suite, about 11 minutes; the full backend, about 15) run in the
  background. Wait for the completion notification; **never a polling loop**.
- Slop ratchet: `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check extension|backend`
  from the repo root.
  - Extension must report OK.
  - Backend is at 580 against 571 on origin/main from the 0.7.1 work. Don't let it grow; if
    added tests raise it, re-baseline with `baseline backend` and give the reason in the commit.
- `extension/content/agent.js` must stay under 700 lines. This plan does not touch it.
- Never stage `docs/reports/`.
- End every commit with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Comments explain *why* in full sentences and cite the live case, matching the files.

**Shared vocabulary.** Defined once, in the file named; everything else imports it.

| Name | Values | Defined in |
|---|---|---|
| Engine | `jev`, `fast` | `app/schemas/autofill_fill.py` (Task 1) |
| Second | `asked` (it ran and did not change the answer), `decided` (its answer stands) | same |
| PolarityWay | `same`, `opposite`, `neither`, `unsure` | same |
| Op | `map`, `polarity`, `pick`, `step` (decisions); `explore`, `choose`, `set`, `write`, `move` (page actions); `sweep`, `recipe` | `app/schemas/autofill_trace.py` (Task 5); mirrored in fill-loop.js (Task 10) |
| Effect | `progress`, `no_effect`, `unexpected`, `reverted`, `unconfirmed`, `refused`, `late`, `error` | same |
| Band | `str(min(int(p * 10 + 1e-9), 9) / 10)`: 0.93 → "0.9", 1.0 → "0.9", 0.5 → "0.5", 0.3 → "0.3" | `app/services/autofill_trace.py` (Task 6) |

**Effect of a page action**, used by Task 10 and pinned by its test. It is derived from the page's
`got`, **reason first**. The vocabulary is fill-loop.js's header (L109-122) and `LANDS` (L256).

| Page result | Effect |
|---|---|
| `reason == "no_effect"` (the first ignored gesture: `outcome "unexpected"`, L497-507 and `noteNoEffect` L429) | `no_effect` |
| `reason` in `LANDS` (`group_committed`, `search_committed`) | `progress` |
| outcome `verified`, `partial`, `progressed`, `closed` | `progress` |
| outcome `unexpected` (any other reason) | `unexpected` |
| outcome `reverted` | `reverted` |
| outcome `unconfirmed` | `unconfirmed` |
| act() `refused` (yours, blocked, unsupported, a second no_effect kind, `committed_while_opening`) | `refused` |
| act() `late`, page `timeout` | `late` |
| act() `stale`, anything else | `error` |
| act() `halted`, page `cancelled` | **no step is noted** (Stop is not an attempt) |

An explore uses its own table. The input is `got.error` (`exploreRefused` L534-556), or the option
count when there is no error.

| Explore result | Effect |
|---|---|
| no error and at least one option | `progress` |
| no error and no options | `no_effect` |
| error `no_effect` | `no_effect` |
| error in REFUSED | `refused` |
| error `committed_while_exploring` | `unexpected` |
| error `stale` | `error` |
| error `cancelled` | **no step is noted** |
| any other error (`no_popup`, `unsettled`, … the `OUTRIGHT` set at L588) | `no_effect` |

---

### Task 1: Decision-trace schemas, and the pinned response shapes they change

**Files:**
- Modify: `backend/app/schemas/autofill_fill.py`. Add after `Reason` (L25). Change `Mapped`
  (L77-82), `Picked` (L117-119) and `StepResponse` (L170-175).
- Test: create `backend/tests/test_autofill_decision_trace.py`.
- Test pins that change: `None` fields serialize in `model_dump()` and in FastAPI `response_model`.
  - `tests/test_autofill_pick.py`: about 16 dict pins (L87, 94, 111, 124, 150, 179, 405, 434, 441,
    892, 1046, 1089, 1131, 1166, 1347). Switch them to compare `model_dump(exclude_none=True)`.
  - `tests/test_autofill_step.py`: the `step()` helper (L84-85) returns `.model_dump()`. Make it
    `.model_dump(exclude_none=True)`, and fix L328.
  - `tests/test_autofill_map.py` L78 and L812, and `tests/test_autofill_fill_router.py` L73, 161,
    194, 208, 277, 288. Rewrite them as subset pins
    (`{k: v for k, v in got.items() if k not in ("trace", "polarity")}`). `Picked` and
    `StepResponse` serialize `"polarity": None` too.
    `exclude_none` would drop the `"format": None` that L78 pins on purpose.

**Step 1: Write the failing test**

```python
"""The decision traces /map, /pick and /step return beside each answer: value-free by
construction (enums and numbers only), and optional."""
import pytest
from pydantic import ValidationError

from app.schemas.autofill_fill import DecisionTrace, Mapped, Picked, PolarityTrace, StepResponse


def test_a_decision_trace_holds_only_enums_and_numbers():
    t = DecisionTrace(engine="fast", p=0.93, floor=0.9, second="decided", first_p=0.82)
    assert t.model_dump() == {"engine": "fast", "p": 0.93, "floor": 0.9, "second": "decided", "first_p": 0.82}
    for bad in ({"engine": "gpt"}, {"second": "maybe"}, {"p": 1.5}, {"first_p": -0.1}, {"note": "x"}):
        with pytest.raises(ValidationError):
            DecisionTrace(**bad)


def test_answers_carry_an_optional_trace_and_polarity():
    assert Mapped(route="none").trace is None
    assert Picked(oids=[], reason="abstained").trace is None
    assert Picked(oids=[], reason="abstained").polarity is None
    assert StepResponse(mid=None, reason="abstained").trace is None
    assert StepResponse(mid=None, reason="abstained").polarity is None
    assert PolarityTrace(way="unsure").model_dump() == {"way": "unsure", "engine": None, "p": None}
```

**Step 2:** Run `/opt/anaconda3/bin/python -m pytest -q tests/test_autofill_decision_trace.py`.
Expect an ImportError.

**Step 3: Implement**

```python
# How a model decided an answer: value-free by construction (enums and numbers), returned
# beside /map, /pick and /step answers for the run trace (docs/plans/2026-10-02-fill-trace-design.md).
Engine = Literal["jev", "fast"]
Second = Literal["asked", "decided"]   # asked: it ran and did not change the answer; decided: its answer stands
PolarityWay = Literal["same", "opposite", "neither", "unsure"]


class DecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Engine | None = None   # None: no model was asked (a code path)
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None
    # With second == "decided": the FIRST engine's probability for the answer that now
    # stands, or its top choice when it abstained — the evidence for whether a lower floor
    # would have been safe (the calibration goal).
    first_p: float | None = Field(default=None, ge=0.0, le=1.0)


class PolarityTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    way: PolarityWay
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
```

Then change the response models:
- `Mapped`, `Picked` and `StepResponse` each get `trace: DecisionTrace | None = None`.
- `Picked` and `StepResponse` each get `polarity: PolarityTrace | None = None`.
- Leave their `model_config` alone: none of them is frozen, and none has `extra="forbid"`.

**Step 4:** Update the pins listed under Files. Then run
`-m pytest -q tests/test_autofill_decision_trace.py tests/test_autofill_pick.py tests/test_autofill_step.py tests/test_autofill_map.py tests/test_autofill_fill_router.py`.
Expect everything to pass.

**Step 5:** Commit: `feat(autofill): value-free decision traces on map, pick and step answers`

*As built:* the pick and step pins exclude the trace keys **by name**
(`TRACE_KEYS = {"trace", "polarity"}`), not with `exclude_none`. The step pins assert `"mid": None`
on purpose, and `exclude_none` would drop it. Later tasks keep this pattern; don't switch back.
`DecisionTrace` also has `first_same: bool | None`.

---

### Task 2: /map returns its decision trace

**Files:**
- Modify: `backend/app/services/autofill_map.py`: `map_fields` L518-557, `_second_opinion`
  L492-504, `_route` L451-467 (with `_placed_key` at L457), and `_floor` L182.
- Test: `backend/tests/test_autofill_map.py`. Use its `fake_jev` (L27), `fake_llm` (L54) and
  `run` (L69).

**What to record**

`engine`:
- `"jev"` when Jev's answer stands;
- `"fast"` when the fast model mapped the batch (Jev off or failed), or the second opinion decided
  the field.

`p`: the probability or confidence of the answer that stands.

`floor`:
- `_floor(facts[key])` for the key the model chose, computed **before** `_placed_key` remaps it
  (L457);
- otherwise `SLOT_FLOOR`.

Return the floor beside the `Mapped`, as a small tuple from a helper. Don't recompute it after the
remap.

`second`:
- `"decided"` for fids in the local `decided` dict (L537);
- `"asked"` for fids sent to the second opinion when it **ran** and did not decide them;
- None otherwise.

`_second_opinion` returns `{}` both when it ran and found nothing and when it never ran (no
budget, or a failure). Change it to return `None` when it did not run, and keep the `unsure` list
it was given. `map_fields` merges `second or {}` (`second.items()` at L536) and remembers
separately whether it ran.

`first_p` and `first_same` (on `second == "decided"`):
- `first_p` is Jev's `p` for its own top choice, even under the floor.
- `first_same` is whether that top choice equals the key the second opinion decided.

The second opinion runs only when Jev abstained, so its top choice is often "none". Only agreeing
cases are floor evidence (Task 1 review).

Low-stakes and reasoned routes (L551-556): `trace=DecisionTrace(engine=<the engine that judged
it>)`.
- `_low_stakes` asks Jev (engine "jev") or the fast model (engine "fast").
- `_answerable` always asks the fast model (engine "fast").

`p` stays None: `_low_stakes` and `_answerable` discard it (L401-420). Leave that known gap with a
one-line comment.

**Step 1: Failing tests:**
- **Jev decides.** Slot X at 0.97 → `trace == DecisionTrace(engine="jev", p=0.97, floor=<floor of X>)`.
- **Fast decides.** Jev unsure, the fast second opinion decides at 0.9 →
  `engine="fast", p=0.9, second="decided", first_p=<Jev's p>`.
- **Fast only asked.** Jev unsure, the second opinion runs and decides nothing →
  `engine="jev", second="asked"`.
- **Fast never ran.** Jev unsure, no budget left (patch `Budget.left` to None) → `second is None`.
- **Fast engine.** `engine="fast"`, `second is None`.
- **Floor from the original key.** A websites placement (`_placed_key` remaps) keeps the floor of
  the key the model chose.
- **Privacy.** `set(m.trace.model_dump()) == {"engine","p","floor","second","first_p"}` for every
  field.

**Step 2–4:** Run `-m pytest -q tests/test_autofill_map.py -k trace`: FAIL, then implement, then
PASS. Then run `tests/test_autofill_map.py tests/test_autofill_fill_router.py` and expect PASS.

**Step 5:** Commit: `feat(autofill): /map says which engine decided, how sure, and against what floor`

---

### Task 3: /pick returns its trace and polarity; abstain is tested by content, not equality

**Files:**
- Modify `backend/app/services/autofill_pick.py`:
  - `ABSTAIN` (L53), `verdict` (L94-107), `_with_jev` (L207), `_with_llm` (L227),
    `_second_opinion` (L254-267), `pick` (L270-311), `polarity_answers` (L160-181).
- Modify `backend/app/services/autofill_polarity.py`:
  - `Polarity` (L96-99): add `p: float | None = None`. Leave `UNSURE` alone.
  - Set `p` where `Polarity(way, "jev")` and `Polarity(way, "fast")` are built in `decide`
    (L212-251).
- Modify `backend/scripts/eval_fill_decisions.py` L483-484.
- Tests: `backend/tests/test_autofill_pick.py` (helpers `fake_jev(…, ways=…)` L43, `fake_llm` L57,
  `pf` L72 and `pick` L78), `tests/test_autofill_polarity.py`, and
  `tests/test_eval_fill_cases.py` if it covers `engine_of`.

**Shared with Task 2 (as built).** Use `autofill_map.second_decided(trace, first, decided)` and
`autofill_map.second_asked(trace)` for all second-opinion bookkeeping. Don't build those traces by
hand. `first_same` is None when the first engine gave no readable answer.
- Assemble the trace in one pass over the unsure fields.
- A field whose confidence was unreadable is recorded as `p=None` in the trace. Routing keeps
  treating it as 0.0, but a trace never shows a fake 0.0 (`autofill_pick.py` ~L249,
  `autofill_step.py` ~L99).
- Include a mixed-batch assertion: a confident field keeps `second is None` while another field
  in the same request was decided by the second opinion.
- Include a router test that the trace and polarity reach the JSON response.

**Blocker fixed here.** `==` on a Pydantic model compares every field, so a `Picked` carrying a
trace never equals `ABSTAIN`. The comparison sites are:
- `autofill_pick.py:301` (`picked[f.fid] == ABSTAIN`): `unsure` goes empty, so the second opinion
  is never asked;
- `autofill_pick.py:304` (`p != ABSTAIN`): an abstain carrying a trace counts as decided;
- the eval at `L483-484`: `fast_decided` is always true.

Fix:
- Add `def abstained(p: Picked) -> bool: return not p.oids` and use it at all three sites.
- Keep `ABSTAIN` only for returns that carry no trace (the not-askable fields at L280).
- Return a fresh `Picked(oids=[], reason="abstained", trace=…)` wherever a trace exists.

**What to record:**
- **`verdict`.** Its signature becomes
  `verdict(field, oid, p, policy, *, complete, engine)`. `_with_jev` passes `"jev"` and `_with_llm`
  passes `"fast"`. The step's own callers come in Task 4.

  Every return carries `trace=DecisionTrace(engine, p, floor)`. The floor is the one the answer was
  judged against:
  - `ASSUMED_FLOOR` for low-stakes;
  - `CLOSEST_FLOOR` when the result is "closest";
  - `MATCH_FLOOR[policy]` otherwise, including for an abstain.

  When the oid is the no-match key, the trace still carries `p`, the probability of the no-match
  answer.
- **Second opinion in `pick`.** `unsure` is the slot fields whose Jev pick is abstained:
  - when the second opinion decides one: its trace, plus `second="decided"`,
    `first_p=<Jev's p for its own top choice>`, and `first_same=<whether Jev's top oid equals
    the decided oid>`;
  - when it ran and didn't decide: Jev's trace with `second="asked"`;
  - when it didn't run (`budget.left` is None, or a failure), `second` stays None. Make
    `_second_opinion` return None when it didn't run, as in Task 2. `pick` merges
    `(second or {})` at L302-304.
  - The eval's `asked()` wrapper (`eval_fill_decisions.py:477-484`) calls `got.values()` or
    compares `got` against `ABSTAIN`, whatever `_second_opinion` returned. A `None` falls to the
    step branch and raises. Make it
    `run.fast_decided = got is not None and (any(not autofill_pick.abstained(p) for p in got.values()) if isinstance(got, dict) else not autofill_step.abstained(got))`.
    Task 4 adds `autofill_step.abstained`; until then, use `got.mid is not None` in this line.
- **Polarity.** Add a sibling `polarity_ways(fields, facts, session, budget) -> dict[str, Polarity]`.
  Keep `polarity_answers`' current return type, because `/step` (`autofill_step.py:138`) uses it.
  The simplest change is to have `polarity_answers` take an optional `ways` dict it fills in.
  - `pick` attaches `polarity=PolarityTrace(way=w.way or "unsure", engine=w.engine, p=w.p)` to every
    slot field that went through polarity.
  - That includes the ones it abstains on at L285, which have `trace=None` because no pick was
    asked: the CC-305 case from 2026-10-02.

**Step 1: Failing tests:**
- **Jev matches.** Jev picks o2 at 0.95 with an exact policy →
  `trace == DecisionTrace(engine="jev", p=0.95, floor=0.9)`.
- **Fast decides.** Jev abstains at 0.82 and the fast model decides at 0.97 →
  `trace == DecisionTrace(engine="fast", p=0.97, floor=0.9, second="decided", first_p=0.82, first_same=True)`
  when Jev's top choice was the same oid. Add a second case where Jev's top choice was the no-match
  key, which gives `first_same=False`. This
  test also proves the second opinion is still asked: the equality bug above made `unsure` empty.
- **Fast asked.** Jev abstains and the fast model also abstains → `second="asked"`, and the result
  is abstained.
- **Polarity unsure.** `got[fid].polarity.way == "unsure"`, `trace is None`, and `abstained(got[fid])`.
- **Polarity same.** Jev says same at 0.97 → `polarity == PolarityTrace(way="same", engine="jev", p=0.97)`.
- **Privacy.** With fact value `"No, I do not have a disability"`, neither the `trace` nor the
  `polarity` sub-dict contains it anywhere.
- **Eval.** A unit test of `engine_of` (or of the patched `_second_opinion` wrapper) reports
  `fast_decided` false when the fast model abstained with a trace.

**Step 2–4:** Run the pick tests with `-k "trace or polarity"`: FAIL, then implement, then PASS.
Then run `tests/test_autofill_pick.py tests/test_autofill_polarity.py tests/test_autofill_step.py tests/test_autofill_fill_router.py tests/test_eval_fill_cases.py`
and expect PASS.

**Step 5:** Commit: `feat(autofill): /pick says how it decided and why; abstain is tested by content`

---

### Task 4: /step returns its trace and polarity

**Files:**
- Modify `backend/app/services/autofill_step.py`: `ABSTAIN` (L45), `_decide` (L58-64), `_with_llm`
  (L92-99), `_second_opinion` (L102-118, comparison at L116), `step` (L121-160, comparison at L158).
- Modify `backend/scripts/eval_fill_decisions.py` L483-484 and L505.
- Test: `backend/tests/test_autofill_step.py`.

**Shared with Task 2 (as built).** Use `autofill_map.second_decided(trace, first, decided)` and
`autofill_map.second_asked(trace)` for all second-opinion bookkeeping. Don't build those traces by
hand. `first_same` is None when the first engine gave no readable answer.
- Assemble the trace in one pass over the unsure fields.
- A field whose confidence was unreadable is recorded as `p=None` in the trace. Routing keeps
  treating it as 0.0, but a trace never shows a fake 0.0 (`autofill_pick.py` ~L249,
  `autofill_step.py` ~L99).
- Include a mixed-batch assertion: a confident field keeps `second is None` while another field
  in the same request was decided by the second opinion.
- Include a router test that the trace and polarity reach the /step JSON response.

**Reuse from Task 3 (as built after its cleanup):**
- `verdict(field, oid, p, policy, *, engine)` no longer takes `complete`; it reads
  `field.complete`. An answer click's floor is `picked.trace.floor`, so don't recompute it.
- `polarity_ways(fields, facts, session, budget)` makes the model calls and
  `polarity_answers(fields, facts, ways)` is pure; step already calls them.
- `polarity_trace(w)` builds the `PolarityTrace`.
- The eval's `_fast_decided(got)` should use `autofill_step.abstained(got)` in place of
  `got.mid is not None`.
- **Pin test (Task 3 review):** add a test that greps `backend/app/services/autofill_*.py` and
  `backend/scripts/eval_fill_decisions.py` for `[!=]=\s*(\w+\.)?ABSTAIN\b` and expects no
  match. That stops the equality bug from coming back.

**Blocker fixed here** (same as Task 3). `second != ABSTAIN` (L116) and `decided != ABSTAIN`
(L158) break once a trace is attached.
- Add `def abstained(r: StepResponse) -> bool: return r.mid is None` and use it at both sites, and
  in the eval at L484.
- *As built:* the eval's Jev-only step stub returns `None` ("never ran"), not `ABSTAIN`; `ABSTAIN`
  would now record `second="asked"` for a second opinion that never ran.

**What to record:**
- **`_decide`.** Its signature becomes `_decide(req, mid, p, policy, *, engine)`.
  - It returns `trace=DecisionTrace(engine, p, floor)`.
  - The floor is `PROGRESS_FLOOR` for a progress move, and the verdict's own floor for an answer
    click (via Task 3's `verdict(…, engine=…)`).
  - A `give_up` and a no-mid answer still carry engine and `p`; they are calibration evidence for
    give-ups. Return a fresh `StepResponse(mid=None, reason="abstained", trace=…)`.
- **Second opinion.**
  - It decided: `second="decided"`, `first_p=<Jev's p>` and `first_same=<Jev's mid == the decided
    mid>`.
  - It ran and abstained: Jev's trace with `second="asked"`.
  - It didn't run: `second` is None.
- **Polarity.** `step()` decides polarity at L137-140. Attach a `PolarityTrace` the same way
  Task 3 does, including on the L140 polarity-unsure abstain.
- The early abstains at L127 and L133 carry no trace.

**Step 1: Failing tests:**
- a progress move at 0.6 by Jev → `DecisionTrace(engine="jev", p=0.6, floor=0.5)`;
- Jev gives up at 0.7 and the fast model decides an answer click →
  `engine="fast", second="decided", first_p=0.7, first_same=False`;
- the second opinion still runs after a Jev abstain that carries a trace (the regression test for
  L158);
- polarity unsure gives `polarity.way == "unsure"`;
- under the fast engine, `engine="fast"`.

**Step 2–4:** Run `-m pytest -q tests/test_autofill_step.py tests/test_eval_fill_cases.py`: FAIL,
then implement, then PASS.

**Step 5:** Commit: `feat(autofill): /step says how each move was chosen`

---

### Task 5: The run-trace schema, models and migration

**Files:**
- Create: `backend/app/schemas/autofill_trace.py`
- Create: `backend/app/models/autofill_run.py` and `backend/app/models/autofill_mechanism_stat.py`
- Modify: `backend/app/models/__init__.py`. One import line per model, alphabetical, plus `__all__`.
- Create: `backend/migrations/versions/<12-hex>_fill_trace.py`
  - `down_revision = "643ba5470e73"`.
  - Write the id by hand: `python -c "import uuid;print(uuid.uuid4().hex[:12])"`.
  - Use implementation types only (`sa.Uuid`, `sa.Text`, `sa.String`, `sa.JSON`, `sa.DateTime`,
    `sa.Integer`), like `980498217fe6_health_evaluations.py`. Never import app code.
- Test: `backend/tests/test_autofill_trace_schema.py`

**Schema.** Every model has `extra="forbid"`. Import the shared types from
`app.schemas.autofill_fill`: `Route`, `Why`, `Engine`, `Second`, `PolarityWay`, `StepReason`,
`Shape`, `FID`, `MOVE_ID` and `MAX_PICK_OPTIONS`.

```python
Op = Literal["map", "polarity", "pick", "step",                      # decisions
             "explore", "choose", "set", "write", "move",            # page actions
             "sweep", "recipe"]
Effect = Literal["progress", "no_effect", "unexpected", "reverted", "unconfirmed", "refused", "late", "error"]
WORD = r"^[a-z_]{1,40}$"   # a page word or a status: lowercase only, so a value cannot hide in it
MAX_RUN_FIELDS, MAX_FIELD_STEPS, LABEL_MAX = 200, 40, 200


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Op
    ms: int | None = Field(default=None, ge=0, le=600_000)   # page action OR model-call latency
    effect: Effect | None = None                              # page actions
    word: str | None = Field(default=None, pattern=WORD)     # the page's outcome/reason word
    route: Route | None = None                                # map
    slot: str | None = Field(default=None, max_length=120, pattern=r"^[a-z_]+(\.[a-z0-9_]+)*$")  # a fact NAME
    why: Why | None = None
    engine: Engine | None = None
    p: float | None = Field(default=None, ge=0.0, le=1.0)
    floor: float | None = Field(default=None, ge=0.0, le=1.0)
    second: Second | None = None
    first_p: float | None = Field(default=None, ge=0.0, le=1.0)
    first_same: bool | None = None
    chose_none: bool | None = None   # the model's top choice was the no-answer key (none/no-match/give_up)
    way: PolarityWay | None = None                            # polarity
    option: int | None = Field(default=None, ge=0, le=MAX_PICK_OPTIONS)  # index into the field's options
    reason: StepReason | None = None                          # pick / step
    move: str | None = Field(default=None, max_length=40, pattern=MOVE_ID)  # op step / move


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
    outcome: str = Field(pattern=WORD)
    round: int = Field(default=0, ge=0, le=10)


class RunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9A-Za-z-]+$")
    host: str = Field(max_length=255)
    started_at: datetime
    ended_at: datetime
    mode: Literal["assist"] = "assist"   # only "Saved answers + AI" runs the loop (panel/actions/fill.js:458)
    halted: Literal["stopped", "timeout"] | None = None
    rounds: int = Field(default=0, ge=0, le=10)
    fields: list[TraceField] = Field(max_length=MAX_RUN_FIELDS)
```

Check the `slot` pattern against the real slot names: `personal.phone`, `custom.3`,
`experience.0.start` and `derived.sponsorship_now_or_future`. Widen the pattern if one fails; never
loosen it to free text.

**Models:**
- `AutofillRun`:
  - `id`: UUID primary key, as in `AutofillFieldObservation`;
  - `run_id`: String(64), unique (`uq_autofill_runs_run_id`);
  - `host`: Text;
  - `started_at`, `created_at`: UTCDateTime;
  - `trace`: JSONDoc, not null.
- `AutofillMechanismStat`:
  - `key`: Text, primary key;
  - `counts`: JSONDoc, not null, default dict;
  - `updated_at`: UTCDateTime, `onupdate=utcnow`.

The docstrings say why: value-free; the counters hold no host and no label.

**Step 1: Failing tests:**
- a valid RunTrace round-trips;
- an unknown key at any level raises;
- a 201-character label raises;
- 41 steps raise;
- `option` 251 raises;
- `word` rejects `"No, I do not"`;
- `slot` accepts the four names above and rejects `"Jane Doe"`;
- `move` accepts `click:o3` and rejects `click:Jane`.

**Step 2–4:**
- `-m pytest -q tests/test_autofill_trace_schema.py`: FAIL, then implement, then PASS.
- Conftest runs `alembic upgrade head` once per session, so the migration chain is exercised by any
  test run.
- Also run `-m pytest -q tests/ -k "migration or alembic"`.

**Step 5:** Commit: `feat(autofill): the run-trace schema, its two tables and their migration`

---

### Task 6: Store a run, prune to 50, fold the counters, clear

**Files:**
- Create: `backend/app/services/autofill_trace.py`
- Modify: `backend/app/routers/autofill.py`. Add `POST /runs` beside `POST /telemetry` (L71), and
  extend `DELETE /telemetry` (L152-173).
- Test: `backend/tests/test_autofill_trace_router.py`, copying the `_client(db_session)` pattern
  from `tests/test_autofill_telemetry_router.py`.
- Test pins that change: `tests/test_autofill_telemetry_router.py` L780 and L812 pin the DELETE
  response; update them.

**Service:**

```python
RUNS_KEPT = 50
KEPT = {"verified", "closest", "assumed", "already", "partial"}          # report statuses (fill-loop.js header)
FAILED = {"unconfirmed", "cannot_operate", "unsupported"}

def band(p: float | None) -> str | None:
    """The confidence band a decision is counted in: str(min(int(p * 10 + 1e-9), 9) / 10)."""

def store_run(db: Session, trace: RunTrace) -> None:
    """Insert the run (a re-post of the same run_id replaces it and is NOT folded twice), prune
    to the newest RUNS_KEPT by started_at, and fold a NEW run into the counters."""

def fold(trace: RunTrace) -> dict[str, dict[str, int]]:
    """The counter increments one run adds, keyed without host or label."""
```

Read the field statuses for `KEPT` and `FAILED` from the fill-loop header's report-status list
(L124-130), and pin them with a test that scans the header, as
`test_autofill_telemetry_router._outcomes_the_fill_loop_emits` (L333-345) does.

**Counter keys.** These are the only keys. Each holds enums and ids, never a page's text.

`action|<family or "-">|<kind>`
- `kind` is the step's `op` for a page action (`explore`, `choose`, `set`, `write`).
- For `op == "move"`, `kind` is the move id up to its first `:` (`click`, `search`, `open`,
  `scroll`, `give_up`), so the key space stays bounded.
- Counts: `tries`, one per effect (`progress`, `no_effect`, `unexpected`, `reverted`,
  `unconfirmed`, `refused`, `late`, `error`), and `ms`.

`decision|<op>|<engine or "-">|<floor>|<band or "-">|<answer or none>`
- Count only steps that carry a decision trace with an `engine`. "No trace" means code decided
  (Task 4 review), so code decisions are never counted.
- `op` is `map`, `polarity`, `pick` or `step`.
- `floor` is part of the key, so step answer clicks (floor 0.9/0.75/0.4) and progress moves (0.5)
  are never mixed.
- The last part is `none` when `chose_none` is true, else `answer`. That keeps "the model was sure
  there is nothing" apart from "its option fell under the floor".
- Counts:
  - `n`;
  - `kept`, `left` or `failed`, from the field's final status;
  - `rejected`, when the next page-action step after this decision on the same field had effect
    `no_effect`, `unexpected`, `reverted` or `refused`. This is the design's "a pick the page
    rejected or reverted".

`first|<op>|<band of first_p>`, for steps with `second == "decided"` **and** `first_same` true
- Counts: `n`, and `kept` / `left` / `failed` as above.
- This is the evidence for "Jev at 0.8x, confirmed by the fast model, kept by the page".

`second|<op>`
- Counts: `asked`, `decided`, `decided_kept`.

Write counters by read-modify-write, reassigning `counts` and never mutating the JSON (see the
telemetry route's comment).

**Concurrency and storage (Task 5 review):**
- `store_run` calls `app.db.begin_write(db)` (`BEGIN IMMEDIATE`; precedent: `routers/proposals.py`,
  `services/health_disputes.py`) **first**, before the `run_id` lookup. Routes run in the
  threadpool, so two posts close together would otherwise lose counter increments or 500 on a
  duplicate insert. Add a test that two stores of different runs both land in the counters.
- Store the trace as `model_dump(mode="json", exclude_none=True)`. A step has 18 mostly-null keys.
- Prune by `started_at DESC, created_at DESC`, so ties are deterministic.
- A comment notes that a re-post of a run already pruned looks new and is folded again.
  That is accepted, because it is rare.

**Routes:**
- `POST /api/autofill/runs` takes a `RunTrace` body and returns 204.
- `DELETE /api/autofill/telemetry` also deletes every `AutofillRun`. It returns
  `{"deleted": n, "runs_deleted": m}`; the frontend card reads only `deleted`
  (`frontend/components/analytics/autofill-coverage-card.tsx:92-98`). The counters stay.

**Step 1: Failing tests:**
- **Store.** A POST stores one row. A second POST with the same `run_id` keeps one row and does not
  double the counters.
- **Pruning.** 52 posts keep the 50 newest by `started_at`.
- **`fold`.** On a hand-built three-field run:
  - action tries and ms;
  - `rejected` after a pick followed by a `no_effect` choose;
  - `first|pick|0.8` from `second="decided", first_p=0.82`;
  - second-opinion counts.
- **Bands.** `band` edges: 0.93 → "0.9", 1.0 → "0.9", 0.5 → "0.5", 0.3 → "0.3", 0.7 → "0.7",
  None → None.
- **Privacy.** For a run with host `"secret.example"` and label `"Secret label"`, neither string
  appears in `json.dumps` of all `AutofillMechanismStat` rows.
- **Clear.** DELETE removes the runs, keeps the counters, and returns both counts.
- **Strict body.** An unknown key in the body gives 422.

**Step 2–4:** Run `-m pytest -q tests/test_autofill_trace_router.py tests/test_autofill_telemetry_router.py`:
FAIL, then implement, then PASS.

**Step 5:** Commit: `feat(autofill): keep the last 50 run traces and count what each mechanism did`

---

### Task 7: One copy-only database guard for the scripts

`backend/scripts/` is a package (`scripts/__init__.py`). The eval runs as
`python -m scripts.eval_fill_decisions` (its docstring, L49), and the tests import it with
`from scripts import eval_fill_decisions as ev` (`tests/test_eval_fill_cases.py:13`). They also use
`ev.HERE`, `ev.DB_FILENAME`, `ev.refused_dirs` and `ev.refusal`, and they call
`monkeypatch.setattr(ev, "bind_read_only", …)` (L175-186, 223, 181).

**Files:**
- Create `backend/scripts/db_copy.py`:
  - Move `HERE`, `DB_FILENAME`, `refused_dirs`, `_identity`, `refusal` and `bind_read_only` here,
    unchanged (`eval_fill_decisions.py` L132-210).
  - Add `open_copy(db: Path, *, bind=None) -> None`. It does the env setup `main` does before app
    imports (L826-832): set `DATABASE_URL`, pop `TEST_DATABASE_URL`, and default
    `SETTINGS_DIR`/`LOGS_DIR` to a temp dir. Then it calls `(bind or bind_read_only)(db)`.
- Modify `backend/scripts/eval_fill_decisions.py`:
  - `from scripts.db_copy import HERE, DB_FILENAME, refused_dirs, refusal, bind_read_only, open_copy`,
    **by name**, so `ev.<name>` and the monkeypatch keep working.
  - `main` calls `open_copy(args.db, bind=bind_read_only)`, passing the module-level name so a patch
    of `ev.bind_read_only` still takes effect.

**Steps:** move the code, then run `-m pytest -q tests/test_eval_fill_cases.py` and expect PASS
unchanged.

Commit: `refactor(scripts): one copy-only database guard, shared by the eval and the trace reader`

---

### Task 8: `python -m scripts.fill_trace last`

**Files:**
- Create: `backend/scripts/fill_trace.py`
- Test: `backend/tests/test_fill_trace_script.py`

**Behaviour.** Run it from `backend/` as
`python -m scripts.fill_trace --db COPY last [--host H] [--n 1]`.
- Refusal: if `db_copy.refusal` returns a reason, print it and exit with code 2.
- Then `db_copy.open_copy`, then the import of the app.
- First line, per run: host, time, fields, filled, left, prefilled, halted, rounds.
- Per field: `[outcome]  "label"  shape  label←source  family  round N`.
- Then one line per step, for example:
  - `map → eeo.disability_status  jev 0.97 ≥0.90  1.2s`
  - `pick #2  fast 0.97 ≥0.90  (decided; jev was 0.82)  2.1s`
  - `polarity unsure  fast 0.61 (asked)`
  - `choose → no_effect (no_effect)  412ms`
  - `move click:o3 → progress  380ms`

**Test:**
- Build a temp SQLite database with `alembic upgrade head`. Copy how conftest's
  `_test_database_ready` points Alembic at a file.
- Insert one `AutofillRun` with a hand-built trace.
- Run `subprocess.run([sys.executable, "-m", "scripts.fill_trace", "--db", path, "last"], cwd=<backend dir>)`
  and assert that those lines appear.
- For the refusal: mirror `tests/test_eval_fill_cases.py:170-186`. Point the `DATA_DIR` env at a
  temp directory holding the file, and expect exit code 2. Don't create files inside the checkout;
  a worktree may have no `data/`, and `refused_dirs` only counts directories that exist.

**Steps:** test FAIL, then implement, then PASS. Commit:
`feat(scripts): fill_trace last — one run's decision path, field by field`

---

### Task 9: `python -m scripts.fill_trace report`

**Files:** `backend/scripts/fill_trace.py`, `backend/tests/test_fill_trace_script.py`

**Sections.** Plain text, from `AutofillMechanismStat` and the stored runs.

1. **Wasted actions.** Per family × kind: `tries`, the share that was not `progress`
   (`1 − progress/tries`; `effect_unknown` shown apart), and average ms (`ms / timed`). Sort by
   wasted ms, which is (the counts of the imported `REJECTED` set) × average ms. Don't list the
   effects again. Sort by wasted ms, which is (`no_effect + unexpected + reverted + refused` tries) × average
   ms. Show the top 15.
2. **Calibration.** Per decision op × engine × by × floor × band, with `answer`, `none` and
   `unknown` rows kept apart (polarity rows by `way`): `n`, then the `kept`, `left`, `failed` and
   `rejected` shares.
3. **First-engine evidence.** Per op × band of `first_p`, counting only the cases where the first
   engine's top choice was the answer that stood (`first_same`): `n` and the `kept` share. Pair it with
   the second opinion's value per op: `asked`, `decided`, and the share of `decided_kept`.
4. **Slowest fields.** From the stored runs, the 10 fields with the most steps and the most total
   ms: host, label, steps, ms, outcome.
5. **Suggestions.** Caveat (Task 6 review): a `first|pick|<CLOSEST_FLOOR>|…` row's floor is the
   one the second opinion's "closest" pick cleared, not the match floor Jev faced. Skip those
   rows in suggestions. From section 3 only: a `first|<op>|<band>` with at least 20 decisions and a
   kept share of at least 0.95, below the floor recorded on those steps. For example:
   `pick: jev 0.8–0.9 was confirmed and kept 41/42 — the jev floor 0.90 could be 0.80`.
   - If none qualifies, say so.
   - Sub-floor decisions without a second opinion are never kept (they abstain), so the outcome
     proxies cannot support a suggestion for them. Say that once, and point to the eval for those.

**Test:** seed counters and runs that produce one suggestion, and one candidate that falls short
at 19 decisions. Assert the suggestion line appears and the short one does not.

Commit: `feat(scripts): fill_trace report — wasted actions, calibration, second-opinion value`

---

### Task 10: The fill loop records each field's path

**Files:**
- Modify: `extension/shared/fill-loop.js`
- Test: `backend/tests/browser/test_fill_loop.py`
  - Harness: `run(page, load, **spec)` (L146-154), plus helpers `f`, `opt` and `row`.
  - The DRIVER's fake api passes spec `trace` / `polarity` keys through untouched (L55-56).

**Round-trip validation (add this first).** In `run()` (L146-154), validate every harness report
with `RunTrace.model_validate(out["report"]["trace"])`, the way `MODELS` validates request bodies.
Do it whenever `out["report"]` has a `trace`, so every browser test of the loop also proves that
the trace it builds is one the backend accepts. The live run must never be the first time a
backend schema meets an extension-built trace. When the sw posts a trace the schema rejects, the
whole run is lost silently.

**Recorder:**
- Each row gets `steps: []`.
- `note(fid, step)` appends a step while `steps.length < 40`.
- **Time model calls.** Make `post()` (L460-467) return `{res, ms}`, or record `ms` on the call,
  and set `ms` on the map, pick and step decision steps.
- **Time page actions** with `const t0 = Date.now()` around `broadcast`, and set `ms` on the step.

**Where to note:**

| Where | Note |
|---|---|
| `mapFields` apply (L1131-1138) | `{op:"map", ms, route, slot, why, ...decision(m.trace)}` |
| `pick` (L653-659) / `pickBatch` (L669-683), per field | when `got.polarity`: `{op:"polarity", way, engine, p}`; then `{op:"pick", ms, reason, option: <index of the chosen oid in offered>, ...decision(got.trace)}`. A batch's ms is the batch's, divided evenly across its fields. |
| `act` (L486-510), on **every** return path | `act()` returns early at L492 (`stale`), L498-499 (REFUSED → `refused`), L502-503 (`committed_while_opening` → `refused`) and L505-506 (a second no_effect → `refused`). Rename the body `actOnce` and wrap it: `act` times the call and notes `{op: action.op, effect: effectOf(result, got), word, ms}` from what came back. `action.op` is choose, set, write or move; add `move: action.mid` when `op == "move"`. Note nothing for halted or cancelled. |
| `explore` (L520-531) | `{op:"explore", ms, effect: exploreEffect(got), word: got.error ?? null}` |
| `adapt` per /step (L735-744) | `{op:"step", ms, move: chosen.mid ?? null, reason, ...decision(res.trace)}`, plus a polarity step when `res.polarity`. The `act` that follows notes itself. |
| `sweep` re-open (L1151-1174) | `{op:"sweep", effect:"reverted"}` |
| `lookUp` hit (L559-573) | `{op:"recipe"}`. A variant is an order string, never a move id; don't record it. |

- `decision(t)` copies only `engine`, `p`, `floor`, `second`, `first_p`, `first_same` and
  `chose_none`, and only those present.
- **Shape rules the backend schema enforces** (Task 5 review). One rejected trace loses the whole
  run silently.
  - `ms` is a whole number: use `Math.round`, including for a batch's ms divided across its fields.
  - `option` is the 0-based index into the options offered to /pick, or `null`, never `-1`.
  - `word` is `null`, never `""`.
  - `option_count` is the page's **full** option count; `options` is capped at 30.
  - `run_id` and `host` are lowercase.
- `effectOf` and `exploreEffect` implement the two tables above. A test pins `effectOf` against the
  header's page-outcome list (L109-114): every word listed there must have a row.

**Rounds:**
- Stamp `round` on the row in `finish`, `done` and `unconfirmed` (L374-390), using the loop's
  current round (L1525).
- Add `rounds` to the report (L1672).

**The run trace.** `buildRunTrace(report, rows, meta)` is published on `ns.fillLoop` beside
`buildLoopObservations`, and its result is returned as `report.trace`. **Allowlist only:** it builds
each field object from named sources and never spreads or iterates a row.

| Trace field | Source |
|---|---|
| `fid` | `row.fid` |
| `label` | `row.field.question`, blanked when `holdsValue` (L1694) matches it against **any** of `row.answer`, `row.value`, `row.wrote` or `row.leftover` |
| `label_source` | `row.field.source` |
| `shape` | `row.field.shape`, or "unknown" |
| `section` | `row.field.section`, blanked by the same rule |
| `required` | `row.field.required` |
| `options` | **only** the inventory's passive `row.field.options` texts, read before anything was typed, each blanked by the same rule; capped at 30 × 200. A `search:value` explore's results echo the typed value (employer, school and city names), so explore results are never used. |
| `option_count` | the length of that list |
| `family` | `row.field.recipe?.family`, when it matches `^f:[0-9a-z]{1,24}$` |
| `steps` | `row.steps` |
| `outcome` | the report status |
| `round` | `row.round` |

Per run:
- `run_id`, `host`;
- `started_at` / `ended_at`, taken at the start and end of `runFill` as ISO strings;
- `halted`: `"stopped"` or `"timeout"`, from the report's `stopped` / `timedOut`;
- `rounds`.

**Never** read `row.ignored` (it holds `"type:<typed value>"`, L431), `row.field.committed` (the
page's current value, `inventory.js:166`), `row.field.help`, or any explore option list.

**Step 1: Failing Playwright tests:**
- **Steps in order.** A two-field run: one select that Jev picks at 0.95, and one mapped text. The
  ops come out in order `map, pick, choose` and `map, write`, every action has `ms` and `effect`,
  and every decision has `ms`.
- **Polarity.** A pick that comes back from the fake api with `polarity` records a polarity step.
- **Wasted actions.** A first ignored gesture records `effect "no_effect"`, `word "no_effect"`.
  The second records `effect "refused"`.
- **A stopped run** has `halted == "stopped"`, and `rounds` plus each field's `round` are set.
- **Privacy, with sentinels.** The fake profile answers (`"555-0100"`,
  `"No, I do not have a disability"`) and sentinel strings injected into a typed value (so it lands
  in `row.ignored`), into `field.committed`, into `field.help`, into a label that echoes the
  written value, and into a search explore's results must appear nowhere in
  `JSON.stringify(report.trace)`.
- **The 40-step cap** holds.
- **The pinned `effectOf` table** covers every header word.

**Step 2:** Run `-m pytest -q tests/browser/test_fill_loop.py -k trace` and expect FAIL.

**Step 3:** Implement.

**Step 4:**
- Run `-m pytest -q tests/browser/test_fill_loop.py` and expect PASS, including the round-trip
  validation on every existing test.
- Then run `-m pytest -q tests/browser` in the background, about 11 minutes.

**Step 5:** Commit: `feat(companion): the fill loop records each field's decision path`

---

### Task 11: The panel sends the trace; the service worker scrubs and posts it

**Files:**
- Modify:
  - `extension/panel/actions/fill.js`, `startLoopFill` (L328-392): after `store.telemetry(…)` (L374),
    add `if (loop?.trace) store.trace(loop.trace);`.
  - `extension/panel/panel.js`, `actionStore()` (L4280): add
    `trace: (trace) => { ask("fill_trace", { trace }).catch((err) => console.warn("[maestro-cs] trace failed:", err)); }`.
  - `extension/sw.js`: add a `fill_trace` handler to HANDLERS beside `telemetry` (L545). When
    `telemetryEnabled === false` it returns `{posted: 0}`; otherwise it posts `scrubTrace(msg.trace)`
    to `/api/autofill/runs`.
- Tests:
  - `backend/tests/test_extension_sw_router.py`: mirror the telemetry tests around L612-640.
  - `backend/tests/test_extension_panel_fill.py`: mirror
    `test_loop_telemetry_is_one_value_free_observation_per_field` (L3882) with `_loop` (L3713). Add
    `"fill_trace": _reply({"posted": 1})` to `_loop`'s replies (L3716-3719), and give `LOOP_REPORT`
    a small `trace`.

**`scrubTrace`:**
- A whitelist at three levels (run, field, step), using exactly Task 5's names.
- Cut strings: labels and sections to 160; options to 30 × 160.
- Coerce numbers, and drop non-finite ones. Round `ms` to an integer. Drop an `option` outside
  0..249, and drop an empty `word`. Lowercase `host`.
- Drop a step whose `op` is not in the Op list.
- Drop a `slot`, `move`, `word`, `label_source` or `family` that does not match its Task 5
  pattern, rather than forwarding it. One odd profile key would otherwise 422 the whole run, and
  the run would be lost silently.
- Cut more than 200 fields, or more than 40 steps, rather than rejecting.
- Keep it near `scrubObservation`, in the same comment voice.

**Tests:**
- **Opted out.** Nothing is posted.
- **Injected keys.** A trace with `value`, `answer`, `wrote` and `prompt` keys injected at all
  three levels posts none of them. Grep the posted body for the injected strings.
- **Key sets.** The posted keys equal the schema's at each level.
- **Panel.** The panel sends exactly one `fill_trace` after a loop run, and none when the report has
  no trace.

**Steps:** tests FAIL, then implement, then PASS. Then run
`-m pytest -q tests/ -k extension --ignore=tests/browser`.

Commit: `feat(companion): send each run's trace, scrubbed, behind the telemetry switch`

---

### Task 12: Docs, pins and full suites

**Files:**
- `SYSTEM.md`, invariant `inv-autofill-telemetry-no-values` (about L336-343). Rewrite it in place
  so it covers traces:
  - what a trace holds;
  - the allowlist and the scrub;
  - the 50-run retention;
  - counters with no host or label;
  - that Clear deletes runs.

  The file is at its 1000/1000 cap: integrate, and cut elsewhere if needed. Then run
  `/opt/anaconda3/bin/python scripts/check_system_md.py` from the repo root; it must pass.
- `.system_md_enforcement.json`: `inv-autofill-telemetry-no-values` sits in `unpinned.ids` (L69).
  Pin it to its new tests:
  - the sw scrub test from Task 11;
  - `tests/test_autofill_trace_router.py`'s privacy test;
  - the Playwright sentinel test from Task 10.

  Remove it from `unpinned`, and make sure the SYSTEM.md gate still passes.
- `extension/INTERNALS.md`: a short "Run trace" paragraph beside the telemetry section (about L1223).
- `CHANGELOG.md`, under `## [Unreleased]` → `### Added`: one entry in user terms, e.g. "Autofill
  keeps a private record of how it decided each field, for diagnosing and tuning it."

**Gates (long suites in the background):**
- `-m pytest -q tests/ mcp_server/tests/`
- `-m pytest -q tests/browser`
- the slop ratchet for both surfaces
- `check_system_md`

Commit: `docs: the run trace in SYSTEM.md, INTERNALS and the changelog; pin the invariant`

---

### Task 13: Live check (the owner runs Docker)

1. Fast-forward local main to the branch. Give the owner `docker compose build backend` and
   `docker compose up -d backend` in separate blocks; the migration runs at startup.
2. The owner reloads the extension and runs Autofill on any application form.
3. Copy the database read-only to the scratchpad:
   `sqlite3 "file:<main>/data/maestro_cs.sqlite3?mode=ro" ".backup <scratch>/copy.sqlite3"`.
   Then, from `backend/`, run `python -m scripts.fill_trace --db <copy> last` and `… report`.
4. Check:
   - every field has steps;
   - decisions show an engine, `p` and ms;
   - page actions show an effect and ms;
   - **no answer value appears anywhere.** In Python, test each of the owner's profile name, email,
     phone and city against the copy's `autofill_runs.trace` JSON, printing only whether it is
     absent and never the values.
5. Delete the copy. Report the run's summary to the owner.
