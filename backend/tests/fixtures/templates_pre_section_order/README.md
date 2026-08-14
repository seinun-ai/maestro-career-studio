# Bundled template sources, frozen before the `section_order` refactor

These are byte-exact copies of `backend/app/templates/**` as they stood
immediately before the `section_order` knob macro-factored every bundled
template (migration `0bc45a1bf6d6`).

**Never update these files.** They are a historical snapshot pinned to a
migration, not a mirror of the live templates. Their sha256 digests are what
`0bc45a1bf6d6._OLD_TEMPLATE_SOURCES` matches against to decide whether a
stored seed row is untouched, and that decision is about bytes that shipped —
it cannot change when the templates change again.

## Why the snapshot exists at all

The previous resync migration's test (`test_template_date_resync.py`) verified
its pinned hashes by reconstructing the old sources *from the live templates*,
reversing the specific edits that migration had made. That works exactly once:
the next template change breaks the reconstruction, and it did — all three of
that file's tests went red on the `section_order` refactor, even though nothing
about dates had changed.

A frozen snapshot ends that coupling. The date test now reverses its edits
against these bytes instead of against a moving target, so it keeps testing the
date migration forever. A future template change should do the same thing this
one did: freeze its own "before" snapshot next to its own migration.
