/**
 * A template's own state, in words the gallery and the editor share. Pure, so `node --test` runs it
 * (`template-status.test.ts`).
 */

/**
 * The server's reason for a LaTeX template on a computer without TeX (`template_validation.REQUIRES_TEX`,
 * pinned equal by `test_frontend_resume_review.py`). Nothing is wrong with the template itself: the Needs
 * setup badge says what is missing.
 */
export const REQUIRES_TEX_REASON = "requires TeX (pdflatex not found)";

/** A template whose last check found a problem in the template, not a missing TeX. */
export function templateHasErrors(template: { last_error: string | null }): boolean {
  return Boolean(template.last_error) && template.last_error !== REQUIRES_TEX_REASON;
}

/** What the editor says when the preview can't be made because TeX is missing. */
export const NEEDS_TEX_WORDS =
  "This template needs TeX, which isn't installed on this computer, so its preview can't be made here.";
