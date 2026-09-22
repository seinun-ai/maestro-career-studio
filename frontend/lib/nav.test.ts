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
