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
  const CHROME_SELECTOR = "nav, header, footer";
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
        || heading.closest(CHROME_SELECTOR)) continue;
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

  const oneLine = (text) => String(text ?? "").replace(/\s+/g, " ").trim();

  // The Darwinbox candidate portal (Angular; no JSON-LD, no `h1`, document title "Job Details Page"). Recorded
  // from a live page, DOM only: a job page is /ms/candidatev2/<x>/careers/jobDetails/<id> on a darwinbox host.
  const DARWINBOX_HOST = /(^|\.)darwinbox\.(in|com)$/i;
  const DARWINBOX_JOB_PATH = /^\/ms\/candidatev2\/[^/]+\/careers\/jobDetails\/[^/]+\/?$/;
  // The portal's translation key, shown where its language file did not load ("mainPage.companyName").
  const UNTRANSLATED_KEY = /^[A-Za-z][\w-]*(\.[\w-]+)+$/;

  /** Title, company and place of a Darwinbox job page, each left out when the page does not give it.
   * Title: the header's `span.title`. Place: the visible Job Snapshot item labelled "Location". Company:
   * only the meta description ("Job Title | <Company>"), and not when that holds a translation key. */
  function darwinboxFacts() {
    if (!DARWINBOX_HOST.test(location.hostname) || !DARWINBOX_JOB_PATH.test(location.pathname)) return {};
    const snapshot = [...document.querySelectorAll(".grid-item")].find((item) => isShown(item)
      && oneLine(item.querySelector(".label")?.textContent).toLowerCase() === "location");
    const named = /^Job Title \| (.+)$/.exec(
      oneLine(document.querySelector('meta[name="description"]')?.getAttribute("content")));
    return {
      title: oneLine(document.querySelector(".header-section .title-section > .title")?.textContent),
      place: oneLine(snapshot?.querySelector(".value")?.textContent),
      company: named && !UNTRANSLATED_KEY.test(named[1]) ? named[1] : "",
    };
  }

  /** The first visible `h1` outside site chrome, for a page whose title no recorded adapter gives. */
  function visibleH1Title() {
    for (const h1 of document.querySelectorAll("h1")) {
      const text = oneLine(h1.textContent);
      if (text && text.length <= 200 && isShown(h1) && !h1.closest(CHROME_SELECTOR)) return text;
    }
    return "";
  }

  /** The `Title:` / `Company:` / `Location:` lines the JSON-LD path writes, for a page read as visible
   * content: what a recorded site adapter knows, else the page's own `h1` for the title. Empty when
   * the page gives none; the caller writes the blank line after them only when there are some. */
  function postingHeaderLines() {
    const site = darwinboxFacts();
    const title = site.title || visibleH1Title();
    return [title && `Title: ${title}`, site.company && `Company: ${site.company}`,
      site.place && `Location: ${site.place}`].filter(Boolean);
  }

  ns.findJobPostingInDocument = findJobPostingInDocument;
  ns.postingHeaderLines = postingHeaderLines;
  ns.usableDescriptionNode = usableDescriptionNode;
  ns.descriptionUnderHeading = descriptionUnderHeading;
})();
