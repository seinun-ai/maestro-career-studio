import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import {
  FIELD,
  TABBABLE,
  finalFocusOn,
  focusIfDropped,
  focusIfStranded,
  focusReturnPoint,
  focusSuccessor,
  focusTarget,
  holdsDraft,
} from "./focus.ts";

/**
 * A stand-in DOM, just enough for these helpers: a tree, `isConnected`, focus, and the three selectors
 * they use. An unknown selector throws, so a helper that starts asking for something else fails loudly.
 */
class El {
  tag: string;
  attrs: Record<string, string>;
  children: El[] = [];
  parentElement: El | null = null;
  isContentEditable = false;

  constructor(tag: string, attrs: Record<string, string> = {}) {
    this.tag = tag;
    this.attrs = attrs;
  }

  get tabIndex(): number {
    return this.attrs.tabindex === undefined ? -1 : Number(this.attrs.tabindex);
  }

  get isConnected(): boolean {
    return this.parentElement ? this.parentElement.isConnected : doc.documentElement === this;
  }

  private sibling(step: number): El | null {
    const kids = this.parentElement?.children ?? [];
    return kids[kids.indexOf(this) + step] ?? null;
  }

  get nextElementSibling(): El | null {
    return this.sibling(1);
  }

  get previousElementSibling(): El | null {
    return this.sibling(-1);
  }

  append(...kids: El[]): this {
    for (const kid of kids) {
      kid.parentElement = this;
      this.children.push(kid);
    }
    return this;
  }

  remove(): void {
    const parent = this.parentElement;
    if (!parent) return;
    parent.children.splice(parent.children.indexOf(this), 1);
    this.parentElement = null;
  }

  private isField(): boolean {
    if ("disabled" in this.attrs) return false;
    if (this.tag === "input") return this.attrs.type !== "hidden";
    return this.tag === "textarea" || this.tag === "select";
  }

  matches(selector: string): boolean {
    if (selector === FIELD) return this.isField();
    if (selector === TABBABLE) {
      if (this.isField()) return true;
      if (this.tag === "button") return !("disabled" in this.attrs);
      if (this.tag === "a") return "href" in this.attrs;
      return this.attrs.tabindex !== undefined && this.attrs.tabindex !== "-1";
    }
    if (selector === '[tabindex="-1"]') return this.attrs.tabindex === "-1";
    if (selector === "[inert]") return "inert" in this.attrs;
    throw new Error(`stand-in DOM: unknown selector ${selector}`);
  }

  closest(selector: string): El | null {
    if (this.matches(selector)) return this;
    return this.parentElement ? this.parentElement.closest(selector) : null;
  }

  querySelector(selector: string): El | null {
    for (const kid of this.children) {
      if (kid.matches(selector)) return kid;
      const deeper = kid.querySelector(selector);
      if (deeper) return deeper;
    }
    return null;
  }

  focus(): void {
    doc.activeElement = this;
  }
}
class Input extends El {}
class TextArea extends El {}

const doc = {
  documentElement: new El("html"),
  body: new El("body"),
  activeElement: null as El | null,
  getElementById(id: string): El | null {
    const walk = (e: El): El | null => {
      if (e.attrs.id === id) return e;
      for (const kid of e.children) {
        const hit = walk(kid);
        if (hit) return hit;
      }
      return null;
    };
    return walk(doc.documentElement);
  },
};

Object.assign(globalThis, {
  document: doc,
  HTMLElement: El,
  HTMLInputElement: Input,
  HTMLTextAreaElement: TextArea,
});

const h = (tag: string, attrs: Record<string, string> = {}, ...kids: El[]): El => {
  const Ctor = tag === "input" ? Input : tag === "textarea" ? TextArea : El;
  return new Ctor(tag, attrs).append(...kids);
};
const asEl = (e: El | null) => e as unknown as HTMLElement;

beforeEach(() => {
  doc.documentElement = new El("html");
  doc.body = new El("body");
  doc.documentElement.append(doc.body);
  doc.activeElement = doc.body;
});

test("a dropped focus moves to the target", () => {
  const target = h("button");
  doc.body.append(target);
  focusIfDropped(asEl(target));
  assert.equal(doc.activeElement, target);
});

test("no active element at all counts as dropped", () => {
  const target = h("button");
  doc.body.append(target);
  doc.activeElement = null;
  focusIfDropped(asEl(target));
  assert.equal(doc.activeElement, target);
});

test("focus the user put somewhere else stays there", () => {
  const target = h("button");
  const summary = h("textarea");
  doc.body.append(target, summary);
  summary.focus();
  focusIfDropped(asEl(target));
  assert.equal(doc.activeElement, summary);
});

test("no target leaves a dropped focus alone", () => {
  focusIfDropped(null);
  assert.equal(doc.activeElement, doc.body);
});

test("the return point is the element itself while it is connected", () => {
  const field = h("input");
  const panel = h("div", { tabindex: "-1" }, field);
  doc.body.append(h("main", { id: "main-content", tabindex: "-1" }, panel));
  assert.equal(focusReturnPoint(asEl(field))(), field);
});

test("a removed element returns to the nearest tabIndex=-1 ancestor that survived", () => {
  const field = h("input");
  const inner = h("section", { tabindex: "-1" }, h("div", {}, field));
  const outer = h("div", { tabindex: "-1" }, inner);
  doc.body.append(h("main", { id: "main-content", tabindex: "-1" }, outer));
  const back = focusReturnPoint(asEl(field));
  field.remove();
  assert.equal(back(), inner);
  inner.remove();
  assert.equal(back(), outer, "the chain was read while attached, so the outer panel is still found");
});

test("with no surviving panel the main area is the return point", () => {
  const field = h("input");
  const panel = h("div", { tabindex: "-1" }, field);
  const main = h("main", { id: "main-content", tabindex: "-1" });
  doc.body.append(main, panel);
  const back = focusReturnPoint(asEl(field));
  panel.remove();
  assert.equal(back(), main);
});

test("body and nothing have no return point", () => {
  assert.equal(focusReturnPoint(asEl(doc.body))(), null);
  assert.equal(focusReturnPoint(null)(), null);
});

/** A gallery: three cards (each a link and a ⋯) in a grid inside a `tabIndex={-1}` list, inside the main area. */
function gallery() {
  const cards = ["a", "b", "c"].map((id) => h("div", { id }, h("a", { href: `/${id}` }), h("button")));
  const grid = h("div", {}, ...cards);
  const list = h("section", { tabindex: "-1" }, grid);
  const main = h("main", { id: "main-content", tabindex: "-1" }, list);
  doc.body.append(main);
  return { cards, grid, list, main };
}

test("a removed item hands focus to the next item's first tabbable", () => {
  const { cards } = gallery();
  const back = focusSuccessor(asEl(cards[1]));
  assert.equal(back(), cards[2].children[0], "even while the item is still attached");
  cards[1].remove();
  assert.equal(back(), cards[2].children[0]);
});

test("the last item hands focus back to the previous one", () => {
  const { cards } = gallery();
  const back = focusSuccessor(asEl(cards[2]));
  cards[2].remove();
  assert.equal(back(), cards[1].children[0]);
});

test("the only item hands focus to the list, then the main area", () => {
  const { cards, grid, list, main } = gallery();
  cards[0].remove();
  cards[2].remove();
  const back = focusSuccessor(asEl(cards[1]));
  assert.equal(back(), list, "never the item itself, though it is still attached");
  grid.remove();
  assert.equal(back(), list, "the list outlives the grid");
  list.remove();
  assert.equal(back(), main);
});

test("a return target that takes focus is handed to Base UI", () => {
  const button = h("button", { tabindex: "0" });
  assert.equal(finalFocusOn(asEl(button)), button);
});

test("no return target is Base UI's default", () => {
  assert.equal(finalFocusOn(null), true);
});

test("a landmark is focused directly once focus has dropped", async () => {
  const list = h("section", { tabindex: "-1" });
  doc.body.append(list);
  assert.equal(finalFocusOn(asEl(list)), false, "Base UI would focus its first tabbable child");
  assert.equal(doc.activeElement, doc.body, "not before the popup has gone");
  await Promise.resolve();
  assert.equal(doc.activeElement, list);
});

test("a control that takes focus itself is its own target", () => {
  const pencil = h("button");
  assert.equal(focusTarget(asEl(pencil)), pencil);
});

test("an editor lands in its first text field, even behind a button", () => {
  const field = h("textarea");
  const editor = h("div", {}, h("button"), h("div", {}, field), h("input"));
  assert.equal(focusTarget(asEl(editor)), field);
});

test("disabled and hidden inputs are not fields", () => {
  const name = h("input");
  const editor = h("div", {}, h("input", { type: "hidden" }), h("input", { disabled: "" }), name);
  assert.equal(focusTarget(asEl(editor)), name);
});

test("an editor with no field lands on its first tabbable, else on itself", () => {
  const done = h("button");
  assert.equal(focusTarget(asEl(h("div", {}, h("span"), done))), done);
  const empty = h("div", {}, h("span"));
  assert.equal(focusTarget(asEl(empty)), empty);
});

test("inputs, textareas and contenteditables hold drafts; buttons do not", () => {
  assert.equal(holdsDraft(asEl(h("input"))), true);
  assert.equal(holdsDraft(asEl(h("textarea"))), true);
  const editable = h("div");
  editable.isContentEditable = true;
  assert.equal(holdsDraft(asEl(editable)), true);
  assert.equal(holdsDraft(asEl(h("button"))), false);
  assert.equal(holdsDraft(null), false);
});

test("focusIfStranded takes focus from <body> or an inert panel, never from a live control", () => {
  const hidden = h("div", { role: "tabpanel", inert: "" }, h("button", { id: "old" }));
  const shownPanel = h("div", { role: "tabpanel", tabindex: "0", id: "new" });
  const live = h("button", { id: "live" });
  doc.body.append(hidden, shownPanel, live);
  (doc.getElementById("old") as El).focus();
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, shownPanel);
  live.focus();
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, live);
  doc.activeElement = doc.body;
  focusIfStranded(asEl(shownPanel));
  assert.equal(doc.activeElement, shownPanel);
});
