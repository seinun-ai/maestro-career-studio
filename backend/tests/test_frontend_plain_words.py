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


_CARD = _read("components/chat/edit-proposal-card.tsx")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i)]


def test_resolved_words_freeze_and_a_failed_apply_thaws_them():
    # Discard freezes the words it showed: the card stops fetching the document.
    discard = _block(_CARD, "onClick={() => {", "Discard")
    assert 'setResolution("discarded")' in discard
    assert "setFrozen(edits);" in discard
    # A failed Apply unfreezes: the card is live again and must track the document.
    assert "setFrozen(null);" in _block(_CARD, "onError:", "},")


def test_the_words_list_is_prose_not_code():
    words = _read("components/edit-words-list.tsx")
    assert "<ul" in words
    assert not re.search(r"font-mono|<code|<pre", words)


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


_HOOK = _read("hooks/use-base-resume-label.ts")


def test_the_name_hook_reads_the_list_with_archived_rows():
    assert '"/api/base-resumes?include_archived=true"' in _HOOK
    assert "baseResumeLabel(slug, data)" in _HOOK
    assert 'return ["base-resumes", { includeArchived }] as const;' in _HOOK
    for hook in ("useBaseResumeLabel", "useBaseResumeName"):
        body = _block(_HOOK, f"export function {hook}(", "\n}")
        assert "useBaseResumes(true)" in body, hook


def test_a_soft_deleted_resume_is_named_from_its_own_row():
    body = _block(_HOOK, "export function useBaseResumeName(", "\n}")
    # Same key as the studios' and the edit card's detail query.
    assert 'queryKey: ["base-resumes", slug]' in body
    # Only once the list has loaded WITHOUT the slug, and only when asked.
    assert "enabled: enabled && list.isSuccess && !listed," in body


# Every surface that names ONE résumé that may be soft-deleted goes through
# useBaseResumeName, so they all say the same thing.
_ONE_SLUG_SURFACES = {
    "components/chat/change-card.tsx": "useBaseResumeName(card.resume_key,",
    "components/chat/proposal-card.tsx": "useBaseResumeName(proposal.target_key,",
    "components/chat/edit-proposal-card.tsx": "useBaseResumeName(proposal.target_key,",
    "components/proposals/proposals-section.tsx": "useBaseResumeName(base ??",
    "components/application-panel.tsx": "useBaseResumeName(app.base_resume, open && !app.base_resume_name)",
}


def test_one_resume_surfaces_share_the_name_hook():
    missing = [rel for rel, call in _ONE_SLUG_SURFACES.items() if call not in _read(rel)]
    assert missing == [], missing
    assert "{baseName}" in _read("components/proposals/proposals-section.tsx")
    tracker = _read("app/applications/page.tsx")
    assert "r.app.base_resume_name || baseName(r.app.base_resume)" in tracker


def test_humanize_slug_names_no_resume():
    """The slug's words are a FALLBACK inside baseResumeLabel. The one other
    caller is the role picker's own fallback, for role keys."""
    callers = [
        f"{p.relative_to(_FRONTEND)}"
        for root in ("app", "components", "hooks")
        for p in sorted((_FRONTEND / root).rglob("*.ts*"))
        if "humanizeSlug(" in p.read_text(encoding="utf-8")
    ]
    assert callers == ["components/role-category-picker.tsx"], callers


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
