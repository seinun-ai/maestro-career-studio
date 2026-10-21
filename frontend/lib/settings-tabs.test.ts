import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PROFILE_TABS,
  SETTINGS_TABS,
  anchorHref,
  landingFor,
  parseTab,
  settingsPageAt,
  tabForAnchor,
  tabHref,
} from "./settings-tabs.ts";

test("an absent, repeated or unknown ?tab= reads as the page's first tab", () => {
  assert.equal(parseTab("settings", undefined), "basics");
  assert.equal(parseTab("settings", "nope"), "basics");
  assert.equal(parseTab("settings", "constructor"), "basics", "an own key, not the prototype's");
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

test("Agent apps opens with the connection card, then the folded explainer", () => {
  const agents = SETTINGS_TABS.find((tab) => tab.value === "agents")!;
  assert.equal(agents.label, "Agent apps");
  assert.deepEqual(agents.anchors.slice(0, 2), ["connect-assistant", "connected-agents"]);
  assert.equal(tabForAnchor("settings", "connect-assistant"), "agents");
  assert.equal(anchorHref("/settings", "connect-assistant"), "/settings?tab=agents#connect-assistant");
});

test("an old ?tab= lands on the tab and card that hold what it opened with", () => {
  assert.deepEqual(landingFor("settings", "models"), { tab: "basics", anchor: "api-keys" });
  assert.deepEqual(landingFor("settings", "ai"), { tab: "basics", anchor: "api-keys" });
  assert.deepEqual(landingFor("settings", "tailoring"), { tab: "advanced", anchor: "quick-tailor" });
  assert.deepEqual(landingFor("settings", "appearance"), { tab: "basics", anchor: "appearance" });
  assert.deepEqual(landingFor("settings", ["about", "agents"]), { tab: "basics", anchor: "about" });
  // Still a tab: it opens as it is, with no card to land on.
  assert.deepEqual(landingFor("settings", "agents"), { tab: "agents", anchor: null });
  assert.deepEqual(landingFor("settings", "nope"), { tab: "basics", anchor: null });
  assert.deepEqual(landingFor("settings", "constructor"), { tab: "basics", anchor: null });
  assert.deepEqual(landingFor("profile", "autofill"), { tab: "autofill", anchor: null });
  assert.equal(parseTab("settings", "tailoring"), "advanced");
});

test("every card an old tab held still opens a tab", () => {
  for (const anchor of ["form-filling", "prompts", "quick-tailor", "resumes-folder", "agent-hints", "second-copy"]) {
    assert.notEqual(tabForAnchor("settings", anchor), null, anchor);
  }
  assert.equal(tabForAnchor("settings", "form-filling"), "companion");
  assert.equal(tabForAnchor("settings", "resumes-folder"), "basics");
  assert.equal(tabForAnchor("settings", "prompts"), "advanced");
});

test("a card id resolves to its tab, an id inside the autofill card by prefix", () => {
  assert.equal(tabForAnchor("settings", "api-keys"), "basics");
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
  assert.equal(tabHref("settings", "basics"), "/settings");
  assert.equal(tabHref("settings", "advanced"), "/settings?tab=advanced");
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
