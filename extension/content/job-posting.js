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

  ns.findJobPosting = findJobPosting;
  ns.findJobPostingInDocument = findJobPostingInDocument;
})();
