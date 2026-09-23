"""The app speaks the user's words: edits are described, never printed as ops;
resumes are named, never slugged. Node tests are not in CI, so the behaviour of
lib/describe-edit.ts is pinned here: every op kind the backend accepts has a
case, and both surfaces render through it."""

import re
from pathlib import Path

from app.schemas.resume_edit import op_kinds

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_DESCRIBER = _read("lib/describe-edit.ts")


def test_every_op_kind_the_backend_accepts_has_words():
    body = _DESCRIBER[
        _DESCRIBER.index("function describeOne(") : _DESCRIBER.index("\nfunction advance(")
    ]
    cased = set(re.findall(r'case "([a-z_]+)":', body))
    assert cased == op_kinds(), {"missing": op_kinds() - cased, "unknown": cased - op_kinds()}


def test_the_fallback_never_prints_the_kind():
    assert "op.kind}" not in _DESCRIBER  # no template interpolating the key
    assert "// A kind this file does not know yet: plain words, never the key." in _DESCRIBER


def test_the_describer_takes_no_value_imports():
    # node --test loads it; `@/` and extensionless specifiers do not resolve there.
    assert not re.search(r"^import (?!type )", _DESCRIBER, re.M)


def test_both_surfaces_render_words():
    card = _read("components/chat/edit-proposal-card.tsx")
    sheet = _read("components/resume-editor/instruct-sheet.tsx")
    assert "describeEdits(proposal.ops, pending ? doc : null)" in card
    assert "onMutate: () => setFrozen(describeEdits(proposal.ops, doc))" in card
    assert "describeEdits(proposal.ops, resume)" in sheet
    for rel, src in (("card", card), ("sheet", sheet)):
        assert "<EditWordsList edits=" in src, rel
        assert "font-mono" not in src, rel
        assert "describeOp" not in src, rel
    assert "resume={live?.data}" in _read("components/resume-editor/editor-body.tsx")


# A bare baseResumeLabel(x) is a slug dressed as a name. Allowed only as the
# fallback half of `display_name ?? baseResumeLabel(x)` / `|| ...`, or with a list.
_BARE = re.compile(r"(?<!\?\? )(?<!\|\| )baseResumeLabel\([^,()]*\)")


def test_no_resume_is_named_by_its_slug():
    offenders = [
        f"{p.relative_to(_FRONTEND)}:{n}"
        for root in ("app", "components")
        for p in sorted((_FRONTEND / root).rglob("*.tsx"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _BARE.search(line)
    ]
    assert offenders == [], offenders


def test_the_name_hook_reads_the_list_with_archived_rows():
    hook = _read("hooks/use-base-resume-label.ts")
    assert '"/api/base-resumes?include_archived=true"' in hook
    assert "baseResumeLabel(slug, data)" in hook
    assert 'return ["base-resumes", { includeArchived }] as const;' in hook


def test_one_selectable_list_query():
    """The selectable-list fetch lives in one hook. Prefix invalidation of
    ["base-resumes"] stays at the call sites; that is not a second fetch."""
    hook = _read("hooks/use-base-resume-label.ts")
    assert "export function useBaseResumes(" in hook
    assert "apiFetch<BaseResumeSummary[]>" in hook
    callers = (
        "components/ats-score-panel.tsx",
        "components/chat/chat-page.tsx",
        "components/career/send-to-resume-dialog.tsx",
        "components/resume-editor/project-port-dialog.tsx",
        "app/base-resumes/page.tsx",
    )
    missing = [rel for rel in callers if "useBaseResumes(" not in _read(rel)]
    copies = [
        f"{p.relative_to(_FRONTEND)}"
        for root, pattern in (("app", "*.tsx"), ("components", "*.tsx"), ("hooks", "*.ts"))
        for p in sorted((_FRONTEND / root).rglob(pattern))
        if p.name != "use-base-resume-label.ts"
        and "apiFetch<BaseResumeSummary[]>" in p.read_text(encoding="utf-8")
    ]
    assert missing == [], missing
    assert copies == [], copies
