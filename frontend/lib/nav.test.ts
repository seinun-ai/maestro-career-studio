import assert from "node:assert/strict";
import { test } from "node:test";

import { navCurrent } from "./nav.ts";

test("the exact route is the current page", () => {
  assert.equal(navCurrent("/applications", "/applications"), "page");
});

test("a child route marks its section current, not as the page", () => {
  assert.equal(navCurrent("/base-resumes/data_scientist", "/base-resumes"), "true");
});

test("a sibling sharing a prefix is not current", () => {
  assert.equal(navCurrent("/applications-archive", "/applications"), undefined);
});

test("an unrelated route is not current", () => {
  assert.equal(navCurrent("/settings", "/profile"), undefined);
});

test("a job page marks Applications current", () => {
  assert.equal(navCurrent("/jobs/abc", "/applications"), "true");
});

test("a job opened from proposals marks Agent Proposals instead", () => {
  assert.equal(navCurrent("/jobs/abc", "/proposals", "proposals"), "true");
  assert.equal(navCurrent("/jobs/abc", "/applications", "proposals"), undefined);
});

test("the tailor flow follows the job page's section", () => {
  assert.equal(navCurrent("/jobs/abc/tailor/s1", "/applications"), "true");
});

test("a route that only shares the jobs prefix is not Applications", () => {
  assert.equal(navCurrent("/jobsite", "/applications"), undefined);
});
