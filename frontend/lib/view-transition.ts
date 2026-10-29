/**
 * The names the Jobs row and the job page give the one pair that morphs between them (design refresh Task 4.5):
 * the company's monogram and the job's title, named from the job id so only the same job's pair finds each other.
 * A `view-transition-name` is a CSS identifier: the id keeps only the characters one allows. No imports: `node
 * --test` loads this file as it is.
 */
export function morphName(jobId: string, part: "monogram" | "title"): string {
  return `job-${part}-${jobId.replace(/[^A-Za-z0-9_-]/g, "")}`;
}

/** A popstate from a job page to the Jobs list: the way back the pair morphs on. Either url may carry a query. */
export function isBackToJobsList(from: string, to: string): boolean {
  const path = (url: string) => url.split(/[?#]/)[0];
  return /^\/jobs\/[^/]+$/.test(path(from)) && path(to) === "/applications";
}

/*
 * The way back. The pair morphs back only onto a row in the viewport, so the list opens where it was left, and it
 * keeps that place itself: Back to Jobs is a link, and the browser's own restore lands on the job page (the leave
 * guard holds that popstate for one task, components/leave-guard-listeners.tsx). Module state: one tab, one list,
 * and a reload starts clean.
 */
let listScroll: number | null = null;
let returning = false;

/** The Jobs list is leaving: where it was scrolled. */
export function leaveJobsList(scrollY: number): void {
  listScroll = scrollY;
}

/** Whether the Jobs list was left in this tab, so a return has a place to put back. */
export function jobsListLeft(): boolean {
  return listScroll !== null;
}

/** A job page is going back to the Jobs list. */
export function returnToJobsList(): void {
  returning = true;
}

/** The list's rows are on screen: after a return, the scroll to put back (the top when it was never left), once. */
export function takeJobsListReturn(): number | null {
  if (!returning) return null;
  returning = false;
  return listScroll ?? 0;
}
