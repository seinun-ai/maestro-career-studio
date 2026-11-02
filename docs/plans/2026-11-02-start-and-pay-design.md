# Start and pay: pay per country, notice in days, and who asks

Owner ask (2026-11-01), after the country form questions shipped to the live app: some of Start and pay's
answers belong to one country, and the tile doesn't say which. Three problems in the owner's own profile:

- **Pay is asked twice, and crosses countries.** "Desired salary: $80,000" sits in Start and pay, and each
  country's "Expected salary" sits in Country answers. A country whose own figure is empty falls back to the
  generic one (`autofill_country.with_country_answers`: "A blank answer ... fills nothing, so the generic answer
  stays"), so Indian and Irish forms get "$80,000". The knockout salary check compares every job with the
  generic figure converted at the ECB rate, so most Indian jobs read as below it.
- **Notice is asked twice.** "Notice period" (free text, required) and "Notice period in days" (the
  `india_basics` pack, optional) are one fact in two shapes.
- **Pack questions don't say they are.** Serving notice, last working day and preferred locations show in
  Start and pay only because India is chosen; over 18 and non-compete only because the US is; the CEFR level
  only because Germany or the Netherlands is. Nothing on screen says so.

Builds on `docs/plans/2026-10-30-country-form-questions-design.md` (the catalog, packs, Country answers) and
its plan's Decision 3 ("expected pay per country optional; the generic desired salary stays counted"), which
this design replaces for pay.

## Owner decisions (2026-11-02)

1. **A country with no pay of its own gets none.** Its form's pay question is left to the Companion, which
   asks on that job; Profile shows that country's pay as open. Rejected: the home figure converted at today's
   rate (a currency conversion is not what anyone asks for in another country), and the home figure as
   written (today's behaviour, the bug).
2. **Home pay stays put.** The home country's figure is still `preferences.desired_salary`, shown in the home
   country's set in Country answers; every other country keeps `answers_by_country[market].expected_pay`.
   Rejected: every country alike, with a one-time move of `desired_salary` into the home entry (cleaner storage,
   but readiness, the MCP tools, the Companion's learning and the knockout check all change, plus a data move).
   This mirrors how work permits treat the legacy one-set `work_auth`: read as the home's, pinned on a move.
3. **Notice is one answer in days**, for everyone.
4. **A question only some countries ask says which**, under its label.

## 1. Pay: one figure per country, all in Country answers

**Profile.** Each country's set in Country answers ends with its pay, in that country's terms (`markets.yaml`
`pay.label`): "Expected salary (USD)", "Expected CTC (₹ per year)", "Expected salary (EUR)". The home country's
field reads and writes `preferences.desired_salary` and is required (no "(optional)"); every other country's is
`answers_by_country[market].expected_pay` and optional. Start and pay shows "Desired salary" only while no
country is chosen.

**Storage.** One place per country:
- **On save** (`autofill_profile`, every writer: the web app, the Companion's learning, MCP): an
  `expected_pay` under the home market is moved into `preferences.desired_salary` and dropped from the map, so
  the home figure is never in two places.
- **On a move of home** (`market_settings.set_market`, beside `pin_legacy_work_auth`): the old home's
  `desired_salary` is pinned to `answers_by_country[old_home].expected_pay` first (unless that country already
  has its own), and the new home's `expected_pay`, if any, moves into `desired_salary`. A move that would find
  both set keeps the new home's own figure and pins the old one.
- **No country chosen**: `desired_salary` is the one figure, as today.

**What a form gets** (`autofill_country.with_country_answers`, which learns the home):
- the home market: `desired_salary`, as stored;
- another market with its own `expected_pay`: that, over the `preferences.desired_salary` slot (unchanged);
- another market with none: the `preferences.desired_salary` slot is **removed** from the view, so the fill
  leaves it and the Companion asks. Pay never crosses countries;
- no market (a job whose country Maestro can't tell): `desired_salary`, as today.

**Readiness.** The home figure counts, as `desired_salary` does today, but in the `work_auth` group (Country
answers' tile) once a country is chosen; in `preferences` while none is. Other countries' pay stays optional.

**Knockout salary check** (`knockout._salary_check`, `scan_args`). The figure is the job's country's own: the
home's `desired_salary` for a home job, the country's `expected_pay` for another, and **no check** for a country
with none (never a figure converted from another country). Each market's pay names its period
(`markets.yaml` `pay.period`: `year`, or `month` for the Netherlands and the UAE); a monthly figure is compared
×12 with a yearly posting. A job with no country uses the home figure, as today.

**Agents.** `get_job_search_brief`'s per-market `expected_pay` reads `desired_salary` for the home market;
`set_autofill_profile` takes either shape, normalised on save. No new tool.

## 2. Notice: one answer, in days

**Profile.** Start and pay has one "Notice period", `preferences.notice_days` (whole days, required), for
everyone: it leaves the `india_basics` pack. Hint: "0 if you can start now. Forms that offer fixed choices get
the next one up." The free-text `notice_period` field is gone from the tile.

**Setup.** The quick choices stay: "Now", "2 weeks", "1 month", "3 months" store 0, 14, 30 and 90 days; a days
box takes anything else.

**What a form gets.** The fill's `preferences.notice_period` slot keeps its name, so the Companion, the catalog
and /choose read the same slot; its value is computed from the days (`autofill_catalog.with_fill_rules`):
0 → "Immediately", a whole number of weeks under 4 → "N week(s)", 30/60/90 → "N month(s)", anything else
"N days". A form with fixed choices takes the shortest choice at least that long, never a shorter one
(`notice_days`' `describe`, unchanged).

**Existing answers.** A one-time startup step (`notice.days_checked`, a local flag like
`market.chosen_checked`; the always-on copy skips it, its row arrives by sync) turns a stored `notice_period`
into `notice_days` when `notice_days` is empty and the text reads as one of: "0", "now", "immediately",
"immediate", "N day(s)", "N week(s)", "N month(s)" (30 days a month). Text it can't read ("negotiable") stays
stored: forms get it while the days are empty, Profile shows it beside the empty days box ("You wrote
'negotiable' before. Forms get that until you give days."), and readiness counts it as answered, so no one's
count drops.

**Saving from elsewhere.** A save that carries `notice_period` text (an older Companion learning it, an agent)
is parsed into `notice_days` on the server the same way; unreadable text is stored as the legacy answer.

**Unchanged.** "Are you serving your notice period?" and "Last working day" stay India-only and optional, and
the fill still drops them once the day has passed. "Earliest start date" stays its own answer.

## 3. Markers on questions only some countries ask

**Served set.** Each catalog field with a `pack` is served with `asked_by`: the markets in `apply_in` whose
packs name it, in `apply_in` order (`form_questions.resolve`). A field no pack gates, and any field inside a
country's own set, is served without it.

**Profile.** A field with `asked_by` gets a muted first sentence in its hint slot: "Asked by forms in India.",
"Asked by forms in Germany and the Netherlands." Country names, never adjectives, so any country reads
naturally. An existing hint follows on the same line. It is part of the hint, so `aria-describedby` reads it.

Today that marks serving notice, last working day and preferred locations (India) in Start and pay; total
experience (India) and over 18 and non-compete (United States) in Screening questions; and the CEFR level
(Germany and the Netherlands) in Languages.

## Tests

- Server: a market with no `expected_pay` gets no pay slot, the home market gets `desired_salary`, no market
  gets `desired_salary`; a home `expected_pay` is folded into `desired_salary` on save; a move of home pins and
  swaps; the salary check compares only the job's country's figure and annualises a monthly one; notice text
  parses to days, unreadable text is kept and still counts; days turn into words; `asked_by` names the asking
  markets in order; readiness counts the home figure once, in the right group.
- Frontend: the home set shows pay bound to `desired_salary`, required; Start and pay drops "Desired salary"
  once chosen and keeps it unchosen; the notice field is days with the legacy-text note; markers render in the
  hint.
- A browser check at 1280 and 1024 with a copy of the owner's data (US home, applying in the US, India and
  Ireland).

## Touch points

`data/markets.yaml` (`pay.period`), `data/form_questions.yaml` (notice, `desired_salary` placement),
`services/form_questions.py` (`resolve`, `asked_by`), `services/autofill_profile.py` (save normalisers),
`services/market_settings.py` (move pin), `services/autofill_country.py` (no cross-country pay),
`services/autofill_catalog.py` (notice words), `services/knockout.py`, `services/job_search_brief.py`,
`services/setup_status.py`, a startup step beside `mark_answered_installs_chosen`, `mcp_server/server.py`
(docs and types), the Profile tiles (`work-permits.tsx`, `start-and-pay.tsx`, `field-control.tsx` for the
marker), Setup's notice step, `lib/autofill-options.ts` and `lib/setup-answers.ts`. Docs: `SYSTEM.md` §10,
`CHANGELOG.md` Unreleased, `docs/entities/others.md`, `docs/agent-surfaces.md`, `USING_MAESTRO.md`. The
Companion needs no change: it reads the same slots, and the server normalises what it saves.

## Amended while planning (2026-11-02)

The plan (`docs/plans/2026-11-02-start-and-pay.md`, "Decisions taken while expanding") changes four details here:
- **Notice converts on read**, not by a one-time startup step: a read computes `notice_days` from readable text, and
  the next save stores it. No flag, nothing for the always-on copy to skip.
- **Readiness counts the home pay in `preferences`**, as it counts `desired_salary` today, not in the `work_auth`
  group: Setup's answers step needs that group complete and Setup never asks pay. Country answers' own tile still shows
  the home pay as open when it is missing.
- **With no country chosen, pay reaches every country's form**, as today: the stored home is then a default, not a
  choice.
- **When both home figures are stored, the home's own `expected_pay` wins** and the generic one goes; and a job in a
  country with no market (France) keeps the home pay in the form and the check, as today (open for the owner).
