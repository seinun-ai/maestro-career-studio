# Browser fixtures

Hand-written offline pages that reproduce how a live ATS widget BEHAVES (what it
accepts, when it validates, where its popup renders, how it closes). Never
captured DOM; never real names, emails, phone numbers or addresses
(test_fixture_privacy.py enforces it).

`workday_text.html` is deliberately STRICTER than live Workday: it accepts only
trusted (real-keyboard) input. It is a conservative bar for the engine to clear,
not evidence of what Workday itself rejects.

Each page's script is wrapped in an IIFE so two fixtures can never clash on a
top-level `const`; element ids (`#portal`) are still shared, so load one per page
— or, as the end-to-end gate (`tests/browser/test_fill_end_to_end.py`) does,
rename each page's `portal` when composing them into one.

`workday_listbox.html` updates its button's aria-label on a pick, as live Workday
does (`"<question> <value> Required"`): a static label would read "Select One"
as the question once the value changed.
