// Skills by role rendered with a seeded read (owner decision D7: a share from 20 in its denominator,
// the counts below). pytest runs it: backend/tests/test_frontend_jobs_honest_analytics.py.
import assert from "node:assert/strict";
import test from "node:test";

import { React, load, renderElement } from "../render-harness.mjs";

const { HeatmapChart } = load("components/charts/heatmap-chart.tsx");

const KEY = ["explore", "heatmap", undefined, 15];
const row = (skill_name, role_category, count, of) => ({
  skill_name, role_category, count, of, pct_jobs: Math.round((count / of) * 10000) / 100,
});

const cells = (html) => [...html.matchAll(/<td\b[^>]*title="([^"]*)"[^>]*>([^<]*)<\/td>/g)].map((m) => [m[1], m[2]]);

test("a role with fewer than 20 jobs shows its counts, and no share", () => {
  const html = renderElement(React.createElement(HeatmapChart), [[KEY, [
    row("python", "data_engineer", 2, 3),
    row("sql", "data_engineer", 3, 3),
    row("python", "data_scientist", 10, 25),
  ]]]);
  assert.deepEqual(cells(html), [
    ["Python · Data Engineer: 2 of 3", "2 of 3"],
    ["Python · Data Scientist: 40%", "40%"],
    ["SQL · Data Engineer: 3 of 3", "3 of 3"],
    // No job in the role asks for it: empty, and the title says what that is against the role's jobs.
    ["SQL · Data Scientist: 0%", ""],
  ]);
  assert.doesNotMatch(html, /67%|100%/);
  // A count cell is not coloured as a share; a share cell is.
  assert.match(html, /title="Python · Data Engineer: 2 of 3" class="[^"]*bg-surface-container-high/);
  assert.match(html, /title="Python · Data Scientist: 40%"[^>]*style="background-color:color-mix/);
  assert.match(html, /A role with fewer than 20 jobs shows its counts, such as 2 of 3\./);
});
