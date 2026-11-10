// Undo and Redo in the studio's Review changes list (components/resume-editor/diff-review.tsx): an Undo is
// `revertHunk`, a Redo is `revertHunk` of that Undo's own inverse (`inverseHunk`), and the row's one button says
// which of the two it does. The resume pair and its hunks are the backend's own
// (backend/tests/test_resume_diff_fixture.py writes the file and fails when the diff drifts from it).
// pytest runs this file: backend/tests/test_frontend_resume_review.py.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { React, load, renderElement } from "../render-harness.mjs";

const { DiffReviewPanel, hunkKey, inverseHunk, revertHunk } = load("components/resume-editor/diff-review.tsx");
const { resumeDataSchema } = load("lib/resume-schema.ts");

const fixture = JSON.parse(
  fs.readFileSync(path.join(import.meta.dirname, "../../../backend/tests/fixtures/resume_diff/review-changes.json"), "utf8"),
);
/** The saved draft as the studio holds it, and the list Review changes shows for it. */
const saved = resumeDataSchema.parse(fixture.tailored);
const hunks = fixture.hunks;
const text = (doc) => JSON.stringify(doc);

/** The studio's two handlers over one draft: `undone` is its map from a row to that row's Redo. */
function studio(start = saved) {
  const state = { draft: start, undone: new Map() };
  return {
    state,
    undo(i) {
      const next = revertHunk(state.draft, hunks[i]);
      if (!next) return false;
      state.undone.set(i, inverseHunk(state.draft, next, hunks[i]));
      state.draft = next;
      return true;
    },
    redo(i) {
      const next = revertHunk(state.draft, state.undone.get(i), saved);
      if (!next) return false;
      state.undone.delete(i);
      state.draft = next;
      return true;
    },
  };
}

/** The entry that is both hidden and reworded: its two rows edit the same place, so they have their own test. */
const HIDDEN = hunks.findIndex((h) => h.kind === "entry_disabled" && h.section === "experience");
const REWORDED_INSIDE = hunks.findIndex((h) => h.kind === "bullet_edited" && h.section === "experience" && h.index === hunks[HIDDEN].index);
const apart = hunks.map((_, i) => i).filter((i) => i !== HIDDEN);

/** A seeded shuffle (mulberry32), so a failing order can be run again. */
function shuffler(seed) {
  let a = seed;
  const random = () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return (items) => {
    const out = [...items];
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  };
}

test("the fixture covers the rows this file is about", () => {
  assert.ok(HIDDEN >= 0 && REWORDED_INSIDE >= 0);
  assert.equal(hunks.length, 31);
});

test("Undo then Redo puts one change back exactly, as often as it is pressed", () => {
  for (const i of hunks.keys()) {
    const s = studio();
    for (let round = 0; round < 3; round++) {
      assert.ok(s.undo(i), `undo ${i} ${hunks[i].kind}`);
      assert.notEqual(text(s.state.draft), text(saved), `undo ${i} ${hunks[i].kind} changed nothing`);
      assert.ok(s.redo(i), `redo ${i} ${hunks[i].kind}`);
      assert.equal(text(s.state.draft), text(saved), `redo ${i} ${hunks[i].kind}`);
    }
  }
});

test("every order of undoing and redoing three siblings ends on the saved draft", () => {
  const orders = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  const families = [
    hunks.flatMap((h, i) => (h.kind === "skills_group_changed" && h.before === null ? [i] : [])),
    hunks.flatMap((h, i) => (h.kind === "bullet_added" && h.section === "experience" ? [i] : [])),
    hunks.flatMap((h, i) => (h.kind === "bullet_removed" && h.section === "experience" ? [i] : [])),
    hunks.flatMap((h, i) => (h.kind === "entry_added" ? [i] : [])),
    hunks.flatMap((h, i) => (h.kind === "entry_removed" ? [i] : [])),
    hunks.flatMap((h, i) => (h.kind === "bullet_added" && h.section === "certifications" ? [i] : [])),
  ];
  for (const family of families) {
    assert.equal(family.length, 3);
    for (const undoOrder of orders) {
      for (const redoOrder of orders) {
        const s = studio();
        const label = `${hunks[family[0]].kind} in ${hunks[family[0]].section}: undo ${undoOrder}, redo ${redoOrder}`;
        for (const n of undoOrder) assert.ok(s.undo(family[n]), `${label} (undo ${n})`);
        for (const n of redoOrder) assert.ok(s.redo(family[n]), `${label} (redo ${n})`);
        assert.equal(text(s.state.draft), text(saved), label);
      }
    }
  }
});

test("rows undone and redone in any mix, across every section, end on the saved draft", () => {
  for (let seed = 1; seed <= 150; seed++) {
    const shuffle = shuffler(seed);
    const s = studio();
    // Undo a random half, redo some of those, undo more, then redo everything still undone, each in its own order.
    const picked = shuffle(apart);
    const first = picked.slice(0, 15);
    for (const i of first) assert.ok(s.undo(i), `seed ${seed}: undo ${i} ${hunks[i].kind}`);
    for (const i of shuffle(first).slice(0, 7)) assert.ok(s.redo(i), `seed ${seed}: redo ${i} ${hunks[i].kind}`);
    for (const i of picked.slice(15, 24)) assert.ok(s.undo(i), `seed ${seed}: late undo ${i} ${hunks[i].kind}`);
    for (const i of shuffle([...s.state.undone.keys()])) assert.ok(s.redo(i), `seed ${seed}: last redo ${i} ${hunks[i].kind}`);
    assert.equal(s.state.undone.size, 0);
    assert.equal(text(s.state.draft), text(saved), `seed ${seed}`);
  }
});

test("Redo puts back what the draft held, a hand edit included, not the saved text", () => {
  const SUMMARY = hunks.findIndex((h) => h.kind === "summary_changed");
  const GROUP = hunks.findIndex((h) => h.kind === "skills_group_changed" && h.before !== null);
  const edited = resumeDataSchema.parse({
    ...saved,
    summary: `${saved.summary} Open to night shifts.`,
    skills: saved.skills.map((group, at) => (at === hunks[GROUP].index ? { ...group, items: [...group.items, "Night dispatch"] } : group)),
  });
  const s = studio(edited);
  assert.ok(s.undo(SUMMARY) && s.undo(GROUP));
  assert.equal(s.state.draft.summary, fixture.base.summary);
  assert.deepEqual(s.state.draft.skills[hunks[GROUP].index], fixture.base.skills[hunks[GROUP].index]);
  assert.ok(s.redo(GROUP) && s.redo(SUMMARY));
  assert.equal(text(s.state.draft), text(edited));
});

test("a Redo whose restored text was edited since refuses instead of overwriting it", () => {
  const GROUP = hunks.findIndex((h) => h.kind === "skills_group_changed" && h.before !== null);
  const s = studio();
  assert.ok(s.undo(GROUP));
  const at = hunks[GROUP].index;
  s.state.draft = resumeDataSchema.parse({
    ...s.state.draft,
    skills: s.state.draft.skills.map((group, n) => (n === at ? { ...group, items: [...group.items, "Typed since"] } : group)),
  });
  const before = text(s.state.draft);
  assert.equal(s.redo(GROUP), false);
  assert.equal(text(s.state.draft), before);
});

test("two rows over one entry: the outer Redo waits for the inner row, then both land exactly", () => {
  const s = studio();
  assert.ok(s.undo(REWORDED_INSIDE) && s.undo(HIDDEN));
  // Last undone, first redone, works as it does anywhere.
  assert.ok(s.redo(HIDDEN) && s.redo(REWORDED_INSIDE));
  assert.equal(text(s.state.draft), text(saved));
  // The other way round, the entry Undo put back has changed under its row: that Redo refuses and writes nothing.
  assert.ok(s.undo(REWORDED_INSIDE) && s.undo(HIDDEN) && s.redo(REWORDED_INSIDE));
  const held = text(s.state.draft);
  assert.equal(s.redo(HIDDEN), false);
  assert.equal(text(s.state.draft), held);
  // Undoing the inner row again frees it.
  assert.ok(s.undo(REWORDED_INSIDE) && s.redo(HIDDEN) && s.redo(REWORDED_INSIDE));
  assert.equal(text(s.state.draft), text(saved));
});

test("undoing added siblings top down takes out each one's own item", () => {
  const added = hunks.flatMap((h, i) => (h.kind === "skills_group_changed" && h.before === null ? [i] : []));
  const s = studio();
  assert.ok(s.undo(added[0]) && s.undo(added[1]));
  assert.deepEqual(s.state.draft.skills.map((group) => group.category), [
    ...fixture.base.skills.map((group) => group.category),
    hunks[added[2]].after.category,
  ]);
});

// --- the row ---------------------------------------------------------------------------------------------------

const SUMMARY = hunks.findIndex((h) => h.kind === "summary_changed");
const panel = (revertedKeys) =>
  renderElement(
    React.createElement(DiffReviewPanel, { hunks, revertedKeys, dirty: revertedKeys.size > 0, onRevert() {}, onRedo() {} }),
  );
/** Each row's button: its words, the name its `aria-labelledby` builds, and its attributes. */
function rowButtons(html) {
  const byId = (id) => new RegExp(`id="${id}"[^>]*>(.*?)</(?:span|button)>`, "s").exec(html)?.[1].replace(/<[^>]+>/g, "").trim();
  return [...html.matchAll(/<li\b.*?<button\b([^>]*)>(.*?)<\/button><\/li>/gs)].map(([, attrs, inner]) => ({
    attrs,
    words: inner.replace(/<[^>]+>/g, "").trim(),
    name: /aria-labelledby="([^"]+)"/.exec(attrs)?.[1].split(" ").map(byId).join(" "),
    describedBy: /aria-describedby="([^"]+)"/.exec(attrs)?.[1],
  }));
}

test("an undone row offers Redo where Undo was, named for its change, and the others keep Undo", () => {
  const html = panel(new Set([hunkKey(hunks[SUMMARY], SUMMARY)]));
  const buttons = rowButtons(html);
  assert.equal(buttons.length, hunks.length);
  const redo = buttons.filter((b) => b.words === "Redo");
  assert.equal(redo.length, 1);
  assert.equal(redo[0].name, "Redo Summary rewritten");
  // Never disabled (the class list names the state; no attribute sets it): Redo can be focused and pressed.
  assert.ok(!/\s(?:aria-|data-)?disabled(?:=|\s|$)/.test(redo[0].attrs), redo[0].attrs);
  // The same ghost xs button as Undo, with the arrow that mirrors Undo's.
  const undo = buttons.find((b) => b.words === "Undo");
  assert.equal(undo.name.split(" ")[0], "Undo");
  assert.equal(/class="([^"]*)"/.exec(redo[0].attrs)[1], /class="([^"]*)"/.exec(undo.attrs)[1]);
  assert.match(html, /lucide-redo-2/);
  assert.equal((html.match(/lucide-undo-2/g) ?? []).length, hunks.length - 1);
  // Its row still says the change is undone and unsaved, on the heading's own line.
  assert.equal((html.match(/Undone\. Not saved yet\./g) ?? []).length, 1);
  // The description is the row's own old and new text.
  assert.match(html, new RegExp(`id="${redo[0].describedBy}"[^>]*>.*?Before: `, "s"));
});

test("with nothing undone every row offers Undo, each named for its change", () => {
  const buttons = rowButtons(panel(new Set()));
  assert.deepEqual([...new Set(buttons.map((b) => b.words))], ["Undo"]);
  assert.ok(buttons.every((b) => b.name.startsWith("Undo ") && b.name.length > 5 && b.describedBy));
  assert.equal(new Set(buttons.map((b) => b.describedBy)).size, buttons.length);
});
