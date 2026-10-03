The Maestro mark is an M made of two folded blades, blue on the left and yellow on the right. The files are the outlined brand package from `docs/assets/brand/`; the wordmark is converted to paths, so no font is needed.

- `maestro_lockup_light.svg`: mark, "maestro" wordmark and tagline for light grounds. Wordmark ink `#0F172A`, tagline `#64748B`.
- `maestro_lockup_dark.svg`: the same for dark grounds. Wordmark ink `#FFFFFF`, tagline `#CBD5E1`.
- `maestro_mark_small.svg`: the two-color mark alone, for compact and square places. This is what the sidebar shows beside "Maestro CS".
- `maestro_mark_navy.svg`: single-ink mark in `#0F172A`, for one-color print or a light ground where color is not available.
- `maestro_mark_white.svg`: single-ink mark in `#FFFFFF`, for dark or colored grounds.
- `maestro_avatar_primary.svg`: white and yellow mark on a `#2563EB` rounded square, for profile pictures.
- `maestro_avatar_light.svg`: the avatar on a light ground.
- `app-icon.svg`: the browser and app icon (`frontend/app/icon.svg`).

Rules: the mark's blue (`brand-blue`) and yellow (`brand-yellow`) are fixed and never follow the theme. In the app, draw the mark with `MaestroMark` and the lockup with `MaestroLogo` from `components/brand-logo.tsx`; their wordmark takes `currentColor`. Omit the tagline below about 300px wide. Do not recolor, outline or rotate the mark, and do not use yellow anywhere else in the UI.
