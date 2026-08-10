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

## Why the Slanted faces are NOT here

XCharter ships two italic designs: a **true italic** (`XCharter-Italic`,
`XCharter-BoldItalic`) and a mechanical **oblique** (`XCharter-Slanted`,
`XCharter-BoldSlanted`). All four declare family `XCharter` and set the italic
bit, so a plain "italic" request matches two faces at each weight, and typst
resolves the tie by **font enumeration order — which is filesystem order**.

That is not a stable property. The same resume rendered in this repository's
own CI (Linux) and on the maintainer's laptop (macOS) picked *different italic
designs* from the same six files: `XCharter-Italic` on one, `XCharter-Slanted`
on the other. Vendoring the fonts had removed the "which XCharter?" question and
left "which italic?" open, which is the same class of defect one layer down.

Only the four unambiguous faces are vendored now, so the match is forced. This
also closes a real parity gap rather than merely a test failure: LaTeX's
`xcharter` package maps `\textit` to the **true italic**, so typst picking the
oblique meant the two engines were producing visibly different letterforms while
the parity suite reported agreement.

To restore an oblique deliberately, add the file back **and** give it a distinct
family name — do not reintroduce the tie.

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
