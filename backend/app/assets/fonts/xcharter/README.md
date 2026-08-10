# Vendored fonts: XCharter

The resume templates render in **XCharter**. These OTFs are vendored so font
resolution is identical on every machine — contributor laptop (any OS), CI, and
the container — with no TeX Live installation and no environment variable.

## Why vendored rather than discovered

Typst **silently falls back to its embedded fonts when a font directory does not
exist** — no error, no warning. A path-based default therefore fails as a wrong
typeface in the output rather than as a loud error, and the only thing that
catches it is the pt-exact LaTeX/Typst parity assertion in
`tests/test_user_templates.py`. Pointing the default at a TeX Live installation
also cannot generalize: TeX lives at `/usr/share/texlive` (Debian),
`/opt/texlive` (install-tl), `/usr/local/texlive/<year>` (macOS/MacTeX),
`C:\texlive\<year>` (Windows), somewhere else entirely under TinyTeX or Nix — or
nowhere at all, which is the intended end state once the LaTeX render path is
cut (SYSTEM.md §13 `texlive-layer`).

Shipping the font removes the question.

## Provenance

- **Family:** XCharter, version 1.26 (2024-06-18)
- **Authors:** Bitstream Inc. (original Charter, 1989-1992); modifications
  (c) 2009-2012 Andrey Panov, (c) 2013-2024 Michael Sharpe
- **Source:** CTAN / TeX Live `texmf-dist/fonts/opentype/public/xcharter`
- **License:** see `LICENSE-XCharter.txt` (verbatim upstream README). The font
  files are free under the original Bitstream Charter terms, which permit use,
  copy, modification, sublicensing, sale, and redistribution "for any purpose
  and without restriction", provided the notice travels with the fonts and the
  Bitstream trademark is acknowledged. That notice file is why it is here — keep
  it alongside the OTFs.

Only the OTFs and that notice are vendored. The LaTeX support files (LPPL) are
not needed: the LaTeX render path resolves XCharter through TeX's own font
machinery, not through this directory.

## Updating

Replace the OTFs and `LICENSE-XCharter.txt` together from the same upstream
release, then run `pytest tests/test_user_templates.py` — the parity tests
compare Typst output against LaTeX output and will catch a metrics change.
