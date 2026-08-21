# ResumeVersion (`models/resume_version.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

Append-only full snapshots (kind + key string), written on EVERY
`customized_json`/base-data write path with a `source` tag (import, form_edit,
edit_ops, tailor, chat, restore, create). This is the undo story — restore is
itself a new version. `record_version` does NOT commit; the caller owns the
transaction.

