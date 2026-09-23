import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { FIELD, TABBABLE, focusIfDropped, focusReturnPoint, focusTarget, holdsDraft } from "./focus.ts";

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
