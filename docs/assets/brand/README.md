# Maestro Career Studio brand files

The mark is one M in one colour: the two bolts of the original mark joined into
a single shape. In the app it takes the text colour. Icons put it in ink on a
marigold rounded tile.

## Regenerate everything

Every file below that holds the mark comes from one script, which owns the
mark's geometry. From the repo root:

```sh
backend/.venv/bin/python scripts/build_brand_assets.py
```

It needs only Pillow (a backend dependency), prints what it wrote, and gives the
same files when run again. It leaves `mcpb/icon.png` alone unless you pass
`--with-mcpb`: that icon is packed into the Claude Desktop bundle, whose hash
`server.json` pins, so it changes only at release time, just before the bundle
is re-packed (`docs/RELEASING.md`, step 2). Change the mark there, never by
editing a file it writes.

## Files in this folder

The masters sit flat here; only `icons/` is a subfolder.

- `maestro_mark.svg`: the mark in `currentColor`, so it takes the text colour
  of wherever it is placed.
- `maestro_mark_navy.svg`: the mark in navy, for documents, PDF footers and
  one-colour print.
- `maestro_mark_white.svg`: the mark in white, for dark surfaces and watermarks.
- `maestro_mark_small.svg`: a white mark on a navy rounded tile, for 32 px and
  below.
- `maestro_avatar_primary.svg`: the mark cut out of a navy rounded tile, so it
  shows whatever is behind it. For profile pictures.
- `maestro_avatar_light.svg`: a navy mark on a white rounded tile.
- `maestro_lockup_light.svg`: mark, wordmark and tagline for light grounds. Mark
  and wordmark navy, tagline grey.
- `maestro_lockup_dark.svg`: the same for dark grounds. Mark and wordmark white,
  tagline light grey.
- `social-preview.png`: the 1280 x 640 link-preview card for the repo. It is
  made outside this repo; replace the PNG to change it.

The lockups keep their outlined wordmark; the script swaps only the mark group
and stores where it fits in the group's `data-fit` attribute, so a second run
lands in the same place.

## Colours

- Navy `#0F172A`: the mark and wordmark in print and on light grounds.
- Marigold `#FFB81F`: the icon tile. In the app, marigold is the one signal
  colour: a fill with dark text, never a text or line colour.
- On-marigold `#1A1300`: the mark on the marigold tile, and any text on a
  marigold fill.
- Grey `#64748B`: the tagline on light grounds.
- Light grey `#CBD5E1`: the tagline on dark grounds.
- White `#FFFFFF`.

Machine-readable versions are in `brand-tokens.css` and `brand-tokens.json`.

## Icons

All icons are the same marigold tile with the ink mark. The tile is a rounded
square inset 16 units in a 256 box (corner radius 54), with the mark at 0.72
scale in the middle; outside the tile is transparent.

- `frontend/app/icon.svg`: the app's favicon.
- `frontend/app/apple-icon.png`: 180 px. This one fills the whole square with
  marigold and has no transparency, because iOS rounds the corners itself.
- `extension/icons/{16,32,48,128}.png`: the Companion's icons.
- `mcpb/icon.png`: 512 px, the Claude Desktop bundle icon (only with `--with-mcpb`).
- `icons/icon-192.png`, `icons/icon-512.png`: for `site.webmanifest`. The 512
  is also the GitHub avatar and store-listing size.
- `icons/favicon.ico`: 16, 32 and 48 px in one file, for old browsers.
- `icons/site.webmanifest`: theme colour `#0c0c0f`. The app does not ship a
  manifest yet; this is kept for future web pages.

## Using the files

In the app, draw the mark with `MaestroMark` and the lockup with `MaestroLogo`
from `frontend/components/brand-logo.tsx`; both take the text colour. Elsewhere,
use the light lockup on light headers and the dark lockup on dark ones. Keep
clear space around the lockup at least the height of the lowercase `m` stem.
Do not stretch, outline, rotate or add shadows or gradients. Do not draw the
mark in two colours or put it in marigold on a light ground.

For a very small header, use the mark or a tile instead of shrinking the
wordmark until it cannot be read.

For a web page outside this repo:

```html
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#0c0c0f">
```

## Typography

The wordmark is Inter, already turned into outlines in both lockups, so the
SVGs need no font and look the same everywhere. Set new type in Inter (then
Manrope, then Arial) and outline it the same way before committing a
replacement.
