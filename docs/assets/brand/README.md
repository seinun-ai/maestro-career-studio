# Maestro Career Studio — Brand Package v2

## Primary files

- `logos/maestro_lockup_light.svg`
  Use on white and light backgrounds.
- `logos/maestro_lockup_dark.svg`
  Use on dark backgrounds. The mark remains blue/yellow; the wordmark becomes white.
- `logos/maestro_mark_small.svg`
  Simplified two-color mark for sizes at or below 32 px.
- `logos/maestro_avatar_primary.svg`
  Primary avatar: blue tile with white + yellow M.
- `logos/maestro_avatar_light.svg`
  Alternate avatar for forced light-tile contexts.
- `logos/maestro_mark_navy.svg`
  Monochrome navy mark for documents, PDF footers, stamps, and one-color print.
- `logos/maestro_mark_white.svg`
  Monochrome white mark for dark surfaces and watermark use.

## Favicon / app-icon files

- `icons/favicon.svg` — preferred modern browser favicon
- `icons/favicon.ico` — legacy browser fallback (16/32/48 px)
- `icons/favicon-16x16.png`
- `icons/favicon-32x32.png`
- `icons/favicon-48x48.png`
- `icons/apple-touch-icon.png` — 180 × 180
- `icons/android-chrome-192x192.png`
- `icons/android-chrome-512x512.png`
- `icons/site.webmanifest`

## Locked color tokens

- Blue: `#2563EB`
- Blue facet: `#1D4ED8`
- Yellow: `#FBBF24`
- Yellow facet: `#D99A00`
- Navy: `#0F172A`
- Grey: `#64748B`
- Dark-mode tagline: `#CBD5E1`
- White: `#FFFFFF`

Machine-readable versions are in `tokens/brand-tokens.css` and
`tokens/brand-tokens.json`.

## Website header usage

Use the light lockup on white navigation bars and the dark lockup on dark
navigation bars. Keep clear space around the lockup equal to at least the
height of the lowercase `m` stem. Avoid stretching, recoloring, adding
shadows, or reintroducing gradients.

For very compact mobile headers, use the primary avatar or small mark instead
of shrinking the full wordmark below legibility.

## Recommended HTML

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#2563EB">
```

## Typography

The SVG lockups are configured for `Inter`, with `Manrope` and `Arial` as
fallbacks. For a fully portable production master, convert the final approved
wordmark text to vector outlines in Figma, Illustrator, or Inkscape after
confirming the exact Inter weight and tracking.

## GitHub social preview

- `social/social-preview.png` — 1280 × 640 final sharing card
- `social/social-preview.svg` — editable vector source

The brand wordmark in both production lockups is converted to genuine Inter
vector outlines so GitHub and other image viewers do not depend on locally
installed fonts.

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
