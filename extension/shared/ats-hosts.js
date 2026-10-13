/* Maestro CS Companion — which hosts are a known applicant-tracking system.
 *
 * ONE list, read by two callers that must never disagree: `content/detect.js` (which ATS is this
 * page, so its signals name the vendor) and the queued run's driver (shared/queue-run.js), which
 * types the saved job-site password only on a host listed here (design Part 4; the owner's
 * decision, 2026-10-13). A host that is not on the list is the user's to sign in to.
 *
 * Anchored at a dot or at the start of the host, never a substring: `greenhouse.io.attacker.test`
 * contains every ATS name you could want it to.
 *
 * WHAT THIS FILE PUBLISHES: ns.atsHosts = { HOSTS, vendorOf, isKnown }. Pure; no DOM.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  const HOSTS = [
    ["workday", /(^|\.)myworkdayjobs\.com$/],
    ["greenhouse", /(^|\.)greenhouse\.io$/],
    ["lever", /^jobs\.lever\.co$/],
    ["ashby", /^jobs\.ashbyhq\.com$/],
    ["smartrecruiters", /(^|\.)smartrecruiters\.com$/],
    ["workable", /^apply\.workable\.com$/],
    ["recruitee", /(^|\.)recruitee\.com$/],
    ["bamboohr", /(^|\.)bamboohr\.com$/],
    ["rippling", /^ats\.rippling\.com$|(^|\.)rippling-ats\.com$/],
    ["jobvite", /(^|\.)jobvite\.com$/],
    ["icims", /(^|\.)icims\.com$/],
    ["taleo", /(^|\.)taleo\.net$/],
    ["successfactors", /(^|\.)successfactors\.com$/],
  ];

  /** The vendor name for a hostname, or null. */
  function vendorOf(host) {
    const name = String(host ?? "").toLowerCase();
    return (HOSTS.find(([, pattern]) => pattern.test(name)) || [])[0] ?? null;
  }

  ns.atsHosts = { HOSTS, vendorOf, isKnown: (host) => vendorOf(host) !== null };
})();
