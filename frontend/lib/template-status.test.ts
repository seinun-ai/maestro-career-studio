import assert from "node:assert/strict";
import { test } from "node:test";

import { REQUIRES_TEX_REASON, templateHasErrors } from "./template-status.ts";

test("a template missing only TeX has no errors; any other reason is an error", () => {
  assert.equal(templateHasErrors({ last_error: REQUIRES_TEX_REASON }), false);
  assert.equal(templateHasErrors({ last_error: null }), false);
  assert.equal(templateHasErrors({ last_error: "" }), false);
  assert.equal(templateHasErrors({ last_error: "render error: Undefined control sequence" }), true);
});
