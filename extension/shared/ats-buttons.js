/* Maestro CS Companion — the navigation buttons an ATS names by its own markers.
 *
 * A button's text usually says what it is (shared/page-kind.js sorts it), but a submit button
 * can read "Done", and a vendor's own id is better evidence than a guessed word. This table
 * lists a few such markers per vendor. It is for NAVIGATION buttons only: how any page is
 * FILLED stays the generic loop, never a per-vendor procedure.
 *
 * THE TABLE CAN ONLY STOP A RUN. A shipped verdict is "submit" (the button is a Submit whatever
 * it reads) or "text" (the marker names the vendor's navigation button, and its own text still
 * decides Next or Submit). A "next" entry would be a button the run clicks on a marker's word
 * alone, so none ships without a recorded fixture that shows the marker (the entries below say
 * where their evidence stands). Whatever the verdict, a Submit word in the button's text still
 * wins in `ns.pageKind.sortButton`, so even a wrong "next" could not turn a Submit-worded
 * button into a Next.
 *
 * WHAT THIS FILE PUBLISHES: ns.atsButtons = { knownSort, HOSTS, RULES }. HOSTS and RULES are
 * published for the tests that pin them.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Copied from `content/detect.js` ATS_HOSTS (it publishes no table); a test pins that the
  // two agree for every vendor listed here.
  const HOSTS = {
    workday: /(^|\.)myworkdayjobs\.com$/,
    greenhouse: /(^|\.)greenhouse\.io$/,
    lever: /^jobs\.lever\.co$/,
  };

  // Each button entry names attributes that must ALL equal the button's own: `id`, `qa` (its
  // data-qa) or `automationId` (its data-automation-id).
  //
  // Workday: SEEN. backend/tests/test_extension_detection.py (`_WORKDAY_MY_INFORMATION`) records a
  // live apply page whose footer button is data-automation-id="pageFooterNextButton" reading
  // "Save and Continue". The marker says THIS is the step's navigation button, and "text" leaves
  // the verdict to its label: Workday relabels the same button "Submit" on the last step, so it is
  // never mapped to "next".
  //
  // Greenhouse and Lever: ASSUMED, not seen. No fixture or recorded page in this repo shows either
  // vendor's apply form; the markers are written from knowledge of the vendors' public forms, to
  // be confirmed in the Phase 2 live check. They stay because a wrong "submit" entry costs a
  // stopped run, and a missing one costs nothing the text would not catch.
  const RULES = [
    { vendor: "workday", buttons: [{ automationId: "pageFooterNextButton", verdict: "text" }] },
    { vendor: "greenhouse", buttons: [{ id: "submit_app", verdict: "submit" }] },
    { vendor: "lever", buttons: [
      { id: "btn-submit", verdict: "submit" },
      { qa: "btn-submit", verdict: "submit" },
    ] },
  ];

  const ATTRS = ["id", "qa", "automationId"];

  /** "submit" | "next" | "text" when this vendor's table names the button, else null. "text" means
   * the button is the page's navigation and its own label decides; null means the table says
   * nothing, and the label decides too. */
  function knownSort(host, attrs) {
    if (typeof host !== "string" || !host || !attrs || typeof attrs !== "object") return null;
    const name = host.toLowerCase();
    for (const rule of RULES) {
      const hostPattern = HOSTS[rule.vendor];
      if (!hostPattern || !hostPattern.test(name)) continue;
      for (const entry of rule.buttons) {
        const keys = ATTRS.filter((k) => entry[k] !== undefined);
        if (keys.length && keys.every((k) => typeof attrs[k] === "string" && attrs[k] === entry[k])) {
          return entry.verdict === "next" || entry.verdict === "text" ? entry.verdict : "submit";
        }
      }
    }
    return null;
  }

  ns.atsButtons = { knownSort, HOSTS, RULES };
})();
