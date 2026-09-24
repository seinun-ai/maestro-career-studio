"""Error words: a failure says what failed and what to do, never raw text.

A toast or a load error goes through lib/error-text.ts (`couldnt`,
`errorDetail`), which shows a thrown message only when it is a plain sentence
for the user (docs/frontend-conventions.md, Microcopy rules, *Errors*).
lib/api.ts writes the network and rejected-form sentences and logs the
developer detail to the console. Node tests cover error-text.ts; they are not
in CI, so the branches that matter are pinned here.

The ratchet counts RAW sites: an error's own message (`err.message`,
`String(err)`, a stream's `event.detail`) put on screen by a toast
(`toast.error(…)`, `toast.warning(…)`), a load error's `detail={…}`, a JSX
child (`{query.error.message}`), or a helper that hands it on (`return
err.message`, `x = err instanceof Error ? err.message : …`). Files a wave-3 copy
task has not converted yet sit in that task's `_PENDING_T*` block with their
count, which may only go down (docs/plans/2026-09-23-ux-ia-copy.md, Tasks
17-21). `python tests/test_frontend_error_words.py` from backend/ prints the
counts as they are.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ROOTS = ("app", "components", "lib", "hooks")
# Route handlers answer the browser, not the user: their words reach the
# screen through lib/api.ts, which this file pins.
_SKIP_DIRS = ("app/api/",)

# An error object's own words: `err.message`, `(q.error as Error)?.message`,
# `String(err)`, a stream event's `event.detail`.
_ERR_OBJ = r"\(?[\w.]*[eE]rr\w*(?:\s+as\s+\w*Error(?:\s*\|\s*null)?)?\)?\??"
_RAW = re.compile(rf"{_ERR_OBJ}\.message\b(?!s)|String\(\s*\w+\s*\)|\bevent\.detail\b|firstMessage\(")
# Sinks whose whole argument is read: a toast and a load error's detail.
_SINK_OPENERS = re.compile(r"\btoast\.(?:error|warning)\(|\bdetail=\{")
# Sinks matched whole: a JSX child `{err.message}` and a helper handing it on.
_INLINE = re.compile(
    rf"(?<![=$\w])\{{\s*{_ERR_OBJ}\.message\s*\}}"
    rf"|(?<![=$\w])\{{\s*\w+ instanceof \w*Error \? {_ERR_OBJ}\.message\b"
    rf"|\breturn\s+{_ERR_OBJ}\.message\b"
    rf"|=\s*\w+ instanceof \w*Error\s*\?\s*{_ERR_OBJ}\.message\b"
)
_PAIRS = {"(": ")", "{": "}"}

# (file, sites): raw text that is deliberate. Each must still occur.
_ALLOWED: dict[str, int] = {
    # The error page shows the thrown message in development builds only.
    "app/error.tsx": 1,
    # The browser's own fetch error: networkErrorMessage turns a network
    # failure into words and hands any other one on unchanged.
    "lib/api.ts": 1,
    # The one reader of a thrown message, which shows it only when it is a
    # plain sentence (errorDetail).
    "lib/error-text.ts": 1,
}

# Raw-message sites a wave-3 copy task has not converted yet, one block per
# task, so two lanes never edit the same lines. A task lowers its counts as it
# goes and deletes its block when it lands. Tasks 22-23 have no block: the
# Companion panel and the server are not scanned here.
_PENDING_T17: dict[str, int] = {  # D §2 jobs and tracking
    "app/applications/[id]/page.tsx": 1,
    "app/applications/page.tsx": 5,
    "app/jobs/[id]/page.tsx": 4,
    "app/new/page.tsx": 1,
    "app/referrals/page.tsx": 4,
    "components/analytics/analytics-overview.tsx": 3,
    "components/analytics/autofill-coverage-card.tsx": 1,
    "components/analytics/base-summary-cards.tsx": 1,
    "components/analytics/gap-tiers-panel.tsx": 1,
    "components/application-panel.tsx": 3,
    "components/ats-compare-panel.tsx": 3,
    "components/ats-score-panel.tsx": 4,
    "components/charts/chart-kit.tsx": 1,
    "components/job-tracking-url-field.tsx": 1,
    "components/proposals/proposal-agent-panel.tsx": 1,
    "components/proposals/proposals-section.tsx": 1,
    "components/proposals/triage-actions.tsx": 3,
    "components/qa-tab.tsx": 7,
}
_PENDING_T18: dict[str, int] = {  # D §3 the gap page
    "app/jobs/[id]/tailor/[sessionId]/page.tsx": 6,
}
_PENDING_T19: dict[str, int] = {  # D §4 resumes, studios, health, templates
    "app/applications/[id]/resume/page.tsx": 1,
    "app/base-resumes/[slug]/page.tsx": 1,
    "app/base-resumes/page.tsx": 4,
    "app/templates/[id]/page.tsx": 5,
    "app/templates/page.tsx": 7,
    "components/base-resumes/new-base-resume-dialog.tsx": 2,
    "components/resume-editor/editable-title.tsx": 1,
    "components/resume-editor/editor-body.tsx": 2,
    "components/resume-editor/instruct-sheet.tsx": 2,
    "components/resume-editor/kb-import-drawer.tsx": 4,
    "components/resume-editor/project-port-dialog.tsx": 1,
    "components/resume-editor/tailored-resume-studio.tsx": 4,
    "components/resume-health/batch-ask-dialog.tsx": 1,
    "components/resume-health/finding-cards.tsx": 5,
    "components/resume-health/health-report-page.tsx": 3,
    "components/resume-health/report-errors.ts": 1,
    "components/resume-versions/version-history-sheet.tsx": 1,
    "components/role-category-picker.tsx": 1,
}
_PENDING_T20: dict[str, int] = {  # D §5 Career history
    "app/career/page.tsx": 2,
    "components/career/capture-box.tsx": 2,
    "components/career/documents-panel.tsx": 3,
    "components/career/entity-detail.tsx": 3,
    "components/career/exports-card.tsx": 2,
    "components/career/first-run-import-card.tsx": 1,
    "components/career/inbox-panel.tsx": 4,
    "components/career/merge-entity-dialog.tsx": 2,
    "components/career/new-entity-dialog.tsx": 1,
    "components/career/notes-editor.tsx": 1,
    "components/career/points-list.tsx": 2,
    "components/career/profile-panel.tsx": 2,
    "components/career/resume-import-dialog.tsx": 2,
    "components/career/send-to-resume-dialog.tsx": 4,
    "components/kb-sync-pill.tsx": 1,
}
_PENDING_T21: dict[str, int] = {  # D §6 Settings and Profile; D §7 Assistant, shell, errors, setup
    "app/profile/page.tsx": 1,
    "components/chat/change-card.tsx": 1,
    "components/chat/chat-page.tsx": 6,
    "components/chat/edit-proposal-card.tsx": 1,
    "components/chat/proposal-card.tsx": 1,
    "components/chat/scope-picker.tsx": 1,
    "components/settings/auto-apply-section.tsx": 1,
    "components/settings/autofill-section.tsx": 3,
    "components/settings/job-preferences-section.tsx": 1,
    "components/settings/mcp-workflow-section.tsx": 1,
    "components/settings/model-catalog-panel.tsx": 3,
    "components/settings/models-section.tsx": 2,
    "components/settings/persona-section.tsx": 2,
    "components/settings/prompts-section.tsx": 2,
    "components/settings/quick-tailor-section.tsx": 1,
    "components/settings/setting-card.tsx": 1,
    "components/setup/getting-started-card.tsx": 1,
    "components/setup/use-document-queue.ts": 1,
}
_BLOCKS = (_PENDING_T17, _PENDING_T18, _PENDING_T19, _PENDING_T20, _PENDING_T21)
_PENDING: dict[str, int] = {rel: n for block in _BLOCKS for rel, n in block.items()}


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _without_comments(src: str) -> str:
    """The code a reader of the screen could meet: comments dropped (a URL's `//` stays)."""
    return re.sub(r"(?<![:\"'])//[^\n]*", "", re.sub(r"/\*.*?\*/", "", src, flags=re.S))


def _balanced_end(src: str, open_at: int) -> int:
    """Index after the bracket that closes the one at open_at (strings are not special)."""
    want = [_PAIRS[src[open_at]]]
    for j in range(open_at + 1, len(src)):
        if src[j] in _PAIRS:
            want.append(_PAIRS[src[j]])
        elif src[j] == want[-1]:
            want.pop()
            if not want:
                return j + 1
    return len(src)


def raw_sites(src: str) -> list[int]:
    """Offsets of each raw-message site in one source file."""
    sites = []
    for opener in _SINK_OPENERS.finditer(src):
        arg = src[opener.end() : _balanced_end(src, opener.end() - 1)]
        if _RAW.search(arg):
            sites.append(opener.start())
    sites.extend(m.start() for m in _INLINE.finditer(src))
    return sorted(sites)


def _counts() -> Counter[str]:
    out: Counter[str] = Counter()
    for root in _ROOTS:
        for path in sorted((_FRONTEND / root).rglob("*.ts*")):
            rel = path.relative_to(_FRONTEND).as_posix()
            if ".test." not in path.name and not rel.startswith(_SKIP_DIRS):
                out[rel] += len(raw_sites(path.read_text(encoding="utf-8")))
    return +out


def test_no_raw_error_text_reaches_the_screen():
    now = _counts()
    bad = {rel: n for rel, n in now.items() if rel not in _PENDING and n > _ALLOWED.get(rel, 0)}
    assert not bad, f"use couldnt(what, err) or errorDetail(err) from lib/error-text.ts: {bad}"


def test_pending_error_sites_only_shrink():
    now = _counts()
    grew = {rel: f"{now[rel]} now, {cap} pending" for rel, cap in _PENDING.items() if now[rel] > cap}
    done = {rel: f"{now[rel]} now, {cap} pending" for rel, cap in _PENDING.items() if now[rel] < cap}
    assert not grew, f"new raw error text in a file not yet converted (never raise a count): {grew}"
    assert not done, f"lower these _PENDING counts (delete the row at 0): {done}"


def test_each_pending_file_has_one_owner_and_the_allowlist_is_current():
    owners = Counter(rel for block in _BLOCKS for rel in block)
    assert not [rel for rel, n in owners.items() if n > 1]
    now = _counts()
    assert {rel: now[rel] for rel in _ALLOWED} == _ALLOWED


@pytest.mark.parametrize(
    "src,sites",
    [
        ("onError: (err) => toast.error(err.message),", 1),
        ("toast.error(err instanceof ApiError ? err.message : String(err))", 1),
        ("toast.error(`Notes not saved: ${error.message}`)", 1),
        ("toast.warning(String(e))", 1),
        ("toast.error(event.detail);", 1),
        ("detail={(query.error as Error | null)?.message}", 1),
        ("detail={\n  (apps.error as Error)?.message ??\n  (saved.error as Error)?.message\n}", 1),
        ("detail={firstMessage(queries)}", 1),
        ("<p>{profile.error.message}</p>", 1),
        ("<p>{(kb.error as Error).message}</p>", 1),
        ('{loadError instanceof Error ? loadError.message : "The item may no longer exist."}', 1),
        ("if (error instanceof ApiError) return error.message;", 1),
        ("const reason = err instanceof Error ? err.message : String(err);", 1),
        # Words the app wrote, and what is not an error, never count.
        ('toast.error(couldnt("save the resume", err))', 0),
        ("detail={errorDetail(query.error)}", 0),
        ("<span>{c.message}</span>", 0),
        ("toast.success(variables.message)", 0),
        ('if (error.message === "No actionable resolutions to tailor") {}', 0),
        ("const n = detail.data?.messages.length;", 0),
    ],
)
def test_the_scanner_finds_raw_sites(src: str, sites: int):
    assert len(raw_sites(src)) == sites, raw_sites(src)


# (file, text that must be there, text that must not): lib/api.ts writes words
# for a desktop user and keeps the developer detail in the console.
_API_WORDS = (
    ('"Maestro CS isn\'t responding. Check that it\'s running, then try again."', "docker compose"),
    ('console.error("apiFetch: network error"', "curl "),
    ('"Some details weren\'t accepted. Check them and try again."', "FastAPI"),
    ('"Something went wrong. Try again."', "port 8001"),
    ('"This file is too large."', "Original error"),
    ('"The Assistant couldn\'t reply. Try again."', "JSON.stringify(detailRaw)"),
    ('console.error("apiFetch: request failed"', "Request failed: ${"),
    ("\"Couldn't upload the file.\"", "Upload failed ("),
)


@pytest.mark.parametrize("present,absent", _API_WORDS)
def test_the_server_unreachable_words_are_for_a_desktop_user(present: str, absent: str):
    api = _without_comments(_read("lib/api.ts"))
    assert present in api
    assert absent not in api
    assert "Chat request failed (" not in api


def test_the_proxy_says_the_same_words_when_the_server_is_down():
    route = _read("app/api/[...path]/route.ts")
    assert "{ detail: \"Maestro CS isn't responding. Check that it's running, then try again.\" }" in route
    assert 'console.error("api proxy: backend unreachable"' in route
    assert "Upstream fetch failed" not in route


def test_the_load_error_default_names_the_next_step():
    src = _read("components/load-error-state.tsx")
    assert '{shownDetail ?? "Check that Maestro CS is running, then try again."}' in src
    assert "backend restarting" not in src


def test_error_text_shows_only_plain_sentences():
    src = _read("lib/error-text.ts")
    assert "/^[A-Z][^{}[\\]<>_`|\\\\]*[.!?]$/.test(t)" in src
    assert "return `Couldn't ${what}. ${errorDetail(err) ?? \"Try again.\"}`;" in src
    assert "t.length <= 240" in src
    assert not re.search(r"^import (?!type )", src, re.M)


def test_optional_reads_optional_in_brackets():
    label = _read("components/ui/label.tsx")
    assert "· optional" not in label
    # One inline run of text, so a wrapped label keeps the marker beside its last word.
    assert re.search(
        r'<span>\s*\{children\}\{" "\}\s*<span className="text-muted-foreground font-normal">\(optional\)</span>\s*</span>',
        label,
    )


if __name__ == "__main__":  # prints the per-file counts for the tree as it is now
    for rel, n in sorted(_counts().items()):
        print(f'    "{rel}": {n},')
