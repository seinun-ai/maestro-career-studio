> **Appendix A1 (studio correctness) to `docs/plans/2026-09-22-ux-followups.md`.** Research brief written read-only
> against `a3c800bb`; each task in the plan names the section it uses. Where this appendix offers
> options, the plan's "Owner decisions" section is binding. Line numbers drift: re-locate before editing.

# Phase A1 — studio correctness: implementation brief

Worktree `.claude/worktrees/seinun-resume-update-45a8c0`,
branch `claude/ux-followups` at `a3c800bb`. All paths below are relative to that root. Line numbers
are at `a3c800bb`.

## 0. Read this first

**Four findings change the directions in the ask:**

1. **A plain `JSON.stringify` savedKey breaks the normal content save** (item 1). The
   `["application", id]` cache is structurally shared (TanStack default, not turned off in
   `frontend/app/providers.tsx`). `replaceEqualDeep` keeps the OLD object, **with its old key
   order**, for every subtree whose content is unchanged. The PATCH response is raw, and the backend
   rewrites key order on PATCH (`ResumeData.model_validate(...).model_dump(mode="json")`,
   `backend/app/routers/applications.py:326-339`). Other paths store other orders:
   - materialize stores the base file as-is (`applications.py:458`, `base_resume_data.py:82`);
   - `apply_edits` keeps the input order;
   - **drafts migrated from Postgres are in JSONB key order** (SYSTEM.md §13 `postgres-to-sqlite`).

   So the first studio Save after a Build draft, an MCP edit or the migration yields
   `JSON.stringify(cache) !== JSON.stringify(response)`. The user's own Save would then read as a
   foreign edit and show the banner. I checked this with `@tanstack/query-core@5.99.2` in this repo
   (plain-stringify keys: false; sorted-key keys: true). **Fix: compare by a sorted-key
   `serverKey()` on both sides.**
2. **The remount is the root cause of items 2 and 3.** It also resets things nobody listed. A
   content Save remounts `StudioEditor`, and with it `EditorShell`, which causes all of these:
   - the section tab jumps back to Contact (`<Tabs defaultValue="contact">`, :865);
   - the Formatting panel closes (`fmtOpen` in `editor-shell.tsx:62`);
   - the editor pane scrolls back to the top;
   - the preview width shows the default for a frame, then jumps to the stored width
     (`editor-shell.tsx:63-80`, hydrated after mount);
   - raw-JSON mode, the Review toggle and coherence results reset;
   - the status live region remounts.

   **Recommended design: our own Save moves the editor's baseline IN PLACE (no remount). Only a
   foreign copy that replaces the content remounts.** That fixes items 2 and 3 and all of the above
   in one change. It is smaller than the alternatives once item 3 is included (see item 2).
3. **The base studio has a worse twin of item 2.** Base `PUT` renders inline
   (`backend/app/routers/base_resumes.py`, `update_base_resume` → `render_base_resume`), so
   `save.isPending` lasts the whole LaTeX compile. The form stays editable, and on success
   `adoptBaseResumeDetail(result)` (`editor-body.tsx:215`) overwrites every edit typed during it.
   The status reads "Saving…" throughout, then "All changes saved", so the loss is silent.
4. **Rebuild from base while dirty shows the banner instead of replacing the editor**
   (pre-existing). `onRebuild` (:300) arms nothing, so the materialized key is treated as foreign,
   and a dirty editor gets "This draft changed outside the editor". The confirm had already said
   "erases … any unsaved edits". This is a one-line addition to the same adoption decision (item 1).

**Order:** do items 1+2+3 as one task (one design). Item 4 builds on the `dirty`/`unsaved`
definitions from that task. Items 5, 6 and 7 are independent (item 6 is a two-line change once
`unsaved` exists).

## Global constraints (read before writing any step)

- **Lint (`npm run lint`) has the React Compiler rules at error level**:
  `react-hooks/refs` (no `ref.current` read during render), `react-hooks/set-state-in-effect`,
  `react-hooks/set-state-in-render`. I probed them via
  `eslint --stdin --stdin-filename components/__probe.tsx`:
  - a conditional `setX` in an effect with no ref access → **error**;
  - the same with a ref read in the effect (today's tailored adoption effect) → passes;
  - `ref.current` in render → **error**;
  - React's documented "adjust state while rendering on prop change" pattern
    (`if (value !== prev) { setPrev(value); … }`) → passes.

  The repo silences the rule only with a reason comment (`editor-shell.tsx:70`). **Run lint after
  every step.** Prefer event handlers over effects for new setState.
- **Frontend slop ratchet has zero duplication headroom (518/518)**
  (`docs/plans/2026-09-22-honest-studio.md`, Out of scope). Any logic added to BOTH studios must go
  through a shared helper or hook, or jscpd flags a new clone. Run
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` (and name the
  surface in the claim, SYSTEM.md "Slop ratchet").
- **Node unit tests are not in CI.** Run `cd frontend && node --test lib/*.test.ts` (40/40 at
  baseline). `lib/*.ts` files import only relative paths or bare packages (no `@/`), so new pure
  helpers belong in `lib/studio.ts` / `lib/formatting.ts`. A test may import `zod` and
  `@tanstack/query-core` from `node_modules` (verified).
- **Source pins**: `cd backend && pytest tests/test_frontend_studio.py tests/test_frontend_first_run.py
  tests/test_frontend_query_error_states.py tests/test_formatting_parity.py
  tests/test_kb_sync_frontend.py tests/test_frontend_color_roles.py -q`. The ones affected are
  listed per item.
- **Docs contract**: rewrite (do not append to) the SYSTEM.md §12 bullet "Studio external-edit
  dirty-guard" (`SYSTEM.md:896-898`). Rewrite the `docs/frontend-conventions.md` "honest studio"
  sub-bullets *Tailored studio* (:140-145) and *Cmd/Ctrl+S* (:114-125), and add a *Raw JSON*
  sub-bullet. Add one dated §12 gotcha for finding 1 (structural sharing keeps the old key order in
  subtrees whose content is unchanged). Run `python3 scripts/check_system_md.py`. Delete the
  shipped items from the follow-ups list in `docs/plans/2026-09-22-honest-studio.md:1959-1990`
  (or leave that plan frozen and track them in the new plan; the planner decides).

---

## Item 1 — Tailored adoption guard (HIGH PRIORITY)

### Locations
- `frontend/components/resume-editor/tailored-resume-studio.tsx`
  - :186-189 `customizedKey`
  - :191-212 adoption state + effect
  - :214-227 `parseResumeData` (inline arrow) / `adoptedData` / `serverChanged`
  - :229-241 `materialize`
  - :290-313 `<StudioEditor key={adoptedKey} … onLoadLatest onSaved>`
  - :355-361 child prop types
  - :562-566 `onSaved()` in `save.onSuccess`
  - :662-685 banner
- Backend facts used below:
  - `applications.py:284-395` PATCH (normalize at :326-339; commit + `db.refresh` + return at :393-395, `response_model=ApplicationRead`);
  - :276-281 GET (`_detail` → `ApplicationDetail`, which inherits `customized_json: dict[str, Any] | None` from `ApplicationRead`, `schemas/application.py:73-103`);
  - :443-471 materialize (stores `load_base_resume` raw);
  - `application_render.py:66-72` (render writes `customized_json` ONLY when it is None);
  - `models/types.py:16` `JSONDoc = sa.JSON` (SQLite TEXT, key order kept).

### Current code
```tsx
const customizedKey = application.customized_json == null ? "" : JSON.stringify(application.customized_json);
const [adoptedKey, setAdoptedKey] = useState(customizedKey);
const adoptNextServerKey = useRef(false);
…
useEffect(() => {
  if (customizedKey === "" || customizedKey === adoptedKey) return;
  if (adoptNextServerKey.current || !editorDirty) {
    adoptNextServerKey.current = false;
    setAdoptedKey(customizedKey);
  }
}, [customizedKey, adoptedKey, editorDirty]);
…
<StudioEditor key={adoptedKey} … onLoadLatest={() => setAdoptedKey(customizedKey)}
  onSaved={() => { adoptNextServerKey.current = true; }} />
```

### Cause
The flag is consumed only when a *different* key arrives. A Save that leaves `customized_json`
unchanged (formatting or template only) never produces a new key, so the flag stays `true`
indefinitely. The next foreign key (chat/MCP) then takes the first branch and is adopted, which
remounts the editor with the foreign copy even while `editorDirty` is true. The user's unsaved edits
are discarded with no banner. The flag says "the next key is ours" without saying which key.

### What `savedKey` must be
`savedKey = serverKey(result.customized_json)`, where `result` is the PATCH response and
`serverKey` is **a sorted-key canonical JSON** (not `JSON.stringify`). **`customizedKey` must be
computed with the same function.**

Plain `JSON.stringify(result.customized_json)` fails for the reason in finding 1. Reproduction
(ran in this repo):
```
old  = {contact:{name,email}, experience:[{title,company}], summary:"old"}   // cached (JSONB/base-file order)
resp = {contact:{email,name}, summary:"new", experience:[{company,title}]}   // PATCH response (schema order)
replaceEqualDeep(old, resp) → contact/experience[0] are the OLD objects
plain-stringify equal: false    sorted-key equal: true
```
The zod parse downstream does not care about order (zod v4 `z.object` emits shape order and strips
unknown keys; verified), so switching the key's format changes nothing for `adoptedData`,
`initialSerialized` or the dirty compare.

### Why the new rule cannot regress the content-save path (the proof the ask wants)
For the refetched `customizedKey` to equal `savedKey` after our own content Save, it is enough that
the refetched value is the value the PATCH returned, compared by value:
1. The PATCH commits and then `db.refresh(application)` re-reads the row. Its `customized_json` is
   the stored JSON (json.loads of the TEXT). The GET serializes the same row, through the same
   pydantic field type (`dict[str, Any]`, inherited).
2. Nothing on the Save chain writes `customized_json`. Render writes it only when it is None
   (`application_render.py:66-72`), and re-score never does.
3. `apiFetch` → `response.json()` (`lib/api.ts:141-143`). Equal values give equal sorted-key strings,
   whatever order the keys arrive in and whatever structural sharing kept.

So `customizedKey === savedKey` holds whenever no other writer landed between our PATCH commit and
the refetch GET. In that one case the keys differ, and the rule falls through to the dirty check
(banner). That is the correct outcome: silently adopting a foreign write that landed right after
our save is the bug class being fixed. A formatting-only save now arms nothing, so a later foreign
key always goes through the dirty check.

### Fix design
**`frontend/lib/studio.ts`** (pure; node-testable):
```ts
/**
 * A server JSON value as one comparable string, object keys sorted at every depth. The query
 * cache is structurally shared: a refetch keeps the OLD object, and its key order, for every
 * subtree whose content did not change, while a mutation response is raw. With plain
 * JSON.stringify, a Save that only reordered keys in an untouched section would not match its
 * own refetch (and drafts migrated from Postgres are in JSONB key order).
 */
export function serverKey(value: unknown): string {
  if (value == null) return "";
  return JSON.stringify(value, (_key, v: unknown) =>
    v !== null && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
        )
      : v,
  );
}

export type AdoptAction = "none" | "in-place" | "remount" | "banner";

/**
 * What the tailored studio does when the server's customized_json moves (SYSTEM.md §12).
 * `own`: keys our own Saves returned, oldest first, not yet seen from the server.
 * - one of ours → move the baseline IN PLACE (the working copy is never replaced);
 * - anyone else's, editor clean, or a Rebuild the user confirmed → replace the content (remount);
 * - anyone else's over unsaved edits → keep the editor; the banner offers Load latest.
 */
export function adoptServerKey(s: {
  live: string; adopted: string; own: readonly string[]; dirty: boolean; forced: string | null;
}): { action: AdoptAction; own: string[] } {
  if (s.live === "" || s.live === s.adopted) return { action: "none", own: [...s.own] };
  const i = s.own.indexOf(s.live);
  if (i !== -1) return { action: "in-place", own: s.own.slice(i + 1) }; // drops older, unseen own keys too
  if (!s.dirty || s.live === s.forced) return { action: "remount", own: [] };
  return { action: "banner", own: [...s.own] };
}
```
The queue (not a single ref) covers two Saves inside one refetch window. Without it, the first
Save's refetch arrives while the ref already holds the second key, and a false banner flashes.

**Parent `TailoredResumeStudio`** (replaces :186-212, :214-224 inline parse, :290-313, and adds a
line to materialize):
```tsx
// module scope (was an inline arrow at :214), so the child parses a Save response the same way
function parseResumeData(key: string): ResumeData | null { /* body unchanged */ }

const customizedKey = useMemo(() => serverKey(application.customized_json), [application.customized_json]);
const [adoptedKey, setAdoptedKey] = useState(customizedKey);
// Remounts StudioEditor. Bumped only when a server copy REPLACES the editor's content (a foreign
// edit adopted while clean, Load latest, Rebuild). Our own Save moves the baseline in place, so the
// working copy, focus, tab, scroll, raw draft and status line survive it.
const [editorGen, setEditorGen] = useState(0);
const ownKeys = useRef<string[]>([]);
const forcedKey = useRef<string | null>(null); // Rebuild: the user already agreed to lose edits
const [editorDirty, setEditorDirty] = useState(false);
const onDirtyChange = useCallback((dirty: boolean) => setEditorDirty(dirty), []);

useEffect(() => {
  const next = adoptServerKey({ live: customizedKey, adopted: adoptedKey, own: ownKeys.current,
    dirty: editorDirty, forced: forcedKey.current });
  ownKeys.current = next.own;
  if (next.action === "in-place" || next.action === "remount") setAdoptedKey(customizedKey);
  if (next.action === "remount") { forcedKey.current = null; setEditorGen((g) => g + 1); }
}, [customizedKey, adoptedKey, editorDirty]);
```
- `materialize.onSuccess: (result) => { forcedKey.current = serverKey(result.customized_json); …existing }`
  (the response is `ApplicationDetail` with `customized_json`, `applications.py:471`).
- Render: `<StudioEditor key={editorGen} …`
- `onLoadLatest={() => { ownKeys.current = []; setAdoptedKey(customizedKey); setEditorGen((g) => g + 1); }}`
- `onSaved={(key) => { if (key !== adoptedKey) ownKeys.current = [...ownKeys.current, key]; }}`
  - The guard matters. A formatting-only save returns the current key, and enqueuing it would
    leave a stale entry. A stale entry can only ever cause an in-place move (never a content
    replacement), but it would hide a foreign revert to that exact content.
- Child prop type: `onSaved: (key: string) => void`. The child calls
  `onSaved(serverKey(result.customized_json))` (full child changes in item 2).

**If the planner rejects the in-place design** (keeps `key={adoptedKey}`), item 1 still stands:
the same helper, with `in-place` meaning `setAdoptedKey` (which remounts). Items 2 and 3 then need
the fallbacks described there.

### Tests / pins
- New `frontend/lib/studio.test.ts` cases:
  - **"a formatting-only save arms nothing: a later foreign key over unsaved edits shows the
    banner"** (`own: []`, `dirty: true`) — this is THE regression test for the HIGH PRIORITY bug;
  - own key → `in-place`, queue pruned through it;
  - two saves, the older lands first → `in-place`, the newer stays queued;
  - foreign while clean → `remount`, queue cleared;
  - `forced` while dirty → `remount`;
  - `live === ""` and `live === adopted` → `none`;
  - `serverKey`: nested key order is irrelevant, array order matters, `null` → `""`;
  - `serverKey(replaceEqualDeep(old, resp)) === serverKey(resp)`, importing `replaceEqualDeep`
    from `@tanstack/query-core` (proves finding 1 stays fixed).
- `backend/tests/test_frontend_studio.py`: add pins —
  - `"adoptNextServerKey" not in _TAILORED`;
  - `"serverKey(application.customized_json)"` and `"onSaved(serverKey(result.customized_json))"` in `_TAILORED`;
  - `"key={editorGen}"` in `_TAILORED`;
  - `"adoptServerKey("` in `_TAILORED`.
- Existing pin `test_tailored_status_ignores_the_post_save_refetch_gap` (:115-121) keeps
  `"onDirtyChange(dirty)"`; do not rename `dirty`.

### Edge cases / risks
- **Lint**: the effect sets state with ref reads inside, the same shape as today (passes). If
  `set-state-in-effect` fires anyway, keep the effect and add a reasoned disable like
  `editor-shell.tsx:70`. Adoption can only be decided after a query update, so it has to be an
  effect.
- **Foreign write between our PATCH and the refetch**: now a banner (editor dirty against the
  pre-save baseline). `unsaved` is false at that point, so Save is disabled. "Load latest" loses
  nothing unsaved (our copy is in History). This is acceptable and honest.
- **Save while the banner shows**: our PATCH overwrites the foreign copy, the key comes back as
  ours → in-place, `serverChanged` becomes false and the banner goes.
- **Version-history restore** (`onRestored` invalidates) stays "foreign": clean → remount;
  dirty → banner. Unchanged.
- **Same component, different application** (navigating `/applications/A/resume` →
  `/applications/B/resume` reuses the instance): pre-existing; a dirty A shows the banner over B.
  Optional hardening: `key={app.id}` on `<TailoredResumeStudio>` in
  `app/applications/[id]/resume/page.tsx:63`.
- `serverKey` cost: memoized on the `customized_json` reference, which structural sharing keeps
  stable while the content is unchanged.

---

## Item 2 — Edits typed in the post-save gap are lost; formatting/template changes are clobbered

### Locations
- `tailored-resume-studio.tsx`
  - :367 `useState(initialData)`
  - :370-372 formatting state
  - :487-516 `dirty`
  - :526-540 `sentData` / `savedSnapshot` / `unsaved`
  - :542-606 `save` (:552 `sentData.current = data`; :562-589 response adoption; :603 chained render)
  - :770 `onSave={() => save.mutate()}`
- Base twin: `editor-body.tsx:175-190` `adoptBaseResumeDetail`, :192-222 `save` (:215 adopts
  everything); base PUT renders inline (finding 3).

### Current code (tailored `onSuccess`)
```tsx
onSaved();
setFormatting((result.formatting as Partial<ResumeFormatting> | null) ?? null);   // clobbers in-flight formatting edits
onTemplateChange(templateIdFromApi(result.template_id));                           // clobbers an in-flight template pick
setSavedSnapshot(snapshotOf(sentData.current ?? data, savedFormatting, templateIdToApi(templateIdFromApi(result.template_id))));
… invalidate ["application"] (→ refetch → new key → remount) … render.mutate({ thenRescore: true });
```

### Cause
- **Content**: the refetch brings the new key, and the adoption effect remounts `StudioEditor`
  with `useState(initialData)` set to the server copy. Anything typed after `mutationFn` captured
  `data` is gone: during the PATCH, and between the response and the refetch. The `unsaved` flag
  shows those edits as "Unsaved changes" and then the remount deletes them.
- **Formatting/template**: `onSuccess` unconditionally writes the server's values over whatever
  the user changed while the PATCH was in flight.
- **Base**: `adoptBaseResumeDetail(result)` does the same for data/displayName/formatting/template.
  The window is the whole inline render (seconds).

### Options and tradeoffs
| Option | Fixes 2 | Fixes 3 | Cost |
|---|---|---|---|
| A. Block editing while saving (`inert` / `<fieldset disabled>` from mutate until the refetch) | yes | **no, worse**: disabling or inerting the focused field drops focus to `<body>` | Keystrokes during Cmd/Ctrl+S-then-keep-typing are dropped silently. Formatting panel and template select sit outside the editor pane, so they need a separate lock. |
| B. Carry the working copy across the remount (child mirrors `{data, formatting}` into a parent ref; the new mount seeds from it when it differs from what was sent) | yes | no | New props and a ref protocol. The remount still resets tab, Formatting panel, scroll, preview width, raw mode, review, focus and the live region. |
| **C. Own saves adopt IN PLACE (recommended)** | yes | yes (with item 3's button fix) | The parent changes are in item 1. The child adopts the server's normalized copy only where nothing changed since the send. |

**Recommend C.** Once item 3 is counted it is the smallest change, and it removes the underlying
cause (the remount on own saves) instead of compensating for it.

### Fix design (C), tailored child
```tsx
type SaveSent = { data: ResumeData; formatting: Partial<ResumeFormatting> | null; templateId: string };
// props: onSaved: (key: string) => void;  onTemplateChange: Dispatch<SetStateAction<string>>
//   (parent already passes setTemplateId; TemplateSelect's `(v: string) => void` still type-checks)

// delete `sentData` (:533); keep `savedSnapshot`/`unsaved` exactly (the gap before the refetch
// still exists — the baseline moves when the refetch lands)

const save = useMutation({
  mutationFn: async (sent: SaveSent) => {
    const validated = resumeDataSchema.safeParse(sent.data);
    if (!validated.success) throw new Error(/* unchanged */);
    return apiFetch<Application>(`/api/applications/${applicationId}`, {
      method: "PATCH",
      body: JSON.stringify({ customized_json: validated.data, formatting: sent.formatting,
        template_id: templateIdToApi(sent.templateId) }),
    });
  },
  onSuccess: (result, sent) => {
    // Ours: the parent moves this editor's baseline to this key in place (no banner, no remount).
    const key = serverKey(result.customized_json);
    onSaved(key);
    // Take the server's normalized copies, but only where nothing changed since the send: an edit
    // typed while the save ran stays, and reads as unsaved.
    const savedData = parseResumeData(key) ?? sent.data;
    const savedFormatting = (result.formatting as Partial<ResumeFormatting> | null) ?? null;
    const savedTemplateId = templateIdFromApi(result.template_id);
    setData((cur) => keepIfEdited(cur, sent.data, savedData));
    setFormatting((cur) => keepIfEdited(cur, sent.formatting, savedFormatting));
    onTemplateChange((cur) => keepIfEdited(cur, sent.templateId, savedTemplateId));
    setSavedSnapshot(snapshotOf(savedData, savedFormatting, templateIdToApi(savedTemplateId)));
    // …invalidations, setRevertedKeys, render.mutate({ thenRescore: true }) unchanged
  },
  onError: (err: Error) => toast.error(err.message),
});
// button: onSave={() => save.mutate({ data, formatting, templateId })}   (item 4 wraps this)
```
**`lib/studio.ts`**:
```ts
/** `saved` when `current` still equals what was sent, else `current`: a save's response must not
 *  overwrite an edit made while the save ran. Compared by value (a re-picked equal value is a new object). */
export function keepIfEdited<T>(current: T, sent: T, saved: T): T {
  return JSON.stringify(current) === JSON.stringify(sent) ? saved : current;
}
```
Why this is correct without the remount:
- With no edits after the send, `data` becomes `parseResumeData(key)`. After the refetch the parent
  adopts the same key and passes `initialData = parseResumeData(key)`, so `initialSerialized`
  (a memo on the prop, :491-494) matches and `dirty` is false.
- `snapshotOf(savedData, …)` uses the *normalized* data. If it used the sent data, a normalization
  difference would read as "Unsaved changes" in the gap.
- With edits after the send, `data` keeps them, `unsaved` is true at once, and Save re-enables when
  `busy` clears.

Rewrite the comments at :487-490 and :526-532: they describe the remount.

What the remount used to reset, and what happens now:
- `revertedKeys`: already reset in `onSuccess`.
- `diff`: re-fetched via invalidation.
- `review`: persists. Before, it snapped back to `reviewDefault` on every save, which re-opened the
  panel after a user closed it on a `?review=1` visit.
- `coherence` flags: persist; the plan-writer decides. Recommendation: keep them. The user may be
  working through the list, and an unapplied flag that no longer matches already toasts "Couldn't
  locate…".
- `rawMode`: persists (item 4 relies on this).

### Base twin (same helper, `editor-body.tsx:192-222`)
```tsx
mutationFn: async (sent: { data: ResumeData; displayName: string; formatting: …; templateId: string }) => PUT with sent.*,
onSuccess: (result, sent) => {
  setData((cur) => keepIfEdited(cur, sent.data, result.data));
  setDisplayName((cur) => keepIfEdited(cur, sent.displayName, result.display_name ?? ""));
  setFormatting((cur) => keepIfEdited(cur, sent.formatting, (result.formatting as …) ?? null));
  setTemplateId((cur) => keepIfEdited(cur, sent.templateId, templateIdFromApi(result.template_id)));
  const snapshot = /* same JSON.stringify({data, displayName, formatting, templateId}) of result as :182-187 */;
  lastSyncedRef.current = snapshot; setLastSyncedSnapshot(snapshot);
  qc.setQueryData(...); … unchanged
},
// onSave={() => save.mutate({ data, displayName, formatting, templateId })}
```
Keep `adoptBaseResumeDetail` for InstructSheet and KbImport (:577, :584). Both are gated on
`!hasUnsavedChanges`, so full adoption is correct there. Factor the snapshot builder (it now
appears three times) into one local function, for the ratchet.

### Tests / pins
- `lib/studio.test.ts`: `keepIfEdited` (equal → saved; edited → current; `null` sent and `null`
  current → saved).
- `test_frontend_studio.py`: add `"keepIfEdited(" in _TAILORED` and `in _BASE`;
  `"sentData" not in _TAILORED`. `_mutation(_TAILORED, "save")` in
  `test_tailored_save_chain_fires_no_success_toasts` (:90-104) still slices correctly.
- The existing pins `savedSnapshot`, `"savedSnapshot === null ||"`, `"dirty: unsaved"` and
  `"const canSave = unsaved && !busy;"` keep passing.

### Edge cases / risks
- **Save chain render and an in-flight template pick**: `render.mutate` reads the parent's
  *current* `templateId` (:163-165). If the user picked a template during the PATCH, the PDF
  renders with the unsaved pick while the status reads "Unsaved changes". This is pre-existing,
  and the status is honest about it.
- **Response `customized_json` fails the zod parse**: `parseResumeData` → null → keep `sent.data`.
  The parent then renders its "invalid" placeholder (pre-existing behavior).
- **Browser check**, both studios: edit a field, press Save, and keep typing during the PATCH (the
  base studio's inline render makes this easy). The text must stay and read "Unsaved changes" once
  "Saving…" clears. Also check that tab, Formatting panel, scroll and preview width survive a
  content save.

---

## Item 3 — Focus drops to `<body>` after Save; the status live region remounts

### Locations
- `frontend/components/resume-editor/studio-save-button.tsx:37-46`
- `save-status.tsx:14-37` (`role="status"`, rendered in the header subtitle at
  `tailored-resume-studio.tsx:707`, inside the remounting `StudioEditor`)
- `hooks/use-save-shortcut.ts:50-62` (blur, re-focus the field, save)

### Current code
```tsx
<Button size="sm" onClick={() => onSave()} disabled={!canSave} title=… aria-keyshortcuts="Meta+S Control+S">
```

### Cause
Two independent causes:
1. **The button disables itself.** `canSave` goes false as soon as `save.isPending` (and it stays
   false after a successful save). A focused native `<button>` that becomes `disabled` loses focus
   to `<body>` (the HTML focus-fixup rule). This hits BOTH studios.
2. **The remount.** It destroys the button and the whole editor subtree, including the field the
   Cmd/Ctrl+S path just re-focused (`use-save-shortcut.ts:60`). It also recreates
   `<span role="status">`. A live region inserted with content is not announced, so the first
   post-remount status ("Rendering PDF…") is missed.

### Fix design
- Cause 2 is fixed by item 2 option C: no remount on our own save, so the field keeps focus, the
  status span stays mounted, and every transition (Saving… → Rendering PDF… → Re-scoring… → All
  changes saved) is announced by a region that already existed. **No need to lift
  `SaveStatusText`.** The remaining remount paths (foreign adoption while clean, Load latest,
  Rebuild) end on "All changes saved", so no announcement is lost there.
- Cause 1: keep focus on Save. Base UI's Button supports it natively
  (`node_modules/@base-ui/react/utils/useFocusableWhenDisabled.js`):
  - with `focusableWhenDisabled`, a native button gets `aria-disabled` and `data-disabled` instead
    of `disabled`, stays in the tab order, and blocks click and keyboard activation;
  - the shared `buttonVariants` dims with `disabled:` (the `:disabled` pseudo-class), which does
    not match an aria-disabled button, so restyle locally.
  ```tsx
  <Button
    size="sm"
    onClick={() => onSave()}
    disabled={!canSave}
    // Stays focusable while disabled: Save turns itself off, and a disabled <button> drops focus to
    // <body>, which lost a keyboard user's place after every save. Dimmed via data-disabled below
    // because `disabled:` only matches the native attribute.
    focusableWhenDisabled
    className="data-disabled:pointer-events-none data-disabled:opacity-50"
    title={`Save (${shortcutLabel(mod, "S")})`}
    aria-keyshortcuts="Meta+S Control+S"
  >
  ```
- **Where focus goes**:
  - keyboard Save (Enter/Space) → stays on Save; the SR hears "Save, dimmed", and the status line
    announces progress;
  - Cmd/Ctrl+S from a field → back in that field (the hook already does this; the remount was
    undoing it);
  - mouse click → Chrome focuses the button, so it stays there. WebKit (Safari and the desktop
    shell's WKWebView) never focuses a clicked button, so focus stays wherever it was. That is the
    platform convention and needs nothing.
  - Rejected alternatives: moving focus to the status line (not focusable, and it would announce
    twice) and moving it to the first field (surprising).

### Tests / pins
- `test_one_save_button_owns_the_click_and_the_shortcut` (:52-56) keeps `"disabled={!canSave}"`.
  Add `"focusableWhenDisabled" in _SAVE_BUTTON` and `"data-disabled:opacity-50" in _SAVE_BUTTON`.
- `test_save_button_keeps_its_label_while_saving` (:285-290): the `/>\}\s*Save\s*</Button>` regex
  still matches.

### Edge cases / risks
- Save is now a tab stop even when disabled (clean studio). This is intended: the SR reads the
  state, and the title names the shortcut.
- Base UI's `onKeyDown` calls `preventDefault` for every non-Tab key on a focused disabled button.
  A Cmd/Ctrl+S pressed ON the disabled Save therefore reaches `useSaveShortcut` as `claimed` and is
  ignored. `canSave` is false in that state anyway, so nothing is lost; worth knowing when testing.
- Browser check: Tab to Save, press Enter, and confirm `document.activeElement` is still the Save
  button after "All changes saved". Press Cmd/Ctrl+S in the Summary textarea and confirm focus
  returns to the textarea and stays after the refetch. Use VoiceOver or the accessibility tree to
  hear all four statuses.

---

## Item 4 — Raw-JSON drafts are untracked

### Locations
- `frontend/components/resume-editor/raw-json-toggle.tsx:1-54` (whole file)
- `studio-overflow.tsx:64-67` ("Form view" / "Edit raw JSON" toggle)
- Tailored:
  - `tailored-resume-studio.tsx:368` `rawMode`
  - :503-518 `dirty` and unload warning
  - :536-540 `unsaved`
  - :615 `canSave`
  - :776-780 toggle
  - :828-833 mount
- Base:
  - `editor-body.tsx:77` `rawMode`
  - :118-151 external-adoption effect
  - :249-259 `hasUnsavedChanges`/status/`canSave`
  - :388-390 toggle
  - :452-457 mount

### Current code
```tsx
const [text, setText] = useState(() => JSON.stringify(value, null, 2));   // draft lives only here
const apply = () => { …parse + zod… onChange(result.data); onClose(); };
<Button onClick={apply}>Apply JSON</Button>
<Button variant="outline" onClick={onClose}>Cancel</Button>               // discards silently
```

### Cause
The draft is local state the studios cannot see. `data` changes only on Apply, so `dirty`,
`unsaved`, `canSave`, the status line, the stale strip and `useUnsavedChangesWarning` all read
"clean" while typed JSON is pending. The Cmd/Ctrl+S chord is swallowed because `canSave` is false.
Cancel and "Form view" unmount the pane and drop the text. There is one more hazard: the tailored
adoption guard reads `dirty`, so a foreign edit would remount over a pending draft. In the base
studio, the external-adoption effect (:140) would `setData(live.data)` underneath an open draft,
and a later Apply would silently overwrite the adopted server copy.

### Decision: Cmd/Ctrl+S in raw mode = apply-then-save when valid (recommended)
Reasons:
1. This is the studio's existing rule. `useSaveShortcut` already blurs a field to commit a
   blur-committed draft (chip input, section rename) and then saves, "so the key never saves less
   than the button would" (conventions :118-123). Apply is the raw pane's commit step, so the same
   rule applies.
2. "Unapplied JSON + Save disabled" would also block saving unrelated form, formatting or template
   edits while the pane is open. It would add a sixth status and a primary action that is disabled
   with no reason given.
3. An invalid draft already has a place to report itself (the pane's error block). Saving nothing
   and pointing there is honest. The status stays "Unsaved changes".

### Fix design
**`lib/studio.ts`**:
```ts
/** Whether typed JSON would change `value`. Whitespace and object key order are not changes; text
 *  that does not parse is (the user would lose it). */
export function jsonDraftDiffers(text: string, value: unknown): boolean {
  try { return serverKey(JSON.parse(text)) !== serverKey(value); } catch { return true; }
}
```
**`raw-json-toggle.tsx`** (shared hook in the same file keeps the two studios clone-free):
```tsx
export type RawJsonHandle = {
  /** Save's first step: the applied resume; null when invalid (the pane shows why); undefined when there is no draft. */
  commit: () => ResumeData | null | undefined;
};

export function useRawJsonDraft() {
  const ref = useRef<RawJsonHandle>(null);
  const [pending, setPending] = useState(false);
  /** Commit a pending draft into `apply`, then run `next`. An invalid draft runs neither. */
  const commitThen = (apply: (d: ResumeData) => void, next: (d: ResumeData | undefined) => void) => {
    const committed = ref.current?.commit();
    if (committed === null) return;
    if (committed) apply(committed);
    next(committed);
  };
  return { pending, bind: { ref, onPendingChange: setPending }, commitThen };
}

export function RawJsonToggle({ value, onChange, onClose, onPendingChange, ref }: {
  value: ResumeData; onChange: (next: ResumeData) => void; onClose: () => void;
  /** Whether typed JSON differs from `value`: the studio counts it as unsaved. */
  onPendingChange: (pending: boolean) => void;
  ref?: Ref<RawJsonHandle>;
}) {
  const confirm = useConfirm();
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  // A value that changes under an untouched pane (a save's normalized copy) re-syncs the text.
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    if (!jsonDraftDiffers(text, shown)) setText(JSON.stringify(value, null, 2));
  }
  const pending = useMemo(() => jsonDraftDiffers(text, value), [text, value]);
  useEffect(() => { onPendingChange(pending); }, [pending, onPendingChange]);
  useEffect(() => () => onPendingChange(false), [onPendingChange]);   // closing the pane clears it

  const parse = (): ResumeData | null => { /* the existing try/JSON.parse/safeParse/setError body, returning data or null */ };
  const apply = () => { const next = parse(); if (next) { onChange(next); onClose(); } };
  useImperativeHandle(ref, () => ({
    commit: () => {
      if (!pending) return undefined;
      const next = parse();
      if (next) setText(JSON.stringify(next, null, 2));
      return next;
    },
  }));
  const cancel = async () => {
    if (pending && !(await confirm({ title: "Discard your JSON edits?",
        description: "The JSON you typed has not been applied. This can't be undone.",
        confirmLabel: "Discard", destructive: true }))) return;
    onClose();
  };
  // render: error <pre role="alert">…; buttons: Apply JSON → apply, Cancel → cancel
}
```
Note on the re-sync: compare the text against the PREVIOUS value (`shown`), not the new one. After
a save, the normalized copy can differ in shape from what was typed, and comparing against the new
value would lock the pane into "pending".

**Tailored studio:**
```tsx
const raw = useRawJsonDraft();
const dirty = useMemo(() => raw.pending || JSON.stringify(data) !== initialSerialized || …, [raw.pending, …]);
const unsaved = raw.pending || (dirty && (savedSnapshot === null || snapshotOf(…) !== savedSnapshot));
const onSave = () => raw.commitThen(setData, (applied) => save.mutate({ data: applied ?? data, formatting, templateId }));
<StudioSaveButton onSave={onSave} … />
onToggleRaw={() => (rawMode ? raw.commitThen(setData, () => setRawMode(false)) : setRawMode(true))}
<RawJsonToggle {...raw.bind} value={data} onChange={setData} onClose={() => setRawMode(false)} />
```
Folding `raw.pending` into both `dirty` and `unsaved` gives these for free:
- the status line ("Unsaved changes") and `canSave`;
- the stale strip and the empty-preview copy;
- the unload warning;
- the adoption guard (`onDirtyChange(dirty)` → a foreign edit shows the banner instead of
  remounting over the draft);
- item 6's gates.

**Base studio:** the same `raw` hook and the same `onSave` / `onToggleRaw` shapes.
- `const hasUnsavedChanges = raw.pending || currentSnapshot !== lastSyncedSnapshot;`
- In the adoption effect (:140), change the adopt branch to
  `else if (serverMoved && localSnap === lastSyncedRef.current && !raw.pending)` and add
  `raw.pending` to the deps. The adoption runs once the draft is applied or discarded.

"Form view" with a pending draft behaves like Apply: switching views is not a discard gesture, and
an invalid draft keeps the pane open with its error. Cancel is the only discard, and it confirms.

### Tests / pins
- `lib/studio.test.ts`: `jsonDraftDiffers`:
  - whitespace-only → false;
  - reordered keys → false;
  - changed value → true;
  - unparseable → true.
- New pins in `test_frontend_studio.py`:
  - `"onPendingChange" in raw-json-toggle.tsx`, `"useRawJsonDraft(" in _TAILORED and _BASE`,
    `"{...raw.bind}" in _TAILORED and _BASE`;
  - `"Discard your JSON edits?" in raw-json-toggle.tsx`;
  - `'role="alert"' in raw-json-toggle.tsx`;
  - `"raw.pending ||" in _TAILORED` (in `unsaved`);
  - `"!raw.pending" in _BASE`.
- Existing pins unchanged:
  - `"dirty: unsaved"` (substring still present);
  - `"const canSave = unsaved && !busy;"`;
  - `"previewStale={unsaved}"`;
  - `"emptyMessage={emptyPreviewMessage(unsaved)}"`;
  - `"onDirtyChange(dirty)"`;
  - base `"previewStale={hasUnsavedChanges}"`;
  - `"canSave={canSave}"`.

### Edge cases / risks
- Cmd/Ctrl+S from inside Monaco: `holdsDraft` sees Monaco's textarea, blurs and re-focuses it, and
  then saves. Monaco fires `onChange` on every keystroke, so no draft is waiting on blur. Check in
  the browser that Monaco does not `preventDefault` the chord. If it did, `useSaveShortcut` would
  treat it as `claimed`.
- `raw.pending` lags the pane by one effect. `commit()` reads the pane's own fresh `pending`, so
  Save never acts on stale state.
- The re-sync block uses setState during render. The lint probe passes it; keep the condition
  exactly as written.
- Apply-then-save sends the committed data straight to `save.mutate`, because `setData` is async.
  This is why item 2's `mutationFn(sent)` shape is a prerequisite.

---

## Item 5 — Score tab: focus after Import → Done, and the "No ATS scores yet." flash

### Locations
- `frontend/components/ats-score-panel.tsx`
  - :213 `importOpen`
  - :232-238 `run`
  - :288-296 first-visit auto-run
  - :310-318 post-import effect
  - :324-334 skeleton
  - :336-345 error
  - :347-369 import prompt (UploadDialog mounted INSIDE it at :366)
  - :370-380 "No ATS scores yet."
- `components/setup/upload-dialog.tsx:144-181` (no `finalFocus` passthrough)
- `components/career/resume-import-dialog.tsx:270` (Done → `onClose`)
- `components/ui/dialog.tsx:52-79` (`DialogContent` spreads Popup props, so `finalFocus` passes through)
- Job page mount `app/jobs/[id]/page.tsx:492-493`

### Cause (trace)
1. Done → `setImportOpen(false)`. The branch condition `!unscorable && (noBases || importOpen)` is
   now false (bases were refetched while the report was open), so the prompt branch unmounts
   together with the `UploadDialog` inside it. The dialog's return-focus target (the "Import
   resumes" button) is gone, so focus goes to `<body>`. No exit animation runs either.
2. Same render: `baseRows` is empty and `run` is not pending, so "No ATS scores yet." + "Run ATS
   scoring" paints.
3. The effect then calls `runMutate()`. `mutate()` updates the observer synchronously, but
   `useMutation` is notified through TanStack's `notifyManager`, which defaults to `setTimeout(0)`
   (`query-core/build/modern/notifyManager.js:3`). The skeleton therefore arrives a frame or more
   later. This is the "before" flash.
4. `run.onSuccess` fires `invalidateQueries` without returning it, so `run.isPending` goes false
   while the `["ats-scores"]` refetch is still in flight. The cached `[]` renders "No ATS scores
   yet." until the refetch lands. This is the "after" flash.
5. The same mechanism causes a first-visit flash: `scores` succeeds with `[]`, "No ATS scores yet"
   paints, and only then does the auto-run effect fire.

### Fix design
```tsx
const rootRef = useRef<HTMLDivElement>(null);

const run = useMutation({
  mutationFn: () => runAtsScores(jobId),
  // Returned: the run stays pending until the list has refetched, so the skeleton hands straight
  // to the cards — no frame of "No ATS scores yet." after a run.
  onSuccess: () => qc.invalidateQueries({ queryKey: ["ats-scores", jobId] }),
  onError: (err: Error) => toast.error(err.message),
});

// Score the imported resumes in the SAME event as the close: mutate() marks the run pending
// synchronously, and the render that drops the prompt reads it through useSyncExternalStore, so it
// paints the skeleton, never "No ATS scores yet.". The effect below stays as the fallback for a
// base list that lands after the dialog closed.
const onImportOpenChange = (open: boolean) => {
  setImportOpen(open);
  if (!open && sawNoBases.current && baseCount > 0 && !run.isPending) {
    sawNoBases.current = false;
    run.mutate();
  }
};
```
- Keep the :310-318 effect verbatim. It is the fallback, and it carries two pinned strings.
- Optional first-visit fix: the skeleton condition becomes
  `scores.isLoading || (baseRows.length === 0 && (run.isPending || (run.isIdle && scores.data?.length === 0)))`.
  `run.isIdle` with an empty list means the auto-run is about to fire; `autoRan` and a non-idle run
  move together.
- **Hoist the dialog and give it a stable return target.** Move the body's early returns into a
  nested `renderBody()` (a plain function, not a component), then:
  ```tsx
  return (
    // Focus lands here when the import dialog closes: its opener, the prompt's button, is gone by then.
    <div ref={rootRef} tabIndex={-1} className="outline-none">
      {renderBody()}
      <UploadDialog open={importOpen} onOpenChange={onImportOpenChange} finalFocus={rootRef} />
    </div>
  );
  ```
  Delete the in-branch `<UploadDialog …/>` (:366). Keep `|| importOpen` in the branch condition so
  the prompt stays behind the open dialog.
- `UploadDialog`: add an optional `finalFocus?: RefObject<HTMLElement | null>` and pass it to
  `<DialogContent size="lg" finalFocus={finalFocus}>`. Its other callers pass nothing, so nothing
  changes for them.
- Focus target alternative: the job page's `TabsContent value="fit"` is already a focusable,
  labelled tabpanel (Base UI gives it `tabIndex=0`), so it could be the target:
  `finalFocus={() => rootRef.current?.closest<HTMLElement>('[role="tabpanel"]') ?? true}`. That is
  semantically nicer but couples the panel to the page. Either is acceptable; the wrapper is
  self-contained.

### Tests / pins
- `test_frontend_first_run.py`:
  - `test_score_tab_offers_import_when_there_is_nothing_to_score` (:38-50) keeps `<UploadDialog`,
    `bases.isSuccess && bases.data.length === 0`, and the `scores.isError` < prompt and
    `const unscorable` < prompt source order (the hoisted dialog sits after both);
  - `test_score_tab_rescores_once_after_an_import_never_twice` (:53-60) keeps
    `if (noBases && !bases.isFetching)` and `!importOpen && !run.isPending`.
- `test_frontend_query_error_states.py:78` ("No ATS scores yet." after the error branch) is
  unchanged.
- Add pins:
  - `onSuccess: () => qc.invalidateQueries` (returned, regex allowing whitespace);
  - `finalFocus={rootRef}`;
  - `onOpenChange={onImportOpenChange}`;
  - `panel.count("<UploadDialog") == 1` placed after `renderBody()`;
  - `finalFocus` in `upload-dialog.tsx`.

### Edge cases / risks
- Double run: the handler clears `sawNoBases` before mutating, so the effect in the same commit sees
  it false. Both paths check `!run.isPending`.
- Returning the invalidate promise makes "Re-score base resumes" read "Re-scoring…" until the list
  lands. That is more accurate than today.
- A tabIndex=-1 wrapper has no visible ring (`outline-none`). A programmatic focus after a mouse
  click shows no `:focus-visible` anyway. If the planner wants a ring for keyboard users, use
  `focus-visible:ring-2 ring-ring rounded-md`.
- Optional: an SR-only `role="status"` "Scoring against your resumes…" in the skeleton branch,
  because the skeleton has no text. This is out of the ask; flag only.
- Browser check: on a job with zero base resumes, open the Score tab, import one, and click Done.
  Expect skeleton then cards with no "No ATS scores yet." frame (record a performance trace or step
  frames), and `document.activeElement` is the wrapper (or the tabpanel).

---

## Item 6 — ⋯ Generate PDF gated on `dirty`; Re-score re-enables during "Rendering PDF…"

### Locations
- `tailored-resume-studio.tsx`
  - :608 `busy = save.isPending || rescore.isPending || materializePending` (no render)
  - :745-765 Re-score (:749 `disabled={busy || dirty}`)
  - :787-802 ⋯ Generate/Regenerate PDF (:788 `disabled={busy || render.isPending || dirty}`)
  - :838-849 `DiffReviewPanel dirty={dirty}`
- `diff-review.tsx:726-729` ("This list describes the last saved version. Save to refresh it.")

### Cause
- **Re-score.** It is blocked mid-render only by accident: `dirty` is stale-true until the post-save
  refetch lands. The refetch is a quick GET; the LaTeX render takes seconds. Once the refetch lands
  (today, via the remount), `dirty` is false and `busy` ignores `render.isPending`, so Re-score
  re-enables while the status reads "Rendering PDF…". A click then runs a manual re-score
  concurrently with the chain's own (`render.onSuccess` → `rescore.mutate({announce:false})`,
  :181). Tailored rows are append-only (`models/ats_score.py:13-23`; the unique index covers
  `phase='base'` only), so this writes a duplicate trajectory point and fires a toast mid-chain.
  Scoring does not read the PDF, so it is not a wrong-content bug. It is a double run.
- **Generate PDF.** It renders the SERVER copy, so the right blocker is "edits the server has not
  seen" (`unsaved`). `dirty` is additionally true in the post-save gap. `render.isPending` covers
  most of that gap, but after a fast render failure (a 400 before the refetch lands) the item stays
  disabled while `emptyPreviewMessage(unsaved)` says "Generate one from More resume actions (⋯)".
  That points at a disabled item, which breaks the conventions promise at
  `docs/frontend-conventions.md:103-108`.
- **DiffReviewPanel note.** It is a user-facing signal, and it says "Save to refresh it" in the gap.

### Decision and fix
- Re-score: `disabled={busy || render.isPending || unsaved}`. Reasons:
  - no re-score while the chain's render is out, because the chain re-scores itself when it lands;
  - `unsaved`, not `dirty`, because re-scoring reads the saved draft and the hint (`title`)
    already reads `unsaved`.

  Rewrite the comment at :750-752.
- ⋯ Generate PDF: `disabled={busy || render.isPending || unsaved}`. User-facing gates read
  `unsaved` (conventions *Tailored studio*). After item 4, `unsaved` includes a pending raw draft.
- `DiffReviewPanel dirty={unsaved}` (the prop name can stay).
- **Do not add `render.isPending` to `busy`.** `busy` also gates Save, Load latest and Rebuild.
  Blocking Save for the whole render would make "type during render, then Cmd/Ctrl+S" do nothing,
  and the status orders dirty above rendering precisely because edits during a render are
  expected.

### Tests / pins
- **Update** `test_tailored_rescore_hint_reads_unsaved` (`test_frontend_studio.py:158-164`): replace
  the `"disabled={busy || dirty}"` assertion with `"disabled={busy || render.isPending || unsaved}"`
  and fix its comment ("no re-score mid-render" now reads `render.isPending`). Keep the
  `title={ unsaved ?` regex.
- Add a pin that the ⋯ block has `disabled={busy || render.isPending || unsaved}`. Slice from
  `onClick={() => render.mutate()}` backwards, or from `"Regenerate PDF"`, to the enclosing
  `<DropdownMenuItem`.

### Edge cases / risks
- A banner showing a foreign copy (`serverChanged`) with `unsaved === false`: Generate PDF becomes
  enabled and renders the foreign server copy while the editor shows ours. This is acceptable,
  because the banner explains it and the PDF matches the saved document. Add `|| serverChanged` only
  if the planner prefers strictness.
- Rebuild (`disabled={busy}`) during a render stays allowed. This is pre-existing and out of scope.

---

## Item 7 — Section order: move down then back up leaves "Unsaved changes"

### Locations
- `frontend/lib/formatting.ts`
  - :28 `section_order` doc
  - :83-90 `SECTION_ORDER_FALLBACK`
  - :149-161 `diffFrom`
  - :170-180 `sameFormattingValue`
- `frontend/components/resume-editor/formatting-panel.tsx`
  - :82 `effective`
  - :85-90 `setKey` → `onChange(diffFrom(baseline, { ...effective, [key]: next }))`
  - :214-264 `sectionOrderRow` (:218 `order = effective.section_order ?? SECTION_ORDER_FALLBACK`;
    :254 `setKey(key, move(order, index, target))`)
- Backend semantics: `app/schemas/formatting.py:119-148` `resolve_section_order` (null/empty → the
  template's native order; a partial list goes first and the rest are appended).
  `template_registry.py:505-523`: Harshibar is the only bundled template whose native order differs,
  and it ships an explicit `section_order` default.

### Cause
With `baseline.section_order === null` (every template except Harshibar, and no base override),
the panel shows `SECTION_ORDER_FALLBACK`.
- Move down: `diffFrom` compares the moved list with `null` → stored.
- Move up: the list equals the fallback again, but `sameFormattingValue([...], null)` is `false`
  (Array vs null) → the explicit list is stored.
- The result is `{ section_order: [...] }` against a server value of `null`, so the state reads
  dirty in both studios.

### Fix design (in the pure lib, so it is node-testable and also cleans stored data)
```ts
/** The order the section-order control shows: `null` (the template's own order) shows the fallback list. */
export function shownSectionOrder(order: SectionKey[] | null | undefined): SectionKey[] {
  return order ?? SECTION_ORDER_FALLBACK;
}

export function diffFrom(baseline, value) {
  const out: Partial<ResumeFormatting> = {};
  for (const key of Object.keys(FORMATTING_DEFAULTS) as (keyof ResumeFormatting)[]) {
    const v = value[key];
    if (v === undefined) continue;
    // Compare what the control SHOWS: an explicit list equal to the inherited order is not an
    // override, so moving a section down and back up stores nothing (null = inherit).
    const same = key === "section_order"
      ? sameFormattingValue(shownSectionOrder(v as SectionKey[] | null), shownSectionOrder(baseline.section_order))
      : sameFormattingValue(v, baseline[key]);
    if (!same) (out as Record<string, unknown>)[key] = v;
  }
  return Object.keys(out).length ? out : null;
}
```
Panel :218 → `const order = shownSectionOrder(effective.section_order);`, so there is one
definition of "what null shows". Update the `diffFrom` doc comment (:139-148).

This stores `null` exactly when the explicit list equals the inherited order as displayed.
- Studio baseline with a base-resume override L: moving back to L gives equal lists → dropped
  (worked before too).
- Baseline null, list returns to the fallback → dropped (the fix).
- Baseline L ≠ fallback, list equals the fallback → still stored (a genuine override of L).

### Tests / pins
- New `frontend/lib/formatting.test.ts` (`node --test` picks it up; `formatting.ts` has no
  imports):
  - `diffFrom(FORMATTING_DEFAULTS, { ...FORMATTING_DEFAULTS, section_order: [...SECTION_ORDER_FALLBACK] })` → `null`;
  - a moved list → `{ section_order: moved }`;
  - `baseline.section_order = L`, value `L` → `null`;
  - baseline `L`, value fallback → `{ section_order: fallback }`;
  - `section_order: null` with baseline null → `null`;
  - a non-order knob still diffs (`font_size: 12` → `{font_size: 12}`).
- Existing pins unaffected:
  - `test_section_order_has_no_drag_path` / `test_section_order_buttons_are_24px_targets`
    (`test_frontend_studio.py:215-232`, anchors `const sectionOrderRow = () => {` …
    `const showContent`);
  - `test_formatting_parity.py` (parses the `FORMATTING_DEFAULTS` literal only).

### Edge cases / risks
- **Stored data cleanup**: a resume or application that already stores an explicit list equal to
  the fallback (from this bug) loses it at its next formatting edit. This is intended. It renders
  identically for every bundled null-default template:
  - `resolve_section_order` puts the requested members first;
  - carlito's native order lacks `extra_sections`, which simply falls out.

  One behavioral nuance: if that resume later switches to Harshibar, it now inherits Harshibar's
  order instead of the fallback order. That matches what the panel showed ("inherited").
- **Template editor** (`app/templates/[id]/page.tsx:300-307`, baseline `FORMATTING_DEFAULTS`):
  Harshibar's list contains `certifications` and not `extra_sections`, so it can never equal the
  fallback, and no user-visible change is possible there. A user template with a null default and
  a different native order already displayed the fallback (pre-existing inaccuracy). Returning to
  it now restores exactly the pre-edit `null`.
- Browser check: in each studio, move Experience down then up. The status must return to "All
  changes saved" and Save must disable.

---

## Suggested task split for the plan
1. **Pure helpers + node tests** (`lib/studio.ts`: `serverKey`, `adoptServerKey`, `keepIfEdited`,
   `jsonDraftDiffers`; `lib/formatting.ts`: `shownSectionOrder` + `diffFrom`). These are
   fail-first: write the tests, see red, then implement.
2. **Items 1+2+3**:
   - tailored parent and child in-place adoption;
   - base `save` variables + `keepIfEdited`;
   - `StudioSaveButton` `focusableWhenDisabled`;
   - pins;
   - SYSTEM.md §12 bullet rewrite + new dated gotcha (structural sharing / key order);
   - conventions *Tailored studio* sub-bullet rewrite (drop "until the post-save refetch remounts
     the editor").
3. **Item 4**: `RawJsonToggle` handle + `useRawJsonDraft`, both studios, pins, and a conventions
   *Raw JSON* sub-bullet plus a *Cmd/Ctrl+S* sentence on apply-then-save.
4. **Item 6**: gates + the pin update. Item 7: panel + pins. Item 5: Score panel + UploadDialog +
   pins.
5. **Gate**:
   - `pytest` (the pin files above, then the full suite);
   - `node --test lib/*.test.ts`;
   - `npx tsc --noEmit`, `npm run lint`, `npm run build`;
   - frontend slop ratchet (named);
   - `scripts/check_system_md.py`;
   - browser pass on a throwaway stack (memory: worktree verification recipe) covering every
     "Browser check" above, light + dark, 1280 and 375.

**Proposed SYSTEM.md §12 bullet (replacement, present tense):** "**Studio external-edit
dirty-guard**: TailoredResumeStudio compares `customized_json` by `serverKey` (sorted-key JSON).
A key its own Save returned moves the editor's baseline in place: no remount, so the working copy,
focus and status line survive. Any other new key remounts the editor only when it is clean or a
confirmed Rebuild; over unsaved edits it shows the Load-latest banner."

**Proposed new §12 gotcha:** "**The query cache keeps old key order** (date): structural sharing
reuses the previous object for every subtree whose content is unchanged, so `JSON.stringify` of
refetched data ≠ the mutation response whenever the server reordered keys (PATCH re-dumps in schema
order; Postgres-migrated drafts are JSONB order). Compare server JSON by `serverKey`."
