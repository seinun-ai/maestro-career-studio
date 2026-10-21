A tile card is the editor a Profile tile opens: a settings card under the tile grid, titled by its tile, with Close in its header.

**You provide:** the `tile` id (from `lib/profile-tiles.ts`), the `query` its editor needs (and `also`, any others), an `errorTitle` for a failed load, an optional `description` and `skeleton`, and the editor as `children(value)`.

- The tile grid's buttons (`TileButton`) say what each tile holds in real values with a state word: Ready (the done mark in `success`), **Needs you** (the `attention-container` pill, round because it is a state) or a count in words ("3 countries"). A tile that needs you takes an inset `attention-container` ring; the open one a 2px `primary` ring.
- A tile is a button with `aria-expanded` and `aria-controls`, named by its title and state and described by its summary.
- One editor shows at a time, under the grid. Every editor stays mounted while closed, so a draft and its save survive.
- The card is a `SettingCard` (the one shell: header, loading skeleton, the failure with Try again) with the card id its deep links name (`/profile#autofill-personal` opens Contact). **Close** is the last action in its header, a `ghost` small button, and hands focus back to the tile.
- Most editors save as you go: their `AutosaveStatus` sits in the same header.

Source: `frontend/components/profile/tile.tsx`, `frontend/lib/profile-tiles.ts`.
