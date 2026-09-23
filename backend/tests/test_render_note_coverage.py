"""Design 2026-09-19 §2.2: every base-resume re-render explains itself.

`render_base_resume` sets a transient `render_note` on the row whenever a
LaTeX template was rendered through a Typst one (a TeX-less host). A caller
that drops it substitutes an engine silently — which is exactly what Tasks
10b, 10c and 10d each found again, one call site at a time, after the note
itself had shipped.

So this is an ENUMERATION gate, not a behaviour test: it lists every call to
`render_base_resume` under `app/routers` and `app/services` and fails on any
call site the list does not know, naming for each what carries the note. A new
re-rendering route fails here until someone writes its line — that is the
whole point. Whether a listed site ACTUALLY carries its note is pinned by
tests/test_render_fallback.py, per route.

Style: tests/test_db_portability.py (source scan against a reviewed list).
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCANNED = ("app/routers", "app/services")
RENDER_CALL = "render_base_resume"

# file:function -> what carries the note on that path. Adding an entry is a
# review decision; "needs none" has to say why.
ALLOWED: dict[str, str] = {
    "app/routers/base_resumes.py:create_base_resume": (
        "BaseResumeDetail.render_note (POST /base-resumes, and /import + /from-kb, "
        "which answer through this handler); a failed render answers with "
        "render_error instead"
    ),
    "app/routers/base_resumes.py:update_base_resume": (
        "BaseResumeDetail.render_note (PUT /base-resumes/{slug})"
    ),
    "app/routers/base_resumes.py:duplicate_base_resume": (
        "BaseResumeDetail.render_note (POST /{slug}/duplicate); a failed render "
        "answers with render_error instead"
    ),
    "app/routers/base_resumes.py:port_project_to_base_resume": (
        "BaseResumePortProjectResult.render_note; a failed render answers with "
        "render_error instead (POST /{slug}/port-project)"
    ),
    "app/routers/base_resumes.py:render_base_resume_endpoint": (
        "BaseResumeDetail.render_note (POST /{slug}/render, MCP render_pdf)"
    ),
    "app/routers/resume_versions.py:restore_version": (
        "ResumeVersionRestoreResult.render_note; a failed render answers with "
        "render_error instead (POST /resume-versions/base/{key}/{n}/restore, "
        "MCP restore_resume_version)"
    ),
    "app/services/career_kb.py:_persist_port": (
        "the returned row's transient note -> KBPortResponse.resume.render_note, "
        "for both POST /kb/port and POST /kb/port/adapt/apply"
    ),
    "app/services/kb_import.py:_mint_base": (
        "ImportedBase.render_note on POST /kb/import (onboarding)"
    ),
    "app/services/resume_ops.py:edit_base": (
        "BaseResumeDetail.render_note on PATCH /base-resumes/{slug}/edits, and "
        "ChatChangeCard.render_note on the chat edit_resume tool"
    ),
    "app/services/seeding.py:seed_base_resumes": (
        "needs none: boot-time seeding has no HTTP response and no user waiting "
        "on it; the engines block in GET /setup/status is what reports the host"
    ),
}


def _call_sites() -> dict[str, int]:
    """Every `render_base_resume(...)` call under the scanned trees, as
    file:function -> line (the definition itself is not a call, so
    services/base_resume_render.py contributes only if it calls itself)."""
    found: dict[str, int] = {}
    for tree_name in SCANNED:
        for path in sorted((BACKEND / tree_name).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if f"{RENDER_CALL}(" not in source:
                continue
            rel = str(path.relative_to(BACKEND))
            stack: list[str] = []

            class Visitor(ast.NodeVisitor):
                def visit_FunctionDef(self, node):  # noqa: N802 — ast API
                    stack.append(node.name)
                    self.generic_visit(node)
                    stack.pop()

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_Call(self, node):  # noqa: N802 — ast API
                    func = node.func
                    name = getattr(func, "attr", None) or getattr(func, "id", None)
                    if name == RENDER_CALL:
                        where = stack[-1] if stack else "<module>"
                        found.setdefault(f"{rel}:{where}", node.lineno)
                    self.generic_visit(node)

            Visitor().visit(ast.parse(source))
    return found


def test_every_base_resume_render_call_site_is_a_reviewed_one():
    found = _call_sites()
    unlisted = sorted(f"{site} (line {found[site]})" for site in found if site not in ALLOWED)
    assert not unlisted, (
        "new render_base_resume call site(s): "
        + ", ".join(unlisted)
        + ". Carry the row's transient render_note onto this path's response "
        "(see tests/test_render_fallback.py for the per-route pins), then add "
        "the site to ALLOWED in this file saying which schema carries it."
    )
    stale = sorted(site for site in ALLOWED if site not in found)
    assert not stale, (
        "ALLOWED lists call site(s) that no longer exist: "
        + ", ".join(stale)
        + ". Delete the entries — a list nobody prunes stops meaning anything."
    )


def test_the_list_says_what_carries_the_note_everywhere():
    """The note beside each entry is the reviewed part; an empty one would
    turn the gate into a rubber stamp."""
    assert [site for site, why in ALLOWED.items() if len(why.strip()) < 20] == []
