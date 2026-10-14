# Browser fixtures

Hand-written offline pages that reproduce how a live ATS widget BEHAVES (what it
accepts, when it commits, where its popup renders, how it closes). Never
captured DOM; never real names, emails, phone numbers or addresses
(test_fixture_privacy.py enforces it; public institution names are fine).

## The fixture rule

A fixture reproduces a behaviour that field notes observed on a LIVE page, or it
is labelled adversarial (`adversarial_*.html`, with a comment saying what it
models). Never model a vendor from memory: the guessed Workday fixtures passed
while live Workday failed. The Workday pages follow
`docs/reports/2026-09-26-workday-field-interactions.md` (local-only field notes;
the `§` numbers in each fixture's comments point into it). Where the notes are
silent, a fixture takes the simplest behaviour consistent with them and says so
in a comment. A page that models no vendor and no observed behaviour belongs
inline in its test, not here.

## The oracle

Every Workday, adversarial and custom-widget fixture keeps `window.__oracle[<field>]`: the
value the fake APP holds — what live Workday would save — as distinct from what
the page shows. It is set only by the widget's own commit path (a real leave for
text and dates, the result row's radio or checkbox for a search, the option
click that fills the backing input for a popup, the finished upload for a file).
The engine never reads it (`test_the_extension_never_reads_the_oracle` pins
that); tests assert on it, so a false "verified" fails. Scripts use
`window.__oracle = window.__oracle || {}` so fixtures composed on one page share
it; keys are unique across fixtures, and each is set at load (except
`workday_sections.html`'s `"<entry>/<question>"` keys, which appear with an
entry's first commit):

- `null` — the app never received a commit for the field (the text boxes start so);
- `""` / `[]` — the app holds an empty value (a commit of nothing, or a widget
  whose empty state is itself app state, like a popup on "Select One").

Tests read it through `tests/browser/pages.oracle(page, key)`, which raises on a
missing key, so a typo never reads as "nothing committed".

| Fixture | Notes | Oracle keys |
|---|---|---|
| `workday_text.html` | §1 — draft on input, commit on a real focusout | `city`, `zip` |
| `workday_search.html` | §2 — press, Enter on key-up, staged reused rows, radio/checkbox commits, virtualized skills | `heard`, `school` (string), `skills` (array) |
| `workday_listbox.html` | §3, §8a — popup button + hidden backing input; outside click hides, `aria-expanded` stays `true` | `degree`, `auth` |
| `workday_date.html` | §6 — the wrapper validates when focus has left it; Year moves focus to Month; MM/DD/YYYY variant | `from`, `signed` |
| `workday_upload.html` | §7 — input emptied at once; the uploaded-file row is the proof | `files` |
| `workday_sections.html` | §5, §4 — Add / Add Another, unnamed Delete, "I currently work here" removes To | `entries`, `deleted`, `"<entry>/<question>"` |
| `adversarial_revert.html` | §8a's unexplained revert — first pick shows, never commits, reverts when a test calls `window.__revertNow()` | `relocate` |
| `adversarial_same_text.html` | two "Other" options under different visible categories | `referral` |
| `adversarial_recipe_poison.html` | recipe poisoning: opens from the keyboard only; its first commit is taken, then taken back 700 ms later (after the engine's own verify, inside the loop's quiet period) | `shift` |
| `adversarial_trusted_only.html` | a Workday-style popup whose handlers act on trusted input only (`event.isTrusted`): the engine has none, so the honest outcome is `unsupported` | `shift_pref` |
| `adversarial_virtual_same_text.html` | `adversarial_same_text`'s two "Other" options in a virtualized popup list: eight rows rendered, the second "Other" (under "Social Media") outside the first window | `found` |
| `adversarial_search_headers.html` | a Workday-style search box (§2's gestures) whose default list groups options under header rows while its search results are flat: an option's category path differs between the two views | `arrangement` |
| `react_select.html` | a React-Select combobox (not a Workday reproduction); commits on the option click, `window.rejectClicks` refuses them | `country` |
| `popup_with_search.html` | a popup button whose dialog holds its own search box (generic, not Workday) | `fos` |
| `gem_form.html` | jobs.gem.com, live 2026-09-27 — bare text boxes labelled only by a hashed-class span above their wrappers; Yes/No radios with no name and no container, asked five ancestors up | `gem_first_name`, `gem_last_name`, `gem_email`, `gem_linkedin`, `gem_graduating`, `gem_cs_degree` |
| `icims_profile.html` | iCIMS candidate profile, live 2026-10-01, markup modelled — select2-style boxes over a hidden native select (School's hidden the way select2 does, with a 1px clip) showing "— Make a Selection —"; Month / Day / Year controls with bare labels under one row label; phone and address "Type" selects | `icims_degree`, `icims_school`, `icims_country`, `icims_state` |
| `workday_errors.html` | owner's live run 2026-10-13, run trace — a step whose Save and Continue is refused while its required upload (labelled only "Upload a file (5MB max)", seven levels under the section that says "resume") is empty: the "Errors Found" banner (a collapse button, "Error - <field>" buttons), `aria-invalid` and "The field … is required and must have a value." beside the box; fifteen skills pills already held; an optional Field of Study; with a file held, Next changes the heading | `files` (array), `step` (string), `nexts` (count of presses) |
| `workday_misses.html` | owner's live run 2026-10-13, run traces + screenshots — a visible and an offscreen robot trap beside real optional boxes; a phone-code selectinput already holding a pill; an optional empty Phone Extension; skills with two-stage results, a pill 600 ms after the click and a first "Pandas" click lost to a redraw; a required Field of Study whose full value lists nothing; search results in two stages, 300 ms then 700 ms; a Country choice that swaps the address inputs for new nodes 400 ms later | `robotWebsite`, `robotBlank`, `website`, `middleName`, `phoneExt`, `addressLine`, `cityName`, `postalCode` (text, `null`), `phoneCode` (string), `slowSkills` (array), `fieldOfStudy` (string), `countryChoice` |
| `antd_readonly_select.html` | ATS-D (an Ant Design application form), live 2026-10-14, markup captured then made-up labels — a read-only select whose combobox `<input>` is `type=search readonly role=combobox` with `style="opacity: 0"` over a sibling `.ant-select-selection-item`; its dropdown is a `role=listbox` holder of `role=option` rows rendered into `<body>`, a row click shows the pick and closes it | `antd_contact` (string, `""`) |
| `pill_buttons.html` | ATS-O (a Knockout-and-React application form), live 2026-10-14, markup captured then made-up labels — Yes/No and Degree questions drawn as `ul[role=list][aria-label=<question>]` of `li > button[aria-pressed]`; the label's required star is a CSS-only empty span (the label carries a `--required` class, so the star is not in its text); a click on another pill replaces the pick and a click on the PRESSED pill un-selects it | `pills_prior`, `pills_degree` (string, `""`), `pills_clicks` (count of pill clicks) |

Generic wizard pages (no vendor modelled; the page reader's tests and the queued run's driver tests
use them, which is why they are files and not inline): `wizard_step1.html` (a required field and a
`<button type="submit">Next</button>`; oracle `advanced`, set only by the form's own submit),
`wizard_step2.html` (a plain "Save and Continue" button; oracle `advancedStep2`), `wizard_review.html`
(a Submit, no Next; oracle `submitted`, which no test may ever see true), `wizard_confirmation.html`,
`signin.html` (oracle `typed` {email, password} as of the last input event, `signedIn` set only by the
form's own submit), `create_account.html`, `verify_code.html`, `captcha.html` (a challenge frame wrapper;
its markup is ASSUMED, not captured), `posting_external.html` (Apply link), `posting_board_native.html`
(Apply button, served under a board hostname by its test) and `closed.html`. They reproduce no
observed vendor behaviour: change one and `tests/browser/test_page_reader.py` first.

`native.html` keeps no oracle: a native control's own value (`input_value`,
`checked`) is what the page submits, so tests read that.

`tests/browser/test_fixture_fidelity.py` drives each fixture with Playwright's
trusted input and pins the behaviour above; change a fixture and that file first.

## Unfocused-window mode

Live, while the browser WINDOW is not focused, `el.focus()` / `el.blur()` still
move focus but fire no focus, blur, focusin or focusout events (§1, §6) — the
reason text and dates showed but never committed. The test page's window is
focused, so the browser fires them there. The opt-in `page_unfocused` fixture
(`tests/browser/conftest.py`, `UNFOCUSED_WINDOW`) recreates the live condition:
during a native `focus()`/`blur()` call every focus event is stopped at the
window, while trusted Playwright input and events the engine dispatches itself
still pass. `tests/browser/pages.in_both_windows(...)` runs a test in both modes;
a leave that works only in the focused mode is not a fix.

During a native `focusout` Chrome already reports `<body>` as
`document.activeElement`, which is why the date wrapper checks after the event.

## Composition

Each page's script is wrapped in an IIFE so two fixtures can never clash on a
top-level `const`; element ids (`#portal`) are still shared, so load one per
page — or, as the end-to-end gate (`tests/browser/test_fill_end_to_end.py`)
does, rename each page's `portal` when composing them into one (write it as
`id="portal"` and `getElementById("portal")` so the rename finds it).

`workday_listbox.html` updates its button's aria-label on a pick, as live Workday
does (`"<question> <value> Required"`, the question part empty on these
buttons): a static label would read "Select One" as the question once the value
changed.
