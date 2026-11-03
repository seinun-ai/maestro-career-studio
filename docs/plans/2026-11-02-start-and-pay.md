# Start and pay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task
> (owner's standing choice: Opus implements and reviews each task, spec review then quality review).

**Goal:** Each country's pay lives in its Country answers set and never reaches another country's form; notice is one
answer in days; a question only some countries ask says which.

**Architecture:** Design `docs/plans/2026-11-02-start-and-pay-design.md` (approved 2026-11-02). Home pay stays
`preferences.desired_salary`, shown in the home country's set; every other country keeps
`answers_by_country[market].expected_pay`. The server normalises every save in `autofill_profile._as_stored`, so the web
app, the Companion and MCP need no shape change. The served question set carries the new facts (`home`, `askedBy`,
`legacy`), and the frontend renders what it is served.

**Tech Stack:** FastAPI + Pydantic (backend/app), YAML catalog (`services/data`), Next.js + React (frontend), node:test
and pytest.

## Goal Card

Goal: The owner's Start and pay tile asked pay twice and let "$80,000" reach Indian and Irish forms; notice was asked in
words and again in days; India-only questions didn't say so. Fix all three so each country's forms get that country's
answers and the screen says who asks what.
Principles:
- Never guess an answer: a country with no pay of its own gets none (owner decision 1).
- One place per fact: home pay is `desired_salary`, notice is `notice_days`; anything that arrives in the other shape is
  folded on save.
- Old clients keep working: the Companion and agents may still send `answers_by_country[home].expected_pay` or
  `notice_period` text.
Non-goals: per-country notice, a pay currency picker, moving `earliest_start_date`, a Companion release.
Autonomy: peer (Opus implementers): adapt how within a task's scope, log each deviation in the commit body; anything
touching another task's interface comes back as a deviation note.

## Decisions taken while expanding

1. **Notice converts on read, not by a startup step.** The design proposed a one-time startup step. A read view that
   computes `notice_days` from parseable `notice_period` text (as the legacy `work_auth` is placed on read) needs no
   flag, no sync caveat, and lands in storage on the next save of any kind. Unparseable text stays as the legacy answer.
2. **Home not applied in.** Someone who lives in the US and applies only in India has no home set in Country answers.
   Their `desired_salary` stays in Start and pay, optional, hinted "For jobs whose country Maestro can't tell." (the one
   place it is still read: a job with no country). Unchosen: it stays there, required, as today.
3. **First choice of countries pins nothing.** An unchosen install's `desired_salary` is "the one figure" in whatever
   currency the user meant. On a move of home, the old home's figure is pinned to the old country only when the stored
   market was `chosen`; a first choice adopts it as the new home's pay.
4. **`home` is passed to the fill, never inferred.** The read view names the home (`work_auth_market`) only when it
   holds permit answers. `autofill_country.for_market` and `autofill_job.view_for` take a required keyword `home`, and
   their four callers read it from the market setting they already have a session for.
5. **The served marker is a sentence.** `askedBy: "Asked by forms in Germany and the Netherlands."` is composed on the
   server from `markets.yaml` (a new `in_text` for the four names that take "the"), so the frontend needs no article
   rules and agents read the same words.
6. **`legacy` is a served field attribute** ("an older key whose text still answers this field until it is given"),
   read by readiness on both sides through one helper each. Only `notice_days` uses it.

Added after the plan review (2026-11-02):

7. **Unchosen keeps pay everywhere.** With no country chosen the stored home is the default "US", not a choice. Every
   caller passes `home` as the stored home when `chosen`, else `None`, and `home=None` keeps `desired_salary` for every
   market, in the fill and the salary check alike ("No country chosen: the one figure, as today").
8. **Readiness counts home pay in `preferences`, as today.** It is `preferences.desired_salary`. Setup's answers step
   (`frontend/lib/setup-flow.ts` `stepsDone`) needs the `work_auth` group complete and Setup never asks pay, so counting
   it there would make that step unfinishable. Only the Country answers tile's own done mark reads it as that country's.
   The design's "counts under Country answers" is amended to this.
   Amended 2026-11-03 (Task 9 review): the home pay counts on its own (`autofill.home_pay`, beside the groups in
   readiness and `done`), not inside `preferences`, so Profile's ring and its tiles agree: Country answers holds it
   open. Setup's answers step still reads `groups.work_auth` and never asks it.
9. **`notice_days` is coerced to an int.** Profile's, Next up's and Setup's number boxes send text (`field-control.tsx`
   `onChange`), so a whole-number string under `notice_days` is stored as an int, on save and on read.
10. **The save fold compares with the stored text** (`_parse_stored(raw)`), never with `before`, the read view: the read
    view has already folded the home pay and the notice text away, so "stored" would always read as unset.
11. **Both home figures stored: the home's own `expected_pay` wins**, on read and on save, and the generic one goes: no
    other country reads it now (owner decision 1), and a job with no country reads the home figure. The move rule
    agrees. Known limit: a Netherlands or UAE home whose only figure is a `desired_salary` saved before this change
    (likely yearly) shows under the monthly label until edited; logged in §13 and the changelog.
12. **A job in a country with no market (France) keeps the home pay**, in the form and the check alike: both read it as
    "no market", as today. Open for the owner (the alternative is none, with the Companion asking).
13. **The home pay is a country answer on a home job.** For the home market with `desired_salary` set, `with_country_answers`
    lists `preferences.desired_salary` in `COUNTRY_ANSWERED`, so `_pay_describe` words it in the home's terms and the
    Companion learns a home pay into the country map, which the server folds.

Added after the Task 10 review (2026-11-03):

14. **The notice label names its unit.** `notice_days` reads "Notice period (days)": the box takes a number, and a
    blank one said no unit in Profile, Next up or Setup. Setup's heading, "How soon could you start?", is unchanged.

Known limit (no Companion release in scope): the Companion's Undo of a learned home pay (`unlearnAnswers`,
`extension/panel/actions/pause.js`) nulls the home entry, but the fold has already overwritten `desired_salary`, so Undo
cannot bring the old figure back. Task 4 pins it with a test that documents the gap; `docs/deferred.md` gets an item.

## Shared shapes

```python
# schemas/form_questions.py, Field (served unless noted)
askedBy: str | None = None    # "Asked by forms in India."; set by resolve on pack fields
legacy: str | None = None     # "notice_period": its text still answers this field until given
# CountryQuestions
home: bool = False            # this country is where you live: its pay reads preferences.desired_salary
```

```ts
// frontend/lib/types.ts
FieldDef.askedBy?: string; FieldDef.legacy?: string; CountryQuestions.home?: boolean;
```

```python
# services/autofill_profile.py
def pay_for(profile: Any, market: str | None, home: str | None) -> str | None:
    """The pay a form in `market` gets: the home's `desired_salary`, another market's own `expected_pay`, or None for a
    market with none. No market (a job whose country can't be told, or one no market covers): `desired_salary`.
    `home` is `chosen_home(session)`: None when unchosen, which reads as today (a market's own, else the one figure)."""

def chosen_home(session: Session | None = None) -> str | None:   # the stored home when chosen, else None
    """Built in Task 3 (89743143). Every pay reader passes this, never the stored home (Decision 7)."""
```

```python
# services/notice.py (new)
def days_from_text(text: Any) -> int | None   # "0", "now", "immediately", "immediate", "N day(s)/week(s)/month(s)"
def notice_words(days: int) -> str            # 0 "Immediately", 7..21 by 7 "N week(s)", 30/60/90 "N month(s)", else "N day(s)"
```

Commands: backend tests from `backend/` with `.venv/bin/python -m pytest <paths> -q -p no:cacheprovider`; the full
suite as `.venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile -p no:cacheprovider`.
Frontend from `frontend/`: `node --test lib/*.test.ts`, `node --test "components/**/*.test.mjs"`, `npx tsc --noEmit`,
`npx eslint <files>`. Served-set fixtures regenerate with `MAESTRO_SERVED_QUESTIONS_WRITE=1`, the MCP wire golden with
`MAESTRO_WIRE_GOLDEN_WRITE=1` (rerun without it after). Commits end with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Notice words and parsing

**Files:** Create `backend/app/services/notice.py`, `backend/tests/test_notice.py`.

**Step 1: failing tests**

```python
import pytest
from app.services import notice

@pytest.mark.parametrize("text,days", [
    ("0", 0), (" now ", 0), ("Immediately", 0), ("immediate", 0), ("1 day", 1), ("45 days", 45),
    ("2 weeks", 14), ("1 week", 7), ("1 month", 30), ("3 Months", 90), (0, 0), (30, 30),
])
def test_days_from_text_reads_plain_answers(text, days):
    assert notice.days_from_text(text) == days

@pytest.mark.parametrize("text", ["negotiable", "2", "", None, "two weeks", "-1 days", True, "1.5 months"])
def test_days_from_text_leaves_what_it_cannot_read(text):
    assert notice.days_from_text(text) is None   # a bare "2" has no unit: never guessed

@pytest.mark.parametrize("days,words", [
    (0, "Immediately"), (7, "1 week"), (14, "2 weeks"), (21, "3 weeks"), (28, "28 days"),
    (30, "1 month"), (60, "2 months"), (90, "3 months"), (45, "45 days"), (1, "1 day"),
])
def test_notice_words(days, words):
    assert notice.notice_words(days) == words
```

`True` is not a number here (`bool` is an `int` subclass: refuse it first). A bare integer (a JSON number) is days.

**Step 2:** run, expect ImportError. **Step 3:** implement with one regex
`^\s*(\d+)\s*(day|days|week|weeks|month|months)\s*$` (case-insensitive) plus the zero words; months are 30 days.
**Step 4:** pass. **Step 5:** commit `feat(notice): read a notice period as days and say days in words`.

### Task 2: Catalog and the served set

**Files:** `backend/app/services/data/markets.yaml`, `backend/app/services/markets.py` (load `pay.period`, `in_text`),
`backend/app/services/data/form_questions.yaml`, `backend/app/schemas/form_questions.py`,
`backend/app/services/form_questions.py`, `backend/tests/test_form_questions.py`,
`backend/tests/fixtures/served_questions/*` (regenerated).

**Catalog changes**
- `markets.yaml`: every `pay` gains `period: year` except NL and AE (`period: month`); US, UK, NL and AE gain
  `in_text: the United States` (etc.). `markets.get` serves `pay.period` (default `year`) and `in_text` (default the
  label). A test pins NL/AE monthly and every other market yearly.
- `form_questions.yaml` preferences: remove `notice_period`; `notice_days` loses `pack`, becomes required, and reads:
  ```yaml
  - key: notice_days
    label: Notice period (days)
    hint: 0 if you can start now. Forms that offer fixed choices get the next one up.
    type: number
    legacy: notice_period
    describe: >- (unchanged)
  ```
  Keep its position (after `desired_salary`). The `expected_pay` answer's comment changes from "The generic desired
  salary stays the answer readiness counts (Decision 3)" to the home rule.

**`resolve` changes** (`home`, `apply_in`, `chosen` as today):
- `CountryQuestions.home = (market == home)`.
- `_answers(m, is_home)`: the home's `expected_pay` is `optional: False`; every other country's stays optional.
- `_groups`: `desired_salary` is dropped from preferences when `chosen and home in apply_in`; kept and made
  `optional: True` with hint "For jobs whose country Maestro can't tell." when `chosen and home not in apply_in`;
  unchanged when unchosen (Decision 2).
- `askedBy` on every pack field in `groups` and `language_fields`: the apply-in markets whose `packs` name its pack, in
  apply-in order, as `in_text`, joined "A", "A and B", "A, B and C": `f"Asked by forms in {names}."`. Never on a country
  set's own fields.

**Step 1: failing tests** (in `test_form_questions.py`; add two helpers, since `_field(raw)` there is the golden's:
`_group_of(qs, key)` returns the served `Group`, `_field_of(qs, group, key)` its `Field`; the tests below call them
`_group`/`_field` for short; rename on the way in):

```python
def test_home_pay_is_the_home_sets_and_required():
    qs = form_questions.resolve(home="US", apply_in=["US", "IN", "IE"], chosen=True, profile=None)
    us, india, ireland = qs.countries
    assert (us.home, india.home, ireland.home) == (True, False, False)
    pay = {c.market: next(f for f in c.answers if f.key == "expected_pay") for c in qs.countries}
    assert pay["US"].optional is False and pay["IN"].optional and pay["IE"].optional
    assert "desired_salary" not in [f.key for f in _group(qs, "preferences").fields]

def test_desired_salary_stays_in_start_and_pay_while_unchosen_or_home_not_applied():
    unchosen = form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None)
    assert _field(unchosen, "preferences", "desired_salary").optional is False
    abroad = form_questions.resolve(home="US", apply_in=["IN"], chosen=True, profile=None)
    field = _field(abroad, "preferences", "desired_salary")
    assert field.optional and field.hint == "For jobs whose country Maestro can't tell."

def test_notice_is_one_answer_in_days_for_everyone():
    for qs in (form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None),
               form_questions.resolve(home="IN", apply_in=["IN"], chosen=True, profile=None)):
        keys = [f.key for f in _group(qs, "preferences").fields]
        assert "notice_period" not in keys and keys.count("notice_days") == 1
        days = _field(qs, "preferences", "notice_days")
        assert days.optional is False and days.legacy == "notice_period" and days.askedBy is None

def test_pack_fields_say_who_asks():
    qs = form_questions.resolve(home="US", apply_in=["US", "IN", "DE", "NL"], chosen=True, profile=None)
    assert _field(qs, "preferences", "serving_notice").askedBy == "Asked by forms in India."
    assert _field(qs, "eligibility", "over_18").askedBy == "Asked by forms in the United States."
    cefr = next(f for f in qs.language_fields if f.key == "cefr")
    assert cefr.askedBy == "Asked by forms in Germany and the Netherlands."
    assert _field(qs, "preferences", "willing_to_relocate").askedBy is None
    assert all(f.askedBy is None for c in qs.countries for f in (*c.permits, *c.answers))
```

Also add `Scenario("US", ["US", "IN", "IE"])` to `SCENARIOS` in `tests/test_served_questions_fixtures.py` (Task 9's
component tests render a US home; `render-harness.mjs` throws for a scenario with no fixture).

Tests this task breaks and updates in the same commit: the `test_form_questions.py` goldens
(`test_a_chosen_us_user_sees_todays_set`, `test_every_home_gets_todays_groups`, `test_india_asks_its_basics…`, the
`_INDIA` set: `notice_days` is everyone's, `askedBy` is served); `test_frontend_every_item_has_a_home.py:190`
(`asked("preferences","notice_period")`); and the frontend suites that read the regenerated fixtures
(`profile-view.test.mjs`, `setup-flow.test.mjs`): update only assertions broken by the served data (the notice key, the
Start and pay rows); behaviour tests belong to Tasks 9 and 10. Every suite is green at the commit.

**Step 2:** run, expect failures. **Step 3:** implement. **Step 4:** pass, then regenerate the served fixtures
(`MAESTRO_SERVED_QUESTIONS_WRITE=1 .venv/bin/python -m pytest tests/test_served_questions_fixtures.py -q`), rerun without
the variable, and read the fixture diff: only `home`, `askedBy`, `legacy`, the notice swap and the pay placement may
change. **Step 5:** run `tests/test_form_questions*.py tests/test_served_questions_fixtures.py tests/test_setup_status.py
tests/test_frontend_every_item_has_a_home.py` and both frontend suites. `test_setup_status.py` fails on the notice key and
the pay placement until Task 5: land Task 5's `_group` legacy read and its preferences pay count here if they are needed
to keep it green, and say so in the commit body. Commit `feat(questions): serve home pay, notice in
days and who asks a pack's question`.

### Task 3: One place for home pay (save, read, move)

**Files:** `backend/app/services/autofill_profile.py`, `backend/app/services/market_settings.py`,
`backend/tests/test_home_pay.py` (new), `backend/tests/test_market_settings.py`.

**Rules**
- **Save** (`_as_stored`, after the maps are merged; `set_profile` passes the stored text as well, Decision 10): let
  `sent` be the save's own `answers_by_country[home].expected_pay` and `stored` the one in the raw stored text. If
  `sent` is set and differs from `stored`, it becomes `preferences.desired_salary`. Otherwise a merged home
  `expected_pay` that is set becomes `desired_salary` (Decision 11: the home's own wins). Either way the home entry
  loses `expected_pay` (an entry left empty goes). Home `None` (unchosen): nothing moves.
- **Read** (`_with_work_auth_by_country`, which already takes `home`): the same fold without a write (a set home
  `expected_pay` wins), so no reader ever sees home pay in two places. `get_profile`/`peek_profile` pass `home` only when
  the market is chosen (Decision 7).
- **`pay_for(profile, market, home)`** as in Shared shapes, reading a read view.
- **Move** (`market_settings.set_market`, after `pin_legacy_work_auth`, same session): new
  `autofill_profile.pin_home_pay(old, new, session)`, called only when `home` changes **and the stored market was
  chosen** (Decision 3): a set `desired_salary` goes to `answers_by_country[old].expected_pay` unless that has its own;
  then `answers_by_country[new].expected_pay`, if set, becomes `desired_salary` and leaves the map, else
  `desired_salary` is removed (it was the old home's).

**Step 1: failing tests** (`test_home_pay.py`, using the module's `set_profile`/`get_profile` on `db_session` as
`test_autofill_profile_schema.py` does, and `market_settings.set_market` for the home):

```python
def test_a_home_expected_pay_is_saved_as_desired_salary(db_session):
    _live_in("US", ["US", "IN"], db_session)
    saved = autofill_profile.set_profile(
        {"preferences": {"desired_salary": "$80,000"},
         "answers_by_country": {"US": {"expected_pay": "$95,000"}, "IN": {"expected_pay": "₹40,00,000"}}}, db_session)
    assert saved["preferences"]["desired_salary"] == "$95,000"
    assert saved["answers_by_country"] == {"IN": {"expected_pay": "₹40,00,000"}}

def test_an_unchanged_home_entry_does_not_overwrite_a_new_desired_salary(db_session): ...  # echo of the read view
def test_a_stored_home_expected_pay_wins_on_read(db_session): ...   # raw text with both: the home's own is shown
def test_unchosen_folds_nothing(db_session): ...
def test_pay_for_home_other_none_and_no_market(db_session): ...   # US "$80,000"; IN own; IE None; None -> "$80,000"
def test_moving_home_pins_the_old_pay_and_adopts_the_new(db_session): ...   # chosen US -> IN
def test_a_first_choice_of_countries_pins_nothing(db_session): ...         # unchosen -> IN keeps desired_salary
```

**Step 2–4:** fail, implement, pass; then run `tests/test_autofill_profile*.py tests/test_market_settings.py
tests/test_market_chosen.py tests/test_autofill_country.py`. `test_autofill_country.py:516`
(`test_the_knockout_salary_check_reads_the_generic_desired_salary`, NL home with both figures) now reads the home's
"EUR 5000": update it to that figure here (the check still reads `desired_salary` until Task 7, which annualises it). **Step 5:** commit `feat(profile): home pay has one place, kept across a move`.

### Task 4: No pay crosses countries in the fill

**Files:** `backend/app/services/autofill_country.py` (`with_country_answers`, `for_market`),
`backend/app/services/autofill_job.py` (`view_for`, `profile_for_job`), `backend/app/routers/autofill.py` (~463),
`backend/app/services/autofill_choose.py` (~306), `backend/app/services/filled_answers.py` (~105),
`backend/tests/test_autofill_country.py`, plus whichever route tests pin `/api/autofill/context`.

**Rule** (`with_country_answers(profile, market, *, home)`): the home market and no market leave
`preferences.desired_salary` as stored; another market writes its own `expected_pay` over it (today), and with none
**removes** `desired_salary` from the view. `for_market(profile, market, *, home, today=None)` and
`view_for(profile, job, market, *, home)` make `home` a required keyword (Decisions 4 and 7: the stored home when
chosen, else `None`, which keeps `desired_salary` for every market); `with_work_auth` gets the same
`home` it got before at each call site (check: for a read view, passing `home` places nothing new, since `work_auth`
already equals the home entry; add a test if none pins that).

**Step 1: failing tests** (`test_autofill_country.py`):

```python
PROFILE = {"preferences": {"desired_salary": "$80,000"},
           "answers_by_country": {"IN": {"expected_pay": "₹40,00,000"}}}

def test_a_country_with_no_pay_of_its_own_gets_none():
    assert "desired_salary" not in autofill_country.for_market(PROFILE, "IE", home="US")["preferences"]

def test_home_and_unknown_country_get_the_home_pay():
    for market in ("US", None):
        assert autofill_country.for_market(PROFILE, market, home="US")["preferences"]["desired_salary"] == "$80,000"

def test_another_country_gets_its_own():
    assert autofill_country.for_market(PROFILE, "IN", home="US")["preferences"]["desired_salary"] == "₹40,00,000"
```

Also: unchosen (`home=None`) keeps `desired_salary` for IE; a home job lists `preferences.desired_salary` in
`country_answered` (Decision 13); a /context test: an Irish job's context carries no `preferences.desired_salary` and
`country_answered` stays `[]`; and the Companion Undo gap (Known limit) as a test that reads the stored profile after a
learned home pay is unlearned and asserts what is left, with a comment pointing at `docs/deferred.md`.

Tests this task breaks: `test_extension_panel_fill.py:2104-2105` and `test_autofill_catalog.py:960` call `for_market`
without `home` (add it); `test_autofill_country.py:337-357` and `test_autofill_choose_jev.py:361` pin the cross-country
fallback (invert them: no pay for a country without its own).

**Step 2–4:** fail, implement, pass; run `tests/test_autofill_country.py tests/test_autofill_choose*.py
tests/test_filled_answers*.py` and the autofill route tests (`grep -l "autofill/context" tests/*.py`). **Step 5:**
commit `fix(fill): a country with no pay of its own gets none, never the home figure`.

### Task 5: Readiness counts home pay in Country answers, and a legacy notice

**Files:** `backend/app/services/setup_status.py`, `backend/tests/test_setup_status.py`.

- `_group` counts a field answered when its own value is, or (`field.legacy`) the legacy key's text is non-blank.
- The home pay counts in `preferences` (Decision 8): when the served preferences group no longer lists
  `desired_salary` (chosen, home applied in), `_autofill_step` adds the home country's required `expected_pay`, read
  through `autofill_profile.pay_for`, to the `preferences` count. Never to `work_auth` or `blocking`.
- Docstring of the module: where the home pay counts and why.

**Tests:** owner-shaped profile (US home, US/IN/IE, `desired_salary` set, notice "0") counts work_auth 10/11 (no
citizenship) and preferences complete with the home pay counted there; the same profile with no pay counts preferences
one short and `stepsDone`'s `work_auth` group unchanged; a profile with only `notice_period: "negotiable"` counts notice
answered; an unchosen profile counts `desired_salary` in preferences as today. Run `tests/test_setup_status.py
tests/test_setup*.py`. Commit `feat(setup): home pay counts in Country answers; old notice text still counts`.

### Task 6: Notice in days on read, save and fill

**Files:** `backend/app/services/autofill_profile.py`, `backend/app/services/autofill_catalog.py` (`with_fill_rules`),
`backend/tests/test_notice_profile.py` (new), `backend/tests/test_autofill_catalog*.py` (the fill-rules tests).

- **Read** (`_parse_profile` view): `notice_days` blank and `notice_period` parses → the view has `notice_days` and no
  `notice_period`; text that doesn't parse stays as `notice_period` (the legacy answer); `notice_days` set → the view
  drops `notice_period`.
- **Save** (`_as_stored`): a whole-number string under `notice_days` is stored as an int (Decision 9); a
  `notice_period` the save sends that differs from the one in the stored text (Decision 10) is parsed into
  `notice_days` (an older Companion learning "2 weeks"); then `notice_days` set → `notice_period` is not stored;
  unparseable text is stored only while `notice_days` is blank.
- **Fill** (`with_fill_rules`): `preferences.notice_period` = `notice.notice_words(notice_days)` when `notice_days` is
  an int; else the legacy text as it is. `notice_days` stays in the view (its `describe` drives fixed choices).

**Tests:** a Profile save of `notice_days: "14"` stores 14 and fills "2 weeks"; "0" reads as 0 days with no text; "negotiable" reads as legacy text and fills as written; a save with
`notice_days: 14` stores no text and fills "2 weeks"; a save sending new text "1 month" over stored days 14 stores 30;
the stale serving-notice rule is unchanged. Tests this task breaks: `test_settings_agent_patch.py:48` and `:372`
assert stored `notice_period` text (update to `notice_days`). Run the new file, `tests/test_autofill_catalog*.py`,
`tests/test_autofill_profile*.py`, `tests/test_settings_agent_patch.py`. Commit `feat(notice): one notice answer in days, words for forms`.

### Task 7: The salary check and the brief read each country's own pay

**Files:** `backend/app/services/knockout.py` (`scan_args`, `scan_job`, `_salary_check`),
`backend/app/services/job_search_brief.py` (`_expected_pay`), `backend/tests/test_knockout.py`,
`backend/tests/test_job_search_brief.py`.

- `scan_args` adds `pay_by_market: dict[str, tuple[str, str]]` (market → (figure, period)) for every applied market
  and the home, from `autofill_profile.pay_for` and `markets.get(m)["pay"]["period"]`; markets with no figure are left
  out. Unchosen (Decision 7): `pay_by_market` is `None`, today's path. A job in a country with no market (Decision 12)
  reads the home figure.
- `scan_job(..., pay_by_market=None)`: when given, the job's market (the `_work_auth_for_job` rule: its country, else
  home) picks the figure; a market with none → no salary check. When not given (direct callers), today's
  `preferences.desired_salary` path, unchanged.
- `_salary_check` takes the figure, its period and its default currency (the home's money currency for the home, the
  market's `currency` otherwise); a monthly figure is ×12 against a yearly posting.
- `_expected_pay(profile, market, home)` in the brief reads `pay_for`.

- `components/job-knockout-card.tsx:84-87` links "Add your desired salary" to `autofill-preferences`: once a country is
  chosen the home pay lives in Country answers, so the link goes to that tile and the words name the pay ("Add your
  expected pay").

Tests this task breaks: `test_autofill_country.py:516` (now the NL home's "EUR 5000" ×12 = 60,000 against 70,000:
pass, `profile_value` names 60,000); `test_frontend_jobs_honest_words.py:71-74` pins
`(preferences or {}).get("desired_salary")` in `knockout.py` and the card's link (update to the new reader and target).

**Tests:** an Indian job with no India pay has no salary check (today it compared $80,000); with India pay
"₹40,00,000" it compares in INR; a Dutch job with "€5,000" monthly compares 60,000; a home job reads `desired_salary`;
a direct `scan_job(job, preferences=…)` call behaves as before; the brief's US `expected_pay` is the desired salary.
Run `tests/test_knockout*.py tests/test_job_search_brief.py tests/test_autofill_country.py
tests/test_frontend_jobs_honest_words.py`. Commit `fix(knockout): compare a job's pay only with its
own country's figure`.

### Task 8: MCP descriptions

**Files:** `backend/mcp_server/server.py` (`PreferenceAnswers` docstring ~368, the `answers_by_country` description
~503–509, the `get_autofill_profile` docstring), `backend/mcp_server/tests/fixtures/wire_golden.json` (regenerated).

`PreferenceAnswers`: "desired_salary is the pay of the country you live in (each other country's is
`answers_by_country[market].expected_pay`; a home entry sent there is saved here); notice_days is the notice period in
whole days (notice_period text such as "2 weeks" is read as days, and kept as text only when it can't be); …". Keep
the field list (old agents may still send `notice_period`). Tool count stays 94. Regenerate the golden, rerun, read the
diff (docstrings only). Run `mcp_server/tests/`. Commit `docs(mcp): home pay and notice days as the server keeps them`.

### Task 9: Profile: home pay in its country set, counts and Next up

**Files:** `frontend/lib/types.ts`, `frontend/lib/autofill-options.ts`, `frontend/lib/autofill-options.test.ts`,
`frontend/components/profile/work-permits.tsx`, `frontend/components/profile/next-up.tsx`,
`frontend/components/profile/profile-view.test.mjs`, `frontend/components/render-harness.mjs` if its fixtures need
`home`.

- Types per Shared shapes.
- `countryAnswerEntry(profile, country)` takes the `CountryQuestions`: for `country.home`, `expected_pay` reads
  `preferences.desired_salary`. `withCountryAnswer(profile, country, key, value)`: the home's `expected_pay` writes
  `preferences.desired_salary`. Update every caller.
- `countryAnswersOpen(profile, questionSet, market)`: required `answers` not answered. The country's heading done mark
  and the tile's row are done only when permits and these are; words stay the permit words, or "expected pay not
  given" when only pay is open.
- `missingAnswers`: after each country's permits, its open required answers as `{ kind: "answer", market, field }`;
  `missingKey` gives `answer:${market}:${key}`; Next up renders it like a permit card (value and save through the two
  helpers above).
- One helper, `answeredIn(field, values)` (its own value, or `field.legacy`'s text), used by `countOf`,
  `missingAnswers` and `useStartTile`'s missing list (`start-and-pay.tsx:19-21`), so a "negotiable" notice is neither
  counted set and listed missing, nor asked by Next up.

Tests this task breaks: `test_frontend_profile_tiles.py:113` pins `withCountryAnswer(current, market, key, next)`
(update to the new call).

**Tests:** lib tests for the two helpers (home writes `desired_salary`, IN writes its entry), `missingAnswers` order
(citizenship, US permits, US pay, …), legacy counting; component tests: the US set shows "Expected salary (USD)"
without "(optional)" holding `$80,000`; Start and pay has no "Desired salary"; Next up asks US pay when blank. Run lib
and component suites, `npx tsc --noEmit`, eslint on the touched files. Commit `feat(profile): home pay sits in its
country's set`.

### Task 10: Notice field, markers and Setup

**Files:** `frontend/components/profile/field-control.tsx`, `frontend/components/profile/start-and-pay.tsx`,
`frontend/components/profile/languages.tsx` (its `FieldControl` has no hint paragraph or `hintId` today: add both so the
CEFR marker renders and is described),
`frontend/components/setup/setup-answers-step.tsx`, `frontend/lib/setup-answers.ts`, `frontend/lib/setup-flow.ts`,
their tests (`lib/setup-flow.test.ts`, `components/setup/setup-flow.test.mjs`, `profile-view.test.mjs`).

- `FieldGrid`/`FieldControl`: the hint line is `[field.askedBy, hint].filter(Boolean).join(" ")`, under the same
  `hintId`, so it is described. A `hints` entry still replaces only the field's own hint.
- Start and pay: while `notice_days` is blank and `notice_period` holds text, `hints.notice_days` is
  `You wrote “${text}” before. Forms get that until you give days.`
- Setup's notice step: the choices store `0`, `14`, `30`, `90` in `notice_days` (labels unchanged), the box is a
  number of days; the step is done when `notice_days` is set or legacy text exists. `PreferenceKey` becomes
  `"notice_days" | "willing_to_relocate"`. Setup asks no pay (Decision 8).

Tests this task breaks: `test_frontend_every_item_has_a_home.py:334-335` pins Setup's
`withPreference(… "notice_period", choice)`; `test_frontend_settings_assistant_words.py:787` pins the hint line.

**Tests:** markers render in the hint for serving notice ("Asked by forms in India.") and the CEFR level, and never in
a country set; the legacy note shows for "negotiable" and not for 0; Setup's "2 weeks" stores 14. Run the suites, tsc
and eslint. Commit `feat(profile): notice in days, and who asks a question`.

### Task 11: Docs, gates and a live check

- `SYSTEM.md`: §6 `{#inv-country-answers-stay-home}` gains "pay included: a country with none gets none"; one §10
  decision line (2026-11-02, superseding plan Decision 3's counted generic pay); two §13 rows (contract rule 2: built
  twice), each mirrored by trigger in `.slopledger.json`: `notice-period-text` (the read and save that turn
  `notice_period` text into days; trigger: no stored autofill profile holds `preferences.notice_period`, and the release
  after has shipped) and `home-expected-pay-fold` (the read and save fold of `answers_by_country[home].expected_pay`;
  trigger: the Companion learns a home pay into `preferences.desired_salary` directly, and no stored profile holds a
  home entry's `expected_pay`). Note the NL/AE legacy-label limit (Decision 11) on the second. Run
  `python3 scripts/check_system_md.py`.
- `docs/deferred.md`: an item for the Companion Undo gap (Known limit).
- `CHANGELOG.md` Unreleased: Changed (pay per country, notice in days, markers), Fixed (home pay reaching Indian and
  Irish forms; the salary check comparing other countries' jobs with converted home pay).
- `docs/entities/others.md` (the autofill profile: `notice_days`, home pay), `docs/agent-surfaces.md` (MCP words),
  `USING_MAESTRO.md` (Start and pay and Country answers), `extension/INTERNALS.md` (the salary row: the server folds a
  home entry), the design doc's notice section (Decision 1 here: on read, no startup step).
- Full backend suite, lib and component suites, tsc, lint, the slop ratchet on both surfaces touched
  (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend` and `… check frontend`, named in the
  claim; `complexity_hotspots` is re-baselined with a reason, never chased), then a browser check on spare ports with a gunzipped copy of the latest backup
  (recipe in the worktree memory): US set shows $80,000 required, India/Ireland pay optional, Start and pay has one
  notice answer reading 0 and no Desired salary, India markers under serving notice, last working day and preferred
  locations. At 1280 and 1024.
- Commit `docs: Start and pay per country`.
