# MCP writes for form answers and preferences

Owner-approved boundary (2026-10-23). An agent connected over MCP, with no web UI and no AI key in Maestro, can
finish Setup's facts: the form answers, where the user lives and applies, the jobs they want and their persona.

## Goal

A live check found that after a full MCP onboarding, `GET /api/settings/autofill` returned `{}`. Setup status read
form readiness 0.0, with work permits blocking. MCP could read the form answers and preferences
(`get_autofill_profile`, `get_job_search_brief`) but could not write them.

Done when:
- an MCP-only agent can fill the autofill profile and the preferences;
- setup readiness rises;
- per-country work-permit answers round-trip through `get_autofill_profile`;
- the human-only settings stay unwritable over MCP.

## Boundary

Over MCP an agent may write the facts that Setup and Profile ask for. Two exceptions: the AI key, and the diversity
(EEO) answers. It never writes:
- Settings' behaviour switches;
- the consent records;
- the secret.

| Written over MCP | Human-only (no tool) |
|---|---|
| autofill profile, without `eeo` | full automation (inv-auto-consent-gated) and auto-apply |
| job preferences | EEO standing consent (inv-eeo-standing-consent) and every EEO answer value |
| market (`home`, `apply_in`) | job-site login (inv-job-site-password-local) |
| money's `home_currency` | Screening answers dial (`companion-apply`), hints switch (`mcp-workflow`) |
| persona | model keys, model picks, prompts, Jev, form-filling options, quick-tailor |

Quick-tailor stays out: it is a Settings › Advanced behaviour (which automatic resolutions Quick tailor may make), and
an MCP agent writes its own tailoring ops.

## What the endpoints do today

- `PUT /api/settings/autofill` replaces the whole profile. Only `work_auth_by_country` merges, by market
  (`autofill_profile._as_stored`).
- It does not check market keys: "GB" would be stored, and no reader would ever use it. The market key is "UK".
- `PUT /job-preferences` and `PUT /money` validate full models with defaults, so a partial body resets the rest.
- Setup status counts work-permit answers only for the countries in `apply_in`. It also counts persona as a step.

So every tool reads the setting, merges in what it was given, and writes the result. There is no new REST route. A
Profile tab open at the same moment sends the whole profile, and could overwrite either way: profile saves have no
version check (docs/deferred.md). A server-side PATCH would only narrow a window of a few milliseconds.

## Tools (four; `full` gets them all)

1. **`set_autofill_profile`** (`apply`, `career`). Takes `personal`, `eligibility`, `preferences`,
   `work_auth_by_country`, `education`, `languages`, `custom`.
   - Only the sections passed change.
   - Inside `personal`, `eligibility`, `preferences` and each market's answers, only the keys passed change, and a
     null removes a key.
   - A market set to null removes that market's answers.
   - `education`, `languages` and `custom` replace the stored list whole.
   - Each shape is a TypedDict that refuses unknown keys, so the shapes live in the schema.
   - Market keys are a `Literal` of `markets.keys()`.
   - It has no `eeo` field, and the client refuses any section outside its list. That makes two gates. The stored
     `eeo` is written back unchanged.
   - Returns the saved profile without `eeo`, plus setup's `autofill` block (a best-effort read).
2. **`set_job_preferences`** (`career`). Takes `favored_roles`, `years_experience`, `employment_types`, `locations`,
   `remote`, `min_salary`, `notes`.
   - Only the fields passed change; `[]` clears a list and `""` clears notes.
   - `role_categories` is derived on the server and is not a parameter.
3. **`set_markets`** (`career`). Takes `home`, `apply_in`, `home_currency`.
   - `home` and `apply_in` merge into `PUT /market`.
   - `home_currency` merges into `PUT /money`; `""` follows the home market.
   - Returns home, apply_in, the resolved currency and setup's `autofill` block.
4. **`set_persona`** (`career`). Replaces the whole text; `""` clears it. The app's own draft needs its AI key, so
   the agent drafts the persona and the user approves it.

The hunt profile gets none of them. The apply profile gets `set_autofill_profile` only, so an answer learned during an
application is saved once.

## Pins

- A source scan of `mcp_server/client.py` keeps the settings paths the MCP writes to equal to the five above. A new
  settings write over MCP then needs a deliberate test change.
- `set_autofill_profile`'s schema has no `eeo` property.
- The client test checks that the stored `eeo` survives a write and never reaches the response.
- Market keys outside the market list are refused.
- Profiles: `apply` and `career` carry what is listed above, and `hunt` carries none.
- `next_after_base_from_kb` names `set_autofill_profile` only when the profile registered it and setup status says
  the form answers are not done.
