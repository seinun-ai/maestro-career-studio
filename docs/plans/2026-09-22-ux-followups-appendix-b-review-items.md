> **Appendix B (earlier UX review items) to `docs/plans/2026-09-22-ux-followups.md`.** Research brief written read-only
> against `a3c800bb`; each task in the plan names the section it uses. Where this appendix offers
> options, the plan's "Owner decisions" section is binding. Line numbers drift: re-locate before editing.

# Brief: Phase B earlier-review items (8 items)

Research snapshot: worktree `seinun-resume-update-45a8c0`, branch `claude/ux-followups` at `a3c800bb`.
Everything below was read in the code on that commit (the `docs/ux/` reports lag the code, so each
claim here was re-checked against source). Line numbers refer to that commit.

**Goal (carry this into the plan).** Nothing a person reads should show an internal key or slug, nothing
the UI shows should claim something it does not do, and each item lands with the smallest honest change.
Do not add features. Where a decision was asked for, this brief makes it and says why. The plan-writer can
overrule it, but should say so.

**Cross-cutting constraints**
- **The MCP docstring IS the API** (SYSTEM.md §7). Ratchet `mcp_server/tests/test_server.py::test_registered_tool_docstrings_fit_client_truncation_budget`,
  cap `_DOCSTRING_CLIENT_BUDGET = 2000` (line 1096). It takes the max of the raw, cleandoc and SOURCE lengths.
  Current source lengths: `explore_gap_frequency` 941, `get_job_search_brief` 690. Both have more than 1,000 chars of room.
- **Chat prompt edits do not reach existing installs.** `prompts.get_prompt` and `seeding.seed_prompts` write
  `prompt.chat_system` into the DB on first read and never resync it (SYSTEM.md §7). A change to
  `chat_system.txt` only reaches fresh installs or a manual reset. Put any rule the model must obey in the
  **tool description** (`chat_tools.TOOL_SPECS`), which is live on every run. A prompt line is optional
  reinforcement on top of that.
- **Version skew is routine** (frontend-conventions Analytics bullet). New response fields must be optional in TS,
  and an old backend must degrade to "less shown", never to "wrong shown".
- **Frontend slop ratchet has zero headroom** (the honest-studio plan notes 518/518). New helpers and components
  can move `complexity_hotspots`. Run `slop_scan.py check frontend` and `check backend`, name both in the claim,
  and re-baseline with a reason if the count moves without real decay.
- **Doc contract:** update `docs/frontend-conventions.md` (and SYSTEM.md where noted) in the same change, in present tense.
- Verify: `cd backend && pytest tests/ mcp_server/tests/ -q`; `cd frontend && npx tsc --noEmit && npm run lint && node --test lib/*.test.ts`;
  `python3 scripts/check_system_md.py`. Use the fresh-stack recipe for the browser pass (memory: worktree verification recipe).

**Suggested order:** 1 → 4 → 6 → 7 (small, independent) → 2 → 3 (backend + frontend) → 5 → 8 (widest file spread, docs decision).

---

## 1. Career KB "Profile" tab collides with `/profile`

**Where**
- `frontend/app/career/page.tsx:34`: `const [activeTab, setActiveTab] = useState("profile");`
- `:50`: comment `// On an entity tab, "New entity" defaults to that kind; on Profile, to experience.`
- `:104`: `<Tabs id="kb-entities" value={activeTab} onValueChange={setActiveTab} className="gap-5">`
- `:106`: `<TabsTrigger value="profile">Profile</TabsTrigger>`
- `:119`: `<TabsContent value="profile" className="space-y-4">` (holds `<ProfilePanel />` + `<CareerExportsCard />`)

**Root cause.** The sidebar footer's "Profile" (`/profile`, who the candidate is: persona, market, preferences,
autofill) and this tab share one word for two different records.

**URL/deep-link audit (decides the value question).**
- Tab state is plain `useState`. Nothing reads or writes `?tab=` on `/career`, so no URL carries the value.
- `grep` for `tab=profile`, `/career?`, `/career#` finds only `/career#kb-inbox` (upload-dialog.tsx:91) and
  `/career#inbox` (kb-capture-card.tsx:19). Both anchors exist (`id="kb-inbox"` wrapper and `id="inbox"` on the
  InboxPanel Card, inbox-panel.tsx:161), and neither touches the tabs.
- `setup-steps.ts:117` `anchor: "kb-entities"` targets the `Tabs` root. `useFocusSection` only scrolls and rings it and
  does not select a tab, so the default tab (this one) is what the "Import resumes" step lands on. The rename does not change that.

**Fix (decision: rename the value too).** It carries no compatibility cost, and a value that disagrees with its
label invites the next reader to "fix" one of them.
```tsx
const [activeTab, setActiveTab] = useState("basics");
// On an entity tab, "New entity" defaults to that kind; on Basics, to experience.
<TabsTrigger value="basics">Basics</TabsTrigger>
<TabsContent value="basics" className="space-y-4">
```
Leave the card title "Career profile" (profile-panel.tsx:261, :120) alone. It names the KB record, the export is literally
`# Career Profile` (services/exports.py:98), and it is not a nav word. Optional: the Autofill card's disabled reason
(`components/settings/autofill-section.tsx:701`, "Add usable contact details to your career profile first.")
could say where that is: "Add contact details under Career KB, Basics, first."

**Tests.** No test pins the tab label or value. `tests/test_frontend_query_error_states.py:68` pins
`("app/career/page.tsx", "No custom sections yet")`, which is untouched. No new test is needed: it is a one-word
copy change with no logic.

**Risks.** None found. No docs mention the KB "Profile" tab (only `docs/ux/` and the plan's out-of-scope list).

---

## 2. Gap category ids leak into chat/MCP prose

**Where the keys come from.** `backend/app/services/gap_analysis.py:10-18` `_CATEGORIES` (key, title, description), and
`:24-39` `_HINT_TO_CATEGORY`, whose **values are exactly the five skill-kind categories** (`missing_skills`,
`mirror_wording`, `dual_place`, `resurface_recent`, `adjacent`). Neither analytics sweep emits a label:
- `backend/app/services/explore_gaps.py:174-188`: `gap_frequency` rows `{"skill","n_jobs","avg_potential_points","category","requirement_level","low_sample"}`
- `backend/app/services/explore_build_areas.py:143-158`: `build_areas` rows `{..., "status", "tier", "category", "wording_jobs"}`
- Routers `backend/app/routers/explore.py:281-291` (`/gap-frequency`) and `:333-344` (`/build-areas`) return plain dicts
  with **no `response_model`**, so no schema change is needed.

**Where the only human labels live.** `frontend/components/analytics/gap-tiers-panel.tsx:45-57`:
```ts
const CATEGORY_LABEL: Record<BuildAreaCategory, string> = {
  missing_skills: "no evidence on this resume",
  mirror_wording: "exact token missing",
  dual_place: "needs corroborating",
  resurface_recent: "stale evidence",
  adjacent: "adjacent skill",
};
```
Used at `:180-181` (`isSurface && row.category ? CATEGORY_LABEL[row.category] : null`) and rendered at `:203-205`.

**Where agents read keys.**
- MCP `explore_gap_frequency` (`backend/mcp_server/server.py:1185-1211`) returns gap_frequency rows. The docstring says nothing about wording.
- MCP `get_job_search_brief` (`server.py:304-316`) carries `build_areas` (via `services/job_search_brief.py:182`). The docstring only says "build areas".
- Chat `tool_analytics_gap_frequency` (`backend/app/services/chat_tools.py:358-374`) returns both lists. Its spec (`:626-652`)
  says `"status is the raw KB-evidence label (missing/in_kb/ported) ... category is the gap category driving the row."`
  That invites the model to quote `dual_place`.
- `backend/app/prompts/chat_system.txt:13`: the analytics rule. It does not mention wording.

**Decision: ONE source, on the server; the frontend reads it and drops its mirror.** Rationale:
three consumers (web panel, MCP, chat) need the words, and two of them cannot import TS. A backend constant plus a
frontend mirror plus a contract test is the SYSTEM.md §13 "cross-boundary duplication" shape, and it buys nothing
here: the server already sends the row. Skew degrades honestly, because an old backend sends no `category_label`, so
the surface row simply shows no secondary label (never a wrong one). Keep the frontend's current strings exactly,
so the web UI does not change.

**Backend fix**
`backend/app/services/explore_gaps.py`, placed next to `_is_hygiene_wording`:
```python
# Plain words for each skill-gap category, for every surface that shows a row to
# a person: the Analytics "Skill gaps" panel, chat, and MCP agents. The keys are
# internal (gap_analysis._HINT_TO_CATEGORY values) and must never reach prose.
# Worded for a SURFACE row, so mirror_wording avoids the word "wording": that word
# belongs to the wording tier alone, and mirror_wording on an effective row is the
# adds_credit sibling, which has real headroom.
GAP_CATEGORY_LABELS: dict[str, str] = {
    "missing_skills": "no evidence on this resume",
    "mirror_wording": "exact token missing",
    "dual_place": "needs corroborating",
    "resurface_recent": "stale evidence",
    "adjacent": "adjacent skill",
}


def category_label(key: str | None) -> str | None:
    """Plain words for a gap category key. None when there is no category (wording
    rows) or the key is unknown (a legacy row): callers omit it, never show a key."""
    return GAP_CATEGORY_LABELS.get(key) if key else None
```
In `gap_frequency` (`:174-188`), turn the comprehension into a loop so `category` is computed once:
```python
    rows = []
    for skill, ids in job_ids.items():
        category = _most_common(categories[skill])
        rows.append({
            "skill": skill,
            "n_jobs": len(ids),
            "avg_potential_points": round(sum(points[skill]) / len(points[skill]), 1) if points[skill] else 0.0,
            "category": category,
            "category_label": category_label(category),
            "requirement_level": _most_common(req_levels[skill]),
            "low_sample": _low_sample(len(ids)),
        })
```
In `explore_build_areas.py`, import `category_label` alongside the existing `explore_gaps` imports (`:57-62`) and add
`"category_label": category_label(category),` after `"category": category,` (`:155`).

**Frontend fix**
- `frontend/lib/types.ts:848-860` `BuildAreaRow` and `:979-987` `GapFrequencyRow`: add
  ```ts
  /** Plain words for `category`, owned by the server. Absent on a backend that predates it. Render this, never `category`. */
  category_label?: string | null;
  ```
- `gap-tiers-panel.tsx`: delete `CATEGORY_LABEL` and its comment (`:45-57`). Move the "why no 'wording'" reasoning to the
  backend constant's comment, as above. Drop `BuildAreaCategory` from the import (`:11`) if nothing else uses it. Replace `:180-181` with
  `const categoryLabel = isSurface ? (row.category_label ?? null) : null;`. Keep the `BuildAreaCategory` type in `types.ts`,
  because it still types `category`.

**Agent-facing text** (all additive, and placed AFTER the tier content, so the conventions line "both docstrings LEAD with
`tier`" stays true):
- `server.py` `explore_gap_frequency` docstring. Insert before "Optionally filtered…":
  `Each row also carries category_label, the plain-words form of category (e.g. "needs corroborating"); in anything you tell the user, say category_label (and, on build_areas rows, the tier word), never a raw key such as dual_place or missing_skills.`
  That is about 250 chars, bringing it to about 1,190 of 2,000.
- `server.py` `get_job_search_brief` docstring. Change "build areas," to
  `build areas (per-skill tier plus category_label; speak those words, never the raw category key),`
  That is about 90 chars, bringing it to about 780 of 2,000.
- `chat_tools.py:643-645` spec. Replace the last two sentences with:
  `"... status is the raw KB-evidence key (missing/in_kb/ported) and does NOT on its own mean 'learn it' — read tier for that. category is the gap category key driving the row; category_label is the same in plain words. When you describe a row to the user, use the tier word and category_label, and say status in words (not in your Career KB / in your Career KB / ported before) — never a raw key like missing_skills, dual_place or in_kb. "`
  Chat specs have no length ratchet.
- `chat_system.txt:13`. Append: ` Speak plain words from those results (tier words, category_label), never internal keys.`
  This is reinforcement only, since it seeds once (see constraints).
- `docs/agentic-job-search.md:96-102`, the `build_areas` bullet: add "`category_label` is the plain-words reason; say that, not `category`."
- `docs/frontend-conventions.md:502-506` (Analytics bullet, "Additive fields `tier`…, `category`…"): add
  "`category_label` (server-owned plain words for `category`, `null` on wording rows; the panel renders it and holds no
  label map of its own)".
- Optional: `backend/mcp_server/README.md:335` table row. Mention `category_label`.

**Optional scope extension (decide in plan):** `status` keys (`in_kb`) leak the same way. The frontend `STATUS_META`
(gap-tiers-panel.tsx:24-43) also carries hint + chip classes, which are presentation. The chat wording above covers the
agent side without a new field. A server `status_label` would repeat the category pattern. It is not recommended now.

**Tests**
- Existing tests that touch these rows and stay green: `tests/test_explore_gaps.py` (e.g. `:209`
  `by_skill["kubernetes"]["category"] == "missing_skills"`, `:455`, `:517`), `tests/test_explore_build_areas.py` (`:315`
  wording row `category is None`, `:337`, `:364` `dual_place`, `:385`), `tests/test_chat_upgrades.py:160-228` (`:228` asserts
  `gaps == {"common_gaps": [], "build_areas": []}` on empty data, which still holds), `tests/test_job_search_brief.py:113`,
  `mcp_server/tests/test_client_coach.py:36`. No test asserts a whole row dict, so the added key breaks nothing.
- New:
  1. `test_explore_gaps.py::test_every_skill_gap_category_has_a_label`:
     `assert set(explore_gaps.GAP_CATEGORY_LABELS) == set(gap_analysis._HINT_TO_CATEGORY.values())`
     (a new skill category without a label fails here, not in chat prose).
  2. Extend `test_gap_frequency_ranks_by_distinct_jobs` (`:209`): `category_label == "no evidence on this resume"`.
  3. `test_explore_build_areas.py`: at the `dual_place` case (`:364`) assert `category_label == "needs corroborating"`; at the
     wording row (`:315`) assert `category_label is None`.
  4. `mcp_server/tests/test_server.py`: `assert "category_label" in srv.explore_gap_frequency.__doc__` and in
     `srv.get_job_search_brief.__doc__`. The budget ratchet runs automatically.
  5. `test_chat_upgrades.py`: the `analytics_gap_frequency` spec description in `chat_tools.TOOL_SPECS` contains `"category_label"`.

**Risks**
- MCP/chat contract: additive only. `explore_gap_frequency`/`build_areas` consumers that key on `category` keep working.
- Docstring budget: both stay under about 1,200 of 2,000.
- Prompt seeding: the prompt line alone would be invisible on existing installs. The tool description is the real carrier.
- `"no evidence on this resume"` reads slightly odd on a cross-job `gap_frequency` row ("this" = the best base per job).
  This brief keeps it, for zero UI churn. If the owner wants context-free wording ("no evidence on the resume"), change it
  in the ONE backend constant.

---

## 3. Analytics shows raw role slugs

**What the vocabulary actually offers (corrects the premise).** `other`/`unknown` DO have labels:
`backend/app/services/role_categories.py:34` `RESERVED = {OTHER: "Other", UNKNOWN: "Unknown"}`, `labels()` merges them
(`:213-215`), `label_for()` (`:251-270`) resolves categories, specific roles, and humanizes unknown keys, and
`GET /api/role-categories` (`routers/role_categories.py`) returns both reserved rows with `reserved: true`. The vocabulary has
25 declared categories (so more than 6 roles is realistic), with long labels ("IT Support / Systems Administrator").

**Two frontend helpers exist today.**
- `components/role-category-picker.tsx:29-46`: `useRoleCategories()` (the catalog, `staleTime` 1h) and pure
  `roleLabel(key, options?)` (catalog hit, else humanize). Used by `base-resume-gallery.tsx:52`.
- `lib/format.ts:12-26`: `roleCategoryLabel(key)`, a humanizer with a hard-coded `special` map (`ai_ml_engineer`,
  `bi_developer`, `mlops_engineer`, `other`, `unknown`). That is a partial second copy of the vocabulary, which its own comment
  says it avoids. Its only caller is `components/charts/role-mix-chart.tsx:20,63`.

**Every raw-slug render (the fix set)**
| Where | Current |
|---|---|
| `backend/app/services/explore_overview.py:76` | `"title": f"Best-paying track: {best['role_category']}"` |
| `frontend/app/analytics/page.tsx:116-126` | `SelectValue` `(v) => (v === ANY ? "any" : String(v ?? ""))`; `SelectItem` `{it}` (role filter shows slugs) |
| `frontend/components/charts/ats-over-time-chart.tsx:57-58,101-110` | series key `` `${row.role_category} · ${row.phase}` `` doubles as the legend name (no `name` prop); colours `COLORS[... % COLORS.length]` (`:50-51`) |
| `frontend/components/charts/tailoring-lift-chart.tsx:39,85` | `role: r.role_category` → `<XAxis dataKey="role" />` |
| `frontend/components/charts/role-mix-chart.tsx:58-68` | labelled via `roleCategoryLabel`, but colours cycle `i % COLORS.length` |
| `frontend/components/charts/heatmap-chart.tsx:70,86` | `<th>{role}</th>`, `title={`${skill} · ${role}: ${pct}%`}` |
| `frontend/components/explore/explore-overview.tsx:78-79,171` | `toBars(o.role_mix)` → `label: r.key` (slug) |
| `frontend/components/explore/explore-overview.tsx:277` | salary tile `{r.role_category}` |

`chart-kit.tsx:16-18` says the palette is a "fixed assignment order (never cycle or generate hues)". Every `% COLORS.length` breaks that.

**Fix: one label hook, used everywhere**
- `components/role-category-picker.tsx`: add next to `useRoleCategories`:
  ```ts
  /** key -> display label from the fetched catalog; humanizes while it loads or for a key it no longer has. */
  export function useRoleLabel() {
    const { data } = useRoleCategories();
    return useCallback((key: string | null | undefined) => roleLabel(key, data), [data]);
  }
  ```
  (Optional: move pure `roleLabel` into `lib/role-labels.ts` so `node --test` can cover it. Use only `import type` from `@/lib/types`,
  because Node's type-stripping erases type imports and does not resolve `@/`.)
- Delete `lib/format.ts` (the file holds only `roleCategoryLabel`). `role-mix-chart.tsx` switches to `useRoleLabel()`.
- `explore-overview.tsx`: `const label = useRoleLabel();` use
  `o.role_mix.map((r) => ({ label: label(r.key), count: r.count }))` for the role-mix card only (the other `toBars` callers
  are work mode/level/location/OPT, not roles), and `{label(r.role_category)}` at `:277`.
- `heatmap-chart.tsx`: `{label(role)}` in the `<th>` and the `title`. Long labels: drop `whitespace-nowrap` on the header
  `<th>` (`max-w-28 align-bottom`) so they wrap. The table already sits in `overflow-x-auto`.
- `tailoring-lift-chart.tsx:39`: `role: label(r.role_category)`. The "all" row is already filtered out.
- `app/analytics/page.tsx` `filterSelect` (`:100-127`): add a `format: (v: string) => string = (v) => v` parameter:
  ```tsx
  <SelectValue>{(v) => (v === ANY ? "Any" : format(String(v ?? "")))}</SelectValue>
  ...
  <SelectItem value={ANY}>Any</SelectItem>
  {items.map((it) => <SelectItem key={it} value={it}>{format(it)}</SelectItem>)}
  ```
  Pass `label` for the role filter only, and sort role options by label (`options.roles` sorts by slug at `:89`). The
  "Any" capitalization is item 4's nit, landed here.

**ATS-over-time series cap (decision: top N, the tail EXCLUDED, not averaged)**
- **N = 4 roles** (`MAX_ROLE_SERIES`). Each role draws two lines (base dashed, tailored solid), so that is 8 lines and 4 of the 6 hues,
  and colours never cycle. Rank roles by total `n` (score count) across all weeks and phases, with key asc on ties.
- **Why exclude rather than build an "Other" line.** (1) An "Other" weekly average pools unlike roles, so its level moves with the
  week's role *composition*, not with resume quality. That misleads on a trend chart even when weighted honestly
  (`sum(avg*n)/sum(n)`). (2) `other` is a real stored category whose label is "Other", so a synthetic "Other" series would collide with it in the
  legend. (3) The tail is always one click away: the Role category filter collapses the chart to that role's base/tailored lines
  (`singleRole`, `:44`).
- New pure module `frontend/lib/analytics-series.ts` (testable with `node --test`):
  ```ts
  /** Roles a multi-role line chart draws. Two lines per role (base dashed, tailored
   *  solid): 4 roles = 8 lines and 4 of CHART_COLORS' 6 hues, so colours never cycle. */
  export const MAX_ROLE_SERIES = 4;

  /** Rank roles by total weight, key asc on ties; split into drawn and hidden. */
  export function splitTopRoles<T>(
    rows: T[], roleOf: (r: T) => string, weightOf: (r: T) => number, max = MAX_ROLE_SERIES,
  ): { shown: string[]; hidden: string[] } {
    const totals = new Map<string, number>();
    for (const r of rows) totals.set(roleOf(r), (totals.get(roleOf(r)) ?? 0) + weightOf(r));
    const ranked = [...totals.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([role]) => role);
    return { shown: ranked.slice(0, max), hidden: ranked.slice(max) };
  }
  ```
- `ats-over-time-chart.tsx` `useMemo` (`:46-81`): when `!singleRole`, `const { shown, hidden } = splitTopRoles(data, r => r.role_category, r => r.n)`.
  Build weeks and series from `data.filter(r => shown.includes(r.role_category))`, `roleColor = (role) => COLORS[shown.indexOf(role)]`,
  and return `hidden`. Keep the dataKey slug-based (stable), but give each `<Line>` a
  `name={singleRole ? PHASE_LABEL[meta.phase] : `${label(meta.role)} · ${PHASE_LABEL[meta.phase]}`}` with
  `const PHASE_LABEL = { base: "Base", tailored: "Tailored" } as const`. Compute `anyLow` over the drawn rows. Caption (`:92-97`), appended:
  `hidden.length ? ` Showing the ${MAX_ROLE_SERIES} roles with the most scores. Pick a role category above to see the other ${hidden.length}.` : ""`
  (The filter row renders above the card grid on the `fit` tab, analytics/page.tsx:219.)
- `role-mix-chart.tsx` also cycles colours. Counts are additive, so here a tail bucket IS honest: reuse
  `splitTopRoles(data, r => r.role_category, r => r.count, 5)` and sum the hidden roles into one stacked series keyed `__more__`,
  named **"More roles"** (not "Other", which is the collision again). Five named roles plus one bucket uses exactly 6 hues. Dropping
  the tail here would make the stack under-report the weekly total.

**Backend insight**
`explore_overview.py:70-82`:
```python
from app.services import role_categories
...
    # Reserved buckets are not a "track": "Best-paying track: Unknown" says nothing.
    paid = [
        r for r in o["salary_by_role"]
        if r.get("avg_max") and r["role_category"] not in role_categories.RESERVED
    ]
    if paid:
        best = max(paid, key=lambda r: r["avg_max"])
        ...
            "title": f"Best-paying track: {role_categories.label_for(best['role_category'])}",
```
(`_salary_by_role_rows` coalesces a null role to `"unknown"`, `:137`, which is why the reserved filter matters.) The signals are
not read by MCP: `job_search_brief` uses `build_overview` for `role_mix`/`top_required_skills` only (`:180-181`).

**Tests**
- Existing: `tests/test_explore_router.py::test_overview_signals` (`:364-383`) asserts titles contain "OPT", "Texas", "Python", and
  `:273-274` asserts `salary_by_role` keys stay slugs (unchanged: labels are display-only). No frontend test pins chart code.
- New backend: `test_explore_router.py::test_best_paying_signal_uses_role_label`: two paid roles (e.g. `data_scientist` 150k,
  `ai_ml_engineer` 200k), and assert a signal titled `"Best-paying track: AI/ML Engineer"`. Variant: the top payer has
  `role_category=None` → no "Unknown" title, and the next role wins.
- New frontend: `frontend/lib/analytics-series.test.ts`: ranks by summed weight; key-asc tie-break; `shown.length <= max`;
  `hidden` gets the rest; `max >= roles` → `hidden` empty. If `roleLabel` moves to `lib/`, add `role-labels.test.ts`
  (catalog hit, unknown-key humanize, null → "Unknown").

**Risks**
- `useRoleLabel` renders humanized text (e.g. "Ai Ml Engineer") for the first paint until `/api/role-categories` resolves
  (cached for 1h afterwards). This is acceptable, and it is why `roleCategoryLabel`'s special map existed. Do NOT reintroduce the map.
- Keep series `dataKey`s on slugs. Only `name` (legend and tooltip) changes, so recharts' data joins are untouched.
- Out of scope but found in passing: the same page renders other raw enum keys (`work_mode` "onsite", OPT `yes`/`stem_opt_ok`/`unstated`,
  sponsorship keys via `toBars`, explore-overview.tsx:195,242,248). MCP `explore_*` tools also return role slugs with no
  `role_label`. Record these as a follow-up. Do not widen this item.

---

## 4. Copy nits

**4a. Stat tile labels are lowercase.** `frontend/components/explore/explore-overview.tsx:127-151` (the sibling
`analytics-overview.tsx:90-113` already uses sentence case):
| Line | Now | Proposed |
|---|---|---|
| 129 | `label="total JDs"` | `"Job descriptions"` |
| 131 | `` `since ${…}` `` | `` `Since ${…}` `` |
| 134 | `"role categories"` | `"Role categories"` |
| 138 | `"onsite"` | `"Onsite"` |
| 143 | `"avg yearly salary"` | `"Avg yearly salary"` |
| 119 | sub `"filter by currency"` | `"Filter by currency"` |
| 121 | sub `` `${n} disclosed · ${m} omit pay` `` | `` `${n} list pay · ${m} don't` `` |
| 122 | sub `"year only · omit is normal"` | `"Yearly pay only"` |

**4b. Analytics filter "any".** `app/analytics/page.tsx:117` and `:121` → `"Any"` (landed with item 3's `filterSelect` change).

**4c. "Needs you" in two colours.** `frontend/components/status-chip.tsx:117-118`:
```ts
needs_decision: { label: "Needs you", className: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
needs_human:    { label: "Needs you", className: "bg-orange-500/10 text-orange-700 dark:text-orange-400" },
```
**Decision: orange for both,** defined once so they cannot drift:
```ts
// needs_decision and needs_human are ONE state to the user ("Needs you"), so they
// share one object: one label, one colour. Orange, not amber: amber is the
// application chip's "Interviewing", which sits in the same tracker column.
const NEEDS_YOU = { label: "Needs you", className: "bg-orange-500/10 text-orange-700 dark:text-orange-400" };
...
  needs_decision: NEEDS_YOU,
  needs_human: NEEDS_YOU,
```
Rationale: `SavedJobChip` (`:134-147`) renders these in the tracker next to `StatusChip`'s `interviewing` amber (`:30-33`).
Orange also matches `submission_uncertain` (`:122`), the other "you must check" state. No test pins these classes.

**4d. Templates subtitle.** `frontend/app/templates/page.tsx:172`: `subtitle="Templates used to render resumes."` →
`subtitle="The look of the PDF."`

**4e. Backend insight copy** (`backend/app/services/explore_overview.py:43-102`). These are UI copy (rendered by `explore-overview.tsx:154-163`),
so the microcopy rules apply: no em-dash clause joiners, no jargon.
| Line | Now | Proposed |
|---|---|---|
| 53 | `"{accept} of {total} say yes or STEM-OPT; the rest are 'no' or unstated."` | `f"{accept} of {total} accept OPT or STEM OPT. The rest say no or don't say."` |
| 60 | `"Highest concentration of JDs by location."` | `"More JDs name this location than any other."` |
| 67 | `f"Most-required skill — {s['n']} of {total} JDs."` | `f"Required in {s['n']} of {total} JDs, more than any other skill."` |
| 78-80 | `f"~{k}k{cur_bit} avg max across {n} disclosed JDs."` | `f"Average top of the pay range: about {k}k{cur_bit}, from {n} JDs that list pay."` |
| 88-89 | `f"{without} of {total} omit pay numbers — normal (~40%+ US / ~88% DE; IL may only hyperlink a pay page)."` | `f"{without} of {total} leave pay out. That is common, so it is not a red flag."` |
Drop the unsourced percentages and the "IL"/"DE" abbreviations. If the owner wants the jurisdiction fact kept, spell it out
and source it (Illinois lets an employer link to pay details instead of listing them). Keep the words OPT, the location
and the skill name in the TITLES (test_overview_signals pins them).

**Tests**
- No test pins any of these strings (`grep` over `backend/tests`, `mcp_server/tests`, `frontend/lib/*.test.ts`). The OPT/Texas/Python title pins survive.
- New: `test_explore_router.py::test_overview_signal_copy_has_no_em_dash`, which asserts `"—"` appears in no signal `title`/`detail`
  (use the `test_overview_signals` fixture plus a paid job, so every branch fires).

---

## 5. Referrals form always on the page

**Where.** `frontend/app/referrals/page.tsx:32-42` renders `<CreateReferralCard />` (`:44-161`, an always-open 4-field form card)
above `<ReferralsTableCard />` (`:163-208`). The empty state (`:176-183`) says "Add a company **above** where someone can refer you."
Pre-existing defects in the same file:
- The error branch (`:173-176`) is a bare `<p className="text-destructive">`, not `LoadErrorState`. That breaks the conventions'
  "a failed fetch is a THIRD state" rule, and the page is missing from `tests/test_frontend_query_error_states.py` `_QUERY_SURFACES`.
- Optional suffix is hand-rolled (`:125-129`, `:139-143`) instead of `<Label optional>` (`components/ui/label.tsx`).
- Field rows use `space-y-1.5` (`:98`, `:109`, `:121`, `:136`). The convention is `grid gap-1.5`.

**Decision: dialog when populated, inline form when empty.** Precedent: Career KB's header "New entity" → `NewEntityDialog`
(`app/career/page.tsx:78-83`, `components/career/new-entity-dialog.tsx`). Conventions that apply: `DialogContent` owns
max-height, initial focus is Base UI's `initialFocus` (not `autoFocus`; see `confirm-dialog.tsx:73-84`,
`merge-entity-dialog.tsx:146-151`), and delete stays behind `useConfirm` (`:227-237`, unchanged).

**Shape**
```tsx
export default function ReferralsPage() {
  const referrals = useQuery({ queryKey: REFERRALS_KEY, queryFn: () => apiFetch<Referral[]>("/api/referrals") });
  const [addOpen, setAddOpen] = useState(false);
  const rows = referrals.data ?? [];
  const populated = !referrals.isLoading && !referrals.isError && rows.length > 0;
  return (
    <PageShell>
      <PageHeader title="Referrals" subtitle="Companies where someone can refer you."
        actions={populated ? <Button onClick={() => setAddOpen(true)}><Plus aria-hidden="true" /> Add referral</Button> : undefined} />
      {referrals.isLoading ? <Skeleton className="h-40 w-full" />
        : referrals.isError ? <LoadErrorState title="Couldn't load referrals." detail={(referrals.error as Error).message}
                                retrying={referrals.isFetching} onRetry={() => void referrals.refetch()} />
        : populated ? <ReferralsTable rows={rows} />
        : <FirstReferralCard />}            {/* the form IS the page */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent initialFocus={companyRef}>
          <DialogHeader><DialogTitle>Add referral</DialogTitle></DialogHeader>
          <ReferralForm companyRef={companyRef} onCreated={() => setAddOpen(false)} />
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
```
- `ReferralForm` = today's form body and mutation (`:44-160`), with `onCreated` and an optional ref, `<Label optional>`, `grid gap-1.5` rows,
  and the submit button inside `DialogFooter` when in the dialog.
- `FirstReferralCard` = a `Card` titled "Add your first referral", one line of description ("A company where someone can refer you."),
  then `<ReferralForm />`. Keep the `Handshake` icon if wanted. The "above" wording disappears.
- `ReferralsTable` = today's `TableFrame`/`Table` (`:184-205`) with `ReferralRow`/`ReferralViewRow`/`ReferralEditRow` unchanged.

**Tests**
- Add `("app/referrals/page.tsx", "Add your first referral")` to `_QUERY_SURFACES` in `tests/test_frontend_query_error_states.py`
  (its regex accepts `referrals.isError ?`, and the error branch must precede the marker).
- Optional source pin: the page imports `Dialog` and still uses `useConfirm` for delete.

**Risks**
- Focus: after the FIRST create, the inline form unmounts and the table and header button mount, so focus drops to `<body>`
  (the same class as the honest-studio follow-ups). Move focus to the new header "Add referral" button, or to the first table row, in
  `onCreated` for the inline case. After a dialog create, Base UI restores focus to the trigger.
- The header button is hidden while loading or errored on purpose (it cannot know the state). Do not show a create action beside
  a `LoadErrorState`.
- Browser-verify at 768px (conventions: the worst band) and 375px (dialog fit).

---

## 6. Template thumbnails show a synthetic résumé without saying so

**Where.** `frontend/components/templates/template-thumbnail.tsx:43-56` passes `PreviewThumbnail` a `chip` only when stale
("needs re-validation"). `frontend/components/gallery/preview-thumbnail.tsx:37-43` (props) and `:76-86` (the chip renders
**bottom-left**, `absolute bottom-1.5 left-1.5`, only while `showImage`). The sample data is
`backend/app/services/template_validation.py:23` (`"name": "Jordan Sample"`, also the parse probe at `:153`). Consumers:
`/templates` (manage mode, `template-gallery.tsx:154-164`, stretched link) and the template picker dialog
(`template-select.tsx:155-206`, select mode, reached from both studios). There the user can easily take the image for their own
résumé rendered in that look. Corner map: the default star is top-left (`template-gallery.tsx:80-88`, on the card), actions sit in the
card header's bottom-right row, the stale chip is bottom-left, and **the image's top-right is free**.

**Gallery convention to update.** `docs/frontend-conventions.md:307-315`: "A gallery supplies only what differs: preview URL,
empty-state wording, optional corner chip, card body." A second slot is a shell change and must be recorded there.

**Fix**
`preview-thumbnail.tsx`, new prop plus render:
```ts
  /** Persistent top-right marker for what the image IS (e.g. "Sample"). `chip`
   *  reports a degraded STATE bottom-left; both can show at once. */
  mark?: string;
...
      {showImage && mark && (
        <span
          aria-hidden="true"   // the alt text carries it for AT
          className="bg-background/90 text-muted-foreground absolute top-1.5 right-1.5 rounded px-1.5 py-0.5 text-[10px] font-medium backdrop-blur"
        >
          {mark}
        </span>
      )}
```
`template-thumbnail.tsx`: `mark="Sample"` and
`alt={`${template.display_name ?? template.id} preview, rendered with a sample resume`}`. Only when the image shows: the
"Not validated" placeholder is not a sample. Base-resume thumbnails (real user data) pass no mark.
Optional: `template-select.tsx:163` add `<DialogDescription>Previews show a sample resume, not yours.</DialogDescription>`.

**Tests.** None touch these components (`test_kb_sync_frontend.py:192` reads `gallery-card.tsx` only). Optional source pin:
`template-thumbnail.tsx` passes `mark=` and the alt mentions "sample".

**Risks / found in passing**
- The mark must be self-explanatory WITHOUT a tooltip. On `/templates` the card's stretched link (`gallery-card.tsx:55-61`,
  `absolute inset-0 z-10`) paints above the thumbnail, so the existing stale chip's `title` explanation is very likely
  unreachable by hover in manage mode. Verify in the browser pass. If confirmed, record it as a follow-up; do not fix it here.
- 10px text: `text-muted-foreground` on `bg-background/90` matches the existing chip, so contrast is no worse than today.

---

## 7. Orphan route `/applications/[id]/health`

**Where.** `frontend/app/applications/[id]/health/page.tsx` (20 lines) renders
`<HealthReportPage kind="application" resumeKey={id} backHref={`/applications/${id}/resume`} …/>`. Nothing links to it:
`grep` finds `/health` links only to `/base-resumes/${slug}/health` (`health-badges.tsx:148`, `editor-body.tsx:349`).
`components/resume-editor/studio-toolbar.tsx:19-21` states the design: "a tailored resume's health score is inherited from its base,
so the tailored studio checks structure through the post-tailoring review instead". There are no backend- or extension-generated
links to it.

**Every caller of the application-kind resume-lint API**
| Surface | Caller | Application kind used? |
|---|---|---|
| Frontend | `lib/api.ts:668-770` (`getLintReport`, `runLintReport`, `waiveGate`, `unwaiveGate`, `answerAsk`, `getAskAnswers`, `draftRewrite`) take `kind: "base" \| "application"` | Only via `HealthReportPage` props, which only the orphan route sets to `"application"` |
| Frontend | `components/resume-health/health-report-page.tsx:77,97-133,242,252-254` (app query, `ApplicationDetail`, `resumeDataSchema` parse, job label, `["application"]` invalidation, "Couldn't load this application.") | Only for the orphan route |
| Frontend | `health-badges.tsx:46-56` `HealthBadges kind` | Its sole caller passes `"base"` (`editor-body.tsx:346-350`) |
| Frontend | `finding-cards.tsx`, `batch-ask-dialog.tsx`, `demonstrate-skill-dialog.tsx` `kind` props | Threaded from `HealthReportPage` |
| Backend | `routers/resume_lint.py:26` `Kind = Literal["base","application"]`, `_load_resume` (`:159`), all `/{kind}/{key}/…` routes | Serves both |
| Backend services | `tailoring_session.py:160,184` and `explore_base_summaries.py:120` read `"base"` only | No |
| **MCP** | `server.py:232-274` `run_health_check`, `get_health_report`, `waive_health_gate`, `unwaive_health_gate` document `kind='application'`; `client.py:527-541` | **Yes: public surface** (SYSTEM.md §7 "health (run/get + waivers)") |
| Chat | `chat_tools.py` has no lint tool | No |
| Extension | none | No |

**Recommendation: delete the route; keep every backend endpoint** (MCP exposes application-kind health, so the REST
surface is live even with no web page).

**Deletion set**
1. Delete `frontend/app/applications/[id]/health/page.tsx` (and the empty `health/` dir).
2. `components/resume-health/health-report-page.tsx`: narrow to base. Drop the `kind` prop (set `const kind = "base" as const`
   inside, so the child call sites stay untouched), and delete `appQuery` (`:102-106`), the `ApplicationDetail` import (`:51`), the
   `resumeDataSchema` import (`:48`, used only by the application branch at `:113`), the application branches of `resumeData`/
   `templateId`/`label` (`:109-133`), `qc.invalidateQueries({ queryKey: ["application"] })` (`:242`) and the
   "Couldn't load this application." arm (`:252-254`). Update `app/base-resumes/[slug]/health/page.tsx` to stop passing `kind`.
3. Leave the `kind: "base" | "application"` unions in `lib/api.ts` and the child components. They mirror the REST API and are
   shared with `applyResumeEdits`. Narrowing them is churn with no behaviour change.
4. `studio-toolbar.tsx:19-21`: optionally append "There is no application health page; MCP's health tools still accept
   kind='application'."

**Tests.** No test references the route. The `health-report-page.tsx` pins (`test_frontend_health_report.py:13-91`,
`test_frontend_color_roles.py:28,220-221`, `test_frontend_query_error_states.py:80` "No health report yet.") are all
base-path strings, and survive. Backend lint tests never exercise `application` (`grep` for `resume-lint/application`
finds nothing). Optional: add one router test for `GET /api/resume-lint/application/{id}` 404-without-report, since MCP depends on that path.

**Risks.** A bookmarked URL now hits `app/not-found.tsx`. That is acceptable, because nothing linked to it. The slop ratchet's orphan LOC
should go DOWN (a good event). Do not remove the `Kind` literal or the MCP docstring wording.

---

## 8. Placeholder convention conflicts with its cited source

**The conflict (verified).** `docs/frontend-conventions.md:365-370` ("placeholders are example values only") and `:388-397`
(Microcopy rules, sourced to "GOV.UK Design System text-input guidance, NN/g": "*Placeholder*: an example VALUE (`e.g. Acme Corp`)").
GOV.UK's text-input page says, under "Avoid placeholder text": "Do not use placeholder text in place of a label, or for hints
or examples". Its reasons: the text vanishes on typing, not all screen readers read it, and default styles fail WCAG 1.4.3. NN/g
("Placeholders in Form Fields Are Harmful") also says to keep hints and instructions outside the field, with minimal relief only for one-
or two-field forms such as search or login.

**Inventory: all 75 `placeholder=` hits in `frontend/` (app, components, lib), plus data-driven values.**
Classes: **E** example value · **S** statement about the field (default, state, what belongs there) · **I** instruction/prompt ·
**L** restates the label · **N/A** not a text-input placeholder.

| File:line | Text | Class | Note |
|---|---|---|---|
| app/referrals/page.tsx:104 / :115 / :130 / :145 | `Acme Corp` / `https://example.com/careers` / `Jane Doe` / `Met at the AWS meetup` | E | no `e.g.` prefix |
| app/referrals/page.tsx:369 / :378 | `Jane Doe` / `Met at the AWS meetup` | E | table edit row, aria-label only |
| app/base-resumes/page.tsx:241 | `Data Scientist (1 page)` | E | |
| app/new/page.tsx:121 | `https://boards.example.com/job/123` | E | |
| app/applications/page.tsx:420 | `Search company or role…` | I | search box (NN/g exception), aria-label present |
| app/templates/page.tsx:272 | `classic_serif` | E | slug constraint shows only on error (`:277-281`), and it belongs in a hint |
| app/jobs/[id]/tailor/[sessionId]/page.tsx:675 | `e.g. emphasize leadership, keep it to one page, …` | E | |
| components/role-picker.tsx:396 | `Search roles, or type your own…` | I | combobox search |
| components/role-category-picker.tsx:153 | `Set role…` | I | the only visible text of an empty header control |
| components/job-tracking-url-field.tsx:87 | `https://…` | E | its `description` renders BELOW the control, unwired (`:93-95`) |
| components/qa-tab.tsx:156 | `One question per line…` | I | a constraint needed while typing; aria-label only |
| components/ui/chip-input.tsx:20,176 (default `Add…`); callers profile-panel.tsx:198 `Add skills…`, skills-editor.tsx:70 `Add skill…`, editor-body.tsx:663 & tailored-resume-studio.tsx:940 `Add certification…`, education-editor.tsx:153 `Add course…` | | I | add-row prompt inside a labelled chip list |
| components/settings/job-preferences-section.tsx:159 / :214 / :237 | `e.g. 6` / `e.g. Chicago, IL⏎New York, NY` / `e.g. $140,000` | E | hint "One location per line." sits below the control, unwired (`:228`) |
| components/settings/models-section.tsx:313 | `Saved · type to replace` (configured) | S+I | the status is already shown beside the label (`:297-306`) |
| components/settings/models-section.tsx:228/237 via :313 | `sk-...` / `AIza...` | E | key prefix format |
| components/settings/models-section.tsx:384 | `llama3.2:3b` | E | |
| components/settings/llm-endpoint.tsx:84 | `http://host.docker.internal:11434/v1` | E | |
| components/career/merge-entity-dialog.tsx:171 | `Search by title…` | I | filter box, aria-label present |
| components/settings/persona-section.tsx:15-21,137 | multi-line `e.g. Vision: … Strengths: … Goals: … How I work: …` | E | structural example |
| components/settings/quick-tailor-section.tsx:121 | `e.g. keep bullets under two lines` | E | |
| components/resume-health/finding-cards.tsx:244 / :1160 | `e.g. this metric lives in the next bullet` / `e.g. this template is certified elsewhere` | E | |
| components/settings/auto-apply-section.tsx:197 | `e.g. Acme Corp` | E | |
| components/settings/autofill-section.tsx:70,166,215,216,225,247-251 (via :830/:861) | `e.g. Apt 4B`, `e.g. Asian`, `e.g. $120,000`, `e.g. 2 weeks`, `e.g. Job board`, `e.g. Master of Science`, `e.g. Data Science`, `e.g. 3.8`, `e.g. 2021`, `e.g. 2023` | E | |
| components/settings/autofill-section.tsx:902 | `e.g. Why do you want to work here?` | E | |
| components/settings/autofill-section.tsx:916 | `Answer` | L | aria-label "Answer to custom question N" |
| components/career/profile-panel.tsx:185 | `ML Ops` | E | |
| components/career/profile-panel.tsx:225 | `Visa timeline, target roles, location constraints, and other private context…` | S | says what belongs, so it is a hint |
| components/career/capture-box.tsx:139 | `This week I shipped…` | E | sentence starter; label is sr-only but a card title and description are visible |
| components/career/notes-editor.tsx:152 | `Stack, scale, constraints, collaborators, and what you personally owned…` | S | hint; label is sr-only |
| components/career/new-entity-dialog.tsx:220 | `e.g. Publications, Volunteer Work` | E | |
| components/career/new-entity-dialog.tsx:281-287 | `e.g. Paper Title or Role` / `Project name` / `Role or title` | S / L / L | |
| components/career/new-entity-dialog.tsx:303-307 | `Conference, publisher, or org` / `Company, institution, or issuer` | S | |
| components/career/new-entity-dialog.tsx:321 / :333 | `Jan 2025` / `Present` | E / S | a KB entity's status select governs "ongoing" |
| components/career/entity-detail.tsx:292 / :304 / :316 | `Acme Labs` / `Jan 2025` / `Present` | E / E / S | |
| components/resume-editor/experience-editor.tsx:126 / :132 | `Jan 2023` / `Present` | E / S | an empty end date renders "Present" (resume.tex.j2:104; typst_classic.typ:62,94 `ongoing: true`), so this states a DEFAULT |
| components/resume-editor/extra-sections-editor.tsx:389 / :396 / :484 | `2025` / `https://…` / `Publications` | E | |
| components/resume-editor/contact-form.tsx:21 (via :56) | `you@example.com` | E | |
| components/resume-editor/instruct-sheet.tsx:121 | `e.g. Tighten the summary and lead with the platform work` | E | |
| components/resume-health/demonstrate-skill-dialog.tsx:205 | `How ${skill} shows up here` | L | the same words as its aria-label; no visible label |
| components/resume-health/metric-ask-input.tsx:95 / :122 / :131 | `5,000` / `unit` / `6 months` | E / L / E | `unit` restates aria-label "Custom unit" |
| components/base-resumes/new-base-resume-dialog.tsx:438 | `Defaults to the file name` (file mode) / `Machine Learning Engineer` | S / E | a default belongs in a hint |
| components/base-resumes/new-base-resume-dialog.tsx:495 | `e.g. Lead with production ML work, senior in tone` | E | |
| components/gap-analysis/gap-card.tsx:697-701 | `Draft your JD-aligned value proposition. This becomes your summary.` | I+S | instruction plus consequence |
| components/gap-analysis/resolution-controls.tsx:430 | `Exact wording to add` | L/I | label is "Wording" (`:422-424`) |
| components/gap-analysis/resolution-controls.tsx:442 (default) | `e.g. Built the ingestion pipeline in Python and Airflow` | E | |
| components/proposals/triage-actions.tsx:189 | `e.g. hiring freeze announced` | E | |
| components/proposals/proposals-section.tsx:474 | `e.g. 50` | E | |
| components/chat/chat-page.tsx:469 | `Ask about your resume…` | I | single-field composer (NN/g exception), aria-label "Message" |
| components/application-panel.tsx:210; settings/autofill-section.tsx:813; base-resumes/new-base-resume-dialog.tsx:604; resume-editor/project-port-dialog.tsx:114 | `None` / `—` / `Choose a base resume` / `Choose base resume` | N/A | `SelectValue` empty text, not a text input |
| gallery/preview-thumbnail.tsx via base-resume-thumbnail.tsx:39, template-thumbnail.tsx:46 | `Not rendered yet` / `Not validated` | N/A | image-placeholder prop |
| resume-editor/field.tsx:41, contact-form.tsx:56, resolution-controls.tsx:474, chip-input.tsx:176, role-picker.tsx:134 | pass-through | N/A | |

Tally (text-input placeholders): about 45 **E**, 8 **S**, 12 **I** (5 search/composer/filter, 6 chip add-rows, 1 constraint),
5 **L**. No test pins any placeholder string. `test_autofill_groups_parity.py` regex-parses the autofill `GROUPS`
block (`:44-60`), so do NOT reformat that array's `key/title/fields` header lines if you touch its field objects.

**Options**
- **A. Follow the sources:** move every example into hint text ("For example, Acme Corp") between the label and the control, wired with
  `aria-describedby`. Cost: about 45 fields across about 20 files gain a line each, including dense entry cards (date pairs,
  metric-ask inline inputs, table edit rows, chip lists). That works against the owner's density work, and GOV.UK's own merge example
  concedes internal expert users (docs/ux research, R6).
- **B. Record a deliberate, scoped deviation** (recommended), and fix everything that breaks even the house rule.

**Recommendation: B.** GOV.UK's three reasons, checked against this app:
(1) *Contrast* does not apply. Placeholders use `placeholder:text-muted-foreground` in `ui/input.tsx:12`, `ui/textarea.tsx:10`,
`chip-input.tsx:177` and `role-picker.tsx:407-408`, and `--muted-foreground` (oklch 0.505) on `--background` (0.976) is about 5.4:1 (dark about
5.8:1). (2) and (3), *vanishing* and *screen readers*, are harmless exactly when the placeholder carries nothing the user needs, so
make that the rule. The house rule already bans the harmful classes. The honest fix is to say we deviate, say why, and enforce the
boundary.

**Proposed conventions text**
- `:365-370` Form conventions: replace "placeholders are example values only" with "a placeholder may hold only an example value
  (see Microcopy rules)".
- `:394-397` Microcopy, *Placeholder*:
  > *Placeholder*: an example VALUE prefixed `e.g.` (`e.g. Acme Corp`), and only when losing it costs nothing. A visible label (or,
  > for a search box, the chat composer or a chip add-row, a named control) already says what the field is. Anything needed while
  > typing, such as a format, a constraint, a default or a consequence, is hint text. Instructions, questions, statements about the
  > field and label restatements are never placeholders. **This deviates from GOV.UK on purpose:** its text-input guidance
  > forbids placeholders for examples too, because they vanish on typing, not every screen reader reads them, and default styles
  > fail contrast. Here placeholders use `--muted-foreground` (≥4.5:1, pinned), and an example that carries nothing needed is safe
  > to lose. NN/g's exception for one- and two-field forms (search) covers the search boxes and the composer.

**Code fixes under B** (every S/L, plus the one I that is a constraint):
| Field | Change |
|---|---|
| qa-tab.tsx:156 | add hint `<p id>` "One question per line." with `aria-describedby`; placeholder `e.g. Why this team?` or none |
| models-section.tsx:313 | configured → no placeholder, and hint "Type a new key to replace the saved one." (the status is already beside the label) |
| new-base-resume-dialog.tsx:438 (file mode) | hint "Defaults to the file name."; no placeholder |
| gap-card.tsx:697 | summary placeholder → an example (`e.g. Data scientist who ships forecasting models to production`); "This becomes your summary." joins the hint line resolution-controls.tsx:466-467 already renders (add a `hint` prop) |
| resolution-controls.tsx:430 | label "Exact wording"; placeholder `e.g. PySpark` or none |
| demonstrate-skill-dialog.tsx:205 | visible `<Label>` "How {skill} shows up in this bullet"; drop placeholder |
| metric-ask-input.tsx:122 | `e.g. users` |
| autofill-section.tsx:916 | drop `Answer` |
| new-entity-dialog.tsx:281-287, :303-307 | examples (`e.g. Senior Data Scientist`, `e.g. Fraud detection pipeline`, `e.g. Best Paper Award`, `e.g. Acme Corp`, `e.g. NeurIPS 2024`) |
| profile-panel.tsx:225, notes-editor.tsx:152 | move the text to a wired hint ("Private context such as visa timeline, target roles, location constraints." / "Stack, scale, constraints, collaborators, and what you owned."); keep or drop the placeholder |
| experience-editor.tsx:132 | placeholder `e.g. Mar 2025`, hint "Leave empty for a current role." (true in both engines for experience) |
| new-entity-dialog.tsx:333, entity-detail.tsx:316 | `Present` → `e.g. Mar 2025` (KB status, not an empty date, means ongoing) |
| templates/page.tsx:272 | `e.g. classic_serif`, and the slug rule becomes an always-visible hint (keep the error text) |
| bare examples (referrals ×6, base-resumes:241, new:121, profile-panel:185, entity-detail:292/304, new-entity-dialog:321, experience-editor:126, extra-sections ×3, metric-ask:95/131, models:384, llm-endpoint:84, contact-form:21) | add the `e.g.` prefix (it keeps a placeholder from reading as a pre-filled value). For URL format cues (`https://…`), keep as is. |
Also wire the two hints that sit below their control and unwired (job-preferences-section.tsx:228; job-tracking-url-field.tsx:93-95):
move them between the label and the control with `aria-describedby` (conventions "Hint text sits between the label and the control").

**Tests (new)**
- `tests/test_frontend_color_roles.py`: add `--muted-foreground` on `--background` (and on `--card`) ≥4.5:1 in both modes. This is the pin the new
  doc text cites.
- Optional ratchet `tests/test_frontend_placeholders.py`: scan `frontend/{app,components}` `placeholder="…"` string literals.
  Allow `e.g. `, `https://`, `…`-ending add-row/search prompts from a small allowlist (the search/composer/chip add-row files), and
  fail on anything else. This keeps the deviation scoped as code grows.

**Risks.** Option B changes about 20 files, mostly one-liners. Keep hints one short sentence (Microcopy *Hint* rule), and do not
add a hint that restates the label. Browser-check the entry cards for height growth at 768px.

---

## Doc updates checklist (same change as the code)
- `docs/frontend-conventions.md`: Analytics bullet (item 2 `category_label`; item 3 "role slugs never render raw, all analytics
  labels go through `useRoleLabel()`; multi-role line charts cap at `MAX_ROLE_SERIES` and name the hidden count; stacked counts sum the
  tail into 'More roles'"); Card galleries bullet (item 6 `mark` slot, top-right, and what it is for); Form conventions and Microcopy
  (item 8); Naming bullet optional (proposal "Needs you" is one colour).
- `docs/agentic-job-search.md:96-102` (item 2).
- SYSTEM.md: none required. §7's MCP paragraph already says the docstring is the API. Optionally mention `category_label` next to
  "`analytics_gap_frequency` incl. build-areas" (§7, line 551). Run `scripts/check_system_md.py`.
- §11/§12 candidates for the session log: the prompt-seed-once trap is already in §7. Add a §11 item for the out-of-scope raw enum
  keys on Job market (item 3 risks) and for MCP `explore_*` returning role slugs with no labels.
