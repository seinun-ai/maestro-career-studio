/* Maestro CS Companion — tells the panel THAT you changed a field, never what
 * you typed.
 *
 * `inventory.js` calls `ns.onFieldTouched(fid)` for each field the USER changed
 * (a trusted input or change while the engine is not working on that field: the
 * engine's own writes are exempt there, by `fillBusyEl`). This file batches those
 * fids and sends the panel ONE throttled message, `{ type: "fields_touched", fids }`,
 * at most once per `THROTTLE_MS`. The panel treats it as a hint to re-read the
 * page through the gated `fill_inventory` and post what changed
 * (`panel/panel.js` `onFieldsTouched`); the message itself carries field ids
 * (opaque tokens this frame minted) and nothing else.
 *
 * THE FRAME GATE IS ASKED AT SEND TIME (`ns.frameMayReceiveUserData`, from
 * agent.js): a frame that has not earned the user's data (an ad or chat iframe)
 * says nothing about what happens in it (SYSTEM.md {#inv-frame-earns-data}). The
 * top frame passes; a subframe must show a form of its own.
 *
 * LOAD ONCE, like inventory.js: `panel_prepare` re-injects every content script
 * into the same isolated world.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/touch-notice.js")) return;
  loaded.add("content/touch-notice.js");

  const THROTTLE_MS = 2000;
  const MAX_FIDS = 200;
  let pending = new Set();
  let timer = null;

  function flush() {
    timer = null;
    const fids = [...pending].slice(0, MAX_FIDS);
    pending = new Set();
    try {
      if (!fids.length || ns.frameMayReceiveUserData?.({}) !== true) return;
      // The panel (an extension page) hears it; the service worker has no handler
      // for the type and ignores it. A page with no panel open answers nothing.
      Promise.resolve(chrome.runtime.sendMessage({ type: "fields_touched", fids })).catch(() => {});
    } catch {
      // The extension reloaded under this page: nothing to tell.
    }
  }

  ns.onFieldTouched = (fid) => {
    pending.add(fid);
    if (timer === null) timer = setTimeout(flush, THROTTLE_MS);
  };
})();
