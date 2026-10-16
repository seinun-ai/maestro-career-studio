# Third-party notices

Maestro CS itself is licensed under the **Apache License 2.0** — see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). This file lists **third-party**
material incorporated into the project. The original copyright notices and the
licenses under which we received them are set out here in full, as those
licenses require.

**This file is part of the required attribution.** Apache 2.0 §4(d) obliges
anyone redistributing this work to carry the `NOTICE` file forward, and `NOTICE`
points here. Redistributing Maestro CS without this file leaves the bundled
resume templates, font and model unattributed.

---

## Jake's Resume (LaTeX resume template)

**Source:** https://github.com/jakegut/resume
**Author:** Jake Gutierrez
**License:** MIT

Used in:
- `backend/app/templates/resume.tex.j2`
- `backend/app/templates/_header.tex.j2`
- `backend/app/templates/cover_letter.tex.j2` (preamble)
- `backend/app/templates/cover_letter.typ` (port of the shared header layout)
- `backend/app/templates/user/carlito_dense.tex.j2`
- `backend/app/templates/user/xcharter_serif.tex.j2`
- `backend/app/templates/user/xcharter_serif.typ` (port of the LaTeX design)
- `backend/app/templates/user/harshibar.tex.j2` (through Harshibar's adaptation)

The document structure, section formatting, and the `\resumeItem` /
`\resumeSubheading` / `\resumeSubHeadingListStart` / `\resumeItemListStart`
command set derive from this template, as does the
`\input{glyphtounicode}` + `\pdfgentounicode=1` ATS-parseability approach.

Modifications: converted to Jinja2 with custom delimiters (`((* *))`,
`((( )))`, `((# #))`), parameterized through the `fmt.*` formatting knobs,
extended with `extra_sections` rendering, and refactored so the header is a
shared partial used by both the resume and cover-letter templates. Carlito Dense
changes the font, section case and spacing; XCharter Serif changes the font,
heading weights and spacing. Their `\resumeSubheading` / `\resumeProjectHeading`
`tabular*` definitions and paired list macros retain Jake's distinctive command
structure. XCharter's Typst source explicitly describes its calibrated LaTeX
port. The Typst cover letter explicitly mirrors the LaTeX header layout.

Jake's upstream source credits `sb2nov/resume`; that inherited attribution and
license are preserved below. The copyright year here matches the upstream
[`LICENSE`](https://github.com/jakegut/resume/blob/master/LICENSE).

```
MIT License

Copyright (c) 2020 Jake Gutierrez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Harshibar's resume (LaTeX resume template)

**Source:** https://github.com/harshibar/resume
**Author:** Harshibar (upstream copyright holder: Harshi)
**License:** MIT

Used in `backend/app/templates/user/harshibar.tex.j2`, seeded as `harshibar`.
The matching `light-grey` / `dark-grey` / `text-grey` values, FiraMono scale,
`\ebseries` / `\texteb` declarations, grey date columns in
`\resumeSubheading`, and 2pt grey section rule identify the upstream design;
the name alone is not the provenance evidence. Upstream `main.tex` also
credits Jake Gutierrez and `sb2nov/resume`.

Modifications: Jinja2 data binding and formatting controls, geometry margins,
Helvetica-style font substitution, simplified underline, optional sections,
and section-order dispatch. License text comes from the upstream
[`LICENSE`](https://github.com/harshibar/resume/blob/main/LICENSE).

```
MIT License

Copyright (c) 2021 Harshi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Sourabh Bajaj's resume (ancestor of Jake's Resume)

**Source:** https://github.com/sb2nov/resume
**Author:** Sourabh Bajaj
**License:** MIT

Jake's and Harshibar's upstream LaTeX headers explicitly credit this template.
The inherited four-argument `\resumeSubheading` with a two-column `tabular*`,
`\resumeSubItem`, paired heading/item list helpers, and section-rule layout
remain in the bundled adaptations listed above. The notice preserves the
[original license](https://github.com/sb2nov/resume/blob/23a4c800c668a79edcea4746ff004143ace00179/LICENSE)
from before Jake's adaptation; the upstream repository later changes its
copyright year.

```
The MIT License (MIT)

Copyright (c) 2015 Sourabh Bajaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Monaco Editor (vendored into the frontend image)

**Source:** https://github.com/microsoft/monaco-editor
**Copyright:** (c) Microsoft Corporation
**License:** MIT

Copied into `frontend/public/monaco` at build time by
`frontend/scripts/vendor-monaco.mjs` (a `prebuild`/`predev` step) so the editor
loads from the local origin instead of a CDN — this app is designed to run with
no outbound network access. Unmodified; the upstream `LICENSE.txt` and
`ThirdPartyNotices.txt` ship inside the vendored directory.

---

## BAAI/bge-small-en-v1.5 (embedding model)

**Source:** https://huggingface.co/BAAI/bge-small-en-v1.5
**License:** MIT (FlagEmbedding) — released for commercial use free of charge

The ATS engine's semantic layer runs this model **locally on CPU** through
`fastembed`/ONNX. It is pinned in `backend/app/services/ats/data/weights.yaml`
and hashed into the ATS `config_version`, which is what makes a score
reproducible: the same resume, JD and config always produce the same number.
The weights are downloaded on first use, not committed here.

Cite the C-Pack paper if you build on the scoring engine:

```bibtex
@misc{bge_embedding,
  title  = {C-Pack: Packaged Resources To Advance General Chinese Embedding},
  author = {Shitao Xiao and Zheng Liu and Peitian Zhang and Niklas Muennighoff},
  year   = {2023},
  eprint = {2309.07597},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL}
}
```

---

## Document toolchain (installed into the backend image)

| Component | Role | License |
|---|---|---|
| [TeX Live](https://tug.org/texlive/) `scheme-basic` + the packages listed in `backend/Dockerfile` | `pdflatex` rendering | LPPL and others, per package |
| [XCharter](https://ctan.org/pkg/xcharter) | resume body font | OFL / LPPL |
| [FontAwesome 5](https://ctan.org/pkg/fontawesome5) | contact icons | OFL / LPPL |
| [Typst](https://github.com/typst/typst) | second render engine | Apache-2.0 |

The engine stays genuine pdfTeX: the `\pdfinterwordspaceon` extraction-fidelity
fix is a pdfTeX primitive, so swapping to XeTeX or Tectonic would require
re-running the parse certification.

Remote Typst package imports (`@preview/…`) are **rejected fail-closed** by
`typst_compiler.py`. They resolve over the network and would execute unreviewed
third-party code at render time, so no `@preview` package is a dependency of
this project.

---

## PDF tooling — why PyMuPDF is not used

PyMuPDF (`fitz`) is available under **AGPL-3.0** or a paid Artifex commercial
licence. Since Maestro CS relicensed to Apache 2.0 (2026-08-08) this is once
again a hard incompatibility, not just a toolchain preference: AGPL is one-way
compatible with Apache, so shipping PyMuPDF would drag the entire distribution
onto AGPL terms. We stay on the **pdfplumber + pypdfium2 + Pillow** stack, and
it must not be reintroduced — in runtime code *or* in tests. Current
replacements:

| Job | Library | Licence |
|---|---|---|
| PDF text extraction | pdfplumber | MIT |
| PDF rasterization | pypdfium2 | BSD-3-Clause / Apache-2.0 |
| Standalone image handling | Pillow | MIT-CMU (HPND) |
| Test PDF fixtures | typst | Apache-2.0 |

`backend/tests/pdf_fixtures.py` builds test PDFs with typst, which is already a
runtime dependency — the test suite adds no extra library for this.

## Dependency inventory

Declared in `backend/pyproject.toml` and `frontend/package.json`. Everything
here is permissive except libvips on the frontend, which is called out below
rather than left buried in a table.

**Backend (Python)**

| Package | License |
|---|---|
| FastAPI, SQLAlchemy, Alembic, Pydantic, pydantic-settings | MIT |
| Uvicorn | BSD-3-Clause |
| openai (Python SDK) | Apache-2.0 |
| fastembed | Apache-2.0 |
| typst (Python binding) | Apache-2.0 |
| python-multipart | Apache-2.0 |
| Jinja2 | BSD-3-Clause |
| PyYAML, pdfplumber | MIT |
| langfuse (optional `tracing` extra; included in Docker) | MIT |
| pypdfium2 | BSD-3-Clause / Apache-2.0 |
| Pillow | MIT-CMU (HPND) |
| pytest, pytest-asyncio, ruff, respx (dev) | MIT |
| httpx (dev) | BSD-3-Clause |
| mcp (MCP server extra) | MIT |

> **`@img/sharp-libvips-*` is LGPL-3.0-or-later while this project is
> Apache-2.0.** That combination is fine and is the ordinary LGPL path: libvips
> arrives as a prebuilt platform binary pulled in by Next.js for image
> optimization, used unmodified, as a separately replaceable library. The LGPL
> terms attach to libvips, not to our code. Anyone who redistributes a
> *modified* libvips, or links it statically, takes on further obligations.
>
> (v0.4.0 also shipped psycopg, LGPL-3.0, for its one-time Postgres import;
> v0.5.0 removed it.)

**Frontend (JavaScript)**

| Package | License |
|---|---|
| Next.js, React, React DOM | MIT |
| Tailwind CSS, tailwind-merge, tw-animate-css | MIT |
| Base UI (`@base-ui/react`) | MIT |
| shadcn / shadcn-ui components | MIT |
| TanStack Query | MIT |
| Monaco Editor, `@monaco-editor/react` | MIT |
| Recharts | MIT |
| Zod | MIT |
| react-markdown, remark-gfm, remark-breaks | MIT |
| Sonner, next-themes, clsx, class-variance-authority | MIT |
| lucide-react | ISC |

---

## Design references (no code vendored)

The Companion's reasoning step (`extension/shared/reason-loop.js`,
`backend/app/services/autofill_reason.py`) took four ideas from other work. We read
these; we copied none of their code, so no licence text ships with us. They are named
because the ideas are theirs.

- **Nanobrowser**, `src/agent/guards.ts` — Apache-2.0,
  <https://github.com/nanobrowser/nanobrowser>. The idea: an action is signed by what it
  does and to what, and an action that failed twice, or a target that changed nothing
  twice, is not offered again.
- **browser-use**, `ActionLoopDetector` and `PageFingerprint` — MIT,
  <https://github.com/browser-use/browser-use>. The idea: tell "the same page again" by a
  fingerprint of the page, not by the address.
- **Spotlighting**, Hines et al. (Microsoft), "Defending Against Indirect Prompt Injection
  Attacks With Spotlighting", arXiv:2403.14720,
  <https://arxiv.org/abs/2403.14720>. The idea: mark the untrusted text (here, page text is
  wrapped in a data block and its whitespace replaced by a marker) so the model can tell it
  from the instructions.
- **LLM Guard**, `invisible_text.py` — MIT, <https://github.com/protectai/llm-guard>. The
  idea: strip invisible Unicode (categories Cf, Co and Cn) from text before a model reads it.

---

## Method note

The ATS engine is our own scoring model — deterministic lexical layers plus an
anchored semantic layer over the embedding model above. It is **not** an
implementation of any published ATS and does not attempt to reproduce any
commercial system's output. Its only third-party component is that model.

If an attribution is missing here, it is an oversight rather than a position;
please open an issue.

---

## Bundled template inventory

All nine template source files under `backend/app/templates/` ship as package data
(`backend/pyproject.toml` includes `templates/*` and `templates/**/*`).
`template_registry.ensure_seed_templates` inserts the two classics and the
four entries in `BUNDLED_TEMPLATES` on a fresh install. The directory named
`user/` contains bundled sources, not private user data.

| Name / id | Engine | Source file(s) | Seeded on fresh install | Provenance |
|---|---|---|---|---|
| Classic / `default` | LaTeX | `backend/app/templates/resume.tex.j2`; shared `backend/app/templates/_header.tex.j2` | Yes; default | Jake's Resume / Sourabh Bajaj |
| Typst Classic / `typst-classic` | Typst | `backend/app/templates/typst_classic.typ` | Yes | Original implementation; no evidence of third-party template code |
| XCharter Serif / `xcharter_serif` | LaTeX | `backend/app/templates/user/xcharter_serif.tex.j2` | Yes | Jake's command structure / Sourabh Bajaj |
| XCharter Serif (Typst) / `xcharter_serif_typst` | Typst | `backend/app/templates/user/xcharter_serif.typ` | Yes | Explicit port of the preceding LaTeX design |
| Carlito Dense / `carlito_dense` | LaTeX | `backend/app/templates/user/carlito_dense.tex.j2` | Yes | Jake's command structure / Sourabh Bajaj |
| Harshibar / `harshibar` | LaTeX | `backend/app/templates/user/harshibar.tex.j2` | Yes | Harshibar / Jake Gutierrez / Sourabh Bajaj |
| Cover letter | LaTeX | `backend/app/templates/cover_letter.tex.j2`; shared `backend/app/templates/_header.tex.j2` | No separate row; renderer uses it | Jake-derived preamble and shared header |
| Cover letter | Typst | `backend/app/templates/cover_letter.typ` | No separate row; renderer uses it | Port of the Jake-derived shared header layout |
| Template license | N/A | `backend/app/templates/LICENSE-resume-templates.txt` | No; bundled package data | Full MIT terms and all three copyright notices |
| New-template starter / `STARTER_SOURCE` | LaTeX | `backend/app/services/template_registry.py` | No; copied when a draft has no source | Original minimal skeleton (`\sectiontitle`, no Jake command set) |

Repository history: the initial public commit `e81696be` (Ajey Dhayashanker
Loganathan, "Maestro Career Studio") contains all resume sources and the
original attribution for Classic and its shared LaTeX header/preamble. It
also contains the XCharter Typst port comments. Commit `086b6449` by the same
author ("feat(templates): seed the four bundled designs, earn ready, and
archive") adds the four designs to automatic seeding. Commit `8b1f5e5e` by
the same author ("feat(cover-letter): render on the resume's engine; bundled
cover_letter.typ") adds the Typst cover letter. These commits establish the
bundling and port history; the source headers and distinctive structures
establish third-party provenance, rather than the public importer name.

The frontend gallery has no independent seed list: `frontend/app/templates/page.tsx`
fetches `/api/templates`, and `frontend/components/templates/template-gallery.tsx`
renders those rows and their runtime thumbnails. `docs/assets/templates.png`
is a gallery screenshot, not a template source or seed. No template PDF, TeX
or Typst preview is tracked under `base_resumes/` or `docs/`.
`base_resumes/example.json` is synthetic resume data, not a template source.
`base_resumes/template_previews/` is ignored runtime output; validation writes
`<template_id>.pdf` there. Historical `harshibar.pdf` previews are not seeded
assets, but the current Harshibar source **ships and seeds**.

## Notes for maintainers

- `backend/app/templates/typst_classic.typ` is an original implementation;
  using the same resume data contract or font does not establish third-party
  template provenance. Font licenses apply separately: the vendored XCharter
  notice and full font terms are in
  `backend/app/assets/fonts/xcharter/LICENSE-XCharter.txt`.
- Every derived template carries a comment banner with its copyright notice,
  MIT license name, upstream source and pointers to this file and the full
  `backend/app/templates/LICENSE-resume-templates.txt`. The latter ships beside
  the sources as package data, including in wheels that omit root documents.
  Preserve the license with the templates and this file with repository copies.
- When changing bundled seed source bytes, freeze the old source and update
  `SUPERSEDED_SEED_DIGESTS` / `CURRENT_SEED_DIGESTS` so untouched installed
  copies receive the current attribution too. Frozen test fixtures retain
  their historical bytes; the notices above also cover those copies.
