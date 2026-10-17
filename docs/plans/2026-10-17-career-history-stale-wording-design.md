# Career history stops collecting stale wording: design

Approved by the owner 2026-10-17, after six decisions and one whole-design review. No code yet;
the implementation plan is the next document.

## Why

A base resume synced into career history (`kb_base_sync`, MCP `kb_sync_base`, the studio's "Add N
things to career history" pill) is deterministic and never edits a point. Per bullet it finds an
exact normalized match (in sync), else a cosine of 0.90 or more against the item's active points
(drift: a `from_source` port-log note, the Drifted badge), else it writes a fresh draft. Nothing in
that path links the new draft to the bullet it rewrites, merges, or retires anything. Every real
rewrite of a base bullet therefore lands as a second bullet beside the first, and the pile only
grows. The one LLM merge (`kb_consolidation.consolidate`) runs at import and is documented as
unsafe to re-run. Grooming is by hand in the `/career` draft inbox.

Measured on the owner's live KB on 2026-10-17 (pinned embedder `BAAI/bge-small-en-v1.5`, every
pair of active bullets on the same item):

| Cosine band | Pairs | What they are |
|---|---|---|
| 0.90 and up | 10 | the same bullet twice, both approved (`consolidated` next to `base_sync`) |
| 0.85 to 0.90 | 16 | rewrites of one claim with a changed detail ("Partnered with stakeholders…" / "Worked with business stakeholders to define KPIs, then built the Informatica pipelines…") |
| 0.80 to 0.85 | 15 | half rewrites, half distinct claims on one topic |
| 0.75 to 0.80 | 38 | mostly distinct claims ("MCP server exposing 34+ tools" / "Expanded the MCP server to 83 tools") |
| under 0.75 | 962 | unrelated |

One experience item has 13 active bullets and every one of them has a neighbour at 0.80 or above;
another has 42 active bullets, 16 of them with such a neighbour. Ten pairs at 0.90 and up exist
even though sync classifies that band as drift: when the embedder cannot load, `_best_cosine`
returns no match and every bullet reads as "new", silently. So the fix has two halves: stop the
next duplicate at sync time, and give the user a deterministic way to shrink what is already there.

## Owner decisions

- **Band.** A new draft carries a "replaces" link when its best match on the same item scores
  **0.80 to under 0.90**. Not 0.75 (half the extra hits are distinct claims) and not 0.85 (misses
  half the real rewrites). Drift stays at 0.90 and up, unchanged.
- **Storage.** A column on the point, `kb_points.replaces_point_id`, nullable, self-referencing,
  `ON DELETE SET NULL`. Not a port-log row (that table means "this wording appeared in this resume"
  and every reader of `direction` would learn a new value), not a tag (no FK, dangling on delete).
- **Approve gesture.** The inbox row shows the old bullet with a switch "Retire the old bullet", on
  by default; Approve does both in one request. Not two buttons, not a dialog after the fact.
- **Groom shape.** A read-only report plus a review panel. Groom computes clusters and returns them;
  nothing is written until the user keeps one and retires the rest through the existing bulk-state
  endpoint. Re-run safe by construction. Not persisted proposals, not draft points (with no LLM
  there is no merged text, so a draft would only duplicate the keeper).
- **Keep both.** Pairs the user marks "Not the same" are remembered in a small table so groom
  stops proposing them.
- **Drift note.** The Drifted badge becomes actionable: a popover lists each resume wording with
  "Use this wording". Sync itself still writes only the note. Drift does not also land in the inbox.

## Principles

- **Sync stays LLM-free and write-light.** Classification and groom use only
  `services/ats/embeddings` (pinned model, memoized, out-of-process on small machines). A test
  pins that none of them calls `llm.call_openai`.
- **Nothing is applied silently.** Sync adds a link to a draft; it retires nothing. Groom proposes;
  the user retires. Adoption of a resume's wording is one click, never automatic.
- **Provenance never moves** (`inv-provenance-no-decay`). No path here reads or writes
  `KBPoint.provenance`. Retire-on-approve and groom change only `state` and `approved_at`; "Use
  this wording" changes only `text`. A `user_cannot_confirm` point is never a replaces target and
  never clustered, over and above being retired already.
- **Retiring never edits a resume.** Resumes that used the old bullet keep their text; the copy
  says so wherever a retire is offered.
- **Honest when it cannot compare.** If the embedder is unavailable, every surface that depends
  on it says so instead of reading as "all new" or "nothing similar".

## 1. Data model

One Alembic revision (follow §12's revision-id rule; SQLite needs `batch_alter_table` for the FK):

```
kb_points
  + replaces_point_id   UUID NULL  REFERENCES kb_points(id) ON DELETE SET NULL, indexed
                        -- set by base sync on a 0.80–0.90 match; cleared when the draft moves item

kb_point_kept_pairs     -- "Not the same": groom skips these
  point_a_id  UUID NOT NULL REFERENCES kb_points(id) ON DELETE CASCADE
  point_b_id  UUID NOT NULL REFERENCES kb_points(id) ON DELETE CASCADE
  created_at  UTCDateTime NOT NULL
  PRIMARY KEY (point_a_id, point_b_id)   -- stored with point_a_id < point_b_id, always
```

No score is stored: it is a classification detail, and the inbox copy does not change with it.
No backfill: the owner's KB has no open drafts, and the existing approved duplicates are groom's
job. ORM: `KBPoint.replaces_point_id` plus a `replaces` relationship (`remote_side=id`,
`post_update` not needed since the link is one-directional); `KBPointKeptPair` with a helper that
canonicalises the pair order.

Schemas:

- `KBPointOut` gains `replaces: KBReplacedOut | None` with `{id, text, state, usage_count}`,
  resolved by one extra `selectinload` in the inbox list and `_to_point_out`. Null when the link
  is null or the target is gone.
- `KBPointPatch` gains `retire_replaced: bool = False`. Honoured only when the patch sets
  `state="approved"`, the point has a live link and the target is not retired; otherwise ignored,
  never an error. The response is the approved point; the retired one is in `replaces.state`.
- `KBPointBulkState` gains `retire_replaced: bool = False`, same rule per id, and each result row
  gains `retired_replaced: UUID | None`.
- `SyncItemOut` gains `replaces_point_id: UUID | None` and `replaces_score: float | None`.
  `SyncStatus` and `SyncResult` gain `compared_wording: bool` (false when the embedder failed).
- New `GroomReport` (section 4).

## 2. Sync

`kb_base_sync.SyncItem` gains `replaces_point_id` and `replaces_score`. `_ladder_bullet` gets one
more rung after drift:

```
exact normalized match           -> in_sync
best cosine >= 0.90              -> drift            (unchanged)
0.80 <= best cosine <  0.90      -> new, replaces_point_id = best point
else                             -> new
```

`SYNC_REPLACES_COSINE = 0.80` sits next to `SYNC_DRIFT_COSINE`. The candidate set is the item's
active points minus any with `provenance == "user_cannot_confirm"` (belt and braces; they are
retired anyway). `_apply_new` copies the link onto the draft it creates. Everything else in apply
is unchanged: the duplicate check, the title upgrade, skills, the sync stamp. A second apply is
still a no-op (the draft now exists, so the bullet is in sync or drift).

`_best_cosine` reports failure instead of hiding it: `classify()` returns `compared_wording=False`
when any embed call raised. Items still classify as "new" without links, as today, because the
user asked for the add and blocking would make sync unusable where fastembed cannot load. The
pill popover appends "Couldn't compare wording, so everything here reads as new." and
`syncResultSentence` appends "Couldn't compare wording." MCP `kb_sync_base` returns the flag and
its docstring tells the agent to say so.

Counts do not change: a linked draft is still `new`, so the pill number, the breakdown lines and
`items_added` keep their meaning.

## 3. The draft inbox

A draft with a live link renders, under its text and actor chip, in the same muted block that
today shows "Wording from your resumes":

```
Replaces this bullet
<old bullet text>
Approved · used on 2 resumes                 (state word; the usage line only when used)
[switch, on]  Retire the old bullet
```

- **Approve** sends `{state:"approved", retire_replaced:<switch>}`. Toast with the switch on:
  "Bullet approved. Retired the old wording." with Undo; Undo restores the old bullet to its prior
  state and the new one to draft in one PATCH each. Switch off: "Bullet approved" as today.
- **Edit** before approving keeps the link (the user is refining the replacement).
- **Move to another item** clears the link server-side (`entity_id` change nulls
  `replaces_point_id`): a bullet on another item cannot be the one it replaces. The block
  disappears on the refetch.
- **Discard** the draft: nothing happens to the old bullet.
- **Approve all shown**: the confirm gains a checkbox, on by default, "Also retire the 3 bullets
  they replace" (count of listed drafts with a live link; the line is absent when zero). The bulk
  request carries `retire_replaced` for the batch; per-row switches do not apply to the bulk
  action.
- The old bullet may itself be a draft from an earlier sync. Retire still applies (uniform,
  reversible); the state word reads "Draft".
- A retired or deleted target hides the block: the link is null or its target retired, so the
  row is an ordinary draft.

Copy rule (frontend-conventions): the word is **bullet**, the resume is named through
`useResumeKeyLabel`, "retire" is spelled out as "Won't be offered again" only in the points list
where that phrase already lives; the inbox says "Retire the old bullet" because the object is
visible right there.

The entity page's points list shows nothing new for an approved point that replaced another;
the old one sits in the retired group as today.

## 4. Groom

### Service

`services/kb_groom.py`, `groom_entity(db, entity_id) -> GroomReport`, read-only, no LLM:

1. Candidates: the item's points with `state != "retired"` and `provenance != "user_cannot_confirm"`,
   drafts included (they are part of the pile).
2. Embed every text in one `embed_texts` call; cosine every pair.
3. Edges at `SYNC_REPLACES_COSINE` (0.80) and above, minus pairs in `kb_point_kept_pairs`.
4. Connected components (single link) of size two or more are clusters. Single link is chosen
   on purpose: a chain of rewrites (A→B→C) is one claim even when A and C fall under 0.80.
5. Keeper proposal, in order: approved over draft, then most recently `updated_at`, then longest
   text, then id. The rule is stated in the panel so the proposal is explainable.
6. Clusters sort by their highest pair score, descending; members sort keeper first, then by
   their best score to the keeper.

```
GroomReport
  entity_id, entity_title
  compared_wording: bool            # false when the embedder failed; clusters is then []
  active_points: int
  clusters: [ { score: float,       # highest pair in the cluster
                keeper_id: UUID,
                members: [ { id, text, state, origin, provenance, usage_count,
                             best_score: float } ],
                pairs: [ [id, id, score] ] } ]
```

Deterministic: same texts, same pinned model, same machine, same report. The band constant is
shared with sync so "similar" means one thing.

### Endpoints

- `GET /api/kb/entities/{id}/groom` → `GroomReport`. 404 unknown item. Sync def (CPU work).
- `POST /api/kb/points/keep-apart` `{point_ids: [a, b, …]}` → records every unordered pair among
  the ids (a cluster of three records three pairs); same item required (400 otherwise); idempotent.
- `DELETE /api/kb/points/keep-apart` same body → forgets those pairs (the Undo of "Not the same").
- Retiring the non-keepers is `POST /api/kb/points/bulk-state {ids, state:"retired"}`, unchanged.

### Web

On the entity page, next to the bullets header, a **Tidy bullets** button, shown when the item
has two or more active bullets. It opens a dialog:

```
Similar bullets on {item title}
These say nearly the same thing. Keep one and retire the rest. Retired bullets stay on
resumes that already use them.

┌ 0.93 similar ─────────────────────────────────────────────────┐
│ (•) Keep this one   Cleansed, standardized, and validated 2M+ … │  Approved · used on 1 resume
│ ( )                 Cleansed, standardized, and validated 2M+ … │  Approved
│                                      [Retire the other]  [Not the same] │
└───────────────────────────────────────────────────────────────┘
```

- "Keep this one" is a radio with the proposed keeper preselected; "Retire the other(s)" retires
  every non-selected member, toast "Retired 2 bullets. {keeper} stays." with Undo (bulk-state back
  to each prior state). The cluster leaves the list.
- "Not the same" records the kept pairs, toast "Won't suggest these again" with Undo (the DELETE).
- Footer: "Done". No "Retire all suggestions" button: each cluster is one decision.
- Empty: "No similar bullets here." Embedder failed: "Couldn't compare wording right now." with
  Retry. Loading: a skeleton of two clusters.
- While the dialog is open the points list behind it refetches on each retire, so closing it shows
  the result.

### MCP

- `kb_groom_entity(entity_id)`, read-only, returns the `GroomReport`. Docstring: deterministic,
  zero LLM calls, proposes only; to act, show the user each cluster and call `kb_retire_points`
  with the ids they drop.
- `kb_retire_points(point_ids)`, the retire twin of `kb_approve_points`, behind the same consent
  gate (one yes per call), per-id honest results via bulk-state. Retiring is reversible from
  `/career`, so `destructive=False`, `idempotent=True`.
- "Not the same" stays web-only this round; the agent can ignore a cluster. `kb_edit_point`
  still cannot change state.
- `docs/agent-surfaces.md` lists both tools; the career profile and the full profile get them.

## 5. The drift note

The Drifted badge on a point (points list) becomes a popover trigger:

```
Reworded on a resume
Data Scientist resume · experience
"<the base's wording>"                           [Use this wording]
```

- One row per `from_source` usage whose wording differs from the point (`drifted` is already
  computed per usage). "Use this wording" sends `PATCH {text}`; the web PATCH keeps the state, so
  an approved point stays approved (the wording is the user's own base). Toast "Bullet updated"
  with Undo (PATCH the old text back).
- After adoption the base bullet matches exactly, so the next classify reads in sync and the
  badge clears (`drifted` compares the note's text to the current point).
- `to_resume` rows (a port whose point was edited afterwards) show the resume's wording with no
  button and the line "Send to resume to update it": adopting there would revert the KB edit.
- Several resumes with different wordings list several rows; adopting one leaves the others as
  notes.
- A `user_cannot_confirm` point is retired, so it never carries a drift note; nothing to guard.

## 6. What does not change

- Drift at 0.90 and up still writes only the note; `recorded` still silences it.
- Import consolidation, `consolidate_deterministic`, `merge_entities`, the gap flow's write-back,
  skills merge and title upgrades are untouched.
- No surface retires, merges or rewrites without a click, in the web or from an agent.

## 7. Build and test

Order: migration and models → sync rung → inbox → groom service and endpoints → groom web →
drift popover → MCP tools → docs. Each step lands with its tests; the plan document splits them.

Backend (`backend/tests`, xdist):

- `test_kb_base_sync_classify.py`: 0.80–0.90 item is `new` with `replaces_point_id` and score;
  0.79 has none; 0.90 is still `drift`; a retired or `user_cannot_confirm` point is never the
  target; `compared_wording` false and no links when `embed_texts` raises; existing tests unchanged.
- `test_kb_base_sync_apply.py`: the draft carries the link; apply twice is still a no-op; the
  link always points at a point on the draft's own item.
- `test_career_kb_router.py` (or a new `test_kb_replaces.py`): inbox resolves `replaces`;
  `retire_replaced` on approve retires the target and reports it; ignored when not approving,
  when there is no link, when the target is already retired; moving the draft clears the link;
  deleting the target nulls it (`SET NULL`); bulk-state with `retire_replaced`.
- `test_kb_groom.py`: fixed vectors (monkeypatched `embed_texts`) give deterministic clusters;
  single link joins a chain; keeper rule in each tiebreak order; kept pairs break an edge; drafts
  included, retired and `user_cannot_confirm` excluded; one-point item is empty; embedder failure
  sets `compared_wording` false; keep-apart canonical order, idempotent, same-item 400, cascade on
  point delete, DELETE forgets.
- `test_kb_provenance_stamping.py::test_no_writer_flips_user_cannot_confirm` gains the three new
  writers (retire-on-approve, groom retire, wording adoption).
- A pin that `kb_base_sync.classify/apply` and `kb_groom.groom_entity` never call
  `llm.call_openai` (monkeypatch it to raise).
- `test_db_portability.py` picks up the new column and table through `models/types.py`.
- `mcp_server/tests`: `kb_groom_entity` wires to the GET; `kb_retire_points` honours the consent
  gate and forwards ids; `kb_sync_base` passes `compared_wording` through.

Frontend (`node --test` on pure modules, as `kb-sync-words.test.ts`):

- `kb-sync-words`: breakdown and result sentences gain the "Couldn't compare wording" line only
  when `compared_wording` is false.
- Inbox: the Replaces block renders only with a live link; the switch defaults on; Approve sends
  `retire_replaced`; the Approve-all confirm counts linked drafts and omits the line at zero.
- Groom dialog: keeper preselected; "Retire the other(s)" sends the non-selected ids; "Not the
  same" sends every pair; empty and failed states.
- Drift popover: only `from_source` rows get the button; `to_resume` rows get the hint line.

Docs: `docs/entities/others.md` Career KB paragraph (the rung, the link, groom, kept pairs,
adoption), `docs/agent-surfaces.md` (two tools), `docs/frontend-conventions.md` (Tidy bullets,
the Replaces block). SYSTEM.md §6 gets no new invariant: `inv-provenance-no-decay` already covers
the rule and its pin test grows instead.

## Follow-ups (not in this design)

- The tailoring write-back (`_write_back_elicited_points`) dedups at 0.90 and could set the same
  link in the 0.80–0.90 band; separate writer, separate change.
- The owner's KB holds two LoopMind project items that differ only by an em dash versus a hyphen;
  `find_near_identity` should have matched them. Worth a look at `_near_project` and a
  `merge_entities` by hand meanwhile.
- A KB-wide "items with similar bullets" count would need embedding every item on list load; not
  until the per-item action has earned it.
