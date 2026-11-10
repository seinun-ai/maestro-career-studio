The Maestro mark is one M in one colour: the two bolts of the original mark joined into a single shape. The files are the brand package in `docs/assets/brand/`, all written by `scripts/build_brand_assets.py`; the wordmark is converted to paths, so no font is needed.

- `maestro_mark.svg`: the mark in `currentColor`. This is what the app draws.
- `maestro_lockup_light.svg`: mark, "maestro" wordmark and tagline for light grounds. Mark and wordmark `#0F172A`, tagline `#64748B`.
- `maestro_lockup_dark.svg`: the same for dark grounds. Mark and wordmark `#FFFFFF`, tagline `#CBD5E1`.
- `maestro_mark_navy.svg`: the mark in `#0F172A`, for one-colour print or a light ground.
- `maestro_mark_white.svg`: the mark in `#FFFFFF`, for dark or coloured grounds.
- `maestro_mark_small.svg`: a white mark on a navy rounded tile, for 32 px and below.
- `maestro_avatar_primary.svg`: the mark cut out of a navy rounded tile, for profile pictures.
- `maestro_avatar_light.svg`: a navy mark on a white rounded tile.
- App icon (`frontend/app/icon.svg`) and every icon PNG: the mark in `#1a1300` on a `#ffb81f` marigold rounded tile.

Rules: in the app, draw the mark with `MaestroMark` and the lockup with `MaestroLogo` from `components/brand-logo.tsx`; both take `currentColor`, so the mark follows the text colour in light and dark. Omit the tagline below about 300px wide. Do not recolour, outline or rotate the mark, and do not draw it in two colours. Marigold is the app's one signal colour, used as a fill with dark text; the mark itself is one colour and takes the text colour.
