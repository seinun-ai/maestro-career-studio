/* Maestro CS Companion — the reasoning step: ask, act, look again (docs/plans/2026-10-14-companion-reasoning-step-design.md).
 *
 * Panel-side and pure, as queue-run.js is: every effect is an op the host passes (`ops`), so node drives it with fakes.
 * The driver calls it through the host's `reason` dep at a park it may think about. It reads the page, asks
 * POST /api/autofill/reason with a VALUE-FREE snapshot, does at most LIMITS.actions actions through the host's
 * existing code, reads again, and repeats for at most LIMITS.rounds rounds inside LIMITS.pageMs.
 *
 * GUARDS (design references only: Nanobrowser's guards.ts and browser-use's ActionLoopDetector/PageFingerprint):
 * - an action's signature is `type:target` (the backend's `signature()`); one that failed twice goes back as
 *   `excluded`, which the backend refuses; a `fill` is judged per field;
 * - a field an action changed nothing on, twice, leaves the snapshot;
 * - a round that leaves the page's key (fingerprint, error count, filled fields) unchanged ends the loop;
 * - ask_user, a missing or late reply, Stop and the page clock end it too (no call starts with under 25 s of the page's 60 s left).
 * NEVER a value: a field is `filled` or not, a written answer is its length. NEVER a press of its own: press_next is
 * the driver's `ctx.press` (the page re-sorts it; Submit is refused there), close_dialog the host's guarded dismiss.
 * The reply is checked again here (ids in THIS snapshot, a button's role, the actions this stuck reason allows).
 *
 * WHAT THE HOST PASSES
 *   ctx  { why, open: [{fid, ...}], recent: ["press_next -> rejected", ...], press(frameId, id, fingerprint, baseline) →
 *          "moved" | "rejected" | "same" | "refused", applicationId?, base?, pageUrl?, today? }
 *   ops  { now(), cancelled(), onLine(text), read(why) → read | null, ask(body, ms) → reply | null,
 *          fill(fids, scope) → report | null, dismiss(frameId, id) → {clicked}, follow(tabId) → bool }
 *   read { frameId, url, summary, fields: [inventory rows], errors: [{label, kind, target}], tabs: [{tabId, host}],
 *          lastFill: {fid: {status, slot}} }   (a moved_away read needs only `tabs`)
 *   scope (to ops.fill, beside the fids; the host adds `only`) { routes, slotHints, reasoner, redo, variants, reasoned }:
 *          fill-loop.js's options, plus `reasoned` (write | choose | answer_from | redo), which the host files under
 *          "Check before you submit".
 * think() returns { moved, advanced, followed, note, ask, tried, rounds, wrote }: `advanced` is the fingerprint of the
 * page a press left, `note` the model's last note, `ask` the ask_user note, `rounds` the trace entries (outcomes:
 * progress | no_effect | refused | rejected | moved | asked), `wrote` the rows to list as answered for you.
 *
 * WHAT THIS FILE PUBLISHES: ns.reasonLoop = { think, snapshotOf, signatureOf, lineFor, LIMITS, ACTIONS }.
 * Every ns.* it uses is read at CALL time: it loads after queue-run.js and before page-kind.js.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const LIMITS = Object.freeze({ rounds: 3, actions: 3, pageMs: 60000, callMs: 30000, fields: 60, options: 20,
    history: 8, buttons: 20, errors: 20, tabs: 5, excluded: 30, note: 200, text: 300, minCallMs: 25000 });
  const ACTIONS = Object.freeze(["fill", "answer_from", "write", "choose", "retry", "redo", "close_dialog",
    "press_next", "follow_tab", "ask_user"]);
  const VARIANTS = Object.freeze({ open_with_keys: { open: "keys" }, search_with_enter: { search: "enter" },
    search_and_wait: { search: "debounce" } });
  // The only actions a page the run could not read as a form allows (inv-rejected-next: only a page the run filled is pressed).
  const ALLOWED_AT = Object.freeze({ unknown_page: ["close_dialog", "follow_tab", "ask_user"],
    moved_away: ["follow_tab", "ask_user"] });
  const WHYS = new Set(["page_errors", "open_questions", "unknown_page", "no_change", "loop", "moved_away"]);
  const SHAPES = new Set(["text", "date", "select", "group", "search", "popup"]);
  const DONE = new Set(["verified", "closest", "assumed", "already", "partial"]);
  const WRITTEN = new Set(["verified", "closest", "assumed", "partial"]);   // the engine wrote it ("already" it did not)
  const REFUSED = new Set(["yours", "blocked", "cannot_operate"]);
  const FAILED = new Set(["no_effect", "refused", "rejected"]);
  const FID = /^[A-Za-z0-9_-]{1,64}$/;
  const SLOT = /^[a-z_]+(\.[a-z0-9_]+)*$/;
  const HISTORY = /^[a-z_]+(:[A-Za-z0-9_-]{1,64})? -> [a-z_]+$/;
  const HOST = /^[a-z0-9.-]{1,253}(:\d{1,5})?$/;
  const WORD = /^[a-z_]+$/;
  const INVISIBLE = /[\p{Cf}\p{Co}\p{Cn}]/gu;
  const cut = (text, n = LIMITS.text) => String(text ?? "").replace(INVISIBLE, "").replace(/\s+/g, " ").trim().slice(0, n);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const attempt = async (fn) => {
    try {
      return await fn();
    } catch {
      return null;   // a failing op is a missing answer, never a throw out of the step
    }
  };

  // ---- the snapshot

  const selectorOf = (ctx) => ({
    ...(ctx.applicationId ? { application_id: String(ctx.applicationId) } : {}),
    ...(ctx.base ? { base: String(ctx.base).slice(0, 200) } : {}),
    ...(ctx.pageUrl ? { page_url: String(ctx.pageUrl).slice(0, 2048) } : {}),
    ...(ctx.today ? { today: String(ctx.today) } : {}),
  });

  const fieldRows = (read, dropped) => {
    const last = read.lastFill ?? {};
    return (read.fields ?? []).filter((f) => f && typeof f.fid === "string" && FID.test(f.fid) && !f.policyBlocked && !dropped.has(f.fid))
      .slice(0, LIMITS.fields).map((f) => {
        const options = (Array.isArray(f.options) ? f.options : []).filter((o) => o && !o.policyBlocked);
        const slot = last[f.fid]?.slot;
        return {
          fid: f.fid, question: cut(f.question), shape: SHAPES.has(f.shape) ? f.shape : "unknown",
          required: f.required === true, filled: f.answered === true, invalid: f.invalid === true, multi: f.multi === true,
          multiline: f.multiline === true, by_run: WRITTEN.has(last[f.fid]?.status), touched: f.touched === true,
          ...(typeof slot === "string" && slot.length <= 120 && SLOT.test(slot) ? { slot } : {}),
          options: options.slice(0, LIMITS.options).map((o, i) => ({ ref: `o${i + 1}`, text: cut(o.text) })),
          option_count: Math.min(options.length, 5000),
        };
      });
  };

  /** Whether the page is one the step must not act on: a wall, a review page, or anything that asks about submitting.
   * Only a form step (or a page not yet known) is worked. A moved_away read carries no page to judge. */
  const walled = (ctx, read) => ctx.why !== "moved_away" && Boolean(read.summary)
    && (read.summary.submitContext === true || !["form_step", "unknown"].includes(ns.pageKind.classify(read.summary).kind));

  /** The page's own Next and dialog-dismiss buttons, by role; refs `b1`.. in page order. The Next is the ONE the
   * classifier names (pressable, in the step); a dialog button is offered only while nothing asks about submitting. */
  const buttonRows = (read) => {
    const verdict = read.summary ? ns.pageKind.classify(read.summary) : { kind: "unknown" };
    const nextId = verdict.kind === "form_step" ? verdict.next : null;
    const asking = read.summary?.submitContext === true;
    const out = [];
    for (const b of read.summary?.buttons ?? []) {
      if (out.length >= LIMITS.buttons) break;
      if (!b || typeof b.id !== "string" || b.visible === false || b.inErrors === true || b.fieldControl === true || b.chrome === true) continue;
      const role = b.id === nextId ? "next"
        : !asking && b.overlay === true && ns.pageKind.isDismiss(b.text, { cookie: b.cookie === true, asks: b.overlayAsks === true }) ? "dialog" : null;
      if (role) out.push({ ref: `b${out.length + 1}`, text: cut(b.text), role, id: b.id });
    }
    return out;
  };

  const errorRows = (read) => (read.errors ?? []).slice(0, LIMITS.errors).map((e) => ({
    text: cut(e?.label), ...(e?.kind === "field" && typeof e.target === "string" && FID.test(e.target) ? { fid: e.target } : {}),
  }));

  const tabRows = (read) => (read.tabs ?? []).filter((t) => t && t.tabId !== undefined && HOST.test(String(t.host ?? "").toLowerCase()))
    .slice(0, LIMITS.tabs).map((t, i) => ({ ref: `t${i + 1}`, host: String(t.host).toLowerCase(), tabId: t.tabId }));

  /** `{ body, refs }`: `body` is exactly a ReasonRequest; `refs` maps `b<i>` to {frameId, id} and `t<i>` to a tabId, and is never sent. */
  function snapshotOf(ctx, read, { round = 1, history = [], excluded = [], dropped = new Set() } = {}) {
    const away = ctx.why === "moved_away";
    const buttons = away ? [] : buttonRows(read);
    const tabs = tabRows(read);
    const refs = {};
    for (const b of buttons) refs[b.ref] = { frameId: read.frameId, id: b.id };
    for (const t of tabs) refs[t.ref] = t.tabId;
    const body = {
      ...selectorOf(ctx), why: ctx.why, round,
      fields: away ? [] : fieldRows(read, dropped),
      buttons: buttons.map(({ ref, text, role }) => ({ ref, text, role })),
      errors: away ? [] : errorRows(read),
      tabs: tabs.map(({ ref, host }) => ({ ref, host })),
      history: history.filter((h) => typeof h === "string" && h.length <= 120 && HISTORY.test(h)).slice(-LIMITS.history),
      excluded: excluded.slice(0, LIMITS.excluded),
    };
    return { body, refs };
  }

  // ---- actions

  /** `type:target`, the backend's `signature()`: the field, button or tab an action works (a fill's first field). */
  const signatureOf = (action) => `${action.type}:${action.fid ?? action.button ?? action.tab ?? action.fids?.[0] ?? "user"}`;
  const targetOf = (action) => signatureOf(action).split(":").slice(1).join(":");

  const fieldIn = (snap, fid) => snap.body.fields.find((f) => f.fid === fid);
  const questionOf = (snap, fid) => fieldIn(snap, fid)?.question ?? "";

  /** The line the card shows while an action runs: fixed words and the page's own, never a value. */
  function lineFor(action, snap) {
    const q = cut(questionOf(snap, action.fid), 80);
    switch (action.type) {
      case "fill": return `Filling ${plural(action.fids?.length ?? 0, "field")}…`;
      case "write": return `Answering ${q}…`;
      case "choose":
      case "answer_from": return `Choosing for ${q}…`;
      case "retry": return `Trying ${q} another way…`;
      case "redo": return `Filling ${q} again…`;
      case "close_dialog": return "Closing a popup…";
      case "press_next": return `Pressing ${cut(snap.body.buttons.find((b) => b.ref === action.button)?.text, 80)}…`;
      case "follow_tab": return "Moving to the application's tab…";
      default: return "";
    }
  }

  const triedOf = (action, snap) => {
    const q = cut(questionOf(snap, action.fid), 80);
    switch (action.type) {
      case "fill": return `filled ${plural(action.fids?.length ?? 0, "field")}`;
      case "write": return `answered ${q}`;
      case "choose":
      case "answer_from": return `chose an option for ${q}`;
      case "retry": return `tried ${q} another way`;
      case "redo": return `filled ${q} again`;
      case "close_dialog": return "closed a popup";
      case "press_next": return `pressed ${cut(snap.body.buttons.find((b) => b.ref === action.button)?.text, 80)}`;
      default: return "";
    }
  };

  const redoPlan = (a) => ({ fids: [a.fid], scope: { redo: [a.fid], reasoned: "redo" } });
  // The fill-loop options each field action becomes. The model named a target; the fill loop supplies every value.
  // answer_from also says `redo`: a box the run filled (a text box answered from the wrong fact) is mapped again, a
  // user's (`touched`) never is.
  const PLANS = {
    fill: (a) => ({ fids: a.fids, scope: {} }),
    answer_from: (a, f) => ({ fids: [a.fid], scope: { slotHints: { [a.fid]: a.slot }, ...(f?.multi ? {} : { redo: [a.fid] }), reasoned: "answer_from" } }),
    write: (a, f) => ({ fids: [a.fid], scope: { routes: { [a.fid]: "free_text" }, reasoner: { [a.fid]: f?.multiline ? "essay" : "short" },
      reasoned: "write" } }),
    choose: (a) => ({ fids: [a.fid], scope: { routes: { [a.fid]: a.basis === "history" ? "reasoned" : "low_stakes" }, reasoned: "choose" } }),
    retry: (a) => (a.technique === "clear_and_set" ? redoPlan(a)
      : VARIANTS[a.technique] ? { fids: [a.fid], scope: { variants: { [a.fid]: VARIANTS[a.technique] } } } : null),
    redo: redoPlan,
  };

  /** What a fill report says about `fids`: each one's row, and the action's outcome. */
  function judged(report, fids) {
    const rows = fids.map((fid) => (report?.fields ?? []).find((r) => r?.fid === fid) ?? null);
    const outcomes = rows.map((r) => (!r ? "no_effect" : DONE.has(r.status) ? "progress" : REFUSED.has(r.status) ? "refused" : "no_effect"));
    const outcome = !report ? "rejected" : outcomes.includes("progress") ? "progress" : outcomes.every((o) => o === "refused") ? "refused" : "no_effect";
    return { rows, outcomes, outcome };
  }

  async function runField(action, snap, ops, out) {
    const plan = PLANS[action.type]?.(action, fieldIn(snap, action.fid));
    const known = new Set(snap.body.fields.map((f) => f.fid));
    if (!plan || !plan.fids.length || !plan.fids.every((fid) => known.has(fid))) return { outcome: "rejected" };
    // Reworking a field is for the run's own work: never the user's (touched), nor one the run did not fill, nor a set of values.
    const field = fieldIn(snap, action.fid);
    const reworks = action.type === "redo" || action.type === "answer_from" || (action.type === "retry" && action.technique === "clear_and_set");
    if (reworks && field && (field.touched || (field.filled && (!field.by_run || field.multi)))) return { outcome: "rejected" };
    const report = await attempt(() => ops.fill(plan.fids, plan.scope));
    const { rows, outcomes, outcome } = judged(report, plan.fids);
    const extra = {};
    rows.forEach((row, i) => {
      if (!row || !WRITTEN.has(row.status) || !plan.scope.reasoned) return;
      if (!out.wrote.some((w) => w.fid === row.fid)) {
        out.wrote.push({ fid: row.fid, question: cut(row.question || questionOf(snap, row.fid), 80),
          note: ns.fillLoop?.REASONED_NOTES?.[plan.scope.reasoned] ?? null });
      }
      if (action.type === "write" && i === 0) extra.written = String(row.answer ?? "").length;
    });
    return { outcome, ...extra, perFid: action.type === "fill" ? plan.fids.map((fid, i) => [fid, outcomes[i]]) : null };
  }

  async function runButton(action, snap, ctx, ops, state) {
    const ref = snap.refs[action.button];
    const asked = snap.body.buttons.find((b) => b.ref === action.button);
    const role = action.type === "press_next" ? "next" : "dialog";
    if (!ref || asked?.role !== role) return { outcome: "rejected" };
    let target = { frameId: ref.frameId, id: ref.id, read: state.cur };
    if (state.dirty) {
      // An earlier action this round changed the page: its button is found again in a fresh read (ids are minted per
      // read), and a press waits for change from THAT page's fingerprint. A Next is the one the classifier names, with
      // the words it had; a dialog button must be the only one with its role and words. A page that now asks about
      // submitting, or is any wall, ends the step.
      const fresh = await attempt(() => ops.read(ctx.why));
      if (!fresh) return { outcome: "refused" };
      state.cur = fresh;
      if (walled(ctx, fresh)) {
        state.walled = true;
        return { outcome: "refused" };
      }
      const same = buttonRows(fresh).filter((b) => b.role === role && b.text === asked.text);
      if (same.length !== 1) return { outcome: "refused" };
      target = { frameId: fresh.frameId, id: same[0].id, read: fresh };
    }
    if (action.type === "close_dialog") {
      const got = await attempt(() => ops.dismiss(target.frameId, target.id));
      return { outcome: got?.clicked === true ? "progress" : "refused" };
    }
    const fp = ns.queueRun.fingerprint(target.read.url, target.read.summary);
    const got = await attempt(() => ctx.press(target.frameId, target.id, fp, target.read.summary?.errorKeys ?? []));
    const outcome = got === "moved" ? "moved" : got === "rejected" ? "rejected" : got === "same" ? "no_effect" : "refused";
    return { outcome, ...(outcome === "moved" ? { advanced: fp } : {}) };
  }

  async function perform(action, snap, ctx, ops, state, out) {
    if (ALLOWED_AT[ctx.why] && !ALLOWED_AT[ctx.why].includes(action.type)) return { outcome: "rejected" };
    if (action.type === "press_next" || action.type === "close_dialog") return await runButton(action, snap, ctx, ops, state);
    if (action.type === "follow_tab") {
      const tabId = snap.refs[action.tab];
      if (tabId === undefined) return { outcome: "rejected" };
      return { outcome: (await attempt(() => ops.follow(tabId))) === true ? "moved" : "refused" };
    }
    return await runField(action, snap, ops, out);
  }

  // What failed is counted by what the action worked, so it survives the button list renumbering: a field by its
  // signature, a button by its role and words, a tab by its host. `excludedFor` turns the counts back into the
  // signatures THIS snapshot's refs carry.
  const failKey = (action, snap) => {
    if (action.button) return `${action.type}|${snap.body.buttons.find((b) => b.ref === action.button)?.text ?? ""}`;
    if (action.tab) return `${action.type}|${snap.body.tabs.find((t) => t.ref === action.tab)?.host ?? ""}`;
    return signatureOf(action);
  };
  function excludedFor(ctx, read, fails) {
    const twice = (key) => (fails.get(key) ?? 0) >= 2;
    const out = [...fails.keys()].filter((key) => !key.includes("|") && twice(key));
    if (ctx.why !== "moved_away") {
      for (const b of buttonRows(read)) if (twice(`${b.role === "next" ? "press_next" : "close_dialog"}|${b.text}`)) out.push(`${b.role === "next" ? "press_next" : "close_dialog"}:${b.ref}`);
    }
    for (const t of tabRows(read)) if (twice(`follow_tab|${t.host}`)) out.push(`follow_tab:${t.ref}`);
    return out;
  }

  // ---- looking again

  const filledFids = (read) => (read.fields ?? []).filter((f) => f.answered === true).map((f) => f.fid).sort();
  const pageKeyOf = (read) => [ns.queueRun.fingerprint(read.url, read.summary), (read.errors ?? []).length, filledFids(read).join(",")].join("\n");

  /** Whether the stuck reason is gone (design §2): the run can press Next again. */
  function resolved(ctx, before, after) {
    const filled = new Set(filledFids(after));
    const there = new Set((after.fields ?? []).map((f) => f.fid));
    switch (ctx.why) {
      case "page_errors": return (after.errors ?? []).length === 0;
      case "open_questions": return (ctx.open ?? []).length > 0 && ctx.open.every((o) => o.fid && (filled.has(o.fid) || !there.has(o.fid)));
      case "no_change":
      case "loop": return pageKeyOf(after) !== pageKeyOf(before);
      case "unknown_page": return ns.pageKind.classify(after.summary).kind !== "unknown";
      default: return false;
    }
  }

  const saneReply = (reply) => (reply && typeof reply === "object" && Array.isArray(reply.actions) && reply.actions.length
    && reply.actions.every((a) => a && ACTIONS.includes(a.type)) ? reply : null);

  /** The step. Returns when the page moved, the model asked the user, or a limit or guard ended it. */
  async function think(ctx, ops) {
    const out = { moved: false, advanced: null, followed: false, note: "", ask: null, tried: [], rounds: [], wrote: [] };
    if (!WHYS.has(ctx?.why)) return out;
    const began = ops.now();
    const over = () => ops.cancelled?.() === true || ops.now() - began >= LIMITS.pageMs;
    const say = (text) => {
      if (!text) return;
      try {
        ops.onLine?.(text);
      } catch {
        // A live line never stops the step.
      }
    };
    const first = await attempt(() => ops.read(ctx.why));
    if (!first) return out;
    if (walled(ctx, first)) {
      out.rounds.push({ round: 1, why: ctx.why, model: null, ms: 0, note: "", actions: [], rejected: [], stopped: "wall" });
      return out;
    }
    const state = { cur: first, dirty: false, walled: false };
    const history = (ctx.recent ?? []).filter((h) => typeof h === "string" && HISTORY.test(h)).slice(-LIMITS.history);
    const fails = new Map();     // signature -> times it failed
    const idle = new Map();      // fid -> rounds an action left it unfilled
    for (let round = 1; round <= LIMITS.rounds && !over(); round += 1) {
      const entry = { round, why: ctx.why, model: null, ms: 0, note: "", actions: [], rejected: [], stopped: null };
      out.rounds.push(entry);
      const snap = snapshotOf(ctx, state.cur, { round, history, excluded: excludedFor(ctx, state.cur, fails),
        dropped: new Set([...idle].filter(([, n]) => n >= 2).map(([fid]) => fid)) });
      // The backend gives the model 25 s: a call with less page clock left than that would be cut off, and paid for.
      if (began + LIMITS.pageMs - ops.now() < LIMITS.minCallMs) {
        entry.stopped = "clock";
        break;
      }
      say("Thinking about this page…");
      const asked = ops.now();
      const reply = saneReply(await attempt(() => ops.ask(snap.body, Math.max(0, Math.min(LIMITS.callMs, began + LIMITS.pageMs - ops.now())))));
      entry.ms = Number.isInteger(reply?.ms) ? reply.ms : Math.max(0, ops.now() - asked);
      if (!reply) {
        entry.stopped = "no_reply";
        break;
      }
      entry.model = cut(reply.model, 120) || null;
      entry.note = cut(reply.note, LIMITS.note);
      entry.rejected = (Array.isArray(reply.rejected) ? reply.rejected : []).filter((c) => typeof c === "string" && WORD.test(c)).slice(0, 10);
      out.note = entry.note;
      if (ops.cancelled?.() === true) {
        entry.stopped = "stopped";
        break;
      }
      say(entry.note ? `Thinking: ${entry.note}` : "");
      const actions = reply.actions.slice(0, LIMITS.actions);
      const asking = actions.find((a) => a.type === "ask_user");
      if (asking) {
        entry.actions.push({ type: "ask_user", target: targetOf(asking), outcome: "asked" });
        out.ask = cut(asking.note, LIMITS.note) || null;
        entry.stopped = "asked";
        break;
      }
      state.dirty = false;
      const before = state.cur;
      const targeted = new Set();
      const progressed = new Set();
      let ended = false;
      for (const [i, action] of actions.entries()) {
        if (ops.cancelled?.() === true) {
          entry.stopped = "stopped";
          ended = true;
          break;
        }
        if (ops.now() - began >= LIMITS.pageMs) {
          entry.stopped = "clock";
          ended = true;
          break;
        }
        say(lineFor(action, snap));
        const last = i === actions.length - 1;
        const result = action.type === "press_next" && !last ? { outcome: "rejected" } : await perform(action, snap, ctx, ops, state, out);
        const target = targetOf(action);
        entry.actions.push({ type: action.type, target, outcome: result.outcome, ...(result.written !== undefined ? { written: result.written } : {}) });
        history.push(`${action.type}:${target} -> ${result.outcome}`);
        history.splice(0, Math.max(0, history.length - LIMITS.history));
        // A fill is judged per field (the backend checks its signatures that way); anything else by its own.
        for (const [key, outcome] of result.perFid ? result.perFid.map(([fid, o]) => [`fill:${fid}`, o]) : [[failKey(action, snap), result.outcome]]) {
          if (FAILED.has(outcome)) fails.set(key, (fails.get(key) ?? 0) + 1);
        }
        if (state.walled) {
          entry.stopped = "wall";
          ended = true;
          break;
        }
        if (result.outcome !== "rejected" && triedOf(action, snap)) out.tried.push(triedOf(action, snap));
        for (const fid of action.fids ?? (action.fid ? [action.fid] : [])) {
          targeted.add(fid);
          if (result.perFid ? result.perFid.some(([f, o]) => f === fid && o === "progress") : result.outcome === "progress") progressed.add(fid);
        }
        if (result.outcome === "moved") {
          ended = true;
          entry.stopped = action.type === "follow_tab" ? "followed" : "moved";
          out.moved = action.type === "press_next";
          out.followed = action.type === "follow_tab";
          out.advanced = result.advanced ?? null;
          break;
        }
        if (!["close_dialog", "press_next", "follow_tab"].includes(action.type)) state.dirty = true;
      }
      if (ended) break;
      const after = await attempt(() => ops.read(ctx.why));
      if (!after) {
        entry.stopped = "page_gone";
        break;
      }
      const filledBefore = new Set(filledFids(before));
      const filledAfter = new Set(filledFids(after));
      for (const fid of targeted) {
        const changed = filledBefore.has(fid) !== filledAfter.has(fid);
        if (changed) idle.delete(fid);
        else if (!progressed.has(fid)) idle.set(fid, (idle.get(fid) ?? 0) + 1);
      }
      state.cur = after;
      if (walled(ctx, after)) {
        entry.stopped = "wall";
        break;
      }
      if (resolved(ctx, first, after)) {
        entry.stopped = "resolved";
        out.moved = true;
        break;
      }
      if (pageKeyOf(after) === pageKeyOf(before)) {
        entry.stopped = "same_page";
        break;
      }
      if (round === LIMITS.rounds) entry.stopped = "rounds";
    }
    out.tried = [...new Set(out.tried)].slice(0, 6);
    return out;
  }

  ns.reasonLoop = { think, snapshotOf, signatureOf, lineFor, LIMITS, ACTIONS };
})();
