/* Maestro CS Companion — the navigation buttons an ATS names by its own markers.
 *
 * A button's text usually says what it is (shared/page-kind.js sorts it), but a submit button
 * can read "Done", and a vendor's own id is better evidence than a guessed word. This table
 * lists a few such markers per vendor. It is for NAVIGATION buttons only: how any page is
 * FILLED stays the generic loop, never a per-vendor procedure.
 *
 * A ROW EXISTS ONLY FOR A MARKER RECORDED IN THIS REPO (a fixture or a recorded page); nothing is
 * modelled from memory of a vendor. The verdicts: "text" (the marker names the vendor's navigation
 * button, and its own text still decides Next or Submit), "submit" (a Submit whatever it reads)
 * and "next". None ships as "next": that would be a button the run clicks on a marker's word
 * alone. Whatever the verdict, a Submit word in the button's text still wins in
 * `ns.pageKind.sortButton`, so even a wrong "next" could not turn a Submit-worded button into a
 * Next.
 *
 * THE START CHOOSER'S ONE LINK. A Workday posting's Apply leads to a "Start Your Application" page of three
 * same-tab links. Two of them do something to the user's data (one sends the resume to the site's parser, one copies
 * an earlier application's answers) and are never followed; the third, Apply Manually, only opens the form. CHOOSERS
 * lists exactly that one, by host, automation id, visible text and the end of its path, and cites the fixture that
 * records it. `isChooser` is the page reader's test of a link; the run follows the link by address and never clicks it
 * (content/page-reader.js `pressChooser`).
 *
 * WHAT THIS FILE PUBLISHES: ns.atsButtons = { knownSort, isChooser, HOSTS, RULES, CHOOSERS }. HOSTS, RULES and CHOOSERS
 * are published for the tests that pin them.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Copied from `shared/ats-hosts.js`; a test pins that the two agree for every vendor listed here.
  const HOSTS = {
    workday: /(^|\.)myworkdayjobs\.com$/,
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
  // Other vendors have no row: no fixture or recorded page here shows their navigation buttons.
  // Add one only with that evidence, citing it as above.
  const RULES = [
    { vendor: "workday", buttons: [{ automationId: "pageFooterNextButton", verdict: "text" }] },
  ];

  // SEEN: backend/tests/fixtures/browser/workday_chooser.html (owner's live run, 2026-10-14). ONE row, and the other two
  // links of that page are deliberately absent: a row is an allowance to follow a link, never a description of a page.
  const CHOOSERS = [
    { vendor: "workday", automationId: "applyManually", text: /^apply manually$/i, path: /\/apply\/applyManually$/ },
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

  /** Whether a link is the one the CHOOSERS table allows on this host: `attrs` is `{automationId, text, path}`, the link's
   * own data-automation-id, visible text (spaces squashed) and the path of its address. All must match, on the
   * vendor's host. An unknown host or a missing field is false. */
  function isChooser(host, attrs) {
    if (typeof host !== "string" || !host || !attrs || typeof attrs !== "object") return false;
    const name = host.toLowerCase();
    return CHOOSERS.some((row) => HOSTS[row.vendor]?.test(name)
      && attrs.automationId === row.automationId
      && typeof attrs.text === "string" && row.text.test(attrs.text.replace(/\s+/g, " ").trim())
      && typeof attrs.path === "string" && row.path.test(attrs.path));
  }

  ns.atsButtons = { knownSort, isChooser, HOSTS, RULES, CHOOSERS };
})();
