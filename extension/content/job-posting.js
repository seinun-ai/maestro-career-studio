/* Maestro CS Companion — shared schema.org JobPosting walk. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** A JSON-LD node with every property under schema.org's own spelling, all the way down.
   *
   * schema.org spells a property with a lower-case first letter ("description", "hiringOrganization").
   * A career site whose serializer capitalises them ("Title", "Description", "HiringOrganization":
   * {"Name": …}, "Address"; Cornerstone's career site) still declares a JobPosting, and a reader of
   * schema.org's spelling finds no description in it. A property the node already carries in schema.org's
   * spelling wins over its capitalised twin, and `@` keywords are as written. */
  function schemaSpelled(node) {
    if (Array.isArray(node)) return node.map(schemaSpelled);
    if (!node || typeof node !== "object") return node;
    // `fromEntries` defines each property outright, so a page's "__proto__" key is only a property.
    return Object.fromEntries(Object.entries(node)
      .map(([key, value]) => [key.charAt(0).toLowerCase() + key.slice(1), key, value])
      .filter(([name, key]) => name === key || !Object.hasOwn(node, name))
      .map(([name, , value]) => [name, schemaSpelled(value)]));
  }

  /** Find the first usable JobPosting in a JSON-LD tree.
   * presenceOnly=true is detection: a type declaration is enough.
   * presenceOnly=false is extraction: a description is required, and the posting comes back in
   * schema.org's spelling (`schemaSpelled`), so every reader of it reads one shape. */
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
    if (isPosting && presenceOnly) return node;
    if (isPosting) {
      const posting = schemaSpelled(node);
      if (posting.description) return posting;
    }
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

  // Elements a browser starts on a new line. A `p` also gets a blank line around it, as `innerText` gives it.
  const BLOCK = /^(address|article|aside|blockquote|caption|center|dd|details|div|dl|dt|fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|pre|section|summary|table|tbody|tfoot|thead|tr|ul)$/;
  const UNREAD = /^(script|style|template|noscript)$/;
  const CELL = -1; // between two cells of a row

  /** A JobPosting description's HTML as the text a reader of the page sees.
   *
   * A JSON-LD description is markup that is never rendered, and the `innerText` of a node that is not
   * rendered is its `textContent`: blocks with no space between them in the source ran together
   * ("Annual SalaryJob Closing"), and a `style` block's rules read as prose. So the markup is parsed
   * into a document of its own (nothing in it loads or runs) and walked: a block starts a new line, a
   * `p` leaves a blank line, a `br` breaks the line, the cells of a row are a tab apart, and breaks
   * that meet count once, the widest. Whitespace between two blocks is not text, and a run of spaces
   * is one; a newline inside a run of text is kept, since a description written as plain text has
   * nothing else to tell its lines apart. */
  function descriptionText(html) {
    const items = []; // text as written, and numbers: the line breaks a block edge asks for, or CELL
    const walk = (node) => {
      for (const child of node.childNodes) {
        if (child.nodeType === 3) {
          const text = child.nodeValue.replace(/[^\S\n]+/g, " ");
          items.push(text.trim() ? text : " ");
        }
        if (child.nodeType !== 1) continue;
        const tag = child.tagName.toLowerCase();
        if (UNREAD.test(tag)) continue;
        if (tag === "br") { items.push("\n"); continue; }
        const edge = tag === "p" ? 2 : BLOCK.test(tag) ? 1 : 0;
        if (edge) items.push(edge);
        walk(child);
        if (edge) items.push(edge);
        if (/^t[dh]$/.test(tag) && child.nextElementSibling) items.push(CELL);
      }
    };
    walk(new DOMParser().parseFromString(String(html ?? ""), "text/html").body);
    let text = "";
    let gap = 0;
    for (const item of items) {
      if (typeof item === "number") {
        gap = item === CELL || gap === CELL ? CELL : Math.max(gap, item);
      } else if (!(gap && item === " ")) {
        if (text) text += gap === CELL ? "\t" : "\n".repeat(gap);
        gap = 0;
        text += item;
      }
    }
    return text.replace(/ {2,}/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }

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
  const DESCRIPTION_HEADING = /^(job description|about the (job|role|position)|job summary|role (description|overview)|position (description|summary)|((job|role) )?description (&|and) (requirements|qualifications))\s*:?$/i;
  // Not `label` or `legend`: those name a form field ("Role Description" over a rich-text box).
  const HEADING_CANDIDATES = "h1, h2, h3, h4, h5, h6, [role=heading], p, div, span, strong, b, dt";
  // PAGE-level chrome only: a `header`/`footer` inside an article, section, aside or main belongs to that
  // section (its own title block, its "Posted 3 days ago"), and is part of the posting.
  const SECTIONED = ":is(article, section, aside, main)";
  const CHROME_SELECTOR = `nav, header:not(${SECTIONED} header), footer:not(${SECTIONED} footer), `
    + "[role=navigation], [role=banner], [role=contentinfo]";
  // The field reader's control rule plus the ARIA widgets that show a value as plain text.
  const FORM_CONTROL = 'input:not([type="hidden"]), select, textarea, button[aria-haspopup], [role="combobox"], '
    + '[role="textbox"], [role="listbox"], [contenteditable]:not([contenteditable="false"])';
  const PAGE_WIDE = /^(html|body|main|article|form)$/i;
  const headingKey = (el) => oneLine(el.textContent).replace(/\s*:$/, "").toLowerCase();

  /** The text under a description heading, for a posting with no JSON-LD and no job-description class.
   *
   * Finds a visible element whose whole text is a description heading, then climbs to the first ancestor
   * with more than 300 characters of text: that ancestor is the description's own section. The climb is
   * ABANDONED (this heading answers nothing) at `main`/`article`/`body`/`form`, because that is the page's
   * text or an application form and not a section; at page-level `nav`/`header`/`footer`, and at an ancestor that
   * CONTAINS site chrome (a page-wide wrapper); at any ancestor holding a form control or an ARIA text
   * widget, so a value the user typed into an application form never rides into a save; and at an
   * ancestor holding the same heading twice, which is a list of cards and not a posting. The first
   * heading in document order that gives a section answers. */
  function descriptionUnderHeading() {
    // An `article` beside another `article` is one card of a posting drawn as cards ("General Information",
    // "Description & Requirements"), not the page's text; the same heading in a sibling makes them a list.
    const cardArticle = (node, heading, key) => node.tagName === "ARTICLE"
      && [...(node.parentElement?.children ?? [])].some((sib) => sib !== node && sib.tagName === "ARTICLE")
      && !headings.some((other) => other !== heading && headingKey(other) === key && node.parentElement.contains(other));
    const found = [...document.querySelectorAll(HEADING_CANDIDATES)].filter((el) => el.childElementCount <= 2
      && el.textContent.length <= 400 && oneLine(el.textContent).length <= 60 && DESCRIPTION_HEADING.test(oneLine(el.textContent))
      && isShown(el) && !el.closest(CHROME_SELECTOR));
    // A heading drawn as `div > span` matches twice; the inner one is the heading.
    const headings = found.filter((el) => !found.some((other) => other !== el && el.contains(other)));
    for (const heading of headings) {
      const key = headingKey(heading);
      for (let node = heading.parentElement; node; node = node.parentElement) {
        if ((PAGE_WIDE.test(node.tagName) && !cardArticle(node, heading, key)) || node.matches(CHROME_SELECTOR) || node.querySelector(FORM_CONTROL)
          || node.querySelector(CHROME_SELECTOR)
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
  const GENERIC_BANNER = /^(careers?|jobs?|open (roles|positions|jobs)|join (us|our team)|work with us)$/i;
  function namedByPage(text) {
    const meta = (property) => oneLine(
      document.querySelector(`meta[property="${property}"]`)?.getAttribute("content")).toLowerCase();
    const lower = text.toLowerCase();
    if (lower === meta("og:site_name") || GENERIC_BANNER.test(text)) return false;
    // A title usually ends with the site ("Senior Data Analyst | Acme Corp"): an h1 equal to that last
    // segment is the site's hero, not the posting.
    const named = [oneLine(document.title).toLowerCase(), meta("og:title")].filter((title) => {
      const parts = title.split(/\s[|\-\u2013\u2014\u00b7:]\s/);
      return title.includes(lower) && !(parts.length > 1 && parts[parts.length - 1] === lower);
    });
    return named.length > 0;
  }

  /** The first visible `h1` outside site chrome that the page's own title names, for a page whose title
   * no recorded adapter gives. */
  function visibleH1Title() {
    const own = (el) => isShown(el) && !el.closest(CHROME_SELECTOR);
    const named = (els) => els.map((el) => oneLine(el.innerText))
      .find((text) => text && text.length <= 200 && namedByPage(text)) ?? "";
    const h1s = [...document.querySelectorAll("h1")].filter(own);
    // A page whose only h1 is the logo's (in the site header) titles the role in an h2 banner.
    return h1s.length ? named(h1s) : named([...document.querySelectorAll("h2")].filter(own));
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
  ns.descriptionText = descriptionText;
  ns.postingHeaderLines = postingHeaderLines;
  ns.usableDescriptionNode = usableDescriptionNode;
  ns.descriptionUnderHeading = descriptionUnderHeading;
})();
