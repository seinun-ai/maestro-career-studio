# Chrome Web Store listing notes

The owner submits this listing using the checklist in
[RELEASING.md](../docs/RELEASING.md#chrome-web-store). The listing is public:
<https://chromewebstore.google.com/detail/maestro-cs-companion/bppkeipififkepldkogmfpkkhoakgndl>.

## Single purpose

Maestro CS Companion helps you prepare and track job applications in your own
Maestro Career Studio: save the job you are viewing, choose or tailor a resume,
fill the application from your saved answers, and record its status. These
actions share one side panel and your local Maestro backend. The Companion
never submits an application. Autofill stays on the page you are on. With full
automation on in Maestro, **Apply** takes the job you are viewing through its
application: it fills each page, presses Next, signs in or makes an account on
known application sites with the job-site login you saved in Maestro, and
stops on the review page. You press Submit.

## Permission justifications

| Permission | Why this purpose needs it |
|---|---|
| `storage` | `chrome.storage.sync`: the backend and app addresses, fill mode and the Keep a fill log choice (off unless the user turns it on). `chrome.storage.local`: learned form-control moves (at most 200, each dropped after 60 days unused). `chrome.storage.session`: the job each tab is on, the application each tab is working through, and the state of a running Apply, held in memory and cleared when the browser closes; a tab's job is also forgotten when the tab closes. Career history and saved answers stay in Maestro's backend. |
| `tabs` | Bind the panel to the tab you are viewing and clear that binding when it leaves a job page, including navigation to browser settings or a local file. Without this permission Chrome omits those destination URLs and the panel can retain the previous job. See [INTERNALS.md, "`tabs` stays"](INTERNALS.md#install-internals) for the measured behavior. During Apply: open the job's application link in the run's tab (`tabs.update`), read that tab's address and load state while it waits for the next page (`tabs.get`, `tabs.onUpdated`), follow the run into a tab the application opens (`tabs.onCreated`, `tabs.query` in the current window), and forget a tab's job when it closes (`tabs.onRemoved`). |
| `webNavigation` | Enumerate the page's frames to find embedded application forms and detect when an application frame finishes navigating, so the panel reads the current form. During Apply the same frame list reaches the form on each page that loads after Next. |
| `scripting` | Inject the packaged content scripts after you press a panel action on a tab opened before installation or reload. This lets capture and filling work without asking you to reload the page first. |
| `sidePanel` | Show the job, resume, fill and tracking steps beside the posting or application form, opened from the toolbar or shortcut. |
| `http://*/*`, `https://*/*` host access | Read job postings and fill application forms on employers' sites and embedded hiring platforms, whose domains cannot be enumerated in advance; reach your configured Maestro backend. Scripts wait for a Companion request before reading a posting or filling a form. Subframes receive your data only after the existing form or application-flow check passes. During Apply, press Next on application pages, and on known application sites type the job-site login saved in Maestro into that site's own sign-in or account form, in the top frame only. |

## Code and data disclosures

**No remote code.** Every script is packaged with the extension. The backend
returns job data, answers and files; the extension does not download or execute
remote JavaScript.

**No data collected by the developer.** The developer receives no browsing
history, career data, answers, usage reports or crash reports. Job captures and
form-filling requests go to the user's own Maestro backend. Optional AI help
sends content from that backend to the AI provider the user configures, under
that provider's policy.

**Credentials.** The job-site email and password are stored only in the
user's own Maestro, in its local secrets file
(`settings/secrets/job-site-login.json`, mode 0600). The Companion fetches
them from the local backend (`POST /api/companion/job-site-login`, admitted
only for the Companion's origin) only while full automation is on in Maestro,
for a job the user has queued, and types them only on known application sites
(a fixed list in `shared/ats-hosts.js`), into that site's own form in the top
frame. Each fetch is recorded as a `login_shared` event without the value. The
login never goes to the developer, an AI model, a trace, a log, the fill log or
the panel. A failed sign-in is never retried.

**What reaches an application site.** What the Companion types into an
application goes to that site. With Apply, each page it moves past with Next,
and the login it signs in or makes an account with, reach the site before the
user presses Submit.

**Input watching.** While an Apply run waits for the user, the content script
notes which kinds of gestures the user used to fix a field (clicks, typing and
a few key names such as ArrowDown or Enter, never values) and keeps them in
this browser, to try first on that kind of field next time.

**Page snapshots for the Reasoning model.** When an Apply run is stuck on a
page and Think when stuck is on, the Companion sends the user's backend a
snapshot of the page with no answers in it (questions, whether each is filled,
options, buttons, error lines). The backend sends it to the AI provider the
user chose.

The local usage log records field labels, option texts, outcomes, site hostnames
and timestamps, never typed answers or profile text. Local run traces keep the
latest 50 runs. Both are off unless the user ticks **Keep a fill log** on the options page, next to a plain description of what it keeps; nothing is recorded before that. Chrome sync
handles extension preferences. See the [privacy policy](../PRIVACY.md) and
[Companion README](README.md#privacy-and-telemetry) for retention and deletion.
Use the public repository's `PRIVACY.md` URL for the listing's privacy-policy
field.

## Privacy practices declarations

Chrome's Privacy practices tab asks what the extension handles, even when the
developer receives none of it. Declare by category:

| Data category | Declare | Why |
|---|---|---|
| Personally identifiable information | Yes | Name, email, phone and address from the user's profile are filled into application forms. |
| Authentication information | Yes | The job-site email and password are typed into sign-in and account forms on known application sites. |
| Website content | Yes | Posting text, form questions and options, and value-free page snapshots go to the user's own backend, and from there to the user's AI provider. |
| Web history | Yes | Saved job and application links; with the fill log on, site names and times. |
| User activity | Yes | While a run waits, the kinds of gestures the user used to fix a field are kept in this browser. |
| Health information | Yes (conservative) | A voluntary disability self-identification answer can be filled, only with the user's standing EEO consent. |
| Financial and payment information, personal communications, location | No | A salary expectation is not payment data; an address is personal information, not device location. |

Certify all three: the data is not sold to third parties, not used or
transferred for purposes unrelated to the single purpose, and not used to
determine creditworthiness or for lending.

## Five screenshots to take

Apply shows only with full automation on in Maestro, so a reviewer will not see
it without Maestro; the screenshots carry it.

Take each at **1280 x 800 pixels** with the side panel beside a sample job or
application page. Use fictional career data and employer examples throughout;
check that no real contact details, answers, credentials or browser accounts
are visible.

1. **Save a job:** Job step on a fictional posting, with two base resumes
   scored for the job, each with its colour square.
2. **Apply gets ready:** the live checklist (save, score, resume, queue,
   tailor, PDF, open the application) with its **Stop** button.
3. **Moving through pages:** the run card in the middle of an application, with
   its answered list and a note such as "Drafted from your history: read it".
4. **Stops before Submit:** **Ready to submit** on the review page, with the
   **Check before you submit** list and Submit untouched.
5. **Connect to Maestro:** Extension options dialog with both addresses and
   the Test connection result reading "Connected."
