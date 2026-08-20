"""The panel's session entry — one shape, one file.

WHAT MUST STAY IN SYNC: `entry()`/`PICKED_ENTRY` are the store shape
`sessionEntryFrom` (`extension/panel/panel.js`) writes and `restorableSession`
(`extension/shared/decisions.js`) reads back; a key added on either side belongs
here, or the writer and the reader are being tested against two different
shapes. Since R-C every field in that entry is read back — see
`sessionEntryFrom`, which dropped the three that were not.

WHY A MODULE RATHER THAN A COPY PER FILE, decided when
`test_extension_panel.py`'s section 13 split out. The obvious alternative was
to duplicate
these six names into the new file — cheap, no import, and wrong for this
particular shape: the SUBJECT of the split is that one key carries one entry
between two surfaces, so two copies of it drifting is the exact failure both
sides exist to catch, and each copy would go on passing while it did. A
duplicate is defensible for an incidental constant; it is not defensible for
the contract under test.

The addresses travel with the shape because the entry is SCOPED to them:
`origin` and `tenant` are two of `restorableSession`'s three guards, and an
apply URL the backend cannot name is the page on which the remembered pick is
the only thing there is (see the comment on `LIGHTNING_APPLY_URL`).

Nothing else belongs here. The node harness, the drivers and the source reads
are `tests/extension_harness.py`'s and each test file's own — this module is
data, imports nothing from the extension, and must stay that way.
"""

import time


GREENHOUSE_ORIGIN = "https://job-boards.greenhouse.io"
LIGHTNING_TENANT = f"{GREENHOUSE_ORIGIN}/lightningai"
COHERE_TENANT = f"{GREENHOUSE_ORIGIN}/cohere"

POSTING_URL = "https://job-boards.greenhouse.io/lightningai/jobs/99"
# The next page of the same wizard: same tenant, a url the backend cannot name.
# A pick is READ BACK on a page like this rather than on the posting, and the
# choice of page is the whole point — `restorableSession`'s "the backend wins"
# rung tolerates a tenant mismatch when `/api/jobs/match` names the very job the
# entry does, so on the posting page the tenant is not the guard doing the work.
# On an apply URL the backend knows nothing, which is precisely when the
# remembered pick is worth having and precisely when its scope is all there is.
LIGHTNING_APPLY_URL = f"{POSTING_URL}/apply"


def entry(**overrides):
    """The bridge entry as a PRE-R-C panel wrote it — deliberately, and this is
    the label that keeps it from being tidied up.

    IT CARRIES `attachedBase` AND `guidedArmed`, which R-C dropped from
    `sessionEntryFrom`. That is not drift left behind: it makes this fixture
    the suite's standing sample of the shape sitting in every profile that ran
    an earlier build, so every test that restores from it is also exercising
    the upgrade path for free. Deleting the two keys to "match the writer"
    would silently retire that coverage — the writer has its own pin
    (`test_extension_panel_score.py`), and this object's job is the opposite
    one: to be the OLD shape, read back.

    (`claimed` is the third key R-C dropped and is deliberately NOT here: the
    entries below name no application or name one plainly, and the cases where
    a stale `claimed` is the subject are explicit in
    `test_extension_panel_job.py`'s legacy-entry section, which writes its own
    literal so the reader can see exactly what is being restored.)

    `at` is a LIVE clock, not a frozen number: freshness is one of the three
    guards, so an entry stamped at a constant would start failing the day the
    fixture aged past the TTL — and would then be refused for a reason no test
    here is about.

    NOT `_entry`, which is what it was called while it lived in one file. A
    leading underscore says "private to this module", and the whole reason this
    function moved is that it is not.
    """
    return {
        "origin": GREENHOUSE_ORIGIN, "tenant": LIGHTNING_TENANT,
        "at": int(time.time() * 1000), "applicationId": "app-remembered", "status": "draft",
        "jobId": "job-lightning", "company": "Lightning AI",
        "title": "Research Engineer", "pdfReady": True, "touched": False,
        "attachedBase": None, "baseSlug": "ai_ml_engineer", "guidedArmed": False,
        **overrides,
    }


# The same shape with NO application behind it — "the job is in the library, a
# base has been picked, and nothing has been tailored yet", which is how a user
# arrives at the Resume stage and is also the entry `restoreSession`'s
# `if (entry.applicationId)` guard exists for. `at` is filled per run:
# freshness is one of the guards. Carries the pre-R-C keys for the reason
# `entry()` above spells out — it is kept as the OLD on-disk shape on purpose.
PICKED_ENTRY = {
    "origin": GREENHOUSE_ORIGIN, "tenant": LIGHTNING_TENANT,
    "at": None,
    "applicationId": None, "status": "draft", "jobId": "job-lightning",
    "company": "Lightning AI", "title": "Research Engineer",
    "pdfReady": False, "touched": False, "attachedBase": None,
    "baseSlug": "ai_ml_engineer", "baseArmed": False, "guidedArmed": False,
}
