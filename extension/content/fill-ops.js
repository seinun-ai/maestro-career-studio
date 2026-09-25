/* Maestro CS Companion — the page half of the fill loop.
 *
 * The panel sends every message to every frame; a frame acts only on fids it
 * owns. Each operation runs under a budget with its own cancellation token
 * (fillBase.withinBudget) and never throws: a Stop, a timeout, a field that
 * cannot take focus or a box that refuses typing all come back as outcomes.
 *
 * Re-checked at EXECUTION, not only when the decision was made: the
 * fingerprint is mandatory and must match both the one recorded at inventory
 * and the one the page reads NOW; a field the user edited, or that policy
 * blocks, is never written. A decision made on an older view never acts.
 *
 * `ns.fillBusyEl` names the field the engine is working on — for its typing,
 * its clicks, and the blur that follows — so only the engine's own events on
 * THAT field are not taken for the user's.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/fill-ops.js")) return;
  loaded.add("content/fill-ops.js");
  // Mutable so a test can force a timeout; the loop never changes them.
  const budgets = { explore: 4000, apply: 6000, setItem: 4000, setMax: 20000, step: 2000 };
  const inv = () => ns.fillInventory;
  const core = () => ns.fillCore;
  let runId = null;
  let consentForms = false; // the run's standing consent, from its inventory
  // What each verified operation committed, so the sweep can catch a page
  // that quietly reverts a value after it was verified.
  const verified = new Map(); // fid -> { expected, format }
  const mine = (fid) => typeof fid === "string" && fid.startsWith(`${inv().frame}-`);
  // Whether Stop is latched: check() without a token throws only then.
  const halted = () => {
    try {
      ns.fillBase.check();
      return false;
    } catch {
      return true;
    }
  };

  // Runs one operation on one field. `aborted` means it did not finish on its
  // own (Stop, timeout, a throw), so a popup it opened may still be up.
  const run = async (fn, ms, el) => {
    ns.fillBusyEl = el;
    try {
      return { got: await ns.fillBase.withinBudget(fn, ms), aborted: false };
    } catch (err) {
      if (err?.name === "Cancelled") return { got: { outcome: halted() ? "cancelled" : "timeout" }, aborted: true };
      if (!el.isConnected) return { got: { outcome: "stale" }, aborted: true };
      if (err?.name !== "Unfocusable") console.warn("[maestro-cs] fill operation failed:", err?.name);
      return { got: { outcome: "unexpected", reason: err?.name === "Unfocusable" ? "unfocusable" : "page_error" }, aborted: true };
    } finally {
      ns.fillBusyEl = null;
    }
  };
  // Closing a popup the engine opened is the one thing a stopped or timed-out
  // operation may still do; it never types (no text value is cleared).
  const cleanup = async (el) => {
    ns.fillBusyEl = el;
    try {
      await core().tidy(el, null, { cleanup: true });
    } catch {
      // Best effort: cleanup never turns an outcome into a throw.
    } finally {
      ns.fillBusyEl = null;
    }
  };
  const target = (fid, fp) => {
    const el = inv().resolve(fid);
    if (!el || !fp || inv().fpOf(fid) !== fp || inv().liveFp(fid) !== fp) return { refused: "stale" };
    if (inv().isTouched(fid)) return { refused: "yours" };
    if (inv().isBlocked(fid)) return { refused: "blocked" };
    const shape = inv().shapeOf(fid);
    if (!shape || shape.kind === "unknown") return { refused: "unsupported" };
    return { el, shape };
  };
  // A popup deliberately left open (a category's children) is closed before
  // any other field is touched; an adaptive move keeps its own field's open.
  const closeLeftOpen = async (exceptFid) => {
    const keep = exceptFid ? inv().resolve(exceptFid) : null;
    for (const el of [...core().leftOpen.keys()]) if (el !== keep) await cleanup(el);
  };

  // ONE operation at a time per frame: each shares fillBusyEl, the focus and
  // the page, so a second message waits for the first (a Stop does not — it
  // latches at once and every queued operation then starts cancelled).
  let queue = Promise.resolve();
  const serial = (fn) => (...args) => {
    const next = queue.then(() => fn(...args));
    queue = next.catch(() => {});
    return next;
  };

  const explore = async (requests) => {
    const out = {};
    for (const r of requests ?? []) {
      if (!mine(r?.fid)) continue;
      await closeLeftOpen(null);
      const { el, shape, refused } = target(r.fid, r.fp);
      if (refused) {
        out[r.fid] = { options: [], complete: false, searchable: false, error: refused };
        continue;
      }
      const { got, aborted } = await run((t) => core().explore(el, shape, { term: r.term ?? undefined, consentForms }, t),
        budgets.explore, el);
      if (aborted) await cleanup(el);
      out[r.fid] = got.options ? got : { options: [], complete: false, searchable: false, error: got.reason ?? got.outcome };
    }
    return out;
  };

  const operate = (a, el, shape, t) => {
    if (a.op === "write") return core().write(el, shape, a.value, t, { format: a.format });
    if (a.op === "choose") return core().choose(el, shape, { text: a.text, term: a.term ?? undefined, consentForms }, t);
    if (a.op === "set") return core().set(el, shape, { texts: a.texts ?? [], terms: a.terms ?? [], consentForms }, t);
    if (a.op === "recommit") return core().recommit(el, shape, t);
    if (a.op === "close") return core().tidy(el, t).then(() => ({ outcome: "closed" }));
    // An adaptive move carries the state version it was chosen from.
    // `as: "progress"`: /step judged the click a step toward the value (a
    // category), not the answer — it must never be verified as one.
    if (a.op === "move") {
      return core().move(el, shape, { mid: a.mid, version: a.version, as: a.as, consentForms }, t);
    }
    return Promise.resolve({ outcome: "unexpected", reason: "unknown_op" });
  };

  const applyNow = async (actions) => {
    const out = [];
    for (const a of actions ?? []) {
      if (!mine(a?.fid)) continue;
      await closeLeftOpen(a.op === "move" ? a.fid : null);
      const { el, shape, refused } = target(a.fid, a.fp);
      if (refused) {
        out.push({ fid: a.fid, outcome: refused, committed: null });
        continue;
      }
      const ms = a.op === "set"
        ? Math.min(budgets.setMax, budgets.setItem * Math.max(1, (a.texts ?? []).length)) : budgets.apply;
      const { got, aborted } = await run((t) => operate(a, el, shape, t), ms, el);
      if (aborted) await cleanup(el);
      // Remember what was actually COMMITTED: the clicked option's text for a
      // choose (not the raw decision), the texts for a set, the value for a write.
      const { text, ...row } = got;
      if (row.outcome === "verified") {
        verified.set(a.fid, { expected: text ?? a.texts ?? a.value, format: a.format });
      } else {
        verified.delete(a.fid);
      }
      out.push({ fid: a.fid, ...row, committed: el.isConnected ? shape.read(el) : null });
    }
    return out;
  };

  // The adaptive step's view of one field: its state now and the moves code
  // allows, under a version a move must name. A field's own held popup stays
  // open; any other field's is closed first.
  const stepState = async (r) => {
    if (!mine(r?.fid)) return null;
    await closeLeftOpen(r.fid);
    const { el, shape, refused } = target(r.fid, r.fp);
    if (refused) return { error: refused, version: null, candidates: [] };
    const { got } = await run((t) => core().stepState(el, shape, { value: r.value, consentForms }, t), budgets.step, el);
    return got.candidates ? got : { error: got.reason ?? got.outcome, version: null, candidates: [] };
  };

  const sweep = async () => {
    const out = [];
    const reported = new Set();
    // Delayed reversion: a value verified earlier that no longer holds. A
    // field the user has since edited is theirs, not reverted.
    for (const [fid, { expected, format }] of [...verified]) {
      const el = inv().resolve(fid);
      const shape = inv().shapeOf(fid);
      if (!el || !shape || inv().isTouched(fid)) {
        verified.delete(fid);
        continue;
      }
      if (core().verify(el, shape, expected, { format }) !== "verified") {
        verified.delete(fid);
        reported.add(fid);
        out.push({ fid, outcome: "reverted" });
      }
    }
    // Text holding a value and showing an error: commit its own value again.
    for (const f of inv().list({ consentForms }).fields) {
      if (halted()) break;
      if (reported.has(f.fid) || f.kind !== "text" || !f.committed || !f.invalid || f.touched || f.policyBlocked) continue;
      const [row] = await applyNow([{ fid: f.fid, fp: f.fp, op: "recommit" }]);
      if (row) out.push({ fid: f.fid, outcome: row.outcome });
    }
    return out;
  };

  const focus = (fid) => {
    if (!mine(fid)) return false;
    const el = inv().resolve(fid);
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    el.focus({ preventScroll: true });
    return true;
  };

  ns.fillOps = {
    // A new runId starts a new run: the Stop latch is released and the
    // verified-values memory starts empty. consentForms is per call and
    // defaults to OFF.
    // Queued like every other operation: a Stop latched under an operation
    // already waiting is never released before that operation starts.
    inventory: serial(async (opts = {}) => {
      if (opts.runId && opts.runId !== runId) {
        runId = opts.runId;
        ns.fillBase.resume();
        verified.clear();
      }
      consentForms = opts.consentForms === true;
      return inv().list({ consentForms });
    }),
    explore: serial(explore), apply: serial(applyNow), stepState: serial(stepState), sweep: serial(sweep), focus, budgets,
    // Stop: latch at once, then close any popup a commit left open on purpose.
    cancel: () => {
      ns.fillBase.cancelAll();
      return closeLeftOpen(null);
    },
  };
})();
