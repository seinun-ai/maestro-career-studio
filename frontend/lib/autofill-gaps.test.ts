import assert from "node:assert/strict";
import { test } from "node:test";

import { FILL_LOG_OFF_TEXT, gapsLine } from "./autofill-gaps.ts";

const summary = (kinds: number, sites: number, user_fixed: number) => ({ kinds, sites, user_fixed, top: [] });

test("the line counts kinds, sites and the ones you fixed", () => {
  assert.equal(
    gapsLine(summary(4, 3, 2)),
    "Fields the Companion couldn't operate: 4 kinds on 3 sites, 2 fixed by you.",
  );
});

test("one kind on one site reads in the singular", () => {
  assert.equal(
    gapsLine(summary(1, 1, 0)),
    "Fields the Companion couldn't operate: 1 kind on 1 site, 0 fixed by you.",
  );
});

test("with no rows the line says how to turn the fill log on, as the coverage card does", () => {
  assert.equal(gapsLine(summary(0, 0, 0)), FILL_LOG_OFF_TEXT);
  assert.match(FILL_LOG_OFF_TEXT, /^No data yet\. The fill log is off unless you turn it on\./);
  assert.match(FILL_LOG_OFF_TEXT, /Options, and tick Keep a fill log\.$/);
});
