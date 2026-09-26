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

Every Workday and adversarial fixture keeps `window.__oracle[<field>]`: the
value the fake APP holds — what live Workday would save — as distinct from what
the page shows. It is set only by the widget's own commit path (a real leave for
text and dates, the result row's radio or checkbox for a search, the option
click that fills the backing input for a popup, the finished upload for a file).
The engine never reads it; tests assert on it, so a false "verified" fails.
Scripts use `window.__oracle = window.__oracle || {}` so fixtures composed on
one page share it; keys are unique across fixtures.

| Fixture | Notes | Oracle keys |
|---|---|---|
| `workday_text.html` | §1 — draft on input, commit on a real focusout | `city`, `zip` |
| `workday_search.html` | §2 — press, Enter on key-up, staged reused rows, radio/checkbox commits, virtualized skills | `heard`, `school` (string), `skills` (array) |
| `workday_listbox.html` | §3, §8a — popup button + hidden backing input; outside click hides, `aria-expanded` stays `true` | `degree`, `auth` |
| `workday_date.html` | §6 — the wrapper validates when focus has left it; Year moves focus to Month; MM/DD/YYYY variant | `from`, `signed` |
| `workday_upload.html` | §7 — input emptied at once; the uploaded-file row is the proof | `files` |
| `workday_sections.html` | §5, §4 — Add / Add Another, unnamed Delete, "I currently work here" removes To | `entries`, `deleted`, `"<entry>/<question>"` |
| `adversarial_revert.html` | §8a's unexplained revert — first pick shows, never commits, reverts | `relocate` |
| `adversarial_same_text.html` | two "Other" options under different visible categories | `referral` |

`tests/browser/test_fixture_fidelity.py` drives each fixture with Playwright's
trusted input and pins the behaviour above; change a fixture and that file first.

What no fixture reproduces: live, `el.focus()`/`el.blur()` fire no events while
the browser WINDOW is unfocused (§1). The test page is focused, so there the
browser fires them natively — a fixture can check where focus went, not whether
the window had it. During a native `focusout` Chrome already reports `<body>` as
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
