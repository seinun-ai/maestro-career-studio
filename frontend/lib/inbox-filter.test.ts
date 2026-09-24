import assert from "node:assert/strict";
import { test } from "node:test";

import { boardHost, chosenScore, filterProposals } from "./inbox-filter.ts";

const job = {
  company: "Acme",
  title: "Data Scientist",
  role_category: "data_scientist",
  source_url: "https://boards.greenhouse.io/acme/1",
};
const p = (over: Record<string, unknown> = {}) => ({
  fit_json: { chosen_base: "ds", scores: { ds: 72 } } as Record<string, unknown> | null,
  job,
  ...over,
});
const all = { q: "", role: "all", board: "all", minScore: null };

test("no filter keeps every row", () => {
  assert.equal(filterProposals([p(), p()], all).length, 2);
});

test("search matches company or title, case-insensitively, trimmed", () => {
  const rows = [p(), p({ job: { ...job, company: "Beta", title: "ML Engineer" } })];
  assert.equal(filterProposals(rows, { ...all, q: "  acme " }).length, 1);
  assert.equal(filterProposals(rows, { ...all, q: "ENGINEER" }).length, 1);
  assert.equal(filterProposals(rows, { ...all, q: "zzz" }).length, 0);
  assert.equal(filterProposals(rows, { ...all, q: "   " }).length, 2);
});

test("search survives a job with no company or title", () => {
  const rows = [p({ job: { ...job, company: null, title: null } })];
  assert.equal(filterProposals(rows, { ...all, q: "acme" }).length, 0);
});

test("a score floor drops rows below it and rows with no score", () => {
  const rows = [
    p(),
    p({ fit_json: { chosen_base: "ds", scores: { ds: 40 } } }),
    p({ fit_json: null }),
    p({ fit_json: { chosen_base: "ds", scores: { ds: 70 } } }),
  ];
  assert.equal(filterProposals(rows, { ...all, minScore: 70 }).length, 2);
});

test("role and board compare keys and hosts", () => {
  assert.equal(filterProposals([p()], { ...all, role: "ml_engineer" }).length, 0);
  assert.equal(filterProposals([p()], { ...all, role: "data_scientist" }).length, 1);
  assert.equal(filterProposals([p()], { ...all, board: "boards.greenhouse.io" }).length, 1);
  assert.equal(filterProposals([p()], { ...all, board: "jobs.lever.co" }).length, 0);
});

test("the helpers never throw on odd input", () => {
  assert.equal(chosenScore({ fit_json: { chosen_base: 3 } }), null);
  assert.equal(chosenScore({ fit_json: { chosen_base: "ds", scores: { ds: "72" } } }), null);
  assert.equal(chosenScore({ fit_json: null }), null);
  assert.equal(boardHost("not a url"), null);
  assert.equal(boardHost(null), null);
});
