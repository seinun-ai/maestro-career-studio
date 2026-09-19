# Desktop step 2, branch 1: engines that explain themselves — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** A backend with no TeX renders every resume and cover letter through
Typst and says so in the response, the gallery and `setup/status`, while a
backend with TeX (the Docker image) behaves exactly as before.

**Architecture:** One probe module (`app/services/engines.py`) answers "can
this process run pdflatex / typst" and is the only place that looks for a
binary. One resolver (`pdf_render.resolve_render_template`) applies the single
fallback rule and returns a `render_note`; every document render (resume, base
resume, cover letter) goes through it, template validation deliberately does
not. The cover letter gets a bundled `cover_letter.typ` and an
engine-dispatching compile. Seeds, schemas, the setup checklist and the MCP
docstrings surface `engine_available` / `render_note`; nothing is stored.

**Tech Stack:** FastAPI + SQLAlchemy 2 (SQLite), pydantic v2, Jinja2 sandbox +
pdflatex subprocess, typst 0.15 in-process (`typst_compiler`), pdfplumber for
text assertions, pytest; Next 16 + React 19 + TypeScript for the gallery and
checklist; SYSTEM.md contract v4 with `scripts/check_system_md.py`.

Design: `docs/plans/2026-09-19-desktop-step2-design.md` §2 (this branch), §6
and §7 (docs, SYSTEM.md, gates G1–G3). Owner decisions already taken: fall
back and say so; cover letter follows the resume's engine; `engines` ships
before `mcp-http`.

---

## Before you start

- Work in the worktree `.claude/worktrees/desktop-step2` on branch
  `claude/desktop-step2-engines-mcp`. Never `cd` to the main checkout; its
  compose stack is live on 3000/8001/55432 and its `data/` is the real
  database. Never run `./scripts/update.sh`.
- Interpreter: `/opt/anaconda3/bin/python3` holds the editable backend
  install; run `python3 -m pytest …` from `backend/` in the worktree so
  `app`/`mcp_server` resolve to the worktree (cwd wins on `sys.path`). Tests
  need no database service: `tests/conftest.py` makes a throwaway SQLite file
  per process.
- TeX on the maintainer's Mac lives in `/Library/TeX/texbin`. After Task 1 the
  probe finds it even when `PATH` lacks it, so **to simulate a TeX-less host
  set `MAESTRO_CS_PDFLATEX=/nonexistent`** (a wrong override fails closed and
  never searches). Tests never depend on the host: they monkeypatch
  `app.services.engines.pdflatex_available` / `probe_pdflatex`.
- Every commit message ends with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Keep the **Deviation log** and **Gate results** tables at the end of this
  file current. Append-only; one line per deviation with the reason.
- Suggested subagent model per task: default (Fable) for Tasks 2, 3, 6, 12;
  `opus` for the rest (`opus` is fine for docs, schemas, frontend and tests
  that follow a given shape).
- Slop ratchet (maintainer tooling, not shipped):
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend`
  and `… check frontend` from the repo root, named per surface in the claim.

---

### Task 1: The engine probe (`app/services/engines.py`)

**Files:**
- Create: `backend/app/services/engines.py`
- Modify: `backend/app/config.py` (after the `typst_font_paths` validator, ~line 248)
- Test: `backend/tests/test_engines.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_engines.py
"""The probe is the ONE place that looks for a PDF engine binary."""
import subprocess
from pathlib import Path

import pytest

from app.config import settings
from app.services import engines


@pytest.fixture(autouse=True)
def _fresh_probe(monkeypatch):
    engines.reset_cache()
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", None)
    yield
    engines.reset_cache()


def _fake_pdflatex(directory: Path) -> Path:
    exe = directory / "pdflatex"
    exe.write_text("#!/bin/sh\necho 'pdfTeX 3.141592653-2.6-1.40.26 (TeX Live 2025)'\n")
    exe.chmod(0o755)
    return exe


def test_missing_pdflatex_is_unavailable_with_a_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [])
    status = engines.probe_pdflatex()
    assert status.available is False
    assert status.path is None
    assert "not found" in status.reason


def test_found_pdflatex_reports_path_and_version(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = engines.probe_pdflatex()
    assert status.available is True
    assert status.path == str(exe)
    assert status.version.startswith("pdfTeX")


def test_known_tex_homes_are_searched_when_path_lacks_tex(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [str(tmp_path)])
    assert engines.probe_pdflatex().path == str(exe)


def test_wrong_override_fails_closed_and_never_searches(monkeypatch, tmp_path):
    _fake_pdflatex(tmp_path)  # a search WOULD find this one
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", tmp_path / "nope")
    status = engines.probe_pdflatex()
    assert status.available is False
    assert "MAESTRO_CS_PDFLATEX" in status.reason
    assert engines.pdflatex_command() == str(tmp_path / "nope")


def test_version_runs_once_per_path(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", exe)
    calls: list[list[str]] = []
    real_run = subprocess.run

    def counting_run(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(engines.subprocess, "run", counting_run)
    engines.probe_pdflatex()
    engines.probe_pdflatex()
    assert len(calls) == 1


def test_typst_probe_reports_version_and_fonts():
    status = engines.probe_typst()
    assert status.available is True
    assert status.version


def test_typst_probe_fails_when_a_font_dir_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "typst_font_paths", [tmp_path / "missing"])
    status = engines.probe_typst()
    assert status.available is False
    assert "missing" in status.reason


def test_probe_bundles_both_engines():
    both = engines.probe()
    assert both.typst.name == "typst"
    assert both.pdflatex.name == "pdflatex"
```

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_engines.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: app.services.engines` and
`AttributeError: maestro_cs_pdflatex`.

**Step 3: Add the setting**

In `backend/app/config.py`, directly after the `_parse_font_paths` validator:

```python
    # Explicit pdflatex binary. When set it WINS and is never searched around:
    # a wrong value makes the probe report unavailable with the reason, exactly
    # like the MCPB shim treats a wrong Docker path. Unset = search PATH plus the
    # known TeX homes (app/services/engines.py). Doubles as the test switch for
    # a TeX-less host: MAESTRO_CS_PDFLATEX=/nonexistent.
    maestro_cs_pdflatex: Path | None = None
```

**Step 4: Write the module**

```python
# backend/app/services/engines.py
"""Which PDF engines can THIS process run — the one place that looks for one.

A GUI-launched process (the desktop shell, a Claude Desktop child) has no shell
`PATH`, so MacTeX's `/Library/TeX/texbin` is invisible to it. The probe searches
the known TeX homes after `PATH`, and `pdf_render` runs the resolved absolute
path. `MAESTRO_CS_PDFLATEX` overrides the search and fails closed when wrong.

Cheap by design: `which` re-runs on every call (installing TeX while the app
runs is noticed on the next probe), the `--version` subprocess runs once per
resolved path per process.
"""
from __future__ import annotations

import glob
import importlib.metadata
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

# Where TeX installs put pdflatex when it is not on PATH. Globs sort newest
# TeX Live year first.
_TEX_HOMES_POSIX = (
    "/Library/TeX/texbin",
    "/usr/local/texlive/*/bin/*",
    "~/.TinyTeX/bin/*",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)
_TEX_HOMES_WINDOWS = (
    "%LOCALAPPDATA%\\Programs\\MiKTeX\\miktex\\bin\\x64",
    "C:\\texlive\\*\\bin\\windows",
)


@dataclass(frozen=True)
class EngineStatus:
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EnginesStatus:
    pdflatex: EngineStatus
    typst: EngineStatus


def _candidate_dirs() -> list[str]:
    homes = _TEX_HOMES_WINDOWS if sys.platform == "win32" else _TEX_HOMES_POSIX
    dirs: list[str] = []
    for pattern in homes:
        expanded = os.path.expandvars(os.path.expanduser(pattern))
        dirs.extend(sorted(glob.glob(expanded), reverse=True))
    return dirs


def find_pdflatex() -> tuple[str | None, str | None]:
    """(path, reason). An explicit override is not a hint: wrong = unavailable."""
    override = settings.maestro_cs_pdflatex
    if override is not None:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate), None
        return None, (
            f"MAESTRO_CS_PDFLATEX points at {override}, which is not an "
            "executable file; correct it or unset it to search the usual locations"
        )
    search = os.pathsep.join([os.environ.get("PATH", ""), *_candidate_dirs()])
    found = shutil.which("pdflatex", path=search)
    if found is None:
        return None, "pdflatex not found on PATH or in the usual TeX locations"
    return found, None


def pdflatex_command() -> str:
    """argv[0] for a pdflatex run: the override verbatim (wrong ones fail at
    spawn, by design), else the resolved path, else the bare name."""
    override = settings.maestro_cs_pdflatex
    if override is not None:
        return str(override)
    found, _ = find_pdflatex()
    return found or "pdflatex"


# path -> (version, reason). One --version per path per process.
_VERSION_CACHE: dict[str, tuple[str | None, str | None]] = {}


def reset_cache() -> None:
    _VERSION_CACHE.clear()


def _pdflatex_version(path: str) -> tuple[str | None, str | None]:
    if path in _VERSION_CACHE:
        return _VERSION_CACHE[path]
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=15, check=False
        )
        first = (result.stdout or "").strip().splitlines()
        outcome = (first[0], None) if result.returncode == 0 and first else (
            None, f"{path} --version failed (exit {result.returncode})"
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        outcome = (None, f"{path} could not be run: {exc}")
    _VERSION_CACHE[path] = outcome
    return outcome


def probe_pdflatex() -> EngineStatus:
    path, reason = find_pdflatex()
    if path is None:
        return EngineStatus("pdflatex", False, reason=reason)
    version, reason = _pdflatex_version(path)
    if version is None:
        return EngineStatus("pdflatex", False, path=path, reason=reason)
    return EngineStatus("pdflatex", True, version=version, path=path)


def pdflatex_available() -> bool:
    return probe_pdflatex().available


def probe_typst() -> EngineStatus:
    try:
        import typst  # noqa: F401 — presence is the point
    except ImportError:
        return EngineStatus("typst", False, reason="the typst package is not installed")
    version = importlib.metadata.version("typst")
    missing = [str(p) for p in settings.typst_font_paths if not Path(p).is_dir()]
    if missing:
        # typst falls back to embedded fonts SILENTLY for a missing dir — a
        # wrong typeface, not an error — so report it here instead.
        return EngineStatus(
            "typst", False, version=version,
            reason=f"font directory missing: {', '.join(missing)}",
        )
    return EngineStatus("typst", True, version=version)


def probe() -> EnginesStatus:
    return EnginesStatus(pdflatex=probe_pdflatex(), typst=probe_typst())
```

**Step 5: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_engines.py -q`
Expected: 8 passed.

**Step 6: Commit**

```bash
git add backend/app/services/engines.py backend/app/config.py backend/tests/test_engines.py
git commit -m "feat(engines): probe pdflatex and typst, with known TeX homes and a fail-closed override"
```

---

### Task 2: pdflatex runs by resolved path; a missing binary is a clean error

**Files:**
- Modify: `backend/app/services/pdf_render.py` (`_pdflatex_argv` ~line 124; `compile_pdf` ~line 333; `render_and_compile` ~line 566)
- Test: `backend/tests/test_render_fallback.py` (new; more tests join it in Task 3)

**Step 1: Write the failing tests**

```python
# backend/tests/test_render_fallback.py
"""Design 2026-09-19 §2.2: a render never changes engine silently, and a
missing pdflatex is an actionable error, never a 500 from FileNotFoundError."""
from pathlib import Path

import pytest

from app.services import engines, pdf_render

MINIMAL_TEX = "\\documentclass{article}\\begin{document}x\\end{document}"


def _no_tex(monkeypatch):
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "pdflatex not found (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/nonexistent/pdflatex")
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)


def test_argv_uses_the_resolved_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/opt/tex/bin/pdflatex")
    argv = pdf_render._pdflatex_argv(tmp_path / "x.tex", tmp_path, "x")
    assert argv[0] == "/opt/tex/bin/pdflatex"
    assert "-no-shell-escape" in argv


def test_compile_pdf_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path)


def test_render_and_compile_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    from app.services.template_validation import SAMPLE_RESUME

    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.render_and_compile(
            SAMPLE_RESUME, tmp_path / "r.tex", tmp_path / "r.pdf"
        )
```

(`render_and_compile` with `session=None` renders the bundled `resume.tex.j2`
through the latex branch, which is the second call site.)

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py -q`
Expected: the argv test fails on `"pdflatex" != "/opt/tex/bin/pdflatex"`; the
other two fail with `FileNotFoundError`, not `RuntimeError`.

**Step 3: Implement**

In `pdf_render.py`:

1. Import: `from app.services import engines, typst_compiler` (replace the
   existing `from app.services import typst_compiler`).
2. `_pdflatex_argv`: `argv = [engines.pdflatex_command(), "-no-shell-escape"]`
   and add one docstring sentence: "argv[0] is the path the probe resolved
   (`engines.pdflatex_command`), so a GUI-launched process with no shell PATH
   still finds MacTeX."
3. Add one runner used by BOTH call sites, keeping each site's comments:

```python
def _run_pdflatex(source_path: Path, out_dir: Path, stem: str) -> subprocess.CompletedProcess:
    """The one spawn. A missing binary is the actionable "install TeX or pick a
    Typst template" error, not a FileNotFoundError 500."""
    try:
        return subprocess.run(
            _pdflatex_argv(source_path, out_dir, stem),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_compile_env(out_dir),
            cwd=_compile_cwd(source_path),
        )
    except FileNotFoundError as exc:
        _, reason = engines.find_pdflatex()
        raise RuntimeError(
            "pdflatex is not installed on this machine "
            f"({reason or exc}). Install TeX or pick a Typst template."
        ) from exc
```

4. `compile_pdf`: replace its `subprocess.run(...)` block with
   `result = _run_pdflatex(tex_path, out_dir, stem)`.
5. `render_and_compile`: replace its `subprocess.run(...)` block with
   `result = _run_pdflatex(source_path, out_pdf_path.parent, out_pdf_path.stem)`,
   keeping the "SECOND pdflatex call site" comment above it (it still explains
   why `_compile_env` matters there).

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py tests/test_pdf_render.py tests/test_base_resumes_router.py tests/test_security_boundaries.py -q`
Expected: all pass. If an existing test pins `argv[0] == "pdflatex"`, change
that assertion to `argv[0].endswith("pdflatex")` and log the deviation.

**Step 5: Commit**

```bash
git add backend/app/services/pdf_render.py backend/tests/test_render_fallback.py
git commit -m "fix(render): run pdflatex by resolved path; a missing binary is an actionable RuntimeError"
```

---

### Task 3: The fallback resolver and `render_note`

**Files:**
- Modify: `backend/app/services/template_registry.py` (after `get_usable_template`, ~line 510)
- Modify: `backend/app/services/pdf_render.py` (`RenderedDoc` ~line 498; `render_document` ~line 515)
- Test: `backend/tests/test_render_fallback.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_render_fallback.py`:

```python
from app.models.template import Template
from app.services import template_registry as reg
from app.services.template_validation import SAMPLE_RESUME


def _seed_rows(db_session, *, typst_ready: bool = True):
    """Every seed as a draft row (no compile), then mark typst-classic ready."""
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session, validate=False)
    if typst_ready:
        db_session.get(Template, reg.TYPST_CLASSIC_ID).status = "ready"
        db_session.commit()


def test_latex_template_without_tex_renders_with_typst_and_says_so(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template("default", db_session)
    assert tmpl.id == reg.TYPST_CLASSIC_ID
    assert "TeX is not installed" in note
    assert "Typst Classic" in note and "Classic" in note

    doc = pdf_render.render_document(SAMPLE_RESUME, template_id="default", session=db_session)
    assert doc.engine == "typst"
    assert doc.resolved_template_id == reg.TYPST_CLASSIC_ID
    assert doc.render_note == note


def test_a_ready_typst_default_wins_over_typst_classic(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    mine = Template(id="mine", display_name="Mine", engine="typst", status="ready",
                    source=db_session.get(Template, reg.TYPST_CLASSIC_ID).source)
    db_session.add(mine)
    db_session.commit()
    reg.set_default(db_session, "mine")
    tmpl, note = pdf_render.resolve_render_template("xcharter_serif", db_session)
    assert tmpl.id == "mine"


def test_no_ready_typst_template_is_a_400_class_error(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    with pytest.raises(ValueError, match="needs TeX"):
        pdf_render.resolve_render_template("default", db_session)


def test_typst_templates_are_untouched_without_tex(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template(reg.TYPST_CLASSIC_ID, db_session)
    assert tmpl.id == reg.TYPST_CLASSIC_ID
    assert note is None


def test_latex_templates_are_untouched_with_tex(db_session, monkeypatch):
    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template("default", db_session)
    assert tmpl.id == "default"
    assert note is None
```

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py -q`
Expected: `AttributeError: … has no attribute 'resolve_render_template'`.

**Step 3: Implement**

`template_registry.py`, after `get_usable_template`:

```python
def first_ready_typst(session: Session) -> Template | None:
    """The substitute for a LaTeX template on a TeX-less host, in a FIXED
    order so the same install always falls back the same way: the default if
    it is a ready Typst template, else typst-classic, else any ready Typst
    template by id."""
    default = session.scalar(select(Template).where(Template.is_default.is_(True)))
    for candidate in (default, session.get(Template, TYPST_CLASSIC_ID)):
        if (
            candidate is not None
            and candidate.engine == "typst"
            and candidate.status == "ready"
            and candidate.archived_at is None
        ):
            return candidate
    return session.scalar(
        select(Template)
        .where(
            Template.engine == "typst",
            Template.status == "ready",
            Template.archived_at.is_(None),
        )
        .order_by(Template.id)
    )
```

`pdf_render.py`:

```python
TEX_MISSING_NO_TYPST = (
    "This template needs TeX, which is not installed on this machine. "
    "Install TeX or pick a Typst template."
)


def tex_fallback_note(substitute: str, requested: str) -> str:
    return (
        "TeX is not installed on this machine; rendered with "
        f"{substitute} instead of {requested}."
    )


def resolve_render_template(template_id: str | None, session):
    """The ONE fallback rule (design 2026-09-19 §2.2): resolve as before, then a
    LaTeX template on a host with no pdflatex becomes the first ready Typst
    template, with a note that names both. No ready Typst template → ValueError
    (the routers' 400). Document renders use this; template VALIDATION never
    does — validating template A must never validate template B."""
    from app.services import template_registry  # lazy import to avoid a cycle

    tmpl = template_registry.get_usable_template(template_id, session)
    if tmpl.engine != "latex" or engines.pdflatex_available():
        return tmpl, None
    substitute = template_registry.first_ready_typst(session)
    if substitute is None:
        raise ValueError(TEX_MISSING_NO_TYPST)
    note = tex_fallback_note(
        substitute.display_name or substitute.id, tmpl.display_name or tmpl.id
    )
    logger.info("render fallback: %s", note)
    return substitute, note
```

(`pdf_render.py` has no logger yet: add `import logging` and
`logger = logging.getLogger(__name__)` at the top.)

`RenderedDoc` gains a field after `resolved_template_id`:

```python
    # Non-null ONLY when the engine was substituted (TeX missing); says why.
    render_note: str | None = None
```

`render_document`: replace
`tmpl = template_registry.get_usable_template(template_id, session)` with
`tmpl, note = resolve_render_template(template_id, session)` (drop the now
unused lazy import there if nothing else uses it) and pass
`render_note=note` into BOTH `RenderedDoc(...)` constructions.

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py tests/test_template_registry.py tests/test_pdf_render_typst.py -q`
Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/services/template_registry.py backend/app/services/pdf_render.py backend/tests/test_render_fallback.py
git commit -m "feat(render): fall back to the first ready Typst template without TeX, and say so"
```

---

### Task 4: `render_note` on both render responses

**Files:**
- Modify: `backend/app/schemas/application.py` (`RenderResult`, ~line 105)
- Modify: `backend/app/schemas/base_resume.py` (`BaseResumeDetail`, ~line 38)
- Modify: `backend/app/services/base_resume_render.py` (~line 45)
- Modify: `backend/app/routers/base_resumes.py` (`_detail` ~line 155; the render endpoint ~line 795)
- Modify: `backend/app/routers/applications.py` (`RenderResult(...)` ~line 512)
- Test: `backend/tests/test_render_fallback.py` (append)

**Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from tests.test_applications_router import _job
from tests.test_base_resumes_router import _override_db, _seed


def test_base_resume_render_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post("/api/base-resumes/data_scientist/render")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved_engine"] == "typst"
    assert "TeX is not installed" in body["render_note"]
    assert Path(body["pdf_path"]).exists()


def test_application_render_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    from app.routers import applications as applications_router

    monkeypatch.setattr(
        applications_router.base_resume_data, "load_base_resume",
        lambda slug, session=None: SAMPLE_RESUME,
    )
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="data_scientist", status="draft")
    db_session.add(application)
    db_session.commit()
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["resolved_engine"] == "typst"
    assert "TeX is not installed" in r.json()["render_note"]


def test_render_note_is_null_when_nothing_was_substituted(db_session, tmp_path, monkeypatch):
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            f"/api/base-resumes/data_scientist/render?template_id={reg.TYPST_CLASSIC_ID}"
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["render_note"] is None
```

If `_job` / `_seed` / `_override_db` have different names or signatures in
those modules, adapt the imports (they exist: `_seed(db_session, slug=,
data_json=)`, `_override_db(db_session)`, `_job(db_session)`) and log it.

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py -q`
Expected: `KeyError: 'render_note'`.

**Step 3: Implement**

- `RenderResult`: add `render_note: str | None = None` after `template_fallback`.
- `BaseResumeDetail`: add `render_note: str | None = None` after `template_fallback`.
- `base_resume_render.render_base_resume`: after `row.resolved_engine = doc.engine`
  add `row.render_note = doc.render_note`.
- `routers/base_resumes.py::_detail`: add a keyword parameter
  `render_note: str | None = None` and pass `render_note=render_note` into
  `BaseResumeDetail(...)`. In the render endpoint's `return _detail(...)` add
  `render_note=getattr(rendered, "render_note", None)`.
- `routers/applications.py`: add `render_note=doc.render_note` to the
  `RenderResult(...)` construction.

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_render_fallback.py tests/test_base_resumes_router.py tests/test_applications_router.py -q`
Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/schemas backend/app/services/base_resume_render.py backend/app/routers/base_resumes.py backend/app/routers/applications.py backend/tests/test_render_fallback.py
git commit -m "feat(render): render_note on base-resume and application render responses"
```

---

### Task 5: Contact URLs in `_header.tex.j2` use `latex_escape_url` (§11 item 7)

**Files:**
- Modify: `backend/app/templates/_header.tex.j2` (three `\href{…}` URL arguments)
- Test: `backend/tests/test_cover_letter_render.py` (append)

**Step 1: Write the failing tests**

```python
import shutil

import pytest

from app.services import pdf_render
from app.services.template_validation import SAMPLE_RESUME

TILDE_CONTACT = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "location": "Austin, TX",
    "linkedin": "linkedin.com/in/~jane",
    "github": "github.com/jane_dev",
}


def test_cover_letter_header_urls_survive_a_tilde_and_underscore():
    tex = render_cover_letter_tex(contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1))
    assert r"\href{https://linkedin.com/in/~jane}" in tex
    assert r"\href{https://github.com/jane_dev}" in tex
    # Display text is typeset, so it keeps body escaping.
    assert r"\textasciitilde{}jane" in tex


def test_resume_header_urls_survive_a_tilde_and_underscore():
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    tex = pdf_render.render_tex_from_source(source, {**SAMPLE_RESUME, "contact": TILDE_CONTACT})
    assert r"\href{https://linkedin.com/in/~jane}" in tex
    assert r"\href{https://github.com/jane_dev}" in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_with_tilde_url_compiles(tmp_path):
    tex = render_cover_letter_tex(contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1))
    assert pdf_render.compile_cover_letter_pdf(tex, tmp_path).exists()
```

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cover_letter_render.py -q`
Expected: the two escaping tests fail (`\textasciitilde{}` inside the `\href`
URL argument).

**Step 3: Implement**

In `_header.tex.j2`, change ONLY the URL argument of each `\href`:

- `\href{mailto:((( contact.email|latex_escape )))}` → `\href{mailto:((( contact.email|latex_escape_url )))}`
- `\href{https://((( contact.linkedin|latex_escape )))}` → `\href{https://((( contact.linkedin|latex_escape_url )))}`
- `\href{https://((( contact.github|latex_escape )))}` → `\href{https://((( contact.github|latex_escape_url )))}`

The display text (`\underline{((( … |latex_escape )))}`) stays as it is.

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_cover_letter_render.py tests/test_pdf_render.py tests/test_template_validation.py -q`
Expected: all pass (the compile test runs only where pdflatex exists).

**Step 5: Commit**

```bash
git add backend/app/templates/_header.tex.j2 backend/tests/test_cover_letter_render.py
git commit -m "fix(render): header contact URLs go through latex_escape_url (SYSTEM.md §11 item 7)"
```

---

### Task 6: The cover letter on both engines

**Files:**
- Create: `backend/app/templates/cover_letter.typ`
- Modify: `backend/app/services/pdf_render.py` (cover-letter section, ~line 616 to end)
- Modify: `backend/app/routers/qa.py` (`render_cover_letter`, ~line 155)
- Modify: `backend/app/schemas/qa.py` (`QAEntryRead`)
- Modify: `backend/tests/test_qa_router.py` (`fake_compile` in `test_render_cover_letter_writes_pdf_and_sets_path`, ~line 289)
- Test: `backend/tests/test_cover_letter_typst.py` (new)

**Step 1: Write the failing tests**

```python
# backend/tests/test_cover_letter_typst.py
"""Cover letters follow the resume's engine (design 2026-09-19 §2.3)."""
import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from app.services import pdf_render

pytest.importorskip("typst")
pytest.importorskip("pdfplumber")

CONTACT = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "",          # cleared in the editor: must not print "None"
    "location": "Austin, TX",
    "linkedin": "linkedin.com/in/janedoe",
    "github": None,
}
BODY = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for the Data Analyst role at Acme.\n\n"
    "Sincerely,\nJane Doe"
)
TODAY = date(2026, 5, 1)


def _text(pdf: Path) -> str:
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        return " ".join(" ".join((p.extract_text() or "").split()) for p in doc.pages)


def _words(text: str) -> set[str]:
    # Icon glyphs (LaTeX fontawesome) and layout tokens fall out; words stay.
    return set(re.findall(r"[a-z0-9][a-z0-9@./'-]*", text.lower()))


def test_typst_cover_letter_compiles_with_header_date_and_body(tmp_path):
    doc = pdf_render.render_cover_letter(engine="typst", contact=CONTACT, body=BODY, today=TODAY)
    assert doc.engine == "typst"
    pdf = pdf_render.compile_cover_letter_pdf(
        doc.source_text, tmp_path, stem="cl", engine=doc.engine, sys_inputs=doc.sys_inputs
    )
    text = _text(pdf)
    for needle in ("Jane Doe", "jane@example.com", "Austin, TX", "May 1, 2026",
                   "I am excited to apply", "Sincerely"):
        assert needle in text, text
    assert "None" not in text and "null" not in text


def test_latex_cover_letter_is_the_default_engine():
    doc = pdf_render.render_cover_letter(engine="latex", contact=CONTACT, body=BODY, today=TODAY)
    assert doc.engine == "latex"
    assert "\\begin{document}" in doc.source_text


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_parity_across_engines(tmp_path):
    latex = pdf_render.render_cover_letter(engine="latex", contact=CONTACT, body=BODY, today=TODAY)
    typst = pdf_render.render_cover_letter(engine="typst", contact=CONTACT, body=BODY, today=TODAY)
    a = _text(pdf_render.compile_cover_letter_pdf(latex.source_text, tmp_path / "l", engine="latex"))
    b = _text(pdf_render.compile_cover_letter_pdf(
        typst.source_text, tmp_path / "t", engine="typst", sys_inputs=typst.sys_inputs
    ))
    assert _words(a) == _words(b)
```

And the router test — in `tests/test_qa_router.py` change the fake to accept
the engine kwargs and add the fallback case:

```python
    def fake_compile(source, out_dir, stem="cover_letter", **kwargs):
```

Append to `tests/test_qa_router.py` (reusing that test's setup):

```python
def test_render_cover_letter_follows_the_resume_engine_without_tex(
    db_session, tmp_path, monkeypatch
):
    from app.models.template import Template
    from app.services import engines, template_registry as reg

    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session, validate=False)
    db_session.get(Template, reg.TYPST_CLASSIC_ID).status = "ready"
    db_session.commit()

    application = _application(db_session)
    entry = QAEntry(application_id=application.id, kind="cover_letter",
                    prompt="cover letter", answer="Dear team,\n\nHello.\n\nJane")
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        qa.base_resume_data, "load_base_resume",
        lambda slug, session=None: {"contact": {"name": "Jane Doe", "email": "jane@example.com"}},
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/render")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert Path(body["pdf_path"]).exists()
    assert "TeX is not installed" in body["render_note"]
```

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cover_letter_typst.py tests/test_qa_router.py -q`
Expected: `AttributeError: … 'render_cover_letter'`; the router test fails on
`render_note`.

**Step 3: Write the Typst template**

```typst
// backend/app/templates/cover_letter.typ
// The bundled cover letter for the Typst engine — the counterpart of
// cover_letter.tex.j2 + _header.tex.j2, self-contained because a Typst
// compile is root-scoped to one staged file (typst_compiler) and cannot
// include a bundled partial. Header layout and spacing mirror the LaTeX one.
//
// Data contract (every sys.input is a string): contact = ResumeData.contact
// JSON with blank strings already coerced to null; paragraphs = JSON array of
// strings; today = an already-formatted date; fmt = merged formatting JSON
// (honors font_size and header_align, like the LaTeX header partial).
#let contact = json(bytes(sys.inputs.contact))
#let paragraphs = json(bytes(sys.inputs.paragraphs))
#let today = sys.inputs.today
#let fmt = json(bytes(sys.inputs.fmt))

#set page(paper: "us-letter", margin: (x: 0.9in, y: 0.8in))
#set text(font: ("XCharter", "Libertinus Serif"), size: fmt.font_size * 1pt)
#set par(justify: false, leading: 0.6em)

#let header_alignment = if fmt.header_align == "left" { left } else if fmt.header_align == "right" { right } else { center }
#let field(key) = contact.at(key, default: none)

#align(header_alignment)[
  #text(size: 1.7em, weight: "bold", smallcaps(contact.name))
  #if field("location") != none [\ #field("location")]
  #{
    let parts = ()
    if field("phone") != none { parts.push(field("phone")) }
    if field("email") != none { parts.push(link("mailto:" + field("email"))[#underline(field("email"))]) }
    if field("linkedin") != none { parts.push(link("https://" + field("linkedin"))[#underline(field("linkedin"))]) }
    if field("github") != none { parts.push(link("https://" + field("github"))[#underline(field("github"))]) }
    if parts.len() > 0 [\ #text(size: 0.9em, parts.join([ #sym.dot.c ]))]
  }
]

#v(12pt)
#today

#v(6pt)
#for p in paragraphs [
  #p
  #v(6pt)
]
```

If typst rejects a construct, fix the template until the compile test passes
and log the change; the test is the specification, the snippet is a start.

**Step 4: Implement the Python side**

In `pdf_render.py`, replace the cover-letter section (from
`def render_cover_letter_tex` to the end) with:

```python
COVER_LETTER_TEMPLATE = "cover_letter.tex.j2"
COVER_LETTER_TYPST_TEMPLATE = "cover_letter.typ"


def cover_letter_paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def render_cover_letter_tex(
    *,
    contact: dict[str, Any],
    body: str,
    today: _date,
) -> str:
    template = _environment().get_template(COVER_LETTER_TEMPLATE)
    # The cover letter includes the shared _header.tex.j2 partial, which reads
    # fmt.* (e.g. fmt.header_align). Pass default formatting so the header keeps
    # its historical centered layout and does not raise UndefinedError.
    return template.render(
        contact=contact,
        body_paragraphs=cover_letter_paragraphs(body),
        today_date=today.strftime("%B %-d, %Y"),
        fmt=merge_formatting(None),
    )


def cover_letter_typst_inputs(
    *, contact: dict[str, Any], body: str, today: _date
) -> dict[str, str]:
    """sys_inputs for cover_letter.typ; blanks coerced like the resume path so a
    cleared phone never prints as "None"."""
    return {
        "contact": json.dumps(_coerce_blank_to_none(dict(contact))),
        "paragraphs": json.dumps(cover_letter_paragraphs(body)),
        "today": today.strftime("%B %-d, %Y"),
        "fmt": merge_formatting(None).model_dump_json(),
    }


def render_cover_letter(
    *, engine: str, contact: dict[str, Any], body: str, today: _date
) -> RenderedDoc:
    """Engine-dispatching render half for cover letters. The engine is the
    resolved RESUME template's engine (routers/qa.py), so a Typst-template user
    and a TeX-less host both get Typst, and a LaTeX user sees no change."""
    if engine == "typst":
        source = (TEMPLATE_DIR / COVER_LETTER_TYPST_TEMPLATE).read_text(encoding="utf-8")
        return RenderedDoc(
            "typst", source, cover_letter_typst_inputs(contact=contact, body=body, today=today)
        )
    return RenderedDoc("latex", render_cover_letter_tex(contact=contact, body=body, today=today))


def compile_cover_letter_pdf(
    source_text: str,
    out_dir: Path,
    stem: str = "cover_letter",
    *,
    engine: str = "latex",
    sys_inputs: dict[str, str] | None = None,
) -> Path:
    """Cover-letter compile for either engine. The latex branch is a thin alias
    for `compile_pdf` — see its docstring for why the two are no longer separate
    implementations. Kept as a named entry point because callers read better for
    it, and because the `latex-render-path` ledger row (SYSTEM §13) tracks it by
    name."""
    if engine == "typst":
        return compile_typst_pdf(source_text, out_dir, stem, sys_inputs=sys_inputs or {})
    return compile_pdf(source_text, out_dir, stem, document="cover letter")
```

`schemas/qa.py::QAEntryRead`: add `render_note: str | None = None` after
`pdf_path` (transient; set on the ORM row before serialization, like
`resolved_engine` on base resumes).

`routers/qa.py::render_cover_letter`: replace the two lines

```python
    tex_text = pdf_render.render_cover_letter_tex(...)
    pdf_path = pdf_render.compile_cover_letter_pdf(tex_text, out_dir, stem=stem)
```

with

```python
    try:
        tmpl, render_note = pdf_render.resolve_render_template(application.template_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    doc = pdf_render.render_cover_letter(
        engine=tmpl.engine, contact=contact, body=entry.answer, today=rendered_at.date()
    )
    pdf_path = pdf_render.compile_cover_letter_pdf(
        doc.source_text, out_dir, stem=stem, engine=doc.engine, sys_inputs=doc.sys_inputs
    )
```

and after `db.refresh(entry)` add `entry.render_note = render_note`.

Move the resolver call ABOVE `application_artifacts.get_dir(...)` so a 400
never leaves an empty artifact directory behind.

**Step 5: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_cover_letter_typst.py tests/test_cover_letter_render.py tests/test_qa_router.py tests/test_qa.py -q`
Expected: all pass. If the parity assertion differs by a systematic extraction
artifact (a ligature, a stray icon codepoint), tighten `_words` for that class
only and log the deviation with the offending token.

**Step 6: Commit**

```bash
git add backend/app/templates/cover_letter.typ backend/app/services/pdf_render.py backend/app/routers/qa.py backend/app/schemas/qa.py backend/tests/test_cover_letter_typst.py backend/tests/test_qa_router.py
git commit -m "feat(cover-letter): render on the resume's engine; bundled cover_letter.typ"
```

---

### Task 7: Seeds short-circuit without TeX; `engine_available` on templates

**Files:**
- Modify: `backend/app/services/template_registry.py` (`_seed_validate`, ~line 287)
- Modify: `backend/app/schemas/template.py` (`TemplateSummary`)
- Modify: `backend/app/routers/templates.py` (`_with_fmt_keys`, ~line 25; `list_templates`)
- Test: `backend/tests/test_template_registry.py`, `backend/tests/test_templates_router.py` (append)

**Step 1: Write the failing tests**

Append to `tests/test_template_registry.py`:

```python
from app.services import engines, template_validation as tv


def test_seed_validation_without_tex_leaves_latex_seeds_draft_with_a_reason(db_session, monkeypatch):
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session, validate=True)

    default = reg.get(db_session, "default")
    assert default.status == "draft"
    assert default.last_error == "requires TeX (pdflatex not found)"
    assert reg.get(db_session, reg.TYPST_CLASSIC_ID).status == "ready"
    # Nothing was compiled, so nothing was "attempted": the guard is unconsumed
    # and the next validating ensure (next boot) re-checks the probe.
    assert "default" not in reg._SEED_VALIDATION_ATTEMPTED

    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)
    calls: list[str] = []

    def fake_validate(template_id, session):
        calls.append(template_id)
        row = session.get(Template, template_id)
        row.status, row.last_error = "ready", None
        session.commit()
        return {"ok": True}

    monkeypatch.setattr(tv, "validate_template", fake_validate)
    reg.ensure_seed_templates(db_session, validate=True)
    assert "default" in calls
    assert reg.get(db_session, "default").status == "ready"
```

(`Template` is imported at the top of that test module already; if not, add
`from app.models.template import Template`.)

Append to `tests/test_templates_router.py`:

```python
def test_list_reports_engine_availability(db_session, monkeypatch):
    from app.services import engines

    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/templates").json()
        detail = TestClient(app).get("/api/templates/default").json()
    finally:
        app.dependency_overrides.clear()
    by_engine = {t["engine"]: t["engine_available"] for t in body}
    assert by_engine == {"latex": False, "typst": True}
    assert detail["engine_available"] is False

    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        body = TestClient(app).get("/api/templates").json()
    finally:
        app.dependency_overrides.clear()
    assert all(t["engine_available"] for t in body)
```

**Step 2: Run them to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_template_registry.py tests/test_templates_router.py -q -k "tex or engine_availability"`
Expected: the registry test fails (`last_error` is a compile error or None);
the router test fails with `KeyError: 'engine_available'`.

**Step 3: Implement**

`template_registry.py`: import `engines` alongside `pdf_render, typst_compiler`
and add the short-circuit at the top of `_seed_validate`, BEFORE the attempt
guard is consumed:

```python
    if tmpl.id in _SEED_VALIDATION_ATTEMPTED:
        return
    if tmpl.engine == "latex" and not engines.pdflatex_available():
        # Not an attempt: nothing compiled, so the guard stays unconsumed and
        # the next validating ensure (startup, or POST /validate) re-checks the
        # probe. The reason is recorded so the gallery can say "requires TeX".
        reason = "requires TeX (pdflatex not found)"
        if tmpl.last_error != reason:
            tmpl.last_error = reason
            session.commit()
        return
    _SEED_VALIDATION_ATTEMPTED.add(tmpl.id)
```

`schemas/template.py::TemplateSummary`: after `engine`:

```python
    # False when this template's engine cannot run on the backend host (a LaTeX
    # template with no pdflatex). The gallery shows "requires TeX"; a render
    # through it falls back to Typst and says so (render_note). Not stored.
    engine_available: bool = True
```

`routers/templates.py`:

```python
from app.services import engines


def _with_fmt_keys(row, pdflatex_ok: bool | None = None):
    # Attach the derived fmt.* key list so from_attributes serialization picks it
    # up (it is computed from source, not stored on the model).
    row.supported_fmt_keys = reg.supported_fmt_keys(row.source or "", row.engine)
    if pdflatex_ok is None:
        pdflatex_ok = engines.pdflatex_available()
    row.engine_available = row.engine != "latex" or pdflatex_ok
    return row
```

and in `list_templates`: `pdflatex_ok = engines.pdflatex_available()` once,
then `return [_with_fmt_keys(row, pdflatex_ok) for row in rows]`.

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_template_registry.py tests/test_templates_router.py tests/test_typst_classic_seed.py tests/test_user_templates.py tests/test_seeding.py -q`
Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/services/template_registry.py backend/app/schemas/template.py backend/app/routers/templates.py backend/tests/test_template_registry.py backend/tests/test_templates_router.py
git commit -m "feat(templates): seeds record 'requires TeX' instead of failing; engine_available on list and detail"
```

---

### Task 8: `engines` in `setup/status`

**Files:**
- Modify: `backend/app/schemas/setup_status.py`
- Modify: `backend/app/services/setup_status.py` (`build_status`, ~line 165 and the `template=` step)
- Test: `backend/tests/test_setup_status.py` (append)

**Step 1: Write the failing test**

```python
def test_status_reports_engines_and_default_engine_availability(client, monkeypatch):
    from app.services import engines

    monkeypatch.setattr(
        engines, "probe_pdflatex",
        lambda: engines.EngineStatus("pdflatex", False, reason="pdflatex not found (test)"),
    )
    body = _status(client)
    assert body["engines"]["pdflatex"]["available"] is False
    assert "not found" in body["engines"]["pdflatex"]["reason"]
    assert body["engines"]["typst"]["available"] is True
    assert body["engines"]["typst"]["version"]
    # The seeded default is LaTeX Classic, so its engine is the missing one.
    assert body["template"]["detail"]["default_engine_available"] is False
    assert body["template"]["done"] is False  # engines never change completeness
```

**Step 2: Run it to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_setup_status.py -q -k engines`
Expected: `KeyError: 'engines'`.

**Step 3: Implement**

`schemas/setup_status.py`:

```python
class EngineProbe(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    reason: str | None = None


class EnginesProbe(BaseModel):
    model_config = {"from_attributes": True}

    pdflatex: EngineProbe
    typst: EngineProbe
```

and on `SetupStatus`, after `template`:

```python
    # Which PDF engines this backend can run. Informational: never part of
    # `complete` (Typst is always shipped, so a PDF is always possible).
    engines: EnginesProbe
```

`services/setup_status.py`: import `engines` in the `from app.services import (…)`
block and `EnginesProbe` from the schema; in `build_status`, before the
`steps = SetupStatus(...)` construction:

```python
    probed = engines.probe()
    default_engine_available = (
        default_tpl is None or default_tpl.engine != "latex" or probed.pdflatex.available
    )
```

add `"default_engine_available": default_engine_available,` to the template
step's `detail` dict, and `engines=EnginesProbe.model_validate(probed),` to
the `SetupStatus(...)` call.

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest tests/test_setup_status.py mcp_server/tests/test_workflow.py -q`
Expected: all pass (the MCP workflow reads `setup_status` dicts by key, so an
added key is harmless; confirm).

**Step 5: Commit**

```bash
git add backend/app/schemas/setup_status.py backend/app/services/setup_status.py backend/tests/test_setup_status.py
git commit -m "feat(setup): report PDF engine availability in setup/status"
```

---

### Task 9: MCP docstrings carry the two new facts

**Files:**
- Modify: `backend/mcp_server/server.py` (`render_pdf` ~line 941, `list_templates` ~line 1034, `get_template` ~line 1043, `create_template_draft` ~line 1061)
- Test: `backend/mcp_server/tests/test_server.py` (append)

The tools pass REST JSON through verbatim, so `render_note` and
`engine_available` already flow; the docstring is the API (SYSTEM.md §7), so
the agent must be told they exist.

**Step 1: Write the failing test**

```python
def test_engine_availability_is_documented_on_the_template_and_render_tools():
    assert "render_note" in srv.render_pdf.__doc__
    assert "engine_available" in srv.list_templates.__doc__
    assert "engine_available" in srv.get_template.__doc__
    assert "TeX" in srv.create_template_draft.__doc__
```

**Step 2: Run it to verify it fails**

Run: `cd backend && python3 -m pytest mcp_server/tests/test_server.py -q -k engine_availability`
Expected: FAIL on the first assertion.

**Step 3: Implement** — add ONE sentence to each docstring (keep every tool
under the truncation budget test):

- `render_pdf`: after the `template_fallback` sentence: `render_note` is
  non-null only when the backend has no TeX and a LaTeX template was rendered
  through a Typst template instead; it names both.
- `list_templates`: `engine_available=false` marks a LaTeX template on a
  backend with no TeX: still pickable, renders through Typst with a
  `render_note`.
- `get_template`: same fact, one clause: "`engine_available` (see
  list_templates)".
- `create_template_draft`: "A LaTeX draft cannot validate on a backend with no
  TeX (list_templates → engine_available); use engine='typst' there."

**Step 4: Run the tests**

Run: `cd backend && python3 -m pytest mcp_server/tests/ -q`
Expected: all pass, including
`test_registered_tool_docstrings_fit_client_truncation_budget`.

**Step 5: Commit**

```bash
git add backend/mcp_server/server.py backend/mcp_server/tests/test_server.py
git commit -m "docs(mcp): render_note and engine_available in the tool docstrings"
```

---

### Task 10: Frontend — "requires TeX" badges and the engines checklist row

**Files:**
- Modify: `frontend/lib/types.ts` (`SetupStatus` ~line 401; `TemplateSummary` ~line 1018)
- Modify: `frontend/components/templates/template-gallery.tsx` (`TemplateBadgeStrip`, ~line 48)
- Modify: `frontend/app/templates/[id]/page.tsx` (~line 253)
- Modify: `frontend/components/setup/setup-steps.ts` (`SetupStepView.id` union; the `steps` array)
- Modify: `frontend/components/setup/getting-started-card.tsx` (`ACTION_LABELS`)

No unit runner exists for the frontend; the gates are `npx tsc --noEmit`,
`npm run lint`, `npm run build` (from `frontend/`).

**Step 1: Types**

`TemplateSummary`, after `engine`:

```ts
  /**
   * False when this template's engine cannot run on the backend host (a LaTeX
   * template with no pdflatex). Still pickable: a render through it falls back
   * to a Typst template and the response says so in `render_note`.
   */
  engine_available: boolean;
```

`SetupStatus`, after `template`:

```ts
  /** Which PDF engines the backend can run. Informational, never blocks. */
  engines: {
    pdflatex: EngineProbe;
    typst: EngineProbe;
  };
```

with, above `SetupStatus`:

```ts
interface EngineProbe {
  name: string;
  available: boolean;
  version: string | null;
  path: string | null;
  reason: string | null;
}
```

**Step 2: Gallery and detail badges**

In `TemplateBadgeStrip`, directly after the engine badge:

```tsx
      {!template.engine_available && (
        <Badge
          variant="outline"
          className="border-amber-500/40 text-amber-600 dark:text-amber-400"
          title="TeX is not installed where the backend runs. A resume using this template renders through a Typst template instead, and the render says so, until TeX is installed."
        >
          requires TeX
        </Badge>
      )}
```

In `app/templates/[id]/page.tsx`, after the engine badge, the same block
reading `tq.data.engine_available`.

**Step 3: Checklist row**

`setup-steps.ts`: add `| "engines"` to the `id` union, and after the
`template` step object:

```ts
    {
      id: "engines",
      label: "PDF engines",
      title: "PDF engines",
      detail: status.engines.pdflatex.available
        ? `Typst ready · TeX ${status.engines.pdflatex.version ?? "found"}`
        : "Typst ready · TeX not found (LaTeX templates render with Typst until it is installed)",
      done: status.engines.typst.available,
      home: "/templates",
      anchor: "template-gallery",
    },
```

`getting-started-card.tsx`: `engines: "See templates",` in `ACTION_LABELS`.

The pill strip lists only unfinished steps, so this row appears there only if
Typst itself is broken (font dir missing), which is the one case worth a pill.

**Step 4: Gates**

Run, from `frontend/`: `npx tsc --noEmit && npm run lint && npm run build`
Expected: clean. If `SetupStepView.id` is switched over somewhere with an
exhaustive check, add the new id there and log it.

**Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/components/templates/template-gallery.tsx "frontend/app/templates/[id]/page.tsx" frontend/components/setup/setup-steps.ts frontend/components/setup/getting-started-card.tsx
git commit -m "feat(ui): 'requires TeX' badges and a PDF-engines row in the setup checklist"
```

---

### Task 11: User docs

**Files:**
- Modify: `README.md` (the two-engines paragraph ~line 776; troubleshooting ~line 1067)
- Modify: `KNOWN_ISSUES.md` (Rendering bullet ~line 25; "Two render engines" bullet ~line 231)
- Modify: `CHANGELOG.md` (`## [Unreleased]`: add `### Added` and `### Fixed` after the Breaking changes list, or extend them if present)
- Modify: `.env.example` (a commented `MAESTRO_CS_PDFLATEX` line near the ports block; note it is for a host/venv backend, the image has TeX)

Content, one sentence each unless stated:

- README engines paragraph: add "TeX is optional: where `pdflatex` is missing
  (a host-run backend, later the desktop app) a LaTeX template renders through
  the first ready Typst template and the response, the gallery and the setup
  checklist say so — nothing is substituted silently."
- README troubleshooting entry "`pdflatex` or `typst` compilation failures on
  boot": rewrite to: seeds that need TeX on a host without it are left as
  drafts with "requires TeX" and validate on the next boot after TeX is
  installed; `GET /api/setup/status` → `engines` says what the backend found;
  `MAESTRO_CS_PDFLATEX` names a binary outside the usual locations.
- KNOWN_ISSUES Rendering bullet: "…cross-engine parity is enforced by tests,
  cover letters included."; "Two render engines" bullet: add "Without TeX,
  LaTeX templates fall back to Typst with a `render_note`; the default stays
  LaTeX where TeX exists."
- CHANGELOG `[Unreleased]` → `### Added`: engine probe (`GET /api/setup/status`
  `engines`), `render_note` on render responses, `engine_available` on
  templates, Typst cover letter (`cover_letter.typ`), `MAESTRO_CS_PDFLATEX`.
  `### Fixed`: contact URLs with `~`/`_` in the header partial no longer
  corrupt the link target (both resume and cover letter).

Run: `git diff --stat` and read each hunk once for accuracy against the code.

Commit:

```bash
git add README.md KNOWN_ISSUES.md CHANGELOG.md .env.example
git commit -m "docs: TeX is optional — fallback, render_note, engine_available, MAESTRO_CS_PDFLATEX"
```

---

### Task 12: SYSTEM.md, the enforcement pin, the ledger mirror

**Files:**
- Modify: `SYSTEM.md` (§2 ~lines 89–92; §6 after `{#inv-pdf-word-spacing}` ~line 417; §9 the "Never verify new code…" bullet ~line 707; §11 item 7 ~line 800; §12 top ~line 856; §13 `latex-render-path` row ~line 963)
- Modify: `.system_md_enforcement.json` (`invariants`)
- Modify: `.slopledger.json` (`latex-render-path.hand_check`)

SYSTEM.md is at 999/1000 lines. Every addition below is paid for by reflowing
prose in the SAME section (join short wrapped lines; never drop a fact).
Verify losslessness with a word-stream diff before committing:

```bash
git show HEAD:SYSTEM.md | tr -s ' \n' '\n' > /tmp/old.words; tr -s ' \n' '\n' < SYSTEM.md > /tmp/new.words; diff /tmp/old.words /tmp/new.words
```

Only the words you meant to add or remove may appear.

**Edits:**

1. §2 `services/` line: `pdf_render (dual-engine: pdflatex + typst), engines (the probe), pdf_preview,`;
   `templates/` line: `bundled .tex.j2 sources, typst_classic.typ, cover_letter.typ`.
2. §6, a new invariant after `{#inv-pdf-word-spacing}`:

   ```
   - **A render never changes engine silently** `{#inv-render-fallback-explained}`: with no `pdflatex`
     (`services/engines`, the ONE probe; `MAESTRO_CS_PDFLATEX` overrides and fails closed) a LaTeX
     template renders through the first ready Typst template and `render_note` names both — resumes,
     base resumes and cover letters alike (`pdf_render.resolve_render_template`); no ready Typst
     template is a 400, never a 500. Template VALIDATION never substitutes. Pinned by
     `tests/test_render_fallback.py`.
   ```
3. §9 "Never verify new code…" bullet: replace `+ /Library/TeX/texbin on PATH`
   with `(TeX optional: the probe searches /Library/TeX/texbin itself; MAESTRO_CS_PDFLATEX=/nonexistent simulates a TeX-less host)`.
4. §11: delete item 7's two lines. Do NOT renumber.
5. §12, a new first gotcha:

   ```
   - **A GUI-launched process has no shell `PATH`** (2026-09-19): MacTeX lives in `/Library/TeX/texbin`,
     which a desktop app never sees; `engines.find_pdflatex` searches the known TeX homes and pdflatex
     runs by the resolved absolute path — never assume a bare `pdflatex` resolves.
   ```
6. §13 `latex-render-path` row: replace `cover letters ported off compile_cover_letter_pdf` with
   `cover_letter.tex.j2 has no caller (render_cover_letter(engine="latex") unreachable)`.
7. `.system_md_enforcement.json` → `invariants["inv-render-fallback-explained"]`:

   ```json
   [
     {"path": "backend/tests/test_render_fallback.py",
      "symbol": "test_latex_template_without_tex_renders_with_typst_and_says_so"},
     {"path": "backend/app/services/pdf_render.py", "symbol": "resolve_render_template"},
     {"path": "backend/app/services/engines.py", "symbol": "find_pdflatex"}
   ]
   ```

   (match the exact entry shape already used by the other invariants).
8. `.slopledger.json` `latex-render-path.hand_check`: append
   "Cover letter is dual-engine since 2026-09-19 (cover_letter.typ)."

Run: `python3 scripts/check_system_md.py`
Expected: `OK — N/1000` with N ≤ 1000, no errors.

Commit:

```bash
git add SYSTEM.md .system_md_enforcement.json .slopledger.json
git commit -m "docs(system): inv-render-fallback-explained; engines probe; §11 item 7 shipped"
```

---

### Task 13: Full verification and gates G1–G3

**Step 1: G1**

```bash
cd backend && ruff check . && python3 -m pytest tests/ mcp_server/tests/ -q
```

Expected: `All checks passed!`; suite green (previous baseline 4280 passed,
2 skipped; expect ~+30). Then from the repo root:

```bash
python3 scripts/check_system_md.py && python3 scripts/check_mcpb_bundle.py
python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend
python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend
```

If `complexity_hotspots` rises from added tests, re-baseline with a reason in
the commit (SYSTEM.md §9 explains why the count is not decay).

**Step 2: G2 — a TeX-less host renders through Typst and says so**

From `backend/` in the worktree, with every data dir under the scratchpad
(`/private/tmp/claude-501/…/scratchpad/g2`), a fresh SQLite file, and TeX
"missing" via the override:

```bash
export G2=/private/tmp/claude-501/-Users-ajeyds-Projects-maestro-career-studio/416cdd99-680c-4a87-a79f-26e3c556805b/scratchpad/g2
mkdir -p $G2/data $G2/base_resumes $G2/applications $G2/settings $G2/logs $G2/exports $G2/kb_documents
MAESTRO_CS_PDFLATEX=/nonexistent DATA_DIR=$G2/data BASE_RESUMES_DIR=$G2/base_resumes APPLICATIONS_DIR=$G2/applications SETTINGS_DIR=$G2/settings LOGS_DIR=$G2/logs EXPORTS_DIR=$G2/exports KB_DOCUMENTS_DIR=$G2/kb_documents python3 -m uvicorn app.main:app --port 8765
```

Then:

```bash
curl -s localhost:8765/api/setup/status | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['engines'],d['template']['detail'])"
curl -s localhost:8765/api/templates | python3 -c "import json,sys;print([(t['id'],t['status'],t['engine_available'],t['last_error']) for t in json.load(sys.stdin)])"
curl -s -X POST localhost:8765/api/base-resumes/example/render | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['resolved_engine'],d['render_note'])"
```

Expected: `pdflatex.available False` with the override reason; every LaTeX
seed `draft` / `engine_available False` / `last_error "requires TeX…"`;
the render says `typst` + a note. (The seeded `example` base resume exists on
a fresh boot; if the slug differs, list `/api/base-resumes`.) For the cover
letter: create a job + application + a `cover_letter` QA entry through the
API (or insert a row via a short script against the G2 database while uvicorn
runs — SQLite WAL on a local disk is fine), `POST /api/qa/{id}/render`, and
confirm `render_note` and a real PDF. Record the outputs in the gate table.

**Step 3: G3 — the Docker image is unchanged in behaviour**

Build the backend image FROM THE WORKTREE and run it standalone (never the
main checkout's compose stack):

```bash
docker build -t maestro-cs-backend-g3 backend/
docker run --rm -d --name g3 -p 127.0.0.1:8766:8000 -v $G2/docker-data:/app/data maestro-cs-backend-g3
sleep 20; curl -s localhost:8766/api/setup/status | python3 -c "import json,sys;print(json.load(sys.stdin)['engines'])"
curl -s -X POST localhost:8766/api/base-resumes/example/render | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['resolved_engine'],d['render_note'])"
docker rm -f g3
```

Expected: both engines `available True`; `latex None`. Then the text-parity
check: extract the PDF's text (pdfplumber) from the G3 container render and
from a render on `main`'s image if one is handy; if not, record "parity by
test_cover_letter_parity + unchanged LaTeX templates" and mark G3 partial.
If Docker is unavailable in this session, record G3 as deferred to the owner's
rebuild.

**Step 4: Fill the tables below, commit them**

```bash
git add docs/plans/2026-09-19-desktop-step2-engines.md
git commit -m "docs(plans): engines branch — deviation log and gate results"
```

---

## Deviation log (append-only)

| # | Task | What the plan said | What was done instead | Why |
|---|---|---|---|---|
| 1 | 1 | `search = os.pathsep.join([os.environ.get("PATH", ""), *_candidate_dirs()])` | Empty joined components are dropped before the join; pinned by `test_no_path_at_all_does_not_search_the_working_directory` (`d7d5d306`) | CPython `shutil.which` treats an empty path component as the CURRENT DIRECTORY, so a PATH-less GUI process searched cwd ahead of `/Library/TeX/texbin` and returned a relative `pdflatex` that the render subprocess (cwd = staging dir) could not spawn. The eight specified tests pass unchanged under both versions. |
| 2 | 1 | Design §2.1 named the setting `settings.pdflatex_path (env MAESTRO_CS_PDFLATEX)` | Field is `maestro_cs_pdflatex` (as the task text and tests said); design doc corrected in the same commit as this row | `Settings` has no `env_prefix`, so only a `maestro_cs_*` field maps to `MAESTRO_CS_*`. |
| 3 | 1 | Row 1's filter dropped a wholly empty PATH | PATH is split into components first, then empties dropped (`bf27272a`); parametrized test over `":"`, `"/usr/bin:"`, `":/usr/bin"`, `"/a::/b"`, `""` | Quality review: an empty component INSIDE PATH (a trailing colon is common) still made `which` return a relative `pdflatex`. The probe's contract is an absolute path; cwd is never a candidate. |
| 4 | 1 | `_VERSION_CACHE: dict[str, tuple[version, reason]]` caching failures too | `dict[str, str]`, successes only; a failed `--version` is returned unstored | A probe landing mid-install would have marked TeX missing for the life of the process, contradicting "noticed on the next probe". Stale SUCCESS after a removal is the accepted asymmetry (heal upward). |
| 5 | 1 | `subprocess.run(..., text=True)` and `except (OSError, TimeoutExpired)` | `encoding="utf-8", errors="replace"`; `ValueError` added to the except tuple | `UnicodeDecodeError` is a `ValueError`; a wrapper script printing one bad byte would have made every render 500. |
| 6 | 1 | `importlib.metadata.version("typst")` unguarded | `PackageNotFoundError` → `version=None`, `available=True` | A frozen (PyInstaller) build imports typst without dist metadata; the import succeeding is what rendering needs. |
| 7 | 2 | Map `FileNotFoundError` → `RuntimeError` | `_run_pdflatex` catches `OSError` (`f176174b`) | A wrong `MAESTRO_CS_PDFLATEX` may name a directory: spawning one raises `PermissionError`/`IsADirectoryError`. `TimeoutExpired` is not an `OSError` and still propagates. |
| 8 | 2 | Files: `pdf_render.py` and `tests/test_render_fallback.py` | Six files: also `engines.py` (one docstring word, a Task 1 carry-forward), `tests/test_engines.py` (a `_candidate_dirs` smoke test, Task 1 carry-forward), `tests/test_pdf_render.py:45` (`argv[0] == "pdflatex"` → `.endswith`) and `tests/test_security_boundaries.py` (the hardened-env tripwire counted `>= 2` spawns; now `== 1` plus a check that both call sites route through `_run_pdflatex`) | The two carry-forwards were put in the brief by the controller. The single runner the task mandated changes the code shape both pinned tests relied on; the tripwire's intent (every spawn carries `env=`) is kept, and the spec reviewer confirmed by mutation that each regression it was built for still fails it. |
| 9 | 3 | Task 3 touched only the resolver files | Also carried four Task 2 quality follow-ups (`0e1b2a71`): `_run_pdflatex` says "could not be started" when the probe found a binary but the spawn failed, decodes with `errors="replace"`, and no longer names `IsADirectoryError`; `compile_pdf` docstring reworded; `engines.find_pdflatex` wraps the override check in `except OSError`; the tripwire's docstring corrected and its routing token tightened to `= _run_pdflatex(` | Task 2's quality reviewer approved with "fold into Task 3, which reopens the file"; one commit instead of a standalone round-trip. |
| 10 | 3 | `test_a_ready_typst_default_wins_over_typst_classic` requested `xcharter_serif` as-seeded | The test marks `xcharter_serif` ready first and asserts the exact note | As written it passed trivially: under `validate=False` the seed is a draft, so `get_usable_template` already fell to the default before the TeX rule ran and `first_ready_typst` was never exercised. |
| 11 | 3 | Six resolver tests | Plus one direct test of `first_ready_typst`'s three tiers and the archived exclusion; test imports at file top (E402) | The tier order is the load-bearing determinism claim in the design; ruff's pinned rule set forbids mid-file imports. |
| 12 | 7 (planned) | Task 7 touches `template_registry`, `schemas/template`, `routers/templates` | Task 7 will ALSO make `template_validation.compile_against_sample` return "requires TeX (pdflatex not found)" for a LaTeX source when the probe says unavailable, and make `resume_lint.structure_gates` resolve through `resolve_render_template` (falling back to `get_usable_template` if it raises) | Task 3's quality review: the health check derives its structure gates from the template `get_usable_template` returns, so on a TeX-less host it would try to validate the LaTeX default (a traceback per health run, S1/S2/S4 `not_assessed` forever) while the PDF the user gets came from Typst. Design §2.2 already says validation "reports requires TeX cleanly"; nothing implemented that yet. |
| 13 | 4 | Test named `test_render_note_is_null_when_nothing_was_substituted` | `…_is_null_on_the_wire_when_nothing_was_substituted` (`1fe3aa57`) | The plan reused the name of Task 3's service-level test in the same file. |
| 14 | 4 | Comment: `template_fallback` is "resolved id ≠ requested id for ANY reason" | Corrected: it fires only when an EXPLICIT `?template_id=` was passed and differs; a substitution of the PERSISTED choice never sets it, `render_note` is the only signal there; pinned by an assertion | The controller's brief was wrong; the expression is `template_id is not None and resolved != template_id` over the query parameter. Task 9's docstring and any UI gating must follow the corrected semantic. |
| 15 | 4 | Files: the two POST `/render` endpoints | Also `PUT /api/base-resumes/{slug}` and `PATCH …/edits` return `render_note`; `render_base_resume` clears the transient at entry and sets it on success | The web UI never calls the base-resume POST `/render`; it re-renders through PUT/PATCH, so without this a web user on a TeX-less host got a silent substitution. Clearing at entry prevents a stale note surviving a failed re-render on the same identity object. |
| 16 | 10 (planned) | Task 10 shows `render_note` only in a badge tooltip | Task 10 will ALSO surface `render_note` on render success in the web UI (toast) and type `RenderResult`/`render_note` in `frontend/lib/types.ts` | Design principle: every fallback names itself in the response AND the UI; both frontend render call sites currently discard the response body. |

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| G1 suite / ruff / check_system_md / check_mcpb_bundle / slop (backend, frontend) | | |
| G2 TeX-less host: render + cover letter through Typst with `render_note`; setup status; gallery | | |
| G3 Docker image: both engines available, `render_note` null, LaTeX output text-identical | | |

## LLM-call audit

None. No task in this branch calls a model; G2 and G3 use the seeded example
resume and no API key.
