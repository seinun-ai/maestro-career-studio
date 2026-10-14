# Chrome Web Store listing notes

The owner submits this listing using the checklist in
[RELEASING.md](../docs/RELEASING.md#chrome-web-store). Store distribution starts
unlisted; these notes do not mean the extension is published yet.

## Single purpose

Maestro CS Companion helps you prepare and track job applications in your own
Maestro Career Studio: save the job you are viewing, choose or tailor a resume,
fill the application from your saved answers, and record its status. These
actions share one side panel and your local Maestro backend. The Companion
never submits an application. It advances to the next page only when you start Apply, with full automation on in Maestro, and then stops on the review page.

## Permission justifications

| Permission | Why this purpose needs it |
|---|---|
| `storage` | Store the backend and app addresses, fill mode and the Keep a fill log choice (off unless the user turns it on) in Chrome settings sync; remember the current application's panel state and learned form-control moves in local browser storage. Career history and saved answers stay in Maestro's backend. |
| `tabs` | Bind the panel to the tab you are viewing and clear that binding when it leaves a job page, including navigation to browser settings or a local file. Without this permission Chrome omits those destination URLs and the panel can retain the previous job. See [INTERNALS.md, "`tabs` stays"](INTERNALS.md#install-internals) for the measured behavior. |
| `webNavigation` | Enumerate the page's frames to find embedded application forms and detect when an application frame finishes navigating, so the panel reads the current form. |
| `scripting` | Inject the packaged content scripts after you press a panel action on a tab opened before installation or reload. This lets capture and filling work without asking you to reload the page first. |
| `sidePanel` | Show the job, resume, fill and tracking steps beside the posting or application form, opened from the toolbar or shortcut. |
| `http://*/*`, `https://*/*` host access | Read job postings and fill application forms on employers' sites and embedded hiring platforms, whose domains cannot be enumerated in advance; reach your configured Maestro backend. Scripts wait for a Companion request before reading a posting or filling a form. Subframes receive your data only after the existing form or application-flow check passes. |

## Code and data disclosures

**No remote code.** Every script is packaged with the extension. The backend
returns job data, answers and files; the extension does not download or execute
remote JavaScript.

**No data collected by the developer.** The developer receives no browsing
history, career data, answers, usage reports or crash reports. Job captures and
form-filling requests go to the user's own Maestro backend. Optional AI help
sends content from that backend to the AI provider the user configures, under
that provider's policy.

The local usage log records field labels, option texts, outcomes, site hostnames
and timestamps, never typed answers or profile text. Local run traces keep the
latest 50 runs. Both are off unless the user ticks **Keep a fill log** on the options page, next to a plain description of what it keeps; nothing is recorded before that. Chrome sync
handles extension preferences. See the [privacy policy](../PRIVACY.md) and
[Companion README](README.md#privacy-and-telemetry) for retention and deletion.
Use the public repository's `PRIVACY.md` URL for the listing's privacy-policy
field.

## Five screenshots to take

The panel was repainted (direction C: progress bar, Next card, icon header), so shots 1-4
need retaking before the next store submission.

Take each at **1280 x 800 pixels** with the side panel beside a sample job or
application page. Use fictional career data and employer examples throughout;
check that no real contact details, answers, credentials or browser accounts
are visible.

1. **Save a job:** Job step with an editable title, company and job description,
   plus the scored base-resume choices after saving.
2. **Prepare a resume:** Resume step with the base-versus-tailored choice and a
   completed tailored resume showing its PDF and score.
3. **Fill and review:** Fill step after Autofill, showing filled fields, any
   remaining questions, and Check before you submit.
4. **Track an application:** Track step with the chosen resume and Draft or
   Applied status, beside the sample application.
5. **Connect to Maestro:** Extension options dialog with both addresses and
   the Test connection result reading "Connected."
