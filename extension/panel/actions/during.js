/* Maestro CS Companion — the round trip every panel action is made of.
 *
 * ONE FUNCTION, ONE FILE, AND THAT IS THE POINT OF THE FILE (plus the words a
 * failure ends with, `failureNote` and the key matching it shares with Fill). `duringAction` is
 * the `busy` span, and the `busy` span is this directory's ONE serialization
 * rule: every control on the surface reads `busy` to decide whether it may be
 * pressed, so a round trip that happens outside the span is one no control
 * knows about. It was broken once by PLACEMENT (Task 13's learn tail, recorded
 * in full below), and per-concern files each half-remembering the rule is
 * exactly how the next tail lands outside it.
 *
 * So there is one definition, it lives here on its own, and every concern file
 * under `panel/actions/` reads it off the namespace (`ns.panelDuringAction`)
 * rather than carrying a `try` of its own. A second copy of these seventeen
 * lines is the clone the Round A gate already found once and fixed into this
 * function rather than banking it in `.slopconfig.json`.
 *
 * IT REACHES FOR NOTHING, like everything else here: no `card`, no `chrome`, no
 * `document`, no `fetch`, no timers. It is handed the store HANDLE panel.js
 * built (`actionStore()`, whose comment is that contract's definition) and it
 * uses four things off it — `token`, `write`, `render`, `current`.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** The round trip itself, written ONCE: take `busy`, clear the note, run the
   * call, and come back either with an answer or with the failure already in
   * the note slot.
   *
   * WRITTEN OUT THREE TIMES UNTIL THE ROUND-A GATE, which is where the slop
   * ratchet reported it as two clone pairs across `addJob`, `scoreAllBases`
   * and `quickTailor` — an honest finding, and the same fourteen lines each
   * time.
   *
   * THE GENERATION CHECK IS ON BOTH LIMBS, which is the whole reason this is a
   * helper and not a bare `try`. The user is free to change tabs while a POST
   * is open, and a sentence about the page they left — success OR failure — is
   * as wrong in the note slot of the tab they are on. `null` back means "this
   * answer is not yours to paint": either the call failed (note already
   * written) or the panel has moved on (nothing written, deliberately).
   *
   * The caller gets the token back rather than re-reading it, because
   * everything it does after this point is still on behalf of the tab that was
   * bound when the call went out.
   *
   * `busy` COVERS EVERY AWAIT AN ACTION MAKES, including a tail round trip made
   * after the one this helper is named for. That is the serialization rule of
   * this directory and it is stated here because here is where it is enforced —
   * every control on the surface reads `busy` to decide whether it may be
   * pressed, so a round trip that happens outside the span is one no control
   * knows about.
   *
   * STATED AS "EVERY AWAIT" RATHER THAN "EVERYTHING AN ACTION WRITES", which is
   * what this paragraph used to claim and is not true of any action here: every
   * one of them writes its result to the store AFTER this helper returns, with
   * `busy` already cleared. That is safe for one reason and only one — there is
   * no await between the return and those writes, so no other action can be
   * started in between and there is no interleave window to lose. The moment a
   * future action puts an await there, its writes belong INSIDE the span, which
   * is exactly the move `submitAnswer`'s learn tail had to make.
   *
   * It is written down because it was broken once, by placement rather than by
   * decision: `submitAnswer` used to learn the answer AFTER this returned, so
   * `busy` was null for the whole profile round trip. Two rows answered quickly
   * then interleaved GET, GET, PUT, PUT — and the profile takes a WHOLE OBJECT,
   * so the second PUT erased the first row's key while its note already said the
   * answer was saved. The generation token cannot catch that: it moves on a tab
   * change, and both writes were the same tab. A tail that must not overlap the
   * next press belongs inside the span, not after it.
   *
   * `failed` IS THE CALL SITE'S SENTENCE, and a failure never reaches the note
   * as raw text: "Couldn't <what>." (a string, or `{ what, answered }` when a
   * refusal from the backend deserves its own sentence), finished by
   * `failureNote` with the next step. */
  async function duringAction(store, kind, call, failed) {
    const token = store.token();
    store.write({ busy: kind, note: null });
    store.render();
    let out;
    try {
      out = await call();
    } catch (err) {
      if (!store.current(token)) return null;
      store.write({ busy: null, note: { text: failureNote(failed, err), error: true } });
      store.render();
      return null;
    }
    if (!store.current(token)) return null;
    store.write({ busy: null });
    return { token, out };
  }

  /** The server's API key failures, the SAME two patterns the web app's
   * `errorDetail` reads (frontend/lib/error-text.ts; pinned equal by
   * `test_the_panel_recognises_a_key_failure_by_the_web_apps_own_patterns`).
   * They name an environment variable or quote a provider's 401, so the
   * panel recognises them and never shows them. */
  const MISSING_KEY = /\bno (?:openai |gemini )?api key\b|\b[A-Z]+_API_KEY is required\b/i;
  const REFUSED_KEY = /invalid_api_key|incorrect api key|api key not valid|api_key_invalid|error code: 401\b|your key was refused|refused your api key/i;

  /** The two next steps a key failure has, in the panel's words: the
   * Settings path is the web app's, so it says where that is. */
  const KEY_STEPS = {
    missing: "Add an API key in Maestro CS under Settings › AI & models.",
    refused: "Check your API key in Maestro CS under Settings › AI & models.",
  };

  /** Is this failure about the API key, and which way: `"missing"` (none is
   * set), `"refused"` (the provider turned it down, or failed: a 502 is
   * `app.main`'s LLMProviderError, whatever the call was), or null.
   * Missing wins over the status, because no key and a bad key are opposite
   * fixes and the server sends "No API key is set" as a 502 too. */
  function keyProblem(err) {
    const message = String(err?.message ?? "");
    if (MISSING_KEY.test(message)) return "missing";
    if (REFUSED_KEY.test(message) || err?.status === 502) return "refused";
    return null;
  }

  /** What the note says when a round trip fails: "Couldn't <what>." and then
   * what to do next, never the error's own text.
   *
   * The raw message is words for whoever wrote the code (a backend `detail`, a
   * bare status, "Failed to fetch"), so it goes to the console and the user
   * gets the sentence the call site wrote. A message the panel wrote itself
   * passes through as it is, because it already IS that sentence: it carries
   * `shown` (`ns.guidedRun.shown` makes one).
   *
   * THE NEXT STEP TURNS ON THE STATUS AND THE KEY: no status means no HTTP
   * answer came back, so the step is to check the app is running; a key
   * failure (`keyProblem`) is the key's step, add one or check it; any other
   * status means the backend answered and refused, so the step is the call
   * site's `answered` sentence when it has one (a string, or a function of the
   * error that may decline with null), else another try. */
  function failureNote(failed, err) {
    if (err?.shown === true) return String(err.message);
    console.warn("[maestro-cs] panel action failed:", err);
    const { what = "Couldn't do that.", answered = null } =
      typeof failed === "string" ? { what: failed } : failed ?? {};
    if (err?.status === undefined) return `${what} Check that Maestro CS is running.`;
    const key = keyProblem(err);
    if (key) return `${what} ${KEY_STEPS[key]}`;
    const own = typeof answered === "function" ? answered(err) : answered;
    return own || `${what} Try again.`;
  }

  ns.panelDuringAction = duringAction;
  // Read by the Fill action, which reports a `/choose` failure the runner
  // swallowed: the same key words, from the same patterns.
  ns.panelKeyProblem = keyProblem;
  ns.panelKeySteps = KEY_STEPS;
})();
