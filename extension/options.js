/* Address defaults and the fill-log choice are read from the service worker's
 * settings message; its DEFAULTS are the one place a default lives. */
(() => {
  "use strict";

  const form = document.getElementById("settings");
  const backend = document.getElementById("backendUrl");
  const app = document.getElementById("appUrl");
  const save = document.getElementById("save");
  const test = document.getElementById("test");
  const note = document.getElementById("note");
  const fillLog = document.getElementById("fillLog");
  let ready = false;
  let busy = false;

  function address(input, label) {
    const value = input.value.trim();
    try {
      // Check the spelling before URL normalizes paths such as /../ away.
      if (!/^https?:\/\/[^/?#@\\\s]+\/?$/i.test(value)) throw new Error();
      const url = new URL(value);
      if (!url.hostname || url.username || url.password) throw new Error();
      return url.origin;
    } catch (_) {
      note.textContent = `${label}: use http:// or https:// and a host, with an optional port.`;
      input.focus();
      return null;
    }
  }

  function setBusy(value) {
    busy = value;
    save.disabled = !ready || busy;
    test.disabled = !ready || busy;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!ready || busy) return;
    const backendUrl = address(backend, "Backend address");
    if (!backendUrl) return;
    const appUrl = address(app, "App address");
    if (!appUrl) return;
    setBusy(true);
    try {
      await chrome.storage.sync.set({ backendUrl, appUrl });
      backend.value = backendUrl;
      app.value = appUrl;
      const destination = new URL(backendUrl);
      const host = destination.hostname;
      const local = host === "localhost" || host.endsWith(".localhost")
        || host === "127.0.0.1" || host === "[::1]";
      note.textContent = local ? "Saved."
        : `Saved. The Companion now sends job pages and your answers to ${host}.`
          + (destination.protocol === "http:" ? " This address is not encrypted." : "");
    } catch (_) {
      note.textContent = "Couldn't save settings. Try again.";
    } finally {
      setBusy(false);
    }
  });

  test.addEventListener("click", async () => {
    if (!ready || busy) return;
    const backendUrl = address(backend, "Backend address");
    if (!backendUrl) return;
    setBusy(true);
    note.textContent = "Connecting…";
    try {
      // JSON POST includes the extension Origin; GET omits it and bypasses the origin gate.
      const response = await fetch(`${backendUrl}/health`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        signal: AbortSignal.timeout(5000),
      });
      if (response.status === 403) {
        note.textContent = `Maestro at ${backendUrl} refused this extension. Update Maestro or add this extension's ID.`;
      } else {
        note.textContent = "Connected.";
      }
    } catch (_) {
      note.textContent = `Can't reach Maestro at ${backendUrl}.`;
    } finally {
      setBusy(false);
    }
  });

  // The fill log saves on the change itself: a switch that waits for Save reads
  // as on while nothing is stored. It writes its one key and nothing else.
  fillLog.addEventListener("change", async () => {
    if (!ready) return;
    const on = fillLog.checked === true;
    fillLog.disabled = true;
    try {
      await chrome.storage.sync.set({ telemetryEnabled: on });
      note.textContent = on ? "Fill log on." : "Fill log off.";
    } catch (_) {
      fillLog.checked = !on;
      note.textContent = "Couldn't save settings. Try again.";
    } finally {
      fillLog.disabled = false;
    }
  });

  for (const input of [backend, app]) {
    input.addEventListener("input", () => { note.textContent = ""; });
  }

  (async () => {
    try {
      const reply = await chrome.runtime.sendMessage({ type: "read_settings" });
      if (!reply?.ok) throw new Error();
      backend.value = reply.data.backendUrl;
      app.value = reply.data.appUrl;
      fillLog.checked = reply.data.telemetryEnabled === true;
      fillLog.disabled = false;
      ready = true;
      setBusy(false);
    } catch (_) {
      note.textContent = "Couldn't load settings. Reopen this page to try again.";
    }
  })();
})();
