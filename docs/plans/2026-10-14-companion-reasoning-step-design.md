# Companion reasoning step: design

Approved by the owner 2026-10-14, section by section.

## Why

The queued run reasons per field (map, pick, the step agent for widgets, drafted answers) but the run itself is fixed rules: classify the page, fill, press Next, read errors, repair once, else park. Every live check has found a new surprise that a rule did not cover, and each fix has been one more rule. The reasoning step lets the run think about the whole page at the moment it would otherwise stop, act a little, look again, and either carry on or park with a plain note on what it tried.

Pattern: "ask, act, look again". The model decides; the extension acts through its existing, tested code; every safety wall stays in code.

## Owner decisions

- A strong model, used only when the run would otherwise stop ("Reasoning model" setting, default the strong model of the chosen provider; a few cents a round).
- The panel shows a live line while it works and one sentence when it is done; details go to the fill log.
- It may write answers to free-text questions and choose options for questions the profile does not cover, from the profile, career history and resume, all listed under "Check before you submit". It skips an optional essay rather than pad.

## 1. When it runs and what the model sees

**Runs** only where the run would otherwise park on: page errors it could not map, open questions, a page it does not recognise, no change after Next / a loop, or the user moving to another tab. Never on walls (CAPTCHA, email codes, account walls on unknown hosts, a Submit page, protected questions), never when "Stop after each step" is on, and only when "Think when stuck" is on. At most once per page, up to 3 rounds.

**Snapshot** (value-free; built from what the run already reads):
- the stuck reason;
- fields: fid, question, kind/shape, required, filled or empty (never the value), up to 20 options for a choice field;
- error lines, buttons (id, text, role), dialogs;
- the last 8 actions with outcomes;
- which profile answer types exist ("work authorization: present"), never the answers.

All page text is untrusted data: wrapped, datamarked (spotlighting) and stripped of invisible Unicode (Cf/Co/Cn) before it reaches the model. Reply: JSON with a short plain-words note and 1–3 actions.

## 2. Actions and limits

| Action | Effect | Built on |
|---|---|---|
| `fill(fids)` | Normal fill of those fields | `runFill({only})` |
| `answer_from(fid, slot)` | Re-map a field to a profile answer type; `/pick` chooses | `/pick` |
| `write(fid)` | Short answer from profile + history, in the owner's voice; essays only when required | drafting step, new short mode |
| `choose(fid, option)` | Option for a question the profile does not cover, per the safe-default rule and history | `/pick` low-stakes / keen |
| `retry(fid, technique)` | open-and-pick / type-and-pick / search / clear-and-set | fill-loop techniques |
| `redo(fid)` | Clear and refill a field the run filled (never one the user touched) | fill memory + `touched` |
| `close_dialog(button)` | Dismiss a popup; Submit-worded refused at click time | page reader |
| `press_next(button)` | Press Next under the existing rules (never Submit) | `page_advance` |
| `follow_tab(tab)` | Move the run to an open tab already confirmed as this job's application | Phase 2e follow |
| `ask_user(fids, note)` | Park with a plain note naming what the user must do | existing park card |

Values always come from the profile, history and resume through the existing answer rules; page text is only the question. Never answered by the model: work authorization, sponsorship, salary, EEO / self-identification, criminal or background history, signatures and legal attestations, licences, and any fact the profile lacks (dates never given, certificates not held) — those become `ask_user`. A written answer containing a link, email or phone number that is not the owner's is rejected.

**Limits, in code:** 3 rounds, 3 actions per round, about 60 s per page. Every id must exist in the snapshot it was sent; the backend rejects anything else and a rejected reply becomes `ask_user`. An action whose signature (action + target → outcome) failed twice is no longer offered. A field with "no effect" twice is dropped. A round that leaves the page fingerprint unchanged stops the loop.

## 3. What the user sees and what is recorded

- **Live line** in the run card from the model's note and the current action ("Thinking: Field of Study looks filled, the error is on Degree…", "Answering Degree…", "Pressing Save and Continue…").
- **Done:** one sentence if the run moved on ("Sorted it out: answered 2 questions and moved on."); otherwise the park card with the model's note and one line on what it tried.
- **Check before you submit** lists everything it wrote, chose or redid, marked "answered for you".
- **Settings:** "Think when stuck" (on by default) and "Reasoning model".
- **Fill log:** a run-level `reasoning` list, one entry per round: why, model, time, note, chosen actions with outcomes, rejected replies. Never values; a written answer is recorded as written plus its length.

## 4. Build and test

**Backend:**
- `POST /api/autofill/reason`: request is the snapshot plus stuck reason; the server adds answer level, protected list and answer-type presence; calls the Reasoning model with a strict JSON schema built from pydantic action models (`TypeAdapter` validation; discriminated union); validates every action (allowed list, ids in snapshot, protected rules, failed signatures); invalid → `ask_user`. Own ~25 s budget; the panel calls it directly, not through the service worker.
- `write` reuses drafting with a short factual mode plus the link/email/phone check; the value goes to the panel only.
- `choose` reuses `/pick` with the safe-default rule.
- Settings: `think_when_stuck`, `reasoning_model`; frontend Settings controls.
- Provider notes (freshness check 2026-10-14): Anthropic enforces the schema (`output_config.format`); the app's OpenAI path sends `json_object` and Gemini/OpenRouter enforcement varies by model, so server-side validation is mandatory for every provider.

**Extension:**
- `shared/reason-loop.js`: rounds, guards (action signatures, per-field no-effect counter, page fingerprint), executes only through existing host ops.
- `queue-run.js`: before an eligible park, run the loop; moved → continue; else park with the note.
- Panel: live line, summary, Check-before-you-submit rows; trace `reasoning` list in the `RunTrace` schema and `buildRunTrace`.

**Sources (design references only, nothing vendored):** Nanobrowser `src/agent/guards.ts` (Apache-2.0; signature + no-effect counters), browser-use `ActionLoopDetector` / `PageFingerprint` (MIT; same-page detection), Microsoft spotlighting (arXiv 2403.14720), LLM Guard `invisible_text.py` (MIT; Cf/Co/Cn filter). Credited in `THIRD_PARTY_NOTICES.md`.

**Tests:**
- Backend: checker rejects unknown ids, off-list actions, protected targets and failed signatures; the write post-check; prompt marks page text as data and strips invisible characters; recorded model replies replayed offline.
- Driver with a scripted fake reasoner: every eligible park enters the loop, walls never do; round, repeat, no-effect and same-page limits each stop it; timeout falls back to the normal park; Submit never pressed; off when "Stop after each step" or "Think when stuck" is off.
- Browser end to end: a Workday-style fixture with an error the deterministic repair cannot map; the stub reasoner answers it and the page moves on.
- Live check with the fill log on to measure time and cost per round.

**Order:** backend endpoint and checker → reason loop and limits → driver hook → panel and settings → fill log → docs. One builder per batch, review after each, full gate, live app update.
