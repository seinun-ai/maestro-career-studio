# ResumeVersion (`models/resume_version.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

Append-only full snapshots (kind + key string), written on EVERY
`customized_json`/base-data write path with a `source` tag (import, form_edit,
edit_ops, tailor, chat, restore, create). This is the undo story — restore is
itself a new version. `record_version` does NOT commit; the caller owns the
transaction.

**An undo restores only over its own write.** `POST …/{number}/restore?if_latest=N` restores only
while version N is still the latest, else 409 "resume changed since" with nothing restored: it takes
the write lock (`db.begin_write`) before it reads the latest version, so the check and the restore
are one transaction. The health question pass records the latest version V0 before its one batch
write and offers Undo only when the write's own `version_number` (the base `/edits` response names
the version it left latest; an edit that changes nothing writes none) is V0+1, then undoes it with
`if_latest=V0+1`; Version history's Restore passes nothing.
