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
- Delete: `backend/tests/test_autofill_groups_parity.py`, `frontend/scripts/dump-form-questions.ts`
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

---

# Phase 3 — Packs and countries (outline; expanded after Task 2.2)

Each task names its files, the interface other tasks read, and the tests that define done.

### 3.1 "You chose this" and the generic set
- `schemas/market_settings.py`, `services/market_settings.py`: a stored `chosen` mark. Existing
  installs read as chosen (no change for anyone today); a new install starts unchosen until Setup's
  Where step or Profile's Where you apply saves. Find whether `get_market` seeds a row on read
  before deciding how "existing install" is detected; log the rule chosen.
- `form_questions.resolve`: unchosen → the generic set (no US screening, generic permit wording).
- Tests: unchosen gives no `us_screening` fields; chosen US gives today's set.

### 3.2 Packs and the UAE in data
- `form_questions.yaml` gains `packs` (core, us_screening, visa_status, eu_movement, cefr,
  pay_terms, india_basics, gulf); each question gets `scope` (you / country), `counts`
  (knockout / optional), `policy` (exact / flag / any), `describe`, `tile`.
- `markets.yaml` gains per-market `packs`, `work_status`, `pay`; a new `AE` market (AED, DMY,
  `eeo_module: null`, `asks_state` per Task 2.1.5) with a source comment for each fact.
- `countries.py` / `markets.py`: `AE` resolves both ways (ISO `AE`).
- Loader tests: every named pack exists; a key shared by two packs is the same question.

### 3.3 Storage
- `autofill_profile.py`: `personal.citizenships` (ISO codes) and `answers_by_country`
  (`{market: {key: value}}`), merged by market like `work_auth_by_country`; `AGENT_SECTIONS` gains
  it; `merged_profile` and `_as_stored` handle it.
- `schemas/autofill_profile.py`: `WorkAuth.status` becomes `str | None`, checked against the
  market's `work_status` at write; the US values are unchanged.
- Tests: an old profile reads unchanged; a save of one market leaves another's answers alone.

### 3.4 Answers from citizenship
- New `services/autofill_derive.py`: `derived_permits(citizenships, market) -> dict[str, bool]`
  for the verified rules only. Never stored; an explicit answer wins.
- Tests: each rule; explicit wins; nothing written to storage.

### 3.5 The resolved set, with packs
- `resolve` returns `you` questions once (deduped by key) with their tile, a per-market list
  (permit fields first, then that market's `country` questions), and `derived` per market with its
  source ("citizenship"). The served shape gains `countries: {market: {fields, derived}}`; Phase 1's
  `permits` stays served until the frontend moves (then cut, with a §13 row if both live).
- Tests: no country → generic; IN + AE + DE + NL → each question once, EU derived for DE and NL
  when a citizenship is EU.

### 3.6 Readiness: knockout only
- `setup_status`: generic required + each apply-in market's knockout questions; a derived answer
  counts as answered; optional never counts.

### 3.7 The fill reads one country
- `autofill_country.py`: `with_country_answers(profile, market)` folds `answers_by_country[market]`
  and the derived permits into flat sections, beside `with_work_auth`; every `/context`, `/map`,
  `/pick`, `/step` path that calls `with_work_auth` calls it too.
- `autofill_catalog.py` / `autofill_slots.py`: describes and policies for pack questions come from
  the catalog; citizenship and status are `exact`.
- Tests: an AE job's facts hold AE answers and no DE answers; a question naming Germany on an AE
  job gets DE's.

### 3.8 Learning a paused answer
- `routers/autofill.py` + `services/autofill_context.py`: `/context?question=` adds
  `learn_to: {scope, market, key} | null`, matched against the catalog.
- `extension/panel/actions/pause.js`: write to `learn_to`'s place when present, else today's path;
  extension tests; version bump per `docs/RELEASING.md`.

### 3.9 Agents
- `mcp_server/` profile tools and `services/job_search_brief.py`: citizenships,
  `answers_by_country`, the resolved set; writes checked against the catalog. Docstring ratchets
  per `docs/agent-surfaces.md`. EEO untouched.

### 3.10 Profile
- `work-permits.tsx` → Country answers (citizenship at top, a row per apply-in country, derived
  answers marked "From your citizenship" with Answer differently); `lib/profile-tiles.ts` title.
- `eligibility.tsx` → Screening questions; `start-and-pay.tsx` and `languages.tsx` show pack
  questions by `tile`.
- Copy follows `docs/frontend-conventions.md`; checked at 1280 and 1024 only.

### 3.11 Setup
- `setup-answers-step.tsx` / `lib/setup-answers.ts`: citizenship first, then each country's
  knockout questions not settled by citizenship, then the generic required set.

### 3.12 Docs
- SYSTEM.md §6: a new invariant beside inv-work-permit-per-country (a country's answers never
  reach another country's form), pinned in `.system_md_enforcement.json`; §4 / `others.md`
  storage; `agent-surfaces.md`; `docs/deferred.md` item 53 note; changelog Unreleased.

### 3.13 Gates
- Full backend suite (xdist, both paths), frontend gates, extension tests, a browser check of
  Profile and Setup for: no country; US only; IN + AE + DE + NL with an Indian citizenship.

# Phase 4 — Out of this plan

Per-country diversity questions (UK first, then Canada and Australia once verified): its own
design and plan, because it touches inv-eeo-standing-consent.
