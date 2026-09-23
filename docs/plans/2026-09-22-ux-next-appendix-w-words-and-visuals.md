> **Appendix W (words and visuals) to the UX next plan.** This is a research brief. It was written read-only
> against `2cce6139` (`claude/ux-next-plan`, which is local main). It covers items 5, 6, 8, 9 and 10 of the *Next plan* list at the end of
> `docs/plans/2026-09-22-ux-followups.md`. Where it offers options, the plan's owner decisions are binding.
> Line numbers drift, so re-locate each one before you edit.

# Implementation brief: W1–W5, plain words and measured visuals

Worktree `seinun-resume-update-45a8c0`. No repo file was changed except this one. Paths are relative to `frontend/`
unless they start with `backend/` or `docs/`.

**Goal Card (for this plan).** The app never shows internal ids, edit paths or slugs. Selection, current state, focus
and contrast meet WCAG 2.2 AA wherever they are measured. The principles:
- Speak the user's language in the web app, in chat and in MCP: no engine ids, no slugs.
- Accessibility is not negotiable, and contrast is pinned by computed tests.
- No new dependencies.
- MCP and chat contracts change additively only.
- The conventions doc changes in the same commit as the code.

**How the numbers were made.** Every contrast figure below comes from the same arithmetic as the test.
- The helpers were loaded straight from `backend/tests/test_frontend_color_roles.py`: `_oklab`, `_srgb`, `_contrast` and `_over`. The
  arithmetic is OKLCH → OKLab → sRGB → WCAG luminance, with alpha blended in gamma sRGB.
- Token values are parsed from `app/globals.css` by that module.
- Tailwind shades were read from the installed `node_modules/tailwindcss/theme.css` (v4.2.4).
- The scripts ran from the session scratchpad, not the repo.

The W1 describer was checked the same way. It was prototyped in the scratchpad and passes 6/6 under `node --test` (Node 26.9).
It type-checks under `tsc --strict` with the repo's `moduleResolution: bundler`. Its `case` list was diffed against
`app.schemas.resume_edit.op_kinds()`, and the two are equal (16 kinds). No browser was driven for this brief. The browser checks
below are for the implementer.

---

## Suggested task split

| Task | Items | Files | Size | Depends on |
|---|---|---|---|---|
| **T1 Edit words** | W1 | new `lib/describe-edit.ts` (+ `.test.ts`), new `components/edit-words-list.tsx`, `chat/edit-proposal-card.tsx`, `resume-editor/instruct-sheet.tsx`, `resume-editor/editor-body.tsx` (one prop), new `backend/tests/test_frontend_plain_words.py` | M | none |
| **T2 Résumé names** | W2 (names) | new `hooks/use-base-resume-label.ts`, `lib/types.ts`, the 8 call sites plus `project-port-dialog.tsx`, `app/base-resumes/page.tsx` (key only); optional backend: `schemas/application.py`, `routers/applications.py`; pins in `test_frontend_plain_words.py`, one pin edit in `test_frontend_analytics.py` | M | after T1 (both edit `edit-proposal-card.tsx`) |
| **T3 Chips under AA** | W3 | `components/status-chip.tsx`, `career/entity-card.tsx` (if the owner agrees), `templates/requires-tex-badge.tsx`, `test_frontend_color_roles.py` | S | none |
| **T4 Selection and the picker** | W4, plus W2's engine chip | `settings/job-preferences-section.tsx`, `career/new-entity-dialog.tsx`, `gap-analysis/resolution-controls.tsx`, `templates/template-gallery.tsx`, `templates/template-select.tsx`, `app/templates/[id]/page.tsx`; pins in `test_frontend_color_roles.py` | M | none |
| **T5 Tab panel focus** | W5 | `components/ui/tabs.tsx`; one pin | XS | none |

**Two independent lanes.** The words lane is T1 then T2, because they share `edit-proposal-card.tsx`. The visuals lane is T5,
T3, T4. Only T3 and T4 share a pin file, `test_frontend_color_roles.py`, and they add separate functions to it.
- The template gallery's engine chip (W2) goes in **T4**, so `template-gallery.tsx` has one owner.
- T3 also touches `requires-tex-badge.tsx`, which T4 only imports. That is not a conflict.
- Docs: each task edits its own bullet in `docs/frontend-conventions.md`. The SYSTEM.md §11 edits go in T2 (item 30) and
  T5 (item 28).

---

## Global constraints (every task)

- **React Compiler lint runs at error level.** `eslint-config-next` 16 core-web-vitals ships `react-hooks` v7 with
  the compiler rules.
  - No `setState` inside an effect or during render.
  - No `ref.current` reads during render.
  - No mutation of props or of query-cache objects.
  - The W1 describer copies every array before it changes it. The `does not mutate the document` node test pins this, because
    `doc` is react-query's cached object.
  - W1 freezes its words in `onMutate` and in the Discard click. Those are event paths, not render or effect paths.
- **Frontend duplication must not rise above 505 lines / 42 clones.** That is Task 19's measured figure. The committed
  `frontend/.slop-baseline.json` still reads 518/43, so judge against 505/42. Three places matter here:
  - W1 renders one op list in two places, so it goes into one `EditWordsList` component.
  - W2 must not add a fifth copy of the `["base-resumes"]` list `useQuery` block. Four identical copies exist today, in
    `ats-score-panel.tsx:207`, `chat/chat-page.tsx:206`, `career/send-to-resume-dialog.tsx:91` and
    `resume-editor/project-port-dialog.tsx:47`.
  - W4's toggles reuse the existing `variant={x ? "tonal" : "outline"}` + `{x && <Check />}` idiom rather than a new wrapper.
  - Run `slop_scan.py check frontend` after each task and name the surface. If the optional backend part of T2 lands, also run it on `backend`.
- **`lib/*.ts` imports only relative or bare packages.** A file that `node --test` loads may use `import type` only.
  - Node ESM needs file extensions and cannot resolve `@/`. Every node-tested lib file today has no value imports:
    `health-report.ts` has one `import type`, and the rest have none.
  - So `lib/describe-edit.ts` imports nothing.
  - W2's hook lives in `hooks/`, where `@/` imports are fine, and it is not node-tested.
- **MCP docstrings stay at or under ~2,000 characters, and the contracts stay additive.** The ratchet is
  `test_registered_tool_docstrings_fit_client_truncation_budget`.
  - Only T2's optional backend field touches MCP. It reaches `list_applications` and `get_application` through REST passthrough.
  - No tool is renamed and no field is removed.
  - The docstring change is optional and one clause long (see W2).
- **Node tests are not in CI.** Every behavioural claim therefore needs a pytest pin under `backend/tests/`. The host-guard
  precedent (`test_frontend_host_guard.py`) runs Node only on plain `.mjs`, on purpose: type stripping would tie CI to a Node
  version. So W1's CI guard is a kind-parity contract test plus source pins. The node test is the local behavioural check.
- **No new dependencies.** `lucide-react`'s `Check` is already imported in five components.
- **SYSTEM.md is at 999/1000 lines.** Every edit here is a §11 deletion or shortening, so the net line count stays ≤ 0. New rules
  go in `docs/frontend-conventions.md` (the reference tier).
- **The Tailwind v4 trap (read before W5).** `outline-none` sets `--tw-outline-style: none`. `outline-2` then renders
  `outline-style: var(--tw-outline-style)`, which resolves to none (verified in `tailwindcss/dist/lib.js`, v4.2.4). So an element
  carrying `outline-none focus-visible:outline-2` **never paints its outline**. No such element exists today. The grep that
  checked found none.

---

## W1. Chat suggestion cards and "Ask for changes" list internal edits

**Where.**
- `components/chat/edit-proposal-card.tsx:19-42`: `describeOp()` builds `kind · section[i].bullets[j] · “preview”`.
  `:108-114` renders it in a `font-mono` `<ul>`. So users read `replace_bullet · experience[0].bullets[1] · “…”`.
- `components/resume-editor/instruct-sheet.tsx:8` imports `describeOp` from the chat card, and `:174-181` renders the same
  list. The base-studio "Ask for changes" sheet is mounted at `resume-editor/editor-body.tsx:606-613`.

**The vocabulary it must cover.** `backend/app/schemas/resume_edit.py:140-160` defines a 16-kind discriminated union:
- `replace_summary`, `toggle_entry`, `replace_bullet`, `replace_skills_group`, `add_skill_item`, `add_bullet`
- `add_entry`, `replace_entry`, `remove_entry`, `remove_bullet`
- `replace_contact`, `replace_certifications`
- `add_extra_section`, `replace_extra_section`, `remove_extra_section`, `move_extra_section`

Both emitters accept all 16:
- Chat `propose_edits` validates with `ResumeEditRequest` (`services/chat_tools.py:199-231`).
- The sheet's `POST /api/base-resumes/{slug}/propose` validates the same way (`services/base_resume_instruct.py:66-91`).

Both dry-run `apply_edits` against the live document at propose time. `op_kinds()` is the single source.
`test_resume_edit_reference.py` already pins MCP and chat parity against it.

**Cause.** `describeOp` is a debugging renderer. It prints the op's own fields and never reads the resume the op targets.

**Two facts the design must respect.**
1. **Ops apply in order.** `apply_edits` (`services/resume_edit.py:430-454`) mutates one working copy op by op. After
   `remove_entry experience 0`, the next op's `experience[0]` is the *second* original entry. A describer that reads every op
   against the original document names the wrong entry.
2. **Indices count hidden rows.** They index the full JSON arrays, including `enabled: false` rows (SYSTEM.md §6
   `inv-tailor-vs-edit`, "never display ordinals"). So an *entry* is named by its words, never by "entry 3". Bullets have
   no `enabled` flag, so a bullet ordinal matches the PDF, and "bullet 2" is safe.

**Options.**

| | What | For | Against |
|---|---|---|---|
| **A (recommended)** | Pure `lib/describe-edit.ts` describes ops against the document the card targets. It keeps a copy-on-write shadow of the arrays that ops shift. | No contract change. One definition shared by two surfaces. Node-testable. Words follow the document Apply will actually hit. | Mirrors the backend's shifting semantics (about 60 lines). After a reload, a resolved card has no document to describe against, so it shows section-level words. |
| B | Backend stamps additive `labels: list[str]` on `proposal_ops` and `BaseResumeProposeRead`, built from the dry run's `applied[]` echo records (which already carry `name`). | Frozen at propose time and exact for sequences. Chat logs keep the words. | A Python describer plus a TS fallback for cards persisted before the field: two copies of the copy, needing a contract test. Adds to the chat card contract. The copy moves server-side, like `category_label`. |

Recommendation: **A now.** B is the upgrade path if the owner wants resolved cards to keep entry names after a reload
(OWNER decision 1).

**Fix: `lib/describe-edit.ts` (new, no imports, 16 cases, safe fallback).**

```ts
/**
 * Plain words for a typed resume edit ("Rewrite bullet 2 of Data Scientist at
 * Acme"), never the op (`replace_bullet · experience[0].bullets[1]`). Chat's
 * suggestion card and the studio's Ask for changes sheet both list ops with it.
 *
 * Pure, so `node --test` runs it (lib/describe-edit.test.ts). The vocabulary is
 * backend/app/schemas/resume_edit.py; test_frontend_plain_words.py fails when a
 * kind there has no `case` here.
 *
 * Ops apply IN ORDER (resume_edit.apply_edits), so op 2's indices point into
 * the document op 1 left behind. `describeEdits` keeps working copies of the
 * arrays an op can shift. It never guesses: with no document, or an index the
 * document does not have, the words name the section and not the entry.
 */

type Section = "experience" | "projects" | "education";

const SECTION_WORD: Record<Section, string> = {
  experience: "Experience",
  projects: "Projects",
  education: "Education",
};

const PREVIEW_CHARS = 90;

export type EditOp = Record<string, unknown>;

/** The document the ops apply to. Loose on purpose: an application's
 *  customized_json is untyped, and a malformed field must not throw. */
export interface ResumeLike {
  experience?: unknown;
  projects?: unknown;
  education?: unknown;
  skills?: unknown;
  extra_sections?: unknown;
}

export interface EditWords {
  /** What happens, and to which part: "Remove Analyst at Foo". */
  action: string;
  /** The new (or removed) text, shortened; null when there is none. */
  detail: string | null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function short(value: unknown): string | null {
  const joined = Array.isArray(value)
    ? value.map(text).filter((t): t is string => t !== null).join(", ")
    : text(value);
  if (!joined) return null;
  return joined.length > PREVIEW_CHARS ? `${joined.slice(0, PREVIEW_CHARS)}…` : joined;
}

function position(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function field(obj: unknown, key: string): unknown {
  return obj && typeof obj === "object" ? (obj as Record<string, unknown>)[key] : undefined;
}

function isSection(value: unknown): value is Section {
  return value === "experience" || value === "projects" || value === "education";
}

function pair(first: unknown, second: unknown): string | null {
  const a = text(first);
  const b = text(second);
  return a && b ? `${a} at ${b}` : (a ?? b);
}

/** How a person names an entry: "Data Scientist at Acme", "Churn model". */
export function entryName(section: Section, entry: unknown): string | null {
  if (section === "experience") return pair(field(entry, "role"), field(entry, "company"));
  if (section === "projects") return text(field(entry, "name"));
  return pair(field(entry, "degree"), field(entry, "institution"));
}

/** Working copies of every array an op can shift or rename. */
interface Shadow {
  known: boolean;
  entries: Record<Section, unknown[]>;
  extras: unknown[];
  skills: unknown[];
}

function shadowOf(doc: ResumeLike | null | undefined): Shadow {
  const list = (value: unknown) => (Array.isArray(value) ? [...value] : []);
  return {
    known: doc != null,
    entries: {
      experience: list(doc?.experience),
      projects: list(doc?.projects),
      education: list(doc?.education),
    },
    extras: list(doc?.extra_sections),
    skills: list(doc?.skills),
  };
}

function bulletsOf(entry: unknown): unknown[] {
  const bullets = field(entry, "bullets");
  return Array.isArray(bullets) ? bullets : [];
}

function sameKey(a: unknown, b: unknown): boolean {
  const x = text(a);
  const y = text(b);
  return x !== null && y !== null && x.toLowerCase() === y.toLowerCase();
}

function extraIndex(s: Shadow, key: unknown): number {
  return s.extras.findIndex((section) => sameKey(field(section, "key"), key));
}

function skillGroup(s: Shadow, category: unknown): unknown {
  return s.skills.find((group) => sameKey(field(group, "category"), category));
}

function describeOne(op: EditOp, s: Shadow): EditWords {
  const section = isSection(op.section) ? op.section : null;
  const sectionWord = section ? SECTION_WORD[section] : "the resume";
  const index = position(op.index);
  const entry = section && index !== null ? s.entries[section][index] : undefined;
  const name = section ? entryName(section, entry) : null;
  // Hidden rows are in the data but not on the PDF: say so, or "Remove
  // Analyst at Foo" reads like a mistake.
  const hidden = field(entry, "enabled") === false;
  const target = name ? `${name}${hidden ? " (hidden)" : ""}` : null;
  const bulletNo = position(op.bullet_index);
  // An ordinal only for a bullet the entry has: the dry run proved it at
  // propose time, but the document may have moved since.
  const bulletText = bulletNo !== null ? bulletsOf(entry)[bulletNo] : undefined;
  const bullet =
    target && bulletNo !== null && bulletText !== undefined
      ? `bullet ${bulletNo + 1} of ${target}`
      : null;
  const extraAt = extraIndex(s, op.section_key);
  const extraTitle =
    text(field(s.extras[extraAt], "title")) ?? text(field(op.value, "title"));
  const extra = extraTitle ? `the ${extraTitle} section` : "a custom section";

  switch (op.kind) {
    case "replace_summary": {
      const detail = short(op.value);
      return detail
        ? { action: "Rewrite the summary", detail }
        : { action: "Remove the summary", detail: null };
    }
    case "toggle_entry":
      return op.enabled === false
        ? { action: `Hide ${name ?? `an entry in ${sectionWord}`} from the PDF`, detail: null }
        : { action: `Show ${name ?? `an entry in ${sectionWord}`} on the PDF`, detail: null };
    case "replace_bullet":
      return {
        action: bullet ? `Rewrite ${bullet}` : `Rewrite a bullet in ${sectionWord}`,
        detail: short(op.value),
      };
    case "add_bullet":
      return {
        action: target ? `Add a bullet to ${target}` : `Add a bullet in ${sectionWord}`,
        detail: short(op.text),
      };
    case "remove_bullet":
      return {
        action: bullet ? `Remove ${bullet}` : `Remove a bullet in ${sectionWord}`,
        detail: short(bulletText),
      };
    case "add_entry": {
      const added = section ? entryName(section, op.value) : null;
      return {
        action: added ? `Add ${added} to ${sectionWord}` : `Add an entry to ${sectionWord}`,
        detail: null,
      };
    }
    case "replace_entry":
      return { action: target ? `Edit ${target}` : `Edit an entry in ${sectionWord}`, detail: null };
    case "remove_entry":
      return { action: target ? `Remove ${target}` : `Remove an entry from ${sectionWord}`, detail: null };
    case "replace_skills_group": {
      const category = text(field(skillGroup(s, op.category), "category")) ?? text(op.category);
      return {
        action: category ? `Replace the ${category} skills` : "Replace a skills group",
        detail: short(op.items),
      };
    }
    case "add_skill_item": {
      const item = text(op.item) ?? "a skill";
      const group = skillGroup(s, op.category);
      const category = text(field(group, "category")) ?? text(op.category);
      if (!category) return { action: `Add ${item} to the skills`, detail: null };
      // "New" only when the document is known to lack the group.
      return s.known && group === undefined
        ? { action: `Add ${item} to a new ${category} skills group`, detail: null }
        : { action: `Add ${item} to the ${category} skills`, detail: null };
    }
    case "replace_contact":
      return { action: "Update the contact details", detail: null };
    case "replace_certifications": {
      const detail = short(op.items);
      return detail
        ? { action: "Replace the certifications", detail }
        : { action: "Remove every certification", detail: null };
    }
    case "add_extra_section": {
      const title = text(field(op.value, "title"));
      return { action: title ? `Add the ${title} section` : "Add a custom section", detail: null };
    }
    case "replace_extra_section":
      return { action: `Rewrite ${extra}`, detail: null };
    case "remove_extra_section":
      return { action: `Remove ${extra}`, detail: null };
    case "move_extra_section": {
      const to = position(op.to_index);
      const last = s.extras.length - 1;
      const where =
        extraAt < 0 || to === null || to === extraAt
          ? ""
          : to === 0
            ? " to the top"
            : to === last
              ? " to the bottom"
              : to < extraAt
                ? " up"
                : " down";
      return { action: `Move ${extra}${where}`, detail: null };
    }
    default:
      // A kind this file does not know yet: plain words, never the key.
      return { action: section ? `Change ${sectionWord}` : "Change the resume", detail: null };
  }
}

/** Mirror the op's effect on the working copies, so the next op's indices
 *  land where the backend's will. Copy on write: `doc` is the query cache. */
function advance(op: EditOp, s: Shadow): void {
  const section = isSection(op.section) ? op.section : null;
  const index = position(op.index);
  const list = section ? s.entries[section] : null;
  const entry = list && index !== null ? list[index] : undefined;
  const withBullets = (bullets: unknown[]) => ({ ...(entry as object), bullets });
  switch (op.kind) {
    case "add_entry":
      list?.push(op.value);
      return;
    case "replace_entry":
      if (list && index !== null && index < list.length) list[index] = op.value;
      return;
    case "remove_entry":
      if (list && index !== null && index < list.length) list.splice(index, 1);
      return;
    case "toggle_entry":
      if (list && index !== null && entry !== undefined)
        list[index] = { ...(entry as object), enabled: op.enabled };
      return;
    case "add_bullet":
      if (list && index !== null && entry !== undefined)
        list[index] = withBullets([...bulletsOf(entry), op.text]);
      return;
    case "replace_bullet":
    case "remove_bullet": {
      const b = position(op.bullet_index);
      if (!list || index === null || entry === undefined || b === null) return;
      const bullets = [...bulletsOf(entry)];
      if (op.kind === "remove_bullet") bullets.splice(b, 1);
      else bullets[b] = op.value;
      list[index] = withBullets(bullets);
      return;
    }
    case "add_skill_item":
      if (skillGroup(s, op.category) === undefined)
        s.skills.push({ category: op.category, items: [op.item] });
      return;
    case "add_extra_section":
      s.extras.push(op.value);
      return;
    case "replace_extra_section": {
      const at = extraIndex(s, op.section_key);
      if (at >= 0) s.extras[at] = op.value;
      return;
    }
    case "remove_extra_section": {
      const at = extraIndex(s, op.section_key);
      if (at >= 0) s.extras.splice(at, 1);
      return;
    }
    case "move_extra_section": {
      const at = extraIndex(s, op.section_key);
      const to = position(op.to_index);
      if (at >= 0 && to !== null) s.extras.splice(to, 0, ...s.extras.splice(at, 1));
      return;
    }
  }
}

/** One line of words per op, in order. Pass the document the ops will apply
 *  to (the server copy, not an unsaved form), or nothing for words without
 *  entry names: a resolved card's ops no longer match the current document. */
export function describeEdits(
  ops: readonly EditOp[],
  doc?: ResumeLike | null,
): EditWords[] {
  const shadow = shadowOf(doc);
  return ops.map((op) => {
    const words = describeOne(op, shadow);
    advance(op, shadow);
    return words;
  });
}
```

The wording, for review. Every example below comes from the node test fixture.

| kind | with the document | without it (or index out of range) |
|---|---|---|
| replace_summary | Rewrite the summary + "new text" / Remove the summary | same |
| toggle_entry | Hide Data Scientist at Acme from the PDF / Show Analyst at Foo on the PDF | Hide an entry in Experience from the PDF |
| replace_bullet | Rewrite bullet 2 of Data Scientist at Acme + "new text" | Rewrite a bullet in Experience |
| add_bullet | Add a bullet to Churn model + "text" | Add a bullet in Projects |
| remove_bullet | Remove bullet 1 of Churn model + "the removed text" | Remove a bullet in Projects |
| add_entry | Add New tool to Projects | Add an entry to Projects |
| replace_entry | Edit MS Computer Science at Stanford | Edit an entry in Education |
| remove_entry | Remove Analyst at Foo (hidden) | Remove an entry from Experience |
| replace_skills_group | Replace the Languages skills + "Python, SQL" (the stored casing) | Replace the languages skills |
| add_skill_item | Add AWS to a new Cloud skills group / Add AWS to the Languages skills | Add AWS to the Cloud skills |
| replace_contact | Update the contact details | same |
| replace_certifications | Replace the certifications + "AWS SA" / Remove every certification | same |
| add_extra_section | Add the Awards section | Add a custom section |
| replace/remove_extra_section | Rewrite / Remove the Talks section | …a custom section |
| move_extra_section | Move the Awards section to the top / to the bottom / up / down | Move the Awards section |
| (unknown kind) | Change Experience / Change the resume | same |

**`lib/describe-edit.test.ts` (new).** It ran green in the scratchpad (6/6).

```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { describeEdits } from "./describe-edit.ts";

const doc = {
  summary: "Old summary",
  experience: [
    { company: "Acme", role: "Data Scientist", bullets: ["Built a churn model", "Led a team"] },
    { company: "Foo", role: "Analyst", enabled: false, bullets: [] },
  ],
  projects: [{ name: "Churn model", bullets: ["Shipped it"] }],
  education: [{ institution: "Stanford", degree: "MS Computer Science", bullets: [] }],
  skills: [{ category: "Languages", items: ["Python"] }],
  extra_sections: [
    { key: "publications", title: "Publications", type: "bullets", bullets: [] },
    { key: "talks", title: "Talks", type: "bullets", bullets: [] },
  ],
};

const one = (op: Record<string, unknown>, d: unknown = doc) =>
  describeEdits([op], d as never)[0];

test("names the entry and the bullet in the user's words", () => {
  assert.deepEqual(
    one({ kind: "replace_bullet", section: "experience", index: 0, bullet_index: 1, value: "Led a team of four" }),
    { action: "Rewrite bullet 2 of Data Scientist at Acme", detail: "Led a team of four" },
  );
  assert.equal(one({ kind: "remove_entry", section: "experience", index: 1 }).action, "Remove Analyst at Foo (hidden)");
  assert.equal(one({ kind: "toggle_entry", section: "experience", index: 1, enabled: true }).action, "Show Analyst at Foo on the PDF");
  assert.equal(one({ kind: "add_bullet", section: "projects", index: 0, text: "x" }).action, "Add a bullet to Churn model");
  assert.equal(one({ kind: "replace_entry", section: "education", index: 0, value: {} }).action, "Edit MS Computer Science at Stanford");
});

test("covers every op kind without printing a key or a path", () => {
  const ops = [
    { kind: "replace_summary", value: "New" },
    { kind: "replace_summary", value: null },
    { kind: "toggle_entry", section: "experience", index: 0, enabled: false },
    { kind: "replace_bullet", section: "experience", index: 0, bullet_index: 0, value: "v" },
    { kind: "replace_skills_group", category: "languages", items: ["Python", "SQL"] },
    { kind: "add_skill_item", category: "Cloud", item: "AWS" },
    { kind: "add_bullet", section: "experience", index: 0, text: "t" },
    { kind: "add_entry", section: "projects", value: { name: "New tool", bullets: [] } },
    { kind: "replace_entry", section: "projects", index: 0, value: { name: "Churn model" } },
    { kind: "remove_entry", section: "education", index: 0 },
    { kind: "remove_bullet", section: "projects", index: 0, bullet_index: 0 },
    { kind: "replace_contact", value: {} },
    { kind: "replace_certifications", items: ["AWS SA"] },
    { kind: "add_extra_section", value: { key: "awards", title: "Awards" } },
    { kind: "replace_extra_section", section_key: "talks", value: { key: "talks", title: "Talks" } },
    { kind: "remove_extra_section", section_key: "publications" },
    { kind: "move_extra_section", section_key: "awards", to_index: 0 },
    { kind: "brand_new_kind", section: "experience", index: 0 },
  ];
  for (const w of describeEdits(ops, doc as never)) {
    assert.doesNotMatch(w.action, /_|\[|\]|\bundefined\b|\bnull\b/, w.action);
  }
  const words = describeEdits(ops, doc as never).map((w) => w.action);
  assert.equal(words[4], "Replace the Languages skills");
  assert.equal(words[5], "Add AWS to a new Cloud skills group");
  assert.equal(words[13], "Add the Awards section");
  assert.equal(words[16], "Move the Awards section to the top");
  assert.equal(words[17], "Change Experience");
});

test("later ops index the document earlier ops left behind", () => {
  const words = describeEdits(
    [
      { kind: "remove_entry", section: "experience", index: 0 },
      { kind: "replace_bullet", section: "experience", index: 0, bullet_index: 0, value: "v" },
    ],
    doc as never,
  );
  assert.equal(words[0].action, "Remove Data Scientist at Acme");
  // Index 0 is now Foo, which has no bullet 1: no invented ordinal.
  assert.equal(words[1].action, "Rewrite a bullet in Experience");
});

test("without a document, names the section and nothing it cannot know", () => {
  const w = describeEdits([
    { kind: "remove_bullet", section: "experience", index: 3, bullet_index: 2 },
    { kind: "add_skill_item", category: "Cloud", item: "AWS" },
  ]);
  assert.equal(w[0].action, "Remove a bullet in Experience");
  assert.equal(w[1].action, "Add AWS to the Cloud skills");
});

test("an index past the end names no entry", () => {
  assert.equal(one({ kind: "remove_entry", section: "projects", index: 9 }).action, "Remove an entry from Projects");
});

test("does not mutate the document it describes", () => {
  const before = JSON.stringify(doc);
  describeEdits([{ kind: "remove_entry", section: "experience", index: 0 }, { kind: "add_bullet", section: "projects", index: 0, text: "x" }], doc as never);
  assert.equal(JSON.stringify(doc), before);
});
```

**One list component (avoids a clone).** Create `components/edit-words-list.tsx`:

```tsx
import type { EditWords } from "@/lib/describe-edit";

/** A proposal's edits in plain words: what happens, then the new text quoted.
 *  Chat's suggestion card and the studio's Ask for changes sheet share it. */
export function EditWordsList({ edits }: { edits: EditWords[] }) {
  return (
    <ul className="mt-2 space-y-1.5 text-xs">
      {edits.map((edit, i) => (
        <li key={i} className="min-w-0">
          {edit.action}
          {edit.detail ? (
            <span className="text-muted-foreground block truncate">
              “{edit.detail}”
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
```

**`chat/edit-proposal-card.tsx`.**
- Delete `describeOp` (`:19-42`).
- Fetch the target only while the card is still actionable.
- Freeze the words at the moment of resolution.

```tsx
import { useQuery } from "@tanstack/react-query";
import { EditWordsList } from "@/components/edit-words-list";
import { apiFetch } from "@/lib/api";
import { describeEdits, type EditWords } from "@/lib/describe-edit";
import type { ApplicationDetail, BaseResumeDetail } from "@/lib/types";

  const pending = resolution === null;
  // The document Apply will hit. Same keys the studios and chat's pinned-resume
  // query use, so an open chat usually has it cached.
  const base = useQuery({
    queryKey: ["base-resumes", proposal.target_key],
    queryFn: () => apiFetch<BaseResumeDetail>(`/api/base-resumes/${proposal.target_key}`),
    enabled: pending && proposal.target_kind === "base",
  });
  const app = useQuery({
    queryKey: ["application", proposal.target_key],
    queryFn: () => apiFetch<ApplicationDetail>(`/api/applications/${proposal.target_key}`),
    enabled: pending && proposal.target_kind === "application",
  });
  const doc = proposal.target_kind === "base" ? base.data?.data : app.data?.customized_json;
  // Words freeze when the card resolves: after Apply the document has moved, and
  // a remove_entry's index would name the NEXT entry. After a reload there is no
  // frozen copy, so a resolved card describes without names (never wrong ones).
  const [frozen, setFrozen] = useState<EditWords[] | null>(null);
  const edits = frozen ?? describeEdits(proposal.ops, pending ? doc : null);

  const apply = useMutation({
    mutationFn: () => applyResumeEdits(proposal.target_kind, proposal.target_key, proposal.ops),
    onMutate: () => setFrozen(describeEdits(proposal.ops, doc)),
    onSuccess: (result) => { /* unchanged */ },
    onError: (err: Error) => {
      setFrozen(null);
      toast.error(err.message);
    },
  });
  // Discard's onClick: setFrozen(edits); setResolution("discarded"); stamp("discarded");

  // :108-114 becomes
  <EditWordsList edits={edits} />
```

**`resume-editor/instruct-sheet.tsx`.**
- Drop the import from the chat card (`:8`).
- Take the server copy as a prop. The sheet closes on Apply, so nothing needs freezing.

```tsx
import { EditWordsList } from "@/components/edit-words-list";
import { describeEdits } from "@/lib/describe-edit";
import type { BaseResumeDetail, BaseResumeProposal, ResumeData } from "@/lib/types";

  /** The SERVER copy the proposal was made against and Apply will hit, never
   *  the unsaved form: its entries are what the ops' indices point at. */
  resume: ResumeData | null | undefined;

  // :174-181 becomes
  {hasOps ? <EditWordsList edits={describeEdits(proposal.ops, resume)} /> : (/* unchanged */)}
```

In `editor-body.tsx:606`, pass `resume={live?.data}`. `live` is the `["base-resumes", slug]` query (`:113-117`). It holds the
server copy, and `propose` runs against the server row (`base_resume_instruct.propose` reads `row.data_json`).

**Pins.** Add a new `backend/tests/test_frontend_plain_words.py`, source-level, in the same style as `test_frontend_analytics.py`:

```python
"""The app speaks the user's words: edits are described, never printed as ops;
resumes are named, never slugged. Node tests are not in CI, so the behaviour of
lib/describe-edit.ts is pinned here: every op kind the backend accepts has a
case, and both surfaces render through it."""

import re
from pathlib import Path

from app.schemas.resume_edit import op_kinds

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_DESCRIBER = _read("lib/describe-edit.ts")


def test_every_op_kind_the_backend_accepts_has_words():
    body = _DESCRIBER[_DESCRIBER.index("function describeOne(") : _DESCRIBER.index("\nfunction advance(")]
    cased = set(re.findall(r'case "([a-z_]+)":', body))
    assert cased == op_kinds(), {"missing": op_kinds() - cased, "unknown": cased - op_kinds()}


def test_the_fallback_never_prints_the_kind():
    assert "op.kind}" not in _DESCRIBER  # no template interpolating the key
    assert "// A kind this file does not know yet: plain words, never the key." in _DESCRIBER


def test_the_describer_takes_no_value_imports():
    # node --test loads it; `@/` and extensionless specifiers do not resolve there.
    assert not re.search(r"^import (?!type )", _DESCRIBER, re.M)


def test_both_surfaces_render_words():
    card = _read("components/chat/edit-proposal-card.tsx")
    sheet = _read("components/resume-editor/instruct-sheet.tsx")
    assert "describeEdits(proposal.ops, pending ? doc : null)" in card
    assert "onMutate: () => setFrozen(describeEdits(proposal.ops, doc))" in card
    assert "describeEdits(proposal.ops, resume)" in sheet
    for rel, src in (("card", card), ("sheet", sheet)):
        assert "<EditWordsList edits=" in src, rel
        assert "font-mono" not in src, rel
        assert "describeOp" not in src, rel
    assert "resume={live?.data}" in _read("components/resume-editor/editor-body.tsx")
```

**Browser checks** (light and dark, 1280 and 375):
1. Chat: ask for "tighten my second bullet at <company>". The card reads "Rewrite bullet 2 of <Role> at <Company>", with
   the new text quoted, muted and truncated. No monospace text, no brackets, no underscores.
2. Ask for a removal plus a following edit in the same section. The second line names the right entry.
3. Apply. The words stay the same after the mutation. Reload the chat: the applied card shows section-level words.
4. Base studio → ⋯ Ask for changes → Propose. Same wording. Apply closes the sheet.
5. With the network tab throttled, the card first shows section-level words, then the names once the target loads. That
   swap is acceptable. It never shows a name that is wrong.

**Edge cases.**
- An application proposal whose `customized_json` is null cannot happen, because chat refuses it at propose time. The
  describer would fall back to section-level words anyway.
- A target that 404s or errors: `doc` is undefined, so the words are section-level.
- An LLM set that shifts indices, for example two `remove_bullet`s in descending order: the shadow handles it (node test).
- A future op kind: `Change <Section>` in the UI, and the parity pin fails in CI first.
- Extra-section keys and skill categories match case-insensitively, as the backend does (`resume_edit.py:88-104`,
  `:212-237`).

**Docs.**
- `docs/frontend-conventions.md` gets a new bullet after "The post-commit render pair": **"An edit is described, never printed."**
  It covers `lib/describe-edit.ts`, the ordered-ops shadow, freeze-on-resolve, and the pin.
- SYSTEM.md §7's chat bullet needs no change. It describes the card contract, which is unchanged.

---

## W2. `humanizeSlug` as a résumé's permanent name, and the template gallery's `latex` chip

**Where.** Eleven call sites pass a bare slug to `baseResumeLabel`. It is `humanizeSlug` under another name
(`lib/types.ts:1045-1051`):

| Site | Line | What the user sees today |
|---|---|---|
| `app/applications/page.tsx` | 604 | Base column: "Ds Base" (§11 item 30) |
| `app/jobs/[id]/tailor/[sessionId]/page.tsx` | 592 | Gap page subtitle. The `["base-resumes", slug]` **detail** query already sits at `:152-156` and is unused for the name |
| `components/application-panel.tsx` | 196 | Details menu "Base resume" |
| `components/ats-score-panel.tsx` | 98, 289 | Score card title; the "Applied with base resume?" confirm |
| `components/chat/change-card.tsx` | 44-47 | "Edited · Ds Base" |
| `components/chat/proposal-card.tsx` | 60-63 | "→ Ds Base" |
| `components/chat/edit-proposal-card.tsx` | 92-95 | "→ Ds Base" |
| `components/proposals/proposals-section.tsx` | 782 | Row pill (from `fit_json.chosen_base`, `:120-123`) |
| `components/resume-editor/project-port-dialog.tsx` | 74, 77 | Toasts ("Copied to Ds Base as archived"). Its own list query is right there (`:47-51`) |

Sites that are already right: `send-to-resume-dialog.tsx:99,279,288`, `project-port-dialog.tsx:118,126`,
`fit-distribution-chart.tsx:84` (pinned). They all use `display_name ?? baseResumeLabel(slug)`.

**Where `display_name` is available.**

| Source | Has it | Scope |
|---|---|---|
| `GET /api/base-resumes` → `BaseResumeSummary[]` | yes | **selectable only**. `?include_archived=true` adds archived (`routers/base_resumes.py:191-208`). Soft-deleted rows are never listed |
| `GET /api/base-resumes/{slug}` → `BaseResumeDetail` | yes | any row, **deleted included** (no `deleted_at` check at `:211-216`) |
| `/api/explore/fit-distribution`, `/base-summaries` | yes | analytics only |
| `ApplicationSummary` / `ApplicationRead` / `ApplicationDetail` | **no** (`schemas/application.py:52-102`) | tracker, application panel, MCP `list_applications` / `get_application` |
| `TailoringSession`, `AtsScore.target_id`, `Proposal.fit_json.chosen_base` | no | gap page, score cards, proposals |
| Chat `ChatChangeCard`, `ChatProposal`, `ChatProposalOps` | no (`lib/types.ts:1604-1624`) | chat cards |

**Cause.** No component can reach a name without its own query, so each one fell back to the slug's words. The
`baseResumeLabel` comment already says "prefer display_name where the caller has it". No caller had it.

**Options.**

| | What | Covers | Cost |
|---|---|---|---|
| **A (recommended core)** | One hook, `useBaseResumeLabel()`, reads the cached list with archived included. `humanizeSlug` is only the loading, failed or unknown fallback, which is `useRoleLabel`'s pattern exactly. | every web site above, including archived bases | no contract change |
| **B (recommended add-on)** | Additive `base_resume_name` on `ApplicationSummary` and `ApplicationDetail`, joined server-side (archived and deleted rows included) | the tracker and application panel for **deleted** bases; MCP `list_applications` / `get_application` narrate names | two schema fields, one outer join, one `db.get`; MCP passthrough |
| C | Additive names on chat cards (`target_name`) | chat after the base is deleted | chat contract growth for a case that cannot be proposed again (`_load_target` refuses deleted bases). Not worth it |

Why a function-returning hook rather than `useBaseResumeName(slug)`: the tracker and the proposals list call it per row inside
`.map`, where a hook cannot run. `useRoleLabel()` returns `(key) => string` for the same reason.

**Fix A.** In `lib/types.ts:1045-1051`, give it an optional list. Callers that already hold rows pass them:

```ts
export function baseResumeLabel(
  slug: string,
  rows?: readonly Pick<BaseResumeSummary, "slug" | "display_name">[] | null,
): string {
  // The resume's own name when a list is at hand (useBaseResumeLabel reads the
  // cached one). The slug's words only while it loads, after it fails, or for a
  // resume no list has (a deleted one): never blank, never the raw slug.
  const name = rows?.find((r) => r.slug === slug)?.display_name?.trim();
  return name || humanizeSlug(slug);
}
```

New file `hooks/use-base-resume-label.ts`:

```ts
"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { baseResumeLabel, type BaseResumeSummary } from "@/lib/types";

/** The base-resume list's cache key. An object, not a boolean or a string, so it
 *  can never collide with the `["base-resumes", slug]` detail key; every
 *  mutation's `["base-resumes"]` prefix invalidation still reaches it. */
export function baseResumesKey(includeArchived: boolean) {
  return ["base-resumes", { includeArchived }] as const;
}

/** slug -> the resume's own name. Archived rows included: an application,
 *  score or proposal keeps pointing at a resume after it is archived. While the
 *  list loads, after it fails, or for a slug it lacks, `humanizeSlug` stands in
 *  (the `useRoleLabel` pattern). */
export function useBaseResumeLabel() {
  const { data } = useQuery({
    queryKey: baseResumesKey(true),
    queryFn: () => apiFetch<BaseResumeSummary[]>("/api/base-resumes?include_archived=true"),
  });
  return useCallback((slug: string) => baseResumeLabel(slug, data), [data]);
}
```

`app/base-resumes/page.tsx:47` uses `["base-resumes", showArchived]` for the same two URLs. Switch it to
`baseResumesKey(showArchived)`, so the grid with archived shown and the name lookup share one cache entry. Optionally, the
four copies of the default-list `useQuery` (listed under Global constraints) can move to a `useBaseResumes()` exported from the
same module. That lowers duplication, but it is not required. If you do it, the default key becomes
`baseResumesKey(false)`. Prefix invalidation still covers it.

The call sites:

| Site | Change |
|---|---|
| `chat/change-card.tsx:44-47`, `chat/proposal-card.tsx:60-63` | `const baseName = useBaseResumeLabel();` … `? baseName(card.resume_key)` / `baseName(proposal.target_key)` |
| `chat/edit-proposal-card.tsx:92-95` | `base.data?.display_name?.trim() \|\| baseName(proposal.target_key)` (W1's detail query is already there) |
| `application-panel.tsx:196` | `app.base_resume_name \|\| baseName(app.base_resume)` (B), else `baseName(...)` |
| `ats-score-panel.tsx:98` (in `ScoreCard`), `:289` | hook in `ScoreCard` and in the panel |
| `proposals/proposals-section.tsx:782` | hook in the row component |
| tailor page `:592` | `baseResume.data?.display_name?.trim() \|\| baseResumeLabel(session.data.base_resume)`. The detail endpoint returns deleted rows, so no hook is needed |
| `app/applications/page.tsx:604` | `r.app.base_resume_name \|\| baseName(r.app.base_resume)` (B), else `baseName(...)` |
| `project-port-dialog.tsx:74,77` | `baseResumeLabel(result.target_slug, bases.data)` |

**Fix B (backend, additive).**
- `schemas/application.py`: add `base_resume_name: str | None = None` to `ApplicationSummary` and to `ApplicationDetail`, with
  this comment: *the base resume's own name, joined like the job fields; archived and soft-deleted rows included, since the
  application outlives both; null when it has none*.
- `routers/applications.py:181-200`:
  `select(Application, Job, BaseResume.display_name).join(Job, …).outerjoin(BaseResume, BaseResume.slug == Application.base_resume)`,
  then `summary.base_resume_name = base_name or None`.
- `_detail` (`:53-65`): `base_row = db.get(BaseResume, application.base_resume)`, then pass
  `base_resume_name=(base_row.display_name or None) if base_row else None`.
- `PATCH` returns `ApplicationRead` and stays unchanged.
- Frontend `lib/types.ts`: add `base_resume_name?: string | null` to `ApplicationSummary` (`:110`) and `ApplicationDetail`
  (`:104`). It is optional because a backend that predates it omits it.
- MCP: nothing changes in `server.py`, because `list_applications` and `get_application` return REST verbatim. The optional
  docstring clause for `list_applications` (about 220 characters today) is: *"Rows name their base resume
  (`base_resume_name`)."*
- Tests: add a backend test that the list and the detail carry the name, including after `DELETE /base-resumes/{slug}` (soft
  delete) and after archive.

**The template gallery's engine chip.**
- `templates/template-gallery.tsx:51-53` renders `{template.engine}` in `font-mono` ("latex", "typst") on every card, in both
  the manage gallery (`/templates`) and the **picker dialog** (`template-select.tsx:203-210`).
- `app/templates/[id]/page.tsx:251-253` repeats it.
- Next to it, `{template.status}` prints the raw key "ready" / "draft" (`:48-50`, and `page.tsx:247-249`), and the editor
  shows a lowercase `default` badge (`:250`).

What a user should see:
- **In the picker** (a template is a LOOK, per conventions "The template picker is ONE control"): **nothing**. The engine does
  not help choose a look. The one engine fact that matters, "this can't render here", is already the `RequiresTexBadge`.
- **In the manage gallery and the template editor**: the source language, as proper nouns, "LaTeX" / "Typst", in body font. An
  author editing source needs to know which syntax it is in.
- The status reads "Ready" / "Draft", and the badge reads "Default".

```tsx
// template-gallery.tsx
export const ENGINE_LABEL: Record<TemplateSummary["engine"], string> = { latex: "LaTeX", typst: "Typst" };
const STATUS_LABEL: Record<TemplateSummary["status"], string> = { ready: "Ready", draft: "Draft" };

function TemplateBadgeStrip({ template, picking }: { template: TemplateSummary; picking?: boolean }) {
  …
      <Badge variant={isReady ? "default" : "secondary"}>{STATUS_LABEL[template.status]}</Badge>
      {/* Choosing a look, the engine is noise; authoring, it is the source language. */}
      {!picking && <Badge variant="outline">{ENGINE_LABEL[template.engine]}</Badge>}
```

`TemplateCardBody` takes `picking` and passes it down. The `onSelect` branch passes `picking`. The editor page imports
`ENGINE_LABEL`. `TemplateEngine` in `lib/types.ts:1055` is not exported, so index the type through `TemplateSummary["engine"]` as
shown. In a picker that shows only ready templates, the status badge could also go. Leave that to the owner (OWNER decision 4).

**Pins** (in `test_frontend_plain_words.py`):

```python
# A bare baseResumeLabel(x) is a slug dressed as a name. Allowed only as the
# fallback half of `display_name ?? baseResumeLabel(x)` / `|| ...`, or with a list.
_BARE = re.compile(r"(?<!\?\? )(?<!\|\| )baseResumeLabel\([^,()]*\)")

def test_no_resume_is_named_by_its_slug():
    offenders = [
        f"{p.relative_to(_FRONTEND)}:{n}"
        for root in ("app", "components")
        for p in sorted((_FRONTEND / root).rglob("*.tsx"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _BARE.search(line)
    ]
    assert offenders == [], offenders  # 11 today (the table above)


def test_the_name_hook_reads_the_list_with_archived_rows():
    hook = _read("hooks/use-base-resume-label.ts")
    assert '"/api/base-resumes?include_archived=true"' in hook
    assert "baseResumeLabel(slug, data)" in hook
    assert 'return ["base-resumes", { includeArchived }] as const;' in hook


def test_the_picker_hides_the_engine_and_nothing_prints_a_raw_engine():
    gallery = _read("components/templates/template-gallery.tsx")
    assert "{!picking && <Badge" in gallery
    for rel in ("components/templates/template-gallery.tsx", "app/templates/[id]/page.tsx"):
        assert not re.search(r"\{(?:template|tq\.data)\.(?:engine|status)\}", _read(rel)), rel
```

Update the `"resume-fallback"` entry in `test_frontend_analytics.py:58` from `"return humanizeSlug(slug);"` to
`"return name || humanizeSlug(slug);"`. The `"fit-name"` pin stays as it is.

**Browser checks.**
1. Tracker Base column shows each résumé's name. Archive one of them: the column still names it. With B, soft-delete one:
   still named.
2. Chat change, proposal and edit cards. The gap page subtitle. The score cards and the "Applied with base resume?"
   confirm. The proposals row pill. The job page's Details menu.
3. Throttle `/api/base-resumes`: "Ds Base"-style words show briefly, then the name. Never blank, never `ds_base`.
4. Template picker: no LaTeX/Typst chip. `/templates`: "Ready" and "LaTeX". The template editor header: "Default" and "Typst".

**Edge cases.**
- Two résumés can share a display name. Only the *label* changes; keys, dataKeys and routes stay slugs (the fit-chart
  precedent).
- An empty or whitespace `display_name` falls back to the slug's words (`.trim()`).
- A tailored target in the chat cards still reads "tailored resume". Optionally, W1's application query makes
  `Tailored resume for ${job.title} at ${job.company}` a one-line improvement. It is out of scope unless the owner wants it.

**Docs.**
- `docs/frontend-conventions.md:670-679`, the Analytics bullet sentence "`humanizeSlug` … also `baseResumeLabel`'s
  fallback". Rewrite it as one rule: **a résumé is named by `useBaseResumeLabel()`** (or a row's `display_name`), and
  `humanizeSlug` is only the loading fallback. Name the pin.
- `:80-87` (template picker): "the picker shows no engine; the manage gallery and the editor say LaTeX/Typst".
- **SYSTEM.md §11 item 30**: delete the clause *"the Applications table's Base column shows `baseResumeLabel(slug)` ("Ds
  Base") instead of the résumé's `display_name`"*. The other three clauses of item 30 (Job market bars, the Analytics
  Employment/Level filters, MCP `explore_*` role labels) are not W's scope. **Delete the whole item only if another appendix
  fixes those three.**
- If B lands, add one clause to `docs/entities/application.md` noting that the summary and detail carry `base_resume_name`.

---

## W3. Status chips under AA (and every tinted chip pinned)

**Where.** `components/status-chip.tsx`:
- `:31` Interviewing: `bg-amber-500/15 text-amber-700`
- `:41` Accepted: `bg-green-600/10 text-green-700`
- `:129` Queued: `bg-sky-500/10 text-sky-700`
- `:130` Approved: `bg-emerald-500/10 text-emerald-700`

The chips sit on the page (job header), the card (Proposals rows) and **`--muted`** (a selected tracker row,
`ui/table.tsx:60` `data-[state=selected]:bg-muted`; hover is `bg-muted/50`).

**Current contrast: text on its tint, over each surface** (light / dark):

| Chip | light bg / card / muted | dark bg / card / muted |
|---|---|---|
| Applied (blue-700 on blue-600/10) | 5.53 / 5.91 / 5.00 | 9.00 / 7.83 / 6.52 |
| **Interviewing** (amber-700 on amber-500/15) | **4.23 / 4.49 / 3.85** | 10.52 / 9.06 / 7.50 |
| Offer (violet-700 on violet-600/10) | 5.81 / 6.20 / 5.24 | 8.85 / 7.70 / 6.41 |
| **Accepted** (green-700 on green-600/10) | **4.14 / 4.41 / 3.74** | 11.06 / 9.58 / 7.96 |
| Rejected (red-700 on red-600/10) | 5.03 / 5.37 / 4.54 | 8.68 / 7.60 / 6.36 |
| Proposed (blue-700 on blue-500/10) | 5.68 / 6.06 / 5.14 | 6.90 / 6.11 / 5.12 |
| Needs you / Submission uncertain (orange-800 on orange-500/10) | 6.19 / 6.60 / 5.60 | 7.54 / 6.65 / 5.57 |
| **Queued** (sky-700 on sky-500/10) | 4.96 / 5.29 / **4.49** | 8.16 / 7.19 / 6.00 |
| **Approved** (emerald-700 on emerald-500/10) | 4.58 / 4.88 / **4.14** | 9.15 / 8.03 / 6.70 |
| Submitted (emerald-800 on emerald-500/15) | 6.18 / 6.57 / 5.62 | 10.74 / 9.36 / 7.82 |
| Draft / Withdrawn / Skipped / Expired (muted-foreground on `bg-muted`) | 4.93 (fill is opaque) | 5.83 |

On the hovered row (`muted/50` over the page), the numbers are Interviewing 4.03, Accepted 3.94, Approved 4.36 and Queued 4.72.
**Dark mode passes everywhere.** Every failure is light-mode text one shade too light, the same cause as the orange-700 →
800 fix already in the file.

**Fix (light text shade only; tints and dark mode unchanged).**

| Chip | Change | New light bg / card / muted |
|---|---|---|
| Interviewing | `text-amber-700` → `text-amber-800` | 5.97 / 6.34 / 5.43 |
| Accepted | `text-green-700` → `text-green-800` | 5.94 / 6.33 / 5.37 |
| Queued | `text-sky-700` → `text-sky-800` | 6.36 / 6.79 / 5.76 |
| Approved | `text-emerald-700` → `text-emerald-800` | 6.46 / 6.89 / 5.85 |

Rejected passes at 4.54 over muted, which is thin. Leave it: the pin holds it. Moving the tints instead was rejected. Amber-700
on a /10 tint still measures 3.97 over muted, so the text shade is the lever.

**Same defect, same fix, outside the file** (recommended in T3, OWNER decision 6):
- `career/entity-card.tsx:35`, KB "Completed": `bg-emerald-600/10 text-emerald-700` measures **4.46 / 4.76 / 4.04**. Emerald-800
  measures 6.30 / 6.73 / 5.70. The chip literal has the same `chip: "…"` shape, so the generalised pin covers it by adding
  the file.
- `templates/requires-tex-badge.tsx:12` and `template-gallery.tsx:58` ("⚠ ATS spacing"): plain `text-amber-600` on the card
  measures **3.19** (page 2.98). `text-amber-700` measures 5.05 on the card and 4.71 on the page. Dark `amber-400` is 10.43. The
  editor's `app/templates/[id]/page.tsx:256` "unsaved" `text-amber-600` on the page measures 2.98. Move all three to `text-amber-700`, and give
  the editor's one a `dark:text-amber-400`. T4 edits `template-gallery.tsx` anyway, so put the `:58` change there.

**The generalised pin.** It replaces `test_orange_chips_are_found` and `test_orange_chip_text_meets_aa_on_its_tint` in
`test_frontend_color_roles.py:414-434`. The code was simulated against the current file, where it reports exactly the 8
failures above. With the four shade changes it reports none.

```python
# Every tinted chip in the status vocabulary (and the KB entity chips, which
# copy its shape): text on its own tint, over the page, a card and --muted
# (a selected tracker row), both modes. A chip's dark text and tint fall back to
# the light ones when it declares none, as the browser does.
_CHIP_SOURCES = ("components/status-chip.tsx", "components/career/entity-card.tsx")
_CHIP_CLASS = re.compile(r'(?:chip|className):\s*"([^"]*\bbg-[^"]*)"')
_CHIP_UTIL = re.compile(
    r"(?<![\w:/-])(dark:)?(bg|text)-([a-z]+-\d+|muted(?:-foreground)?)(?:/(\d+))?(?![\w/-])"
)
_CHIPS = [(rel, cls) for rel in _CHIP_SOURCES for cls in _CHIP_CLASS.findall(_read(rel))]


def test_every_tinted_chip_is_found():
    found = {rel: sum(1 for r, _ in _CHIPS if r == rel) for rel in _CHIP_SOURCES}
    # 7 application statuses + Needs you + 7 proposal entries; 3 KB states + its fallback.
    assert found == {"components/status-chip.tsx": 15, "components/career/entity-card.tsx": 4}, found


def _chip_colour(mode, name):
    if name.startswith("muted"):
        return _rgb(_MODES[mode], name)
    assert name in _TAILWIND, f"copy --color-{name} from tailwindcss/theme.css into _TAILWIND"
    return _srgb(_oklab(_TAILWIND[name]))


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("rel,chip", _CHIPS, ids=[f"{r.rsplit('/', 1)[-1]}:{i}" for i, (r, _) in enumerate(_CHIPS)])
def test_chip_text_meets_aa_on_its_tint(rel, chip, mode):
    utils = {
        (bool(dark), kind): (colour, int(pct) / 100 if pct else 1.0)
        for dark, kind, colour, pct in _CHIP_UTIL.findall(chip)
    }
    dark = mode == "dark"
    text = utils.get((dark, "text")) or utils[(False, "text")]
    tint = utils.get((dark, "bg")) or utils[(False, "bg")]
    for surface in ("background", "card", "muted"):
        fill = _over(_chip_colour(mode, tint[0]), _rgb(_MODES[mode], surface), tint[1])
        ratio = _contrast(_chip_colour(mode, text[0]), fill)
        assert ratio >= 4.5, f"{mode}: {rel} {chip!r} over --{surface} is {ratio:.2f}:1"
```

Extend `_TAILWIND` (`:392-398`) with every shade the chips name. These are the values from the installed `theme.css`
(v4.2.4, L as a fraction). `test_copied_tailwind_shades_match_the_installed_theme` checks them wherever `node_modules`
exists.

```python
    "blue-300": (0.809, 0.105, 251.813), "blue-400": (0.707, 0.165, 254.624),
    "blue-500": (0.623, 0.214, 259.815), "blue-600": (0.546, 0.245, 262.881),
    "blue-700": (0.488, 0.243, 264.376),
    "amber-300": (0.879, 0.169, 91.605), "amber-400": (0.828, 0.189, 84.429),
    "amber-500": (0.769, 0.188, 70.08), "amber-800": (0.473, 0.137, 46.201),
    "violet-300": (0.811, 0.111, 293.571), "violet-400": (0.702, 0.183, 293.541),
    "violet-600": (0.541, 0.281, 293.009), "violet-700": (0.491, 0.27, 292.581),
    "green-300": (0.871, 0.15, 154.449), "green-400": (0.792, 0.209, 151.711),
    "green-600": (0.627, 0.194, 149.214), "green-800": (0.448, 0.119, 151.328),
    "red-300": (0.808, 0.114, 19.571), "red-400": (0.704, 0.191, 22.216),
    "red-600": (0.577, 0.245, 27.325), "red-700": (0.505, 0.213, 27.518),
    "sky-400": (0.746, 0.16, 232.661), "sky-500": (0.685, 0.169, 237.323),
    "sky-800": (0.443, 0.11, 240.79),
    "emerald-300": (0.845, 0.143, 164.978), "emerald-500": (0.696, 0.17, 162.48),
    "emerald-600": (0.596, 0.145, 163.225), "emerald-800": (0.432, 0.095, 166.913),
```

The pin has three limits. Keep them in mind.
- It reads the chip string literals only. A chip built by concatenation escapes it.
- `test_every_tinted_chip_is_found` catches a chip deleted or reshaped out of the regex's reach. It does not catch a new chip
  file.
- The dots (`dot:` keys) are decorative, because the label carries the state, so they are not measured.

Keep `test_frontend_analytics.py`'s `needs-decision` and `needs-human` pins. They pin identity, not contrast.

**Browser checks.** Tracker at 1280 in light mode: hover a row and open a chip's menu (the row takes `has-aria-expanded:bg-muted/50`). The
Interviewing and Accepted chips read clearly darker. Proposals page: Queued and Approved. Dark mode: unchanged. KB list:
Completed. Templates: "Requires TeX" and "⚠ ATS spacing".

**Docs.** `docs/frontend-conventions.md:434-441`, the Shared components bullet. Replace *"Orange-700 measured 3.98:1 over
`--muted`; `test_frontend_color_roles.py` finds every orange chip…"* with: *every tinted chip is text one step darker than
its tint in light mode (800 on amber, green, sky, emerald and orange). `test_frontend_color_roles.py` finds every chip
literal in `status-chip.tsx` and `career/entity-card.tsx` and computes it over the page, a card and `--muted` in both modes. A
new shade must be copied into its `_TAILWIND` table.* No §11 entry exists for W3.

---

## W4. Selection without `aria-pressed` or a Check; a picker whose focus and selection look alike

**The rule** (`docs/frontend-conventions.md:34-52`): selected in a set is `tonal` plus a leading `Check` plus `aria-pressed`.
There are two recorded exceptions: the formatting panel's solid `bg-primary` segments, and the KB section-type cards'
`border-primary` outline. The tonal fill alone is too faint to carry the state:

| | light | dark |
|---|---|---|
| `--secondary-container` vs page | 1.16 | 1.62 |
| vs card / popover | 1.25 | 1.47 |
| vs the presets box (`bg-muted/20` on popover) | 1.21 | 1.42 |
| `--on-secondary-container` text on it | 9.81 | 9.36 |
| solid `bg-primary` vs page (for comparison) | 6.26 | 9.20 |

**The brief's premise, corrected at `2cce6139`.**

| Site | `aria-pressed` | Check | Fill |
|---|---|---|---|
| New-entity section presets, `career/new-entity-dialog.tsx:185-204` | **missing** | none | solid `default` / `outline` |
| Gap-target `Chip`, `gap-analysis/resolution-controls.tsx:270-324` | **present** (`:291`, every caller passes a boolean) | none | solid `bg-primary` |
| Employment types, `settings/job-preferences-section.tsx:250-268` | **present** (`:265`) | none | solid `default` / `outline` |
| Template picker, `templates/template-gallery.tsx:180-195` | present (`:183`) | none | `ring-2 ring-primary` on the card, while focus is `ring-2 ring-ring` on the wrapper at the same geometry |

**Per site.**

**1. Employment types → the rule (tonal + Check).** This is M3's multi-select filter chip, the same shape as the health-report
filters, with no narrow-pane reason for an exception. Name the group from the visible caption (conventions, "Naming a control").

```tsx
const employmentLabelId = useId();
…
<Label id={employmentLabelId} className="text-xs" optional>Employment types</Label>
<div role="group" aria-labelledby={employmentLabelId} className="flex flex-wrap gap-2">
  {EMPLOYMENT_TYPES.map((type) => {
    const selected = preferences.employment_types.includes(type);
    return (
      <Button key={type} type="button" size="sm"
        variant={selected ? "tonal" : "outline"}
        aria-pressed={selected}
        onClick={() => toggleEmployment(type)}>
        {selected && <Check />}
        {EMPLOYMENT_LABEL[type]}
      </Button>
    );
  })}
</div>
```

While you are here, drop the file-local `humanize()` (`:36-41`), which renders "Full Time", "Part Time" and "Onsite" in
Title Case. Replace it with plain-word maps:
`EMPLOYMENT_LABEL = { full_time: "Full-time", contract: "Contract", part_time: "Part-time", internship: "Internship" }` and
`REMOTE_LABEL = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", any: "Any" }` (used at `:192,199`). That is the W2
principle, and the microcopy rule is sentence case.

**2. Section presets → the rule, plus `aria-pressed`.** A preset stays "on" exactly while `sectionTitle === preset.title`
(typing unsets it), so it is a single-select set.

```tsx
const presetsLabelId = useId();
<Label id={presetsLabelId}>Section presets</Label>
<div role="group" aria-labelledby={presetsLabelId} className="flex flex-wrap gap-1.5">
  {SECTION_PRESETS.map((preset) => {
    const on = sectionTitle === preset.title;
    return (
      <Button key={preset.id} type="button" size="sm" className="text-xs"
        variant={on ? "tonal" : "outline"} aria-pressed={on}
        onClick={…unchanged…}>
        {on && <Check />}
        {preset.label}
      </Button>
    );
  })}
</div>
```

Sentence-case the three labels: "Section Presets", "Section Name" and "Section Type" become "Section presets", "Section name"
and "Section type" (`:185,210,233`). The two section-type cards keep their recorded exception.

**3. Gap-target chips → record the exception (recommended), and fix the text inside the chip.** The selected chip is the
gap's *answer* on a long page. A full-strength `bg-primary` fill (6.26:1 against the page) needs no second cue, the
formatting-segment reasoning applies, and a 16px Check would eat the label of a `max-w-full truncate` chip. The
alternative is tonal + Check. That is OWNER decision 5.
- Either way, make the attribute unconditional: `aria-pressed={selected ?? false}` (`:291`). Today `selected?` is optional, so a
  future caller that omits it drops the attribute.
- Either way, fix three AA failures in the chip's own text (all 10–12px):

| Text (`resolution-controls.tsx`) | light | dark | Fix | After (light / dark) |
|---|---|---|---|---|
| unselected date, `text-muted-foreground/70` on the page (`:307`) | **2.96** (card 3.08) | **4.20** (card 4.02) | `text-muted-foreground` | ≥ 4.5 (pinned token) |
| selected date, `text-primary-foreground/70` on primary (`:307`) | **3.99** | **4.46** | `text-primary-foreground` | 6.43 / 8.34 |
| selected "recent" tag, `bg-primary-foreground/20 text-primary-foreground` (`:318`) | **4.24** | 5.76 | `bg-primary-foreground/10` | 5.23 / 6.97 |

The date then keeps its weight difference through size and `tabular-nums`, not through alpha.

**4. Template picker: selected must not look like focus.**
- Focus is `focus-visible:ring-2 focus-visible:ring-ring` on the wrapping `<button>` (`:185`).
- Selection is `ring-2 ring-primary` on the `GalleryCard` inside it (`:190`).
- The button and the card share `rounded-xl` and the same box, so both are a 2px blue ring on the same edge.
- `--ring` against `--primary` is only 1.49:1 (light) and 1.70:1 (dark). A focused card and a selected card look the same.
- A focused *and* selected card shows one ring.

The fix separates them by **geometry and shape**:
- Focus moves **off** the card, with a 2px offset in the dialog's surface colour.
- Selection keeps the card's own primary edge and gains a leading `Check` in the title row. That is the rule's cue, and it sits
  next to the name you are reading.

```tsx
// template-gallery.tsx, onSelect branch
<button
  key={t.id}
  type="button"
  aria-pressed={selected}
  onClick={() => onSelect(t)}
  // Focus is a ring OUTSIDE the card, 2px off it; selection is the card's own
  // primary edge plus a Check. Both used to be one 2px blue ring on one edge.
  className="rounded-xl text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-popover focus-visible:outline-none"
>
  <GalleryCard className={cn("h-full transition-shadow hover:ring-foreground/20", selected && "ring-2 ring-primary")}>
    <TemplateCardBody template={t} picking selected={selected} />
  </GalleryCard>
</button>

// TemplateCardBody: the title row
<CardTitle className="flex min-w-0 items-center gap-1.5 text-base" title={…unchanged…}>
  {selected && <Check className="text-primary size-4 shrink-0" aria-hidden="true" />}
  <span className="truncate">{template.display_name ?? template.id}</span>
</CardTitle>
```

The numbers:
- The focus ring measures 4.49 (light) and 4.91 (dark) on `--popover`.
- The selection edge (`--primary` on the card) measures 6.71 and 8.32.
- The Check is `text-primary` on the card, also 6.71 and 8.32. That is non-text 3:1 with margin.
- `ring-offset-popover` satisfies `test_ring_offsets_name_their_surface`, because `popover` is on its list.

Three follow-on changes in `template-select.tsx`:
- **The scroll body clips the offset ring.** At `:195`, `min-h-0 flex-1 overflow-y-auto pr-1` has no left or top padding,
  and the ring sits 4px outside the button. The first column and first row are clipped today too, at 2px. Change it to `p-1`.
- **"Use the default template"** (`:176-192`) is the same set. Keep its `border-primary bg-primary/5` outline (the radio-card
  exception's look, with foreground text, so the `bg-primary/N` pin is not triggered). Add the leading Check:
  `{value === DEFAULT_TEMPLATE && <Check className="text-primary size-4 shrink-0" aria-hidden="true" />}` before the label.
- **The accessible name.** The picker button's name today concatenates the image alt, the title and every badge ("… preview,
  rendered with a sample resume XCharter Serif ready latex"). Give it `aria-label={t.display_name ?? t.id}`, so it announces
  as "XCharter Serif, toggle button, pressed". The alt still serves the image's own role in manage mode.

A tonal card fill was considered and rejected. The header tint would be 1.25:1 against the card, and the image is most of the
card, so it adds nothing the edge and the Check do not.

**Pins** (add to `test_frontend_color_roles.py`, beside `test_selected_tonal_toggles_show_a_check`):

```python
def test_every_selection_set_carries_its_state():
    prefs = _read("components/settings/job-preferences-section.tsx")
    assert 'variant={selected ? "tonal" : "outline"}' in prefs
    assert "aria-pressed={selected}" in prefs and "{selected && <Check" in prefs
    assert "role=\"group\" aria-labelledby={employmentLabelId}" in prefs
    dialog = _read("components/career/new-entity-dialog.tsx")
    assert 'variant={on ? "tonal" : "outline"} aria-pressed={on}' in dialog
    assert "{on && <Check" in dialog
    chips = _read("components/gap-analysis/resolution-controls.tsx")
    assert "aria-pressed={selected ?? false}" in chips
    # Alpha on 10px text failed AA (2.96 and 3.99:1 light).
    assert "text-muted-foreground/70" not in chips and "text-primary-foreground/70" not in chips


def test_template_picker_focus_and_selection_differ():
    gallery = _read("components/templates/template-gallery.tsx")
    assert "focus-visible:ring-offset-2 focus-visible:ring-offset-popover" in gallery
    assert 'selected && "ring-2 ring-primary"' in gallery
    assert "{selected && <Check" in gallery
    select = _read("components/templates/template-select.tsx")
    assert "{value === DEFAULT_TEMPLATE && <Check" in select
    assert "overflow-y-auto p-1" in select  # the offset ring is not clipped
```

Also extend `test_segmented_controls_and_entity_cards_expose_pressed` (`:236-240`) with
`assert "aria-pressed={selected ?? false}" in _read(".../resolution-controls.tsx")`, if you prefer the exception pins in one place.

**Browser checks** (light and dark, 1280 and 375):
1. Profile → Job preferences: toggling shows a Check and a tonal fill. VoiceOver or the accessibility tree reads "Employment
   types, group" and "Full-time, toggle button, pressed".
2. Career KB → New item → Custom section: pick a preset, and the Check appears. Type in Section name, and the preset releases.
3. Gap page: choose a target. The chip is solid primary. Its date and "recent" tag are readable in both modes.
4. A studio → Template: Tab through the grid. The focus ring sits *outside* the card with a gap. The selected card has an
   inner primary edge and a Check before its name. A focused and selected card shows both, distinct. The first-column ring is
   not clipped. "Use the default template" shows a Check when chosen.

**Docs.** In the `docs/frontend-conventions.md:34-52` Colour roles bullet:
- Add employment types, section presets and the template picker to the "tonal + Check + `aria-pressed`" list. The picker
  keeps its primary edge as a card's border cue.
- Add gap-target chips to the full-strength-fill exception, with the reason: dense truncating chips, and the fill is the gap's
  answer. (Skip this if the owner converts them.)
- Add a sentence: **selection never borrows the focus ring's shape. A selectable card's focus ring is offset onto the
  surface, and its selection is its own edge plus a Check.**
- `:80-87` (the template picker): note the offset focus ring and the Check.

---

## W5. Studio section tab panels have no visible focus ring (§11 item 28, third clause)

**Where.**
- `components/ui/tabs.tsx:79-105`, `TabsContent`: `"flex-1 text-sm outline-none"`.
- Base UI 1.4.1 renders the open panel with `tabIndex: open ? 0 : -1` (`node_modules/@base-ui/react/tabs/panel/TabsPanel.js:83`).
  That is APG's tab panel. The studios' seven-tab block (`editor-body.tsx:505-568`, `tailored-resume-studio.tsx:942-1029`)
  therefore puts the panel in the Tab order right after the tab list. `outline-none` erases the only indicator, so a keyboard
  user presses Tab and focus disappears. That is WCAG 2.4.7.

**Which element takes focus.** The panel `<div role="tabpanel" tabindex="0">`, not its first field. The same primitive
serves every tabbed surface:
- the Analytics tabs (`app/analytics/page.tsx:186,223,262`)
- the job page (`app/jobs/[id]/page.tsx:481-513`)
- the Career KB (`app/career/page.tsx:119`)
- the upload dialog, chat scope picker, new base résumé dialog and KB import drawer

So the fix belongs in the primitive, and it fixes all of them.

**Options.**
- **A (recommended), in the primitive:** replace `outline-none` with an **inset** solid outline on `:focus-visible`.
- B: make the studio panels untabbable (`tabIndex={-1}`). This was rejected: APG wants a focusable panel when its first
  content is not focusable (the Analytics chart panels), and B would silently fix only the studios.
- C: `ring-2` (a box-shadow). This was rejected: a box-shadow paints outside the box and is clipped by the studio pane's
  `overflow-y-auto`, and an inset box-shadow paints *under* child cards.

An outline with a negative offset draws inside the panel's box, **above** its content, and no ancestor's overflow can clip it.

**Fix.**

```tsx
function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      className={cn(
        // Base UI makes the open panel a tab stop (APG). The indicator is an
        // INSET outline: it paints above the panel's cards and no scrolling
        // ancestor can clip it. Never pair it with `outline-none`: that sets
        // --tw-outline-style: none, which outline-2 reads, and the ring never paints.
        "flex-1 text-sm focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
        …the [&[inert]]:hidden comment and class, unchanged…
        className
      )}
      {...props}
    />
  )
}
```

The "one class" is really a swap, `outline-none` for three `focus-visible:` utilities. Mouse clicks inside a panel do not match
`:focus-visible` in Chromium or WebKit for a non-input element, so pointer users see no ring.

**Contrast.** The solid `--ring` is already pinned at ≥ 3:1 on page, card and muted (`_RING_SURFACES`):
- 4.19 (light) and 5.42 (dark) on the page, where the studios, Analytics and the job page sit;
- 4.49 and 4.91 on the card and popover, where the dialogs and the drawer sit.

**Pin** (`test_frontend_color_roles.py`, next to the focus tests):

```python
def test_tab_panels_show_a_solid_inset_focus_outline():
    tabs = _read("components/ui/tabs.tsx")
    panel = tabs[tabs.index("function TabsContent") : tabs.index("export {")]
    assert "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring" in panel
    # outline-none zeroes --tw-outline-style, which outline-2 reads: no ring at all.
    assert "outline-none" not in panel
    assert "[&[inert]]:hidden" in panel
```

**Browser checks.**
1. Base studio at 1280: Tab to the section tab list, then Tab again. A 2px blue outline appears just inside the panel's edge
   and is drawn over the Contact card. Arrow keys still move between tabs.
2. Tailored studio, same check. At 768, with the preview open, the outline is not clipped by the pane's scroller.
3. Click anywhere inside a panel. No outline appears.
4. Analytics, the job page, and the new base résumé dialog: Tab into a panel and the outline shows. Check light and dark.
5. WebKit (the desktop shell): the same Tab path. WebKit does not focus scrollers itself (see the conventions' PdfPagesPreview note), but a
   `tabindex=0` panel is focusable.

**Edge cases.**
- A panel's own `className` could add `outline-none` back. None of the 16 call sites do today (grep). The pin covers only the
  primitive.
- On a panel whose first child is flush with its edge, the outline covers that child's outer 2px only while focused.

**Docs and ledger.**
- `docs/frontend-conventions.md:368-373`, the `TabsContent` bullet: add *"the open panel is a tab stop (Base UI, APG); its
  focus indicator is an inset solid outline, `-outline-offset-2`, so a scrolling pane cannot clip it and its cards cannot
  cover it; never `outline-none` beside an `outline-N`."*
- `:53-68` (focus rule): add the Tailwind `outline-none` trap in one clause.
- **SYSTEM.md §11 item 28**: delete *"the studio section tabs' `TabsContent` panels take focus with no visible ring."* The
  agent-pipeline bar and the dark ring on the FAB remain. Delete the whole item only if another appendix fixes those two.

---

## Docs to update (collected; integrate in present tense, same commit as the code)

| File | Where | Task |
|---|---|---|
| `docs/frontend-conventions.md` | new bullet "An edit is described, never printed" (after `:292-301`) | T1 |
| same | `:670-679` Analytics sentence on `baseResumeLabel`, rewritten as a résumé-naming rule; `:80-87` picker (no engine chip) | T2 |
| same | `:434-441` Shared components, the generalised chip pin | T3 |
| same | `:34-52` colour roles (the selection lists and exceptions, focus ≠ selection); `:80-87` picker (offset focus, Check) | T4 |
| same | `:53-68` focus (the `outline-none` trap); `:368-373` `TabsContent` | T5 |
| `SYSTEM.md` §11 | item 30: drop the Base-column clause | T2 |
| `SYSTEM.md` §11 | item 28: drop the `TabsContent` clause | T5 |
| `docs/entities/application.md` | `base_resume_name` on summary and detail (if B lands) | T2 |

All the SYSTEM.md edits are deletions, so the 999/1000 cap is safe. Run `python3 scripts/check_system_md.py` after T2 and T5.

---

## Open questions for the owner

1. **W1, words after a reload.** Resolved cards describe without entry names after a page reload (recommended; never wrong). The alternative is
   server-stamped `labels` on `proposal_ops` and `BaseResumeProposeRead` (additive), which keeps names forever at the cost
   of a Python twin of the copy and a contract test.
2. **W2, backend names.** Add additive `base_resume_name` to `ApplicationSummary` and `ApplicationDetail` (recommended)? It names
   deleted bases in the tracker and the application panel, and gives MCP `list_applications` / `get_application` a name to
   narrate. Without it the frontend hook still covers everything except soft-deleted bases.
3. **W2, optional clean-up.** Also fold the four copies of the default base-resume list query into `useBaseResumes()`? This lowers
   duplication and is not required.
4. **W2, engine and status chips.** The picker shows no engine; the manage gallery and the editor show "LaTeX" / "Typst" and "Ready" /
   "Draft" (recommended). The alternative removes the engine chip everywhere. Also decide whether the picker drops the status
   badge too, since it lists only ready templates.
5. **W4, gap-target chips.** Keep them solid `bg-primary` + `aria-pressed` as a recorded exception (recommended; dense truncating chips).
   The alternative converts them to tonal + Check. The text-contrast fixes inside the chip apply either way.
6. **W3, reach.** Extend the chip pin and the fix to the KB entity chips ("Completed" measures 4.04 over muted), and move the three
   `text-amber-600` template badges and labels to `amber-700` (recommended; they measure 2.98–3.19:1 today)?

## Seen nearby, not in scope

- `gap-analysis/resolution-controls.tsx:245-265` `ActionSegment`: the selected segment is `bg-background` on a `bg-muted`
  track, 1.11:1 in light mode and 1.31:1 in dark. `TabsList` uses the same pattern. Both have `aria-pressed` or the tab role, but the visual state is
  faint. This belongs to a tabs and segments pass, not here.
- MCP `score_ats` / `rank_bases` hints and `get_tailoring_session` name bases by slug. An agent can resolve names with
  `list_base_resumes`, which carries `display_name`.
- Both studios duplicate the seven-tab block (`editor-body.tsx:505-568`, `tailored-resume-studio.tsx:942-1029`). That is a
  known clone source, and W5 does not touch it.
