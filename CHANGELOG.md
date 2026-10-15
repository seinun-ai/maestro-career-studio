# Changelog

All notable changes to Maestro CS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Versioning policy, stated honestly for 0.x

Maestro CS follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html),
with the qualification that version 0 actually carries:

- **Before 1.0, a breaking change may land in a minor version** (`0.2.0`) — that
  is what SemVer's major-zero clause permits, and pretending otherwise would
  mean either a dishonest changelog or a `4.0.0` by winter.
- **Every one of them is listed under a `### Breaking changes` heading.** That
  heading is the contract: if a release has one, read it before updating; if it
  does not, the update is a normal one.
- **Migrations only run forward.** The backend applies `alembic upgrade head` at
  boot. Downgrade functions exist in the migration files but have never been a
  supported path — rolling back means the old git ref, the old images, and the
  backup `scripts/update.sh` took before it started, together.
  [`docs/UPDATING.md`](docs/UPDATING.md#rolling-back) has that recipe.
- **Patch releases (`0.1.1`) never change the schema or the `.env` contract.**
  They are safe to take without reading anything.

Version numbers appear in eight places that must agree — the git tag (`v0.2.0`)
and seven files listed in [`docs/RELEASING.md`](docs/RELEASING.md). The published
image tag is the same version with the leading `v` removed (`0.2.0`).

## [Unreleased]

The Companion used to fill one page and wait for you to click through the rest. Turn on full
automation and the Job step now has an **Apply** button that takes one job through its whole
application in the tab you are on: it fills a page, clicks Next, fills the next, and stops on the
review page. Submit is still your click, at every setting. One job at a time for now, and a Queue
view for several is still ahead.

### Breaking changes

- **`PUT /api/settings/autofill-options` takes `{"answer_level": …}` now.** The old
  `{"low_stakes": …}` body is refused with a 422. The Settings page and the Job Search Brief already
  use the new field.
- **Veteran status is one Yes/No question now.** Profile › Autofill asks "Are you a veteran?" with
  Yes, No and "I don't wish to answer". Your old "Veteran" answer reads as Yes. The old "Not a
  protected veteran" answer is gone: it was true of a veteran who is not protected, so it cannot
  answer this question. It reads as unanswered, Profile asks you again, and until you do the
  Companion leaves veteran questions on a form for you. A No answers every "I am not a protected
  veteran" option. A Yes never picks a protected class for you. If your second copy has not been
  updated, it reads a synced Yes or No as "I don't wish to answer", so update the always-on copy at
  the same time as your laptop.

### Added

- **Think when stuck: a stronger model looks before a run gives up.** A run used to stop the moment a page did something it had no rule for.
  A Next refused over a name no field carries, a question nobody saved an answer for, a page it did not recognise. Every live check found one
  more, and every fix was one more rule. Now the Companion asks a model to look at the page once first. Submit is still your click.
  - **When it runs.** Before a run parks on page errors it could not map, open questions, an unknown page, no change after Next, a loop or a
    tab on another site, with full automation On, **Think when stuck** On (Settings › AI & models › Form filling, default On) and **Stop after each
    step** Off. Once per page, up to three rounds, about a minute. Never on a CAPTCHA, an email code, an account on a site it does not know, a
    review page or a page that asks about submitting.
  - **What it sees and does.** A snapshot of the page with no answer in it: the questions, whether each is filled, the options, the buttons, the
    errors. It picks one to three actions from a fixed list (fill, answer from a saved answer, write a short answer, choose an option, retry a field
    another way, redo a field the run filled, close a popup, press Next, follow the application's tab, ask you). The Companion carries them out with the code
    it already has and looks again. The model never types a value: what is written comes from your profile, history and resume under the same rules
    as any answer. Work authorization, sponsorship, salary, EEO, background history, signatures, licences and any fact you never gave are left to you.
    It never presses Submit and presses Next only on the button the page reader names.
  - **What you see.** A live line while it works ("Thinking: …"), one sentence if it sorted the page out ("Sorted it out: answered 2 questions and moved
    on."), or the park card with its note, what it asks of you and a "Tried:" line. What it wrote or chose is listed under **Check before you submit** as
    answered for you.
  - **Reasoning model** (Settings › AI & models). Any model in the list; unset, it is the strong model of your provider (Claude Sonnet 5.5, GPT-6.1 Sol), or
    your smart model for other providers. Claude Haiku 5.5 and GPT-6 Luna are listed as cheaper choices.
  - **Fill log.** With the fill log on, each step is recorded as a run of its own: the model, time, its note, each action and outcome (a written answer as
    its length) and the page snapshot it saw. `scripts/eval_reason.py` replays those snapshots against other models and prints the valid and ask-you rates,
    latency, tokens and a cost estimate. `scripts/fill_trace.py last` prints the rounds.
  - **Backend.** `POST /api/autofill/reason` (the Companion's origin only; every reply is checked in code against the snapshot's ids, the protected list
    and failed actions before the extension sees it). Settings `think_when_stuck` (`GET/PUT /api/settings/companion-apply`) and `reasoning_model`.
- **Apply on the Companion's Job step** (needs full automation On). It saves the job, settles the
  resume (it never replaces a tailored draft or an open tailoring session), queues the job as your
  yes, then drives the tab from the job's apply link to the review page. It never clicks Submit and
  it presses Next only when the button reads like Next. A page with any Submit wording, a dialog
  asking about submitting, a CAPTCHA, an email code, an account on a site it does not know or a job
  board's own apply button stops the run and the panel says why. You fix it in the page and press
  **Resume**.
- **Add job beside Apply.** On a job page you have not saved yet, the Job step shows **Add job**
  next to **Apply**: it saves the job and scores your resumes, then stops on the ranked list without
  tailoring, queueing or running anything.
- **Your answers are remembered.** Whatever you type into a field while a run waits for you is saved
  to your profile when you press Resume, with an Undo. A written answer that names the job's company
  or city is kept for that job only: the same question at another job adds its own answer instead of
  replacing it, and Settings has **Use for every job** to drop the limit.
- **Marked applied after your Submit.** When the confirmation page shows, the panel marks the job
  applied after 8 seconds unless you press Undo. This is recorded as the Companion seeing your
  Submit, on its own consent channel (`companion`), and clicks nothing. It only believes a
  confirmation on the application's own site, straight after its pages. Anywhere else, **Mark
  applied** stays yours to press, and **Done** on the review card ends the run without marking it.
- **Sign-in with your saved job-site login**, on known application sites only (Workday, Greenhouse,
  Lever, Ashby, iCIMS and a few more), in the page's top frame. Anywhere else the run waits for you.
  The password never reaches an AI model, a trace or a log, and a failed sign-in is never retried.
- **Screening answers**, a three-level setting under Settings › Form filling that replaces
  "Answer low-stakes questions for me": **Careful**, **Balanced** (the default) and
  **Confident**. Work authorization, salary, demographic, criminal-history and clearance
  questions, signatures and claims your history does not support are outside every level. Agents
  read the level in the Job Search Brief (`applying.answer_level`).
- **A job remembers the employer's apply link** (`apply_url`) when you save it from a page that shows
  one, and the run opens that link instead of the job board.
- **The form-filling agent has more to try.** It never fills a hidden "leave this blank" trap field,
  leaves optional fields it has no answer for empty and lists them, fills a list such as Skills one
  item at a time and checks each one landed, can search with a word of its own, gets a short
  technique note for each kind of widget, and waits for a page to stop redrawing before it types.
- **It learns from your fix.** When you fix a field by hand while a run waits, the Companion notes
  which gestures you used (never what you typed) and tries them first on that site next time. With
  **Keep a fill log** on, fields it could not work join a private, value-free list that ranks what to
  teach it next. **Clear data** removes that list too.
- **Two new switches for Apply**, under Settings › AI & models › Form filling. **Choose the base
  resume for me** (on by default) lets Apply pick the resume only when one clearly wins: its match
  score reaches Auto-apply's floor and leads the next by Auto-apply's margin. If it is close, Apply
  stops and asks. Off, nothing is picked until you pick. **Stop after each step** (off by default)
  turns Apply into three presses, **Save job**, **Tailor resume** (or **Make PDF**) and **Start
  filling**, and your yes to queueing the job moves to the last one.
- **A live checklist while Apply gets ready.** The Job card lists each step as it happens (saving the
  job, scoring your resumes, the resume it is using, queueing, tailoring, making the PDF, opening the
  application) with a tick, a spinner or a short reason, and a **Stop** button that ends the press
  between steps. Whatever was already done stays done. The resume list is locked while it works.
- **The run reads the page's errors.** When a page refuses Next and says why (Workday's "Errors
  Found" banner, for example), the run no longer counts that as a new page. It fixes only the fields
  the page names, presses Next once more, and if the page still refuses it stops and lists what the
  page asks for. It never refills the rest of the page.
- **The resume is attached before Next.** A required upload box labelled only "Upload a file" is now
  recognised as the resume box when it is the page's only upload. The Companion never presses Next
  over an empty required upload: it attaches your PDF or stops and says which box needs a file. The
  page line reads "Resume attached" or says why it could not, and the counter counts answered fields.
- **Written history questions get answers.** "Do you have experience with X? For how long and for
  which companies?" used to be left blank. It is now written from your career history, and never
  claims what your history does not support.
- **"Have you worked at X before?" answers No from your work history** when your history lists jobs
  and none is at that company. The receipt says "from your work history". Any match still answers
  Yes, and a company that looks like a parent or subsidiary of one of your employers is asked, not
  answered.
- **Accounts are created on known application sites.** When an application asks you to make an
  account, the run does it with your saved job-site login, once, on the sites it knows (Workday,
  Greenhouse, Lever, Ashby, iCIMS and a few more), in the page itself. It ticks only the box that
  agrees to creating the account or to the privacy notice, never a marketing box, and presses only
  "Create Account". An email check stops the run at **Email code** and a CAPTCHA at **CAPTCHA**; a
  site that refuses the account (a password rule, an account that already exists) stops it at
  **Account not created**. It never tries twice, and the password never reaches an AI model, a trace, a log or the screen.
- **More controls get filled.** Dropdowns drawn as read-only boxes, Yes/No and Degree questions drawn
  as rows of buttons, category lists that open before they show their choices, autocomplete boxes
  that answer slowly, and street addresses (typed whole and picked from the suggestions by house
  number and street, or left as typed and flagged). A link is written whole with https. A date box
  that wants a day or month your profile does not have takes the 1st, or January, and the row says
  so. A phone-type box is answered Mobile, a country-code picker takes your country's code, and
  neither ever receives the number.
- **Written questions are drafted for you to read.** A required written question your saved answers
  cannot answer ("Why do you want to work here?") is drafted from your career history and the job,
  in your own voice and about 120 words, or the length the question names. The row says "Drafted from
  your history: read it". Nothing is saved as a standing answer; edit it and press Resume to teach it.
  At **Careful** nothing is drafted, and work authorization, pay, demographic, background,
  availability and "have you worked here" questions never are.
- **"How did you hear about us?" finds the board.** A job board that listed the job is searched by
  name first; a site that groups its answers is walked category by category only when the search does
  not find it, and the row says it was assumed. The company's careers site is picked for a website answer.
- **The Ask box is back under a run.** Paste a question, get one grounded paragraph, copy it. It
  opens when the run pauses, not while it is working.
- **A line when the fill log is off.** If **Keep a fill log** is off the run card says so and when the
  log last recorded a run, so a gap in Analytics has a reason.
- **Notes under a field.** The answered list and **Check before you submit** show a short fixed note
  under a field name: "Drafted from your history: read it", "Day set to the 1st".

### Changed

- **The job page and the Agent inbox lead with what you need to do.** A job's header shows one
  status and one score (**Resume match** once tailored, **Best base resume** before), and a **Where
  this stands** line says whether and how you applied. The knock-out check is a banner only when it
  blocks you, and the proposal card appears only when it carries something. A job you applied to
  yourself reads **Applied yourself**, not Skipped. The inbox opens with one summary line, hides empty
  lanes, shows the search and filters only for a long list and the daily limit only near it, and the
  runs list moved to the Automations page, leaving one line when the newest run proposed jobs.

- **Your tailored resume is written in first person.** Tailoring, rewrites, the Assistant and agents
  now write each line as you would ("Built X", never "He built X" or "Builds X"). If the AI slips,
  Maestro retries once, then repairs the line in code; a pronoun or your name is never stored. Your
  own lines are only touched where it is mechanical. The tailor result lists what was repaired, an
  agent that sends third-person text gets an error saying how to fix it, and the health check notes
  a summary or bullet that reads as written about someone else. **Use resume as is**, Apply with the
  base resume and quick tailor's "nothing to tailor" result use your base text unchanged, so fix a
  third-person summary in the base resume itself.
- **Apply stops guessing between close resumes.** With full automation on, the Companion preselects a
  resume only on a clear win (see the new switches). The pick limits under Auto-apply now say they
  apply to connected agents and the Companion.
- **Tailoring after Apply no longer wedges it.** Apply links the draft it made; a draft you tailor
  afterwards is now linked in its place instead of failing with "proposal already linked".

- **Screening answers start at Balanced.** The old switch stored nothing when it was
  off, so an install that had it off cannot be told apart from one that never touched it. Both now
  read the default, which answers low-stakes questions in the job's favour and says Yes to "N years of
  a skill" only when your history shows the skill. If you want the old behaviour, pick **Careful**.
  If your laptop and your second copy run different versions, saving the level on the newer one
  clears the old switch, which the older copy reads as off until you update it.
- **The Companion remembers the job per tab, not for 30 minutes.** A long application no longer
  forgets its job halfway, and a second tab's pick no longer overwrites the first. The memory lasts
  while the tab is open.
- **The Companion's fill log is now off unless you turn it on.** The record of
  which fields a fill met and on which sites (never what you typed) and the run
  traces are kept only after you tick **Keep a fill log** in the Companion's
  options. That switch is new; the developer-console command is gone. If you
  never chose, logging stops after this update; records already kept stay until
  you clear them in **Analytics → Autofill coverage**.
- **Ready to submit is stricter.** The run says Ready only on a page that has a real Submit button
  and no Next, with no error showing and no required box empty. A review page that is not plainly the
  end stops and says why (More than one Next, May send the application, No Next button found, or Not
  sure about this page): check it, then press **Resume**. A page with nothing to fill and only a "Continue" or "Proceed" stops
  instead of being pressed. A stepper's step names, a cookie notice's buttons and a footer's links are
  no longer mistaken for Submit or Next.
- **A closed posting means closed.** A job description that says a position "is filled" no longer
  ends the run. A page counts as closed only when it shows a closed notice and nothing to fill or
  apply to, and the stop offers **Resume** in case it is not.
- **Resumes that were not scored for the job are tucked away.** The Job step lists the scored base
  resumes and the one selected; **Show N more (not scored for this job)** reveals the rest. With
  nothing scored, every base shows.
- **The resume goes only into a resume box.** A box that imports or fills the form from a resume
  (the site's own parser) is never given the file, a required one stops the run naming it, and the
  **Attach resume** button skips a box meant for a cover letter or another document.
- **A middle name is never made from your first name.** A Middle Name box stays empty unless you
  saved a middle name, and your name is typed as you entered it.
- **"Have you worked here before?" is matched more carefully.** Only a question that asks whether you
  worked for the company is answered from your work history. Questions about relatives, referrals,
  eligibility, a competitor, or a time window are no longer mistaken for it.
- **A degree is compared by its level.** "Master's/Advanced Degree" on a form matches your Master of
  Science without a warning; a form that names a field is compared by its words.

### Fixed

- **Fourth live check of Apply, from an employer's own career site to a Workday tenant.**
  - Apply on a job's own posting now opens the application link saved with the job, instead of staying on the
    posting. If you start Apply part-way through the form, it stays where you are.
  - A career site's **Apply** button that asks for a new tab is pressed in the same tab, but only when it
    leads to the job's application link or to a known application site. If the page you land on is on
    another site, Apply stops there instead of filling it.
  - When Apply waits for you to do a step by hand (the posting's own Apply button, a start page, a sign-in), it
    follows you into the tab you open for the application, and the card says "The run moved to this tab".
    Press **Continue here** to carry on; nothing is filled until you do. If the run waits in another tab, the
    Job step offers **Move the run to this tab** instead of "Running in another tab". A run that is
    filling never moves.
  - After a page refuses **Next**, Apply fills the page it ends up on before pressing anything there. It
    fixes the errors it can match to a field, and the stop names only the ones left.
  - A required field that a search or a click filled (Field of Study, say) no longer stops the run. It is
    listed under **Check before you submit**. Work authorization, sponsorship, eligibility, demographic and
    salary questions are not treated this way and still stop for you.
  - An optional Skills box stays empty in a run, since it was the slowest field on a page. A required one
    is still filled.
  - What you type in the page while Apply waits on "The page asks for more" or on an upload is remembered
    for next time, the same as for a question.
  - A veteran **No** now answers "Are you currently or have you ever served in the military?" with the
    never-served option and says it was assumed. A **Yes** never answers a question about current
    service, and never picks an option that says you serve now.
  - A spouse's or household member's military service gets the safe default **No** (or "I don't wish to
    answer" when offered), listed under **Check before you submit**. Your own military service is never
    defaulted.
  - "Worked as a contractor for X", "employed by an authorized dealer of X" and a short list of companies
    answer No from your history when none of them is yours, and say it was assumed. A company that goes
    by more than one name, or one written as initials in your history, is asked instead.
  - A word like "Mobile" or "Home" that you answered no longer hides part of another question in the fill
    log.
- **Third live check of Apply on a Workday tenant.**
  - A Workday "Start Your Application" page no longer stops the run. It presses **Apply Manually**, the one link
    that only opens the form, and never **Autofill with Resume** or **Use My Last Application**; anywhere else
    it says **Choose how to apply** and waits for you.
  - A dropdown or a Yes/No button whose question mentions "submit" is a field, not a Submit or a Next, and the
    footer's Next decides the step. A normal step is no longer called "maybe the last page".
  - A page is filled before it is judged, and a page that still looks unfinished after about 2 seconds is
    what stops the run. The stop now says why, and **Resume** fills what is still open before it counts as
    your word that this is the last page (it does not, once a Next is on the page).
  - An account that was created is no longer reported as not created: after **Create Account** the run waits
    up to 20 seconds for the site to move on.
  - A page that lists its errors on two lines now maps each one to its question.
  - Questions your profile cannot answer get a safe default: No (or Not applicable) for tribal, union or
    association membership, a referral, or relatives at the company; Yes for willingness to a background
    check, drug test, references, I-9 or documents, and for transport and internet. Criminal or background
    history, salary, work authorization, demographic questions, licences, terminations, agreements and
    boxes that authorize a check are never defaulted. Every default is listed under **Check before you submit**.
  - "Are you currently employed by X?" answers No from your history when X is neither your employer nor the
    job's company as the page spells it, and says it was assumed.
  - A job you marked applied and then set back to Draft can be queued again; while it still says applied, the
    message says so instead of calling it skipped.
  - A job posting with no built-in job data (a Darwinbox careers page, for one) is read from the section under
    its description heading, with its title, company and location, and only from what is on screen.
    Darwinbox's apply page needs a CAPTCHA, so the run stops there.

## [0.10.1] — 2026-10-12

Updating to 0.10.0 could leave the web app showing pages from the version you
just left: no styles, and a banner saying the update hadn't finished. This
release clears that leftover cache every time Maestro starts.

### Breaking changes

None.

### Fixed

- **After `maestro update`, the web app no longer serves the previous version's
  pages.** Next.js keeps a page cache inside the installed app, and an update left
  the old one behind, so pages pointed at scripts and a stylesheet that no longer
  existed. `maestro run` now clears that cache before the web app starts, so
  updating to 0.10.1 also repairs a 0.10.0 install that shows an unstyled page.
- **A page opened before an update now says so.** The banner reads "Maestro CS
  was updated. Reload this page to use the new version." with a Reload button,
  instead of saying the update didn't finish. Any other version mismatch still
  points at How to update.

## [0.10.0] — 2026-10-12

Until now Maestro spoke two AI dialects, OpenAI and Gemini, so a Claude key
could only watch from the side. This release adds Claude, talking to Anthropic
directly, and OpenRouter, with zero data retention switched on for you. A Claude
key alone now runs the whole app, the Assistant included. Your chats are saved in
a format that belongs to no single provider, so you can change models halfway
through a conversation and it still remembers what was said.

Two smaller things you will notice. Every finished resume now also lands in your
Documents folder, one folder per job, so there is no more digging through a data
folder to find it. And the Companion has a new look, one clear next step at a
time, and it no longer drops dropdowns when its tab is in the background.

### Breaking changes

- **A built-in Gemini model now always goes to Google, even with a Custom AI
  server set.** Before, the Assistant sent a role set to `gemini-3.5-flash-lite`
  or `gemini-3.7-flash` to the custom server; now it uses your Gemini key, or
  says that no Gemini key is set. With a custom server and a Gemini key, any
  `gemini-*` Assistant model also goes to Google. If you serve a local model
  under one of those names, give it an id that is not in the built-in list
  (for example `gemini-local`): ids Maestro does not list still go to your
  server.

### Added

- **A resumes folder in your Documents.** Your finished resume used to sit in a data
  folder you had to dig for, so now every resume PDF, and every cover letter PDF, also
  lands in your Documents folder, one folder per job. The copy happens after each render
  and after a job arrives from your second copy, and every start copies the resume PDFs
  you already have, with their cover letters, skipping the ones already there. Folders are named `Company – Job title (date)` under
  `Documents/Maestro Career Studio/Applications` and keep their name if you edit the
  title later. Maestro only writes there: it never reads a copy back or deletes anything,
  a re-render replaces the file with the same name, and a copy you delete or rename
  stays that way until that resume changes or you click Show in Finder. **Show in Finder** (**Show in File
  Explorer** on Windows) on the PDF card and in the tailored-resume studio opens the folder, and
  Settings › Tailoring › Resumes folder switches it off, picks another folder (**Choose…**
  opens your system's folder dialog) and shows the last problem. It is on with the
  `maestro` command, and not on the Docker route or on the second copy that stays on.
  MCP `render_pdf` on an application now returns `copy_path`.
- **Claude as an AI provider.** Add a Claude API key in Settings › AI & models
  (or `ANTHROPIC_API_KEY` in `.env` / `maestro.env`). Claude Haiku 5.5, Sonnet 5.5
  and Opus 5.5 are listed in the model pickers, and **Find Claude models** lists
  the rest; no role switches to Claude on its own. Calls go to Anthropic's own API
  through the official `anthropic` SDK, not its OpenAI-compatible endpoint. The
  Assistant caches its long system prompt and tool list between turns, and when a
  Claude safety check declines a request on Opus 5.5 or Sonnet 5.5, Anthropic
  retries it on another Claude model.
- **OpenRouter as an AI provider.** Add an OpenRouter key in Settings › AI &
  models (or `OPENROUTER_API_KEY`). Every request asks OpenRouter to use only
  providers that keep no data and collect none, and this cannot be turned off.
  **Find OpenRouter models** lists only models with such a provider. OpenRouter
  itself may keep what you send; [PRIVACY.md](PRIVACY.md) says what goes where.
- **Switch providers mid-conversation.** Assistant messages are saved in a
  provider-neutral form. A chat started on one provider continues on another,
  and each provider's private reasoning data is sent back only to that provider.
- Settings › AI & models warns when a role's model belongs to a provider with no
  key saved ("Fast model uses OpenAI, but no OpenAI key is saved").
- Key checks for Claude (`sk-ant-`) and OpenRouter (`sk-or-`) keys, and a warning
  when a Claude or OpenRouter key is pasted into the OpenAI field.
- `backend/scripts/live_provider_check.py`, a manual check that runs the app's
  own one-shot, tool-calling and provider-switch paths against real keys.

### Changed

- **The Companion has a new look.** A progress bar shows where you are in the
  four steps, the step you're on is one "Next" card, finished steps shrink to a
  line with a tick, and Refresh and Open are icon buttons. Nothing it does has
  changed.
- **The Companion fills forms in background tabs.** A tab you switch away from,
  or a window covered by another app, used to slow every field down and drop
  dropdowns. Chrome slows timers in hidden tabs, and the fill now waits in a way
  Chrome doesn't slow.
- **Gemini in the Assistant uses Gemini's own API** instead of Google's
  OpenAI-compatible endpoint, and keeps Gemini 3's thought signatures between
  tool calls.
- The pinned resume and selections for an Assistant message are saved with that
  message instead of being rebuilt on every later turn.
- The setup checklist's AI key step, and the Career KB's first-start seeding,
  count a key for any of the four providers or a Custom AI server.
- **Test** next to a model runs the same streaming, tool-calling request the
  Assistant makes, for every provider.
- New dependency: `anthropic` (1.13 or later, which brings `httpx2`). The Docker
  lock also gains `psutil`, which 0.9.0 added to the package but not the lock.
- `maestro.env`, `.env.example` and `docker-compose.yml` list `ANTHROPIC_API_KEY`
  and `OPENROUTER_API_KEY`. Like the other keys, a key saved in the app wins over
  one from the environment.
- A database migration adds `parts`, `provider` and `model` to `chat_messages`
  and fills `parts` from every existing message when the backend starts. The old
  `tool_calls` and `tool_call_id` columns stay for one more release.

### Fixed

- GPT-5.4, GPT-5.5 and GPT-6 models (including `openai/…` ids on OpenRouter) can
  call tools in the Assistant: Maestro now sends `reasoning_effort: "none"` for
  them, which OpenAI requires on Chat Completions. Before, only GPT-5.6 got it.
- Gemini 3 Assistant turns that need two tool steps in a row no longer lose the
  thought signature Google requires on the second request.
- A Claude account with no API credit reads "your account is out of credit"
  instead of "The AI model didn't answer (error 400)", and the model test does
  not record it as a failed model.

## [0.9.0] — 2026-10-10

This release is about getting Maestro out of its box. AI agents now reach it by
URL instead of reaching into a container, and the whole app installs with two
commands and no Docker at all. If you already run the Docker version,
`maestro import-docker` brings your data across in one go.

### Breaking changes

- **Claude Code and Codex plugins now connect to `http://localhost:8001/mcp`**
  instead of running `docker exec`. They need v0.9.0 images: earlier images
  have no `/mcp` endpoint. If you changed `BACKEND_HOST_PORT`, use Settings ›
  Connected agents › **Connect an agent app** instead of the plugin.
- **Pre-rename environment variables are now ignored silently:**
  `CAREER_STUDIO_EXTENSION_IDS`, `CAREER_STUDIO_MCP_PROFILE`,
  `CAREER_STUDIO_MCP_CLIENT`, `CAREER_STUDIO_PDF_DIR`,
  `CAREER_STUDIO_UPLOAD_DIR` and `RESUME_TAILOR_PDF_DIR`.
  Use the `MAESTRO_CS_*` names. Leaving these set without their replacements
  means an unpacked Companion id loses API write access, the MCP profile falls back
  to `full`, and PDFs/uploads go to the default folders.
- **Nothing in the uv install work needs an action from a Docker install.** The
  Docker images, `docker-compose.yml`, `.env`, ports and `scripts/update.sh` work as
  before (the Changed list below says what moved inside the images).

### Added

- Career history imports PowerPoint decks (.pptx), including speaker notes.
- **`maestro import-docker CHECKOUT`** moves a Docker install's data into the uv
  install, once: the database (with stored file locations rewritten), resumes,
  applications, knowledge-base files, settings, the sync key and the settings in
  its `.env` that Maestro understands. It reads the Docker folder and changes
  nothing in it, saves a snapshot of the uv database first, and puts back the
  database, sync key, settings and `maestro.env` if anything fails. `--dry-run` shows the plan. See `docs/UPDATING.md`.
- **A Docker-free install with uv, and the `maestro` command.**
  `uv tool install --python 3.12 maestro-career-studio` installs Maestro (published
  to PyPI on every release tag, with the web app and Node inside the package) on
  macOS, Linux and Windows x64. `maestro start`, `stop`, `restart`, `status`,
  `logs`, `open`, `update`, `backup`, `migrate`, `check`, `autostart on|off|status`,
  `connect` and `mcp` run it from one per-user folder with one settings file,
  `maestro.env`. `maestro update` saves a verified snapshot of your data before it
  changes anything and prints the changelog's breaking changes first. See the
  README, `docs/GETTING_STARTED.md` and `docs/UPDATING.md`.
- **`maestro connect`** adds Maestro to Claude Desktop (waiting until you quit it,
  because it rewrites its settings while running), Claude Code, Codex, Cursor and
  VS Code. `maestro mcp` is the stdio bridge it points Claude Desktop at; on a uv
  install the connect card's Claude Desktop row shows the command instead of the
  bundle download.
- CI builds the wheel, installs it with uv on macOS, Ubuntu and Windows, smoke-tests
  it, and upgrade-tests one version to the next (`docs/RELEASING.md` has the
  one-time PyPI setup).
- **HTTP MCP inside the backend** at `/mcp`, with `full`, `hunt`, `apply`,
  `explore`, `templates` and `career` tool profiles on the same port and
  Host/Origin boundary as REST.
- **Connect an agent app** on Settings › Connected agents: choose a **Tool set**,
  copy a command or URL, open a client install link or download the Claude Desktop bundle.
- **Companion options page** to set the backend and app addresses and test the connection.
- **Copy setup prompt** on Settings › Connected agents › Second copy, and a
  guide for running an always-on bot (`docs/always-on-bot.md`). The button
  copies a setup prompt for a fresh always-on copy. It fills in the laptop's
  published address and the version this backend is running, and it never
  includes the sync key or a pairing code.
- **`start.sh --unpause`** clears a maintenance pause and exits without
  starting the backend, so the watchdog can start Maestro. `sync.sh` exits 3
  when a round is still running after its wait; check later with
  `sync.sh --now`.

### Changed

- The app calls its score the match score (it was labelled ATS score).
- README rewritten: shorter top screen, the uv install leads the Quickstart; the manual moved to `docs/USING_MAESTRO.md` and `docs/SETUP_REFERENCE.md`.
- **The backend's Python distribution is renamed** `maestro-career-studio-backend`
  to `maestro-career-studio` (it is the PyPI name). The setup scripts uninstall the
  old name; nothing to do. `pyproject.toml` is also the PyPI version.
- **The frontend image runs `node server.js`** from Next's standalone output
  instead of `next start`, with image optimization off (nothing uses it) and no
  `sharp`. `npm start` does the same outside Docker. Same ports, same behavior.
- **Any venv that installs the backend now also pulls Node 24** through
  `nodejs-wheel-binaries` (about 200 MB installed): the native always-on scripts,
  the stdio MCP server, and `pip install -e backend` for development.
- `/health/memory` and the sync file reads work on Windows. On Windows, a sync file
  read no longer refuses a symlink at open (there is no `O_NOFOLLOW`); the
  regular-file check and the packer's symlink check still apply.
- The Claude Code command on the connect card and in the docs is
  `claude mcp add --scope user …`, so Maestro shows up in every folder, not only
  the one you ran it in.
- `PRIVACY.md` names the scoring model's first download (Hugging Face) and the
  `maestro` command's PyPI and changelog requests; both are only made when you run
  them or on first start. Contributors: CI installs now also download
  `nodejs-wheel-binaries` (about 60 MB); `requirements.lock` leaves it out.
- The Claude Desktop **`.mcpb` bundle is a Node stdio-to-HTTP bridge**.
  Reinstall it if you used the older Docker-based bundle. Claude needs no
  Docker or Python on its side; the bundle supports macOS, Windows and Linux.
  Claude Code and Codex plugins connect by URL.
- **`mcp` is now a core dependency.** The `[mcp]` extra remains as an empty
  compatibility alias for existing install commands.
- **The Codex plugin asks before consequential tools**, including consent,
  submission, login and upload hand-offs, restores, health-gate waivers,
  KB approval and sync, in addition to Maestro's own consent gates.
- Langfuse tracing is an optional `tracing` extra. Docker and native installs still
  include it; a source/dev install gets it with `pip install -e ".[tracing]"` from
  `backend/`.
- Backend image copies files with the app user's ownership and excludes tests
  and every backend script except `scripts/sync_key.py`, the Docker sync-key
  tool; dev tools (pytest, ruff) are no longer installed in it. mako moves off
  the yanked 1.4.0 to 1.4.3, and the image shrinks from about 1.88 GB to 1.72 GB.
- The web build ships only the Monaco editor files the JSON and LaTeX editors
  load, cutting `frontend/public/monaco` from about 25 MB to 11 MB.

### Deprecated

- **`scripts/setup-mcp.sh` and the host stdio venv** remain for one release and
  are removed in v0.10.0. Existing `maestro-career-studio-mcp` connections keep
  working as a compatibility fallback.

### Security

- Typst renders can no longer download packages, including through a computed import path. LaTeX compiles each run in its own temporary folder, so a template cannot read or overwrite another resume's source.

### Fixed

- PyPI wheels include the project license and notices; untouched Classic templates receive the complete attribution header on upgrade.
- Bundled resume templates carry complete MIT attribution, including Harshibar;
  third-party notices list all six seeded designs and both cover-letter sources.
- The glossary and package description use match score; the social preview restores Inter Medium.
- First starts without TeX render the demo resume with Typst; a failed seed render shows its reason.
- Windows child processes keep the system environment needed for networking, including backup and update commands.
- Failed startup base-resume renders and artifact file deletions log warnings
  with tracebacks; missing files and folder-pruning failures stay quiet.
- Prompt reads that open their own session use the file default without writing
  when no saved prompt exists, avoiding a SQLite lock wait behind another
  transaction. Startup seeding and caller-supplied sessions still seed defaults.

### Removed

- Companion dead code: the orphan-key sweep, the legacy `eeoAutofillEnabled`
  setting and unused exports; `shared/guided-run.js` no longer loads into every
  page's content scripts (only the panel uses it).
- Word text extraction uses the standard library, removing python-docx and its
  sole lxml dependency while preserving paragraph and table text output.
- Four API routes with no caller outside tests: `POST /api/resume-lint/wording/reset`,
  `GET /api/kb/extra-section-presets`, `GET /api/resume-versions/{kind}/{key}/{number}/diff`,
  and `POST /api/kb/consolidate`. Word-bank reset still saves through `PUT /wording`;
  the preset catalog, version-detail diffs, and onboarding import remain available.
- The `/explore` redirect (Analytics has lived at `/analytics` since July).

## [0.8.0] — 2026-10-07

### Breaking changes

- None that need an action from you. Read these before updating:
  - **Five migrations run at startup.** They only add tables and columns
    (filled answers, agent runs, the autofill run trace, the always-on-copy
    fields, a resume's target), so your data is untouched. `scripts/update.sh`
    snapshots the database first.
  - **No `.env` changes.** `docker-compose.yml` forwards one optional new
    variable, `SYNC_PUBLIC_HOST`, only for a published sync address.
  - **The backend image runs uvicorn with `--no-server-header --ws none`.**
    Nothing relied on either: the app has no WebSocket routes.
  - **The agent skills moved** from `docs/skills/<name>/` to
    `backend/app/automations/skills/<name>/` (`docs/skills/` is now an index).
    The app and any skill you already copied into your agent are unaffected. A
    link or agent instruction that names the old folder now gets a 404; point
    it at the new one or copy the prompt from the Automations page.

### Added

- **Run Maestro without Docker** on a small always-on Linux machine. Four
  commands (`setup`, `start`, `stop`, `health`) install and run the backend
  from one folder, with one loopback worker. No web app there: a connected
  agent starts the MCP server on demand. See `docs/native-install.md`.
- **A second, always-on copy** of Maestro that keeps working while your laptop
  is off. Your laptop keeps your profile; each job has one owner, so nothing
  merges. Job cards show **With your bot**, **On your laptop** or **Going to
  your bot**, with **Keep it here** and **Work on it here**. A queue, skip,
  status or note change on the other copy's job waits as **Sent at the next
  sync**. With full automation on, a job you queue on the laptop is offered to
  the always-on copy. It stays off until a sync key file exists; without one
  nothing changes. Pairing is a one-time code. Every sync message is sealed
  (protocol 2) and can travel over HTTPS through Tailscale Funnel or an SSH
  tunnel. The key never travels, and anything that is not sealed gets the same
  empty 404 as when sync is off, even on the published name. The MCP tool `sync_now` runs a round, and
  `sync.sh` runs one from cron. The always-on copy holds a read-only copy of
  your profile, including the AI key and the job-site login. See
  `docs/sync-setup.md`.

- **`/health/memory`** reports how much memory the backend is using now and at
  its peak, so you can watch a small machine. `health.sh` prints it too.
- **Lighter ATS scoring on small machines.** Set `EMBEDDINGS_OUT_OF_PROCESS=1`
  and each score loads its language model in a short-lived helper, one at a
  time, instead of keeping it in the backend. Scores are the same; backend
  memory after scoring drops from about 410 MB to about 170 MB, and each score
  takes under a second longer. The native `start` command turns it on; the
  Docker install keeps it off.

- **Full automation**, Off by default in Settings › Connected agents: your
  agent can submit queued jobs whose final review is clean without asking
  each time. The daily limit and Companies to skip still apply; anything to
  check goes to Needs you. On the Automations page, **Apply automatically**
  replaces the attended Apply prompt while the switch is On. Order, batching
  and timing stay between you and your agent.
- **Job-site login**: save an email and a password used only for job-site
  accounts. They stay in a private local file; Settings shows only whether a
  password is saved. A connected agent can fetch them for a queued or approved
  job while full automation is On. Each hand-off is recorded without the value;
  the login passes through your agent's AI provider.

- The **Agent inbox dashboard**: readiness marks on open rows, an arrivals strip
  and **Recent runs** with each automation's counts, digest and job links. Queued
  jobs ready to apply sort first. Automations cards show **Last ran**. New MCP
  tool `record_run` keeps the latest 200 run reports.
- The **Automations** page: copy a prompt into Claude Desktop, Codex or any MCP
  agent, which asks when to run and then does the job with Maestro. New
  `mail-status`, `referral-pages` and `tailor-run` skills join `job-hunt`,
  `apply-session` and `customize-job-skills`; the skills now live in
  `backend/app/automations/skills/` (`docs/skills/` is their index).
- Autofill keeps a private record of how it decided each field (which answer it
  chose, demographic questions included, how sure it was, what the page did),
  for diagnosing and tuning it. It holds no typed answer or profile text, stays
  on your machine, keeps your last 50 runs, turns off with the same opt-out as
  field telemetry, and goes when you press Clear data.
- **What was submitted**: the job page keeps a record of every answer the
  Companion or a connected agent filled into the application form, page by page,
  with a small pill saying where each came from (Profile, Resume, Custom,
  Written, Inferred, You, Upload). Answers worth a second look (a screening
  question answered by a guess, every option ticked, an answer unlike your
  profile, a voluntary question with nothing saved) are flagged before you
  submit, in the Companion's new **Check before you submit** group and in the
  agent's final review, and the tab shows them with their reason. Diversity
  answers are kept only with your consent, are cleared when you withdraw it,
  and are never sent to an agent. New MCP tool `record_filled_answers`.
- The knock-out check on a job also compares an on-site or hybrid office with
  where you live and whether you would relocate, and the Companion shows its
  verdict above the form before you fill.
- **A target for each base resume**: the countries it may be sent to, a
  company and a short focus, set in its Target dialog and shown as pills on
  its card. A resume set for other countries is not scored or recommended for
  a job elsewhere and is never ready to send; full automation checks it too.
  Tailoring reads the target. A resume with no countries has no limit.
- **Five new MCP tools:** `set_base_resume_identity` (a resume's target),
  `sync_now`, `record_filled_answers`, `record_run` and `get_job_site_login`
  (full automation only). `score_ats` names the bases it skipped for country.
- **Pause the always-on copy's watchdog** while you work on it: `stop.sh`
  leaves a pause the cron watchdog respects, `start.sh` resumes and
  `health.sh` says when it is paused.

### Changed

- **A new look across the web app**, from one design system: one tab style,
  filled stat cards, shadows only on what floats, and filter chips with counts.
- **One icon for each idea, and meters that say what they mean.** The same
  glyph marks the same thing everywhere, in the Companion too, with no emoji
  as icons. Scores, readiness and progress are small bars and dots with their
  words beside them, never colour alone.
- **Where you stand, at a glance.** The job header shows its best score; Jobs
  shows each job's score, a status dot and a needs-you strip; score cards mark
  the weakest score and show a shared warning once; the knock-out check is
  quiet when it passes and loud on a conflict. Analytics adds a status mix and
  a 28-day trend, and compare shows what a tailor gained or lost.
- **Actions answer you.** Slow buttons spin, a status change turns the chip at
  once, saves say Saved and copies say Copied. Inbox actions toast and the row
  slides out. Approving a draft bullet and archiving a resume offer **Undo**.
  Email, phone and link fields warn before you leave them.
- **The Companion panel uses the web app's status words and colours**, with
  icons in place of text symbols.
- Jobs `job-hunt` saves are marked as found by an agent and keep the job's
  link. They wait in the Agent inbox alongside jobs from referral pages, and
  later hunts recognize jobs already saved.
- Agents record each form page's answers instead of attaching a screenshot of
  every page; the final-review screenshot stays. In full automation, the agent
  records what confirmed submission and a submission screenshot is optional.

### Fixed

- Agent inbox History says **Applied yourself** for jobs you applied to, with
  the Applied badge, counts and filter grouping; their stored status is unchanged.
- A page of screening questions with nothing else on it (iCIMS's Candidate
  Questions step: age, work authorization, sponsorship) is recognised as an
  application form, so Autofill is offered there and can fill it.
- The later steps of a multi-step application (iCIMS's EEO and questions
  pages, any wizard's short steps) no longer say "No application form here".
  Once a form is confirmed on a site in a tab, a later page there with a field
  to fill counts as the form for the next hour, and the employer's own embedded
  form frame on that site accepts the fill. On the next step after a fill, the
  Fill step opens by itself with Autofill.
- Autofill answers more of iCIMS's later steps:
  - a veteran self-identification asked in a paragraph ("please indicate by
    checking the appropriate box below");
  - a follow-up box such as "If applicable, please provide info." (it now
    reads the question it follows);
  - "Are you able to work on-site at our … location?", from your relocation
    answer;
  - with Agreements on, a "Signature" box that signs the form.

  A "please specify referral name" box no longer takes your how-heard answer.
- **The backend starts when `NO_PROXY` holds a bracketed IPv6 address**, as a
  default on some Linux VMs. The entry is repaired at startup, so the AI
  provider and the first language-model download work too.
- **The Score and tailor tab scores a job on first visit** even when all it
  shows is a tailored row or a base hidden for another country.
- A native health check during a launch no longer deletes the pid file.
- **Tighter responses on the published sync name.** uvicorn no longer sends a
  `server:` header and refuses WebSocket upgrades, so nothing names the stack.
  The frontend's `sharp` and `source-map-js` dependencies are updated for
  `npm audit` findings (high).

## [0.7.1] — 2026-10-01

### Breaking changes

- None. No migrations and no `.env` changes. MCP list tools return fewer rows
  by default (see Changed); every one of them still takes `limit` and `offset`.

### Added

- **A listing on the official MCP Registry.** `server.json` describes the
  server as `io.github.seinun-ai/maestro-career-studio`, and the Claude Desktop
  extension is attached to each GitHub Release so the registry, and the
  directories that copy from it, can point at a checked download.
- **A privacy policy.** [`PRIVACY.md`](PRIVACY.md) says what the app stores,
  every place your data can go (the AI provider you configure, optional
  Langfuse tracing, the assistant you connect over MCP), and how to delete it.
  The README, the Claude plugin and the Claude Desktop extension link to it.
- **The Claude plugin has its own README and license**, with example prompts,
  what it runs and what it sends. The Claude Desktop extension gains an icon.
- **Every MCP tool has a title and read-only / destructive hints**, so Claude
  can show a readable name and ask before a tool changes your data.

### Changed

- **MCP tool descriptions say what a tool does instead of telling the agent
  what to do**, and the `next` hints after a tool describe the available next
  steps. Consent still works the same: approving points, consenting to an
  application and marking it submitted record your own decision.
- **MCP lists return less at once.** `list_jobs` returns 50 rows by default,
  `kb_list_points` 50 (at most 100, without the per-resume usage history),
  `list_proposals` 20 (new `limit`/`offset`), and `export_jobs` 10 (new
  `limit`/`offset`, without the raw posting text). `list_tailoring_sessions`
  returns a summary per session; `get_tailoring_session` has the detail.
- **MCP errors are shorter and readable**, a timeout on a write says the write
  may still have finished, and capturing career notes gets the same long wait
  as other AI calls.
- **Next.js telemetry is off** in the images built from this release.
- **The plugin and extension descriptions no longer say a local model keeps
  everything on your machine.** Local models can be configured but are
  untested ([`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)), so the descriptions now say
  only that AI features use the provider you configure.

### Fixed

- **`attach_evidence_file` finds screenshots saved on your computer** when the
  MCP server runs inside Docker (the Claude plugin and Desktop extension).
- **A tool whose change was saved no longer reports an error** when only its
  follow-up hint could not be loaded.
- **Hints no longer suggest tools the active tool profile does not have.**

## [0.7.0] — 2026-10-01

### Breaking changes

- **Four migrations run by themselves at startup.** One stores health-check
  results with the rubric that judged them, and a table for your disputes.
  Two refresh the built-in tailoring prompts (tailoring rules, gap
  tailoring and the Assistant's instructions) and the built-in health-check
  prompts. A built-in prompt moves to the new default only if you never
  edited it; one you changed in Settings › AI & models › Prompts is left
  as it is. The fourth clears saved health-check results for bullets the
  check marked down by mistake, so the next health check reads those
  bullets again; a rating you set by hand is kept.
- **Agree again to let the Companion fill agreements and signatures.** The
  permission now covers more (see Changed), so a yes given before this
  release is off until you give it again. Profile › Autofill says so beside
  the switch: "This now covers more than when you agreed. Turn it on again
  to allow it." Your diversity consent is unchanged.
- API routes and MCP tools: none removed or renamed. The health report gains
  `next_grade` and a question on each finding, and `get_autofill_profile`
  gains `languages`.

### Added

- **A new Fill in the Companion.** "Saved answers + AI" now works a form the
  way you would, Workday-style dropdowns, searches and checkboxes included,
  and counts a field filled only once it has checked what the page actually
  kept. When it finishes it lists what it filled, the closest matches it
  picked, what it answered for you and what still needs your answer; select
  a row to jump to that field. Stop ends a run at any time. "Saved answers
  only" still runs the earlier fill.
- **Autofill also attaches your resume** when the page has an empty resume
  upload box. It never replaces a file already there and never uses a
  cover-letter or other document box. Attach resume is still there for
  those.
- **Answers come from your saved answers.** With a Jev key saved and Jev
  chosen in Settings › AI & models › Form filling, Jev picks first and your
  fast model decides where Jev is unsure.
  Without Jev, your fast model does it all.
- **Yes/No questions worded in reverse are read correctly**, such as "I do
  not require sponsorship". Fill first works out whether the question asks
  the same thing as your answer or the opposite, and leaves the field to you
  when it can't tell. "Now or in the future" sponsorship questions are
  answered from both of your sponsorship answers.
- **Fill adds entries** for the jobs, schools, languages and websites your
  profile holds, using the section's own Add button, and fills each one.
- **Fill remembers which clicks worked** for each kind of box, so the next
  form with the same widgets goes faster. No labels, values or page
  addresses are kept. "Forget learned widget moves" in the Fill step clears
  it.
- **Answer low-stakes questions for me** (Profile › Autofill, off by
  default): questions none of your answers covers and whose answer barely
  matters, like willingness to travel or a preferred contact method, are
  answered in the job's favor. Never work authorization, sponsorship,
  diversity questions, salary, background checks or signatures.
- **Languages** in Profile › Autofill: reading, speaking and writing levels
  (Basic, Intermediate, Fluent), plus separate Native and Fluent answers.
  The Companion adds a language to a form only when all three levels are
  set.
- **Health check v3.**
  - Each bullet gets its own question, a number only where one fits the
    work, always with a way to answer without one. A result stated clearly
    in words now earns full credit.
  - "Start the questions" opens a question pass: every question on one page,
    answered all at once or row by row, saved to the resume as one change
    you can undo.
  - **Not right?** on a finding tells the check why it's wrong, and it reads
    that bullet again with your note. A level never rises without words from
    the bullet itself, and "no number exists" is remembered for that text.
  - A wording checklist flags spelling and grammar slips, clichés and filler
    words, with Apply or Remove where the fix reads cleanly. The cliché and
    filler lists, and a Never flag list, are yours to edit.
  - A summary band on top: the grade, the points to the next one, and "No
    numbers anywhere" when no bullet has a number (a note, not a penalty).
    Findings sit under tabs by what they need.
- **Windows**, through Docker Desktop's WSL 2 engine: install, update and
  the Claude extension work with the clone in your WSL home
  ([On Windows: use WSL](docs/GETTING_STARTED.md#on-windows-use-wsl)).
- **Drag to reorder** bullets, sections and section order in the resume
  editor, by mouse or keyboard. Each bullet's ⋯ menu has Move to top, Move
  up, Move down and Delete.

### Changed

- **The Companion panel has four steps: Job, Resume, Fill, Track.** Save job
  also scores your base resumes and picks the best match, in the same press.
- **A shorter Resume step**: use your base resume or tailor to this job. An
  application whose resume has no PDF yet gets **Create PDF**.
- **Refresh** in the panel reads this page's job and applications again, so
  a PDF you made in Maestro CS shows up. What you typed and the Fill report
  stay.
- The panel's fill button is now **Autofill**, and the note under the panel
  sits on its own line instead of under the buttons.
- **Letting the Companion fill agreements and signatures now covers every
  field**, including signatures, initials, typed-name attestations and
  salary history. It still never moves to the next page and never submits.
- Tailoring writes bullets by the health check's rule: a concrete result,
  with a number only where you gave one, not a number in every line.
- Health checks judge each bullet again under the new rubric the next time
  they run, so a score or grade can move.
- Score and tailor: each card has one button, **Analyze gaps**; Restart gap
  analysis and Mark applied without tailoring are in the card's ⋯ menu.
- Career opens on your history: Quick capture rests as one line, and each
  profile section (Contact, Summary, Skills, Notes for the AI) has its own
  Edit.

### Fixed

- The panel no longer asks you to tailor again when you come back to a job
  whose tailored resume is ready.
- Long steps in the panel scroll instead of being cut off.
- Fill no longer types your phone number into a phone extension box, or your
  street address into a second address line.
- Workday application steps are recognized as forms, so Fill is offered on
  them.
- An application form embedded from another site (such as a Greenhouse form
  inside a company's careers page) is found, so Autofill is offered for it,
  including when the form only appears after you select Apply.
- Forms whose labels aren't linked to their fields (such as Gem's) are read:
  the Companion takes the short label just before a field, and groups Yes/No
  buttons that belong to one question.
- A resume upload counts as attached when the page lists the file, even on
  pages that clear the upload box (Workday), and never when the page refused
  it.
- On Workday, Attach resume is offered on the step with the resume upload
  box, not one step later.
- The "I currently work here" box is ticked for your current job on Workday.
- Fill no longer adds an empty second website entry.
- Military status is answered from your veteran answer.
- With Agreements on, terms and consent boxes are ticked.
- The Companion reads a job description shown inside an embedded frame
  (iCIMS), and no longer saves a blank job when it can't read one.
- An application form inside the page's own embedded frame (iCIMS) is found,
  so Autofill is offered.
- Dropdowns showing "Make a Selection" (iCIMS) are treated as empty and filled.
- Month, Day and Year boxes get only their own part, and a current job never
  gets an end date.

### Security

- Dependency bumps for published advisories: PyJWT 2.15.1 and urllib3 2.8.0
  (backend); brace-expansion, DOMPurify and ip-address (frontend lockfile).

## [0.6.0] — 2026-09-24

### Breaking changes

- None. The one migration adds a column and runs by itself at startup;
  MCP tools and API routes are unchanged.

### Added

- **Agent inbox.** Jobs an agent proposes live on their own page with their own
  words, and every proposal says who filed it: "Proposed by <agent name>" or
  "Queued by you". A new migration records the filer and marks the jobs you
  queued from the web app before this release as yours.
- Settings and Profile are split into tabs you can link to directly; unsaved
  edits still warn before you leave, across tabs too.
- **Gender options.** Profile › Autofill adds Non-binary and Prefer to
  self-describe (with a box for your own words) beside Male, Female and
  Decline to answer. With diversity consent on, the Companion picks the form's
  matching option ("Non-binary", "Nonbinary", "I prefer to self-describe"…)
  and types your words only into a box that asks for them; a form without
  the option is left for you. Answers you already saved keep working.

### Changed

- Plain words everywhere: one name per thing across the web app, the
  Companion extension and the server's error messages, which now say what
  happened and what to do next instead of showing technical detail.
- Long lists keep their toolbar (and, where the table fits, its header) in view
  while you scroll, and say so when a list is cut off at 500 rows.
- **Applications is now Jobs**, since the page lists your saved jobs as well
  as your applications, and its filter reads Tracked · Yours · Agents.
  Tracked (formerly All) shows the same jobs as before: agent-found jobs
  nobody has proposed or applied to are under Agents. Links and bookmarks to
  `/applications` keep working. Analytics keeps All, which there means every
  application.
- "Which model should I pick?" (Settings › AI & models) compares the two
  models in words and links OpenAI's and Google's own pricing pages, instead
  of quoting prices that go out of date.
- The "restrictive covenant" question in Profile › Autofill now says what one
  is: "Such as a non-compete or non-solicit agreement."

### Fixed

- **Privacy:** when autofill asks the AI how to fill a field, your diversity
  answers (race, gender, veteran and disability status) are sent only if
  diversity consent is on. Before, they reached the AI provider even with it
  off.
- Pressing Queue twice quickly no longer creates two proposals for the same job.

## [0.5.0] — 2026-09-23

### Breaking changes

- **Postgres is gone.** The compose file no longer has a `postgres` service or
  `pgdata` volume, and the backend no longer imports a Postgres database —
  v0.4.0 was the release that did that. **On v0.3.0 or older? Update to v0.4.0
  first**; `./scripts/update.sh` now spots an old Postgres volume that was never
  imported, stops before changing anything, and prints the steps
  ([`docs/UPDATING.md`](docs/UPDATING.md#coming-from-v030-or-older)). If an
  older copy of the script already moved you past v0.4.0 and the app came up
  empty, your data is still in the old volume and the same steps recover it.
- `LEGACY_DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  and `POSTGRES_HOST_PORT` are no longer read; leaving them in `.env` is
  harmless. The `legacy-postgres` extra and `python -m
  app.tools.migrate_from_postgres` are removed.

### Changed

- A fresh install downloads and runs two containers instead of three: no
  Postgres image (about 170 MB to download, 660 MB on disk), no idle container,
  no port 55432, no wait at first start.
- After an update, `update.sh` suggests removing the old Postgres volume and
  the `postgres:16` image when they are still on disk; `docs/UPDATING.md` has a
  new "Freeing disk space" section.

### Fixed

- `update.sh` no longer stops in git's pager (`:`) while listing the commits it
  brought in, which hid the extension and MCP reminders printed after it.

## [0.4.0] — 2026-09-23

### Breaking changes

- **The database is now `data/maestro_cs.sqlite3`.** Existing installs are
  imported from Postgres automatically at the first boot of this release
  (verified by row count and content hash; the old volume is left in place).
  Keep your `POSTGRES_*` values in `.env` until the import has run;
  `./scripts/update.sh --check` reports which database is live. The import
  fails closed — if the `postgres` service cannot be reached, or the copy does
  not verify, the backend refuses to start and says why, and nothing is
  deleted. The next release deletes the `postgres` service entirely: install
  this one first.
- **`DATABASE_URL` accepts only `sqlite:///` URLs.** Anything else — a
  Postgres URL in either spelling included — is refused at startup with a
  message saying what to do instead. Leave it unset and the file is derived
  from the new `DATA_DIR` setting (default `/app/data`, where compose mounts
  `./data`). The other new setting, `LEGACY_DATABASE_URL`, is the one place a
  Postgres URL still belongs: compose builds it from your `POSTGRES_*` values,
  and it names the source of the first-boot import.
- **The migration history is squashed to one SQLite baseline**
  (`871d0425b64c`). The Postgres chain survives only inside the importer, so a
  branch carrying a revision parented on the old chain will not apply after
  this release — rebase it onto the baseline.
- **`applied_at`, and the applications list's `created_after` / `created_before`
  filters, now require a UTC offset.** A naive timestamp is refused at the
  boundary with a 422 instead of failing at write time with a 500.

### Added

- **`SQLITE_JOURNAL_MODE`** in `.env` — set it to `DELETE` for a filesystem
  that cannot support WAL; the default (WAL) is right everywhere else.
- **`python -m app.tools.backup_db`** takes an online snapshot of the database
  while the stack runs, and **`python -m app.tools.migrate_from_postgres`** is
  the first-boot import as a command you can run yourself.
- **PDF engine probe** on `GET /api/setup/status` (`engines`), `render_note` on
  render responses when a LaTeX template is rendered through Typst because TeX
  is missing, `engine_available` on templates, a Typst cover letter
  (`cover_letter.typ`), and **`MAESTRO_CS_PDFLATEX`** to name a pdflatex binary
  outside the usual locations (host/venv backends; the image already has TeX).

### Changed

- The backend test suite needs no database service: each test process gets its
  own throwaway SQLite file when `TEST_DATABASE_URL` is unset. When it is set,
  it must be a `sqlite:///` file URL; one under `data/` or naming the app's own
  database is refused.
- psycopg moved into an optional `legacy-postgres` extra, which leaves with the
  `postgres` service next release. A source install that has to import a
  Postgres database needs `pip install -e ".[dev,legacy-postgres]"`.
- `docs/agent-prompts/` is replaced by generic skills in `docs/skills/`:
  `job-hunt`, an autonomous `apply-session` (which also replaces
  `manual-apply-session`), and `customize-job-skills`, which suggests skills
  from what your agent knows about you and your data, asks a few questions, and
  builds your own version or a new skill with your client's skill creator and
  scheduler. `apply-session` asks you only for information the app doesn't
  have, plus one yes per application before it submits.
- The user docs are rewritten for someone new: a plain opening and glossary in
  the README and Getting Started, a five-step first run, and far less jargon.
  The full update procedure (by hand, backups, rolling back, the Postgres
  import) moved to [`docs/UPDATING.md`](docs/UPDATING.md); the extension's
  internals moved to `extension/INTERNALS.md`; development mode and LLM tracing
  moved to `CONTRIBUTING.md`. The docs no longer point to a `⋯` menu in the
  extension panel, which no longer exists.

### Fixed

- **Security:** Next.js 16.3.6, which fixes a critical remote-code-execution
  advisory in its image optimizer (GHSA-2xp9-vwfh-vxw4), plus updated
  `fast-uri`, `hono`, `js-yaml`, `qs` and `sharp` for their advisories.
- Cover-letter regeneration and document upload commit before their LLM call,
  so a slow model no longer holds the database's write lock while it thinks.
- Contact URLs with `~`/`_` in the shared header partial no longer corrupt the
  link target (resume and cover letter). The header also compiles for a contact
  without a location. User templates `carlito_dense` and `harshibar` pass
  `\href` targets through `latex_escape_url` the same way, and existing
  installs are resynced at seed time.

## [0.3.0] — 2026-08-29

### Breaking changes

None.

### Added

- **Claude Desktop extension (`.mcpb`).** `mcpb/maestro-career-studio.mcpb`
  installs the MCP server from Claude's own Settings → Extensions dialog — no
  terminal, no config file, no host Python; the shim runs the server inside
  the backend container. One install covers Claude Desktop and Claude Code
  sessions running inside the Claude app. `scripts/check_mcpb_bundle.py` gates
  the bundle in CI.

### Changed

- `scripts/setup-mcp.sh` slimmed down now that the extension and plugin routes
  cover the common clients; it remains the route for Cursor, Windsurf and
  other stdio clients, a backend outside Docker, and scoped profiles.
- README and Getting Started reorganized around the extension/plugin installs,
  with hand-written client-config fallbacks (Claude Desktop JSON, Codex TOML)
  documented for when a packaged install fails.
- Install docs now state the image **download** size (~1 GB compressed) ahead
  of the unpacked footprint (~3–4 GB), and list Git as a prerequisite.
- Scoped MCP profiles are presented as an opt-in customization everywhere:
  every install route defaults to `full`, the Claude extension's **Tool
  profile** field or a hand-edited config entry scopes it, and the agent
  prompts no longer read as if they require the `hunt`/`apply` profiles.

### Fixed

- The two marketplace plugin manifests (`.claude-plugin/plugin.json`,
  `.codex-plugin/plugin.json`) now carry the release version — they had
  silently stayed at `0.1.2` through two releases.

## [0.2.0] — 2026-08-28

### Breaking changes

- **The compose project name is now fixed to `maestro-career-studio`.**
  `docker-compose.yml` sets it explicitly, because the shipped plugin manifest
  has to name the container as a literal (Codex plugin manifests support no
  `${VAR}` interpolation). This is a **no-op for a normal install** — cloning
  the repo already produced that name. It is *not* a no-op if your stack's
  project name came from a differently-named directory: that stack points at a
  different Postgres volume and comes up **looking empty rather than failing**.
  If that is you, set `COMPOSE_PROJECT_NAME` to your old name in `.env` before
  updating; it still overrides, and it stays the supported way to run two
  stacks side by side.

### Added

- **Install the MCP server from a marketplace.** `claude plugin marketplace
  add` / `codex plugin marketplace add` against this repo, then install
  `maestro-career-studio` — no paths to edit and **no host Python**, because
  the server runs inside the backend container you already started. The `mcp`
  extra is now baked into the image so the container can be the MCP server.
  Claude Desktop is a separate surface and still needs its own entry.
- **A three-part install story** in `docs/GETTING_STARTED.md`: the app is Part
  1 and the only required one; the assistant and the extension are independent
  optional add-ons.

### Fixed

- `prepare_application_pdf_upload` now reports the upload path **the browser
  can open**, not the in-container path it wrote to.
- Requests are no longer paused as "offline" against a local API.
- `scripts/setup-mcp.sh`: dropped a `claude mcp add` scope the CLI never had,
  and a venv check that never ran. Added `--write-desktop-config`, which
  refuses while Claude Desktop is running and backs the file up first.
- `.gitignore`'s `.mcp.json` rule is anchored to the repo root — unanchored, it
  swallowed the shipped plugin payload at `plugins/*/.mcp.json`.

## [0.1.2] — 2026-08-26

### Changed

- **`.env.example` now ships in pull mode.** `IMAGE_REGISTRY` and
  `IMAGE_TAG=latest` are set rather than commented, so a fresh
  `cp .env.example .env && docker compose up -d` DOWNLOADS the published
  multi-arch images instead of compiling TeX Live. Contributors comment
  `IMAGE_REGISTRY` out and keep using `--build` — see CONTRIBUTING. Existing
  installs are unaffected: `update.sh` never edits your `.env`, and it reports
  the two new keys as drift rather than changing modes under you.

## [0.1.1] — 2026-08-26

**The first public release.** Everything before this point predates the
changelog, so the entries below cover only the final pre-release round — the
rest of the product is the baseline this file measures from.

*(A `v0.1.0` tag exists but was never released: it landed on a commit whose
image workflow could not publish, and the tag ruleset — correctly — refused
to let it move. No images, no Release, no consumers; this tag supersedes it
per the policy above.)*

### Added

- **An update path.** `scripts/update.sh` moves an installed instance to the
  newest released version in one command: it backs the database up first, moves
  the checkout to the newest `v*` tag, reports `.env` drift without editing the
  file, brings the images to that same tag, waits for the stack to be healthy,
  and names the two surfaces Docker cannot update (the unpacked extension and
  the MCP client registration). `--check` answers "am I up to date?" and mutates
  nothing; `--force` overrides the dirty-tree refusal.
- **Version identity.** `APP_VERSION` is baked into both images at build time
  and reported by `GET /api/version` alongside the live Alembic schema revision.
  A Settings → About card shows both, and the app raises a persistent banner
  when the frontend and backend images turn out to be different versions — the
  stale-image failure that previously had no symptom at all. A version starting
  with `dev` means "locally built, do not compare" and suppresses the banner.
- **Prebuilt multi-arch images** published to ghcr.io on every `v*` tag, so a
  fresh install downloads instead of compiling TeX Live.
- **Release discipline.** This file, plus a maintainer checklist at
  [`docs/RELEASING.md`](docs/RELEASING.md).

### Changed

- The `latest` image tag now follows tagged releases only. A
  `workflow_dispatch` build publishes `dev-<sha>` and no longer overwrites
  `latest` with an unreleased build.

### Breaking changes

- None.

<!-- Template for the next release — copy, do not accrete. Drop any heading with
     nothing under it, but never drop "Breaking changes" when there is one.

## [0.2.0] — YYYY-MM-DD

### Breaking changes
### Added
### Changed
### Fixed
### Removed
-->
