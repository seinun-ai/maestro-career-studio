/* Maestro CS Companion — the pause row: answer once, learn forever.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES, holds `busy` for as long as that takes, obeys the
 *   generation rule in full, and never assigns a stage.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented — see `panel/actions/during.js`. THIS FILE IS THE REASON
 *   that function has one home: the learn tail below used to run AFTER the
 *   span, which is the serialization hole that lost one row's answer to
 *   another's whole-object PUT. Anything added here that awaits belongs INSIDE
 *   the span.
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers.
 *
 * TWO NAMESPACE READS, both DECISIONS with a single source rather than facts
 * about this panel: `shared/policy.js` for what may never be filled, and
 * `shared/profile-fields.js` (through `ns.profileFieldFor`/`ns.normLabel`) for
 * which questions the fill engine has a typed home for. A second opinion about
 * either is how an answer gets learned where the rules do not look.
 *
 * ONE READ ACROSS THE SPLIT: `ns.panelFillFinished`, published by
 * `panel/actions/fill.js`. The last pause row closing has to mark the page done
 * exactly as a clean run would, so the two paths converge on ONE predicate
 * rather than agreeing about it in two files.
 *
 * WHAT THIS FILE PUBLISHES BESIDES ITS ACTION: `ns.saveTargetFor`,
 * `ns.withProfileAnswer`, `ns.withCustomAnswer` — the three PURE pieces of the
 * save, published beside it because none of them needs a store handle to be
 * driven, and each has a behaviour table behind it.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;

  /** WHERE a learned answer goes, as a pure function.
   *
   * TWO destinations, one store. Both land in the autofill profile through one
   * `PUT /api/settings/autofill`; what this decides is which SHAPE inside it:
   *
   * - a TYPED key (`preferences.notice_period`, `eligibility.over_18`) when the
   *   question is one the fill engine has a declared rule for, so the answer
   *   arrives where that rule already looks;
   * - the `custom` Q&A list otherwise, which the engine matches by label
   *   substring — the general case, and the one most application questions land
   *   in.
   *
   * `qa_entries` IS NOT THE OTHER DESTINATION, and this is the correction the
   * design doc's §R2 line needed. That table is application-scoped and nothing
   * reads it back into a later fill, so an answer saved there would pause again
   * on the next application — the exact promise this feature is named for,
   * broken silently. It stays what it is: the LLM's generated Q&A and cover
   * letters, kept as application evidence.
   *
   * THE PATTERNS ARE THE ENGINE'S OWN (`shared/profile-fields.js`), not a
   * second table written for this router. Two tables agreeing today is how an
   * answer ends up in `custom` for a question the rules fill from
   * `preferences.*` — filled from one place, learned into another, and pausing
   * forever.
   *
   * `fields` is injectable for the same reason `profileFieldFor`'s is: a table
   * test wants to drive the routing without asserting against whichever rules
   * happen to ship today.
   */
  function saveTargetFor(question, fields) {
    const field = ns.profileFieldFor(question, fields);
    return field ? { store: "profile", path: field.path, id: field.id }
      : { store: "custom" };
  }

  /** The profile with one typed key set, without touching anything else.
   *
   * A COPY at every level it walks, never a mutation: the object came off a GET
   * and the caller PUTs the result, so an in-place write would make the
   * before-and-after indistinguishable if the PUT then failed.
   *
   * The answer is stored AS TYPED, and the reason has to be stated across all
   * THREE readers of this profile rather than the one this file can see:
   *
   * - the FILL ENGINE (`content/autofill.js`). `yesNo` passes a string straight
   *   through and only maps booleans, and the option matcher lower-cases before
   *   comparing — so "Yes" fills a yes/no control.
   * - `/choose` (`services/autofill_choose.py`), which is handed the whole
   *   profile as prompt context and reads whatever is there.
   * - the SETTINGS FORM (`frontend/components/settings/autofill-section.tsx`),
   *   which is the one this file cannot test and the one that caught it. A
   *   yes/no field there renders through `booleanAnswer`, which trims and
   *   lower-cases — but ONLY when the field is declared `boolean: true`. The
   *   four fields a pause row can learn a yes/no into were not, so a stored
   *   "Yes" matched no option value and the select rendered EMPTY: the user
   *   opens Settings and their answer is not there.
   *
   * THE FIX WENT TO THE FORM, not to a `.toLowerCase()` here, because the
   * mismatch is not this writer's. A hand-edited `autofill.json` — which the
   * profile is documented as being — could already hold "Yes", and lowering on
   * learn would have fixed only the values this one path writes. A VALUE STORED
   * MUST RENDER IN ALL THREE READERS; that is the rule this docstring exists to
   * carry, because nothing in this file can check it.
   */
  const TYPED_WORK_AUTH_KEYS = [
    "status", "authorized_now", "sponsorship_now", "sponsorship_future",
    "authorization_expires_on", "countries_authorized",
  ];

  // The same dual-read boundary as autofill.js and the backend reader, applied
  // before the FIRST typed pause-row write. Once any typed key exists, both
  // readers intentionally stop consulting legacy keys; promote the two known
  // legacy answers together so learning one answer cannot orphan its sibling.
  const workAuthForWrite = (raw) => {
    const current = raw && typeof raw === "object" && !Array.isArray(raw)
      ? { ...raw }
      : {};
    if (TYPED_WORK_AUTH_KEYS.some((key) => key in current)) return current;
    return {
      ...current,
      authorized_now: current.authorized_to_work,
      sponsorship_future: current.requires_sponsorship,
    };
  };

  function withProfileAnswer(profile, path, answer) {
    const [head, ...rest] = path;
    const base = { ...(profile ?? {}) };
    const child = head === "work_auth" && rest.length
      ? workAuthForWrite(base[head])
      : base[head] ?? {};
    base[head] = rest.length
      ? withProfileAnswer(child, rest, answer)
      : answer;
    return base;
  }

  /** The custom Q&A list with this question answered — appended, or UPDATED in
   * place when it is already there.
   *
   * DEDUPED ON `normLabel`, which is the same normalisation the engine builds
   * its custom rules with (`norm(c.question)` in autofill.js) and the same one
   * `profileFieldFor` uses. Anything else and a question whose whitespace or
   * casing shifted between two ATSs would be appended a second time — and the
   * engine takes the FIRST match, so the older answer would keep winning while
   * the list grew a near-duplicate on every application.
   *
   * THE STORED QUESTION TEXT IS KEPT on an update, and only the answer moves.
   * The engine matches with `labelText.includes(rule.question)`, so a stored
   * question is a SUBSTRING PATTERN as much as a record — a shorter one the
   * user trimmed by hand in Settings matches more labels, and replacing it with
   * this page's longer label would silently narrow a rule the user widened.
   */
  function withCustomAnswer(custom, question, answer) {
    const rows = (Array.isArray(custom) ? custom : []).map((row) => ({ ...row }));
    const key = ns.normLabel(question);
    const at = rows.findIndex((row) => ns.normLabel(row?.question) === key);
    if (at === -1) {
      rows.push({ question, answer });
      return rows;
    }
    rows[at] = { ...rows[at], answer };
    return rows;
  }

  /** Learn the answer: read the profile, put it back with this one added.
   *
   * READ-MODIFY-WRITE against `/api/settings/autofill`, which is the same
   * representation the PUT takes — `get_profile`/`set_profile` over one JSON
   * setting. `/api/autofill/context` returns the identical object, but the
   * panel does not keep it (the store holds the fill's COUNTS, not the profile
   * it was filled from), so re-reading the settings copy is one cheap GET of
   * exactly the thing being written rather than a resume resolution we would
   * throw away.
   *
   * THE RACE, accepted and named, and NARROWER than it first was: the route
   * takes a WHOLE object, so a profile edit saved in the WEB APP between this
   * GET and this PUT is overwritten. That is the whole of the remaining window
   * — the panel's own writes cannot collide, because this runs inside the
   * caller's `busy` span and every control that could start a second one is out
   * of reach for its length (see `duringAction`). The user is standing in this
   * panel rather than in that form, and the alternative is a backend change
   * this task may not make (a merge endpoint, or an ETag). It is the same trade
   * the Settings page itself already makes with every save. If a later round
   * adds a merge route, this function is the one caller to move.
   *
   * THROWS on failure, and the caller treats that as a NOTE rather than a
   * rollback — see `submitAnswer`.
   */
  async function learnAnswer(store, row, answer) {
    const target = saveTargetFor(row.label);
    const current = await store.api("/api/settings/autofill");
    const profile = current?.value ?? {};
    const next = target.store === "profile"
      ? withProfileAnswer(profile, target.path, answer)
      : { ...profile, custom: withCustomAnswer(profile.custom, row.label, answer) };
    await store.api("/api/settings/autofill", {
      method: "PUT", body: JSON.stringify({ value: next }),
    });
    return target;
  }

  /** Answer ONE open field from the panel, and — unless the user said not to —
   * never be asked it again.
   *
   * THE TWO HALVES ARE INDEPENDENT, and that is the whole design of this
   * function rather than a detail of it. Writing the field is a message to a
   * page; learning the answer is a write to the profile. They can fail
   * separately, so they are reported separately: a learn that fails leaves the
   * field FILLED and adds a sentence, and never unwinds the write. Rolling the
   * page write back would be the panel emptying a box the user is looking at
   * because a setting did not save.
   *
   * THE POLICY CHECK IS HERE AS WELL AS IN THE BODY. The body renders no input
   * for a policy-blocked row, so this is unreachable through the UI — which is
   * exactly why it is written: the body's refusal is a rendering decision and
   * this is the one that touches the page. A future row source (a restored
   * residue, a re-collect) that reached this function without passing the
   * renderer would otherwise type a password into a form. `shared/policy.js`
   * is the single source both ask.
   *
   * NO WRITE FOR A ROW THAT IS NOT IN THE RESIDUE. The qid is addressed to a
   * control the collect tagged on THIS page; a submit that arrives after a tab
   * change is holding a token for a document that is gone, and `duringAction`'s
   * guard cannot see that because the store was already cleared.
   */
  async function submitAnswer(store, qid) {
    const facts = store.read();
    if (facts.busy !== null) return;
    const row = (facts.residue ?? []).find((entry) => entry.qid === qid);
    if (!row) return;
    if (ns.isPolicyBlocked(row.label ?? "")) {
      // Not an `error`: nothing went wrong. This is the panel declining, and
      // the sentence says which side declined and why.
      store.write({ note: { text: "This one is never filled from here — "
        + "signatures, passwords and government IDs are yours to type." } });
      store.render();
      return;
    }
    const draft = facts.answers[qid] ?? {};
    // The known value is the default ANSWER as well as the default text: a
    // retryable the user has not retyped is one they are confirming.
    const answer = String(draft.text ?? row.known_value ?? "").trim();
    if (!answer) {
      store.write({ note: { text: "Type an answer first." } });
      store.render();
      return;
    }
    // A retryable's answer came OUT of the profile, so there is nothing to
    // learn from putting it back — the body offers no checkbox for one, and
    // this is the same rule on the acting side.
    const learn = row.known_value == null && draft.learn !== false;
    // BOTH ROUND TRIPS INSIDE ONE `busy` SPAN — the page write AND the learn.
    // The learn used to run after `duringAction` returned, which cleared `busy`
    // for the whole length of it, and that was a serialization hole rather than
    // an untidiness:
    //
    // - two rows answered quickly interleaved as GET, GET, PUT, PUT, and the
    //   second whole-object PUT erased the first row's key while its note had
    //   already said "Saved to your profile" — a lost update the user was told
    //   had landed;
    // - and the footer's primary re-enabled mid-learn, so a second full fill
    //   could be started underneath an open profile write. The generation token
    //   does not catch that: it moves on a TAB CHANGE, and this is the same tab.
    //
    // The disabled state was an accident of where the render fell, and this is
    // the rule instead: `busy` covers everything an action writes, its learn
    // tail included (see `duringAction`'s own contract).
    const done = await duringAction(store, "fill", async () => {
      const frames = await store.broadcast({
        type: "fill_answers",
        // ONE pair, this qid. The message is a broadcast because a qid's frame
        // is not something the panel knows — the token is per-frame random and
        // a frame that does not own it finds nothing and skips — but the
        // PAYLOAD is one field, so no other control on the page is touched.
        pairs: [{ qid, answer, kind: row.kind }],
      });
      if (!frames.some((frame) => frame.result !== undefined)) {
        throw new Error(ns.guidedRun.NO_FRAME_REACHED);
      }
      // `fillAnswersByQid` returns the qids that STUCK — a select whose options
      // did not match, or an input that rejected the value, is simply absent.
      // So this is a readback, not an acknowledgement.
      const stuck = frames.flatMap((frame) => frame.result ?? []).includes(qid);
      if (!stuck || !learn) return { stuck, learned: "" };
      try {
        const target = await learnAnswer(store, row, answer);
        return { stuck,
          learned: target.store === "profile"
            ? " Saved to your profile."
            : " Remembered — this one won’t ask again." };
      } catch (err) {
        // CAUGHT HERE rather than left to `duringAction`, and that is what keeps
        // the two halves independent now that they share a span. A throw out of
        // this callback is the FILL failing: the note goes red and the row stays
        // open. The field is already written, so the honest report is a sentence
        // beside the success — never a rollback, and never a red note about a
        // page that did what it was asked.
        return { stuck, learned: ` Filled, but not remembered: ${
          String(err?.message ?? err)}` };
      }
    });
    if (!done) return;
    const { out: { stuck, learned } } = done;
    if (!stuck) {
      // The page was reached and the value did not take. The row STAYS, because
      // it is still open, and the sentence says what actually happened rather
      // than blaming the connection.
      store.write({ note: { text: row.options?.length
        ? "That answer didn’t match any of the options — try one of them verbatim."
        : "The field wouldn’t take that value. Try it on the page.", error: true } });
      store.render();
      return;
    }
    // PAST THE GUARD, and re-read: the broadcast is a round trip and the four
    // loaders have been writing to this store for the length of it.
    const after = store.read();
    const residue = (after.residue ?? []).filter((entry) => entry.qid !== qid);
    // Counted as written, and it has to be said explicitly: the Application
    // questions row computes "filled" as `writeResults` minus the residue, so a
    // qid that was PURE residue (abstained, or a /choose failure — never in a
    // guided_write) would leave the list by one and the filled count by none.
    // The outcome string is the engine's vocabulary for the same event.
    const writeResults = (after.writeResults ?? []).some((entry) => entry.qid === qid)
      ? after.writeResults
      : [...(after.writeResults ?? []), { qid, outcome: "filled" }];
    // The draft goes with the row. Keeping it would leave a store entry for a
    // control nothing renders, and re-opening the row (a re-run collects a new
    // qid anyway) would show an answer that is already in the form.
    const answers = { ...after.answers };
    delete answers[qid];
    store.write({ residue, writeResults, answers });
    const open = residue.length + (after.essays?.length ?? 0);
    const finished = ns.panelFillFinished({ fill: after.fill, writeResults, residue,
                                            essays: after.essays });
    store.write({
      note: { text: `Filled “${row.label}”.${learned}${open
        ? ` ${store.build.plural(open, "field")} still ${open === 1 ? "needs" : "need"} you.`
        : " Fill finished. Review before you submit."}` },
    });
    // CONVERGES with `startFill` rather than forking from it: the same
    // predicate over the same store fields, so the last pause row closing marks
    // this page done exactly as a clean run would have. `remember` is what
    // carries it across the next page of the wizard.
    if (finished) store.write({ touched: true });
    store.render();
    if (finished) store.remember();
  }

  ns.panelActionsPause = { submitAnswer };
  // Published beside the factory's parts rather than through them: the router
  // is a PURE function of a question and a table, it is the piece with a
  // behaviour table behind it, and a test that had to build a store handle to
  // reach it would be testing the handle.
  ns.saveTargetFor = saveTargetFor;
  ns.withCustomAnswer = withCustomAnswer;
  ns.withProfileAnswer = withProfileAnswer;
})();
