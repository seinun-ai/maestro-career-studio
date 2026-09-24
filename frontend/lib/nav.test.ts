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

test("a job page marks Jobs current", () => {
  assert.equal(navCurrent("/jobs/abc", "/applications", null), "true");
});

test("a job opened from the Agent inbox marks it instead", () => {
  assert.equal(navCurrent("/jobs/abc", "/proposals", "proposals"), "true");
  assert.equal(navCurrent("/jobs/abc", "/applications", "proposals"), undefined);
});

test("the tailor flow follows the job page's section", () => {
  assert.equal(navCurrent("/jobs/abc/tailor/s1", "/applications", null), "true");
});

test("a route that only shares the jobs prefix is not Jobs", () => {
  assert.equal(navCurrent("/jobsite", "/applications", null), undefined);
});

test("a job page whose `from` is not known yet marks no section", () => {
  // The Suspense fallback: marking Jobs would be wrong for a job
  // opened from proposals, so it marks nothing until the params are read.
  for (const href of ["/applications", "/proposals", "/referrals"]) {
    assert.equal(navCurrent("/jobs/abc", href), undefined);
    assert.equal(navCurrent("/jobs/abc/tailor/s1", href), undefined);
  }
});

test("every other route marks the same item whether or not `from` is known", () => {
  const routes = ["/applications", "/proposals", "/base-resumes/x", "/new", "/settings", "/jobsite"];
  const hrefs = ["/new", "/applications", "/proposals", "/base-resumes", "/settings"];
  for (const pathname of routes) {
    for (const href of hrefs) {
      const known = navCurrent(pathname, href, null);
      assert.equal(navCurrent(pathname, href), known, `${pathname} ${href}`);
      assert.equal(navCurrent(pathname, href, "proposals"), known, `${pathname} ${href}`);
    }
  }
});
