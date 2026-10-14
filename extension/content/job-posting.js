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

  const oneLine = (text) => String(text ?? "").replace(/\s+/g, " ").trim();

  /** Whether a node is on screen. `innerText` of a node that is not rendered returns its `textContent`,
   * so a hidden duplicate of a description (a mobile copy a stylesheet hides) reads exactly like the
   * visible one, and a longer hidden copy would win a "longest text" pick. A `display:contents` box
   * has no rectangles of its own but its children do. */
  function isShown(node) {
    if (node.getClientRects().length > 0) return true;
    return getComputedStyle(node).display === "contents" && [...node.children].some(isShown);
  }

  /** A container worth reading as a description: on screen, and more than 300 characters of text. */
  function usableDescriptionNode(node) {
    return isShown(node) && (node.innerText?.trim() ?? "").length > 300;
  }

  // A heading that introduces a description, as the WHOLE text of its element.
  const DESCRIPTION_HEADING = /^(job description|about the (job|role|position)|job summary|role (description|overview)|position (description|summary))\s*:?$/i;
  // Not `label` or `legend`: those name a form field ("Role Description" over a rich-text box).
  const HEADING_CANDIDATES = "h1, h2, h3, h4, h5, h6, [role=heading], p, div, span, strong, b, dt";
  const CHROME_SELECTOR = "nav, header, footer";
  const SITE_CHROME_ANY = "nav, header, footer, [role=navigation], [role=banner], [role=contentinfo]";
  // The field reader's control rule plus the ARIA widgets that show a value as plain text.
  const FORM_CONTROL = 'input:not([type="hidden"]), select, textarea, button[aria-haspopup], [role="combobox"], '
    + '[role="textbox"], [role="listbox"], [contenteditable]:not([contenteditable="false"])';
  const PAGE_WIDE = /^(html|body|main|article|form|nav|header|footer)$/i;
  const headingKey = (el) => oneLine(el.textContent).replace(/\s*:$/, "").toLowerCase();

  /** The text under a description heading, for a posting with no JSON-LD and no job-description class.
   *
   * Finds a visible element whose whole text is a description heading, then climbs to the first ancestor
   * with more than 300 characters of text: that ancestor is the description's own section. The climb is
   * ABANDONED (this heading answers nothing) at `main`/`article`/`body`/`form`, because that is the page's
   * text or an application form and not a section; at `nav`/`header`/`footer`, and at an ancestor that
   * CONTAINS site chrome (a page-wide wrapper); at any ancestor holding a form control or an ARIA text
   * widget, so a value the user typed into an application form never rides into a save; and at an
   * ancestor holding the same heading twice, which is a list of cards and not a posting. The first
   * heading in document order that gives a section answers. */
  function descriptionUnderHeading() {
    const found = [...document.querySelectorAll(HEADING_CANDIDATES)].filter((el) => el.childElementCount <= 2
      && el.textContent.length <= 60 && DESCRIPTION_HEADING.test(oneLine(el.textContent))
      && isShown(el) && !el.closest(CHROME_SELECTOR));
    // A heading drawn as `div > span` matches twice; the inner one is the heading.
    const headings = found.filter((el) => !found.some((other) => other !== el && el.contains(other)));
    for (const heading of headings) {
      const key = headingKey(heading);
      for (let node = heading.parentElement; node; node = node.parentElement) {
        if (PAGE_WIDE.test(node.tagName) || node.querySelector(FORM_CONTROL) || node.querySelector(SITE_CHROME_ANY)
          || headings.some((other) => other !== heading && headingKey(other) === key && node.contains(other))) break;
        if (usableDescriptionNode(node)) return node.innerText.trim();
      }
    }
    return null;
  }

  // The Darwinbox candidate portal (Angular; no JSON-LD, no `h1`, document title "Job Details Page"). Recorded
  // from a live page, DOM only: a job page is /ms/candidatev2/<x>/careers/jobDetails/<id> on a darwinbox host.
  const DARWINBOX_HOST = /(^|\.)darwinbox\.(in|com)$/i;
  const DARWINBOX_JOB_PATH = /^\/ms\/candidatev2\/[^/]+\/careers\/jobDetails\/[^/]+\/?$/;
  // The portal's translation key, shown where its language file did not load ("mainPage.companyName").
  const UNTRANSLATED_KEY = /^[a-z]+[A-Z]\w*\.\w/;

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

  /** Whether the page itself names this text as its title: the document title or `og:title` contains it,
   * and it is not the site's name. A hero ("Acme Corp") or a banner ("Careers") fails both. */
  function namedByPage(text) {
    const meta = (property) => oneLine(
      document.querySelector(`meta[property="${property}"]`)?.getAttribute("content")).toLowerCase();
    const lower = text.toLowerCase();
    return lower !== meta("og:site_name")
      && [oneLine(document.title).toLowerCase(), meta("og:title")].some((named) => named.includes(lower));
  }

  /** The first visible `h1` outside site chrome that the page's own title names, for a page whose title
   * no recorded adapter gives. */
  function visibleH1Title() {
    for (const h1 of document.querySelectorAll("h1")) {
      const text = oneLine(h1.innerText);
      if (text && text.length <= 200 && isShown(h1) && !h1.closest(CHROME_SELECTOR) && namedByPage(text)) return text;
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
