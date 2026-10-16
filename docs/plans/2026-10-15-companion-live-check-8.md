# Companion live check 8 fixes (Phase 2i) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** (A) read job descriptions on hosted career sites that draw sections as sibling cards with headings like "Description & Requirements"; (B) fill application forms built from web components whose fields live in open shadow roots, and never park "Page not recognised" on a page that has fields to fill (owner: "when I am there the autofill should work").

Safety rules unchanged: Submit never pressed; parser upload boxes never written; value-free traces. Diagnosis notes are local only.

## Batch AB — posting read (extension/content/job-posting.js only)
AB1 heading measured on normalised text (raw prefilter 400, normalised ≤ 60); "Description & Requirements" / "and" / "Job Description & Qualifications" forms added (narrow list — never bare "Description", "Responsibilities", "Requirements"); sibling-article cards are sections (a lone article still the page; sibling articles repeating one heading still a list); h2 banner title only when the page has no shown non-chrome h1. Tests per the diagnosis with an Acme role-detail fixture. INTERNALS "Save job" + CHANGELOG line.

## Batch AC — shadow DOM (extension)
AC1 one shared deep-query helper (light DOM query plus open shadow roots) used by `fillableControls`, the page reader's summary buttons, submitSeen, collectRequired, fieldForms, password/code boxes, re-tag and button lookups, error regions; composed-ancestor `closest` for inChrome/overlayOf/inFormOf; a shadow button's label read from its slot's assigned text. All of these land together (no false Ready).
AC2 the owner's rule: an `unknown` page at step 0 that the run has not filled asks the inventory for a field count before parking; with fields it is filled (then review/fields_no_next handling). A parity test pins `fillableControls() > 0` exactly when the inventory lists a field.
AC3 uploads in shadow roots: deep query + composed ancestors in agent.js upload reading; recorded markers — an upload inside an "easy apply"/parser container (SmartRecruiters `oc-easy-apply` / `[data-test="easy-apply-container"]`) is a parser and never written; inside `oc-resume-upload` / `[data-test="resume-upload-container"]` is the resume box.
AC4 detectPage sees shadow forms (panel `hasForm` honest).
AC5 DataDome challenge (`captcha-delivery.com`) reads as a CAPTCHA wall (no model call).
Tests per the diagnosis with an Acme shadow fixture (`shadow_one_page_form.html`).

## Batch AD — docs and gate
INTERNALS (shadow DOM reading, owner's rule guard, parser markers, DataDome), SYSTEM.md, CHANGELOG, USING_MAESTRO. Gate as before.

## Order
AB and AC in parallel (different files; AC owns agent.js, AB owns job-posting.js). AD after review.
