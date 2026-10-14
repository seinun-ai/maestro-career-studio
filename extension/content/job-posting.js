/* Maestro CS Companion — shared schema.org JobPosting walk. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** Find the first usable JobPosting in a JSON-LD tree.
   * presenceOnly=true is detection: a type declaration is enough.
   * presenceOnly=false is extraction: a description is required. */
  function findJobPosting(node, { presenceOnly = false } = {}) {
    if (!node || typeof node !== "object") return null;
    if (Array.isArray(node)) {
      for (const item of node) {
        const hit = findJobPosting(item, { presenceOnly });
        if (hit) return hit;
      }
      return null;
    }
    const type = node["@type"];
    const isPosting = type === "JobPosting"
      || (Array.isArray(type) && type.includes("JobPosting"));
    if (isPosting && (presenceOnly || Boolean(node.description))) return node;
    if (node["@graph"]) {
      return findJobPosting(node["@graph"], { presenceOnly });
    }
    return null;
  }

  function findJobPostingInDocument({ presenceOnly = false } = {}) {
    for (const script of document.querySelectorAll(
      'script[type="application/ld+json"]')) {
      try {
        const posting = findJobPosting(
          JSON.parse(script.textContent), { presenceOnly });
        if (posting) return posting;
      } catch (_) { /* malformed JSON-LD: keep looking */ }
    }
    return null;
  }

  /** Whether a node is on screen. `innerText` of a node that is not rendered returns its `textContent`,
   * so a hidden duplicate of a description (a mobile copy a stylesheet hides) reads exactly like the
   * visible one, and a longer hidden copy would win a "longest text" pick. */
  const isShown = (node) => node.getClientRects().length > 0;

  /** A container worth reading as a description: on screen, and more than 300 characters of text. */
  function usableDescriptionNode(node) {
    return isShown(node) && (node.innerText?.trim() ?? "").length > 300;
  }

  // A heading that introduces a description, as the WHOLE text of its element.
  const DESCRIPTION_HEADING = /^(job description|about the (job|role|position)|job summary|role (description|overview)|position (description|summary))\s*:?$/i;
  const HEADING_CANDIDATES = "h1, h2, h3, h4, h5, h6, [role=heading], p, div, span, strong, b, legend, dt, label";
  const SITE_CHROME = /^(nav|header|footer)$/i;
  const PAGE_WIDE = /^(html|body|main|article)$/i;

  /** The text under a description heading, for a posting with no JSON-LD and no job-description class.
   *
   * Finds a visible element whose whole text is a description heading, then climbs to the first ancestor
   * with more than 300 characters of text: that ancestor is the description's own section. The climb is
   * ABANDONED (this heading answers nothing) at `main`/`article`/`body`, because that is the page's text
   * and not a section's, at `nav`/`header`/`footer`, and at any ancestor holding a form control, so a
   * value the user typed into an application form beside the posting never rides into a save. Several
   * headings: the longest section. */
  function descriptionUnderHeading() {
    let best = null;
    for (const heading of document.querySelectorAll(HEADING_CANDIDATES)) {
      if (heading.childElementCount > 2 || heading.textContent.length > 40
        || !DESCRIPTION_HEADING.test(heading.textContent.trim()) || !isShown(heading)
        || heading.closest("nav, header, footer")) continue;
      for (let node = heading.parentElement; node; node = node.parentElement) {
        if (PAGE_WIDE.test(node.tagName) || SITE_CHROME.test(node.tagName)
          || node.querySelector("input, textarea, select")) break;
        if (usableDescriptionNode(node)) {
          const text = node.innerText.trim();
          if (best === null || text.length > best.length) best = text;
          break;
        }
      }
    }
    return best;
  }

  ns.findJobPostingInDocument = findJobPostingInDocument;
  ns.usableDescriptionNode = usableDescriptionNode;
  ns.descriptionUnderHeading = descriptionUnderHeading;
})();
