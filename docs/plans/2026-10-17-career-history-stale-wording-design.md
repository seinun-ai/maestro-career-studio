# Career history stops collecting stale wording: design

Approved by the owner 2026-10-17 (first form: a "replaces" link on rewrite drafts, retire on
approve, a retire-only groom) and revised with the owner on 2026-10-19 into the **claims with
wordings** model below, which supersedes the first form. Three of the six first-form decisions
were reversed; the record says which. No code yet; the implementation plan is
`docs/plans/2026-10-17-career-history-stale-wording.md`.

## Why

A base resume synced into career history (`kb_base_sync`, MCP `kb_sync_base`, the studio's "Add N
things to career history" pill) is deterministic and never edits a point. Per bullet it finds an
exact normalized match (in sync), else a cosine of 0.90 or more against the item's active points
(drift: a `from_source` port-log note, the Drifted badge), else it writes a fresh draft. Every real
rewrite of a base bullet therefore lands as a second bullet beside the first, a sync of an edited
base reads "Add 12 things", and the pile only grows. The one LLM merge
(`kb_consolidation.consolidate`) runs at import and is documented as unsafe to re-run. Grooming is
by hand in the `/career` draft inbox.

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
returns no match and every bullet reads as "new", silently.

## The owner's goal (2026-10-19)

Clicking Add on an edited base resume must not grow career history by a row per rewrite. A
rewrite should fold into the claim it rewrites; only a genuinely new claim should ask for review;
and each claim should read as one neutral line with every resume's phrasing of it underneath.
The same "is this the same claim?" decision should be one function, so every intake (sync today;
import, document mint and the write-backs later) improves together.

## The model

```
Item (a job, project, school, certification, other-section entry)   = KBEntity
  └─ Claim      state: draft | approved | retired                   = KBPoint (vocabulary unchanged)
       ├─ main wording   the claim's text; always one of the user's own sentences
       └─ wordings       where else it was phrased:
                           a resume's rewording      (KBPortLog from_source rows)
                           a resume's older copy     (KBPortLog to_resume rows that drifted)
                           an imported resume's text (KBPoint.merge_sources_json)
                           a combined claim          (a retired KBPoint whose merged_into_point_id is this claim)
```

Operations, all deterministic and LLM-free:

| Question | Operation | Where |
|---|---|---|
| Does this incoming text restate a claim on this item? | **place**: in sync, wording, or new | `services/kb_claims.place`, used by sync now, other intakes later |
| Which phrasing is the claim's line? | **Use as the main wording** | the claim's wordings popover |
| Was that fold wrong? | **Make its own bullet** (split) | the wordings popover |
| Are these two claims really one? | **Combine** | Tidy bullets, primary action |
| Is this claim still worth offering? | **Stop using** / **Use again** | the claim row today; a secondary action in Tidy bullets |
| Are these two similar but distinct? | **Not the same** | Tidy bullets |

Three rules make it safe:

1. **A wording is never offered to a resume.** Only a claim's main line is. A wrong fold hides a
   line from the picker until the user splits it out; it never puts the wrong words on a resume.
2. **Retire is about the claim, never the wording.** A retired claim keeps its wordings. Combine
   retires the losers reversibly and points them at the keeper. Retiring never touches a resume.
3. **The system never combines or retires on its own.** Intake attaches wordings, which is what
   drift already does today. Combine, retire, split and adoption are clicks (or an agent call the
   user said yes to).

## Owner decisions

- **Band.** A bullet whose best same-item match scores **0.80 or more** is a wording of that
  claim; under 0.80 it is a new claim. One threshold, `SYNC_WORDING_COSINE = 0.80`, shared by
  intake and groom. Not 0.75 (half the extra hits are distinct claims) and not 0.85 (misses half
  the real rewrites). *Supersedes the first form's two bands (drift 0.90+, replaces 0.80–0.90):
  the "replaces" draft is gone; the rewrite is a wording.*
- **Review on exception, not on every row.** The 0.80 to 0.85 band is a coin flip, and the user
  pays for a wrong fold only when they notice one, with one click (Make its own bullet) and no
  loss (the text is stored). *Supersedes the inbox switch "Retire the old bullet" and the
  Approve-all checkbox; the inbox is unchanged by this design.*
- **Storage.** A nullable self-referencing column `kb_points.merged_into_point_id` (`ON DELETE
  SET NULL`, indexed) marks a claim combined into another. Resume wordings stay port-log rows (no
  new `direction` value). No new wording table: the wordings list is derived on read from the
  four sources above. *Replaces `replaces_point_id`, which is not built.*
- **Main wording is chosen, never generated.** The claim's line is one of the user's own
  sentences; adoption is a PATCH of `text`, state unchanged. A true style-free rewrite would be an
  LLM call and an `derived_unverified` draft; it is out of this design and may be added later as
  one explicit per-claim button.
- **Groom shape.** A read-only report plus a review dialog. Groom computes clusters and returns
  them; nothing is written until the user acts on a cluster. Re-run safe by construction.
  Unchanged from the first form.
- **Groom's actions.** **Combine** is the primary action (keeper stays, the others become its
  wordings); **Stop using** on a non-keeper row covers "similar but stale"; **Not the same** is
  remembered in `kb_point_kept_pairs`. *Supersedes "retire the other(s)" as the only action.*
- **Honest when it cannot compare.** If the embedder is unavailable, every surface that depends on
  it says so instead of reading as "all new" or "nothing similar". Unchanged.

## Principles

- **Intake and groom stay LLM-free and write-light.** Classification uses only
  `services/ats/embeddings` (pinned model, memoized, out-of-process on small machines). A test
  pins that neither calls `llm.call_openai`.
- **Provenance never moves** (`inv-provenance-no-decay`). No path here reads `KBPoint.provenance`
  to rank or writes it. Combine and retire change only `state`, `approved_at` and
  `merged_into_point_id`; adoption changes only `text`; split creates a new `user_authored` point
  from the user's own resume text. A `user_cannot_confirm` point is never a wording target, never
  clustered and never a keeper, over and above being retired already.
- **Retiring never edits a resume.** Resumes that used a claim keep their text; the copy says so
  wherever a retire or a combine is offered.
- **One notion of "the same claim".** `kb_claims.place` is the only place the band is applied.

## 1. Data model

One Alembic revision (follow §12's revision-id rule; SQLite needs `batch_alter_table` for the FK,
and `migrations/env.py` runs with foreign keys off, so the table recreate is safe):

```
kb_points
  + merged_into_point_id  UUID NULL  REFERENCES kb_points(id) ON DELETE SET NULL, indexed
                          -- set by Combine; cleared by split (PATCH unmerge) and by Use again

kb_point_kept_pairs       -- "Not the same": groom skips these
  point_a_id  UUID NOT NULL REFERENCES kb_points(id) ON DELETE CASCADE
  point_b_id  UUID NOT NULL REFERENCES kb_points(id) ON DELETE CASCADE
  created_at  UTCDateTime NOT NULL
  PRIMARY KEY (point_a_id, point_b_id)   -- stored with point_a_id < point_b_id, always
```

No backfill. ORM: `KBPoint.merged_into_point_id` plus a one-directional `merged_into`
relationship (`remote_side=id`); `KBPointKeptPair` with a `kept_pair_key` helper that
canonicalises the pair order.

Schemas:

- `KBWordingOut {kind: resume|placed|merged|import, text, resume_keys: [str], section: str|None,
  point_id: UUID|None, adoptable: bool, splittable: bool}`. Derived in `_to_point_out` from the
  point's port-log rows, its `merge_sources_json` and the retired points merged into it; one row
  per distinct normalized text, and a text equal to the claim's own line is never a wording.
  `resume` (a `from_source` row): adoptable and splittable. `placed` (a `to_resume` or legacy row
  whose snapshot differs from the claim): neither, with the hint "Send to resume to update it",
  because adopting there would revert a KB edit. `merged`: adoptable and splittable (split is Use
  again plus clearing the pointer). `import` (`merge_sources_json`): adoptable, not splittable.
- `KBPointOut` gains `wordings: list[KBWordingOut]` and `merged_into_point_id: UUID | None`.
- `KBPointPatch` gains `unmerge: bool = False`: clears `merged_into_point_id`; combined with
  `state` in the same PATCH it is the split of a merged claim and the Undo of a combine.
- `KBCombineRequest {keeper_id, point_ids}` → `KBPointOut` (the keeper, with its new wordings).
- `KBSplitWordingRequest {text, resume_key: str|None}` → `KBPointOut` (the new claim).
- `SyncStatus` and `SyncResult` gain `compared_wording: bool` (false when the embedder failed).
  `SyncItemOut` is unchanged.
- `GroomReport` (section 4) and `KBKeepApartRequest/Response`.

## 2. Intake: `kb_claims.place` and the sync rung

`services/kb_claims.py` holds the one decision:

```
place(text, points) -> Placement(kind, point, score, compared)
  exact normalized match (point_text_key)           -> in_sync, that point
  best cosine >= SYNC_WORDING_COSINE (0.80)          -> wording, that point, score
  else                                               -> new
  compared = False when embed_texts raised (kind is then new, point None)
```

Candidates are the item's points with `state != retired` and `provenance != user_cannot_confirm`.
`kb_base_sync._ladder_bullet` calls `place` and maps `wording` to today's wire tier `drift`
(`counts.drift`, `recorded_drift`, `_apply_drift`'s `from_source` note, the `recorded` seen-set:
all unchanged, so the pill's number, MCP callers and the frontend types keep working). Nothing in
apply changes except the threshold: a rewrite writes one note and no point, as drift always did;
a second apply is still a no-op.

`classify()` and `apply()` return `compared_wording`, false when any `place` call could not
compare. Items still classify as `new` without a wording then, because the user asked for the add
and blocking would make sync unusable where fastembed cannot load. The pill popover appends
"Couldn't compare wording, so everything here reads as new."; `syncResultSentence` appends
"Couldn't compare wording."; MCP `kb_sync_base` returns the flag and its docstring says what it
means.

Copy: the breakdown line becomes "6 reworded bullets (kept as wordings)" and the result sentence
"Kept 6 rewordings." (was "we'll note the change" / "Noted N wording changes").

Other intakes (`consolidate_deterministic._write_verbatim_points`, the document mint, the gap and
tailoring write-backs) keep their own dedup this round and are listed as follow-ups; each is a
separate writer with its own tests and its own threshold today.

## 3. The claim's wordings

On the entity page's points list, the "Wording differs" badge becomes a **N wordings** chip on
every claim that has wordings (the Drifted case is one kind of wording). It opens a popover:

```
Wordings of this bullet
Data Scientist resume · experience                 Use as the main wording · Make its own bullet
"<the resume's rewording>"
Combined from another bullet                       Use as the main wording · Make its own bullet
"<the combined claim's text>"
Compact resume · experience                        Send to resume to update it
"<the older copy a resume still carries>"
```

- **Use as the main wording** sends `PATCH {text}`; state is unchanged, so an approved claim stays
  approved (the wording is the user's own). Toast "Bullet updated" with Undo (PATCH the old text
  back). The next classify reads in sync; the row leaves the list because its text now equals
  the line.
- **Make its own bullet** on a `resume` wording sends `POST /api/kb/points/{id}/split-wording
  {text, resume_key}`: a new approved claim on the same item (`origin=base_sync`,
  `provenance=user_authored`), and the matching `from_source` rows are re-pointed to it so the
  resume's placement history follows the words. On a `merged` wording it sends `PATCH {state:
  "approved", unmerge: true}` on that point. Toast "Now its own bullet" with Undo (delete the new
  point and re-point the rows back; or re-combine).
- Several resumes with one wording are one row naming both resumes; adopting leaves the others.
- A retired claim whose `merged_into_point_id` is set does not appear in the points list's
  retired group; it is a wording of its keeper. Use again on it (from the popover's split) brings
  it back as a claim.
- The draft inbox is unchanged: a new claim is reviewed as today, and a rewrite never reaches it.

## 4. Groom

### Service

`services/kb_groom.py`, `groom_entity(db, entity_id) -> GroomReport`, read-only, no LLM:

1. Candidates: the item's points with `state != "retired"` and `provenance != "user_cannot_confirm"`,
   drafts included (they are part of the pile).
2. Embed every text in one `embed_texts` call; cosine every pair.
3. Edges at `SYNC_WORDING_COSINE` (0.80) and above, minus pairs in `kb_point_kept_pairs`.
4. Connected components (single link) of size two or more are clusters. Single link is chosen
   on purpose: a chain of rewrites (A→B→C) is one claim even when A and C fall under 0.80.
5. Keeper proposal, in order: approved over draft, then most recently `updated_at`, then longest
   text, then id. The rule is stated in the dialog so the proposal is explainable.
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

Deterministic: same texts, same pinned model, same machine, same report.

### Endpoints

- `GET /api/kb/entities/{id}/groom` → `GroomReport`. 404 unknown item. Sync def (CPU work).
- `POST /api/kb/points/combine {keeper_id, point_ids}` → the keeper's `KBPointOut`. Same item
  required (400), keeper not retired and not `user_cannot_confirm` (400), unknown id 404. Each
  other point: `state=retired`, `approved_at=None`, `merged_into_point_id=keeper`. Points already
  merged elsewhere are re-pointed. Idempotent.
- `PATCH /api/kb/points/{id} {state, unmerge: true}` is the split and the Undo of a combine.
- `POST /api/kb/points/keep-apart {point_ids}` records every unordered pair among the ids (a
  cluster of three records three pairs); same item required (400); idempotent.
  `DELETE /api/kb/points/keep-apart` with the same body forgets them (the Undo of "Not the same").
- Retiring one member is `POST /api/kb/points/bulk-state {ids, state:"retired"}`, unchanged.

### Web

On the entity page, next to the bullets header, a **Tidy bullets** button, shown when the item
has two or more active bullets. It opens a dialog:

```
Similar bullets on {item title}
These say nearly the same thing. Keep one as the bullet and fold the others into it as wordings.
Nothing changes on your resumes.
We suggest keeping the approved one, then the most recently edited, then the longest.

┌ 93% similar ──────────────────────────────────────────────────────────┐
│ (•) Keep this one   Cleansed, standardized, and validated 2M+ …  Approved · used on 1 resume │
│ ( )                 Cleansed, standardized, and validated 2M+ …  Approved        [Stop using] │
│                                           [Combine into one]  [Not the same] │
└───────────────────────────────────────────────────────────────────────┘
```

- "Keep this one" is a radio with the proposed keeper preselected. **Combine into one** sends
  the combine request; toast "Combined 2 bullets into one. {keeper} stays." with Undo (PATCH each
  loser back to its prior state with `unmerge`). The cluster leaves the list.
- **Stop using** on a non-keeper row retires that one claim (bulk-state), for "similar but
  stale"; toast "Won't be offered again" with Undo (PATCH back). The cluster re-forms from the
  rest on the next read, which is right.
- **Not the same** records the kept pairs; toast "Won't suggest these again" with Undo (DELETE).
- Footer: "Done". No "Combine all": each cluster is one decision.
- Empty: "No similar bullets here." Embedder failed: "Couldn't compare wording right now." with
  Retry. Loading: a skeleton of two clusters.
- While the dialog is open the points list behind it refetches on each action.

### MCP

- `kb_groom_entity(entity_id)`, read-only, returns the `GroomReport`. Docstring: deterministic,
  zero LLM calls, proposes only; acting is `kb_combine_points` for one claim in other words and
  `kb_retire_points` for a stale one.
- `kb_combine_points(keeper_id, point_ids)`, write, the same consent convention as
  `kb_approve_points` (the state written is the user's decision); reversible from `/career`, so
  `destructive=False`, `idempotent=True`.
- `kb_retire_points(point_ids)`, the retire twin of `kb_approve_points`, same gate, per-id honest
  results via bulk-state; `destructive=False`, `idempotent=True`.
- "Not the same", split and adoption stay web-only this round. `kb_edit_point` still cannot
  change state.
- `docs/agent-surfaces.md` lists the three tools; the career profile and the full profile get them.

## 5. What does not change

- The draft inbox: rows, Approve, Move, Discard, Approve all shown. A rewrite never reaches it.
- `recorded` still silences a wording the KB already notes; the pill's N is still new +
  `skills_new` + unrecorded rewordings.
- Import consolidation, `consolidate_deterministic`, `merge_entities`, the gap flow's write-back,
  skills merge and title upgrades are untouched.
- No surface combines, retires, splits or rewrites without a click, in the web or from an agent.
- Composition and the career export still read only approved claims' main lines.

## 6. Build and test

Order: migration and models → `kb_claims.place` and the sync rung → the wordings read model →
combine, unmerge and split → groom service and endpoints → frontend plumbing and sync words →
the wordings popover → the Tidy bullets dialog → MCP tools → docs. Each step lands with its tests;
the plan document splits them.

Backend (`backend/tests`, xdist):

- `test_kb_base_sync_classify.py`: a 0.85 rewrite is `drift` (a wording) with `matched_point_id`;
  0.79 is `new`; 0.92 is `drift`; a retired or `user_cannot_confirm` point is never the target;
  `compared_wording` false and no matches when `embed_texts` raises; the band constant is 0.80;
  existing tests unchanged.
- `test_kb_base_sync_apply.py`: a 0.85 rewrite writes one `from_source` note and no point; apply
  twice is still a no-op; `compared_wording` in the result.
- `test_kb_sync_router.py`: both routes carry `compared_wording`.
- `test_kb_claims.py`: `place` on fixed vectors returns each kind with the right point and score;
  excludes retired and `user_cannot_confirm`; reports `compared=False` on failure.
- `test_career_kb_models.py`: `merged_into` round-trips and nulls when the keeper is deleted;
  `kept_pair_key` is canonical; kept pairs cascade with either point.
- `test_kb_wordings.py`: wordings derive from each of the four sources with the right
  `adoptable`/`splittable`; one row per distinct text; a text equal to the line is excluded;
  combine retires and points the losers, leaves the keeper's text and provenance alone, 400 on
  mixed items or a retired keeper, 404 unknown, idempotent; `unmerge` PATCH clears the pointer and
  sets the state given; split-wording creates an approved claim and re-points the rows, after
  which classify reads the bullet as in sync; adoption keeps the state; entity detail lists a
  merged claim under its keeper and the points list hides it from the retired group (source pin).
- `test_kb_groom.py`: fixed vectors give deterministic clusters; single link joins a chain; keeper
  rule in each tiebreak order; kept pairs break an edge; drafts included, retired and
  `user_cannot_confirm` excluded; one-point item is empty; embedder failure sets
  `compared_wording` false; a combined cluster is gone on the next report; keep-apart canonical
  order, idempotent, same-item 400, cascade on point delete, DELETE forgets.
- `test_kb_provenance_stamping.py::test_no_writer_flips_user_cannot_confirm` gains the new
  writers (combine, bulk retire, split-wording, adoption) and `test_every_point_creation_site_stamps_provenance`
  gains the split-wording site (`user_authored`).
- A pin that `kb_claims.place`, `kb_base_sync.classify/apply` and `kb_groom.groom_entity` never
  call `llm.call_openai` (monkeypatch it to raise).
- `test_db_portability.py` and `test_migration_model_parity.py` pick up the new column and table.
- `mcp_server/tests`: `kb_groom_entity` wires to the GET; `kb_combine_points` and
  `kb_retire_points` state the gate and forward ids; `kb_sync_base` passes `compared_wording`
  through.

Frontend (`node --test` on pure modules, as `kb-sync-words.test.ts`):

- `kb-sync-words`: the reworded line says "kept as wordings"; the result says "Kept N
  rewordings."; both gain the "Couldn't compare wording" line only when `compared_wording` is false.
- `kb-wordings`: the chip label; which rows get Use as the main wording, Make its own bullet or
  the hint; the split request per kind; hidden merged claims.
- `kb-groom`: keeper preselected; Combine sends the keeper and the others; Stop using sends one id;
  Not the same sends every member; empty and failed states; the toasts.

Docs: `docs/entities/others.md` Career KB paragraph (the model, the one band, wordings, combine,
split, kept pairs, adoption), `docs/agent-surfaces.md` (three tools), `docs/frontend-conventions.md`
(the wordings chip and popover, Tidy bullets). SYSTEM.md §6 gets no new invariant:
`inv-provenance-no-decay` already covers the rule and its pin test grows instead.

## Follow-ups (not in this design)

- Route the other intakes through `kb_claims.place`: `consolidate_deterministic._write_verbatim_points`
  (import), the document mint, the gap write-back and the tailoring write-back
  (`_write_back_elicited_points`, which dedups at 0.90 today). Each is a separate writer with its
  own tests; one at a time, once sync has proven the band.
- A per-claim "Write a neutral version" button: one explicit LLM call, a `derived_unverified`
  draft, never automatic.
- The owner's KB holds two LoopMind project items that differ only by an em dash versus a hyphen;
  `find_near_identity` should have matched them. Worth a look at `_near_project` and a
  `merge_entities` by hand meanwhile.
- A KB-wide "items with similar bullets" count would need embedding every item on list load; not
  until the per-item action has earned it.
