An autosave status tells you that a card saves as you go, and what the last save did, so a card with no Save button never reads as unsaved.

**You provide:** `pending` while a write runs, `failed` after one fails, `idle={false}` while the card holds a value the server lacks (a typed key), and `onRetry` for Try again.

- Four states, in `body-small`: **Saving…** (a spinner), **Saved** (the done mark drawn once by `CheckDraw`, in `success`, held 1.2s by `useSavedHold`, then it settles), **Not saved** (`TriangleAlert` in `destructive`, with a Try again link where the card still holds a value the server lacks) and **Saves automatically** (words only, in `muted-foreground`).
- Saving… and Saved are a polite live region; Saves automatically sits outside it, so each save is announced once and then stops.
- It sits in the card header beside the title through `SettingCardAction`, and holds the widest state's width (`min-w-36`) so the description never re-wraps.
- A successful autosave never toasts; a failure toasts as well. After a retry lands, focus moves to the status only if it fell to the page.
- One of the two save models: a pure preference autosaves; anything with a cost or a blast radius keeps an explicit Save (the Profile persona keeps Save and Discard).

Source: `frontend/components/settings/autosave-status.tsx`, `frontend/lib/use-autosave.ts`, `frontend/hooks/use-saved-hold.ts`.
