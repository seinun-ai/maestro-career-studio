---
name: customize-job-skills
description: Use when the user wants to adapt any ready-made Maestro CS automation to their agent app and routine, or create a new skill of their own around Maestro CS — batch tailoring, referral-first hunting, a weekly digest, anything the tools can do. Suggests ideas from what you know about the user and their data, asks a few questions, then builds it with whatever skill-making and scheduling this app and computer offer.
metadata:
  title: Make your own
  summary: Builds automations around you, or tunes any card above to your agent app and routine.
  kind: custom
  needs: [maestro]
---

# Customize the job skills

Help the user end up with skills that fit how *they* job-hunt — either their own
version of any ready-made skill (`job-hunt`, `mail-status`, `referral-pages`,
`tailor-run`, `apply-session`; this repo: `backend/app/automations/skills/`,
indexed at `docs/skills/README.md`), or something new built on the Maestro CS tools.

## 1. Look before you ask

Draw on what you already know about the user (your memory of them, past
sessions) and what their data shows: `get_job_search_brief` (preferences,
referral careers pages, role mix), `list_referrals`, `list_applications`,
`list_proposals`, `list_base_resumes`. Role, location, work authorization and
ceilings already live in the brief — never ask for those.

## 2. Offer ideas

Suggest two to four skills that fit this user, grounded in what you found, and
let them pick, tweak, or describe their own. Adapting any ready-made automation
to this app and the user's routine is always an option. Ideas can be anything the
tools support, for example:

- Batch-tailor every saved job above a score, then render the PDFs.
- Hunt only at referral companies, from their careers pages.
- A weekly digest of pipeline status, match score trends and skill gaps (`explore_*`).
- Draft cover letters and Q&A answers for the accepted queue.
- Resume health check and Career KB top-up before a new push.

## 3. Ask only what the chosen skill needs

A few short questions, one at a time — for example: which job sources the agent
can reach; whether it runs on a schedule and when; where digests and "needs
you" alerts go (this chat, Slack, email, …) and whether consent comes from there
too (note that channel for `record_consent`); for apply, the whole queue or pick
each one, and which browser tool.

## 4. Build it

- Keep it short: goal, steps, and the user's preferences. Leave mechanics to the
  tools' own descriptions. Never loosen the guard rails: a new apply run works
  accepted proposals only, and every submit waits for the user's yes for that
  one application. An adapted ready-made automation keeps its own guard rails
  exactly as written.
- Write it with this app's own way of making skills if it has one; otherwise
  save it where this app loads skills from. If you can't save it from here, hand
  over the skill text and tell the user where to add it. An app without skills
  gets a paste-ready prompt instead.
- For a schedule, use a scheduler built into this app if it has one, otherwise
  one available on this computer. If neither works from here, say so plainly,
  tell the user where they could run it on a schedule instead, and hand over the
  prompt to run.
- To adapt a ready-made automation, work from its own prompt: read it here if
  you can, otherwise ask the user to paste it (Copy on its card in Maestro). It
  keeps its steps, its guard rails and the `record_run` automation its steps
  already use (the card id, such as `job-hunt`), so its runs still show on its
  card; change only what fits this app and routine (sources, timing, where
  alerts go).
- End every new automation with one step: call `record_run` with its own name
  (40 characters at most), outcome (`ok`, `partial` or `failed`), and `report`
  with `counts`, `digest` and `job_ids` for the jobs touched, so its runs show in
  Maestro's Agent inbox. Use only non-negative whole-number counts named
  `found`, `proposed`, `skipped`, `tailored`, `updated` or `needs_you`.
- Finish by telling the user what was created, where, and how to run or change it.
