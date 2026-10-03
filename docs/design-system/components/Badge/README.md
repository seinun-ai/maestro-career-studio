A badge is a small non-interactive label for a fact about the thing beside it.

**You provide:** one to four words and a `variant`. A badge never takes a click; a status that can be changed is a StatusChip.

- 20px tall, `radius-full`, `label-medium`.
- `tonal` (`secondary-container`) is the default for a fact worth noticing; `secondary` (the grey `secondary` fill) for plain metadata; `outline` for a tag in a set; `default` (`primary`) only for the strongest mark in a group, such as a required skill; `destructive` for a problem.
- For application or proposal state use StatusChip, which owns that vocabulary.
- Location, level and attention are plain text beside the badge, never color alone.

Source: `frontend/components/ui/badge.tsx`.
