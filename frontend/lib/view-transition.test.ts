import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isBackToJobsList,
  jobsListLeft,
  leaveJobsList,
  morphName,
  returnToJobsList,
  takeJobsListReturn,
} from "./view-transition.ts";

test("a pair is named from the job id, one name per part", () => {
  const id = "3f2a1b4c-0000-4000-8000-000000000001";
  assert.equal(morphName(id, "monogram"), `job-monogram-${id}`);
  assert.equal(morphName(id, "title"), `job-title-${id}`);
  assert.notEqual(morphName(id, "title"), morphName("another", "title"));
});

test("only identifier characters reach the name", () => {
  assert.equal(morphName("a b/c.d", "title"), "job-title-abcd");
});

test("only a job page going back to the Jobs list is the way back", () => {
  assert.equal(isBackToJobsList("/jobs/3f2a", "/applications"), true);
  // Either side may carry a query: the job's step, the list's filters.
  assert.equal(isBackToJobsList("/jobs/3f2a?tab=fit", "/applications?status=closed"), true);
  // The pair is only in the job page's header and the list's rows.
  assert.equal(isBackToJobsList("/jobs/3f2a/tailor", "/applications"), false);
  assert.equal(isBackToJobsList("/jobs/3f2a", "/proposals"), false);
  assert.equal(isBackToJobsList("/today", "/applications"), false);
  assert.equal(isBackToJobsList("/applications", "/applications?status=closed"), false);
});

test("the list puts its scroll back once, and only after a return", () => {
  // Never left in this tab (a reload, a job opened on its own): nothing to put back, and the browser restores it.
  assert.equal(jobsListLeft(), false);
  assert.equal(takeJobsListReturn(), null);
  // Back to Jobs on such a page still returns: the list opens at the top.
  returnToJobsList();
  assert.equal(takeJobsListReturn(), 0);

  leaveJobsList(640);
  assert.equal(jobsListLeft(), true);
  // Left for another page and opened again by a link: no return, so the list keeps its usual top.
  assert.equal(takeJobsListReturn(), null);
  returnToJobsList();
  assert.equal(takeJobsListReturn(), 640);
  assert.equal(takeJobsListReturn(), null);
});
