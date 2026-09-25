# Health check v3: bullets earn their place, one question each, a clear report — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task by task. Every
> executor prompt gets the Goal Card and the autonomy grade prepended.

**Revision 2 (2026-09-25).** Rewritten after a peer review with GPT (Codex, "Astra") over the walkie-talkie and the owner's
answers. Revision 1 hard-coded 4 frameworks × 8 blocks in Python. That was cut for three reasons:
- **Not really deterministic.** The model still chose the framework, so the score was still model judgment.
- **Score cliffs.** The same evidence got different "required" blocks under different labels.
- **Tech-shaped.** The research covered US tech/data roles.

Judgment now lives in ONE versioned backend prompt. Code keeps validation, arithmetic, flags, caching and the rewrite
guards.

A second Astra review of revision 2 found seven contract defects, all fixed in place:
- demoted number questions
- malformed-output handling and trivial quotes
- the dispute flow: `new_fact` wiring, cache bypass, persisted `metric_unavailable`, the model-version check and
  every reply branch
- the golden set's dev/test split, per-role thresholds and adversarial disputes
- the version regex
- batch undo
- language fixes going through the guards

## Goal Card

**Goal.** Every resume bullet earns its place with a number or with other concrete evidence (what the person did and
what came of it). The health check judges each bullet on that, asks it only for the one thing it lacks, and never
demands a number where one isn't natural. The report must be easy to read and quick to act on: questions can be
answered in one pass or card by card, and the user can tell the check in their own words why a flag is wrong.
Tailoring follows the same guidance when it writes bullets.

**Principles**
- **Judge the page, not the claim.** Only the bullet text is scored. A user's note may change how the text is READ;
  new facts count only after the user accepts them into the bullet.
- **Rewrites never invent.** `health_guards` (no new numbers, no lost entities, no placeholders) stays the only path
  to appliable text.
- **The prompt judges; code validates and counts.** Levels are a bounded enum. Scores, flags and gates are Python.
  Saved results are keyed by text + rubric version + model, so a re-run on the same text returns the same report.
- **Code checks structure, not judgment.** Its checks (verbatim quotes, a named measure target, a number-free
  alternative) catch malformed or invented output. They cannot prove the model's judgment is right. That is measured
  by the golden set, and the plan claims nothing more.
- **Works beyond tech.** The prompt's examples span roles (engineering, data, nursing, sales, design, research,
  operations). A held-out cross-role set is checked before the evaluator lands.
- **Desktop only** (1024px and up; check at 1280 and 1024).

**Non-goals**
- A hard-coded framework/block taxonomy, a resume-level quota of numbers, JD-aware scoring, an "AI-written" detector.
- Deferred by the owner (2026-09-25):
  - the one-at-a-time question mode (the table pass ships)
  - repeated-opener notes
  - an automatic framework check on tailored drafts
  - a dispute MCP tool

  Each gets a SYSTEM.md §11 item in Task 15.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo reality and log every deviation
(one line, with its reason) in *Deviation log*. Anything touching scope goes back to the planner, as does anything
touching the Goal Card or an interface other tasks use: the evaluation contract (Task 5), the finding fields (Task 6)
or the dispute API (Task 7). Never expand scope.

## Background (read once)

Local-only research (it quotes real resumes): `docs/ux/2026-09-24-health-check-research.md` in the
`resume-health-check-research-e04d21` worktree, with appendix A (resume practice) and appendix B (review UI/UX).
What matters is restated here.

**Today** (`backend/app/services/resume_lint.py`, `health_score.py`, `bullet_classify.py`,
`prompts/resume_bullet_classify.txt`):
- **One way up.** The model puts each bullet on a 5-level ladder, and only a number lifts a bullet past 0.5.
- **One question for every bullet.** Every "adjacent" bullet gets the identical question.
- **The UI sniffs question text.** The frontend picks the number form by matching that question's text
  (`isMetricAsk`).
- **Identical points.** "+N points" is the gain for jumping to 1.0, identical on every card.

**Evidence:**
- **Qualitative results count.** MIT: "Don't worry if you don't have exact numbers". Harvard: "quantify and qualify".
  Arizona and Columbia: not every bullet needs a number.
- **No sourced "percent of bullets" target exists.** What IS sourced: 34% of hiring managers call a resume with no
  quantified results *at all* a deal-breaker (CareerBuilder/Harris 2018).
- **Spelling errors have the strongest evidence of any defect** (PLOS One 2023, 445 recruiters).

**UI** (NN/g, GOV.UK/BDA, Material 3, Primer, Lighthouse, GitHub code scanning, Grammarly):
- **Group and label once.** Group by action and state each rule once.
- **Show the text being judged in full.** Never truncate or italicise it.
- **One primary button per view.**
- **Allow "not right".** Offer an answer with a reason, reversible.
- **Preview before accept-all, and offer undo instead of confirm.**

## Owner decisions (binding)

1. **Simpler design** (2026-09-25). A backend prompt judges each bullet. Code does validation, arithmetic, flags,
   caching, storage and rewrite guards. The skills explain and call this; they never score on their own.
2. **A bullet with a concrete result and no number can score 1.0.**
3. **The question is per bullet and asks for the one thing missing:** a number (only where one is natural), how, why,
   who used it, or what came of it. Every number question carries a no-number alternative.
4. **Disputes are free text.** A dispute is the same evaluation run with the user's note as context. It returns a
   revised assessment and a reply. New facts in the note come back as a proposed rewrite the user must accept. The
   manual "This rating is wrong…" override still wins; "Skip for now" stays.
5. **"No numbers anywhere" is a highlighted flag, not a penalty and not a threshold** (2026-09-25). It shows
   prominently in the summary band when no scored bullet carries a number, has zero score impact, and never counts
   how many numbers are "enough".
6. **Wording is flagged (zero score), never blocking** (2026-09-25). Spelling and grammar slips (reported by the
   AI) and clichés and filler words form one Wording checklist. Clichés and filler come from a word bank matched by
   code, which the user can edit (add, remove, reset to defaults), plus a "Never flag" list.
7. **The rubric lives in the repo** (`docs/health-check-rubric.md`) for transparency; the skills are the usage layer.
8. **The report's left rail is removed.**
9. **Tailoring shares the guidance.** Tailoring's bullet-writing prompts drop "a number in every line" and follow the
   same rubric wording.

## Before you start

- **Where to work:** a worktree off `main`, never the main checkout
  `/Users/ajeyds/Projects/maestro-career-studio`. Its `data/` is the owner's live database, and its Docker stack on
  3000/8001 is live.
- **Read:**
  - `SYSTEM.md`: the §4 index → `docs/entities/others.md` ResumeLintReport, then §6, §9, and §12 "Rewording a
    health `issue` orphans saved ask answers".
  - `docs/frontend-conventions.md`
  - `frontend/AGENTS.md`
- **Python:** `/opt/anaconda3/bin/python3`. Run pytest and ruff from `<worktree>/backend`. The suite is
  `pytest tests/ mcp_server/tests/ -q`. Record the baseline counts in *Gate results* before Task 1.
- **Frontend:** `npm run lint` (React Compiler rules at error level) and `npx tsc --noEmit`. Node tests are not in CI:
  pair every `lib/*.ts` behaviour with a source pin in `backend/tests/test_frontend_health_report.py`.
- **Prompt edits need a resync migration** (read `tests/test_prompt_sync_guard.py`). `get_prompt` returns the stored
  `settings` row, not the file. This plan resyncs by DELETING the row only when it still equals the previous default,
  so the next read re-seeds from the new file. Then refresh `migrations/prompt_defaults.lock.json` with the command in
  that test's `_REMEDY`.
- **Frozen finding ids:** `_fid` hashes `issue`. Where a new issue text replaces an old one on the same kind of
  question, pass the old text as `id_key` (Task 6 says which).
- **No real resume text in committed files** (the repo is public). Tests, docs, the golden set and commit messages
  use synthetic bullets.
- **Mutation-check every pin:** break the code it guards, see exactly that pin fail, then restore from a backup copy
  (never `git stash`).
- **Browser checks:** on your own uvicorn + `next dev`, on free ports, with their own SQLite file (SYSTEM.md §9).
- **Commits:** one per task, with the message given, ending with the session's attribution line. Never commit
  `docs/ux/`.

---

## Phase 1: UI quick wins (frontend only, ships alone)

### Task 1: Bullets are readable where they are judged

**Files:**
- Modify `frontend/components/resume-health/finding-cards.tsx`:
  - `SourceQuote` (~L465)
  - the question paragraph in `AskCard` (~L878, `text-sm italic`)
  - the notes rows (~L1106-1116, `text-xs italic` + `truncate block`)
- Modify `batch-ask-dialog.tsx:221` and `demonstrate-skill-dialog.tsx:206-209`.
- Test: `backend/tests/test_frontend_health_report.py`

**Rules:**
- **Bullet text is body text:** `text-sm text-foreground`, upright, wrapped, `max-w-[65ch]`.
- **Mark it as quoted with a 2px left rule** (`border-l-2 border-border pl-3`). No quote marks, no italics.
- **When space is tight,** use `line-clamp-3` plus a visible "Show all" toggle (`aria-expanded`), never a one-line
  `truncate`.
- **Muted text is for metadata only.** `text-muted-foreground` is for the entry label, "bullet 2", counts and
  timestamps.
- **The question is plain body text:** `text-sm text-foreground`, upright.

**Step 1: failing pins**

```python
import re

def test_judged_text_is_never_italic_or_one_line_truncated():
    batch = (_FRONTEND / "components/resume-health/batch-ask-dialog.tsx").read_text()
    for src in (_CARDS, batch):
        assert not re.search(r'className="[^"]*\bitalic\b', src), "judged text must be upright"
    quote = _CARDS[_CARDS.index("function SourceQuote"):]
    quote = quote[: quote.index("\n}\n")]
    assert "truncate" not in quote
    assert "text-muted-foreground" not in quote
    assert "line-clamp-3" in quote
```

**Step 2:** `pytest tests/test_frontend_health_report.py -q`. Expected: FAIL.

**Step 3: implement**

```tsx
function SourceQuote({ text, clamp }: { text: string; clamp?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-l-2 border-border pl-3">
      <p className={cn("text-foreground max-w-[65ch] text-sm", clamp && !open && "line-clamp-3")}>
        {text}
      </p>
      {clamp && text.length > 220 && (
        <button
          type="button"
          className="text-primary mt-0.5 text-xs underline-offset-2 hover:underline"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Show less" : "Show all"}
        </button>
      )}
    </div>
  );
}
```

Rename the `truncated` prop to `clamp` at every call site (`grep -rn "SourceQuote" frontend`), and remove `italic`
wherever the pin names it.

**Step 4:** pins, `npm run lint` and `npx tsc --noEmit` pass. Mutation-check: re-add `italic` and the pin fails.

**Step 5:** commit `fix(health): judged bullet text is upright, full-contrast and wraps`

### Task 2: Status as text; points once per group; notes collapsed

**Files:**
- Modify `finding-cards.tsx`:
  - `CollapsedRow` (~L599-665)
  - `FindingGroupHeader` (~L667)
  - `NotesTable` (~L950)
- Modify `frontend/lib/health-report.ts`: add `groupPoints`.
- Test: `frontend/lib/health-report.test.ts` and pins.

**Rules:**
- **One plain-text metadata line per row:** `bullet 2 · Specific, no result` (`text-xs text-muted-foreground`).
  No `Badge` pills for location or level; "weighted higher" becomes text.
- **Points appear once per group.** Drop the per-row `+{pts} points`. `FindingGroupHeader` shows `Up to +6 points`
  once, and nothing when the total is 0.
- **`NotesTable` starts collapsed.** Its heading is a disclosure button, "Notes (20). These don't change your
  score.", with `aria-expanded`.

**Step 1: failing node test**

```ts
test("groupPoints sums each finding's points once", () => {
  const fs = [{ level: 0.5 }, { level: 0.5 }, { level: 0.8 }] as never[];
  assert.equal(groupPoints(fs, 28), 2 + 2 + 1);
  assert.equal(groupPoints(fs, null), 0);
});
```

Pins:
- `"+{pts} points"` is gone from `_CARDS`.
- `FindingGroupHeader` uses `groupPoints`.
- `NotesTable` has `aria-expanded`.

**Step 3: implement**

```ts
export function groupPoints(
  findings: { level?: number | null; gain?: number | null }[],
  nScoreable: number | null | undefined,
): number {
  return findings.reduce((sum, f) => {
    if (f.gain != null) return sum + f.gain; // Task 6's honest per-finding gain
    const name = f.level == null ? null : levelNameForValue(f.level);
    return sum + (potentialPoints(name, nScoreable) ?? 0);
  }, 0);
}
```

(`levelNameForValue` inverts `LEVEL_VALUES`. Add it beside `levelNameOf` if nothing similar exists.)

**Step 4:** run the node tests, pins, lint and tsc, and check in the browser at 1280 and 1024.

**Step 5:** commit `fix(health): status as text, points once per group, notes collapsed`

---

## Phase 2: The evaluator (backend + small frontend)

### Task 3: The rubric doc and a cross-role golden set

This comes before the evaluator lands, so its judgment is checked on roles we didn't design for.

**Files:**
- Create `docs/health-check-rubric.md`. It is reference tier and follows the SYSTEM.md header contract; no dates in
  the body.
- Create `backend/tests/fixtures/health_golden.json`: synthetic bullets only.
- Create `backend/scripts/health_golden.py`: a manual script, not CI.
- Modify `SYSTEM.md` §4 table: add one row, `| Health rubric | [docs/health-check-rubric.md](docs/health-check-rubric.md) | what makes a bullet strong, levels, questions, flags — the rules the health check and tailoring share |`.
- Modify `docs/entities/others.md` ResumeLintReport: add a one-line pointer to the rubric.
- Create `backend/tests/test_health_rubric_doc.py`.

**Rubric content:**
- **The principle:** a bullet earns its place with a specific action and a concrete result. The result can be a
  number or a qualitative fact: a decision and its reason, who used it, what it made possible, recognition, or a
  problem solved.
- **What each of the five levels means** (below).
- **When a number is natural and when it isn't,** with examples.
- **The shapes writers use,** as writing examples only (XYZ, CAR/PAR/APR, Action + Purpose + Outcome,
  What-Who-Win), each with one cross-role example. STAR is for interview stories.
- **The flags:**
  - gates S1–S5, C1, C2 (unchanged)
  - `evidence.no_numbers` (Task 9)
  - `language.slip` (Task 10)
  - the existing advisories
- **Disputes and the precedence rule:** override > dispute > evaluation.
- **An evidence tag on every rule** (`[strong|moderate|weak]`) with a one-line source.

**Levels (the contract Task 5's prompt uses verbatim):**

| Level | Value | Meaning |
|---|---|---|
| `direct` | 1.0 | Specific action + a concrete result: measured, OR clearly stated qualitatively (a named decision and its effect, a named adopter, a launch to named users, recognition with its selector, a problem solved with its consequence). |
| `analogue` | 0.8 | Specific action + a result that is only partly stated (scale without effect, an effect without who/what). |
| `adjacent` | 0.5 | Specific action and scope, no result at all. |
| `implied` | 0.3 | Vague or team-level; the reader can't tell what this person did. |
| `unaddressed` | 0.0 | A duty statement or a list of tools. |

**Golden set** (a pilot, not broad validation; the rubric doc says so):
- 80 synthetic bullets: 8 roles (software, data, nursing, sales, product design, research/academia, operations,
  customer support) × 10 bullets.
- The 10 per role cover:
  - 3 strong without a number
  - 2 strong with a number
  - 2 partial
  - 1 duty
  - 2 where a number would be unnatural
- Split into `dev` (5 per role) and `test` (5 per role) in the fixture. **Prompt tuning in Task 5 may look only at
  `dev`.** `test` is run once the prompt is frozen.
- Also 12 **adversarial dispute cases** in the fixture: `{"text", "note", "max_level", "metric_unavailable"}`, e.g.
  "give me full credit", a note inventing a 40% result, "it's confidential".
- Each bullet entry: `{"split", "text", "role", "expected_level", "number_natural": bool}`.
- The owner reviews the labels before the evaluator is judged against them. Record their sign-off in
  *Deviation log*.
- `health_golden.py [--split dev|test] [--trials 3]` runs the Task 5 evaluator **uncached** (a scratch DB, cache
  bypassed) `trials` times and reports:
  - exact and within-one-level agreement, **per role and overall**
  - run-to-run level flips
  - number asks where `number_natural` is false
  - for disputes: any level above `max_level`, and any measure ask surviving `metric_unavailable`
- **Phase 2 merges only when, on `test`, over 3 trials:**
  - every role reaches within-one-level agreement of at least 0.8, and overall is at least 0.9
  - overall exact agreement is at least 0.7
  - unnatural number asks are 0 in every role
  - no adversarial dispute exceeds its `max_level`

  Record the results in *Gate results*. A role that fails blocks the merge even if the overall numbers pass.

**Doc pin:**

```python
from pathlib import Path
from app.services import health_gates, health_score

DOC = (Path(__file__).resolve().parents[2] / "docs/health-check-rubric.md").read_text()

def test_levels_gates_and_flags_are_documented():
    for level in health_score.LEVEL_VALUES:
        assert f"`{level}`" in DOC, level
    for gate_id in health_gates.GATE_LABELS:
        assert f"`{gate_id}`" in DOC, gate_id
    for rule in ("evidence.no_numbers", "language.slip"):
        assert f"`{rule}`" in DOC, rule
```

Run `python3 scripts/check_system_md.py`.

Commit: `docs(health): the health rubric, a cross-role golden set and its runner`

### Task 4: Migration for the evaluation cache and dispute table

**Files:**
- Create `backend/migrations/versions/980498217fe6_health_evaluations.py` (down_revision `9a5744f9b9d9`; check
  `alembic heads` first).
- Modify `backend/app/models/bullet_classification.py`.
- Create `backend/app/models/bullet_dispute.py` and register it in `app/models/__init__.py`.

**Schema:**

`bullet_classifications` gains:
- `rubric_version INTEGER NOT NULL` (server default `1`)
- `evidence_json` (JSONDoc, NULL)
- `question TEXT NULL`
- `ask_kind TEXT NULL`
- `measure_target TEXT NULL`
- `alt_question TEXT NULL`
- `language_json` (JSONDoc, NULL)

New table `bullet_disputes`:
- `content_hash TEXT PK`
- `note TEXT NOT NULL`
- `original_json` (JSONDoc, NOT NULL)
- `revised_json` (JSONDoc, NOT NULL)
- `reply TEXT NOT NULL`
- `suggestion TEXT NULL`
- `metric_unavailable BOOLEAN NOT NULL` (server default `expression.false()`, per the §12 gotcha)
- `rubric_version INTEGER NOT NULL`
- `model TEXT NULL`
- `created_at` (UTCDateTime, `default=utcnow`)

**Constraints:**
- Column types come only from `app/models/types.py` (§6 inv-single-dialect).
- Use `op.batch_alter_table` as in `9a5744f9b9d9`.
- The downgrade drops exactly what the upgrade adds.
- The model/migration parity test stays green.

Commit: `feat(health): store evaluations with their rubric version, and disputes`

### Task 5: The evaluator contract: prompt, validation, versioned cache

**Files:**
- Modify `backend/app/prompts/resume_bullet_classify.txt`: full replacement.
- Modify `backend/app/services/bullet_classify.py`.
- Create `backend/migrations/versions/d08dd68e4eff_resync_health_prompts.py` (down_revision `980498217fe6`).
- Modify `backend/migrations/prompt_defaults.lock.json`.
- Test: `backend/tests/test_bullet_classify.py`.

**Prompt** (keeps `$items_json`):

```
You judge resume bullets (and the summary) the way a careful recruiter reads them. Judge ONLY what
the text establishes. Do not reward adjectives. Give no scores.

A bullet earns its place with a SPECIFIC ACTION and a CONCRETE RESULT. The result may be a number,
or a clearly stated qualitative fact: a decision and what it made possible, who adopted or used the
work, a launch to named users, recognition and who gave it, a problem solved and its consequence.
A number is one kind of result, not the only kind.

Levels:
- "direct": specific action + a concrete result (measured OR clearly stated in words).
- "analogue": specific action + a result that is only partly stated (size without effect, or an
  effect without who or what).
- "adjacent": specific action and scope, no result at all.
- "implied": vague or team-level; the reader can't tell what this person did.
- "unaddressed": a duty statement ("responsible for", "worked on", "helped") or a list of tools.

"evidence": 1-3 short quotes copied EXACTLY from the text that justify the level (the action, the
result). Quote, never paraphrase.

"question": if the level is below "direct", ONE short question (<= 15 words) asking for the single
thing that would most strengthen THIS bullet: what came of it, who used it, why this approach,
what problem it solved, or a number. Null when the level is "direct".

Ask for a number ONLY when a number is natural for this result (speed, cost, volume, accuracy,
revenue, patients, users, time) AND the text already names the thing to measure. Then set
"ask_kind": "measure", "measure_target" to that thing (<= 6 words), and "alt_question" to a
no-number version of the question. Otherwise "ask_kind": "detail" and measure_target/alt_question
null. Research, design decisions, recognition, care quality, confidential work and ongoing work
usually need detail, not a number.

Examples across roles:
- "Chose event sourcing over CDC so auditors could replay any change, which cleared the SOC 2
  finding" -> direct (qualitative result).
- "Triaged 30+ ED patients per shift using ESI, escalating two sepsis cases the attending confirmed"
  -> direct.
- "Redesigned the onboarding flow in Figma" -> adjacent; question: "What changed for new users after
  the redesign?"; ask_kind detail.
- "Reduced invoice processing time by automating reconciliation" -> analogue; ask_kind measure;
  measure_target "invoice processing time"; alt_question "What did finance stop doing by hand?"
- "Responsible for vendor relationships" -> unaddressed; question: "What did you achieve with
  these vendors?"

Hints may accompany an item: "weak_opener" or "passive". Treat weak_opener as strong evidence for
"unaddressed" unless the text clearly shows an action and a result.

"language": up to 3 clear spelling or grammar slips as {"span": "<exact text>", "fix": "<corrected>"}.
Technical terms, names and abbreviations are NOT slips. [] when unsure.

Confidence 0.0-1.0. If torn between two levels, pick the LOWER and set confidence below 0.6.

Items (JSON): $items_json

Return JSON only: {"classifications": [one entry per input item, same ids]}, each entry:
  {"id": "...", "level": "...", "evidence": ["..."], "reason": "<= 12 words",
   "question": "..." | null, "ask_kind": "measure" | "detail" | null,
   "measure_target": "..." | null, "alt_question": "..." | null,
   "confidence": 0.0, "language": []}
```

**Validation in code** (`bullet_classify._validate(text, entry) -> dict | None`). Write the tests first; the fake
LLM returns the new shape, and the real validator runs.

```python
import math

RUBRIC_VERSION = 2
_LEVEL_RANK = ("unaddressed", "implied", "adjacent", "analogue", "direct")
_NUMBER_ASK = re.compile(r"\d|\bhow (?:many|much)\b|\bwhat (?:number|percent|percentage)\b"
                         r"|\bquantif|\bmetric", re.IGNORECASE)
_WORD = re.compile(r"[a-z][a-z'-]{3,}")


def _s(value, limit: int) -> str | None:
    """A trimmed string of at most `limit` chars, or None for anything else (the model may send
    numbers, lists or objects where a string belongs)."""
    return value.strip()[:limit] or None if isinstance(value, str) else None


def _confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(c, 0.0), 1.0) if math.isfinite(c) else 0.0


def _validate(text: str, entry: dict, *, metric_unavailable: bool = False) -> dict | None:
    """STRUCTURAL checks on one model entry. They catch malformed and invented output; they
    do not prove the judgment is right (the golden set measures that)."""
    level = entry.get("level") if isinstance(entry, dict) else None
    if not isinstance(level, str) or level not in LEVEL_VALUES:   # a list/dict level must not raise
        return None
    # Resolve applicability FIRST, so this very response's flag demotes its own number ask.
    metric_unavailable = metric_unavailable or entry.get("metric_unavailable") is True
    norm = " ".join(text.split()).lower()
    raw_ev = entry.get("evidence")
    raw_ev = raw_ev if isinstance(raw_ev, list) else []   # a bare string is not a list of quotes
    spans = []
    for s in raw_ev:
        s = _s(s, 200)
        # A quote must be verbatim AND carry content: at least 3 words, so "the" can't back a level.
        if s and len(s.split()) >= 3 and " ".join(s.split()).lower() in norm:
            spans.append(s)
    spans = spans[:3]
    if _LEVEL_RANK.index(level) > _LEVEL_RANK.index("adjacent") and not spans:
        level = "adjacent"

    question = _s(entry.get("question"), 200)
    ask_kind = entry.get("ask_kind") if entry.get("ask_kind") in ("measure", "detail") else None
    target = _s(entry.get("measure_target"), 60)
    alt = _s(entry.get("alt_question"), 200)
    # The target must name the bullet's own thing: at least half of its content words appear
    # as WHOLE words in the text (not as substrings of other words).
    text_words = set(_WORD.findall(norm))
    target_words = _WORD.findall(target.lower()) if target else []
    target_in_text = bool(target_words) and (
        sum(w in text_words for w in target_words) * 2 >= len(target_words))
    alt_ok = bool(alt) and not _NUMBER_ASK.search(alt)
    if ask_kind == "measure" and (metric_unavailable or not (target_in_text and alt_ok)):
        # Demote to a detail ask. The number question itself must go too: use the number-free
        # alternative when it is valid, else None (Task 6 falls back to static detail copy).
        ask_kind, question = "detail", (alt if alt_ok else None)
    if ask_kind == "detail" and question and _NUMBER_ASK.search(question):
        question = alt if alt_ok else None   # a "detail" ask may not smuggle in a number demand
    if level == "direct":
        question, ask_kind = None, None
    elif question is None:
        ask_kind = "detail"
    keep_measure = ask_kind == "measure"

    raw_lang = entry.get("language")
    langs = []
    for x in raw_lang if isinstance(raw_lang, list) else []:
        span, fix = (_s(x.get("span"), 80), _s(x.get("fix"), 80)) if isinstance(x, dict) else (None, None)
        if span and fix and span != fix and span in text:
            langs.append({"span": span, "fix": fix})
    return {"level": level, "evidence": spans, "question": question, "ask_kind": ask_kind,
            "measure_target": target if keep_measure else None,
            "alt_question": alt if keep_measure else None,
            "language": langs[:3], "reason": _s(entry.get("reason"), 120) or "",
            "confidence": _confidence(entry.get("confidence")),
            "new_fact": _s(entry.get("new_fact"), 300),          # dispute calls only (Task 7)
            "metric_unavailable": metric_unavailable}
```

**Cache rules in `classify_items`:**
- **Miss:** a row whose `rubric_version != RUBRIC_VERSION` or whose `model` differs from the current smart model, and
  that has no `override_level`, is a miss.
- **Overrides always win.** A row with an override returns it, with `question=None` (the user settled it).
- **Writes:** `_classify_batch` stores every validated field plus `rubric_version`.
- **`_result` output:** returns `evidence`, `question`, `ask_kind`, `measure_target`, `alt_question` and `language`
  alongside the existing keys. `uncertain` still comes from confidence.

**Tests to add:**
- A qualitative `direct` with a verbatim quote stays direct and has no digits.
- A `direct` whose evidence is not in the text drops to `adjacent`.
- A `direct` backed only by a trivial quote ("the", two words) drops to `adjacent`.
- Demotions to `detail`:
  - a `measure` ask missing `measure_target` or `alt_question` becomes `detail`, and its "How many…?" question is
    replaced by the alternative or dropped
  - a `measure_target` naming nothing in the text demotes the ask
  - an `alt_question` that asks "how many" demotes the ask and is not shown
  - a `detail` question demanding a number is swapped for the alternative or dropped
- `direct` never carries a question.
- A response with `metric_unavailable: true` AND a measure ask comes back as a detail ask from that same call.
- A target sharing only a substring ("rate" inside "accurate") demotes the ask.
- Malformed output, one test each:
  - `level` as a list or a dict (returns None; must not raise TypeError)
  - `evidence` as a string
  - `question` as a number
  - `confidence` as `"high"` or `NaN`
  - `language` as a dict

  None of these raises; each degrades as specified.
- A changed `rubric_version` or model re-evaluates.
- An override survives a version change.
- A `language` span not in the text is dropped.
- A garbage entry degrades to `implied` + `uncertain` (as today).

**Resync migration `d08dd68e4eff`:** pin the PREVIOUS prompt text (`git show main:backend/app/prompts/resume_bullet_classify.txt`),
then `DELETE FROM settings WHERE key = 'prompt.resume_bullet_classify' AND value = :old`. The downgrade is a no-op,
with a docstring saying why. Refresh the lock file.

**Golden gate:**
1. Tune the prompt's examples, not code, against `--split dev` only.
2. Freeze the prompt.
3. Run `--split test --trials 3` once, with the dispute cases (they need Task 7; run them there if Task 7 is not
   merged yet).
4. Paste both results into *Gate results*.

If `test` fails, report it to the planner. Don't tune against `test`.

Commit: `feat(health): one evaluator prompt judges; code validates quotes and number asks`

### Task 6: Findings carry the bullet's own question; honest points; next grade

**Files:**
- Modify `backend/app/services/resume_lint.py`:
  - `_ladder_findings` and `_classification_fields`
  - `LADDER_COPY` is kept as the static fallback copy
- Modify `backend/app/routers/resume_lint.py` (`LintReportRead.next_grade`).
- Modify `backend/app/services/health_guards.py`: `guarded_rewrite(..., question="")`.
- Modify `backend/app/prompts/resume_bullet_rewrite.txt`, adding:

  ```
  The question this rewrite should answer (with the candidate's context if given): $question
  ```

  plus the rule "A qualitative result is a complete answer; never add a number the candidate did not give". Add this
  key to the `d08dd68e4eff` resync if still unmerged, otherwise to a new one.
- Modify `frontend/lib/types.ts` and `frontend/lib/health-report.ts`.
- Modify `backend/mcp_server/server.py`: the health tools' docstrings, one sentence (stay under the docstring budget).
- Test: `test_resume_lint.py`, `test_health_invariants.py`, `test_health_guards.py` (fake `llm.call_openai`, never
  the guard), `health-report.test.ts`, pins.

**New finding fields** (additive; other tasks depend on these):
- `question`: the evaluator's question, or the static fallback
- `ask_kind`: `"measure" | "detail" | "reword" | null`
- `measure_target`, `alt_question`
- `evidence: list[str]`
- `gain: int`

**The report** gains `next_grade: {"grade": str, "points": int} | null`.

**Issue copy per ask kind** (static, short; the question carries the specifics):

```python
ASK_ISSUE = {
    "measure": {"issue": "Specific, but has no number.",
                "id_key": "Specific, but carries no number.",   # frozen: old adjacent ask
                "why": "This result is usually measured; a number makes it checkable.",
                "how": "Add the number, or answer the no-number question instead."},
    "detail":  {"issue": "Says what you did, not what came of it.",
                "why": "Every strong bullet ends in a result; it doesn't have to be a number.",
                "how": "Answer the question below in a few words."},
}
```

**Routing:**
- **Direct:** no finding. **Cold analogue:** stays silent, as today.
- **The ask** uses `r["question"]` when present, else `FALLBACK_QUESTION[level]`. `ask_kind = r["ask_kind"] or
  "detail"`. The fallback questions are number-free by construction, because a fallback is always a detail ask. Never
  fall back to `LADDER_COPY[...]["question"]`: the adjacent one asks for a number.

  ```python
  FALLBACK_QUESTION = {
      "analogue": "What came of this: what changed, or who used it?",
      "adjacent": "What came of this work: what changed, or who used it?",
      "implied": "What did you personally do here?",
      "unaddressed": "What did you personally do here, and what changed because of it?",
  }
  ```

  Test: no fallback question matches `bullet_classify._NUMBER_ASK`.
- **An analogue with evidence containing a digit** keeps `id_key = LADDER_COPY["analogue"]["id_key"]`, so saved
  answers stay attached.
- **The fix path** (≤ 0.30) is unchanged, with `ask_kind = "reword"`.

**`gain`:**
- Ask and fix findings: `round(100 * (value_of(next level up) - value) / n_scoreable)`.
- Summary findings: `0` (not scored).

**`next_grade`:**
- The band floor above the score and the points needed.
- `None` when a gate caps the score; the frontend then says which check caps it.

**Frontend:**

```ts
export function isMetricAsk(f: { ask_kind?: string | null; question?: string | null }) {
  return f.ask_kind ? f.ask_kind === "measure" : (f.question ?? "").includes(METRIC_ASK_NEEDLE);
}
export function nextGradeLine(r: { next_grade?: { grade: string; points: number } | null }) { /* "1 point to A" */ }
```

- The fallback in `isMetricAsk` covers reports stored earlier.
- `AskCard`:
  - For `measure` asks: show `MetricAskInput`, with the `measure_target` as its label ("Number for: invoice
    processing time"), and a "No number? Answer this instead" link that swaps to a textarea showing
    `alt_question`.
  - Every other ask: the free-text box.
- `groupPoints` prefers `gain` (Task 2 already reads it); remove `potentialPoints` once nothing else uses it.

**Invariants to add:**
- No finding has `ask_kind == "measure"` without both `measure_target` and `alt_question`.
- A `direct` bullet produces no ask.
- **Size invariance** still holds.
- **Advisories are free** still holds.
- **Determinism** (five runs over cached evaluations, zero variance) still holds.

Commit: `feat(health): each bullet gets its own question; honest points and distance to the next grade`

---

## Phase 3: Disputes and flags

### Task 7: Disputes re-evaluate with the user's note (backend)

**Files:**
- Create `backend/app/services/health_disputes.py`.
- Modify `backend/app/prompts/resume_bullet_classify.txt`: reuse it. The dispute call sends ONE item with an extra
  `"note"` field. Add this paragraph, and extend the output schema line with
  `"new_fact": "..." | null, "metric_unavailable": true | false`:

  ```
  If an item has a "note" from the candidate, use it only to understand what the text means.
  Never credit a result the text does not show. If the note states a fact that is not in the
  text, copy that fact into "new_fact". If the note says a number does not exist, was never
  measured, or cannot be shared, set "metric_unavailable": true. Items without a note: null
  and false.
  ```

  Include this in the `d08dd68e4eff` resync if it is unmerged, else in a new one.
- Modify `backend/app/services/bullet_classify.py`: apply disputes.
- Modify `backend/app/routers/resume_lint.py`:
  - `POST /{kind}/{key}/dispute`
  - `GET /{kind}/{key}/disputes`
  - `DELETE /disputes/{content_hash}`
- Modify `frontend/lib/api.ts` and `types.ts`.
- Test: `backend/tests/test_health_disputes.py` and `test_resume_lint_router.py`.

**Contract:**

```
POST /api/resume-lint/{kind}/{key}/dispute
  body: {"location": {...}, "expected_content_hash": "<16 hex>", "note": "<1..1000 chars>"}
  200: {"before": {"level", "question"}, "after": {"level", "question", "ask_kind"},
        "reply": str, "suggestion": str | null, "content_hash": str}
  409: text changed since the report (the same CONTENT_CHANGED guard as answer_ask)
  422: empty note
```

**Service** `dispute(db, text, note) -> dict`:
1. **Bypass the text cache.** Call the batch evaluator directly for
   `[{"id": hash, "text": text, "note": note, "hints": [...]}]`. Don't read the cache first, and never write the
   dispute result into `bullet_classifications`: the ordinary evaluation of that text must stay untouched. Pass the
   result through the same `_validate`. The quote rule stops invented quotes; it cannot stop an over-generous reading
   of a real quote. The adversarial golden cases measure that.
2. **Persist applicability.** When the result has `metric_unavailable`, store it on the dispute. From then on,
   `_validate(..., metric_unavailable=True)` is applied to every evaluation of that hash, so a number is never asked
   for that text again, whatever the model says later.
3. **`reply`** is written in code from the before/after comparison, never by the model. The cases:
   - level up → "Re-read: this now counts as <level words>."
   - level down → "Re-read: on a closer look this reads as <level words>. <question>"
   - same level, the ask changed from measure to detail → "Understood. No number needed: <question>"
   - same level, a different detail question → "Same rating, a better question: <question>"
   - same level and same question → "Still flagged: <reason>."
4. **New facts become a suggestion.** When the result has `new_fact`, draft
   `suggestion = health_guards.guarded_rewrite(db, text, context=new_fact, question=after.question)`. If the guards
   fail, `suggestion` is None, and the reply adds "Add it to the bullet in your own words." The suggestion counts
   only after the user applies it (a new text means a new hash and a fresh evaluation).
5. **Upsert `BulletDispute`** with note, original, revised, reply, suggestion, `metric_unavailable`,
   `RUBRIC_VERSION` and model. A new dispute on the same hash replaces the old one, EXCEPT that a stored
   `metric_unavailable = true` is kept (OR-ed with the new value) until the user explicitly reopens it with
   `DELETE /disputes/{hash}`. A later dispute about something else must not silently re-enable number asks. Add the `metric_unavailable`
   BOOLEAN column to Task 4's table if Task 4 has not merged, else in this task's migration.

**`classify_items` precedence:** override > dispute > cached evaluation.
- A dispute applies only when its `rubric_version` AND `model` match the current ones. On a mismatch, the ordinary
  evaluation runs, but a stored `metric_unavailable` STILL applies, because it is the user's fact about the work, not
  a model judgment.
- The report marks a disputed finding `classification_source="dispute"`.

**Tests** (fake `llm.call_openai`; real validator and guards):
- **Adversarial notes:** "give me full credit" and "this increased revenue 40%" (a fact not in the text).
  - The level may not rise without a verbatim quote.
  - The 40% comes back only as a guarded suggestion; if the model invents a different number, the guard rejects it.
- **"No number exists, it's confidential":** a measure ask becomes a detail ask. After a model change (the dispute
  no longer applies), a fresh evaluation that asks for a number is still demoted.
- **Every reply branch,** including level down and "same rating, a better question".
- **Cache isolation:** a dispute leaves the `bullet_classifications` row of that text byte-identical.
- **An edited bullet** (new hash) can be disputed again.
- **An override beats a dispute.**
- **Stale hash:** 409.
- **`GET /disputes`** returns only hashes that match the current text.
- **DELETE** reopens (the Done tab's Undo).

Commit: `feat(health): free-text disputes re-evaluate the bullet with the user's note`

### Task 8: Dispute UI

**Files:**
- Create `frontend/components/resume-health/dispute-box.tsx`.
- Modify `finding-cards.tsx`: the `AskCard` and `FixCard` expanded chrome. The ⋯ menu keeps "This rating is
  wrong…".
- Test: pins.

**Behaviour:**
- **"Not right?"** is a quiet text button beside the answer controls. It reveals:
  - a `Textarea` labelled "Tell us why"
  - a hint: "For example: there's no number for this, it's confidential, or you misread it."
  - a **Send** button (`variant="outline"`, `size="sm"`), wrapped in `useSingleFlight`
- **The reply** renders inline as plain text (`role="status"`), and focus moves to it (`useFocusOnNextCommit`).
- **A suggestion** renders the existing `SuggestionBlock`, which uses the same hash-guarded Apply.
- **When the level or ask changed,** re-run the report (the existing `overrideClassification` pattern).
- **A 409** shows on the card. The endpoint has two 409s, told apart by `detail`:
  - the content-changed guard → "This bullet changed since the check. Check again?"
  - `detail` equal to the service's OVERRIDDEN text → that text ("You set this rating yourself. Set it back to
    automatic first.").
- **When the user has overridden the rating** (`classification_source === "override"`), don't offer "Not right?".
- **A custom-section (`extra:`) bullet** is disputable. A `new_info` suggestion for it renders copy-only (no Apply):
  there is no bullet edit op for extras.

Commit: `feat(health): tell the check why a flag is wrong`

### Task 9: "No numbers anywhere" is a highlighted flag

**Files:**
- Modify `backend/app/services/resume_lint.py`: a `_shape_notes` note with rule `evidence.no_numbers`.
- Modify the frontend summary band / current summary card (a callout).
- Test: `test_resume_lint.py` and a pin.

**Rules:**
- **Deterministic.** The flag fires when no scored bullet (experience, projects, extras) contains a number (the
  `_has_metric` regex below, applied to the text), and there are at least `MIN_SCOREABLE_ITEMS` scored bullets.
- **Zero score, no threshold, no count of "enough".** The "advisories are free" invariant must hold with this note
  present.
- **Copy:**
  - issue: "None of your bullets has a number."
  - why: "Hiring managers often pass over a resume with no measured results at all. Bullets without numbers are
    fine; a resume with none reads as unmeasured."
  - how: "Add a real number to one or two bullets where one exists."
- **Frontend:** this note renders as a highlighted callout in the summary band (`bg-amber-50` / dark equivalent,
  AA-checked), not inside the collapsed Notes. It links to the Needs-a-number tab when that tab has items.

```python
# Versions are stripped first: a capitalised name followed by a dotted number ("Python 3.11",
# "Spark 3.5.1") or a v-number ("v2.1"). Years are excluded by the lookahead.
_VERSION = re.compile(r"\b[A-Z][A-Za-z+#.-]*\s+v?\d+(?:\.\d+)+\b|\bv\d+(?:\.\d+)*\b")
_METRIC = re.compile(
    r"(?<![\w.])(?!(?:19|20)\d\d\b)\d[\d,]*(?:\.\d+)?"
    r"|\b(?:two|three|four|five|six|seven|eight|nine|ten|dozens?|hundreds?|thousands?|millions?)\b",
    re.IGNORECASE,
)

def _has_metric(text: str) -> bool:
    return bool(_METRIC.search(_VERSION.sub(" ", text)))
```

**Known limits** (write them in the rubric doc):
- A bare "Python 3" (no dot) still counts as a number, so the flag stays silent in that rare case.
- "AUC 0.789" (a capitalised word followed directly by a decimal) is read as a version, so the flag can fire when
  that is the only number.

Both errors affect only a zero-score note.

**Tests** (checked against this regex while writing the plan):

| Input | `_has_metric` |
|---|---|
| "Python 3.11 in 2024" | False |
| "Built with Airflow 2.8 and Spark 3.5.1" | False |
| "Shipped v2.1 of the SDK" | False |
| "Cut latency 40%" | True |
| "Led 3 engineers" | True |
| "Raised AUC from 0.759 to 0.789" | True |
| "Mentored two interns" | True |
| "Grew revenue $1.2M" | True |

- Five number-free bullets fire the flag.
- One "40%" silences it.
- The score is identical with and without the note.

Commit: `feat(health): flag a resume with no numbers at all, without a penalty`

### Task 10: Wording checklist: spelling and grammar, plus an editable word bank

A single **Wording** group combines two sources:
- **Spelling and grammar slips.** The AI already reports these in Task 5's `language` field, so no new LLM call is
  needed.
- **Clichés and filler words**, matched by CODE against a word bank the user can edit.

A code-matched word bank is predictable (the same words always flag), cheap, and fully under the user's control.

**Files:**
- Create `backend/app/services/health_wording.py`, holding:
  - the default bank
  - the load and save helpers
  - the matcher
- Store:
  - `Setting` row `health.word_bank`: JSON `{"cliche": [...], "filler": [...]}`. The row is absent until the first
    edit; absent means the defaults.
  - `Setting` row `health.ignored_words`: JSON list, lower-cased. This is the "never flag" list.
- Modify `backend/app/routers/resume_lint.py`:
  - `GET /wording`: returns `{"cliche", "filler", "ignored", "defaults": {"cliche", "filler"}}`
  - `PUT /wording`: body `{"cliche", "filler", "ignored"}`. Trim, lower-case, dedupe, at most 200 entries per list,
    each 1–40 chars.
  - `POST /wording/reset`: restores the defaults for `cliche` and `filler`. It leaves `ignored` alone.
- Modify `backend/app/services/resume_lint.py`:
  - `_advisories` gets `language.cliche` / `language.filler` notes from the matcher, so `rule_notes` and the
    tailoring coherence check pick them up too.
  - A `language.slip` note for each stored `language` entry.
- Frontend:
  - A **Wording** group in Notes, one checklist row per hit:
    - a slip shows the fix as a word diff, with **Apply** and **Ignore**
    - a cliché or filler word shows "'results-driven' is a cliché" / "'successfully' adds nothing", with **Remove**
      and **Ignore**
  - An **Edit word list** link in the group header opens a dialog with three editable chip lists: *Clichés*,
    *Filler words*, *Never flag*. Each list has add and remove, and there is a **Reset to defaults** button.
- Test: backend, plus a pin.

**Default bank** (lower-case, matched as whole words or phrases; source CareerBuilder/Harris 2014 "worst terms" and
the VMock filler list via Boston University, both tagged moderate in the rubric doc):
- **cliche:** results-driven, results-oriented, team player, go-getter, think outside the box, synergy, best of breed,
  go-to person, thought leadership, value add, detail-oriented, self-motivated, hard worker, strategic thinker,
  dynamic, proactive, track record, self-starter
- **filler:** successfully, effectively, efficiently, various, several, very, really, basically, actually

**Matcher rules:**
- Match whole words or phrases, case-insensitive: `(?<![\w-])<escaped phrase>(?![\w-])`.
- Check the summary and every scored bullet.
- One note per (location, word).
- A word on the *Never flag* list is skipped, whether it came from the bank or from a slip.

**Remove** and **Apply** go through the rewrite guards:
- **Remove** deletes the word in code and cleans up a doubled space or a leading comma.
- **Apply** swaps the slip span for the fix in code.
- The result can be applied only when `health_guards.guard_violations(original, replaced) == []`.
- When the guards object, the row shows the fix as copy-only text, with no button.
- The write is `applyResumeEdits` `replace_bullet` (or `replace_summary`) with `expected_content_hash`.

**Rules:**
- **Zero score.** The "advisories are free" invariant must hold with 20 wording notes.
- **Never suppressed** when the bullet also has an ask.
- **Tests:**
  - the defaults flag "results-driven" and "successfully"
  - a user-added word flags
  - a removed default stops flagging
  - "Never flag" beats the bank
  - reset restores the defaults but keeps the ignored list
  - "dynamic programming" still flags "dynamic". Document this as a known limitation: the user can add
    "dynamic" to *Never flag*.
  - a slip fix that introduces a digit gets no Apply

Commit: `feat(health): wording checklist: spelling, grammar and an editable cliché/filler word bank`

---

## Phase 4: The report and the question pass (frontend)

### Task 11: Summary band, action tabs, no left rail

**Files:**
- Modify `frontend/components/resume-health/health-report-page.tsx`.
- Modify `frontend/lib/health-report.ts`: `actionTabOf(finding)`.
- Modify `backend/tests/test_frontend_health_report.py`: REPLACE the two-pane pins
  (`lg:grid-cols-[18.75rem_minmax(0,1fr)]`, `lg:sticky`) with pins for the new structure.
- Test: node tests for `actionTabOf`.

**Layout:**
- **Header:** back, the title, and the stamp "Checked 2 min ago · Version 28". Beside the stamp, a small
  `RefreshCw` icon button labelled "Check again", which keeps the single-flight behaviour and the `checkRef` focus
  fallback.
- **Summary band:**
  - the grade tile, score and tier
  - a bar to the next band, with `nextGradeLine`
  - the composition line
  - the Task 9 callout, when present
  - "Too little to grade" and the stale banner, as today
  - the page's ONE filled button, **Start the questions (N)** (N = ask findings), hidden at 0
- **Tabs:** Needs a number · Needs detail · Reword · Shorten · Notes · Done.
  - Plain counts on each tab.
  - Default to the tab with the largest summed `gain`.
  - `?tab=` is read with `useSearchParams`, keeping `use(searchParams)` in the page (§12).
  - `actionTabOf` mapping:

    | Finding | Tab |
    |---|---|
    | `ask_kind` `measure` | number |
    | other asks | detail |
    | `fix` | reword |
    | a note with `rule === "bullet.too_long"` | shorten |
    | other notes | notes |

  - Gates stay above the tabs (`GateBanner`).
- **Inside a tab:**
  - One header per group, with its rule text and total gain shown once.
  - Rows show the entry label, "bullet N", the clamped `SourceQuote`, the bullet's own question, one text-style
    action and ⋯.
- **Unscored skills** (`skills.undemonstrated`) become a table (Skill · Listed in · "Show it in a bullet", which
  opens `demonstrate-skill-dialog`), not chips.
- **Removed:** the left rail, the filter chips and the "Add numbers to N bullets" button. Delete
  `StreamFilter`/`filterFindings` if nothing else uses them.
- **Done tab:**
  - fixed this session (the existing `resolved`)
  - disputes (`GET /disputes`), each with **Reopen**
  - corrected ratings (`classification_source === "override"`), each with **Back to automatic**
  - The summary band says "M marked not right" when M > 0.

Check at 1280 and 1024: no horizontal scroll, and one filled button in view.
Commit: `feat(health): summary band and action tabs replace the left rail`

### Task 12: The question pass (table), replacing the add-numbers dialog

**Files:**
- Create `frontend/app/base-resumes/[slug]/health/questions/page.tsx`.
- Create `frontend/components/resume-health/question-pass.tsx`.
- Delete `frontend/components/resume-health/batch-ask-dialog.tsx` once nothing imports it.
- Modify `backend/app/routers/resume_versions.py` (`if_latest` on restore) and `frontend/lib/api.ts`
  (`restoreResumeVersion` gains `ifLatest`).
- Test: pins, node tests for any pure helper, and `backend/tests/test_resume_versions*.py` for `if_latest`.

**Behaviour:**
- **Entry and exit:** "Start the questions" opens this page, and Back returns to the tab the user came from.
- **Layout:**
  - The work list sits on the left (max 65ch).
  - At ≥1280px, a **context pane** on the right shows the entry's heading, dates and all its bullets from the
    resume JSON, with the active row's bullet highlighted (`bg-primary/10` + left rule).
  - Below 1280px, the entry heading and neighbouring bullets show above each row.
- **Rows:** each row shows the full bullet and its own question.
  - `measure` asks get `MetricAskInput` (labelled with `measure_target`) plus the "No number? Answer this instead"
    swap to `alt_question`.
  - `detail` asks get a two-line `Textarea`.
  - Two quiet controls: **Not right?** (Task 8's `DisputeBox`) and **Skip for now** (session only; the row still
    counts).
- **Footer:**
  - "2 of 6 answered"
  - the only primary button, **Write N new versions**. It drafts through `answerAsk` with a pool of 3, and rows fill
    in as each draft finishes.
- **Review:**
  - Each row shows a word diff under the original, with **Accept**, **Edit** and **Try again**.
  - **Accept all shown** first lists the rows it will change, each with a checkbox.
  - Applies go through `applyResumeEdits` with `expected_content_hash`.
- **One write per batch.** "Accept all shown" sends every accepted row as ONE `applyResumeEdits` call: one
  `replace_bullet` op per row, each with its `expected_content_hash`. That is one transaction and one new version.
  If the server 409s on a changed row, drop that row (it shows "This bullet changed. Write it again?") and resend the
  rest once.
- **Undo, not confirm; checked server-side.** Toast "Saved as a new version · Undo".
  - Before the write, the client records the latest version number `V0` from the versions query.
  - Undo calls `restoreResumeVersion(kind, key, V0, { ifLatest: V0 + 1 })`. The server restores ONLY IF the latest
    version is exactly `V0 + 1`, meaning nothing wrote before or after our batch. The check and the restore happen in
    one transaction under the write lock.
  - On a 409, toast "Can't undo: the resume changed since. Use version history." with a link.
  - A single-row Accept follows the same rule.
- **Backend change for this** (in this task):
  - `backend/app/routers/resume_versions.py` `restore_version` gains an optional query param
    `if_latest: int | None`. When it is set, call `db.begin_write(db)` first, then read the latest version number
    for (kind, key). If it differs, raise 409 "resume changed since", before `service.restore`.
  - `frontend/lib/api.ts` `restoreResumeVersion` gains the optional `ifLatest`.
  - Existing callers pass nothing, so behaviour is unchanged.
- **Tests:**
  - backend: `if_latest` mismatch → 409 with nothing restored; match → restored; absent → as today
  - pin: the pass sends accepted rows as one `applyResumeEdits` call and passes `ifLatest`
- **A 409** shows on the row: "This bullet changed. Write it again?"
- **Closing:** re-runs the check in the background, then one toast: "+6 points · 3 fixed · 2 not right · 1 skipped".

Commit: `feat(health): question pass replaces the add-numbers dialog`

---

## Phase 5: Tailoring guidance, skills, docs

### Task 13: Tailoring prompts follow the rubric

**Files:**
- Modify `backend/app/prompts/tailoring_skill.txt`: replace the two lines "Bullets: default to XYZ…" and "Quantify
  with real numbers…" with:

  ```
  - Bullets: every bullet states a specific action and a concrete result. The result may be a
    number (only one the resume or the candidate's answer gives) or a clearly stated qualitative
    fact: a decision and what it made possible, who used the work, a launch, recognition, a
    problem solved. Lead the newest role with its strongest result. Useful shapes: XYZ for
    measurable outcomes, CAR for fixes, action-purpose-outcome for decisions, what-who-win for
    delivered work. Never add a number that was not given.
  ```

- Modify `backend/app/prompts/gap_tailor.txt:28-29` in the same way: "Keep every bullet truthful, specific and
  ending in a result, as the JUDGMENT RULES describe; use real numbers only where given."
- Modify `backend/app/services/prompt_assembly.py` `_skill_preamble`: append one line built from the user's Task 10
  word bank ("Never use these words: …", with the cliché and filler lists, minus *Never flag*). Tailoring then avoids
  exactly the words the health check flags, from one list. Test that the line reflects a user edit to the bank.
- Resync: a new migration `4022b54933e6_resync_tailoring_prompts` (down_revision = the head at the time). Pin both
  previous texts and refresh the lock.
- Test: `test_prompt_assembly.py`, wherever it pins phrases from these files. Update deliberately.

Commit: `feat(tailoring): bullets follow the shared rubric, not a number in every line`

### Task 14: Re-sync the skills (outside the repo; show the owner the diff first)

The skills-plugin path: find it with `find ~/Library/Application\ Support/Claude -path '*resume-health-check/SKILL.md'`.

- **`resume-health-check`** (`SKILL.md` + `references/evidence-ladder.md`):
  - Point to `docs/health-check-rubric.md` for the levels and questions.
  - Record owner decisions 1–6.
  - Fix the stale facts: the score is a plain mean, zones only order the fixes, and the summary is not scored.
  - Remove any "cost ranking by attention weight" arithmetic that the code does not do.
- **`resume-tailoring`** (`references/bullet-frameworks.md` + `SKILL.md` step 5):
  - Remove "XYZ forces a number into every line".
  - Present the shapes as writing aids, with the rubric's principle.

No commit (not in the repo). Log it in *Deviation log*.

### Task 15: Docs sweep, verification and goal critique

**Docs:**
- `docs/entities/others.md` ResumeLintReport:
  - the evaluator contract and `RUBRIC_VERSION` + model cache invalidation
  - verbatim-evidence validation
  - the question fields
  - disputes and their precedence
  - `evidence.no_numbers`, `language.slip`
  - `gain`, `next_grade`
- `SYSTEM.md`:
  - §12: refresh the "Rewording a health `issue`" gotcha (which asks kept `id_key`), and add "A prompt-contract
    change bumps `RUBRIC_VERSION`" (cache rows are keyed by text).
  - §11: new items for the deferred work (one-at-a-time mode; repeated-opener notes; the framework check on
    tailored drafts; a dispute MCP tool).
- `docs/frontend-conventions.md`: the judged-text rule, and one filled button per report view.
- `python3 scripts/check_system_md.py`: groom rather than raise the cap.

**Gates:**
- `pytest tests/ mcp_server/tests/ -q`, ruff, `npm run lint`, `npx tsc --noEmit`, the node tests
- `scripts/health_golden.py` (thresholds from Task 3)
- `check_system_md.py`
- the slop ratchet on `backend` and `frontend`, named explicitly

**Browser** (own stack, 1280 and 1024), on a seeded resume with synthetic bullets from three roles:
- Run the check.
- Answer one measure ask (including the no-number swap) and one detail ask in the pass; accept; undo.
- Dispute three flags: "no number exists", "you misread it", and "it raised revenue 40%".
- Ignore a word.
- Confirm the no-numbers callout appears when every number is removed.

**Goal critique** against the Goal Card, not the plan:
- Is any number asked for without a target and a no-number alternative?
- Is any judged text italic, grey or cut off?
- Can a dispute note raise a level without a verbatim quote?
- Does anything penalise a resume for how many numbers it has?

Commit: `docs: health check v3 (evaluator, disputes, flags, report layout)`

---

## Deviation log

| Task | Planned | Found | Done instead | Goal Card line |
|---|---|---|---|---|
| 1 | Put a toggle in SourceQuote, only above 220 chars | CollapsedRow already wraps it in a button; length does not predict wrapping | Quote is a sibling of the row button; every clamped quote has Show all | Easy to read and quick to act on |

| All | Astra CLI attribution | Exact model variant unavailable in this desktop session | Use GPT-6 (Codex) attribution | Truthful reporting |
| 2 | Browser check before Task 2 commit | Later evaluator fields affect these same cards | Verify integrated Wave 1 at both widths before checkpoint | Easy to read and quick to act on |

| 3 | Owner labels before judging evaluator | Fixture newly created | Labels provisional; requested owner sign-off through Claude; no real provider run | Works beyond tech |

| 5 | Batch evaluation reused by disputes | `_classify_batch` writes the ordinary cache | Extract `_evaluate_batch` (since renamed `evaluate_uncached`) with validated fields and no classification writes; runner uses it | Judge the page; cache isolation |
| 5 | Tune prompt on dev if key available | Real-provider gate delegated to Claude | Keep prompt exactly as specified; no tuning or held-out calls | Works beyond tech |

| 5 | Missing ask kind stays null | Number question could bypass detail sanitization | Normalize invalid/missing ask kind to detail before number checks | Never demand an unnatural number |

| 7 | Stored `metric_unavailable` applied via `_validate(..., metric_unavailable=True)` on every evaluation | Applying it inside `_classify_batch` would write the demoted ask into the ordinary cache row, so DELETE could not reopen it | Applied at read time in `classify_items` (`without_number_ask`) to cache, llm and dispute results; cache rows stay the ordinary evaluation. In `dispute`, re-applied after the no-quote level revert whenever this note or the stored row says no number exists | Never demand an unnatural number; cache isolation |
| 7 | Contract names `GET /disputes` and `DELETE /disputes/{hash}` without shapes | Task 11's Done tab needs to name the bullet and reopen it | GET returns `[{content_hash, location, label, text, note, reply, suggestion, metric_unavailable, before, after, created_at}]`, one row per location of a still-present text; DELETE is 204, idempotent, 422 on a non-hex hash | Allow "not right", reversible |
| 7 | 200 / 409 / 422 | The model can return an invalid entry, or the provider can fail | 502, nothing stored: `DisputeUnreadable` (an invalid entry, or no valid JSON after retries) in the router, a provider outage (`LLMProviderError`) through `app.main`; a local `RuntimeError` stays a 500 (§12); 422 also for an empty target text and a note over 1000 chars | Rewrites never invent |
| 7 | "The level may not rise without a verbatim quote" | `_validate` caps only analogue/direct without a quote, so a note could lift unaddressed/implied to adjacent | `dispute` keeps before's level, question, ask kind and reason when the revised level is higher and has no quote; `_validate` unchanged | Judge the page, not the claim |
| 7 | Suggestion = `guarded_rewrite(context=new_fact)` | `new_fact` is model output, and the guard trusts its context's numbers, so an invented number passed | A `new_fact` with a number found in neither the note nor the bullet is dropped (no suggestion; "Add it to the bullet in your own words.") | Rewrites never invent |
| 7 | Dispute locations resolve like `answer_ask` | `_bullet_text` 422s `extra:` bullets, which still get findings | The dispute endpoint alone reads `extra:` text with `resume_lint._text_at` (a vanished one is 409); answer_ask/draft_rewrite unchanged; extras suggestions are copy-only in the UI (Task 8) | Allow "not right" |
| 7 | 409 only for changed text | A dispute on a hand-set rating would sit behind the override, unseen | 409 "You set this rating yourself. Set it back to automatic first." before any model call | Easy to read and quick to act on |
| 7 | Reply level words | Replies should use the UI's labels | Quoted `EVIDENCE_LEVELS` labels: 'Re-read: now rated "Shows a result".', 'Re-read: on a closer look this is "Vague". …' | Easy to read and quick to act on |
| 7 | `before`/`after` carry `question` | The model's question may be null; the report then shows static fallback copy | `question` is the one the report shows (fallback included); `ask_kind` is measure/detail/null (the fix path's "reword" is not reported) | Easy to read and quick to act on |
| 8 | The reply renders in the card | A dispute that moves the rating re-runs the report, and a new ask kind or level changes the finding id, so the card remounts (collapsed, reply gone) | The page keeps the latest reply per content hash and passes it down (`dispute`, like `storedAnswer`); a card holding one mounts expanded on it | Easy to read and quick to act on |
| 8 | Focus moves to the reply via `useFocusOnNextCommit` | The armed hook cannot follow the remount above | A layout effect keyed on the reply calls `focusIfDropped`: it lands in place (Send leaves with the form) and on the replacement card | Easy to read and quick to act on |
| 8 | A 502 shows `couldnt("re-read this bullet", err)` | The unreadable 502's detail is that same sentence, so it printed twice | That one detail is matched (`DISPUTE_DETAIL.unreadable`, beside `overridden` in one constant pinned to health_disputes.py) and passed as no detail; any other failure goes through `couldnt` unchanged | Errors never print raw text |
| 8 | "Not right?" hidden only for overrides | A stale card (`locked`) would only get the content-changed 409 | Also hidden on a locked card; its stored reply still shows | Easy to read and quick to act on |
| 8 | Content-changed 409 reads "This bullet changed since the check. Check again?" | The card has the report's Check again | "Check again?" is a button running it when the page passes `onReanalyze`, plain text otherwise | Quick to act on |
| 8 | Follow-up: the reply renders in the card | A dispute that lifts a bullet to "Shows a result" removes its card, and the reply and focus went with it (focus to <body>) | The reply, and its suggestion copy-only, move onto that bullet's "Fixed" entry, which takes focus: on mount if the card left first, else by a layout-cleanup handoff from the leaving card (not `useFocusHandoff`, which returns focus beside the card). Only a bullet the dispute's own re-run lifted (`liftedDispute`). An Apply keeps the dispute, so the applied editor keeps "Applied" and focus until the next report | Easy to read and quick to act on |
| 8 | Follow-up: re-runs list vanished finding ids as "Fixed" | A dispute or override that changes a bullet's question changes its id while the bullet is still open, so a false "Fixed" line showed | `resolvedFindings`: a finding that rates text is fixed once no open ask or fix rates that text (content hash) and its place holds no open ask or fix on text new to this report (a still-flagged rewrite); one that rates none (employment gaps, C2) keeps the id test, since several share a location | Easy to read and quick to act on |
| 8 | Review: "findings without a content_hash (gaps, C2)" keep the id test | C2 carries the summary's hash (`resume_lint.py`), so a hash test would hold it open behind the summary's own ask | "Rates text" is a hash AND a `classification_level`; C2 has no level, so it keeps the id test, and only rated asks and fixes hold a hash open | Easy to read and quick to act on |
| 8 | Review: re-expanding a card shows its reply | Focusing any reply on mount stole focus on every re-expand | A reply takes focus only when it is new to that mount, or when the card opened on the page's latest dispute (`disputeFresh`, cleared by collapsing it and by Check again, an override or an Apply) | Easy to read and quick to act on |
| 9 | Frontend callout in the summary band | Task 11 rebuilds the summary band | Task 9 frontend callout deferred to Task 11 (the summary band is rebuilt there); Task 9 is backend only | Easy to read and quick to act on |
| 9 | Location unspecified | The flag is about the whole resume, not one bullet | Task 11 finds it by `rule == "evidence.no_numbers"` at location `{"section": "resume"}` (no index, no bullet_index), label "No numbers anywhere", `type: "note"`, from `_shape_notes`; "scored bullets" are `_ladder_items` minus the summary (resume text, not classified levels, so it fires without the LLM) | Every bullet earns its place |
| 10 | One task, backend + frontend | Another agent holds the frontend files | Split: 10a backend only (this row set), 10b frontend (Wording group, word-list dialog, pin) | Every bullet earns its place |
| 10a | `_advisories` gets the notes "so rule_notes and the coherence check pick them up" | Slips read the classifier's `language` field, which `_advisories` never sees | Clichés/filler come from `_advisories(word_bank=)` (so `rule_notes` and the coherence check carry them); `language.slip` is built in `assemble` from `levels_by_loc`, so the coherence check has no slips | Every bullet earns its place |
| 10a | PUT/reset return shapes and bad stored rows unspecified | 10b needs one shape to adopt | `PUT /wording` and `POST /wording/reset` both return the GET shape; an unreadable or invalid stored row reads as the defaults (bank) or empty (Never flag) | Easy to read and quick to act on |
| 10a | "Trim, lower-case, dedupe" | "team  player" would never match "team player" | Normalizing also collapses inner whitespace, and a phrase matches across any whitespace run (`\s+`) | Predictable word bank |
| 10a | Remove deletes "the word"; Apply swaps "the span" | One note per (location, word); a short slip span ("a") recurs where it is correct | Remove deletes every whole-word occurrence. Apply offers a suggestion only when the span occurs exactly once with the matcher's `[\w-]` boundaries (so "in" never hits "in-house"); otherwise copy-only. A span found only inside another word gets no note | Rewrites never invent |
| 10a | Remove cleans a doubled space and a leading or doubled comma | Re-reviews kept finding Remove text that passed the guards with broken grammar | Filler-only Remove (row below) plus a safety net: copy-only after not / a linking verb / "of" / a/an, for a non -ly filler before a function word or relative pronoun, for "the" before a function word or punctuation, for and/or left with nothing to join or opening a sentence, and for empty quotes. Commas: the one before a filler stays; an -ly word keeps the one after it unless both surround it; a non -ly word takes the one after it. A newline at the cut survives. No a/an guessing | Rewrites never invent |
| 10a | **Planner decision:** Remove offers one click for clichés and filler | 21 broken one-click suggestions in re-review, mostly from cutting clichés, which are nouns and adjectives the sentence needs | Clichés (default and user-added) never carry a `suggestion`; `how` reads "Rewrite this phrase in your own words, or cut it." Filler keeps one-click Remove under the rules above. Overrides the plan's Remove for clichés | Rewrites never invent |
| 10a | A note per stored `language` entry | A cached entry is keyed by whitespace-normalized text, so its span may no longer be verbatim | A span not in the current text as a whole word, a duplicate span at one location, or an empty span/fix is skipped | Rewrites never invent |
| 10a | Suggestion when the guards pass | `extra:` bullets have no bullet-scoped edit op (SYSTEM.md §11 item 20) | Extras still get a guarded `suggestion` (as disputes do, Task 7); 10b shows it copy-only, like Task 8 | Rewrites never invent |
| 10b | Add `resetWording()` to api.ts; Reset to defaults "confirms nothing" | A server reset would outlive the dialog's Cancel | Reset puts GET's `defaults` into the dialog's draft (Never flag kept), so Cancel discards it and Save sends it; `POST /wording/reset` has no caller in the UI, so no dead `resetWording()` | Easy to read and quick to act on |
| 10b | Apply/Remove "invalidate and re-run like other applies" | Every other Apply only invalidates (the page's "N changes applied. Check again" bar) | Same: `onApplied` (`invalidateAfterApply`), the row shows "Applied" holding focus; a second wording Apply on the same bullet 409s on its row until Check again. Ignore and the word list's Save do re-run (`onWordingChanged={reanalyzeReport}`) | Quick to act on |
| 10b | The slip row shows "original span → fix" | The note carries the span (`subject`) but no fix field | `slipFix` reads the fix from the issue sentence, anchored on `subject` (pinned to `_slip_notes`' f-string); an unreadable sentence shows the issue text | Rewrites never invent |
| 10b | Ignore on every row | Never flag holds 1 to 40 characters; a long slip span would 422 | Ignore is offered only when the normalized subject fits (`canIgnore`); it reads GET /wording right before the PUT, since the PUT replaces all three lists | Easy to read and quick to act on |
| 10b | Rows keyed by the note | Browser: a re-run on changed text kept the note's id, so a row kept a stale "This bullet changed since the check." | Rows are keyed by id and `content_hash` | Easy to read and quick to act on |
| 10b | Focus never drops to <body> when a row leaves | `focusSuccessor` reads only the adjacent rows; an Ignore's re-run can take them too | The next or previous row's action, else the Wording group (`tabIndex={-1}`), else the Notes section (`useFocusHandoff`); browser-verified landing on the group | Easy to read and quick to act on |
| 11 | "Start the questions (N)": a placeholder page, or the old batch dialog behind it until Task 12 | The dialog asks number questions only, and N counts every ask | A minimal placeholder route `/base-resumes/[slug]/health/questions` (says Task 12, links back to the report); `batch-ask-dialog.tsx` stays, unimported, for Task 12 to delete | ONE filled button per view |
| 11 | `ask_kind` "measure" → Needs a number | A legacy stored report has no `ask_kind` | `actionTabOf` reads `isMetricAsk` (the question-wording fallback the cards already use) | Easy to read and quick to act on |
| 11 | Default to the tab with the largest summed `gain` | Recomputed on every re-run, the default would move the user to another tab mid-work | Chosen once, when the first report arrives: ties go to the earlier tab, no gain anywhere to the first tab with items, nothing to Notes. `?tab=` and clicks override it | Quick to act on |
| 11 | "One header per group, with its rule text and total gain" | Asks and fixes carry no `rule` id | `ruleGroups`: a detector id groups under its RULE_TITLES title; an ask or fix groups by its issue sentence (the rule's own words). The header shows the shared why and how once, and those rows drop theirs | Group by action and state each rule once |
| 11 | The Task 2 Notes disclosure stays | A tab is already a disclosure; a closed one inside it was a second click to see anything | Notes renders open in its tab, kept mounted (drafts and the Wording group survive a switch) | Easy to read |
| 11 | Done lists "fixed this session" (the existing `resolved`) | A dispute that lifts a bullet hands its reply and focus to the bullet's Fixed entry (Task 8); in the hidden Done panel focus would drop to <body> | The lifted bullet's Fixed entry (the reply, the focus target) renders in the tab it came from; Done lists every fix plainly, without the reply | Allow "not right"; focus never drops |
| 11 | Corrected ratings are the findings with `classification_source === "override"` | An override to "Shows a result" takes the bullet out of the report, and no endpoint lists overrides | Only overrides still in the report are listed (their bullets still ask); a lifted one shows under Fixed this session. No new endpoint (scope; Task 13 held the backend) | Allow "not right", reversible |
| 11 | Reopen: `reopenDispute`, then re-run | The page keeps each reply by hash, so the card would still show the reopened dispute's reply | Reopen also drops that bullet's kept reply (a second `setDisputes`, pinned), then re-runs | Allow "not right", reversible |
| 11 | "M marked not right" | Disputes and hand-set ratings both say a rating is wrong | M counts GET /disputes rows (the "Not right?" control); hand-set ratings show only in Done | Easy to read |
| 11 | The band's list | The rail's count chips and "N left to fix" are not on it | Count chips dropped (the tabs carry the counts); "N left to fix" kept as the band's meta line, beside "M marked not right" | Easy to read |
| 11 | The page's ONE filled button | An opened card had filled Write new wording and Apply suggestion (Shorten's Apply is the same editor) | Both tonal | ONE filled button per view |
| 11 | Rows: one text-style action | Every row's Answer or Review had the same accessible name; a tab's plain count beside its label may drop out of its name (SYSTEM.md §12) | A row's action is named "Answer: <entry> · bullet N"; a tab carries "Needs a number 1" in `aria-label`; a skill row's action "Show it in a bullet: Python" | Easy to read and quick to act on |
| 11 | Delete `StreamFilter`/`filterFindings` if unused | `groupFindings`, `hoistBlurb` and `shortFindingLabel` also lost their last caller | Deleted with their node tests and pins; `addNumbersLabel` stays (the unimported dialog uses it) | Never expand scope |
| 11 review | A dispute that moves its bullet to another tab: `selectTab(newTab)` BEFORE adopting the report | react-query hands `setQueryData` to its observers a tick after a state update, so the switch rendered first: the open panel took focus (`focusIfStranded`) before the new card could land on its reply | `disputeTabMove` (the bullet by hash AND place, before and after) names the tab; the page opens it in the render the re-run's report arrives in (keyed by report id), so the card mounts in the open panel and lands on its reply. `DisputeHandler` now carries the bullet's location | Allow "not right"; focus never drops |
| 11 review | Overrides are undone from Done | An override to "Shows a result" takes the bullet out of the report (no endpoint lists overrides) | Not listed, so it can't be undone from Done; the ⋯ menu's "This rating is wrong…" is gone with its card. Task 15 files a SYSTEM.md §11 follow-up | Allow "not right", reversible |
| 11 review | Analogue `how`: "…; otherwise it's already strong." | Microcopy rules: no semicolons (two sentences) | "Add the outcome if you have it. If you don't, it's already strong." `how` is not in `_fid` (it hashes `issue` or `id_key`), so ids hold; no test pinned the old words | Easy to read |
| 12 | Pins in `test_frontend_health_report.py` | The Task 11 agent was rewriting that file at the same time | Task 12's pins live in `backend/tests/test_frontend_question_pass.py`; the old placeholder pin was removed with Task 11's review commit | Never expand scope |
| 12 | "Node tests for any pure helper" | The pass's pure logic has no file of its own | `passProgress`, `writeVersionsLabel`, `batchEditOps`, `latestVersionNumber`, `mapPool` (moved from the dialog), `passOutcome`, `passOutcomeWords` and `bulletContext` join `lib/health-report.ts`, tested in `health-report.test.ts`; `addNumbersLabel` went with the dialog | Easy to read and quick to act on |
| 12 | "Decide how the pass gets the dispute state" | The pass is its own route: the report page's `disputes`/`afterDispute` are not mounted | Local state keyed by content hash. No re-run mid-pass (it would reorder the rows): the reply stays on its row, new wording from the note goes to the row's review (Accept writes it in the batch), and the closing re-run counts it as "not right" | Allow "not right" |
| 12 | "Check how /edits reports which op failed" | The 409 is one sentence for the whole batch ("content changed since analysis…"), no op index | The client re-reads the resume and hashes each sent row (`staleFindingIds`); those rows show "This bullet changed. Write it again?" and the rest go once more. None found: every sent row is marked changed and nothing is resent. A second 409 marks the rest changed | Rewrites never invent |
| 12 | "Write it again?" | The saved report still has the old hash, so `answerAsk` would 409 again | It re-runs the check (`runLintReport`) and swaps in the new ask at that place, keeping the typed answer, or says the check has no question for it now | Quick to act on |
| 12 | Skip for now: "session only; the row still counts" | What "counts" means on the page | The row folds to "Skipped for now." with Answer it (focus moves there and back); it stays in "N of M answered" (the total is every row), is never drafted, and shows in the closing toast | Skip stays |
| 12 | Closing re-runs the check | A pass has no Close button; people also leave by browser Back or the sidebar | Closing is the page unmounting, however the user leaves; it runs only when the pass saved, disputed or skipped something. Fixed = the pass's rows `resolvedFindings` settles, minus disputed ones; zero parts are left out; "Same score" when nothing moved. A failed run toasts `couldnt("check the resume")` | One toast per batch |
| 12 | 409 toast "with a link" to version history | No URL opens Version history (a sheet in the studio's ⋯) | The toast's action "Open the resume" goes to the base resume (through the leave question) | Undo instead of confirm |
| 12 | "The only primary button, Write N new versions" | Once every answer is written, the next step is Accept all shown | Write is filled while any row can be written; then Accept all shown takes the fill (exactly one either way). The Accept all dialog's own confirm is filled: it is a modal view | ONE filled button per view |
| 12 | Below 1280: heading and neighbouring bullets above each row | The row's label already names the item | The label line adds the dates, and the bullets above and below sit around the quote ("Above:", "Below:") | Easy to read |
| 12 | V0 from the versions query | The versions read can fail | The batch saves anyway, with no Undo in its toast | Undo instead of confirm |
| 12 | The leave guard | A drafted answer and its new wording are stored by `answerAsk` | Only typed answers not yet written and an open Edit that differs register it (Browser: Leave without saving? on Back) | Quick to act on |
| 12 | `if_latest` mismatch → 409 | `begin_write` holds SQLite's write lock until the session ends | The router rolls back before raising, so the lock goes at once | Undo instead of confirm |
| 12 review | Undo only when the write created V0+1; "if /edits can cheaply return the version it wrote, prefer that" | Re-reading the latest after the write cannot tell a no-op batch from another writer's V0+1 | Base `PATCH /edits` answers with `version_number` (the version it left latest; a no-op returns the one before). `undoTarget(v0, written)` offers Undo only when it is V0+1, else the toast reads "Saved". The application `/edits` is unchanged (the pass is base only) | Undo instead of confirm |
| 12 review | Rename "version" to "wording" in the pass | Planner decision: one word per thing | "Write N new wordings", "Accept N new wordings", "Accept all shown"; "Saved as a new version" and Version history keep "version". The glossary in frontend-conventions names **wording**; no ratchet rule added (the old words are not banned elsewhere) | Easy to read |
| 12 review | Move save, undo and recheck into `usePassWrites` | The drop-and-resend flow needs a Node test, and a hook cannot run under `node --test` | The flow is `saveBatch` in `lib/health-report.ts` (dependencies passed in, Node-tested); `use-pass-writes.ts` wires it to the API and holds save, Undo and Write it again; row helpers moved to `pass-rows.ts`, the dialog to `accept-all-dialog.tsx` | Quick to act on |
| 12 review | Skip shut while queued | Skip on a drafted or unrewritable row is still useful | Skip is shut while a row is queued, drafting, saving or checking (`passRowOpen`); Not right? only on rows the check still rates as they stand (`passRowDisputable`: never saved, changed or being written) | Allow "not right" |
| 13 | `_skill_preamble` appends a line from the user's word bank | `_skill_preamble()` has no session; both callers do (`_llm_customized`, `enrich_gaps`) | The line is built in `_avoid_words_line()` with its own short-lived `SessionLocal`, the way `prompts.get_prompt` already reads `prompt.tailoring_skill` one line above; no builder or caller signature changes. Appended in code, so a customized `prompt.tailoring_skill` row still carries it; no line when Never flag empties the list | One list for the check and tailoring |
| 13 | Change only tailoring_skill.txt and gap_tailor.txt; report the other bullet-writing prompts | chat_system.txt said "strong verbs, quantified impact" for resume writing: the same number-in-every-bullet push. base_resume_instruct ("result-first, specific, with the numbers that are already there"), kb_adapt ("match … metric style", never invent), coherence_check (rephrase only) and kb_mint ("prefer quantified phrasing … if the document has no number, write the point without one") do not contradict the rubric | One-line fix in chat_system.txt ("a specific action and a concrete result in every bullet (a real number only where one is given, otherwise a clearly stated outcome)"), with its own resync entry (`OLD_CHAT_SYSTEM`) in `4022b54933e6`; SYSTEM.md §7's chat resync note now cites it. Other prompts unchanged | Never demand an unnatural number |
| 13 | Test that the pinned OLD constants equal `git show main:…`, if d08dd68e4eff has one | No such test exists (d08dd68e4eff has only a deletes-only-the-default test) | Verified by hand, byte for byte, for all three constants; added the deletes-only-the-default test per key (`test_tailoring_prompt_resync.py`) | Rewrites never invent |
| 14 | Re-sync the two skills after the owner sees the diff | The skills live in the Claude app's skills-plugin folder, outside git | Applied 2026-09-25 with the owner's "apply": resume-health-check SKILL.md (source-of-truth note and the six decisions; plain mean; the summary is not scored; a concrete result counts), evidence-ladder.md (a result in words counts), resume-tailoring SKILL.md steps 5 and 7, and bullet-frameworks.md (the "XYZ forces a number into every line" line is removed; Action-Purpose-Outcome and What-Who-Win are added). Originals are kept in the session scratchpad. The app may overwrite that folder on a skills update. | Rubric in the repo for transparency; the skills are the usage layer |
| 15 | `scripts/health_golden.py` is a gate | It died on "no such table: settings" without a migrated DATABASE_URL: `llm.call_openai` reads `llm.json_mode`, the keys and the base URL through the app's global `SessionLocal`, not the runner's session | `golden_session` binds `SessionLocal` to the runner's temp engine for the run (call logs to the temp dir unless LOGS_DIR is set) and hands it back; `test_health_golden_runner.py` runs `main()` with the client faked below `call_openai`. Separate commit. The real-provider run stays unrun (no key in this session) | Works beyond tech |
| 15 | §11: one item per deferred piece of work | SYSTEM.md sat at 971/1000 and §11/§12 at their 25% growth warning | Two grouped items (40: report and pass gaps; 41: follow-ups) plus item 20 extended for the extras bullet op; §12 groomed three entries to one line each rather than raising a baseline | Never expand scope |
| 15 | Slop ratchet green | backend `complexity_hotspots` 424 → 465 (tests: 33 of the 43 new ones); orphan LOC 116 from the runner | Runner declared an entry point (orphan 0); hotspots re-baselined per SYSTEM.md §9 (density 3.32 → 3.20 per KLOC); frontend re-baselined to lock its drop (duplicated lines 518 → 444) | Never expand scope |

## Gate results

Baseline at `444866c1`: `pytest tests/ mcp_server/tests/ -q` → **5706 passed, 1 skipped**, 256.23s.
Task 1: 14 frontend pins, lint (2 pre-existing warnings), tsc, and italic mutation check passed.
Task 3: rubric, 80-case fixture and 12 disputes created; 4 tests, runner help and ruff pass. Owner labels and real evaluator gate remain unverified.
Task 2: 23 Node tests and 15 frontend pins passed; disclosure mutation caught. Browser check follows Task 6.
Task 7: full suite 5755 passed/1 skipped before → **5782 passed, 1 skipped** after; ruff, tsc, lint (2 pre-existing warnings) clean. Mutations caught: dropping the stored-flag carry-over, writing the dispute into the classification cache, dispute ranked above override, no read-time demotion. Real-provider dispute golden cases not run.
Task 8: 7 new pins + the single-flight site, 2 new Node tests (288 pass); all `tests/ -k frontend` pins 1293 passed; lint (2 pre-existing warnings), tsc clean. Mutations caught, each by exactly its pin: "Not right?" offered on overrides, the OVERRIDDEN 409 branch dropped (also the Node test), the reply's `role="status"` removed. No browser check: needs a provider key for the dispute call.
Task 8 follow-up: a dispute that lifts a bullet out of the report puts its reply on the "Fixed" entry, which takes focus (mount effect, plus a layout-cleanup handoff from the leaving card). 1 pin + 1 Node test; both focus paths mutation-checked, each caught by that pin.
Task 8 follow-up 2 (as revised in review): a re-run lists a finding as fixed by content hash when it rates text, by id otherwise (`resolvedFindings`), so a dispute or override that changes a question no longer shows a false "Fixed". Review fixes: the reply rides only on a bullet its dispute lifted, one suggestion per card, and no focus steal on re-expand. 30 Node tests in health-report.test.ts (291 overall), 1334 pins; lint (2 pre-existing warnings), tsc clean. Mutations caught: id-only resolution (pin + Node), C2 counted as rated text (pin + Node), any stored reply on a Fixed entry (pin + Node), no lifted record (pin), `offered` without `canDispute` (pin).
Task 8 re-review: an Apply no longer drops the dispute (the editor kept unmounting, focus to <body>); a still-flagged rewrite at the same place stays open; the fresh-dispute flag is spent on first landing or collapse. 30 Node tests in health-report.test.ts pass (291 overall), 1334 pins, lint (2 pre-existing warnings), tsc clean. Mutations caught: clearing disputes on Apply (pin), dropping the rewrite test (pin + Node).
Task 9 (backend only): full suite **5821 passed, 1 skipped** (247.77s); ruff clean. 15 new tests (8-row `_has_metric` table, fire/silence/extras/summary/min-count/version cases, a no-penalty invariant). Mutations caught: dropping the `MIN_SCOREABLE_ITEMS` guard (the min-count test), dropping version stripping (2 table rows + the versions-alone test; "v2.1" is also blocked by the lookbehind, so that row alone does not catch it).
Task 10a (backend only): full suite **5867 passed, 1 skipped** (248.91s); ruff clean. 46 new tests (45 in `test_health_wording.py`, 1 wording invariant in `test_health_invariants.py`). Mutations caught: Never flag dropped from the matcher (bank test) and from slips (slip test), the guard gate on `suggestion` removed (3 tests), wording notes skipped under a ladder ask (2 tests).
Task 10a review fixes: full suite **5900 passed, 1 skipped** (245.94s; the 10b agent's in-progress frontend pins were included and green); ruff clean. +18 tests. Mutations caught: Apply replacing every occurrence (2 tests), no article agreement (3 rows), keeping the comma after the cut word (4 rows).
Task 10b (frontend): 11 new pins in `test_frontend_health_report.py` (+2 files in the italic pin, +3 single-flight sites); all `tests/ -k frontend` pins **1286 passed**; 7 new Node tests (37 in health-report.test.ts); lint (2 pre-existing warnings), tsc clean. Mutations caught, each by its pin: wording notes left in the rule table, no copy-only for an Other section, Ignore without the re-run, rows keyed by id only; the hash dropped from the bullet write (first only by the Node test, so the pin now counts both writes). Browser (throwaway stack, synthetic resume, 1280 and 1024): Remove, slip Apply, the row's 409, Ignore, and the dialog's add/duplicate error/remove/Reset/Cancel/Save; no horizontal scroll at 1024.
Task 10b review fixes: the Wording group renders with every report; one word list change at a time; no older report adopted over a newer one; Save commits a typed word; plus the minor fixes (judged-text.tsx ends the import cycle, `bulletEditOp`, `focusSuccessor` falls back to the landmark when a neighbour cannot take focus). 1293 frontend pins, 64 Node tests (39 health-report, 25 focus); lint (2 pre-existing warnings), tsc clean. Mutations caught: Notes only with notes, Wording only with hits (first survived; pin tightened), no group gate, Ignore not disabled by the group, an older report adopted, Save dropping the typed word (pin), withDraft dropping it (pin + Node).
Task 10a seam check: full suite **5944 passed, 1 skipped** (246.55s, the 10b agent's in-progress pins included); ruff clean; `health_wording` max cc 6 (`_cut` 5). +37 tests (incl. Never flag matching whatever the inner whitespace). Mutations caught: seam check ignored (23 tests), -ly comma rule dropped (3 tests).
Task 10a filler-only Remove: full suite **6024 passed, 1 skipped** (246.47s); ruff clean; `health_wording` max cc 6. The reviewer's 111 probe rows are regression cases (42 flagged clichés → None, 2 unflagged, 65 filler rows judged clean text or None, 1 non-bank word). Mutations caught: clichés given Remove (14 tests), filler rules off (31), previous-word block off (28), next-word block off (3).
Task 11 (frontend): 11 new pins in `test_frontend_health_report.py` (the rail pins replaced) and 7 pins in 5 other files updated for the removed rail; all `tests/ -k frontend` pins **1304 passed**; 8 new Node tests (68 pass with `focus.test.ts`); lint (2 pre-existing warnings), tsc clean. Mutations caught, each by exactly its pin: unqueued re-runs, too-long notes sent to Notes, the no-numbers flag left in Notes, Reopen re-running before it deletes. Browser (next dev on 3100, scratch backend): 1280 and 1024 wide, no horizontal scroll, one filled button; the callout (injected, AA 19.1 and 6.45:1 light, 17.6 and 8.5:1 dark), Done rows (injected) and Shorten (injected) seen.
Task 11 review fixes: all `tests/ -k frontend` pins **1308 passed** (the Task 12 agent's in-progress `test_frontend_question_pass.py` excluded); 10 new Node tests total for Task 11 (`disputeTabMove`, `mergeResolved` added); lint (2 pre-existing warnings); tsc clean for these files. Mutations caught, each by exactly its pin (and the node test where one exists): no tab move on a dispute, the tab switched a render before its report, the move matched by hash only, the disputes query refreshed only after a re-run, fixes replaced on each re-run, a reopened fix kept. Browser at 1280 and 1024: no horizontal scroll, one filled control (the Start link, an `<a>` with `?from=`).
Task 12: full suite **6070 passed, 1 skipped** (251.12s); ruff, tsc, lint (2 pre-existing warnings) clean; `check_system_md` OK. 4 `if_latest` router tests, 13 pins in `test_frontend_question_pass.py` (+3 single-flight sites, 1 load-error branch), 8 new Node tests (78 pass with `focus.test.ts`); all `tests/ -k frontend` pins pass. Mutations caught, each by its pin: per-row writes instead of one batch, Undo without `ifLatest`, the server's `if_latest` check removed (the mismatch test), skipped rows dropped from the total (pin + Node). Browser (next dev on 3100, scratch backend restarted on the new code, seeded answers, 1280 and 1024, no horizontal scroll): Write with no key (rows say so, one toast, focus stays), Skip and Answer it, Accept all's checkbox list writing 2 of 3 rows as one PATCH and one version, a server 409 dropping the changed row and resending the rest once, single Accept landing focus on Saved, Undo restoring with `if_latest`, Undo refused after a later write (nothing restored), Write it again with no key, Back to `?tab=`, the leave question, Edit focusing its box. Not seen: a successful draft or closing re-run (both need a provider key), so the closing toast's words are checked by Node only.
Task 12 review fixes: full suite **6074 passed, 1 skipped** (244.52s); ruff, tsc, lint (2 pre-existing warnings), `check_system_md` clean; 33 resume_versions tests (+1 for `/edits` `version_number`); 17 pins in `test_frontend_question_pass.py`, all `tests/ -k frontend` pins **1328 passed**; 88 Node tests (health-report + focus; +9: `passRowOpen`, `passRowDisputable`, `changesText`, `undoTarget`, 5 `saveBatch`). Mutations caught: no queued status on the click (pin), a queued row left open (pin + Node), Undo whatever was written (pin + Node), no-change rows accepted (Node, then the tightened pin), `/edits` without its version (wiring test + pin). Browser at 1280 (scratch backend restarted on the new code): a Write's rows shut (fields, Skip, Not right?) until the drafts failed, then reopened; a wording equal to its bullet says No change to save and stays out of Accept all (2 of 3); Accept 2 new wordings offered Undo; an Undo refused after a later write landed focus on the row's Saved line; saved rows have no Not right?; no horizontal scroll.
Task 15 (docs and gates, after the runner fix `f8ffa092`): full suite **6075 passed, 1 skipped** (245.97s); ruff clean; `npm run lint` 0 errors (the 2 pre-existing warnings: `tailored-resume-studio.tsx` unused `opts`, `types.ts` `PROPOSAL_STATUSES`); `npx tsc --noEmit` clean; `node --test lib/*.test.ts` **325 passed** (32 files; no test files outside `lib/`); `npm run build` OK in an isolated copy (17 static pages; the dev server on 3100 was left alone; Google Fonts fetched over the network); `check_system_md.py` OK, 981/1000, 0 warnings. Slop: backend orphan LOC 116 → 0 (entry point), duplicated lines 418 → 397, clones 45 → 43, error masking 10, hotspots 424 → 465 re-baselined (43 new: 33 tests, `_validate` cc 38, `summarize` cc 29, `_slip_notes`, `_stored_result`, `_cut`, `_unwrap`, `dispute`, `metrics`, `_result`/`_store` on params; `assemble` grew cc 17 → 27, `_ladder_findings` 14 → 21); frontend duplicated lines 518 → 444, clones 43 → 37 (knip not installed, so no orphan metric), though the health components went from 3 clone pairs to 7 (`FixCard`/`AskCard` repeat their dispute-landing setup). Runner mutations caught by `test_health_golden_runner.py`: no rebind (the original "no such table: settings"), no restore of the bind, no log redirect. Not run: the real-provider golden gate and the browser script (no provider key in this session).

## Goal critique

(Filled in Task 15.)
