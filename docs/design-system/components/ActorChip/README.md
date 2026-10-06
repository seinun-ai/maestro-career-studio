An actor chip says who or what a thing came from, with the register's icon and a word.

**You provide:** a `kind` (`you`, `ai`, `assistant`, `agent`, `careerHistory`, `resume`, `document` (the attachment glyph), `jobWords`, `merged` or `fromResume`); optionally `name` (overrides the word; null falls back to it), `title` (a tooltip) and `children` (a trailing part inside the chip).

- The icon is the kind's entry in the concept register (`CONCEPT_ICONS`); the agent kind is the Agent inbox's Bot, never a logo. For an agent pass `agentDisplayName(...)` as `name`.
- Default words: You, AI, Assistant, Connected agent, Career history, Your resume, Attachment, Job's words, Merged, From a resume.
- 20px tall, `radius-full`, `surface-container`, `label-medium`, a 12px icon hidden from assistive tech beside the word.

Source: `frontend/components/visual/actor-chip.tsx`.
