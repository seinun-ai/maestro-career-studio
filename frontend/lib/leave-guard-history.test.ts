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
 * machine sees. `shown` is the page Next rendered; `url` is the address bar. The
 * tab keeps at most 50 entries and drops the oldest on a push, as Chrome does.
 * Expectations come from the tab (slots, index, shown), never from the stamps.
 * Traversals are asynchronous, as in a browser: our `history.go` calls queue and
 * run after the action, or when a test calls `settle()` in `manual` mode.
 */
type Slot = { url: string; kind: EntryKind | "other-site"; sentinel: boolean; at: number | null };

const CAP = 50;

class Tab {
  slots: Slot[];
  index: number;
  s: GuardState;
  shown: string;
  asking = false;
  bypass = false;
  unloaded: "quiet" | "warned" | null = null;
  away = false;
  blocked = false;
  manual = false;
  /** Next's HistoryUpdater replaceState lands between each traversal and its popstate. */
  racingRender = false;
  queue: number[] = [];
  /** Every render Next did (a traverse it was not stopped from, a navigation). */
  renders: string[] = [];

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
      if (this.slots.length > CAP) {
        this.slots.shift();
        this.index -= 1;
      }
    } else this.slots[this.index] = { url, kind: "next", sentinel, at: before.at };
    const stamp = stampAfterWrite(how, before, this.entry(), this.slots.length, this.s.here.at);
    Object.assign(this.slots[this.index], stamp);
    this.run(this.feed({ type: "wrote", how, entry: this.entry(), length: this.slots.length }));
  }

  /** A clean in-app link (GuardedLink passes straight through). */
  link(url: string) {
    assert.equal(this.blocked, false);
    this.renders.push(url);
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
    this.act(() => this.run(this.feed({ type: "blocked", blocked })));
  }

  /** The skip link (#main-content): a fragment navigation fires popstate with no state. */
  fragment() {
    this.slots.splice(this.index + 1);
    this.slots.push({ url: this.url, kind: "none", sentinel: false, at: null });
    this.index += 1;
    if (this.slots.length > CAP) {
      this.slots.shift();
      this.index -= 1;
    }
    this.act(() => this.pop());
  }

  back() {
    return this.press(-1);
  }

  forward() {
    return this.press(1);
  }

  /** A user's Back/Forward (or a long-press jump). False when there is no entry there. */
  press(delta: number): boolean {
    let moved = false;
    this.act(() => {
      moved = this.go(delta);
    });
    return moved;
  }

  /** A browser traversal. */
  go(delta: number): boolean {
    const target = this.index + delta;
    if (target < 0 || target >= this.slots.length) return false;
    if (this.slots[target].kind === "other-site") {
      if (!this.away && this.blocked && !this.bypass) {
        this.unloaded = "warned"; // the browser asks; the test dismisses it
        return false;
      }
      if (!this.away) this.unloaded = "quiet";
      this.away = true;
      this.index = target;
      return true;
    }
    this.index = target;
    if (this.racingRender && !this.away) {
      // Next commits a render after the move but before the popstate: its
      // HistoryUpdater rewrites the entry the browser is now on.
      const slot = this.slots[target];
      if (slot.kind === "next") this.write("replace", slot.url, slot.sentinel);
    }
    if (this.away) {
      // Back into our document from the back/forward cache: Next's pageshow
      // handler renders the current entry, and the listeners report it.
      this.away = false;
      this.renders.push(this.url);
      this.render(this.url);
      this.run(this.feed({ type: "restored", entry: this.entry(), length: this.slots.length }));
      return true;
    }
    this.pop();
    return true;
  }

  pop() {
    const commands = this.feed({ type: "pop", entry: this.entry(), length: this.slots.length });
    const stopped = commands.some((c) => c.type === "stop");
    // Next's bubble listener: ignores a stateless entry, renders an app-router one.
    if (!stopped && this.slots[this.index].kind === "next") {
      this.renders.push(this.url);
      this.render(this.url);
    }
    this.run(commands);
  }

  answer(leave: boolean) {
    assert.equal(this.asking, true, "the question is open");
    this.asking = false;
    this.act(() => this.run(this.feed({ type: "answer", leave })));
  }

  stalled() {
    this.act(() => this.run(this.feed({ type: "stalled" })));
  }

  reload() {
    this.blocked = false;
    this.asking = false;
    this.shown = this.url;
    this.s = startGuard(this.entry(), this.slots.length, false);
  }

  /** Next rendered a page: a different one unmounts the editor, which unregisters. */
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
      else if (c.type === "go") this.queue.push(c.delta);
      else if (c.type === "pushSentinel") this.write("push", this.url, true);
      else if (c.type === "replay") {
        this.renders.push(this.url);
        this.render(this.url);
      } else if (c.type === "renderHere") {
        this.renders.push(this.url);
        this.write("replace", this.url, false);
        this.render(this.url);
      } else if (c.type === "navigateAway") {
        this.renders.push("/applications");
        this.render("/applications");
        this.write("push", "/applications", false);
      } else if (c.type === "restorePage") this.write("push", this.shown, false);
    }
  }

  act(fn: () => void) {
    fn();
    if (!this.manual) this.settle();
  }

  /** Let queued traversals land. */
  settle() {
    for (let delta = this.queue.shift(); delta !== undefined; delta = this.queue.shift()) {
      this.go(delta);
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
  tab.back(); // back onto the duplicate: the same page
  assert.equal(tab.asking, false);
  tab.agrees();
  tab.back(); // off the leftover duplicate: one press to the page before
  tab.agrees();
  assert.equal(tab.shown, "/list");
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

/** A tab already at Chrome's 50-entry cap, then /base-resumes and a dirty studio. */
function dirtyStudioAtCap(): Tab {
  const tab = new Tab("/p0");
  for (let i = 1; i < 55; i++) tab.link(`/p${i}`);
  tab.link("/list");
  tab.link("/studio");
  tab.edit();
  assert.equal(tab.slots.length, CAP);
  assert.equal(tab.slots[tab.index].sentinel, true);
  return tab;
}

test("at the 50-entry cap: the first Back asks, Stay keeps URL and page together", () => {
  const tab = dirtyStudioAtCap();
  tab.back();
  assert.equal(tab.asking, true, "the first Back asks");
  assert.equal(tab.url, "/studio");
  tab.answer(false);
  tab.agrees();
  tab.back();
  assert.equal(tab.asking, true, "and the next one too");
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
  assert.deepEqual(tab.walkBack().slice(0, 3), ["/p54", "/p53", "/p52"]);
});

test("at the cap: extra Backs while asking are undone exactly; after a save Back takes one press", () => {
  const tab = dirtyStudioAtCap();
  tab.back();
  tab.back();
  tab.back();
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.shown, "/studio");
  tab.saved();
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("at the cap: a skip-link fragment while parked asks nothing and stays guarded", () => {
  const tab = dirtyStudioAtCap();
  tab.fragment();
  assert.equal(tab.slots.length, CAP);
  assert.equal(tab.asking, false);
  tab.back(); // onto the duplicate: same page
  assert.equal(tab.asking, false);
  tab.agrees();
  tab.back();
  assert.equal(tab.asking, true);
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

for (const atCap of [false, true]) {
  test(`${atCap ? "at the cap: " : ""}a Back onto another page's #fragment entry while asking: Stay returns exactly`, () => {
    const tab = new Tab("/a");
    for (let i = 0; atCap && i < 55; i++) tab.link(`/p${i}`);
    tab.link("/list");
    tab.fragment(); // the skip link on /list
    tab.link("/studio");
    tab.edit();
    const entries = tab.slots.length;
    tab.back(); // asks
    tab.back(); // onto /list#main-content, a stateless entry
    tab.answer(false);
    tab.agrees();
    assert.equal(tab.slots.length, entries, "history kept, nothing pushed over it");
    assert.equal(tab.slots[tab.index].sentinel, true);
    tab.back();
    tab.answer(true);
    tab.agrees();
    assert.equal(tab.shown, "/list");
  });
}

test("resting on the editor's own entry under a leftover duplicate: Forward moves on in one press", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.saved();
  tab.link("/other");
  tab.press(-2); // a long-press jump straight onto the studio's own entry
  tab.agrees();
  assert.equal(tab.shown, "/studio");
  tab.forward();
  tab.agrees();
  assert.equal(tab.shown, "/other", "the leftover duplicate is stepped over");
});

test("no sentinel: Forward back onto the editor while asking, Stay parks there", () => {
  const tab = new Tab("/list");
  tab.link("/studio");
  tab.fragment();
  tab.edit();
  tab.back(); // the studio's own entry
  tab.back(); // another page: asks
  tab.forward(); // back onto the studio's own entry while the question is open
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.slots[tab.index].sentinel, true, "parked");
  tab.back();
  assert.equal(tab.asking, true);
  assert.equal(tab.url, "/studio", "the URL stays on the editor during the question");
});

test("Stay never hands the page to Next: no render while the answer puts the URL back", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.back();
  tab.back();
  const before = tab.renders.length;
  tab.answer(false);
  tab.agrees();
  assert.equal(tab.renders.length, before, "Next rendered nothing");
});

test("a Back pressed before Stay's return has landed asks again and keeps the edit", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.manual = true;
  tab.back();
  tab.back();
  tab.settle();
  tab.answer(false); // queues the return to the duplicate
  tab.back(); // the user presses Back first
  tab.settle();
  assert.equal(tab.asking, true, "asked again");
  assert.equal(tab.shown, "/studio");
  assert.equal(tab.blocked, true, "the edit is still there");
  tab.answer(false);
  tab.settle();
  tab.agrees();
});

test("a fresh tab with a leftover duplicate: Back goes to the app's home, not a dead press", () => {
  const tab = new Tab("/studio");
  tab.edit();
  tab.saved();
  tab.back();
  tab.agrees();
  assert.equal(tab.shown, "/applications");
});

test("back from another site into a cached page: the machine follows the entry Next restores", () => {
  const tab = new Tab("/list", 1);
  tab.link("/studio");
  tab.press(-2); // to the other site: the page goes into the back/forward cache
  assert.equal(tab.away, true);
  tab.forward(); // restored on /list
  tab.agrees();
  assert.equal(tab.shown, "/list");
  tab.forward();
  tab.agrees();
  assert.equal(tab.shown, "/studio");
});

test("a Next render between a traversal and its popstate does not hide the Back", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.racingRender = true;
  tab.back();
  assert.equal(tab.asking, true, "the Back still asks");
  tab.back();
  tab.answer(false);
  tab.agrees();
  tab.back();
  tab.answer(true);
  tab.agrees();
  assert.equal(tab.shown, "/list");
});

test("a Leave that stalls goes home through the router", () => {
  const tab = dirtyStudio(["/a", "/list"]);
  tab.manual = true;
  tab.back();
  tab.settle();
  tab.answer(true);
  tab.queue.length = 0; // the traversal went nowhere
  tab.stalled();
  tab.agrees();
  assert.equal(tab.shown, "/applications");
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

test("a push is the entry it left + 1; a replace keeps the number, and the sentinel only while the URL is the same", () => {
  const before = { at: 5, kind: "next" as const, sentinel: true, url: "/studio" };
  const refreshed = { at: null, kind: "next" as const, sentinel: false, url: "/studio" };
  assert.deepEqual(stampAfterWrite("replace", before, refreshed, 9, 5), { at: 5, sentinel: true });
  const elsewhere = { ...refreshed, url: "/other" };
  assert.deepEqual(stampAfterWrite("replace", before, elsewhere, 9, 5), { at: 5, sentinel: false });
  assert.deepEqual(stampAfterWrite("push", before, refreshed, 9, 5), { at: 6, sentinel: false });
});
