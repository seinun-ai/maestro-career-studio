import assert from "node:assert/strict";
import { test } from "node:test";

import {
  readEntry,
  stampAfterWrite,
  stampState,
  startGuard,
  stepGuard,
  type EntryKind,
  type GuardCommand,
  type GuardEvent,
  type GuardState,
  type HistoryEntry,
} from "./leave-guard.ts";

/**
 * A tab's history, Next's popstate listener and our listeners, reduced to what the
 * machine sees. `shown` is the page Next rendered; `url` is the address bar.
 */
type Slot = { url: string; kind: EntryKind | "other-site"; sentinel: boolean; at: number | null };

class Tab {
  slots: Slot[];
  index: number;
  s: GuardState;
  shown: string;
  asking = false;
  bypass = false;
  unloaded: "quiet" | "warned" | null = null;
  blocked = false;

  constructor(url: string, otherSiteBefore = 0) {
    this.slots = Array.from({ length: otherSiteBefore }, () => ({
      url: "https://elsewhere.example/",
      kind: "other-site" as const,
      sentinel: false,
      at: null,
    }));
    this.slots.push({ url, kind: "none", sentinel: false, at: null }); // before hydration
    this.index = this.slots.length - 1;
    this.shown = url;
    this.s = startGuard(this.entry(), this.slots.length, false);
    this.write("replace", url, false); // Next's hydration replaceState
  }

  get url() {
    return this.slots[this.index].url;
  }

  entry(i = this.index): HistoryEntry {
    const slot = this.slots[i];
    return { at: slot.at, kind: slot.kind as EntryKind, sentinel: slot.sentinel, url: slot.url };
  }

  feed(event: GuardEvent): GuardCommand[] {
    const [next, commands] = stepGuard(this.s, event);
    this.s = next;
    return commands;
  }

  /** An app-router write, stamped the way the listeners' history patch stamps it. */
  write(how: "push" | "replace", url: string, sentinel: boolean) {
    const before = this.entry();
    if (how === "push") {
      this.slots.splice(this.index + 1);
      this.slots.push({ url, kind: "next", sentinel, at: null });
      this.index += 1;
    } else this.slots[this.index] = { url, kind: "next", sentinel, at: before.at };
    const stamp = stampAfterWrite(how, before, this.entry(), this.slots.length, this.s.here.at);
    Object.assign(this.slots[this.index], stamp);
    assert.equal(stamp.at, this.index, "the stamp is the entry's position");
    this.run(this.feed({ type: "wrote", how, entry: this.entry(), length: this.slots.length }));
  }

  /** A clean in-app link (GuardedLink passes straight through). */
  link(url: string) {
    assert.equal(this.blocked, false);
    this.write("push", url, false);
    this.shown = url;
  }

  edit() {
    this.setBlocked(true);
  }

  saved() {
    this.setBlocked(false);
  }

  setBlocked(blocked: boolean) {
    this.blocked = blocked;
    this.run(this.feed({ type: "blocked", blocked }));
  }

  /** The skip link (#main-content): a fragment navigation fires popstate with no state. */
  fragment() {
    this.slots.splice(this.index + 1);
    this.slots.push({ url: this.url, kind: "none", sentinel: false, at: null });
    this.index += 1;
    this.pop();
  }

  back() {
    return this.go(-1);
  }

  forward() {
    return this.go(1);
  }

  /** A browser traversal. False when there is no entry there. */
  go(delta: number): boolean {
    const target = this.index + delta;
    if (target < 0 || target >= this.slots.length || this.unloaded) return false;
    this.index = target;
    if (this.slots[target].kind === "other-site") {
      this.unloaded = this.blocked && !this.bypass ? "warned" : "quiet";
      return true;
    }
    this.pop();
    return true;
  }

  pop() {
    const commands = this.feed({ type: "pop", entry: this.entry(), length: this.slots.length });
    const stopped = commands.some((c) => c.type === "stop");
    // Next's bubble listener: ignores a stateless entry, renders an app-router one.
    if (!stopped && this.slots[this.index].kind === "next") this.render(this.url);
    this.run(commands);
  }

  answer(leave: boolean) {
    assert.equal(this.asking, true, "the question is open");
    this.asking = false;
    this.run(this.feed({ type: "answer", leave }));
  }

  reload() {
    this.blocked = false;
    this.asking = false;
    this.shown = this.url;
    this.s = startGuard(this.entry(), this.slots.length, false);
  }

  /** Next rendered a different page: the editor unmounts and unregisters. */
  render(url: string) {
    if (url !== this.shown && this.blocked) {
      this.blocked = false;
      this.shown = url;
      this.run(this.feed({ type: "blocked", blocked: false }));
    }
    this.shown = url;
  }

  run(commands: GuardCommand[]) {
    for (const c of commands) {
      if (c.type === "stop") continue;
      if (c.type === "ask") this.asking = true;
      else if (c.type === "setBypass") this.bypass = c.on;
      else if (c.type === "go") this.go(c.delta);
      else if (c.type === "pushSentinel") this.write("push", this.url, true);
      else if (c.type === "replay") this.render(this.url);
      else if (c.type === "renderHere") {
        this.write("replace", this.url, false);
        this.render(this.url);
      } else if (c.type === "navigateAway") {
        this.render("/applications");
        this.write("push", "/applications", false);
      } else if (c.type === "restorePage") this.write("push", this.shown, false);
    }
  }

  /** Address bar and page agree whenever no question is open. */
  agrees() {
    assert.equal(this.asking, false);
    assert.equal(this.url, this.shown, "the URL and the page agree");
  }

  /** Press Back until nothing is left; every press must change the page. */
  walkBack(): string[] {
    const seen: string[] = [];
    while (this.back()) {
      assert.notEqual(this.shown, seen.at(-1) ?? null, `dead Back press at ${this.shown}`);
      this.agrees();
      seen.push(this.shown);
    }
    return seen;
  }
}

/** /list → /studio with one unsaved edit: the sentinel is parked above the studio. */
function dirtyStudio(before: string[] = ["/list"]): Tab {
  const tab = new Tab(before[0]);
  for (const url of before.slice(1)) tab.link(url);
  tab.link("/studio");
  tab.edit();
  assert.equal(tab.slots.length, before.length + 2, "the first edit parks a sentinel");
  assert.equal(tab.slots[tab.index].sentinel, true);
  return tab;
}

test("a clean Back renders the previous page in one press", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  tab.back();
  assert.equal(tab.asking, false);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a dirty Back asks, and Stay keeps the page and asks again next time", () => {
  const tab = dirtyStudio();
  tab.back();
  assert.equal(tab.asking, true);
  assert.equal(tab.shown, "/studio");
  assert.equal(tab.url, "/studio");
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, true, "parked again");
  tab.back();
  assert.equal(tab.asking, true);
});

test("a dirty Back, Leave goes back one real entry and clears the bypass", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.back();
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
  assert.equal(tab.bypass, false);
});

test("two Backs while asking: Stay puts the URL back on the editor", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.back();
  tab.back();
  assert.equal(tab.shown, "/studio", "the page stays under the dialog");
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, true);
});

test("three Backs while asking: Stay returns, then Leave goes to the page before", () => {
  const tab = dirtyStudio(["/a", "/b", "/list"]);
  tab.back();
  tab.back();
  tab.back();
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.shown, "/studio");
  tab.back();
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
  assert.deepEqual(tab.walkBack(), ["/b", "/a"]);
});

test("Back then Forward while asking: both answers land right", () => {
  for (const leave of [false, true]) {
    const tab = dirtyStudio(["/a", "/list"]);
    tab.back();
    tab.back();
    tab.forward();
    tab.answer(leave);
    tab.agrees();
    assert.equal(tab.shown, leave ? "/list" : "/studio");
  }
});

test("Forward while asking is not a Back", () => {
  for (const leave of [false, true]) {
    const tab = dirtyStudio(["/a", "/list"]);
    tab.back();
    tab.forward();
    tab.answer(leave);
    tab.agrees();
    assert.equal(tab.shown, leave ? "/list" : "/studio");
  }
});

test("a save that lands while asking, then Stay: the next Back leaves in one press", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.back();
  tab.saved();
  tab.answer(false);
  tab.agrees();
  tab.back();
  assert.equal(tab.asking, false);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("undo to clean while parked leaves no dead step, before or after a link", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.saved();
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/list");
  tab.forward();
  tab.agrees();
  assert.equal(tab.shown, "/studio");
  assert.equal(tab.forward(), false, "nothing is left in front");
  tab.link("/other");
  assert.deepEqual(tab.walkBack(), ["/studio", "/list", "/a"]);
});

test("Back-Leave, then Forward twice: no dead step", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.back();
  tab.answer(true);
  assert.equal(tab.shown, "/list");
  tab.forward();
  tab.agrees();
  assert.equal(tab.shown, "/studio");
  assert.equal(tab.forward(), false);
  assert.deepEqual(tab.walkBack(), ["/list", "/a"]);
});

test("a fragment pop while parked asks nothing, keeps the guard, leaves no bypass", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.fragment();
  assert.equal(tab.asking, false);
  assert.equal(tab.bypass, false, "a reload still warns");
  tab.back(); // back to the sentinel: same page
  assert.equal(tab.asking, false);
  tab.agrees();
  tab.back();
  assert.equal(tab.asking, true, "still guarded");
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a fresh tab: Leave goes to the app's home, and Back returns to the editor", () => {
  const tab = new Tab("/studio");
  tab.edit();
  tab.back();
  assert.equal(tab.asking, true);
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/applications");
  assert.deepEqual(tab.walkBack(), ["/studio"]);
});

test("a fresh tab: Stay parks again", () => {
  const tab = new Tab("/studio");
  tab.edit();
  tab.back();
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, true);
});

test("reload while parked: the first Back is not dead (the machine skips the duplicate)", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.reload();
  tab.back();
  assert.equal(tab.asking, false);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("reload while parked, then a new edit: Back asks without a second sentinel", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.reload();
  const entries = tab.slots.length;
  tab.edit();
  assert.equal(tab.slots.length, entries);
  tab.back();
  assert.equal(tab.asking, true);
});

test("after a reload: a fragment is placed, and a Forward onto a leftover duplicate rests", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.reload();
  tab.fragment();
  assert.equal(tab.s.here.at, tab.index, "a new fragment entry is the last one");
  const other = dirtyStudio(["/a", "/list"]);
  other.back();
  other.answer(true);
  other.reload(); // forgets the duplicate in front
  other.forward();
  other.forward(); // onto the duplicate: nothing ahead of it to step to
  other.agrees();
  assert.equal(other.s.phase.kind, "idle", "no traversal to nowhere");
  assert.deepEqual(other.walkBack(), ["/list", "/a"]);
});

test("Leave to a page outside the app: the unload does not ask again", () => {
  const tab = new Tab("/studio", 1);
  tab.edit();
  tab.back();
  tab.answer(true);
  assert.equal(tab.unloaded, "quiet");
});

test("a Leave with nowhere to go does not keep the bypass: it goes home", () => {
  let s = startGuard({ at: 3, kind: "next", sentinel: false, url: "/studio" }, 5, true);
  s = { ...s, phase: { kind: "asking", home: 4, leaveTo: 2 } };
  const [moving, leave] = stepGuard(s, { type: "answer", leave: true });
  assert.deepEqual(leave, [
    { type: "setBypass", on: true },
    { type: "go", delta: -1, leaving: true },
  ]);
  const [, stalled] = stepGuard(moving, { type: "stalled" });
  assert.deepEqual(stalled, [{ type: "navigateAway" }]);
});

test("a long-press jump past the editor while dirty asks, and Stay returns", () => {
  const tab = dirtyStudio(["/a", "/b", "/list"]);
  tab.go(-3);
  assert.equal(tab.asking, true);
  assert.equal(tab.shown, "/studio");
  tab.answer(false);
  tab.agrees();
  tab.go(-3);
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/b");
});

test("a link from a leftover sentinel: walking Back skips the duplicate", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.saved();
  tab.link("/other");
  assert.deepEqual(tab.walkBack(), ["/studio", "/list", "/a"]);
});

test("no sentinel (edited on a #fragment entry): Back to another page still asks", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  tab.fragment();
  tab.edit();
  assert.equal(tab.slots[tab.index].sentinel, false, "a stateless entry cannot be duplicated");
  tab.back(); // the studio's own entry: same page
  assert.equal(tab.asking, false);
  tab.back();
  assert.equal(tab.asking, true);
  assert.equal(tab.shown, "/studio");
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, true, "parked on the way back");
});

test("no sentinel, and the save lands while asking: Stay does not re-park", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  tab.fragment();
  tab.edit();
  tab.back();
  tab.back();
  tab.saved();
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, false, "nothing unsaved: no duplicate");
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a clean Back onto another page's #fragment entry: Next ignores it, the next Back renders", () => {
  const tab = new Tab("/list");
  tab.fragment();
  tab.link("/studio");
  tab.back();
  assert.equal(tab.shown, "/studio", "Next's own gap: a stateless entry renders nothing");
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("stamps spread Next's state and keep __NA and the tree", () => {
  const next = { __NA: true, __PRIVATE_NEXTJS_INTERNALS_TREE: { tree: 1 } };
  const stamped = stampState(next, 4, true);
  assert.equal(stamped.__NA, true);
  assert.deepEqual(stamped.__PRIVATE_NEXTJS_INTERNALS_TREE, { tree: 1 });
  assert.deepEqual(readEntry(stamped, "/x"), { at: 4, kind: "next", sentinel: true, url: "/x" });
  assert.equal(readEntry(stampState(stamped, 4, false), "/x").sentinel, false);
  assert.equal(readEntry(null, "/x").kind, "none");
  assert.equal(readEntry({ other: 1 }, "/x").kind, "foreign");
});

test("a replace keeps the position, and the sentinel only while the URL is the same", () => {
  const before = { at: 5, kind: "next" as const, sentinel: true, url: "/studio" };
  const refreshed = { at: null, kind: "next" as const, sentinel: false, url: "/studio" };
  assert.deepEqual(stampAfterWrite("replace", before, refreshed, 9, 5), { at: 5, sentinel: true });
  const elsewhere = { ...refreshed, url: "/other" };
  assert.deepEqual(stampAfterWrite("replace", before, elsewhere, 9, 5), { at: 5, sentinel: false });
  assert.deepEqual(stampAfterWrite("push", before, refreshed, 9, 5), { at: 8, sentinel: false });
});
