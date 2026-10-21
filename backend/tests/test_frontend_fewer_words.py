"""Fewer words on the pages without a board (design refresh, Task 4.6).

Career history, Base resumes, Templates, Referrals and the Assistant had a copy pass, not a redesign: no
page subtitle (D1), no hint that restates its label, the rest of a section's explanation in a tooltip or a
fold, one line kept where a consequence must be seen before acting, and sentence summaries turned into
numbers or chips. The ratchet below counts the muted paragraphs those pages still show.

How a page is counted (`_page_files`, `muted_paragraphs`):
- **A page folder** is every `.tsx` under `frontend/app/<folder>/`, plus every component under
  `frontend/components/<folder>/` that those files import, directly or through each other. Shared
  components (`components/ui/`, `components/visual/`, a component another page owns) are not counted: the
  pass leaves them alone.
- **A muted paragraph** is a `<p` element whose opening tag holds `text-muted-foreground` and whose body
  has words of its own: JSX text outside `{…}`, or a quoted string of two or more words inside an
  expression. A line that only prints a value (`{detail}`, a size and a date, a bullet's text) is data,
  not words the page adds, and is not counted. The counter reads one file at a time, so a `{CONSTANT}`
  written elsewhere is not resolved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Page → its folder under app/ (and components/).
_PAGES = {
    "Career history": "career",
    "Base resumes": "base-resumes",
    "Templates": "templates",
    "Referrals": "referrals",
    "Assistant": "chat",
}

# Muted paragraphs before the pass (2026-10-21, at 81ad078), counted by `muted_paragraphs` below.
_BEFORE = {
    "career": 39,
    "base-resumes": 13,
    "templates": 4,
    "referrals": 0,
    "chat": 6,
}

_IMPORT = re.compile(r"""(?:import|export)\s[^;]*?from\s+["']@/(components/[^"']+)["']""", re.S)


def _resolve(spec: str) -> Path | None:
    for ext in (".tsx", ".ts", "/index.tsx", "/index.ts"):
        path = _FRONTEND / f"{spec}{ext}"
        if path.exists():
            return path
    return None


def _page_files(folder: str) -> list[Path]:
    """The page files, then the components of the page's own folder they reach by import."""
    seen: set[Path] = set()
    stack = sorted((_FRONTEND / "app" / folder).rglob("*.tsx"))
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for spec in _IMPORT.findall(path.read_text(encoding="utf-8")):
            if spec.startswith(f"components/{folder}/"):
                found = _resolve(spec)
                if found is not None and found not in seen:
                    stack.append(found)
    return sorted(seen)


def _split_body(body: str) -> tuple[str, list[str]]:
    """JSX text outside `{…}` (tags removed) and the string literals inside expressions that are not
    attribute values of a tag."""
    body = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", body, flags=re.S)
    body = re.sub(r"(?<=\s)//[^\n]*", "", body)
    outside: list[str] = []
    literals: list[str] = []
    depth = 0
    in_tag = False
    expr_in_tag = False
    i = 0
    while i < len(body):
        ch = body[i]
        if depth == 0:
            if in_tag:
                if ch in "\"'":
                    end = body.find(ch, i + 1)
                    i = end if end != -1 else len(body)
                elif ch == "{":
                    depth, expr_in_tag = 1, True
                elif ch == ">":
                    in_tag = False
            elif ch == "<":
                in_tag = True
            elif ch == "{":
                depth, expr_in_tag = 1, False
            else:
                outside.append(ch)
        else:
            if ch in "\"'`":
                end = i + 1
                while end < len(body) and body[end] != ch:
                    end += 2 if body[end] == "\\" else 1
                if not expr_in_tag:
                    literals.append(re.sub(r"\$\{[^}]*\}", " ", body[i + 1 : end]))
                i = end
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        i += 1
    return "".join(outside), literals


def _tag_end(src: str, i: int) -> int:
    """The index of the `>` that closes the opening tag whose name ends at `i`: the first one outside a
    quoted attribute value and outside every `{…}` expression."""
    depth, quote = 0, ""
    while i < len(src):
        ch = src[i]
        if quote:
            quote = "" if ch == quote else quote
        elif ch == '"' or (depth > 0 and ch in "'`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            return i
        i += 1
    return i


def muted_paragraphs(src: str) -> int:
    count = 0
    for match in re.finditer(r"<p(?=[\s>])", src):
        end_of_tag = _tag_end(src, match.end())
        tag = src[match.start() : end_of_tag + 1]
        if "text-muted-foreground" not in tag or tag.endswith("/>"):
            continue
        outside, literals = _split_body(src[end_of_tag + 1 : src.find("</p>", end_of_tag)])
        words = re.sub(r"&\w+;", "", outside)
        if re.search(r"[A-Za-z]", words) or any(len(re.findall(r"[A-Za-z]+", lit)) >= 2 for lit in literals):
            count += 1
    return count


def _count(folder: str) -> int:
    return sum(muted_paragraphs(path.read_text(encoding="utf-8")) for path in _page_files(folder))


def test_the_counter_counts_words_not_values():
    assert muted_paragraphs('<p className="text-muted-foreground">No summary added.</p>') == 1
    assert muted_paragraphs('<p className="text-muted-foreground text-body-small">{detail}</p>') == 0
    assert muted_paragraphs('<p className={cn("text-muted-foreground", x && "a b")}>{formatBytes(n)} · {d}</p>') == 0
    assert muted_paragraphs('<p className="text-muted-foreground">{ok ? "Nothing to combine." : "No match."}</p>') == 1
    assert muted_paragraphs('<p className="text-muted-foreground">{plural(n, "result", "results")}</p>') == 0
    assert muted_paragraphs('<p className="text-body-medium">Not muted.</p>') == 0
    assert muted_paragraphs('<pre className="text-muted-foreground">x y</pre>') == 0
    assert muted_paragraphs('<p\n  className="text-muted-foreground"\n  title={t}\n>\n  Updated {ago(t)}\n</p>') == 1


def test_the_page_folders_hold_their_own_components():
    career = {p.relative_to(_FRONTEND).as_posix() for p in _page_files("career")}
    assert "app/career/page.tsx" in career and "components/career/profile-panel.tsx" in career
    assert not any(p.startswith(("components/ui/", "components/visual/")) for p in career)
    assert "components/chat/chat-page.tsx" in {p.relative_to(_FRONTEND).as_posix() for p in _page_files("chat")}


@pytest.mark.parametrize("page", list(_PAGES))
def test_muted_paragraphs_fell_by_at_least_half(page: str):
    folder = _PAGES[page]
    before, now = _BEFORE[folder], _count(folder)
    assert now * 2 <= before, f"{page}: {now} muted paragraphs, the ratchet allows {before // 2} (was {before})"


@pytest.mark.parametrize("page", list(_PAGES))
def test_these_pages_have_no_subtitle(page: str):
    """D1: a page subtitle goes. PageHeader's subtitle slot is `subtitle`; none of these pages sets it."""
    for path in _page_files(_PAGES[page]):
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<PageHeader\b", src):
            header = src[match.start() : _tag_end(src, match.end()) + 1]
            assert "subtitle=" not in header, path.relative_to(_FRONTEND)


def test_a_hint_tip_is_a_named_button_whose_sentence_is_also_its_description():
    """Where the explanation went: an Info button beside the title or label. Its tooltip shows the sentence,
    and the same sentence is the button's description (and a field's, through `id`), so it is never only
    on hover."""
    src = (_FRONTEND / "components/hint-tip.tsx").read_text(encoding="utf-8")
    assert "aria-label={label}" in src and "aria-describedby={hintId}" in src
    assert "<span id={hintId} hidden>" in src and "<TooltipContent" in src
    assert 'type="button"' in src  # never submits the form it sits in
