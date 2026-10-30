# Form questions by country

Owner ask (2026-10-30): the form answers are one fixed set for every country, shaped like a US
application. Organise them by country: with no country set, ask a generic set; with countries set,
ask what those countries' forms ask. Start with the basics, and let countries share traits.

## Where it stands

Already per country: work-permit answers (`work_auth_by_country`, worded by `work_auth_vocab`
`us_visa` / `uk` / `generic`), the address's state line (`asks_state`, `state_label`), and whether
diversity questions are offered at all (`eeo_module`, US and UK).

One set for everyone: "Are you 18 or older?" and "Subject to a restrictive covenant?" (US
screening questions), education's "GPA", and the diversity answers (a UK form reads the US-shaped
set: deferred item 53). Nothing asks India's current or expected CTC, a notice period in days, an
EU citizen's free movement, or a Gulf residence status. An unchosen country reads as the US
(`markets.DEFAULT_MARKET`), so a new user gets the US set.

## Decision

**A question catalog in data.** Countries name shared **packs** of questions; a country's set is
the generic set plus its packs. Adding a country later is data, not code, as `markets.yaml`
already promises for currency, dates and the diversity posture.

Rejected alternatives: (B) extending today's `work_auth_vocab` switch in code (every country or
pack touches five or six files and the hand-mirrored `GROUPS` grows); (C) seeding per-country
questions into the free-form `custom` answers (knockout questions lose their `exact` handling and
readiness cannot count them).

## Countries and packs

Nine countries: the eight markets already in `markets.yaml` and the United Arab Emirates (new).
Any other country gets the generic set.

**Generic set** (no country chosen, or a country with no market): contact and links, education,
languages, the three work-permit Yes/No questions and expiry, expected pay, notice period,
earliest start, relocation, how you heard, worked here before, citizenship.

| Pack | Adds | Countries |
|---|---|---|
| `visa_status` | The country's own status list before the Yes/No questions | US (exists), CA, AU, AE |
| `eu_movement` | Right to work derived from an EU, EEA or Swiss citizenship (no question of its own) | DE, NL, IE |
| `cefr` | A CEFR level (A1–C2) per language | DE, NL |
| `us_screening` | 18 or older; restrictive covenant | US |
| `pay_terms` | Expected pay worded in the country's terms: annual base, gross annual, package including super, CTC, monthly package | all, per country |
| `india_basics` | Current CTC, expected CTC, notice in days, serving notice and last working day, total and relevant years of experience, preferred locations | IN |
| `gulf` | Citizenship required, residence status (`visa_status`), visa expiry, in the country now, local driving licence, monthly package (basic, housing, transport, total) | AE |
| diversity | The country's own voluntary set | US (exists); UK, CA, AU in phase 4 |

| Country | Packs |
|---|---|
| US | visa_status, us_screening, diversity (exists) |
| CA | visa_status (citizen, PR, open or employer-specific work permit, PGWP, …) |
| UK | right-to-work wording (exists) |
| IE | eu_movement (plus UK citizens through the Common Travel Area) |
| DE, NL | eu_movement, cefr |
| AU | visa_status (citizen, PR, NZ citizen, visa with full or limited work rights), pay including super |
| IN | india_basics |
| AE | gulf |

"Arab countries" is not a pack: forms follow labour and visa law, not language. Saudi Arabia,
Qatar and the other Gulf states are added later as `gulf` plus their own extras (Saudization, a
residence-permit transfer, their permit names).

Date of birth and marital status, which Gulf forms ask, are not stored answers in this design: the
Companion pauses on them each time.

## 1. The catalog and stored answers

**Countries stay in `markets.yaml`.** Each market gains `packs`, its `work_status` choices and its
`pay` terms. The UAE is added:

```yaml
- key: AE
  label: United Arab Emirates
  currency: AED
  packs: [gulf]
  work_status: [citizen, gcc_national, employment_visa, family_visa,
                golden_or_green_visa, freelance_permit, visit_visa, no_visa]
  pay: monthly_package
```

**Packs live in `backend/app/services/data/form_questions.yaml`.** Each question declares: key and
storage path, wording, type and choices, **scope** (`you`: asked once; `country`: asked per
country), whether setup counts it (knockout) or it is optional, its fill policy (`exact` / `flag` /
`any`, `autofill_slots.policy_for`), the plain description the fill loop reads, and the Profile
tile it shows on. A key that appears in two packs must be the same question in both (a loader
check).

**Storage.** Nothing stored today moves.
- `you` answers: the existing sections (`personal`, `preferences`, `eligibility`), new keys.
- `country` answers: a new `answers_by_country: {<market>: {...}}` beside `work_auth_by_country`,
  keyed by market ("UK", not "GB"), like it.
- Visa status stays `work_auth_by_country[<market>].status`; its choices come from the market's
  `work_status`. The US list keeps today's stored values, so `WorkAuthStatus` widens from a
  Literal to a per-market check without rewriting any profile.
- Citizenship: `personal.citizenships`, a list of ISO codes (dual citizens list both). It replaces
  a separate "EU citizen?" question.

**Derived answers** are computed on read, never stored, and an explicit answer always wins:
- a citizen of X: in X, right to work Yes, sponsorship now and later No;
- an EU, EEA or Swiss citizen: the same in DE, NL and IE;
- a UK citizen: the same in IE; an Irish citizen: the same in the UK.

**Readers stay country-blind.** As `autofill_country.with_work_auth` folds the job's market's
permit answers into one `work_auth`, the job's market's `answers_by_country` entry is folded into
flat sections before the fill catalog and the Companion read the profile. A question that names
another country gets that country's answers (`market_for_question`), as permits do.

**No country chosen means the generic set.** Today `market_settings.is_set` cannot tell a deliberate
US pick from the default, so the market setting gains a stored "chosen" mark that question
resolution reads. Currency and date defaults are unchanged.

**US screening leaves the generic set.** `over_18` and `non_compete` move to `us_screening`. A
stored answer stays stored and still fills a form that asks.

**Diversity is unchanged in phases 1–3.** The consent gates around `eeo`
(inv-eeo-standing-consent) are the riskiest code in this area; per-country diversity is phase 4.

## 2. Profile and Setup

**One served question set.** `GET /api/settings/autofill/questions` returns the set resolved for
the chosen countries: `you` questions (each once, with its tile), each country's questions, and the
derived answers with their source. Profile, Setup and `setup_status` read it. The hand-mirrored
`GROUPS` (`frontend/lib/autofill-options.ts`) and `test_autofill_groups_parity.py` are retired. No
country chosen: the generic set.

**The Work permits tile becomes "Country answers".** Citizenship sits at the top ("Citizen of:
India", Edit); then one row per apply-in country with its count or "From your citizenship".
Opening a country shows its permit questions, then its other `country` questions. A derived
answer reads "From your citizenship" with **Answer differently**. "Where you apply" stays the
place to pick countries.

**Pack `you` questions join existing tiles.** Start and pay: current and expected CTC, notice in
days, serving notice, last working day. Languages: a CEFR level while DE or NL is an apply-in
country. The Eligibility fold becomes **Screening questions**: worked here before for everyone,
years of experience for India, the two US questions while the US is an apply-in country.

**Removing a country hides its questions and keeps the answers.**

**Setup asks only knockout questions:** citizenship once; each apply-in country's permit questions
that citizenship does not settle; the generic required set. Optional per-country questions are
never asked in Setup; the Companion asks them when a form does.

**Readiness** counts the generic required questions and each apply-in country's knockout
questions; a derived answer counts as answered; optional questions never count.

## 3. Fill, agents, phases and tests

**Fill.** The fill loop runs server-side and matches by each question's description, so new pack
questions fill without a Companion release. Citizenship and visa status are `exact`.

**Learning a paused answer.** `/context?question=<label>` gains `learn_to` (scope, market, key);
the Companion's pause row writes there (`panel/actions/pause.js`), so a per-country answer lands in
that country's entry, not in `custom` where it could reach another country's form. This needs a
Companion store release; an older Companion keeps writing to `custom`.

**Agents (MCP).** No new tools. `get_autofill_profile` adds citizenships, `answers_by_country` and
the resolved question set; `set_autofill_profile` accepts them, checked against the catalog
(unknown keys and choices refused; `AGENT_SECTIONS` gains `answers_by_country`);
`get_job_search_brief` carries each market's answers beside its permits. EEO values still never
reach an agent.

**Phases.**
1. Catalog, no visible change: `form_questions.yaml` holds today's questions exactly; Profile,
   Setup and readiness read the served set; `GROUPS` and its parity test retired. A golden test
   shows every existing user's set is unchanged. This reverses the call recorded in
   `test_autofill_groups_parity.py` (serving the list was rejected because labels were
   presentation): per-country wording makes them country data. The "chosen" mark moves to phase 3,
   where it is first read.
2. Source check, before building on country facts: CA, AU and AE status lists; the derivation
   rules; whether UAE addresses need an Emirate line (`asks_state`); India's CTC and notice
   conventions. Each source is cited in the YAML, as `markets.yaml` does.
3. Packs and countries: the generic and US split, citizenship and derived answers, the nine
   countries' packs and the AE market, the Country answers tile, Setup's knockout-only answers,
   the fill fold-in, MCP, `learn_to` and the Companion release.
4. Later: per-country diversity, the UK first (its list is verified; deferred item 53), then CA
   and AU once their lists are checked.

**Tests.**
- Catalog loader: every market's packs exist; a shared key is the same question in every pack.
- Phase 1 golden: the US set equals today's `GROUPS` and permit questions.
- Resolution: no country gives the generic set; IN + AE + DE + NL gives each question once.
- Derivation: each rule; an explicit answer wins; derived answers are never stored.
- Fill: a country's answers reach only that country's jobs; older profiles and sync peers read
  unchanged.
- Frontend: `node --test` for the served set's display; a browser check at 1280 and 1024.
- Companion: `learn_to` routing.
- SYSTEM.md: a new invariant beside inv-work-permit-per-country (a country's answers never reach
  another country's form), and the affected sections of `docs/entities/others.md` and
  `docs/agent-surfaces.md`.

## Touch points

- `backend/app/services/data/markets.yaml`, new `form_questions.yaml`, `services/markets.py`
- `schemas/autofill_profile.py`, `services/autofill_profile.py`, `services/autofill_country.py`
- `services/setup_status.py`, `services/market_settings.py`, `routers/settings.py`
- `services/autofill_catalog.py`, `services/autofill_slots.py`
- `mcp_server/` profile tools, `services/job_search_brief.py`
- `frontend/lib/autofill-options.ts`, `components/profile/*` (work-permits, eligibility,
  start-and-pay, languages), `components/setup/setup-answers-step.tsx`, `lib/profile-tiles.ts`
- `extension/panel/actions/pause.js`, `routers/autofill.py` and `services/autofill_context.py` (`/context`)
