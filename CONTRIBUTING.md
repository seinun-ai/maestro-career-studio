# Contributing to Maestro CS

This guide covers setting up a development environment, running the tests, and the project's conventions.

## 1. Living Architecture Reference (SYSTEM.md)

Before touching code or proposing changes, **read [`SYSTEM.md`](SYSTEM.md) first** (repo root). It is the reference for repository layout, end-to-end application workflows, cross-cutting invariants, agent surfaces, and historical gotchas. Two reference sections are extracted and indexed from it — entity lifecycles in [`docs/entities/`](docs/entities/) and frontend conventions in [`docs/frontend-conventions.md`](docs/frontend-conventions.md) — and carry the same contract. `CLAUDE.md` and `AGENTS.md` at the root are one-line shims pointing here, so agent tools that auto-load a context file land on the real document.

### The Deprecation Ledger (§13)
When contributing features or refactorings, adhere strictly to **`SYSTEM.md` Section 13 (Active migrations & deprecation ledger)**:
- Whenever your work **supersedes** an existing design, code path, or schema without simultaneously deleting the old implementation, **you must file a new row in §13**.
- Every row must define an explicit **removal trigger**: an observable condition (e.g., specific SQL query count or grep check) under which the legacy path will be eradicated.
- When an existing removal trigger is met, prune the legacy code and delete the row from the ledger. Never leave satisfied green rows in §13.

### If the SYSTEM.md size check fails on your PR

CI runs `scripts/check_system_md.py`, which caps the doc's size so it stays a
reference agents and humans actually read, not an append-only changelog. If it
goes red on your PR, **don't fight the doc into passing** — either leave
`SYSTEM.md` untouched and describe the doc impact in your PR description, or
write the addition naturally and say so. The maintainer integrates the doc
change and re-baselines (with the auditable `--reason`) at review; a red on
this one check will not sink an otherwise good PR.

---

## 2. Project Scope

Maestro CS is built for **few, well-evidenced applications**, not volume. That
one choice settles most design arguments before they start, so it is worth
stating plainly what follows from it — including the ideas that will be declined
no matter how well they are implemented.

### What belongs here

- Anything that makes the **Career KB** a truer record of what someone actually
  did, or makes feeding it cheaper.
- Anything that keeps a rendered document **connected** to that record — porting,
  drift detection, versioning, provenance.
- **Determinism wherever a number is claimed.** The ATS engine is a pure function
  of (resume, extracted job, versioned config). Keep LLM calls at the boundary,
  never inside a scorer.
- **Local-first.** A feature that only works against a hosted service we run is
  not a feature of this project.
- **Consent, reversibility, and a written record** on anything that acts on the
  user's behalf.

### What will not be built

These were considered and refused. A pull request implementing one will be
declined on scope, independent of code quality — please open a discussion first
if you think the reasoning has expired.

1. **Volume auto-apply or bulk blast.** Employers now filter for applications
   that read as machine-generated, and the flagship high-volume project in this
   space is archived. Shipping a blast tool would aim the product at the one
   market trend most against it.
2. **Any claim that our ATS Score predicts a real ATS.** Ours is deterministic,
   versioned and reproducible — that is the entire claim, and it is defensible
   precisely because it is narrow. One overclaim discredits the rest of it.
3. **A hosted, multi-tenant SaaS version.** Local-only *is* the differentiator
   and the privacy guarantee, and the data in question is someone's complete
   employment history.
4. **Bot-detection evasion, stealth automation, or CAPTCHA bypass.** Off-limits
   on ethics, and flatly contradictory to the consent ledger the apply lane is
   built around.

### Deferred, but not refused

Authentication and multi-user support (only ever as a separate deployment mode,
never the default — it reverses the guarantee above), a job-board registry and
saved searches, internationalization, and server-side pagination for the
applications tracker. Interest and a design proposal are welcome on any of these.

### Those `.slop*` files are not your problem

The `.slop*` JSON files are the maintainer's code-quality baselines, not a CI
job or PR gate: don't run or edit them; the maintainer re-baselines if needed.

### Looking for something to work on?

[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) is the honest list of what is solid, what
is rough, and which limitations are deliberate. The gaps below are real work
rather than invented starter tasks — start here rather than guessing from the
issue tracker, since several have a decided approach that is not visible in the
code.

### Where help is wanted

Ordered roughly by how self-contained they are.

**Good first changes**

1. **Server-side tracker pagination** (`SYSTEM.md` §11 item 5). Contained,
   testable, and it fixes a real slowdown: the client caps at 500 rows.
2. **URL canonicalization server-side.** Tracking-parameter stripping is
   currently every caller's job, which means it is done inconsistently.

**Bigger, and genuinely useful**

3. **The "ready to apply" gate** (§11 item 2). High user value. The metadata
   path it needs already ships.
4. **Extension coverage for more ATS platforms.** The most valuable
   contribution anyone could make, and the hardest to fake: it requires meeting
   a real form. The fixture corpus in `backend/tests/fixtures/autofill/` shows
   how to add a control shape **without** pasting captured DOM.
5. **Token-cost visibility.** Show what a tailoring run cost. Makes the
   local-model argument concrete at the moment it is felt.
6. **The security hardening KNOWN_ISSUES lists as not yet done.** The
   isolated render worker and the resource ceilings have the best
   effort-to-value ratio.

**Wanted, but talk to us first**

7. **Sanctioned job ingest** via an official API, so postings can arrive
   without anyone scraping.
8. **Provider-aware model routing** — cheap or local models for mechanical
   steps, a frontier model for tailoring.

Before you start: read the relevant part of `SYSTEM.md` §6 (most review comments
here are invariants, not style), and open an issue before a large change.

### Migrations in flight

Two things are deliberately live in two forms at once. `SYSTEM.md` §13
carries the full ledger with removal triggers.

- **Two render engines.** LaTeX and Typst are both first-class and both
  supported. The default is LaTeX; a switch to Typst was considered and is on
  hold. Without TeX, LaTeX templates fall back to Typst with a `render_note`;
  the default stays LaTeX where TeX exists. Changes to templates or rendering
  must handle both.
- **Autofill profile shapes.** `work_auth` and `education` each have a legacy
  and a typed form, with readers for both. If you touch autofill, check §13
  before assuming which shape you have.

---

## 3. Licensing your contribution (nothing to sign)

Maestro CS is **Apache License 2.0**. Opening a pull request licenses your
contribution to the project under those same terms — that is
[section 5](LICENSE) of the license, and it is the whole mechanism. There is no
CLA — nothing to sign — and no DCO or sign-off line.

Two things you still owe, and they are about *other people's* code, not yours:

- If you add a dependency, add it to
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) with its license.
- **Do not add a GPL or AGPL dependency.** Those licenses are one-way
  compatible with Apache 2.0: our code can go into their projects, not the
  reverse. Shipping one would force the entire distribution to their terms.
  PyMuPDF is the standing example — see the note in
  `backend/app/services/pdf_preview.py` and the alternatives already in use.

---

## 4. Development Environment Setup

Maestro CS is a single-user, local-first application built with FastAPI (backend), Next.js 16 (frontend), SQLite, and dual-engine PDF rendering (typst + LaTeX).

There is no database service to start. The application database is the file `data/maestro_cs.sqlite3`, created and migrated on the backend's first boot; tests never touch it (see §5).

### Backend Setup
Install the Python backend in editable mode with development and MCP server extras enabled using Python 3.12+:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
```

*Gotcha reminder (SYSTEM.md §9):* Beware of stale `.pth` files in virtual environments if you switch across Git worktrees or branches. Reinstall editable dependencies and restart clients (such as Claude Desktop) if imports unexpectedly point to older workspace directories.

### Frontend Setup
Install Node dependencies in the frontend directory:
```bash
cd frontend
npm ci
```

### Contributors build; users pull

`docker-compose.yml` is one file in two modes, and which one you get is decided
by a single variable:

- **Comment out `IMAGE_REGISTRY`** in your `.env` — a fresh
  `cp .env.example .env` now ships it SET, because users pull — and then
  `docker compose up -d --build` builds both images **from your working
  tree**. That is the mode you want: it is the only way your changes reach the
  running stack.
- Left as shipped (`IMAGE_REGISTRY=ghcr.io/seinun-ai/maestro-career-studio`),
  the same file *pulls* published images. That is the users' path, documented
  in the [README's Updating section](README.md#updating), and it will happily
  ignore every line you just wrote.

Two consequences worth internalising before you debug a ghost:

- **A frontend-only change still needs the frontend image rebuilt.** A stale
  image once made fixed UI look broken for a whole review. For iteration, the
  dev overlay (§8) is faster than rebuilding — it bind-mounts your source.
- **`scripts/update.sh` is not for you.** It moves the checkout to the newest
  released `v*` tag — which is not where you are working. Contributors stay on
  `main` (or their branch) with `--build`; the script's build-mode branch exists
  for users who installed before prebuilt images shipped. Locally built images
  report their version as `dev`, which the app reads as "unknown, do not
  compare" rather than as a mismatch.

Cutting a release is a separate, maintainer-only checklist:
[`docs/RELEASING.md`](docs/RELEASING.md).

---

## 5. Running Tests and Verification

We require all automated test suites to stay clean and green on every commit.

### Backend Testing (`pytest`)
The backend test suite needs no database service, and two runs cannot collide: `backend/tests/conftest.py` creates a throwaway SQLite file per test process under the system temp directory, migrates it, and removes it afterwards.

The suite deletes every table as it goes, so the fixture refuses a `TEST_DATABASE_URL` that is not a SQLite file, that names the application's own database, or that points anywhere inside `data/`. Set it only to send the run at a scratch file of your own; leave it unset for the default.

Run the test suite from inside `backend/`:
```bash
cd backend
pytest tests/ mcp_server/tests/ -q
```
*(Note: Tests that require active network downloads or external LLM API keys should remain cleanly ignored or skipped in CI offline environments).*

### Frontend Verification
Verify type safety and clean static builds before submitting changes:
```bash
cd frontend
npx tsc --noEmit && npm run build
```

---

## 6. Branch Conventions and Workflow

- **Branch Naming:** Name your feature or fix branches descriptively, optionally prefixing with your identifier or team lane (e.g., `feature/typst-default-font` or `bugfix/pdf-render-timeout`).
- **Commits:** Write clear, concise commit messages explaining *why* a change was made and which SYSTEM.md invariants or ledger entries it affects.
- **Privacy & PII Protection:** Maestro CS deals with personal career documents and autofill profiles. **Never commit personal identifiable information (PII)** such as real surnames, private contact info, API keys, or custom resume payloads into tracked git files, tests, or documentation.

## 7. Pull Requests

When submitting a pull request:
1. Complete the checklist in our Pull Request Template. (There is **no CLA**
   and nothing to sign — see §3.)
2. Ensure `pytest` passes cleanly across all backend and MCP tests.
3. Ensure `tsc --noEmit` and `npm run build` succeed for the frontend.
4. Verify that any updates or architectural changes are reflected directly in `SYSTEM.md`.

## 8. Development mode (hot reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev overlay bind-mounts `backend/app` (plus `migrations/` and `tests/`)
and runs `uvicorn --reload`, and builds the frontend from `Dockerfile.dev`
with `frontend/app`, `components`, `lib`, `hooks` and `public` mounted under
`npm run dev`. Plain `docker compose up` stays the production build, because dev
compilation is slow on cold routes.

To run the frontend natively instead (`cd frontend && npm run dev`) against the
compose backend, no extra configuration is needed: the browser talks to Next's
same-origin `/api` proxy, which forwards to `http://127.0.0.1:8001` by default.
If you moved `BACKEND_HOST_PORT`, point `API_PROXY_BACKEND` (the proxy) and
`INTERNAL_API_URL` (server-side calls) at it. `NEXT_PUBLIC_API_URL` matters only
with `NEXT_PUBLIC_API_DIRECT=true`, which skips the proxy.

## 9. LLM tracing (Langfuse, optional)

Every LLM call can be traced to a Langfuse instance you run. Set
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` on a backend
you run yourself, outside compose. Compose deliberately does not forward them:
traces contain your prompts, which means your resume text. Tracing stays off
unless all three are set (`backend/app/services/tracing.py`). The repo
deliberately ships no Langfuse stack — point it at a host you control.
