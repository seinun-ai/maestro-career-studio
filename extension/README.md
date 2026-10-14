# Maestro CS Companion (Chrome extension)

A side panel that connects the job posting or application form you are looking
at to your local Maestro CS app.

## What it does

- **Save the job and pick a base resume.** Grab the title, company and job
  description from the page you are reading, and correct them before saving.
  Saving scores each of your base resumes against the job and picks the best
  one; you can pick another.
- **Pick or tailor a resume.** Use a base resume as is, run Quick tailor, or
  open the job in the app for a custom tailoring session.
- **Fill the application.** Fill the form from your saved answers (Profile ›
  Autofill in the app), with optional AI help for the questions they cannot
  answer. Fields it could not fill are listed so you can finish them. Autofill
  also attaches your tailored resume PDF to an empty resume upload box, and
  Attach resume does it by hand.
- **Apply to one job for you** (needs **full automation** on in Settings ›
  Connected agents). The Job step shows **Apply**: it saves the job, settles the
  resume, queues the job as your yes, then works through the application in this
  tab. It fills each page, clicks **Next** itself, and stops on the review page so
  that **Submit** is yours. It asks you only when it must: a CAPTCHA, an email
  code, an account on a site it does not know or one the site refused, a job
  board's own apply button, a page it does not recognise, or a required question
  it could not answer. Answer in the page, then
  press **Resume** in the panel. Your answers are saved to your profile (with
  an Undo). After you press Submit and the confirmation page shows, the panel
  marks the job applied after 8 seconds, unless you press Undo. If the tab moves
  to some other page first, nothing is marked for you and **Mark applied** is left
  to press; **Done** on the review card ends the run without marking anything.
  If a page refuses **Next** and says why, it fixes only the fields the page names and
  stops, listing them, if that does not help. It attaches your resume before pressing
  **Next** and never presses **Next** over an empty required upload. While it gets ready
  it shows a checklist with a **Stop** button. Two switches under **Settings › AI &
  models › Form filling** steer it: **Choose the base resume for me** (picks only when
  one resume clearly wins, else asks) and **Stop after each step** (three presses:
  **Save job**, **Tailor resume**, **Start filling**).
  Running several jobs at once from a Queue view is not built yet.
  **Ready to submit** means nothing is missing: the page has a real Submit button
  and no Next, shows no error, and has no required box left empty. If the
  Companion is not sure about a page it stops and says why: "More than one Next",
  "May send the application", "No Next button found" or "Not sure about this
  page". Check it, then press **Resume**; the Companion fills what is still open
  first, and your Resume counts as "this is the last page" only when no Next is
  left on it. A page whose only button is "Continue" stops for you the same way.
  Dropdowns and Yes/No buttons are fields, never Next or Submit, so a question
  that mentions "submit" no longer stops a run. On a Workday "Start Your
  Application" page the run presses **Apply Manually** and nothing else on that
  page; if it cannot, it says "Choose how to apply" and waits for you.
  Started on the job's own posting, Apply opens the application link saved with the job instead of staying there. On a
  career site whose **Apply** button asks for a new tab, it presses the button in the same tab, but only when it leads to
  that link or to a known application site; a landing on any other site stops the run. When it waits for a step you do by
  hand, it follows you into the tab you open for the application and says "The run moved to this tab"; press **Continue
  here** and it carries on from there. If you are on the job's tab and the run waits in another one, the Job step offers
  **Move the run to this tab**; a run that is filling never moves.
  On a known application site that asks you to make an account, the run makes it
  with your saved job-site login, once, and waits up to 20 seconds for the site
  to finish before it says "Account not created" (see below). While a run is working the
  panel says "Ask opens when the run pauses"; the Ask box returns when it stops.
- **Written questions are drafted for you to read.** A required question such as
  "Why do you want to work here?" that your saved answers cannot answer is drafted
  from your career history and the job, in your own voice, about 120 words (or the
  length the question names). The row says "Drafted from your history: read it".
  It is never saved as a standing answer and never submitted for you; edit it in
  the page and press **Resume** to keep your version. **Facts only** (Settings ›
  Form filling) turns drafting off, and pay, work authorization, demographic,
  background and "have you worked here" questions are never drafted.
- **Safe defaults for questions your profile cannot answer.** From **Backed by your
  history** up, a Yes/No about membership or relatives at the company is answered
  No (Not applicable when offered), and willingness to a standard step (background
  check, drug test, references, I-9, documents) or basic means (transport,
  internet) is answered Yes, and a spouse's or household member's military service
  is answered No (or "I don't wish to answer"). Criminal or background history, salary,
  work authorization, demographic questions and your own military service are never
  defaulted, and every default is listed under **Check before you submit**, as is a
  required field that a search or a click filled for you (Field of Study, say), which no
  longer stops the run. An optional Skills box stays empty in a run.
- **Postings without built-in job data are read too.** The Job step reads the
  description from the section under a "Job Description" or "About the role"
  heading, and the title, company and location from a recorded page layout (a
  Darwinbox careers page) or the page's own heading. Darwinbox's apply page needs
  a CAPTCHA, so the run stops there and leaves the application to you.
- **Ask one question.** The **Ask** box at the foot of the Fill step takes any
  question from a form, answers it in one paragraph from your history and the job,
  and lets you copy it. It never writes into the page.
- **Track it.** Mark the application Draft or Applied from the panel.

Open the panel with the toolbar icon or `Alt+Shift+J` (change it at
`chrome://extensions/shortcuts`; the shortcut needs Chrome 116 or newer, the
icon works from Chrome 114).

## Install

1. Start the app — `maestro start` (uv install) or `docker compose up` (Docker): backend on `:8001`, app on `:3000`.
2. Open `chrome://extensions` and turn on **Developer mode**.
3. Click **Load unpacked** and choose the repo's `extension/` folder.
4. Pin the extension, then click its icon on a job posting or application form.

With the default ports there is nothing to configure. The extension has a fixed
id, **`pjmfonfapjdabkoicnelpflpjojdjgan`**, and the backend already allows that
id, so there is no id to copy and no backend restart.

**After an update**, press **Reload** on the extension's card at
`chrome://extensions`, then reload any job tabs that were already open. A tab
opened before the reload shows "No job description found on this page" even
when the description is plainly visible, until you reload that tab.

**Installed before the fixed id existed?** Reloading is not enough. On
`chrome://extensions` press **Remove**, then **Load unpacked** on the
`extension/` folder again, and check that the id shown matches the one above.
Otherwise the backend refuses the old id and the panel cannot reach it.

## What it never does

- **Without the agreement permission** (off by default), it never fills
  signatures or initials, passwords, government IDs (Social Security, passport
  or driver's licence numbers), salary history (current or past pay), or
  agreement and consent boxes ("I have read and agree to the terms",
  attestations, arbitration or waiver boxes). It can fill a salary
  *expectation* from your profile either way.
- **With the agreement permission** turned on in **Profile** in the web app, it
  may fill every field, signatures and typed-name attestations included. It
  never unticks a box you already ticked. A password box is still skipped by
  its type.
- **Voluntary EEO questions** are skipped unless you have turned on the EEO
  consent in **Profile**. Veteran status is one Yes/No question there; a Yes never
  picks a protected class for you.
- **Never clicks Submit**, at any setting. Autofill never moves a multi-step
  application to the next page either. Only **Apply**, when you start it with full
  automation on, clicks **Next**, and it stops on the review page. Review
  everything before you submit.
- **Types your saved job-site password only on known application sites**
  (Workday, Greenhouse, Lever, Ashby, iCIMS and a few more), in the page itself.
  Anywhere else it stops and waits for you to sign in. It never retries a failed
  sign-in.
- **Creates an account only on those same known sites**, in the page itself, with
  your saved login and the same password in both boxes. It ticks only the box that
  agrees to creating the account or to the privacy notice (never a marketing
  box), presses only "Create Account", and does it once. An email check, a CAPTCHA
  or a refusal (a password rule, an account that already exists) stops the run
  with **Account not created**; you finish in the page and press **Resume**. The
  password never reaches an AI model, the panel, a log or the fill log.
- **Never fills a field meant to catch robots** (a hidden "leave this blank"
  box). Optional fields it has no answer for are left blank and listed.

## Which application sites it handles

What **Apply** knows about each site, as tested in this repo. "Recorded" means a
page saved from the live site is in the test suite. Everything else it reads
generically (page text and buttons), which is the same code for every site.

| Site | Filling | Next and Submit buttons | Status |
|---|---|---|---|
| Workday | recorded pages for its search boxes, dropdowns, dates, uploads and repeating sections | one recorded marker (the footer button; its text still decides Next or Submit) | deepest coverage; a full run is still to be checked live |
| iCIMS | one recorded page (a profile step) | generic | generic; a full run is untested |
| Greenhouse | generic | generic | untested |
| Lever | generic | generic | untested |
| Ashby | generic | generic | untested |

A page it cannot sort as Next stops the run on that page, and a button with any
Submit wording is never clicked on any site. The table grows only from recorded
pages, never from memory of how a vendor looks.

## Privacy and telemetry

Everything stays on your machine: the extension talks only to your local
backend. The only data that leaves your machine is the AI calls your backend
itself makes.

**The fill log is off unless you turn it on.** Open the Companion's options
(right-click its toolbar icon, then **Options**) and tick **Keep a fill log**.
While it is on, each fill records **which fields it found and whether
they filled** (the field's label, its type, the outcome, and a dropdown's
option texts). It **never records what you typed** or what a field held.
Each record does carry the site's hostname and a timestamp, so over time it
amounts to **a list of where you applied and when**.

A fill that uses AI also keeps a **run trace**: a private, local record of how
Autofill decided each field. It includes the page's own option texts and which
option was chosen, demographic (EEO) questions included, and never anything you
typed or any text from your profile. The last 50 runs are kept.

- **Clear it:** in the web app, **Analytics → Autofill coverage → Clear data**.
  This deletes the records, the run traces and the list of fields the fill could
  not work (hosts and field shapes, never answers) but does not turn the log off.
  That list is only kept while the log is on.
- **Turn it off:** untick **Keep a fill log** in the Companion's options. Run
  traces stop too; nothing is recorded while it is off.

### Learned widget moves

Separately from telemetry, the Companion remembers, in this browser only,
**which clicks and keys worked on each kind of form control**, so the next fill
tries them first. It keeps no answers and no web addresses, but someone with
access to this browser could still work out which employers' application sites
you used, roughly when you last used each, and how often. **Forget learned
widget moves**, in the panel's Fill step, clears it.

## Different ports

The extension expects the backend at `http://localhost:8001` and the app at
`http://localhost:3000`. If you use different ports, open `chrome://extensions`,
choose **Details** on the Maestro CS Companion card, then **Extension options**.
Enter the **Backend address** and **App address**, for example
`http://localhost:9001` and `http://localhost:3001`. Use `http://` or `https://`
with a host and optional port; leave out paths, query strings and credentials.

Press **Test connection** to check the backend address, then **Save**. Testing
does not save your changes. Close and reopen the panel to use the new addresses.
The options page reads the built-in defaults from `sw.js` through the same
settings message as the panel.

## Troubleshooting

- **"No job description found on this page" over a visible posting, or "The
  Companion can't read this page".** Reload the tab. This happens to tabs that
  were open when the extension was installed or reloaded.
- **The panel cannot reach the backend.** Check the app is running. If your
  install predates the fixed id, Remove and Load unpacked again (see Install).
  If you changed ports, see Different ports.
- **Education or work-history sections are missing entries.** The extension
  cannot click "Add another". Add the blocks on the form first, then fill.
- **The shortcut does nothing.** Chrome drops a shortcut another extension
  already uses; set one at `chrome://extensions/shortcuts`, or use the toolbar
  icon. The shortcut opens the panel but cannot close it; use the panel's own
  close button.
- **Multi-step applications** may still need some fields entered by hand. The
  application you picked is remembered in that tab for as long as it stays open,
  so press **Autofill** again on each page (a run started with **Apply** moves
  through the pages by itself).

How it works inside: [INTERNALS.md](INTERNALS.md).
