# Form Questions by Country Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in this session) to implement this plan task-by-task.

**Goal:** Form answers follow the countries the user applies in: a generic set when no country is
chosen, each country's own questions when one is, built from shared packs.

**Architecture:** A question catalog in data (`backend/app/services/data/form_questions.yaml`)
that countries in `markets.yaml` name packs from. The backend resolves the set for the user's
countries and serves it; Profile, Setup and readiness read that one served set instead of the
hand-mirrored `GROUPS`. Per-country answers are folded into flat sections before the fill reads the
profile, as `autofill_country.with_work_auth` already does for work permits.

**Tech Stack:** FastAPI + Pydantic + PyYAML (backend), Next.js 16 / React 19 / react-query
(frontend), the Companion Chrome extension (plain JS).

**Design:** `docs/plans/2026-10-30-country-form-questions-design.md` (approved 2026-10-30).

---

## Goal Card

Goal: Stop treating every user like a US applicant. The form answers in Profile, Setup and the
Companion follow the countries the user applies in: a generic set when no country is chosen, each
country's own questions when one is, with countries sharing packs of common traits. Someone who
applies in several countries answers each fact about themselves once.

Principles:
- Never guess a knockout answer. Unknown stays unknown; the only derived answers are the
  citizenship rules the design lists, and an explicit answer always wins.
- A country's answers never reach another country's form.
- Country facts come from cited primary sources (phase 2), never from memory.
- Data, not code: adding a country or a pack is a YAML edit.

Non-goals:
- Per-country diversity questions (phase 4, a separate plan).
- New Profile tiles beyond renaming Work permits to Country answers; changes to currency or date
  defaults; stored answers for date of birth or marital status.

Autonomy: **peer** (Opus 5.5 executor, Opus 5.5 planner). Adapt *how* when the plan conflicts with
the repo and log each deviation in one line in the task's commit message body; anything touching
scope, a served shape other tasks read, or the Goal Card goes back to the planner as a deviation
note (planned / found / proposed / which Goal Card line).

## Decision this plan reverses

`backend/tests/test_autofill_groups_parity.py` records an earlier call: serving the question list
from the backend was rejected because labels and options are presentation and the Companion ships
on its own cadence. Per-country wording makes the labels country data, and the Companion reads the
stored profile keys, which do not change, never `GROUPS`. Task 1.9 records the reversal in
SYSTEM.md §10.

## Ground rules for every task

- Read `SYSTEM.md` first (§1, §3, §6 inv-work-permit-per-country and inv-eeo-standing-consent,
  §12), then `docs/entities/others.md` "Work permits per country" and the `market` setting.
- Backend tests from `backend/`: `.venv/bin/python -m pytest <paths> -q` for one file; the full
  suite is ALWAYS `.venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
  (name both paths). If `backend/.venv` is missing: `python3 -m venv .venv &&
  .venv/bin/python -m pip install -e ".[dev,mcp]"`.
- Frontend unit tests: `cd frontend && node --test lib/*.test.ts` and
  `node --test "components/**/*.test.mjs"`; gates `npx tsc --noEmit`, `npm run lint`,
  `npm run build`. Read `frontend/AGENTS.md` before frontend code.
- A node-tested `lib/*.ts` file cannot import another lib file's VALUES, only types (SYSTEM.md §12,
  2026-10-21). Pure helpers take the served question set as an argument.
- Many backend tests pin frontend source by string (`backend/tests/test_frontend_*.py`,
  `test_autofill_profile_veteran.py`). After renaming a frontend symbol, `git grep` the old string
  under `backend/tests/` and update the pin to the new code, keeping what it asserts.
- Commit after each task. End every commit message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No push.
- Never start the Docker stack; browser checks use a fresh stack on spare ports (Task 1.10).

---

# Phase 1 — The catalog, no visible change

Outcome: Profile, Setup and readiness read a served question set produced from YAML. Every user
sees exactly what they see today; a golden test proves it.

### Task 1.1: Freeze today's question set as a fixture

**Files:**
- Create: `frontend/scripts/dump-form-questions.ts`
- Create: `backend/tests/fixtures/form_questions_today.json` (generated)

**Step 1: Write the dump script**

```ts
// Writes today's hand-written question set to the backend's golden fixture (Task 1.3 compares the
// served set to it). Run once from frontend/: node scripts/dump-form-questions.ts
import { writeFileSync } from "node:fs";

import { GROUPS, workPermitFields } from "../lib/autofill-options.ts";

const out = {
  groups: GROUPS,
  permits: {
    us_visa: workPermitFields("us_visa"),
    uk: workPermitFields("uk"),
    generic: workPermitFields("generic"),
  },
};
writeFileSync("../backend/tests/fixtures/form_questions_today.json", JSON.stringify(out, null, 2) + "\n");
```

**Step 2: Run it**

Run: `cd frontend && node scripts/dump-form-questions.ts && head -20 ../backend/tests/fixtures/form_questions_today.json`
Expected: JSON starting `{"groups": [{"key": "personal", "title": "Personal details", ...`.

**Step 3: Commit** the script and the fixture (`test(form-questions): freeze today's question set`).
The script is deleted in Task 1.9, once `GROUPS` is gone; the fixture stays.

### Task 1.2: The catalog file and its loader

**Files:**
- Create: `backend/app/services/data/form_questions.yaml`
- Create: `backend/app/schemas/form_questions.py`
- Create: `backend/app/services/form_questions.py`
- Test: `backend/tests/test_form_questions.py`

**Step 1: Write the failing loader tests**

```python
from app.services import form_questions


def test_catalog_loads_and_every_group_has_fields():
    catalog = form_questions.catalog()
    assert [g.key for g in catalog.groups] == ["personal", "eeo", "eligibility", "preferences"]
    assert all(g.fields for g in catalog.groups)


def test_keys_are_unique_within_a_group():
    for group in form_questions.catalog().groups:
        keys = [f.key for f in group.fields]
        assert len(keys) == len(set(keys)), group.key


def test_a_shown_when_names_a_field_of_its_group():
    for group in form_questions.catalog().groups:
        keys = {f.key for f in group.fields}
        for field in group.fields:
            if field.when:
                assert field.when[0] in keys, (group.key, field.key)


def test_every_select_offers_options():
    catalog = form_questions.catalog()
    fields = [f for g in catalog.groups for f in g.fields] + [
        f for wording in catalog.permits.values() for f in wording
    ]
    for field in fields:
        if field.type == "select":
            assert field.options, field.key


def test_every_market_has_permit_wording():
    from app.services import markets

    for key in markets.keys():
        assert markets.get(key)["work_auth_vocab"] in form_questions.catalog().permits
```

**Step 2: Run to see them fail**

Run: `.venv/bin/python -m pytest tests/test_form_questions.py -q`
Expected: FAIL, `ImportError: cannot import name 'form_questions'`.

**Step 3: The schema** (`schemas/form_questions.py`). Field names mirror the frontend's `FieldDef`
exactly, so the served JSON drops into today's components:

```python
"""The form-question catalog's shape (services/data/form_questions.yaml) and what
GET /api/settings/autofill/questions serves. Names mirror the frontend's FieldDef."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Option(BaseModel):
    value: str
    label: str


class Field(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    optional: bool = False
    type: Literal["text", "select", "date"] | None = None
    boolean: bool = False
    options: list[Option] | None = None
    hint: str | None = None
    staleHint: str | None = None  # noqa: N815 (the frontend's name)
    when: tuple[str, str] | None = None
    # The address's state line: named and counted by where you live (markets.yaml).
    byHome: bool = False  # noqa: N815


class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    fields: list[Field]


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[Group]
    # Work-permit fields per `work_auth_vocab` (us_visa, uk, generic), expiry included.
    permits: dict[str, list[Field]]


class QuestionSet(BaseModel):
    """The set for one user's countries: groups resolved for where they live, permit fields per
    apply-in market, and whether any apply-in market offers a diversity set."""

    groups: list[Group]
    permits: dict[str, list[Field]]
    offers_eeo: bool
```

**Step 4: The YAML.** Transcribe `GROUPS` and `WORK_PERMIT_QUESTIONS` + `workPermitFields` from
`frontend/lib/autofill-options.ts` field by field, same order, same words, same options, keeping
their comments as YAML comments. Open the file with the same kind of header `markets.yaml` has (what
the file is, that it is domain data, that Task 1.3's golden test pins it). Shape:

```yaml
groups:
  - key: personal
    title: Personal details
    fields:
      - {key: first_name, label: First name}
      # ...
      - {key: state, label: State, byHome: true}
      # ...
      - {key: linkedin, label: LinkedIn profile link, optional: true}
  - key: eeo
    title: Diversity questions (voluntary)
    fields:
      - key: veteran_status
        label: Are you a veteran?
        staleHint: "Answer again: this question changed."
        type: select
        options:
          - {value: "no", label: "No, I am not a veteran"}
          # ...
permits:
  us_visa:
    - key: status
      label: Work authorization status
      type: select
      options:
        - {value: citizen, label: U.S. citizen}
        # ... US_WORK_STATUS in order
    - {key: authorized_now, label: "Authorized to work in the U.S. now?", type: select, boolean: true,
       options: [{value: "yes", label: "Yes"}, {value: "no", label: "No"}]}
    # ...
    - key: authorization_expires_on
      label: Authorization expires on
      hint: Leave it empty if your right to work there does not run out.
      type: date
      optional: true
  uk: [...]
  generic: [...]
```

Quote `"yes"` and `"no"` (YAML 1.1 reads them as booleans; `countries.yaml` already quotes `"NO"`).

**Step 5: The loader** (`services/form_questions.py`):

```python
"""The form-question catalog (data/form_questions.yaml) and the set resolved for one user.

Domain data, like markets.yaml: the questions Profile, Setup and setup readiness ask, in the words
they ask them. Loaded once and validated; a malformed file fails at import in tests, not at a
user's first Profile visit.
"""

from functools import cache
from pathlib import Path

import yaml

from app.schemas.form_questions import Catalog

_FILE = Path(__file__).parent / "data" / "form_questions.yaml"


@cache
def catalog() -> Catalog:
    return Catalog.model_validate(yaml.safe_load(_FILE.read_text(encoding="utf-8")))
```

**Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_form_questions.py -q`
Expected: 5 passed.

**Step 7: Commit** (`feat(form-questions): the question catalog in data`).

### Task 1.3: Resolve the set for a user's countries (golden test)

**Files:**
- Modify: `backend/app/services/form_questions.py`
- Test: `backend/tests/test_form_questions.py`

**Step 1: Write the failing golden test.** The expected value is today's frontend behaviour:
`groupFields(key, home)` relabels and un-counts the `byHome` state line, and permits come from the
market's `work_auth_vocab`.

```python
import json
from pathlib import Path

import pytest

from app.services import markets

_TODAY = json.loads(
    (Path(__file__).parent / "fixtures" / "form_questions_today.json").read_text(encoding="utf-8")
)


def _today_groups(home: str) -> list[dict]:
    """groupFields(key, home) for every group, as autofill-options.ts did it."""
    m = markets.get(home)
    out = []
    for group in _TODAY["groups"]:
        fields = []
        for field in group["fields"]:
            if field.get("byHome"):
                field = {**field, "label": m["state_label"] or field["label"], "optional": m["asks_state"] is False}
            fields.append(field)
        out.append({**group, "fields": fields})
    return out


def _served(model) -> dict:
    return model.model_dump(exclude_defaults=True)


def _fixture(value) -> dict:
    """The fixture through the same schema, so defaults compare alike."""
    from app.schemas.form_questions import Group

    return Group.model_validate(value).model_dump(exclude_defaults=True)


@pytest.mark.parametrize("home", list(markets.keys()))
def test_every_home_gets_todays_groups(home):
    got = form_questions.resolve(home=home, apply_in=[home])
    assert [_served(g) for g in got.groups] == [_fixture(g) for g in _today_groups(home)]


@pytest.mark.parametrize("market", list(markets.keys()))
def test_every_market_gets_todays_permit_fields(market):
    from app.schemas.form_questions import Field

    got = form_questions.resolve(home="US", apply_in=[market])
    vocab = markets.get(market)["work_auth_vocab"]
    want = [Field.model_validate(f).model_dump(exclude_defaults=True) for f in _TODAY["permits"][vocab]]
    assert [f.model_dump(exclude_defaults=True) for f in got.permits[market]] == want


def test_offers_eeo_follows_the_apply_in_markets():
    assert form_questions.resolve(home="IN", apply_in=["US"]).offers_eeo is True
    assert form_questions.resolve(home="US", apply_in=["IN", "DE"]).offers_eeo is False
```

Note: the fixture's `byHome` field carries `byHome: true` and the served one must too, so a home
that drops it from the count still shows the line (today's behaviour).

**Step 2: Run to see it fail**

Run: `.venv/bin/python -m pytest tests/test_form_questions.py -q`
Expected: FAIL, `AttributeError: module ... has no attribute 'resolve'`.

**Step 3: Implement `resolve`**

```python
from app.schemas.form_questions import Field, Group, QuestionSet
from app.services import markets


def _for_home(field: Field, home: str) -> Field:
    if not field.byHome:
        return field
    m = markets.get(home)
    return field.model_copy(update={"label": m["state_label"] or field.label, "optional": m["asks_state"] is False})


def resolve(*, home: str, apply_in: list[str]) -> QuestionSet:
    """The questions for someone who lives in `home` and applies in `apply_in` (market keys)."""
    cat = catalog()
    groups = [
        Group(key=g.key, title=g.title, fields=[_for_home(f, home) for f in g.fields]) for g in cat.groups
    ]
    permits = {m: cat.permits[markets.get(m)["work_auth_vocab"]] for m in apply_in}
    return QuestionSet(groups=groups, permits=permits, offers_eeo=any(markets.offers_eeo(m) for m in apply_in))
```

Check how `market_settings.offers_eeo` treats an empty `apply_in` and mirror it (`apply_in` empty
reads as `[home]`, docs/entities/others.md "`market` setting"); add a test for it.

**Step 4: Run the tests**, expect all green. **Step 5: Commit**
(`feat(form-questions): resolve the set for a user's countries`).

### Task 1.4: Readiness reads the catalog

**Files:**
- Modify: `backend/app/services/setup_status.py` (delete `_PERSONAL`, `_EEO`, `_PREFERENCES`,
  `_WORK_AUTH_CORE`, `_US_VISA_CORE`, `_personal_fields`)
- Test: existing `backend/tests/test_setup_status*.py` (run them; they must pass unchanged)

**Step 1:** Add a helper in `form_questions.py` and a test for it:

```python
def required_keys(fields: list[Field]) -> list[str]:
    """The keys setup readiness counts: every field not `optional`."""
    return [f.key for f in fields if not f.optional]
```

Test: `required_keys(resolve(home="UK", apply_in=["UK"]).groups[0].fields)` has no `state`;
for `home="US"` it does.

**Step 2:** In `_autofill_step`, resolve once from the stored market
(`form_questions.resolve(home=market.home, apply_in=market.apply_in)`) and take each group's
required keys from it; `_work_permits` takes `set.permits[market]`'s required keys (expiry is
optional there, so it is not counted, as today). Keep the `offers_eeo` branch as it is.

**Step 3:** Run `tests/test_setup_status*.py` and `tests/test_form_questions.py`. Expected: pass
with no test edits. **Step 4: Commit** (`refactor(setup): readiness counts the catalog's questions`).

### Task 1.5: Serve the set

**Files:**
- Modify: `backend/app/routers/settings.py` (beside `GET /autofill`, line ~322)
- Test: `backend/tests/test_form_questions_route.py`

**Step 1: Failing test** with the repo's TestClient fixture (copy the client/setup pattern from an
existing settings-route test such as `test_market_settings.py`):

```python
def test_the_questions_follow_the_market(client):
    client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "US"]}})
    body = client.get("/api/settings/autofill/questions").json()
    personal = next(g for g in body["groups"] if g["key"] == "personal")
    state = next(f for f in personal["fields"] if f["key"] == "state")
    assert state["label"] == "County" and state["optional"] is True
    assert set(body["permits"]) == {"UK", "US"}
    assert body["permits"]["US"][0]["key"] == "status"
    assert body["offers_eeo"] is True
```

**Step 2:** Run, see 404. **Step 3:** Implement:

```python
@router.get("/autofill/questions", response_model=QuestionSet)
def get_autofill_questions(db: Annotated[Session, Depends(get_db)]):
    """The form questions for where you live and apply (services/form_questions): Profile, Setup and
    readiness read this one set, never a list of their own."""
    market = market_settings.get_market(db)
    return form_questions.resolve(home=market.home, apply_in=market.apply_in)
```

Serve with `response_model_exclude_defaults=True` only if the frontend tolerates missing keys (it
does: every `FieldDef` key but `key` and `label` is optional). **Step 4:** Run, pass.
**Step 5: Commit** (`feat(settings): serve the form questions`).

### Task 1.6: Frontend type and hook

**Files:**
- Modify: `frontend/lib/types.ts` (add `QuestionSet`)
- Create: `frontend/components/profile/use-form-questions.ts`
- Modify: `frontend/components/profile/country-fields.tsx` (`useCountriesAutosave` invalidates it)

```ts
// lib/types.ts
/** GET /api/settings/autofill/questions (backend schemas/form_questions.py QuestionSet). */
export type QuestionSet = {
  groups: GroupDef[];
  permits: Record<string, FieldDef[]>;
  offers_eeo: boolean;
};
```

`GroupDef` and `FieldDef` move from `lib/autofill-options.ts` into `lib/types.ts` (types only) so
both files share them; re-export from autofill-options to keep imports working.

```ts
// components/profile/use-form-questions.ts
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { QuestionSet } from "@/lib/types";

export const FORM_QUESTIONS_KEY = ["settings", "autofill", "questions"] as const;

/** The form questions for where you live and apply: the one list Profile and Setup ask from. */
export function useFormQuestions() {
  return useQuery({
    queryKey: FORM_QUESTIONS_KEY,
    queryFn: () => apiFetch<QuestionSet>("/api/settings/autofill/questions"),
  });
}
```

Match the existing query-key style (look at `use-autofill-query.ts`). In `useCountriesAutosave`'s
success path, invalidate `FORM_QUESTIONS_KEY` beside what it already invalidates.

Run `npx tsc --noEmit`. Commit (`feat(profile): read the served form questions`).

### Task 1.7: Pure helpers take the served set

**Files:**
- Modify: `frontend/lib/autofill-options.ts`
- Modify: `frontend/lib/setup-answers.ts`
- Test: `frontend/lib/autofill-options.test.ts`, `frontend/lib/setup-answers.test.ts` (if present)

New signatures (the set is always the first argument after `profile`, or first when there is no
profile):

```ts
export function groupFields(questions: QuestionSet, key: string): FieldDef[];
export function permitFields(questions: QuestionSet, market: string): FieldDef[];        // was workPermitFields(vocab)
export function permitQuestions(questions: QuestionSet, market: string): FieldDef[];     // required only
export function groupCount(profile: Profile, questions: QuestionSet, group: string): Count;
export function permitCount(profile: Profile, questions: QuestionSet, market: string): Count;
export function withField(profile: Profile, questions: QuestionSet, group: string, key: string,
                          value: string | boolean | undefined): Profile;
export function declinedEeo(profile: Profile, questions: QuestionSet): Record<string, string>;
export function missingAnswers(profile: Profile, questions: QuestionSet, applyIn: readonly string[]): MissingAnswer[];
```

Delete `GROUPS`, `WORK_PERMIT_QUESTIONS`, `US_WORK_STATUS`, `permitVocab`, `WorkAuthVocab`,
`HomeMarket`'s `byHome` resolution and `homeMarket` if nothing else reads it (the server resolves
the state line). `missingAnswers` keeps its order (each apply-in country's permit first, then
personal, then preferences, then diversity when `questions.offers_eeo`). Rewrite the file header:
the questions come from the backend; nothing here mirrors a backend list.

Tests: replace imports of `GROUPS` / `US_WORK_STATUS` with a small inline `QuestionSet` built in
the test file (a node-tested file cannot import another lib file's values), covering the same cases
the existing tests cover. Run `cd frontend && node --test lib/*.test.ts`; all pass.

Commit (`refactor(profile): helpers read the served question set`).

### Task 1.8: Components read the hook

**Files (each reads `useFormQuestions()` and passes the set to the helpers):**
- `frontend/components/profile/contact.tsx`, `start-and-pay.tsx`, `eligibility.tsx`,
  `diversity.tsx`, `work-permits.tsx`, `next-up.tsx`
- `frontend/components/setup/setup-answers-step.tsx`, `setup-done.tsx`

While the set loads, render what the component renders while the profile loads (reuse its
existing loading branch; do not add a new skeleton). A failed load uses the component's existing
error branch. `work-permits.tsx` reads `permitFields(questions, key)` per row instead of
`workPermitFields(market?.work_auth_vocab)`.

Then `git grep -n 'groupFields("\|permitQuestions(\|workPermitFields(\|groupCount(' backend/tests`
and update each source pin (e.g. `test_frontend_every_item_has_a_home.py` lines 80-81) to the new
call text.

Run: `npx tsc --noEmit && npm run lint`, `node --test "components/**/*.test.mjs"`, and the pinned
backend tests. Commit (`refactor(profile, setup): ask from the served questions`).

### Task 1.9: Retire the mirror; record the reversal

**Files:**
- Delete: `backend/tests/test_autofill_groups_parity.py`, `frontend/scripts/dump-form-questions.mjs`
  (Task 1.1 shipped it as `.mjs`: tsc rejects `.ts` import paths)
- Delete: `setup_status.py`'s `_PERSONAL`, `_EEO`, `_PREFERENCES`, `_WORK_AUTH_CORE`, `_US_VISA_CORE`,
  `_personal_fields` (kept by Task 1.4 only for the tests); point `test_market_settings.py:236-237`
  at the catalog (`form_questions.required_keys`); drop the `markets` import if only they used it
- Review follow-ups from Tasks 1.4–1.5:
  - `test_form_questions.py`: every permit field key is a `WorkAuth.model_fields` key whose default is
    `None` (readiness reads them with `getattr`; a YAML-only key would 500 setup status, and a key with
    a non-None default would always count as answered). No `getattr(..., None)` fallback.
  - `setup_status._autofill_step`: use the resolved set's `offers_eeo` instead of peeking the market
    again through `market_settings.offers_eeo(db)`.
  - `routers/settings.py`: move the questions GET after the GET/PUT/PATCH `/autofill` group; its
    docstring says readiness calls `resolve`, Profile and Setup read the route.
  - `test_form_questions.py:50-56`: split the frozen test from the extra-key test, or rename it.
  - `test_form_questions_route.py`: assert the market PUT's status.
- Review follow-ups from Tasks 1.6–1.8:
  - `frontend/components/render-harness.mjs` `servedQuestions` re-implements `resolve` in JS from the
    frozen "today" fixture (ignores home; throws on an unknown market). Replace it with per-scenario
    served-set fixtures written from `form_questions.resolve(...)` by the backend (e.g.
    `backend/tests/fixtures/served_questions/<scenario>.json` for the scenarios the render tests use),
    a backend test that fails when a fixture differs from `resolve`'s output (with a documented
    regenerate command), and the harness only loading them.
  - `backend/tests/test_frontend_every_item_has_a_home.py` (~92-186) matches inline YAML text; pin
    through `form_questions.catalog()` like the veteran and covenant tests, so Phase 3's new
    per-question keys do not break ~40 needles.
  - Naming: a `QuestionSet` value is `questionSet` everywhere (Profile names it `questions`, Setup
    `questionSet`; Setup's `FormQuestion[]` stays `questions`); `questionAnswered` takes
    `(question, profile, questionSet)` → keep the set right after `profile` where a profile is passed.
  - Drop the unused `GroupDef` re-export from `lib/autofill-options.ts`.
- Modify: `backend/tests/test_autofill_profile_veteran.py:135-155` (read the veteran question from
  `form_questions.catalog()` instead of the TS source; keep every assertion)
- Modify: `SYSTEM.md` §2 (`services/data/*.yaml` now includes `form_questions`; `form_questions`
  in the services list), §10 (one decision line: the question list is served from
  `data/form_questions.yaml`; supersedes the hand-mirror kept because labels were presentation)
- Modify: `docs/entities/others.md` ~line 531 (readiness reads the catalog; no mirror)
- Modify: `docs/frontend-conventions.md` ~line 1203 if it names `GROUPS`

Run `.venv/bin/python ../scripts/check_system_md.py` (find its exact invocation in SYSTEM.md §9) and
fix what it reports. Commit (`docs: the form questions are served from one catalog`).

### Task 1.10: Phase 1 gates and a look

1. Full backend suite: `.venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`.
2. Frontend: `node --test lib/*.test.ts`, `node --test "components/**/*.test.mjs"`,
   `npx tsc --noEmit`, `npm run lint`, `npm run build`.
3. Fresh stack on spare ports (uvicorn on e.g. 8765 with a scratch `DATABASE_URL` and `*_DIR`s;
   `API_PROXY_BACKEND=http://127.0.0.1:8765 npx next dev -p 3100`), never the Docker stack. In the
   browser pane at 1280 and 1024 wide: Profile (Contact, Work permits, Start and pay, the two folds,
   Next up) and Setup's answers step read exactly as on `main` for a US home and for a UK home
   applying in UK + US.
4. Report results with the commands' output. Phase 1 ends here: **planner checkpoint** (critique
   against the Goal Card, then Phase 2).

---

# Phase 2 — Check the country facts

Outcome: `docs/plans/2026-10-30-country-form-questions-sources.md`, one row per fact with a
primary source, the date checked, and **verified / contested / not found**. Nothing is built from a
fact that is not verified. Run with the research skill (`mattpocock-skills:research`), one
subagent per country group, in parallel.

### Task 2.1: Research

Each fact below: the exact list or rule, the primary source URL (government, regulator, or the
standard's owner; a job board only for "what forms ask" conventions, and then two independent
ones), the date checked.

1. **Canada**: the work-status choices a job form should offer (citizen, permanent resident, open
   work permit, employer-specific work permit, post-graduation work permit, study permit, …), from
   IRCC (canada.ca).
2. **Australia**: citizen, permanent resident, New Zealand citizen (Special Category visa),
   temporary visa with full or limited work rights, needs sponsorship (Skills in Demand / 482),
   from the Department of Home Affairs.
3. **United Arab Emirates**: residence and work statuses (employment visa, family/dependant visa,
   Golden visa, Green visa, freelance permit, visit visa, GCC national, Emirati), from u.ae, ICP or
   MOHRE; whether an Emirati or GCC national needs a work permit.
4. **Citizenship rules**: EU/EEA/Swiss citizens' right to work in Germany, the Netherlands and
   Ireland with no permit (any current transitional limits); UK citizens in Ireland and Irish
   citizens in the UK (Common Travel Area), from Your Europe, gov.ie / citizensinformation.ie and
   gov.uk.
5. **Addresses**: whether a UAE address requires an Emirate line, and what it is called (Google's
   address metadata, the set Chrome autofill uses; `markets.yaml`'s `asks_state` comment cites it).
6. **India**: how forms ask pay and notice (current CTC, expected CTC, in lakhs per annum; notice
   in days; "serving notice" and last working day); total and relevant experience in years.
7. **Pay terms**: Australia "including super"; Gulf monthly basic + housing + transport; German
   and Dutch gross annual.
8. **CEFR**: that German and Dutch application forms ask language level in CEFR (A1–C2), and the
   level names.

### Task 2.2: Owner review (checkpoint)

Present the sources file to the owner; contested and not-found rows are cut from phase 3 or kept
as open items, the owner's call. Then the planner expands Phase 3 below into bite-size TDD steps
with the verified data, and commits the expanded plan.

**Done 2026-10-30.** `docs/plans/2026-10-30-country-form-questions-sources.md` (12203e4b): 125
facts, 97 verified. The owner approved all 23 proposed changes in its "What the sources change in
the design" section; every contested or not-found row is cut, left to the user, or handled at fill
time as its "Contested and not-found rows" section says. Phase 3 below is expanded from them;
"Sources n" in a task points to that section's numbered change.

---

# Phase 3 — Packs and countries

Outcome:
- The nine countries ask their own questions, and someone with no country chosen gets the generic
  set.
- A citizenship settles the work-permit answers the sources verified.
- Profile's Country answers and Setup ask each fact once.
- The fill reads one country's answers per job.

"Sources n" points to change n in the sources doc's "What the sources change in the design"
(approved 2026-10-30). Ground rules as Phase 1. Each task ends green on its own tests plus the
files they touch; Task 3.13 runs everything.

## Decisions taken while expanding

The planner's calls, made from the code. Each changes *how* the design is built, never its scope.

1. **No country chosen asks no work-permit questions. The owner said yes on 2026-10-30.** The
   approved design's generic set included the three permit Yes/No questions, so this was a scope
   change.
   - Why: a permit answer belongs to a country. Storing one under the default US is the US-shaped
     default this plan removes. Setup's Where step comes before its answers step, so anyone who
     goes through Setup has countries.
   - Who it touches: only an install with no stored market row, which never opened Profile or
     Setup. A seeded row from before the mark reads as chosen (Task 3.1).
2. **No `learn_to` on `/context`.**
   - The Companion's pause row already finds a learned answer's place from its own field table
     (`extension/shared/profile-fields.js`, `profileFieldFor`).
   - It already gets the job's market from `/context` (`panel/actions/pause.js`,
     `workAuthPlaceFor`).
   - Country answers join that table and the market rewrite work permits already use (Task 3.8).
   - An older Companion keeps writing them to `custom`, as the design accepted.
3. **Expected pay per country is optional.** On that country's jobs it folds over
   `preferences.desired_salary`, which stays the generic answer and the one readiness counts.
   Requiring the per-country answer would drop every existing user's readiness over an answer they
   already gave.
4. **Pack questions stay in their group.** In `form_questions.yaml` they are tagged with their pack
   (`pack: us_screening`), and a field is shown only while some apply-in country names its pack.
   Today's field order is kept, so a chosen US user's set is unchanged.
   - Three of the design's packs are not field tags: `eu_movement` is a citizenship rule,
     `visa_status` is the per-market status lists, and `pay_terms` is the per-market pay wording.
5. **Current location is not a new question.** Indian forms' "current location" is a city, which
   `personal.city` holds; its describe says so (Sources 22).
6. **Citizenship counts toward readiness.** It is the one new required answer: existing users see it
   missing once. Every other new question, the CA, AU and AE status lists included, is optional, so
   nobody's count drops for anything else.
7. **The Companion's version is not bumped here.** It moves at the next release (docs/RELEASING.md
   bumps it with the app).

## Shared shapes

Several tasks read these, so they are fixed here. Change them only with a deviation note.

**Catalog field** (`schemas/form_questions.py` `Field`) gains:
- `type`: adds `"number"` and `"countries"` (a list of ISO codes, edited with `CountryPicker`).
- `byHome: Literal["state", "postcode"] | None`, replacing the bool. It names the address line that
  is labelled and counted by where you live.
- `unless: tuple[str, list[str]] | None`: hidden while another field of the same list holds one of
  these values (Task 3.5 sets it on the expiry, for statuses that never expire).
- `pack: str | None`: shown only while an apply-in country names this pack.
- `describe: str | None` and `policy: Literal["exact", "flag", "any"] | None`: what the fill loop
  reads for this answer (Task 3.7). Optional; absent means today's rule.
- `fills: str | None` (country answers only): the flat slot it folds into on that country's jobs,
  for example `"preferences.desired_salary"`.

`Option` gains `noExpiry: bool = False` (statuses only).

`pack`, `describe`, `policy`, `fills` and `noExpiry` are catalog-only. Declare them with
`pydantic.Field(default=None, exclude=True)` (import it as `PydanticField`: the schema's own class
is `Field`) so they are never served. Two things follow:
- The served shape stays lean.
- Phase 1's golden comparison keeps passing while the data gains them (Task 3.2).

**Served set** (`GET /api/settings/autofill/questions`):

```python
class DerivedAnswer(BaseModel):
    value: str | bool
    via: str  # the ISO code of the citizenship that settles it ("IE")


class CountryQuestions(BaseModel):
    market: str                # "DE"
    label: str                 # "Germany"
    permits: list[Field]       # stored in work_auth_by_country[market]
    answers: list[Field]       # stored in answers_by_country[market]
    derived: dict[str, DerivedAnswer] = {}


class QuestionSet(BaseModel):
    groups: list[Group]                 # facts about you, each once, pack fields included
    countries: list[CountryQuestions]   # apply-in order; [] when no country is chosen
    language_fields: list[Field] = []   # extra fields on each language (CEFR while DE or NL)
    offers_eeo: bool
    chosen: bool
```

Phase 1's `permits` stays served beside `countries` until Task 3.10 moves the frontend; that task
cuts it.

**Stored answers:**
- `personal.citizenships`: ISO alpha-2 codes, upper-cased and deduped. `GB` reads "British citizen"
  (Sources 2).
- `answers_by_country: {market: {key: value}}`, keyed by market like `work_auth_by_country`. Its
  keys are that market's `CountryQuestions.answers`.
- `work_auth_by_country[market].status`: one of that market's `work_status` values.

**Data:**
- Each market in `markets.yaml` gains:
  - `packs: [...]`;
  - `work_status: us | ca | au | ae | null`;
  - `pay: {label, hint?}`;
  - `asks_postcode` (true everywhere but AE).
- `work_auth_vocab` gains `ca` and `ae`.
- `form_questions.yaml` gains `statuses`, `answers`, `language_fields` and `citizenship`.

---

### Task 3.1: "You chose this" and the generic set

**Files:**
- Modify: `backend/app/schemas/market_settings.py`, `backend/app/services/market_settings.py`
- Modify: `backend/app/services/form_questions.py`, `backend/app/routers/settings.py`
- Test: `backend/tests/test_market_chosen.py` (new), `backend/tests/test_form_questions.py`

**Step 1: Failing tests** (`test_market_chosen.py`; copy the `settings_dir` fixture from
`tests/test_settings_agent_patch.py`):

```python
from app.services import form_questions, market_settings, text_settings
from app.schemas.market_settings import MarketSetting


def test_a_new_install_starts_unchosen(client):
    assert client.get("/api/settings/market").json()["value"]["chosen"] is False
    served = client.get("/api/settings/autofill/questions").json()
    assert served["chosen"] is False and served.get("permits", {}) == {}


def test_saving_where_you_apply_marks_it_chosen(client):
    client.put("/api/settings/market", json={"value": {"home": "US", "apply_in": ["US"]}})
    assert market_settings.peek_market().chosen is True
    served = client.get("/api/settings/autofill/questions").json()
    assert list(served["permits"]) == ["US"]


def test_an_agent_setting_markets_marks_it_chosen(client):
    client.patch("/api/settings/market", json={"value": {"apply_in": ["DE"]}})
    assert market_settings.peek_market().chosen is True


def test_a_row_stored_before_the_mark_reads_as_chosen(settings_dir):
    text_settings.set_text("market", "market.json", '{"home": "US", "apply_in": []}')
    assert market_settings.peek_market().chosen is True


def test_the_mark_leaves_currency_alone():
    # Non-goal: currency and date defaults. `is_set` ignores `chosen`.
    assert market_settings.is_set(MarketSetting(chosen=True)) is False
```

In `test_form_questions.py`:

```python
def test_unchosen_resolves_no_country():
    qs = form_questions.resolve(home="US", apply_in=[], chosen=False)
    assert qs.permits == {} and qs.offers_eeo is False and qs.chosen is False
```

(Task 3.5 adds that unchosen drops the US screening questions, once the packs exist.)

**Step 2: Run them.**
`.venv/bin/python -m pytest tests/test_market_chosen.py tests/test_form_questions.py -q`. Expected:
they fail on `chosen`.

**Step 3: Implement.**
- `MarketSetting.chosen: bool = False`. The legacy rule lives in the setting's `migrate` hook, not
  the model, so `MarketSetting()` stays unchosen:

  ```python
  class _Market(JsonSetting[MarketSetting]):
      def migrate(self, payload):
          # Stored before the mark (2026-10-30): that install kept the set it was shown.
          if isinstance(payload, dict) and "chosen" not in payload:
              return {**payload, "chosen": True}
          return payload
  ```

  A seeded default row is written by `MARKET.set(MarketSetting())`, so it carries
  `"chosen": false`. Confirm that by reading `text_settings.get_text`'s seed path, and log the rule
  in the commit.
  - A row that was never stored (`""`) reads as `MarketSetting()`, so it is unchosen: that install
    never opened Profile or Setup (Decision 1).
  - `MarketSetting._legacy` (`schemas/market_settings.py`) rebuilds a `{"market": X}` payload, so
    make it carry `chosen` through.
- `set_market` and `patch_place` save with `chosen=True`. Sync writes the peer's text as it is, so
  it carries the peer's mark.
- `is_set`: `setting.model_copy(update={"chosen": False}) != MarketSetting()`, so currency
  behaves as before.
- `resolve(*, home, apply_in, chosen=True, citizenships=())`. When `chosen` is false:
  - no permits;
  - `offers_eeo` false;
  - the state line optional.

  `QuestionSet` gains `chosen`; `citizenships` is unused until Task 3.5. The route and
  `setup_status` pass `market.chosen`.

**Step 4: Run the tests**, then `tests/test_form_questions_route.py tests/test_setup_status*.py`.
These existing tests assume a fresh install is US and break. Rewrite each to the unchosen rule, or
give it a chosen market where US is what it means to test:
- `test_form_questions_route.py:28-36` (US permits, a required State, `byHome`);
- `test_setup_status.py:16-23` (`work_auth` blocking on a fresh install);
- `test_setup_status.py:291-326` (work_auth 3 of 4 with no market);
- `test_setup_status.py:426-433` (the state counted with no home).

Expected: all pass.

**Step 5: Commit** (`feat(market): an unchosen market gets the generic questions`).

### Task 3.2: Packs, statuses and the UAE in data

**Files:**
- Modify: `backend/app/services/data/markets.yaml`, `backend/app/services/markets.py`
- Modify: `backend/app/services/data/form_questions.yaml`, `backend/app/schemas/form_questions.py`
- Modify: `backend/app/services/form_questions.py`
- Test: `backend/tests/test_form_questions.py`, `backend/tests/test_markets*.py`

**Step 1: Failing loader tests:**

```python
from app.services import countries, markets


def test_every_market_names_packs_and_lists_that_exist():
    cat = form_questions.catalog()
    tagged = {f.pack for g in cat.groups for f in g.fields if f.pack}
    tagged |= {f.pack for f in [*cat.answers, *cat.language_fields] if f.pack}
    for key in markets.keys():
        m = markets.get(key)
        assert set(m["packs"]) <= tagged, key
        assert m["work_status"] is None or m["work_status"] in cat.statuses, key
        assert m["work_auth_vocab"] in cat.permits, key
        assert m["pay"]["label"], key


def test_every_tagged_pack_is_named_by_a_market():
    named = {p for k in markets.keys() for p in markets.get(k)["packs"]}
    cat = form_questions.catalog()
    tags = {f.pack for g in cat.groups for f in g.fields if f.pack}
    assert tags | {f.pack for f in [*cat.answers, *cat.language_fields] if f.pack} <= named


def test_a_key_appears_once_across_groups_and_answers():
    cat = form_questions.catalog()
    keys = [f.key for g in cat.groups for f in g.fields] + [f.key for f in cat.answers]
    assert len(keys) == len(set(keys))


def test_every_country_answer_says_where_it_fills():
    for field in form_questions.catalog().answers:
        assert field.fills and field.fills.count(".") == 1, field.key


def test_status_values_are_unique_per_list_and_citizen_is_first():
    for name, options in form_questions.catalog().statuses.items():
        values = [o.value for o in options]
        assert len(values) == len(set(values)), name
        assert values[0] == "citizen", name  # the own-country rule sets it (Task 3.4)


def test_citizenship_rules_name_iso_codes_and_markets():
    cit = form_questions.catalog().citizenship
    for members in cit.groups.values():
        assert all(countries.normalize(c) == c for c in members)
    for rule in cit.rules:
        assert all(markets.is_supported(m) for m in rule.markets)
        assert rule.source.startswith("https://")


def test_the_uae_market():
    ae = markets.get("AE")
    assert ae["key"] == "AE" and ae["currency"] == "AED"
    assert ae["asks_state"] is True and ae["state_label"] == "Emirate"
    assert ae["asks_postcode"] is False and ae["eeo_module"] is None
    assert markets.country_code("AE") == "AE" and markets.for_country("AE") == "AE"
```

**Step 2: Run them.** Expected: they fail on the missing data.

**Step 3: The data.** Add `markets.py` `_load()` reads for `packs` (default `[]`), `work_status`
(default None), `pay` (default `{"label": "Expected salary"}`) and `asks_postcode` (default true).

Each market's new keys in `markets.yaml`:

| Market | `packs` | `work_status` | `work_auth_vocab` | `pay.label` |
|---|---|---|---|---|
| US | `[us_screening]` | `us` | `us_visa` | Expected salary (USD) |
| UK | `[]` | null | `uk` | Expected salary (GBP) |
| CA | `[]` | `ca` | `ca` | Expected salary (CAD) |
| AU | `[]` | `au` | `generic` | Expected base salary, excluding super (AUD per year) |
| IE | `[]` | null | `generic` | Expected salary (EUR) |
| IN | `[india_basics]` | null | `generic` | Expected CTC (₹ per year) |
| DE | `[cefr]` | null | `generic` | Expected gross annual salary (EUR) |
| NL | `[cefr]` | null | `generic` | Expected gross monthly salary, excluding holiday allowance (EUR) |
| AE | `[gulf]` | `ae` | `ae` | Expected total monthly salary (AED) |

- The AU, IN, DE, NL and AE wordings cite Sources 14, 18, 16, 15 and 17 in a comment.
- US, UK, CA and IE name only the currency: their pay terms were not researched.
- The AE entry:

```yaml
  - key: AE
    label: United Arab Emirates
    currency: AED
    date_format: DMY
    eeo_module: null          # not verified
    work_auth_vocab: ae
    work_status: ae
    packs: [gulf]
    # Google's address data (chromium-i18n ssl-address/data/AE, read 2026-10-30):
    # "require": "AS", "state_name_type": "emirate", no postcode line.
    asks_state: true
    state_label: Emirate
    asks_postcode: false
    pay:
      label: Expected total monthly salary (AED)
      hint: Basic pay plus allowances, per month.
```

In `form_questions.yaml`:
- **Tag** `over_18` and `non_compete` with `pack: us_screening`, in place. `resolve` ignores tags
  until Task 3.5.
- **Statuses.** Give the US status options an anchor and move them to `statuses.us: &us_statuses`.
  `permits.us_visa`'s status field reads `options: *us_statuses` until Task 3.5 builds the status
  field per market and drops it there.
  - Add `statuses.ca`, `statuses.au` and `statuses.ae` from the sources doc's Proposed data. Values
    and labels follow the table below; each list's comment cites its rows.
  - `noExpiry: true` on: US `citizen`, `permanent_resident`, `not_authorized`; CA `citizen`,
    `permanent_resident`, `maintained_status`, `no_status`; AU `citizen`, `permanent_resident`,
    `nz_citizen`; AE `citizen`, `gcc_national`, `no_visa`.

  | List | Values (in order) |
  |---|---|
  | ca | citizen (Canadian citizen), permanent_resident, open_work_permit, pgwp (Post-graduation work permit), iec_working_holiday, employer_specific (Employer-specific work permit), study_permit, maintained_status, permit_exempt (Allowed to work without a work permit), no_status (Visitor or no work authorization), other |
  | au | citizen (Australian citizen), permanent_resident, nz_citizen (New Zealand citizen, Special Category visa subclass 444), skills_in_demand (Skills in Demand visa, subclass 482), temporary_graduate (subclass 485), student (subclass 500), working_holiday (Working Holiday 417 or Work and Holiday 462), bridging, other_temporary, visitor (Visitor visa or ETA) |
  | ae | citizen (UAE national, Emirati), gcc_national, work_visa (Work visa, employment residence), family_visa (Residence visa on family sponsorship), golden_visa, green_visa, student_visa, virtual_work_visa (Virtual work visa: working for a company outside the UAE), other_residence, visit_visa (Visit visa, including the jobseeker visit visa), no_visa (No UAE visa) |

- **`permits.ca`.** The generic wording, with this hint on both sponsorship questions (Sources
  12): "In Canada this means an employer-specific work permit: an LMIA or an LMIA-exempt offer of
  employment."
- **`permits.ae`.** Sources 9:
  - `authorized_now`: "Can you work in the UAE without an employer sponsoring your residence
    visa?"
  - `sponsorship_now`: "Do you need an employer to sponsor your UAE residence visa now?"
  - `sponsorship_future`: "Will you need an employer to sponsor your UAE residence visa later?"
  - plus `*expires_on`.
- **`answers`** (country answers):
  - `expected_pay` (text, optional, no pack, `fills: preferences.desired_salary`, labelled per
    market from `pay` in Task 3.5);
  - `current_ctc` (text, optional, `pack: india_basics`, `fills: preferences.current_ctc`, label
    "Current CTC (₹ per year)", hint "Leave it empty if you'd rather not share it.");
  - `in_country_now` (yes/no, optional, `pack: gulf`, `fills: eligibility.in_country_now`, label
    "Are you in the UAE now?");
  - `uae_driving_licence` (yes/no, optional, `pack: gulf`, `fills:
    eligibility.uae_driving_licence`, label "Do you hold a UAE driving licence?").
- **India's `you` fields** join the groups in Task 3.5, not here: `resolve` ignores pack tags until
  then, so a group field added now would show to everyone.
- **`language_fields`:** `cefr` (select, optional, `pack: cefr`, label "Level (CEFR)"). Its options
  are A1 to C2, labelled "A1 · Basic user" … "C2 · Proficient user" (Sources 23).
- **`citizenship`**, from the sources doc's Proposed data, each rule citing its source URL:

  ```yaml
  citizenship:
    groups:
      eu_eea_ch: [AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT, LV, LT, LU, MT,
                  NL, PL, PT, RO, SK, SI, ES, SE, IS, LI, NO, CH]
      gcc: [BH, KW, OM, QA, SA]
    rules:
      - {citizens: eu_eea_ch, markets: [DE, NL, IE], source: "https://europa.eu/youreurope/citizens/work/work-abroad/work-permits/index_en.htm"}
      - {citizens: [GB], markets: [IE], source: "https://assets.publishing.service.gov.uk/media/5cd29d56ed915d50b5a206d1/CTA-MoU-UK.pdf"}
      - {citizens: [IE], markets: [UK], source: "https://www.legislation.gov.uk/ukpga/1971/77/section/3ZA"}
      - {citizens: gcc, markets: [AE], status: gcc_national, source: "https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/gcc-nationals-working-in-the-private-sector"}
  ```

  Comment that a citizen in their own country is the implicit first rule (status `citizen`), and
  that the sources doc's "never derive" cases (a British citizen in DE or NL, an EU citizen in the
  UK) are left out on purpose.

`byHome` stays a bool here: Task 3.5 makes it name the line, when `_for_home` learns the postcode.

`schemas/form_questions.py`:

```python
class CitizenshipRule(BaseModel):
    model_config = _CATALOG

    citizens: str | list[str]   # a group's name, or ISO codes
    markets: list[str]
    status: str | None = None
    source: str


class Citizenship(BaseModel):
    model_config = _CATALOG

    groups: dict[str, list[str]]
    rules: list[CitizenshipRule]
```

`Catalog` gains `statuses: dict[str, list[Option]]`, `answers: list[Field]`,
`language_fields: list[Field]` and `citizenship: Citizenship`.

**Step 4: Run** `tests/test_form_questions.py tests/test_markets*.py`. Then `git grep -n "keys()"
backend/tests | grep -i market` and the MCP suite, `mcp_server/tests/ -q -n auto --dist loadfile`:
the new market widens `MarketKey`. Regenerate the wire golden with `MAESTRO_WIRE_GOLDEN_WRITE=1`
and read its diff (AE added to market enums, nothing else). Fix any test that counts markets.

Phase 1's permit golden (`test_every_market_gets_todays_permit_fields`) reads
`_TODAY["permits"][vocab]`. CA's `ca` and AE's `ae` wordings are new on purpose, so limit that test
to the markets whose vocabulary the fixture holds (`us_visa`, `uk`, `generic`).

Expected: green, with the groups golden unchanged. `resolve` is unchanged until 3.5, and the tags
and other catalog-only attributes are never served.

**Step 5: Commit** (`feat(form-questions): packs, status lists and the UAE in data`).

### Task 3.3: Storage

**Files:**
- Modify: `backend/app/schemas/autofill_profile.py`, `backend/app/services/autofill_profile.py`
- Modify: `backend/app/services/autofill_catalog.py` (the `WorkAuthStatus` reader)
- Test: `backend/tests/test_settings_agent_patch.py`, `backend/tests/test_autofill_profile*.py`

**Step 1: Failing tests** (in `test_settings_agent_patch.py`'s style):

```python
def test_answers_by_country_merge_per_market(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        "answers_by_country": {"IN": {"current_ctc": "1800000"}, "AE": {"in_country_now": True}}}})
    _patch(client, "autofill", {"answers_by_country": {"IN": {"expected_pay": "2400000"}}})
    stored = _stored_profile(settings_dir)["answers_by_country"]
    assert stored == {"IN": {"current_ctc": "1800000", "expected_pay": "2400000"},
                      "AE": {"in_country_now": True}}


def test_an_unknown_country_answer_is_refused(client):
    r = _patch(client, "autofill", {"answers_by_country": {"DE": {"current_ctc": "1"}}})
    assert r.status_code == 422 and "current_ctc" in r.text


def test_a_status_from_another_country_is_refused(client):
    r = _patch(client, "autofill", {"work_auth_by_country": {"CA": {"status": "h1b"}}})
    assert r.status_code == 422 and "open_work_permit" in r.text  # names CA's choices


def test_citizenships_are_iso_codes(client, settings_dir):
    _patch(client, "autofill", {"personal": {"citizenships": ["in", "United Kingdom", "IN"]}})
    assert _stored_profile(settings_dir)["personal"]["citizenships"] == ["IN", "GB"]
    assert _patch(client, "autofill", {"personal": {"citizenships": ["Atlantis"]}}).status_code == 422


def test_an_old_profile_reads_unchanged(client):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    assert client.get("/api/settings/autofill").json()["value"]["work_auth_by_country"] == \
        PROFILE["work_auth_by_country"]
```

In the typed reader's tests:

```python
def test_a_status_is_read_against_its_market():
    assert autofill_profile.typed_work_auth({"status": "pgwp"}, "CA").status == "pgwp"
    assert autofill_profile.typed_work_auth({"status": "pgwp"}, "US").status is None
    assert autofill_profile.typed_work_auth({"status": "h1b"}, "US").status == "h1b"
```

**Step 2: Run them.** Expected: fail.

**Step 3: Implement.**
- `WorkAuth.status: str | None`. Delete `WorkAuthStatus`, and replace its readers in this task:
  - `autofill_catalog._US_CITIZEN` reads `form_questions.status_values("US")`;
  - `test_autofill_catalog.py`'s parametrize uses the same;
  - `mcp_server/server.py:19,379`: `WorkPermitAnswers.status` becomes `str | None`. `app.main`
    imports the MCP server, so leaving it would fail every client test. Task 3.9 adds its
    description.
- `typed_work_auth(raw, market=None)`: a status outside `form_questions.status_values(market)`
  reads as None, as a near-miss does today.
  - With no market, it checks against every list together (`form_questions.all_status_values()`),
    so "OPT" still reads as None (`test_autofill_profile_schema.py:98-116`).
  - Pass the market at every caller that has one (`git grep -n "typed_work_auth("`).
- `ANSWERS_BY_COUNTRY = "answers_by_country"`:
  - `AGENT_SECTIONS` gains it;
  - `merged_profile` merges it per market with `_merged_answers`, like `BY_COUNTRY`;
  - `_as_stored` keeps the stored markets a PUT does not send, like `work_auth_by_country`.
- `_refusal` gains three checks, each raising `ValueError` with the allowed values so the router's
  422 names them:
  - an `answers_by_country` market that is not supported;
  - a key that is not in `form_questions.answer_keys(market)` (that market's `answers` after packs);
  - a `work_auth_by_country` status that is not in that market's list.
- `personal.citizenships` is normalised on save (`countries.normalize`, upper-case, dedupe, order
  kept); an unknown country is a refusal.
- `form_questions` gains:
  - `status_values(market) -> list[str]`, which is `[]` without a list;
  - `all_status_values() -> set[str]`;
  - `answer_keys(market) -> list[str]`.

**Step 4: Run** the two test files, then `tests/test_autofill*.py tests/test_settings*.py
tests/test_knockout.py`. Expected: green.

**Step 5: Commit** (`feat(autofill-profile): citizenships and per-country answers`).

### Task 3.4: Answers from citizenship

**Files:**
- Create: `backend/app/services/autofill_derive.py`
- Modify: `backend/app/services/form_questions.py` (`citizenship_rule`)
- Test: `backend/tests/test_autofill_derive.py`

**Step 1: Failing tests:**

```python
from app.services import autofill_derive

SETTLED = {"authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}


def _values(derived):
    return {k: d.value for k, d in derived.items()}


def test_a_citizen_in_their_own_country():
    assert _values(autofill_derive.derived_for(["IN"], "IN")) == SETTLED  # IN lists no statuses
    assert _values(autofill_derive.derived_for(["CA"], "CA")) == {**SETTLED, "status": "citizen"}
    assert autofill_derive.derived_for(["GB"], "UK")["authorized_now"].via == "GB"


def test_eu_eea_and_swiss_citizens_in_germany_the_netherlands_and_ireland():
    for code in ("FR", "IE", "IS", "LI", "NO", "CH"):
        for market in ("DE", "NL", "IE"):
            assert _values(autofill_derive.derived_for([code], market)) == SETTLED, (code, market)


def test_british_citizens_in_ireland_only():
    assert autofill_derive.derived_for(["GB"], "IE")["authorized_now"].via == "GB"
    assert autofill_derive.derived_for(["GB"], "DE") == {}
    assert autofill_derive.derived_for(["GB"], "NL") == {}


def test_irish_citizens_in_the_uk_but_not_other_eu_citizens():
    assert _values(autofill_derive.derived_for(["IE"], "UK")) == SETTLED
    assert autofill_derive.derived_for(["FR"], "UK") == {}


def test_gcc_nationals_in_the_uae():
    assert _values(autofill_derive.derived_for(["SA"], "AE")) == {**SETTLED, "status": "gcc_national"}
    assert _values(autofill_derive.derived_for(["AE"], "AE")) == {**SETTLED, "status": "citizen"}


def test_nothing_else_is_derived():
    assert autofill_derive.derived_for([], "DE") == {}
    assert autofill_derive.derived_for(["IN"], "AE") == {}
    assert autofill_derive.derived_for(["US"], "CA") == {}


def test_dual_citizens_take_the_first_rule_that_settles_it():
    assert autofill_derive.derived_for(["IN", "GB"], "IE")["authorized_now"].via == "GB"


def test_an_explicit_answer_wins_and_the_rest_is_derived():
    profile = {"personal": {"citizenships": ["FR"]},
               "work_auth_by_country": {"DE": {"sponsorship_future": True}}}
    assert autofill_derive.answers_for(profile, "DE") == {**SETTLED, "sponsorship_future": True}


def test_derived_answers_are_never_stored(client, settings_dir):
    client.put("/api/settings/market", json={"value": {"home": "DE", "apply_in": ["DE"]}})
    client.put("/api/settings/autofill", json={"value": {"personal": {"citizenships": ["FR"]}}})
    stored = json.loads((settings_dir / "autofill.json").read_text())
    assert "DE" not in (stored.get("work_auth_by_country") or {})
    assert "DE" not in (client.get("/api/settings/autofill").json()["value"].get("work_auth_by_country") or {})
```

**Step 2: Run them.** Expected: `ImportError`.

**Step 3: Implement.** In `form_questions.py`:

```python
def citizenship_rule(code: str, market: str) -> CitizenshipRule | None:
    """The rule under which a citizen of `code` may work in `market` with no permit, or None."""
    if code == markets.country_code(market):
        return CitizenshipRule(citizens=[code], markets=[market], status="citizen", source="own country")
    cit = catalog().citizenship
    for rule in cit.rules:
        members = cit.groups[rule.citizens] if isinstance(rule.citizens, str) else rule.citizens
        if code in members and market in rule.markets:
            return rule
    return None
```

`autofill_derive.py`:

```python
"""Work-permit answers a citizenship settles, computed on read and never stored.

Only the rules the sources check verified (form_questions.yaml `citizenship`; sources doc changes
1-5): a citizen in their own country, EU/EEA/Swiss citizens in DE, NL and IE, British citizens in
Ireland, Irish citizens in the UK, GCC nationals in the UAE. Anything else stays unknown, and an
answer the user gave always wins (inv-country-answers-stay-home).
"""

from typing import Any

from app.schemas.form_questions import DerivedAnswer
from app.services import autofill_profile, countries, form_questions

_SETTLED = {"authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}


def citizenships(profile: Any) -> list[str]:
    personal = profile.get("personal") if isinstance(profile, dict) else None
    raw = personal.get("citizenships") if isinstance(personal, dict) else None
    if not isinstance(raw, list):
        return []
    return [code for code in (countries.normalize(c) for c in raw) if code]


def derived_for(citizenships: list[str], market: str) -> dict[str, DerivedAnswer]:
    for code in citizenships:
        rule = form_questions.citizenship_rule(code, market)
        if rule is None:
            continue
        values: dict[str, Any] = dict(_SETTLED)
        if rule.status and rule.status in form_questions.status_values(market):
            values["status"] = rule.status
        return {key: DerivedAnswer(value=value, via=code) for key, value in values.items()}
    return {}


def answers_for(profile: Any, market: str, home: str | None = None) -> dict[str, Any]:
    """One market's permit answers as readers see them: the stored ones over the derived ones."""
    stored = autofill_profile.work_auth_entries(profile, home).get(market, {})
    derived = {k: d.value for k, d in derived_for(citizenships(profile), market).items()}
    return {**derived, **{k: v for k, v in stored.items() if v is not None}}
```

`DerivedAnswer` joins `schemas/form_questions.py` (Shared shapes). Only readers call `answers_for`;
the save path (`_as_stored`, `work_auth_entries`) never does.

**Step 4: Run** `tests/test_autofill_derive.py`. Expected: green.

**Step 5: Commit** (`feat(autofill): permit answers from citizenship`).

### Task 3.5: The resolved set, with packs

**Files:**
- Modify: `backend/app/schemas/form_questions.py`, `backend/app/services/form_questions.py`
- Modify: `backend/app/routers/settings.py`, `backend/tests/test_served_questions_fixtures.py`
- Test: `backend/tests/test_form_questions.py`, `backend/tests/test_form_questions_route.py`

**Step 1: Failing tests.** Replace the Phase 1 golden for every market with three checks:
- the chosen US set is today's, field by field;
- the other markets equal today's set apart from the changes this phase makes on purpose;
- the new cases below.

```python
def _keys(fields):
    return [f.key for f in fields]


def test_a_chosen_us_user_sees_todays_set():
    # Labels, options and counted keys as the Phase 1 fixture; only the new attributes may differ
    # (byHome's value, the expiry's `unless`).
    qs = form_questions.resolve(home="US", apply_in=["US"])
    assert [_keys(g.fields) for g in qs.groups] == [[f["key"] for f in g["fields"]] for g in _TODAY["groups"]]
    us = qs.countries[0]
    assert _keys(us.permits) == [f["key"] for f in _TODAY["permits"]["us_visa"]]
    assert [o.value for o in us.permits[0].options] == [o["value"] for o in _TODAY["permits"]["us_visa"][0]["options"]]


def test_each_question_once_for_india_uae_germany_and_the_netherlands():
    qs = form_questions.resolve(home="IN", apply_in=["IN", "AE", "DE", "NL"], citizenships=["IN"])
    you = [f.key for g in qs.groups for f in g.fields]
    assert len(you) == len(set(you))
    assert {"notice_days", "experience_years", "preferred_locations"} <= set(you)
    assert not {"over_18", "non_compete"} & set(you)
    by = {c.market: c for c in qs.countries}
    assert [c.market for c in qs.countries] == ["IN", "AE", "DE", "NL"]
    assert _keys(by["IN"].answers) == ["expected_pay", "current_ctc"]
    assert _keys(by["AE"].answers) == ["expected_pay", "in_country_now", "uae_driving_licence"]
    assert _keys(by["DE"].answers) == ["expected_pay"]
    assert by["AE"].permits[0].key == "status" and by["DE"].permits[0].key == "authorized_now"
    assert by["NL"].answers[0].label.startswith("Expected gross monthly salary")
    assert _keys(qs.language_fields) == ["cefr"]
    assert set(by["IN"].derived) == {"authorized_now", "sponsorship_now", "sponsorship_future"}
    assert by["DE"].derived == {}


def test_eu_citizens_see_germany_and_the_netherlands_settled():
    qs = form_questions.resolve(home="IN", apply_in=["DE", "NL"], citizenships=["FR"])
    assert all(c.derived["authorized_now"].via == "FR" for c in qs.countries)


def test_the_expiry_hides_for_statuses_that_never_expire():
    ae = form_questions.resolve(home="AE", apply_in=["AE"]).countries[0]
    expiry = next(f for f in ae.permits if f.key == "authorization_expires_on")
    assert expiry.unless == ("status", ["citizen", "gcc_national", "no_visa"])


def test_a_uae_home_counts_no_postcode_and_calls_the_state_line_emirate():
    personal = form_questions.resolve(home="AE", apply_in=["AE"]).groups[0]
    by_key = {f.key: f for f in personal.fields}
    assert by_key["postal_code"].optional is True
    assert by_key["state"].label == "Emirate" and by_key["state"].optional is False


def test_unchosen_asks_no_country_and_no_us_screening():
    qs = form_questions.resolve(home="US", apply_in=[], chosen=False)
    assert qs.countries == [] and qs.language_fields == []
    assert not {f.key for g in qs.groups for f in g.fields} & {"over_18", "non_compete"}
```

In the route test: `GET /api/settings/autofill/questions` passes the profile's citizenships, and
serves `countries` and `chosen`.

**Step 2: Run them.** Expected: fail.

**Step 3: Implement.** First add India's `you` fields to `form_questions.yaml`, tagged
`pack: india_basics` (Sources 20–22):
- in `preferences`, after `notice_period`:
  - `notice_days` (number, optional, "Notice period in days", hint "Forms that offer fixed choices
    get the next one up.");
  - `serving_notice` (yes/no, optional, "Are you serving your notice period?");
  - `last_working_day` (date, optional, "Last working day", hint "If you're serving notice."). It
    has no `when`: yes/no answers are stored as `true`, and `when` compares the raw value;
- at the end of `preferences`: `preferred_locations` (text, optional, "Preferred work locations",
  hint "Up to 10 cities, separated by commas.");
- at the end of `eligibility`: `experience_years` and `experience_months` (number, optional, "Total
  experience: years" / "Total experience: months").

Then `resolve(*, home, apply_in, chosen=True, citizenships=())`:
- `packs = {p for m in apply_in for p in markets.get(m)["packs"]}` when chosen, else `set()`.
- **Groups:** keep a field when `field.pack is None or field.pack in packs`, then apply `_for_home`.
  - `byHome` becomes `Literal["state", "postcode"] | None` (YAML: state `byHome: state`, postal
    code `byHome: postcode`).
  - `state` keeps today's rule.
  - `postcode` is optional where `asks_postcode` is false, and keeps its label.
  - With `chosen` false, the state line is optional and keeps its label.
- **US permits:** delete `permits.us_visa`'s status field; the per-market status field below
  replaces it.
- **Each market's permits:**
  - the status field first, if `work_status` names a list: key `status`, label "Work authorization
    status" (US) or "Immigration status" (others), options from the list. It is required for the
    US only, as today. For CA, AU and AE it is `optional: true`, so no existing CA or AU user's count
    drops (Decision 6), and the Companion asks it when a form does;
  - then the market's `permits[vocab]`, minus any `status` field it still carries;
  - the expiry gets `unless = ("status", [values with noExpiry])` when the market has a list.
- **Answers:** `catalog().answers` filtered by pack; `expected_pay` relabelled from `pay.label` and
  hinted from `pay.hint`.
- **Derived:** `autofill_derive.derived_for(list(citizenships), market)`.
- **Language fields:** `catalog().language_fields` filtered by pack.
- **Serving:** `QuestionSet` keeps `permits` (each market's permit list, as Phase 1 served it) until
  Task 3.10.
- **The route** passes `chosen=market.chosen` and
  `citizenships=autofill_derive.citizenships(autofill_profile.get_profile())`.

Add scenarios to `test_served_questions_fixtures.py`, then regenerate with
`MAESTRO_SERVED_QUESTIONS_WRITE=1` and read the diff:
- `lives-IN_applies-IN-AE-DE-NL` with citizenship IN;
- `lives-AE_applies-AE`;
- unchosen as `lives-none`.

`SCENARIOS`, `served()` and `fixture_name` take only home and apply-in today. Extend them, and the
render harness's `servedQuestions`, with optional citizenships and `chosen`.

**Step 4: Run** `tests/test_form_questions*.py tests/test_served_questions_fixtures.py
tests/test_setup_status*.py tests/test_frontend_every_item_has_a_home.py`. That last file pins
through `catalog()` and breaks here:
- its `byHome=True` check (:136) becomes `byHome == "state"`;
- its `asked("us_visa", "status")` (:146) reads the status from `statuses.us`.

Update both, keeping what they assert. Expected: green. Readiness does not use `countries` until
3.6.

**Step 5: Commit** (`feat(form-questions): resolve packs, country answers and citizenship`).

### Task 3.6: Readiness counts knockout questions only

**Files:**
- Modify: `backend/app/services/setup_status.py`
- Test: `backend/tests/test_setup_status*.py` (the readiness file Phase 1 used)

**Step 1: Failing tests:**
- `citizenships` counts once in `personal`: missing, then answered.
- An FR citizen applying in DE has DE's `work_auth_by_country` count at 3 of 3 with nothing stored.
- An IN user with no `current_ctc`, `expected_pay` or `notice_days` gets the same readiness as with
  them: optional never counts.
- An unchosen market has `work_auth` 0 of 0 and no `blocking`.
- An AE home with no postal code has `personal` complete.
- A chosen US user's readiness is unchanged apart from citizenship. Assert this on the existing
  chosen-US readiness cases by giving each `citizenships: ["IN"]`. That answers the question but
  settles nothing in the US; `["US"]` would derive US permit answers and change the counts under
  test.

**Step 2: Run them.** Expected: fail on citizenship and derived.

**Step 3: Implement.**
- `personal.citizenships` is required in the `personal` group, as a field with `type: countries`
  that is not optional. Add it to the YAML after `country`, labelled "Citizen of", and add it to
  3.5's chosen-US golden test (the one intended difference).
  - Contact does not show it: Task 3.10 edits it in Country answers.
- `_work_permits(profile, questions)` iterates `questions.countries` and reads each market's answers
  through `autofill_derive.answers_for(profile, market)`, typed with
  `typed_work_auth(..., market)`. Its keys are `required_keys(country.permits)`.
- `_answered([])` returns True today (`setup_status.py:43-48`). Make a list answered only when it
  is non-empty; no counted field is a list today, so nothing else moves. The frontend's
  `answered()` treats any non-string as blank, so Task 3.10 teaches it the `countries` type.
- Regenerate the served fixtures (`MAESTRO_SERVED_QUESTIONS_WRITE=1`): `personal` gains the field.

**Step 4: Run** the readiness tests, `tests/test_setup*.py`,
`tests/test_served_questions_fixtures.py` and `tests/test_form_questions.py`. Expected: green.

**Step 5: Commit** (`feat(setup): readiness counts each country's knockout answers`).

### Task 3.7: The fill reads one country

**Files:**
- Modify: `backend/app/services/autofill_country.py`, `backend/app/services/autofill_job.py`
- Modify: `backend/app/routers/autofill.py` (`_Catalog`), `backend/app/services/filled_answers.py`
- Modify: `backend/app/services/knockout.py`
- Modify: `backend/app/services/autofill_catalog.py`, `backend/app/services/autofill_slots.py`
- Test: `backend/tests/test_autofill_country.py`, `backend/tests/test_autofill_catalog.py`

**Step 1: Failing tests:**

```python
def test_a_uae_job_reads_uae_answers_and_none_of_germanys():
    profile = {"preferences": {"desired_salary": "90000"},
               "answers_by_country": {"AE": {"expected_pay": "25000", "in_country_now": True},
                                      "DE": {"expected_pay": "70000"}}}
    folded = autofill_country.with_country_answers(profile, "AE")
    assert folded["preferences"]["desired_salary"] == "25000"
    assert folded["eligibility"]["in_country_now"] is True
    assert "answers_by_country" not in folded
    assert "70000" not in json.dumps(folded)


def test_without_a_country_answer_the_generic_one_stays():
    profile = {"preferences": {"desired_salary": "90000"}, "answers_by_country": {"DE": {}}}
    assert autofill_country.with_country_answers(profile, "DE")["preferences"]["desired_salary"] == "90000"


def test_a_citizenship_answers_the_permit_questions_on_the_job():
    profile = {"personal": {"citizenships": ["FR"]}}
    folded = autofill_country.with_work_auth(profile, "NL")
    assert folded["work_auth"]["authorized_now"] is True


def test_catalog_facts_for_india_pack_answers():
    facts = autofill_catalog.build({"preferences": {"notice_days": 45}, ...})  # existing build helper
    notice = next(f for f in facts if f.slot == "preferences.notice_days")
    assert "never a shorter" in notice.describe
```

Also write these tests:
- A question naming Germany on an AE job gets DE's country answers. Follow the existing
  `market_for_question` tests in `test_autofill_country.py`, through `profile_for_job(...,
  question=...)`.
- `personal.citizenships` and `work_auth.status` are `exact` (`policy_for`).
- `last_working_day` is a fact only while `serving_notice` is Yes and the date is today or later.
  A past date also drops the `serving_notice` fact.
- The knockout scan treats an FR citizen's DE job as authorized, not `profile_missing`.
- `countries_authorized` lists the markets a citizenship settles.
- On an NL job, the desired-salary fact's describe names "gross monthly … excluding holiday
  allowance".
- The knockout salary check still reads the generic `desired_salary`, never a folded monthly figure.
- A stored CEFR level becomes a `languages` fact.

**Step 2: Run them.** Expected: fail.

**Step 3: Implement.**
- **`with_country_answers(profile, market)`.**
  - Copy the profile without `answers_by_country`.
  - For each key in `answers_by_country[market]` whose value is set, write it to its field's
    `fills` slot (`section.key`); a set value overrides that slot.
  - Keys not in the market's current `answer_keys` are skipped.
- **`entry(profile, market, home)`** reads `autofill_derive.answers_for`, so `with_work_auth`,
  `work_auth_for` and `countries_authorized` see derived answers.
- **Call sites.** Call `with_country_answers` beside every `with_work_auth`:
  - `autofill_job.profile_for_job`;
  - `routers/autofill.py` `_Catalog._keyed`, whose cache key adds `json.dumps(answers)` for that
    market;
  - `filled_answers.flag_context`.
- **The knockout scan.** `knockout._work_auth_for_job` has no profile: it reads the `by_market`
  dict that `scan_args` (`knockout.py:443-460`) builds from stored entries.
  - Build that dict with `autofill_derive.answers_for` over the stored markets plus the apply-in
    ones, so a citizenship-settled market is seen.
  - Pay stays out of the knockout: `_salary_check` assumes a yearly figure (`knockout.py:181-186`),
    so it keeps reading the generic `desired_salary`, never a folded country answer.
- **`_authorized_countries`** (`autofill_country.py:84-92`) walks `answers_for` for the stored
  markets plus the derived ones, so a settled country is listed.
- **Redaction.** `_redaction_facts` treats `answers_by_country` like `work_auth_by_country`: per
  market, suffixed `#market`.
- **Describe and policy.**
  - `autofill_catalog.describe_of(slot)` and `autofill_slots.policy_for(slot)` consult the catalog
    first. Add `form_questions.describe_for(slot)` and `policy_for(slot)`, keyed by `section.key`,
    or by `fills` for country answers.
  - Give these describes in the YAML:
    - `notice_days`: "notice period in days; when a form offers fixed choices, pick the shortest
      one that is at least this long, never a shorter one";
    - `current_ctc`: "current CTC: total annual cost to company, in rupees";
    - `experience_years` and `experience_months`: "total work experience: years / months";
    - `preferred_locations`: "preferred work locations (cities)";
    - `in_country_now` and `uae_driving_licence`;
    - `cefr`: "CEFR level (A1–C2) of this language; on a verbal scale pick the nearest option".
  - `personal.city`'s describe gains "(also the current location)".
- **Desired salary.** On a market with pay terms, the desired-salary fact's describe is that
  market's `pay.label` plus "(expected pay)", so a Dutch monthly or UAE monthly figure is filled as
  one.
- **Status words.** `_WORDS["work_auth.status"]` reads the job market's status labels from the
  catalog. `_US_CITIZEN` stays US-only.
- **`_profile_sections`** keeps `preferences.last_working_day` only while `serving_notice` is true
  and the date is not past, and drops `serving_notice` with a past date.
- **CEFR.** `_languages` emits only `_LANGUAGE_FACTS` keys and maps levels through `_LEVELS`
  (`autofill_catalog.py:357-383`), so a describe alone never fills a CEFR level. Add `cefr` to the
  language facts, passed through as its code (A1–C2), so a stored level reaches the form.

**Step 4: Run** `tests/test_autofill*.py tests/test_knockout.py tests/test_filled_answers*.py`.
Expected: green.

**Step 5: Commit** (`feat(autofill): a job's fill reads its own country's answers`).

### Task 3.8: The Companion learns a country answer

**Files:**
- Modify: `extension/shared/profile-fields.js`, `extension/panel/actions/pause.js`
- Test: `backend/tests/test_extension_panel_fill.py` (the pause and learn tests near :1896)

**Step 1: Failing tests:**
- A paused salary question on a job with a market learns to that market's
  `answers_by_country[market].expected_pay`, not `preferences.desired_salary`.
  - For example, "Expected CTC" on an Indian job learns to `answers_by_country.IN.expected_pay`.
  - Today a salary learned in rupees on an Indian job would fill a US form.
  - With no market, it learns to `desired_salary` as today.
- "Are you currently in the UAE?" on an AE job learns to `answers_by_country.AE.in_country_now`.
- Use the existing `run_node` harness and the `learnAnswer` tests as the pattern.
- Undo restores the entry before the answer.

**Step 2: Run them.** Expected: they land in `custom`.

**Step 3: Implement.**
- `PROFILE_FIELDS` gains rows with path `["answers_by_country", key]`:
  - current CTC;
  - in the UAE now;
  - UAE driving licence.

  Put each row after the generic rows it must not shadow.
- The salary row (`ns.salaryExpectationRe`) learns to `["answers_by_country", "expected_pay"]` when
  `workAuthPlaceFor` gives a market, and to `preferences.desired_salary` otherwise. The fill-side
  row is unchanged: the backend folds the country's answer over `desired_salary` (Task 3.7).
- `learnAnswer` and `learnAnswers` fetch the place only for work-permit targets today
  (`pause.js:325, 349`). Fetch it for every country-scoped target and for the salary row.
- With no market:
  - a country answer stays unsaved, as a permit does;
  - the salary row falls back to `desired_salary`.
- `isWorkPermit` becomes `isCountryScoped(path)`, true for `work_auth` and `answers_by_country`, so
  `applyAnswer` rewrites both to `[section, market, ...rest]` with the market from
  `workAuthPlaceFor`. With no market, the answer stays unsaved, as permits do today.

**Step 4: Run** `tests/test_extension_*.py`, then
`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check extension` (SYSTEM.md).
Expected: green.

**Step 5: Commit** (`feat(companion): learn a country answer into its country`).

### Task 3.9: Agents

**Files:**
- Modify: `backend/mcp_server/server.py`, `backend/mcp_server/client.py`
- Modify: `backend/app/services/job_search_brief.py`
- Test: `backend/mcp_server/tests/test_profile_write_tools.py`,
  `mcp_server/tests/test_autofill_profile_tool.py`, `backend/tests/test_job_search_brief.py`

**Step 1: Failing tests:**
- `set_autofill_profile` takes `answers_by_country`: the property set gains it.
- The TypedDicts use `extra="forbid"`, so every new key must be named or an agent's write is
  refused:
  - `PersonalAnswers` takes `citizenships` (a list of strings);
  - `PreferenceAnswers` takes `notice_days`, `serving_notice`, `last_working_day` and
    `preferred_locations`;
  - `EligibilityAnswers` takes `experience_years` and `experience_months`;
  - `LanguageEntry` takes `cefr` (A1–C2).

  Test one write per new key.
- `WorkPermitAnswers.status` is a string whose description names where the lists live.
- A `{"CA": {"status": "h1b"}}` write comes back as the 422's message.
- `get_autofill_profile` returns `questions`: per market, its permit keys with their choices, its
  answer keys, and its derived answers.
- The brief's `work_auth_by_country` shows a derived answer for an FR citizen applying in DE, plus
  each market's `expected_pay` when set.
- Tool count still 94.

**Step 2: Run them.** Expected: fail.

**Step 3: Implement.**
- The TypedDicts gain the fields.
- The client gate imports `AGENT_SECTIONS`, so it gains the section on its own.
- `get_autofill_profile`'s docstring is at 1990 of 2000 characters, so new facts go in a param's
  `Field(description=...)` or by tightening wording (docs/agent-surfaces.md).
- EEO stays out, as today.
- The brief reads `answers_for` per market.
- Regenerate the wire golden and read its diff.

**Step 4: Run** `mcp_server/tests/ tests/test_job_search_brief.py -q -n auto --dist loadfile`.
Expected: green.

**Step 5: Commit** (`feat(mcp): citizenships and per-country answers for agents`).

### Task 3.10: Profile

**Files:**
- Modify: `frontend/lib/types.ts`, `frontend/lib/autofill-options.ts`
- Modify: `frontend/components/profile/work-permits.tsx`, `eligibility.tsx`, `languages.tsx`
- Modify: `frontend/components/profile/field-control.tsx`, `profile-view.tsx`, `next-up.tsx`
- Modify: `frontend/lib/profile-tiles.ts`
- Modify: every backend string pin and message the rename touches
- Test: `frontend/lib/autofill-options.test.ts`, `components/profile/profile-view.test.mjs`

**Step 1: Failing tests** (node):
- `permitMarkets` reads `countries` in order.
- `permitAnswered` counts a derived answer as answered.
- `withCountryAnswer(profile, market, key, value)` writes `answers_by_country[market][key]` and
  leaves other markets alone.
- `withPermit` honours `when` and `unless` as `withField` does: setting `status: citizen` clears a
  stored expiry.
- `withCitizenships(profile, codes)`.
- The profile view, seeded with `servedQuestions("IN", ["IN", "AE", "DE", "NL"])`:
  - shows the tile "Country answers";
  - shows "Citizen of" at the top and one row per country;
  - shows "From your citizenship (India)" on IN's three answers;
  - shows the fold "Screening questions";
  - shows the CEFR level on each language.

**Step 2: Run them.** `node --test lib/*.test.ts` and `node --test "components/**/*.test.mjs"`.
Expected: fail.

**Step 3: Implement.**
- **Types.** `QuestionSet`, `CountryQuestions`, `DerivedAnswer` and the new `FieldDef` attributes
  (number, countries, `byHome` as a string, `unless`). `permits` is removed; cut `MarketOption`'s
  `work_auth_vocab`, `asks_state` and `state_label` if nothing reads them (`git grep`).
- **Country answers** (`work-permits.tsx`; the file name and the tile id `permits` stay, to spare
  pins):
  - the title "Country answers";
  - "Citizen of" with `CountryPicker`, where GB reads "United Kingdom (British citizen)";
  - then per country a fieldset of its permits, then its answers.
  - A derived permit shows its value as text with "From your citizenship (<country>)" and an
    **Answer differently** button, which reveals the control. A saved answer then wins.
  - Saving citizenships invalidates `["settings", "form-questions"]` and awaits the refetch, as the
    market autosave does.
  - With no country chosen, the tile shows "Citizen of" and a link to Where you apply instead of
    country rows.
- **Contact.** Contact's `FieldGrid` skips the `countries`-type field. In `missingAnswers` a
  missing `citizenships` becomes `{kind: "citizenship"}` and links to Country answers, not Contact.
- **Screening questions.** `eligibility.tsx` gets the title and summary "Screening questions",
  "Past employers, and what your countries' forms ask".
- **Languages.** `useLanguagesTile(questionSet)` appends `questionSet.language_fields` to
  `LANGUAGE_FIELDS`. `languageWords` shows the CEFR level when set.
- **FieldControl.** Render `type: "number"` as a numeric input; `countries` is only used by the
  Country answers editor.
- **The rename.** `git grep -n "Work permits"` across `frontend/` and `backend/app`, including
  "Profile › Work permits" in the knockout, brief and panel messages. Rename to "Country answers",
  and "Eligibility" (as a fold title) to "Screening questions". Then update each backend pin to the
  new code, keeping what it asserts:
  - `test_frontend_profile_tiles.py`;
  - `test_frontend_every_item_has_a_home.py`, including its `_PROFILE_COUNTS`;
  - `test_frontend_settings_cards.py`;
  - `test_frontend_setup_flow.py`;
  - `test_knockout.py`;
  - `test_job_search_brief.py`;
  - `test_extension_panel_fill.py`;
  - `test_settings_paths_in_words.py`.
- **`answered()`** in `autofill-options.ts` counts a non-empty array for `type: "countries"`.
- **Serving.** Cut `permits` from the served `QuestionSet` and regenerate the served fixtures. Then
  repoint the backend tests that read it to `countries`:
  - `test_market_chosen.py`;
  - `test_form_questions.py:145-162`;
  - `test_form_questions_route.py:23-24`.

**Step 4: Run** the node suites, `npx tsc --noEmit`, `npm run lint`, and the backend
`tests/test_frontend_*.py tests/test_served_questions_fixtures.py tests/test_form_questions*.py
tests/test_market_chosen.py`. Expected: green.

**Step 5: Commit** (`feat(profile): Country answers and Screening questions`).

### Task 3.11: Setup

**Files:**
- Modify: `frontend/lib/setup-flow.ts`, `frontend/lib/setup-answers.ts`
- Modify: `frontend/components/setup/setup-answers-step.tsx`, `setup-done.tsx`
- Test: `frontend/components/setup/setup-flow.test.mjs`, `backend/tests/test_frontend_setup_flow.py`

**Step 1: Failing tests:**
- `formQuestions(questionSet, markets)` is `[citizenship, permit per country, notice, relocate,
  diversity?]`.
- A country whose required permit questions are all derived is answered, so the flow passes it.
- `PermitQuestion` asks only the required permit questions that are neither derived nor answered.
- Optional country answers are never asked.

**Step 2: Run them.** Expected: fail.

**Step 3: Implement.**
- A `{kind: "citizenship"}` question with `CountryPicker`, saved with `withCitizenships`. After it
  saves, the questions refetch, and `questionAnswered` reads the new `derived`.
- `formQuestions` takes the served set (`questionSet.countries`), not `permitMarkets`.
- Update the setup pins named in the Profile and Setup map: `test_frontend_setup_flow.py:157-171`
  and `test_frontend_every_item_has_a_home.py:265-270`.

**Step 4: Run** the node suites and the backend setup pins. Expected: green.

**Step 5: Commit** (`feat(setup): citizenship first, then what it leaves`).

### Task 3.12: Docs

**Files:**
- Modify: `SYSTEM.md`, `.system_md_enforcement.json`, `docs/entities/others.md`
- Modify: `docs/agent-surfaces.md`, `docs/deferred.md`, `CHANGELOG.md`

**Steps:**
- **SYSTEM.md §6:** add `{#inv-country-answers-stay-home}` beside inv-work-permit-per-country. A
  country's answers, typed or derived, reach only that country's jobs; citizenship-derived answers
  are computed on read and never stored. Pin it in `.system_md_enforcement.json` to
  `tests/test_autofill_country.py::test_a_uae_job_reads_uae_answers_and_none_of_germanys` and
  `tests/test_autofill_derive.py::test_derived_answers_are_never_stored`.
- **SYSTEM.md §2:** the catalog line names packs, statuses and citizenship rules.
- **SYSTEM.md §10:** one decision line: data, packs as field tags, unchosen asks no permits.
- **`others.md`:** the storage (`personal.citizenships`, `answers_by_country`), the chosen mark,
  and readiness's knockout-only count.
- **`agent-surfaces.md`:** the two tools' new fields.
- **`deferred.md` item 53:** note that per-country diversity is Phase 4 of this plan.
- **CHANGELOG Unreleased:** the user-facing change, in the owner's voice
  (ajey-writing-voice).
- **The Companion.** Its learning change ships at the next store release.
- Run `scripts/check_system_md.py` (SYSTEM.md's gate). Expected: OK, under the byte cap.
- **Commit** (`docs: form questions by country`).

### Task 3.13: Gates and a look

- The full backend suite, both paths, with xdist.
- The frontend lib and component suites, `tsc`, `lint` and `build`.
- The extension tests and the slop scan.
- A browser check on a fresh stack on spare ports, never the Docker stack. Use the
  `frontend-country-questions` launch config, at 1280 and 1024 only, for:
  1. no country chosen: no permit questions, and no US screening;
  2. US only: today's Profile, plus "Citizen of";
  3. IN + AE + DE + NL with an Indian citizenship:
     - India settled from citizenship;
     - the UAE status list and the Emirate line;
     - Dutch monthly pay wording;
     - CEFR on languages;
     - Setup asks citizenship, then UAE, Germany and the Netherlands only.
- Then a whole-branch review (superpowers:requesting-code-review) before
  finishing-a-development-branch.

# Phase 4 — Out of this plan

Per-country diversity questions (UK first, then Canada and Australia once verified): its own
design and plan, because it touches inv-eeo-standing-consent. Note from Phase 1 review: the
diversity fold gates on the served `offers_eeo` but names its countries from the market list
(`diversityCountries`); the served set should list them itself.
