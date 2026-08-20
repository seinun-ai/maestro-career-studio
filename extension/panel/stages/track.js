/* Maestro CS Companion — the Track stage's body: the journey's end.
 *
 * One of five files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE RULE, restated because a file that only POINTS at it is a file that
 * half-remembers it: NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`,
 * no `document`, no network — everything a body may read is on the CONTEXT it
 * is passed (`stageContext()` in panel.js is that contract's definition).
 *
 * THE STATUS CONTROL IS THE FOOTER's, which is a DECISION rather than an
 * omission. Design §Footer: "the mark-applied nudge lives here permanently —
 * no more hunting" is the whole reason the panel has a constant status
 * segment instead of a Track-stage button — and this body is the richer view
 * beside it. A Draft/Applied pair rendered here as well would be two writers
 * for one field. `trackThis` is the exception that proves the split: Track
 * has no footer primary, the nudge lives where the user is reading, and the
 * write is creating the application the status segment has nothing to say
 * about until it exists.
 *
 * THAT SPLIT IS THE MOCKUP'S, not an invention: its Track scenario draws the
 * segment in the footer and gives the stage body an evidence line and one
 * sentence under it. The panel keeps the split and the reason for it.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** What the status MEANS, in the user's terms, and where the control is.
   *
   * TWO STATUSES ARE THIS SURFACE'S WHOLE VOCABULARY (`STATUS_OPTIONS` in
   * panel.js says why), and the third branch is what keeps that honest: an
   * application moved to `interviewing` in the web app has a real status this
   * panel has no button for, so the sentence NAMES it and sends the user where
   * the rest of the vocabulary lives. Printing "still a draft" over it would be
   * the panel reporting a state the record does not hold.
   */
  const TRACK_NOTES = {
    draft: "Still a draft — mark it Applied below once you have submitted it.",
    // ONE sentence for this event, and `actions/track.js` deliberately stays
    // silent rather than printing a second: `applied_at` is stamped on entry to
    // applied and feeds the analytics series, and two descriptions of that on
    // one screen is how a user comes to believe two things were recorded.
    applied: "Marked applied. The applied date is recorded.",
  };

  /** Nothing is written down for this page.
   *
   * The state is `stageFor`'s `track-this` nudge: a fill that finished from the
   * base resume, with no application behind it. When the panel already holds a
   * `job.id` and a `baseSlug`, the body offers the button the card has always
   * had (`POST /api/applications/from-base`). When it does not — Track never
   * loads a posting, so there is nothing here to save a job from — the
   * sentence says what happened and where to finish it rather than offering a
   * control whose POST would 404. The header's "Open in Maestro CS ↗" is that
   * route, which is why this line does not repeat it as a second link.
   */
  const NOT_TRACKED = "This page was filled from your base resume, and nothing "
    + "has been written down for it. Open Maestro CS to save the job and an "
    + "application.";
  const TRACK_THIS = "This page was filled from your base resume, and nothing "
    + "has been written down for it.";

  /** What this application has to show for itself, or nothing at all.
   *
   * TWO FACTS, and both come off `GET /api/applications/{id}` rather than out
   * of anywhere else — see `evidenceFrom` in panel.js, which is the one place
   * that reads them. The document it sends (`pdf_path`) and the day it went out
   * (`applied_at`). The endpoint carries no other evidence: the proposal
   * ledger's `evidence_json` belongs to the agent-apply flow and this panel is
   * not a client of it, so a receipt line here would be a claim with nothing
   * behind it.
   *
   * NO LINE WHEN THERE IS NOTHING, which is the honest absence rather than a
   * tidy-up: a draft with no rendered PDF has no evidence, and "📎 —" under a
   * step about whether the application went out is a row that reports its own
   * emptiness as a fact.
   *
   * "rendered" AND NOT "attached", which is the word the mockup used and the
   * one thing in it this body would not repeat. Nothing attached that PDF to
   * anything: it exists because a tailor rendered it. The panel says what is
   * true of the record it is reading.
   *
   * The paperclip is DECORATION and says so: an emoji reaches nobody using a
   * screen reader, and the text beside it carries the whole line — the same
   * rule the Fill stage's progress marks follow, with the opposite resolution
   * (there the mark IS the state, so it is labelled; here it is not, so it is
   * hidden).
   */
  function evidenceLine({ facts, build }) {
    const { evidence } = facts;
    if (!evidence) return null;
    const { node, attach } = build;
    const parts = [
      evidence.pdfName ? `${evidence.pdfName} rendered` : null,
      evidence.appliedOn ? `applied ${evidence.appliedOn}` : null,
    ].filter(Boolean);
    const line = node("div", "evi");
    if (evidence.pdfName) {
      const clip = node("span", null, "📎");
      clip.setAttribute("aria-hidden", "true");
      attach(line, clip);
    }
    return attach(line, node("span", null, parts.join(" · ")));
  }

  /** The Track stage: what this application is, and what it has behind it.
   *
   * TWO STATES, and they are the two ways the rail reaches this row:
   *
   * - an application exists — the ordinary end of the journey. The evidence
   *   line when there is any, and one sentence saying what the status means.
   *   The Draft/Applied control is the footer's; see this file's header.
   * - no application at all, which is `stageFor`'s `fillFromBase` path having
   *   finished: the user filled the form from their base resume and nothing was
   *   ever written down. There is no status to be draft ABOUT, so the footer
   *   renders no segment either. If the panel holds a job and a base, the body
   *   offers Track this application; if it does not, it says so.
   */
  function trackBody(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const body = node("div", "stg-body");
    if (!facts.application) {
      const canTrack = Boolean(facts.job?.id) && Boolean(facts.baseSlug);
      if (!canTrack) return attach(body, node("div", "sub", NOT_TRACKED));
      const button = node("button", "save", "Track this application");
      button.type = "button";
      button.disabled = facts.busy === true;
      button.addEventListener("click", act.trackThis);
      return attach(body, node("div", "sub", TRACK_THIS), button);
    }
    const status = facts.application.status ?? "draft";
    return attach(body, evidenceLine(ctx),
                  node("div", "sub", TRACK_NOTES[status]
                    ?? `Status: ${status}. Change it in Maestro CS.`));
  }

  ns.panelStageTrack = trackBody;
})();
