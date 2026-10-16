# Companion live check 9 fixes (Phase 2j) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what a Greenhouse and a Rippling run showed (2026-10-15): the fast model (Claude Haiku) misses its second-opinion time limits, so safe answers are lost; a referral question never reached the safe-default check; a background-check willingness question was filed as protected; two start-date facts compete; a veteran option with a clear "I am not…" was left; a correct searched pick was flagged; a resume that was attached was reported "couldn't attach"; optional fields left blank never appear on the Ready card.

Owner's principle (restated): one question the run can't answer never stops the others; everything not answered is listed.

Diagnosis notes are local only (scratchpad diag-live9.md with extracts in live9/).

## Batch AE — answers (backend)
- **AE1 budgets:** second-opinion floors fit the configured fast model (polarity and map second opinion get at least ~2.5–3 s when the request budget allows; the timeout given is logged); the map trace records the top fact even when under its floor.
- **AE2 low-stakes reach:** a field whose top answer is "no fact" at any p goes to the low-stakes judge unless a second opinion named a fact; a `protected_unanswered` field goes to the judge only when code matches a pre-employment-step willingness question (willing/consent/agree/able to undergo + background check / drug test / reference check / I-9 / E-Verify, never ever/convicted/charged/record).
- **AE3 start date:** when a derived start date exists, /map is offered one start-date fact (the derived date).
- **AE4 veteran in code:** saved No + exactly one option opening with a negation and naming a veteran → picked by code in /pick and /step before polarity; "I am a veteran, but not a protected veteran" never; saved Yes unchanged.
Tests per the diagnosis.

## Batch AF — page side (extension)
- **AF1 upload proof:** keep the chain of upload ancestors (up to ~6 levels) and count file rows in the deepest one still in the page; a written box that left the page with the count falling by exactly that box reads "Couldn't confirm", never "boxes changed"; targeted attach passes `expect` (bug: undefined). Rippling-style: wait longer while the widget shows progress (aria-busy, progress bar, uploading/parsing words), accept the filename stem or a shortened form by prefix and suffix.
- **AF2 searched pick proof:** when the shown text differs from the option (a flag + "+1"), reopen and read the selected option (`*__option--is-selected` or `aria-selected="true"`); if it is the option /pick chose (or equals the value) → verified. Text equality with the saved value stays the first check.
- **AF3 Ready card lists optional fields left blank** ("Left blank — optional") alongside Left for you; never a park.
- **AF4 follow-up label:** a follow-up ("If applicable, … referring employee") joins the earlier question sharing its key noun, not simply the nearest control.
Tests per the diagnosis with Acme fixtures.

## Batch AG — docs and gate
`docs/entities/others.md` (floors by provider, `Budget` keep/late_ok, the Jev-judge and years-check bounds, `top_fact`, the low-stakes reach, one start date, the veteran pick in code), SYSTEM.md §7/§6/§12 (condensed to stay at 997 lines), `extension/INTERNALS.md` (second-opinion floors, `ns.uploadProof` and the hedged-or-changed rule, the list-proof of a searched pick, the follow-up label rule, "Left blank — optional" rows, the `top_fact` whitelist), CHANGELOG (one "Eighth live check" entry), USING_MAESTRO, the extension README. Gate as before. Review fixes that landed after the first build: AE (815132b7: narrow willingness reading, doubt guard on a below-floor none, decline options never a veteran pick, Claude floor by provider; 86190d35: Jev judge skipped under 2 s, years check bounded) and AF (19a086db, e7d008c4, 287d576b).

## Order: AE and AF in parallel.
