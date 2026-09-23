# Maestro CS Companion (Chrome extension)

A side panel that connects the job posting or application form you are looking
at to your local Maestro CS app.

## What it does

- **Save the job.** Grab the title, company and job description from the page
  you are reading. You can correct them before saving.
- **Score it.** See how each of your base resumes scores against this job, best
  first, or score them all with one click.
- **Pick or tailor a resume.** Use a base resume as-is, run Quick tailor, or
  open the job in the app for a custom tailoring session.
- **Fill the application.** Fill the form from your Autofill Profile, with
  optional AI help for the questions the rules cannot answer. Fields it could
  not fill are listed so you can finish them, and it can attach your tailored
  resume PDF when you ask.
- **Track it.** Mark the application Draft or Applied from the panel.

Open the panel with the toolbar icon or `Alt+Shift+J` (change it at
`chrome://extensions/shortcuts`; the shortcut needs Chrome 116 or newer, the
icon works from Chrome 114).

## Install

1. Start the app (`docker compose up`: backend on `:8001`, app on `:3000`).
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

- **Never fills** signatures or initials, passwords, or government IDs (Social
  Security, passport or driver's licence numbers). No setting unlocks these.
- **Never fills salary history** (current or past pay). It can fill a salary
  *expectation* from your profile.
- **Agreement and consent boxes** ("I have read and agree to the terms",
  attestations, arbitration or waiver boxes) are left alone unless you have
  turned on the standing agreement consent in **Profile** in the web app. Even
  then it only ticks a box and never unticks one you already ticked.
- **Voluntary EEO questions** are skipped unless you have turned on the EEO
  consent in **Profile**.
- **Never submits** a form or moves a multi-step application to the next page.
  Review everything before you submit.

## Privacy and telemetry

Everything stays on your machine: the extension talks only to your local
backend. The only data that leaves your machine is the AI calls your backend
itself makes.

When you run a fill, the extension records **which fields it found and whether
they filled** (the field's label, its type, the outcome, and a dropdown's
option texts). It **never records what you typed** or any value on the page.
Each record does carry the site's hostname and a timestamp, so over time it
amounts to **a list of where you applied and when**.

- **Clear it:** in the web app, **Analytics → Autofill coverage → Clear data**.
  This deletes the records but does not turn recording off.
- **Turn it off:** there is no switch in the panel. On `chrome://extensions`,
  click the **service worker** link on the Maestro CS Companion card, open its
  **Console** tab, and run:

  ```js
  chrome.storage.sync.set({ telemetryEnabled: false })
  ```

  Run it again with `true` to turn it back on.

## Different ports

The extension expects the backend at `http://localhost:8001` and the app at
`http://localhost:3000`. If you run them elsewhere, set both in the same service
worker console, then close and reopen the panel:

```js
chrome.storage.sync.set({ backendUrl: "http://localhost:9001", appUrl: "http://localhost:3001" })
```

There is no settings screen in the panel for this. (The built-in defaults live
in `DEFAULTS` at the top of `sw.js`.)

## Troubleshooting

- **"No job description found on this page" over a visible posting, or "The
  companion cannot see this page".** Reload the tab. This happens to tabs that
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
  application you picked is remembered for 30 minutes as you move through the
  steps, so press **Start fill** again on each page.

How it works inside: [INTERNALS.md](INTERNALS.md).
