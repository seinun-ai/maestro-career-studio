# Third-party notices

Maestro CS itself is licensed under the **Apache License 2.0** — see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). This file lists **third-party**
material incorporated into the project. The original copyright notices and the
licenses under which we received them are set out here in full, as those
licenses require.

**This file is part of the required attribution.** Apache 2.0 §4(d) obliges
anyone redistributing this work to carry the `NOTICE` file forward, and `NOTICE`
points here. Redistributing Maestro CS without this file leaves the bundled
LaTeX template, font and model unattributed.

---

## Jake's Resume (LaTeX resume template)

**Source:** https://github.com/jakegut/resume
**Author:** Jake Gutierrez
**License:** MIT

Used in:
- `backend/app/templates/resume.tex.j2`
- `backend/app/templates/_header.tex.j2`
- `backend/app/templates/cover_letter.tex.j2` (preamble)

The document structure, section formatting, and the `\resumeItem` /
`\resumeSubheading` / `\resumeSubHeadingListStart` / `\resumeItemListStart`
command set derive from this template, as does the
`\input{glyphtounicode}` + `\pdfgentounicode=1` ATS-parseability approach.

Modifications: converted to Jinja2 with custom delimiters (`((* *))`,
`((( )))`, `((# #))`), parameterized through the `fmt.*` formatting knobs,
extended with `extra_sections` rendering, and refactored so the header is a
shared partial used by both the resume and cover-letter templates.

```
MIT License

Copyright (c) 2021 Jake Gutierrez

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
here is permissive except psycopg, which is called out below rather than left
buried in a table.

**Backend (Python)**

| Package | License |
|---|---|
| FastAPI, SQLAlchemy, Alembic, Pydantic, pydantic-settings | MIT |
| Uvicorn | BSD-3-Clause |
| **psycopg 3 (`psycopg[binary]`)** | **LGPL-3.0** — see note |
| openai (Python SDK) | Apache-2.0 |
| fastembed | Apache-2.0 |
| typst (Python binding) | Apache-2.0 |
| python-multipart | Apache-2.0 |
| Jinja2 | BSD-3-Clause |
| PyYAML, pdfplumber, python-docx, langfuse | MIT |
| pypdfium2 | BSD-3-Clause / Apache-2.0 |
| Pillow | MIT-CMU (HPND) |
| pytest, pytest-asyncio, ruff, respx (dev) | MIT |
| httpx (dev) | BSD-3-Clause |
| mcp (MCP server extra) | MIT |

> **psycopg is LGPL-3.0 while this project is Apache-2.0.** That combination is
> fine and is the ordinary LGPL path: we use it unmodified, as a library,
> through its public interface, and ship it as a separately installable package
> inside the container, so a user can replace it. The LGPL terms attach to
> psycopg, not to our code. Anyone who redistributes a *modified* psycopg, or
> links it statically, takes on further obligations.
>
> **The same applies to `@img/sharp-libvips-*` (LGPL-3.0-or-later)** on the
> frontend — libvips arrives as a prebuilt platform binary pulled in by Next.js
> for image optimization, unmodified and separately replaceable.

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
| react-hook-form, `@hookform/resolvers`, Zod | MIT |
| react-markdown, remark-gfm, remark-breaks | MIT |
| Sonner, next-themes, clsx, class-variance-authority | MIT |
| lucide-react | ISC |

---

## Method note

The ATS engine is our own scoring model — deterministic lexical layers plus an
anchored semantic layer over the embedding model above. It is **not** an
implementation of any published ATS and does not attempt to reproduce any
commercial system's output. Its only third-party component is that model.

If an attribution is missing here, it is an oversight rather than a position;
please open an issue.

---

## Notes for maintainers

- `backend/app/templates/typst_classic.typ` is original work — no third-party
  attribution needed.
- The dependency inventory below closes the item that used to read "a full
  dependency license inventory is still outstanding" (2026-08-03).
- **Resolved 2026-07-26:** `base_resumes/template_previews/` is no longer
  tracked. It is a runtime output directory — template validation writes
  `<template_id>.pdf` into it — and un-ignoring it had been committing previews
  of whatever templates a developer had created locally. One of those
  (`harshibar.pdf`) was a preview of a user-created LaTeX template whose name
  suggests third-party provenance; it was never a seeded asset, and no code,
  test, or seed reads the committed copies. Only `default` and `typst-classic`
  ship as templates, and both are covered above.
- When adding a template derived from someone else's work, add the notice here
  AND a comment banner in the file itself. A pointer in only one place is not
  compliance.
