"""Editing a prompt file must be a decision, not an accident.

THE MECHANIC THIS GUARDS
------------------------
`app/services/prompts.get_prompt()` returns the `settings` row `prompt.<key>`
whenever one exists. The file under `app/prompts/` is only the value used to
SEED a row that is missing. So on any install that has already read a prompt
once, the row exists and **the file is dead weight at runtime** — editing it
changes nothing.

That is deliberate: it is what lets someone customize a prompt in Settings and
keep the customization across upgrades. The cost is that shipping a prompt
improvement takes two things, not one:

1. the edit to `app/prompts/<key>.txt` (what a NEW install gets), and
2. a resync migration that rewrites the stored row **only when it still matches
   the previous default**, leaving genuine customizations alone
   (pattern: `migrations/versions/c37b89e136ad_add_job_salary_currency.py`,
   which pins the old text in `OLD_EXTRACT_JD` and compares before writing).

Skip step 2 and nothing fails. The code, the tests and the file all agree, the
running app quietly keeps following the old instructions, and the only symptom
is a shipped feature that does not seem to be on.

WHY A HASH PIN AND NOT SOMETHING SMARTER
----------------------------------------
This test cannot prove a resync migration exists or that it is correct — that
would mean parsing migrations and reimplementing their comparison. It does the
one thing that closes the actual failure mode: it makes a prompt edit impossible
to land silently. You either updated the pin deliberately, or the suite is red.

This was written after finding six drifted rows on a live database, of which
only two came from the rename that prompted the check. `gap_enrichment` had lost
its entire `library_candidates` step, and `gap_tailor` its add_keyword honesty
rule — both shipped, tested, and not actually running.

`scripts/prompt-drift.py` is the other half: this guards the repo, that one
inspects a running install.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.prompts import PROMPT_DIR, VALID_PROMPTS

LOCK_PATH = Path(__file__).resolve().parent.parent / "migrations" / "prompt_defaults.lock.json"

_REMEDY = f"""
What to do — pick ONE, deliberately:

  (a) The change should reach EXISTING installs (the usual case for a fix or a
      new instruction). Write a resync migration modelled on
      `c37b89e136ad_add_job_salary_currency.py`: pin the PREVIOUS file text as a
      constant, and UPDATE `settings` where `key = 'prompt.<key>'` only if the
      stored value still equals it. Never overwrite unconditionally — that
      destroys a user's customization without asking.

  (b) The change is cosmetic and genuinely need not reach existing installs
      (a typo in a comment, reflowing a line). No migration.

Then refresh the pin so this test goes green:

  python3 -c "import hashlib,json,pathlib; \\
d=pathlib.Path('backend/app/prompts'); p=pathlib.Path('{LOCK_PATH.relative_to(LOCK_PATH.parent.parent.parent)}'); \\
j=json.loads(p.read_text()); \\
j['prompts']={{f.stem: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.glob('*.txt'))}}; \\
p.write_text(json.dumps(j,indent=2)+chr(10))"

Refreshing the pin WITHOUT doing (a) or (b) defeats the point of the check.
"""


@pytest.fixture(scope="module")
def lock() -> dict[str, str]:
    assert LOCK_PATH.is_file(), f"missing {LOCK_PATH}; it is the pin this test compares against"
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))["prompts"]


def test_every_registered_prompt_has_a_file():
    """`VALID_PROMPTS` and the directory have to agree.

    `get_prompt()` reads PROMPT_DIR/<key>.txt for every registered key, so a
    key with no file breaks startup seeding and the Settings prompt list. A file
    with no key is dead: nothing can ever read it.
    """
    on_disk = {p.stem for p in PROMPT_DIR.glob("*.txt")}
    assert VALID_PROMPTS - on_disk == set(), (
        f"registered in VALID_PROMPTS but no file: {sorted(VALID_PROMPTS - on_disk)}"
    )
    assert on_disk - VALID_PROMPTS == set(), (
        f"prompt files nothing can read (absent from VALID_PROMPTS): "
        f"{sorted(on_disk - VALID_PROMPTS)}"
    )


def test_the_lock_covers_exactly_the_prompts_that_exist(lock):
    """A pin for a deleted prompt, or a prompt with no pin, both hide edits."""
    on_disk = {p.stem for p in PROMPT_DIR.glob("*.txt")}
    assert on_disk - set(lock) == set(), (
        f"prompt files with no pin: {sorted(on_disk - set(lock))}. A new prompt "
        f"needs an entry in {LOCK_PATH.name} — without one its edits are unguarded.\n{_REMEDY}"
    )
    assert set(lock) - on_disk == set(), (
        f"pinned but no longer on disk: {sorted(set(lock) - on_disk)}. Deleting a "
        f"prompt also needs the stale `settings` rows dropped in a migration "
        f"(pattern: the extract_jd_fields drop in be7f98929817)."
    )


@pytest.mark.parametrize("key", sorted(p.stem for p in PROMPT_DIR.glob("*.txt")))
def test_prompt_file_matches_its_pin(key, lock):
    """The ratchet. A changed file with an unchanged pin fails here."""
    actual = hashlib.sha256((PROMPT_DIR / f"{key}.txt").read_bytes()).hexdigest()
    assert actual == lock[key], (
        f"app/prompts/{key}.txt changed but its pin in {LOCK_PATH.name} did not.\n\n"
        f"Existing installs are STILL RUNNING the old text — the stored "
        f"`settings` row wins over this file, so this edit reaches new installs "
        f"only.\n{_REMEDY}"
    )
