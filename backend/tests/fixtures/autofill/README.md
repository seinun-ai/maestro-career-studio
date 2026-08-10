# Extension fixtures

Two corpora, one directory, because the PII guard below has to cover both of
them and one guard nobody can route around is worth more than two tidy
directories:

* **control shapes** (everything without a prefix) — reconstructions of the ATS
  control shapes the extension currently fails on, expressed as harness field
  specs (`tests/extension_harness.run_profile_fill`);
* **page shapes** (`detect_*.json`) — whole pages for the detection gate,
  expressed as URL + attributes + text (`run_detect`).

The prefix is what tells them apart, and the control-shape corpus is defined by
EXCLUSION — so a new prefix that `fixture_names()` does not know about is
silently handed to the fill driver as a form. A fixture filed under the wrong
one fails in that corpus's validator, naming the keys that gave it away.

## Where the labels come from (control shapes)

Every label in a control shape is either **verbatim** from `GET
/api/autofill/telemetry/summary` — listed per fixture under
`telemetry_verbatim` — or **reconstructed** from the vendor's naming
convention, described per fixture under `reconstructed`.

Telemetry signatures are the ground truth on purpose. They are literally what
`labelFor()` produced on the live page, and they are value-free *by schema*:
`AutofillFieldObservation` has no value column (see
`app/schemas/autofill_telemetry.py`). Nothing personal ever entered them, so
nothing has to be scrubbed out of them.

A page shape has no telemetry behind it — autofill telemetry records field
labels, and a page is not a field — so `detect_*` fixtures carry no
`telemetry_verbatim` and their `reconstructed` note has to carry the whole
provenance claim: for each part of the page, which documented convention or
which line of the extension-simplification design §5 it came from (`git show
1db5ca2:docs/plans/2026-07-27-extension-simplification-design.md`). "Everything" is the expected first word of that note.

## Never paste captured DOM in here

These fixtures ship in the public repository, so a fixture carrying a real
value is published along with it. Do not
`copy(el.outerHTML)` from a live application and sanitize it by hand — build
the shape from the telemetry signature instead.

`test_extension_fixture_corpus.py` enforces this mechanically: no `@`, no
`+1`, no `value=`, no `linkedin.com/in/`, no HTML tag, no run of five or more
digits anywhere in these files. The guard is absolute rather than
allowlist-based so it cannot be quietly eroded. If a later fixture genuinely
needs an address, an email or a phone number, pass it at the call site —
`run_fixture(tmp_path, name, profile={...})` replaces the fixture's profile —
rather than weakening the guard.

## Format — control shapes

```jsonc
{
  "reproduces": "one line: which control shape this is",
  "vendor": "workday",
  "changed_by": "which plan task will change this fixture's characterisation",
  "telemetry_verbatim": ["<labels quoted from the summary>"],
  "reconstructed": "which fields were reconstructed, from what, and why",
  "scenario": {
    "fields": [{"label": "...", "kind": "text", "hidden": true}],
    "profile": {},
    "employment": [],
    "eeo_enabled": false
  }
}
```

`scenario` is exactly the keyword arguments of `run_profile_fill`, nested so
the loader can never mistake a metadata key for a scenario key. Field specs
accept every flag `run_profile_fill` documents.

Load them with `load_fixture` / `run_fixture` from `tests.extension_harness`.

## Format — page shapes (`detect_*.json`)

```jsonc
{
  "reproduces": "one line: which page this is, and which tier it is the case for",
  "vendor": "greenhouse",
  "reconstructed": "where every part of the shape came from",
  "page": {
    "url": "https://boards.greenhouse.io/acme/jobs/701",
    "text": "what document.body reports as its text",
    "jsonLd": [{"shape": "bare|array|graph", "types": ["JobPosting"]}],
    "elements": [{"tag": "input", "attrs": {"type": "file"}, "text": ""}]
  }
}
```

`attrs` are the element's real attributes, matched by a real (small) selector
engine — the gate *is* its selectors, so answering them by string equality
would test nothing.

**JSON-LD is declared as a shape, never written out.** The guard above rejects
`@`, and every JSON-LD key begins with one; the harness builds the document
from `shape` + `types`, burying the `JobPosting` behind a sibling so a walk
that only reads the first node cannot pass. `{"malformed": true}` gives one
script text that is not JSON.

Load them with `load_detect_page` / `run_detect_fixture`, and pass a page
inline to `run_detect` for a case that is a boundary rather than a real page.
