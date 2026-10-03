A dialog interrupts for one decision or one short task, and keeps what the person typed if it closes.

**You provide:** a title that states the decision, one or two sentences on what happens, and the actions. Pickers that belong to a menu open in a dialog, not inside the menu.

- `popover` surface, `radius-corner-xl`, 24px padding, `shadow-level3`, over a 10% black scrim. It owns its own max height and scrolls inside.
- Title in `title-medium`, body in `body-medium` `muted-foreground`.
- Actions right-aligned, the confirming one last. The confirm is filled (a dialog is a view of its own) or `destructive` when it destroys something; name it for what it does ("Leave", "Delete"), never "OK".
- Focus moves into the dialog on open and returns to the trigger on close; it never falls to `<body>`.
- A dialog keeps what the user typed, or paid for, across close.
- Leaving with unsaved work asks.

Source: `frontend/components/ui/dialog.tsx`, `confirm-dialog.tsx`. Changed from source: corner 14px to 28px, padding 16px to 24px, `shadow-level3` added.
