# Bundled user-template sources, frozen before each seed-time resync

These are byte-exact copies of `backend/app/templates/user/<seed_id>.tex.j2`
as they stood at each `main` commit that changed the file. Each version is
`<n>.tex.j2` (oldest first) under `templates_superseded/<seed_id>/`.

`template_registry.SUPERSEDED_SEED_DIGESTS` pins the sha256 of these bytes.
A seeded row whose source digest is in that set is ours and never user-edited,
so `ensure_seed_templates` may replace it with the current bundle. A
user-edited row matches nothing and is left alone.

**A wrong digest is a silent no-op.** The resync only replaces a row it
recognises; a mistyped pin simply never matches. That is why
`test_template_seed_resync.py` checks the literals against these frozen files.

## How to add a version

When a bundled user template's bytes change:

1. Freeze the old bytes as the next `<n>.tex.j2` in this directory (do not
   edit earlier versions).
2. Add that file's sha256 to `SUPERSEDED_SEED_DIGESTS` for the seed id.
3. Update `CURRENT_SEED_DIGESTS` to the new bundled source's digest last —
   `test_current_bundled_sources_are_pinned` fails until you do.

Seed-time rather than alembic: `seeding.run_startup` is migrations → legacy
import → seed. On the cutover boot a migration runs against an empty file,
then the importer lands the old rows, and only seeding — every boot — sees
them.
