// A stubbed `chrome.*` for backend/scripts/panel_preview.py: the real panel
// runs in a normal browser page against these canned replies. The server puts
// the fixture in `window.__PANEL_PREVIEW_SPEC` first. Spec keys follow the
// node harness (tests/extension_panel_harness.py `_PANEL_FAKES_JS`): tabs,
// stored, sessionStored, replies, api, page, frames. The per-tab job memory is
// sessionStored["widget.sessions"] (tab id to entry). A string "$now" anywhere
// in the spec becomes the current time in ms.
// Preview-only keys: reopen (a rail row to open once), autoPress (press the
// footer primary once), fillReport (what a finished fill loop returns).
(() => {
  const NOW = Date.now();
  const fresh = (value) => {
    if (value === "$now") return NOW;
    if (Array.isArray(value)) return value.map(fresh);
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fresh(v)]));
    }
    return value;
  };
  const spec = fresh(window.__PANEL_PREVIEW_SPEC);
  const sent = [];
  window.__panelPreview = { spec, sent };

  // A needle may name a LIST of replies, consumed in order with the last one
  // repeating (a read that answers differently the second time).
  const next = (reply) => {
    if (!Array.isArray(reply)) return reply;
    return reply.length > 1 ? reply.shift() : reply[0];
  };
  const unreachable = { ok: false, error: "the backend is unreachable" };
  const apiReply = (msg) => {
    const wire = `${msg.init?.method ?? "GET"} ${msg.path}`;
    for (const [needle, reply] of Object.entries(spec.api ?? {})) {
      if (wire.includes(needle)) return next(reply);
    }
    return unreachable;
  };
  const broadcastReply = (message) => {
    let canned = (spec.frames ?? {})[message.type];
    if (canned === undefined) return { ok: false, error: "no frame answered" };
    if (canned && canned.__seq) canned = next(canned.__seq);
    return { ok: true, data: canned };
  };

  window.chrome = {
    tabs: {
      query: async () => spec.tabs ?? [],
      get: async (tabId) => ({ id: tabId, url: (spec.tabUrls ?? {})[tabId] ?? "" }),
      onActivated: { addListener() {} },
      onUpdated: { addListener() {} },
      onRemoved: { addListener() {} },
      onCreated: { addListener() {} },
    },
    webNavigation: { onCompleted: { addListener() {} } },
    storage: {
      local: {
        get: async (query) => ({ ...query, ...(spec.stored ?? {}) }),
        set: async () => {},
        remove: async () => {},
      },
      sync: { set: async () => {} },
      session: {
        get: async (key) => {
          const stored = spec.sessionStored ?? {};
          return Object.hasOwn(stored, key) ? { [key]: stored[key] } : {};
        },
        set: async () => {},
      },
    },
    scripting: { executeScript: async () => [] },
    runtime: {
      id: "panel-preview",
      onMessage: { addListener() {} },
      sendMessage: async (msg) => {
        sent.push(msg);
        if (msg.type === "api") return apiReply(msg);
        if (msg.type === "page_broadcast") return broadcastReply(msg.message);
        if (msg.type === "panel_frame0" && (spec.page ?? {})[msg.message?.type]) {
          return next(spec.page[msg.message.type]);
        }
        return (spec.replies ?? {})[msg.type] ?? unreachable;
      },
    },
  };

  // A finished fill loop, without the page engine: the panel's own report code
  // runs on the fixture's rows. ns.fillLoop is assigned (not defined) by
  // shared/fill-loop.js, so a setter on the shared namespace can swap runFill
  // in the moment the real module lands.
  if (spec.fillReport) {
    const ns = (window.careerStudioCompanion ??= {});
    let loop;
    Object.defineProperty(ns, "fillLoop", {
      configurable: true,
      get: () => loop,
      set(value) {
        loop = value;
        loop.runFill = async (deps) => {
          deps.onProgress({ phase: "round", round: 1 });
          return { runId: "preview", host: spec.fillReport.host,
                   fields: spec.fillReport.fields, consentForms: false,
                   aiFailure: null, stopped: false, timedOut: false };
        };
      },
    });
  }

  // One-shot UI nudges once the panel has painted its four rail rows.
  const rail = () => document.getElementById("rail");
  const ready = () => rail() && rail().querySelectorAll("li.stg").length === 4;
  const when = (check, then, tries = 100) => {
    if (check()) then();
    else if (tries > 0) setTimeout(() => when(check, then, tries - 1), 50);
  };
  window.addEventListener("DOMContentLoaded", () => {
    if (spec.reopen) {
      when(() => document.getElementById(`stg-open-${spec.reopen}`),
           () => document.getElementById(`stg-open-${spec.reopen}`).click());
    }
    if (spec.autoPress) {
      // Four rows paint on the first render, before the panel is bound to its
      // tab, so "ready" alone clicks the unbound panel's primary. The page's
      // job match going out says binding began; the pause lets its answer land.
      const bound = () => sent.some((msg) => msg.type === "api");
      when(() => ready() && bound() && document.querySelector(".cta"),
           () => setTimeout(() => document.querySelector(".cta").click(), 150));
    }
  });
})();
