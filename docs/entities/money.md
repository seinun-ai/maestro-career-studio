# Money and rates

> Reference tier, indexed from [SYSTEM.md](../../SYSTEM.md) §4. Its header contract governs this file too: integrate, present tense, no dated history, and update alongside the behavior described.

Pay reads in one home currency (owner decision D8). A converted figure is marked "≈" and keeps the posted amount; rates
are the ECB's daily reference rates; missing pay is never estimated. A job's *posted* currency is a separate rule
(`market_settings.default_currency_for_capture`: [job.md](job.md), `salary_currency`); where the user lives is the
`market` setting ([others.md](others.md), "`market` setting").

- **The home currency** (`services/money_settings.home_currency`) resolves in one order, one source per answer: the
  `money` setting's `home_currency` when the user picked one, else where they live
  (`market_settings.home_market_currency`: the home market's currency once a market is chosen, else the deployment's
  `HOME_CURRENCY`, default USD). Left unpicked, it follows a move of `home`.
- **The `money` setting** (`schemas/money.py` `MoneySettings`; file-mirrored at `settings/money.json`, a profile setting
  that syncs like the others; `GET/PUT /api/settings/money` answers `{key, value, home_currency}`, the last resolved; an
  agent's `set_markets` writes `home_currency` alone through `PATCH /api/settings/market`, with the market in one transaction,
  every other money field kept):
  `home_currency` (an ISO 4217 code the country data names, or null for "where I live"; an unknown code 422s),
  `period` (`year`|`month`|`hour`, how pay is shown), `show_posted` (the posted amount under a converted one, default
  on) and `hours_per_year` (default 2080, 1 to 8784; Settings › Advanced).
- **The arithmetic is pure** (`services/money.py`, `Decimal` only; `frontend/lib/money.ts` mirrors it): `convert` goes
  through the euro and returns None for a currency with no rate or with no cache, never a guess (the same currency
  needs no rate); `to_yearly` is hour × hours per year, day × 260, week × 52, month × 12, year × 1, and None for an
  unknown period; `midpoint` is a range's middle or its one end. Nothing sorts or filters on pay yet; Analytics' pay by
  role ranks roles on their converted pay (`explore_overview._pay_by_role`).
- **ECB reference rates** (`services/fx_rates.py`): the euro reference rates file at
  `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`, about 29 currencies per euro, published around
  16:00 CET on working days; the ECB asks to be cited and calls them information only, so a page names the source and
  the rate date. `GET /api/fx/rates` (`{base, date, rates, fetched_at, source, source_url}`, rates as numbers)
  fetches first only when a page asks and the cache is older than a day; a failed try waits an hour before the next;
  offline keeps the last cache; with no cache it answers `date: null, rates: {}` and nothing converts.
  `POST /api/fx/rates/refresh` fetches now (the Update button): a 502 with a fixed sentence when the ECB cannot be
  reached, the cache untouched. `parse_ecb_xml` refuses anything that is not the ECB file (a DOCTYPE, no dated day, a
  rate that is not a positive number). The fetch is injectable (`fetch(url) -> text`); the default is
  `http_client.new_client` with a 5 s timeout. The call carries no user data and is listed in PRIVACY.md, "Exchange
  rates".
- **The rates cache is machine-local**: one `Setting` row, `fx_rates`, in `sync/registry.LOCAL_SETTING_PREFIXES`, with
  no file mirror (a cache, refetched when lost). Each copy fetches its own, the always-on copy may write it (the flush
  guard refuses only profile rows, SYSTEM.md §6 inv-flush-guard) and a profile bundle never carries it. Rates are
  stored as the ECB's own text, so a figure is exact; `fx_rates.current` is the read that never fetches or writes.
- **The browser formats every pay figure with one function** (`frontend/lib/money.ts` `formatPay(pay, options)`, options
  from `hooks/use-money.ts` `useMoney`, which reads `GET /api/settings/money` and `GET /api/fx/rates` through
  react-query): compact currency with each end written out ("€75K–€90K"; `formatRange` is not used, it collapses to
  "€75–90K"), the narrow symbol for the home currency and the full one for others ("US$", "CA$"). A figure in another
  currency, or made yearly from another period (`per`, `hoursPerYear`), reads "≈ …" and keeps `posted`; with no rate
  it is the posting's own and `noRate` says so; with no pay it is null; with no currency it is a plain number, never
  a guessed dollar. `payLine` adds the period in words ("a year"). The job page header, its Job details card (the
  posted amount and rate date under a converted figure, while `show_posted` is on), Today's Next up and Analytics'
  yearly pay by role (each role's range in the home currency, "≈" when any of it was converted, with one line naming
  the currencies converted and the ECB rate date) use it; Profile's Minimum salary and Setup's where step read
  `useMoney` for the home currency (and the ECB's currencies). There is no USD default anywhere. Settings › Basics ›
  Money sets `home_currency`, `period` and `show_posted` and shows the rate date with Update; Advanced › Hours per year
  sets `hours_per_year`.

Pinned by `tests/test_money.py`, `tests/test_fx_rates.py` (one fetch per day, offline, no cache, machine-local) and
`tests/test_frontend_money.py` (the `lib/money.test.ts` node suite and the callers).
