# Maestro Career Studio — Brand Package v2

## Primary files

The masters sit flat in this directory; only `icons/` is a subfolder.

- `maestro_lockup_light.svg`
  Use on white and light backgrounds.
- `maestro_lockup_dark.svg`
  Use on dark backgrounds. The mark remains blue/yellow; the wordmark becomes white.
- `maestro_mark_small.svg`
  Simplified two-color mark for sizes at or below 32 px.
- `maestro_avatar_primary.svg`
  Primary avatar: blue tile with white + yellow M.
- `maestro_avatar_light.svg`
  Alternate avatar for forced light-tile contexts.
- `maestro_mark_navy.svg`
  Monochrome navy mark for documents, PDF footers, stamps, and one-color print.
- `maestro_mark_white.svg`
  Monochrome white mark for dark surfaces and watermark use.

## Locked color tokens

- Blue: `#2563EB`
- Blue facet: `#1D4ED8`
- Yellow: `#FBBF24`
- Yellow facet: `#D99A00`
- Navy: `#0F172A`
- Grey: `#64748B`
- Dark-mode tagline: `#CBD5E1`
- White: `#FFFFFF`

Machine-readable versions are in `brand-tokens.css` and `brand-tokens.json`.

## Website header usage

Use the light lockup on white navigation bars and the dark lockup on dark
navigation bars. Keep clear space around the lockup equal to at least the
height of the lowercase `m` stem. Avoid stretching, recoloring, adding
shadows, or reintroducing gradients.

For very compact mobile headers, use the primary avatar or small mark instead
of shrinking the full wordmark below legibility.

## Recommended HTML

For a web context outside this repo, once the corresponding files are generated
from the masters here (the app itself uses Next's file conventions instead — see
the last section):

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#2563EB">
```

## Typography

The wordmark is `Inter`, already converted to vector outlines in both production
lockups — the SVGs reference no font, so they render identically wherever they
are opened. Set new type in Inter (fallbacks `Manrope`, `Arial`) and outline it
the same way before committing a replacement master.

## GitHub social preview

- `social-preview.png` — 1280 × 640 final sharing card
- `social-preview.svg` — editable vector source

Outlined wordmark, as above, so GitHub and other image viewers do not depend on
locally installed fonts.

## icons/ (kept masters not wired into the app)

- `icon-512.png` — the GitHub org avatar master (blue tile), also the
  Chrome Web Store listing size when that day comes.
- `icon-192.png` — PWA/android-chrome size for `site.webmanifest`.
- `favicon.ico` — legacy-browser fallback, unused today (the app serves
  `frontend/app/icon.svg`); keep for future web contexts.
- `site.webmanifest` — ditto; the app does not ship a manifest yet.

The app's live icons are `frontend/app/icon.svg` + `frontend/app/apple-icon.png`;
the extension's are `extension/icons/{16,32,48,128}.png`. Everything here
regenerates from the SVG masters in this directory.
