# Contributing to Maestro CS

Thank you for your interest in improving Maestro CS! This guide covers how to set up your development environment, run the tests, follow project conventions, and contribute cleanly.

## 1. Living Architecture Reference (SYSTEM.md)

Before touching code or proposing changes, **read [`SYSTEM.md`](SYSTEM.md) first** (repo root). It is the absolute, living source of truth for repository layout, end-to-end application workflows, cross-cutting invariants, agent surfaces, and historical gotchas. Two reference sections are extracted and indexed from it — entity lifecycles in [`docs/entities/`](docs/entities/) and frontend conventions in [`docs/frontend-conventions.md`](docs/frontend-conventions.md) — and carry the same contract. `CLAUDE.md` and `AGENTS.md` at the root are one-line shims pointing here, so agent tools that auto-load a context file land on the real document.

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

You will see `.slopledger.json` at the root and a `.slop-baseline.json` +
`.slopconfig.json` in `backend/`, `frontend/` and `extension/`. They are frozen
metrics for an external code-quality ratchet (the `ai-slop-detector` Claude
skill) that the maintainer runs before a release: it fails if duplication, dead
code or complexity concentration gets worse than the recorded numbers.

**It is not a CI job and not a PR gate.** Nothing in `.github/workflows/` runs
it, and you are not expected to install it, run it, or update those files. If
your change moves a number, the maintainer re-baselines with a stated reason —
that is a judgement call about whether the increase is earned, which is exactly
why it is not automated.

`.slopledger.json` is the one to leave alone most carefully: it mirrors the
removal triggers in `SYSTEM.md` §13, and the two are checked against each
other. Editing one without the other creates the drift the check exists to
catch.

### Looking for something to work on?

[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) is the honest list: what is solid, what is
rough, which limitations are deliberate, and a ranked set of gaps that are real
work rather than invented starter tasks. Start there rather than guessing from
the issue tracker — several of those items have a decided approach that is not
visible in the code.

---

## 3. Licensing your contribution (nothing to sign)

Maestro CS is **Apache License 2.0**. Opening a pull request licenses your
contribution to the project under those same terms — that is
[section 5](LICENSE) of the license, and it is the whole mechanism. There is no
CLA, no DCO and no sign-off line.

This replaced a CLA that existed to let Seinun LLC sublicense contributions for
a commercial dual-license tier. Apache 2.0 already permits commercial and
proprietary use by anyone, so there was no longer any restriction for that tier
to lift, and the paperwork bought nothing.

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

Maestro CS is a single-user, local-first application built with FastAPI (backend), Next.js 16 (frontend), PostgreSQL 16, and dual-engine PDF rendering (typst + LaTeX).

### Database Setup
To prevent port collisions with any existing local PostgreSQL instances on your system, our Docker Compose setup binds PostgreSQL to host port **`55432`** (it remains `5432` inside the container network).

Start PostgreSQL locally:
```bash
docker compose up -d postgres
```

The Docker Postgres instance hosts two databases by default:
- `maestro_cs`: The development database used when running the application.
- `maestro_cs_test`: A dedicated throwaway database reserved exclusively for running test suites.

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

---

## 5. Running Tests and Verification

We require all automated test suites to stay clean and green on every commit.

### Backend Testing (`pytest`)
The backend test suite truncates user-data tables during execution. To protect real user data, our test configuration (`backend/tests/conftest.py`) actively blocks execution against any production or development database named `maestro_cs`.

- **Automatic Fallback:** When running tests locally without explicitly setting an environment variable, `conftest.py` automatically defaults to the throwaway test database:
  `postgresql://app:app@127.0.0.1:55432/maestro_cs_test`
- **Checking Shared Instances:** Because local terminal sessions and background tools share the same test database instance on port `55432`, concurrent test runs will produce cascading false failures. **Always check for active test processes before initiating a suite run:**
  ```bash
  pgrep -f pytest
  ```
  If another session is running `pytest`, wait for it to finish.

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
