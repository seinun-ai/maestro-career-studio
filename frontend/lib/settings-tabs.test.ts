import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PROFILE_TABS,
  SETTINGS_TABS,
  anchorHref,
  parseTab,
  settingsPageAt,
  tabForAnchor,
  tabHref,
} from "./settings-tabs.ts";

test("an absent, repeated or unknown ?tab= reads as the page's first tab", () => {
  assert.equal(parseTab("settings", undefined), "models");
  assert.equal(parseTab("settings", "nope"), "models");
  assert.equal(parseTab("settings", "agents"), "agents");
  assert.equal(parseTab("profile", ["autofill", "you"]), "autofill");
  assert.equal(parseTab("profile", null), "you");
});

test("every anchor belongs to exactly one tab", () => {
  for (const tabs of [SETTINGS_TABS, PROFILE_TABS]) {
    const all = tabs.flatMap((tab) => [...tab.anchors]);
    assert.equal(new Set(all).size, all.length);
  }
});

test("a card id resolves to its tab, an id inside the autofill card by prefix", () => {
  assert.equal(tabForAnchor("settings", "api-keys"), "models");
  assert.equal(tabForAnchor("settings", "agent-hints"), "agents");
  assert.equal(tabForAnchor("settings", "connected-agents"), "agents");
  assert.equal(tabForAnchor("profile", "autofill"), "autofill");
  assert.equal(tabForAnchor("profile", "autofill-work_auth"), "autofill");
  assert.equal(tabForAnchor("profile", "persona"), "you");
  assert.equal(tabForAnchor("profile", "main-content"), null);
  assert.equal(tabForAnchor("settings", ""), null);
  assert.equal(tabForAnchor("profile", "not-autofill-x"), null, "a prefix, not a substring");
});

test("hrefs name the tab only when it is not the default", () => {
  assert.equal(tabHref("settings", "models"), "/settings");
  assert.equal(tabHref("settings", "about"), "/settings?tab=about");
  assert.equal(tabHref("profile", "autofill", "autofill-eeo"), "/profile?tab=autofill#autofill-eeo");
  assert.equal(anchorHref("/settings", "api-keys"), "/settings#api-keys");
  assert.equal(anchorHref("/settings", "agent-hints"), "/settings?tab=agents#agent-hints");
  assert.equal(anchorHref("/profile", "job-preferences"), "/profile#job-preferences");
  assert.equal(anchorHref("/profile", "autofill-work_auth"), "/profile?tab=autofill#autofill-work_auth");
  assert.equal(anchorHref("/career", "kb-entities"), "/career#kb-entities");
});

test("only /settings and /profile are tabbed pages", () => {
  assert.equal(settingsPageAt("/settings"), "settings");
  assert.equal(settingsPageAt("/profile"), "profile");
  assert.equal(settingsPageAt("/career"), null);
  assert.equal(settingsPageAt("/settings/x"), null);
});
