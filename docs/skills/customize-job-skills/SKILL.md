---
name: customize-job-skills
description: Use when the user wants to personalize the Maestro CS job-hunt or apply-session skill, or create a new skill of their own around the app — batch tailoring, referral-first hunting, a weekly digest, anything the tools can do. Suggests ideas from what you know about the user and their data, asks a few questions, then builds it with the client's skill creator and scheduler.
---

# Customize the job skills

Help the user end up with skills that fit how *they* job-hunt — either their own
version of the ready-made `job-hunt` and `apply-session` skills (this repo:
`docs/skills/`), or something new built on the Maestro CS tools.

## 1. Look before you ask

Draw on what you already know about the user (your memory of them, past
sessions) and what their data shows: `get_job_search_brief` (preferences,
referral careers pages, role mix), `list_referrals`, `list_applications`,
`list_proposals`, `list_base_resumes`. Role, location, work authorization and
ceilings already live in the brief — never ask for those.

## 2. Offer ideas

Suggest two to four skills that fit this user, grounded in what you found, and
let them pick, tweak, or describe their own. The ready-made pair is always an
option. Ideas can be anything the tools support, for example:

- Batch-tailor every saved job above a score, then render the PDFs.
- Hunt only at referral companies, from their careers pages.
- A weekly digest of pipeline status, ATS trends and skill gaps (`explore_*`).
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
  tools' own descriptions. Never loosen the guard rails — apply runs work
  accepted proposals only, and every submit waits for the user's yes for that
  one application.
- Write it with the client's own skill-creation tool if it has one; otherwise
  save it where the client loads skills (Claude Code:
  `~/.claude/skills/<name>/SKILL.md`). A client without skills gets a
  paste-ready prompt instead.
- For a schedule, use the client's scheduler (Claude Code: `/schedule`;
  otherwise the client's scheduled tasks). No scheduler — say so and hand over
  the prompt to run.
- Finish by telling the user what was created, where, and how to run or change it.
