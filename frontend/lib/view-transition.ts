/**
 * The names the Jobs row and the job page give the one pair that morphs between them (design refresh Task 4.5):
 * the company's monogram and the job's title, named from the job id so only the same job's pair finds each other.
 * A `view-transition-name` is a CSS identifier: the id keeps only the characters one allows. No imports: `node
 * --test` loads this file as it is.
 */
export function morphName(jobId: string, part: "monogram" | "title"): string {
  return `job-${part}-${jobId.replace(/[^A-Za-z0-9_-]/g, "")}`;
}
