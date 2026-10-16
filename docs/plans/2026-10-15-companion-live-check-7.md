# Companion live check 7 fixes (Phase 2h) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what a one-page Greenhouse application showed (2026-10-15): an extension update under an open tab broke the page reader ("Page not recognised"); the reasoning step never runs on one-page forms; typed searches emptied fixed dropdown lists (Degree, Veteran status); a model timeout left a known answer (relocate) for the user; Location (City) search didn't match; an optional field that failed was never mentioned.

**Owner decision (2026-10-15):** on a one-page form (Submit on the same page) the reasoning step may work on fields only — fill, re-map, write, choose, retry (incl. step by step), redo — and never press anything there (no Next, no Submit, no dialog button). It still stops on any submit dialog.

Diagnosis notes are local only.

---

## Batch Y (extension)
- **Y1 version skew:** page-reader never depends on a newer export of a load-once module (own copy or fallback for ERROR_HEADING, pinned equal); a static test over the manifest's content scripts fails when a re-run file reads, without a fallback, an `ns.X` published only by a load-once file; frames that answered with an error park a new reason with the card "The Companion was updated while this page was open. Reload the page, then press Resume."; Greenhouse one-page fixture (Acme) proves the page is filled at step 0. Tests per the diagnosis.
- **Y2 reasoning on one-page forms (owner decision):** `parkOr` and `walled()` allow `open_questions` and `page_errors` on a review page with no submitContext and no dialog; on such a page every press action (press_next, close_dialog) is refused in the loop and the backend is told the page is a one-page form so the prompt never offers presses. Tests: review page with open questions calls the reasoner; any press refused; submitContext still walls.
- **Y3 empty typed search:** when a typed search empties a search box, explore once more without a term before handing to `/step`; a complete list goes to `/pick`; the word fallback strips apostrophes and plurals. Browser test on a react-select fixture where the saved value matches no option text.
- **Y4 Left for you:** an optional field with a saved answer that ended unanswered is listed on the card as a non-blocking "Left for you" line (never a park). Test.
- **Y5 Location search:** a city field searches "City, State" from the profile; offered options are kept in the trace (value-free rules apply). Test.

## Batch Z (backend)
- **Z1 one-page reasoning:** `/reason` accepts a `one_page` flag (or stuck reason) and never offers or allows press actions then; checker test.
- **Z2 relocate:** polarity second opinion retries once or falls back to the other configured provider on a provider error; a code rule answers Yes for "located in … and/or willing to relocate" with a saved yes. Tests.
- **Z3 degree type:** a rule beside `derived.education_level` maps the saved degree to a generic degree-type option ("Master's Degree" for Masters/MS/M.S./M.Sc; MBA only when the saved degree says Business Administration/MBA; same for Bachelor's/Associate's/Doctorate); abstains when ambiguous. Tests incl. the Greenhouse list.
- **Z4 city match:** a Places-style option matches when its first comma part equals the saved city and the rest names the saved state (abbreviation or full name); reported matched. Tests.

## Batch AA: docs and gate
INTERNALS, SYSTEM.md (§7 one-page reasoning; §12 gotcha: updating main under an open Chrome tab), CHANGELOG, USING_MAESTRO (reload open job tabs after an update). Gate as before.

## Order
Y and Z in parallel (Y2 matches Z1's flag name: `one_page`). AA after review.
