"""Vocabulary ratchet: the words a user reads follow the glossary.

docs/frontend-conventions.md, Microcopy rules, "Canonical terms", is the
glossary. This test reads what reaches the screen and refuses the banned
variants. It reads:

- string literals ('…', "…") and the text chunks of template literals
  (outside `${…}`, whose expressions are scanned as code);
- JSX text (between a tag's `>` and the next `<` or `{`);
- text between tags in the Companion panel's HTML.

It skips comments, `import`/`export … from` specifiers, `"use client"`,
TypeScript type aliases (`type X = "a" | "b"`), `className=` values, the
arguments of `cn(`, `clsx(`, `cva(` and `twMerge(`, and `console.*(` output.

Only PROSE is judged: JSX text, or a literal that holds a space between two
letters, or one capitalized word (`"Knobs"`). Keys, paths, query keys and enum
values (`"kb_inbox"`, `"/api/kb/entities"`, `"on_site"`) have neither, so a
code string never trips a word rule.

`_ALLOWED` lists the deliberate exceptions as (file, phrase). A phrase that no
longer matches anything fails `test_allowlist_is_current`, so the list only
shrinks. Every other file holds no banned word: the wave-3 copy tasks
(docs/plans/2026-09-23-ux-ia-copy.md, Tasks 17-22) swept them all and the
pending blocks went with the last merge. `python
tests/test_frontend_vocabulary.py` from backend/ prints the counts as they are.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_ROOTS = (
    ("frontend/app", (".ts", ".tsx")),
    ("frontend/components", (".ts", ".tsx")),
    ("frontend/lib", (".ts", ".tsx")),
    ("extension/panel", (".js", ".html")),
)
_CLASS_CALLS = frozenset({"cn", "clsx", "cva", "twMerge"})
# Developer output: never on screen.
_SILENT_CALLS = frozenset({"console.log", "console.info", "console.warn", "console.error", "console.debug"})
_CLASS_ATTRS = frozenset({"className", "class", "classNames"})
_KEYWORDS_BEFORE_EXPR = frozenset(
    {"return", "typeof", "case", "in", "of", "delete", "void", "throw", "new", "else", "yield", "await", "do"}
)
_BEFORE_JSX = frozenset("(,=?:{[&|}>;")
_BEFORE_REGEX = frozenset({"(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";", "", "return"})
# A newline or tab escape inside a literal reads as a space on screen.
_ESCAPES = {"n": " ", "t": " ", "r": " "}

# (rule name, pattern, why). Patterns run on prose only.
_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("JD", re.compile(r"\bJDs?\b"), "job description (or job), never JD"),
    ("KB", re.compile(r"\bKB\b"), "career history, never KB"),
    ("knowledge base", re.compile(r"knowledge base", re.I), "career history"),
    ("entity", re.compile(r"\bentit(?:y|ies)\b", re.I), "item, never entity"),
    ("render", re.compile(r"\b(?:re-?)?render(?:s|ed|ing)?\b", re.I), "Create PDF or Update PDF, never render"),
    ("compile", re.compile(r"\b(?:re)?compil(?:e|es|ed|ing)\b", re.I), "update the preview, never compile"),
    ("re-score", re.compile(r"\bre-?scor(?:e|es|ed|ing)\b", re.I), "Update score, never re-score"),
    ("re-extract", re.compile(r"\bre-?extract", re.I), "Refresh details, never re-extract"),
    ("agent proposals", re.compile(r"\bagent proposals\b", re.I), "Agent inbox"),
    ("composite", re.compile(r"\bcomposite\b", re.I), "ATS score, never composite"),
    ("fit score", re.compile(r"\bfit score\b", re.I), "ATS score, never fit score"),
    ("in flight", re.compile(r"\bin flight\b", re.I), "Applying (inbox) or In progress (Analytics)"),
    ("triage", re.compile(r"\btriage\b", re.I), "To review"),
    ("tailoring session", re.compile(r"\btailoring session\b", re.I), "gap analysis, never session"),
    ("waive", re.compile(r"\b(?:un)?waiv(?:e|ed|es|er|ing)\b", re.I), "Mark as OK, then Undo"),
    ("gate", re.compile(r"\bgates?\b", re.I), "Must fix"),
    ("certify", re.compile(r"\bcertif(?:y|ied|ies|ying)\b", re.I), "check, never certify"),
    ("mint", re.compile(r"\b(?:re-?)?mint(?:s|ed|ing)?\b", re.I), "read or add, never mint"),
    ("slug", re.compile(r"\bslugs?\b", re.I), "a resume is named, never slugged"),
    ("knobs", re.compile(r"\bknobs?\b", re.I), "formatting options"),
    ("port", re.compile(r"\bport(?:s|ed|ing)?\b", re.I), "copy, never port"),
    ("résumé", re.compile(r"r(?:ésumé|ésume|esumé)", re.I), "resume, no accents"),
    ("British spelling", re.compile(r"\b(?:behaviour|colour|organisation|honours?)\b", re.I), "US English"),
    ("browser extension", re.compile(r"\b(?:browser )?extension\b", re.I), "Companion"),
    ("chat agent", re.compile(r"\bchat (?:agent|assistant)\b", re.I), "the Assistant"),
    ("fast tailor", re.compile(r"\bfast tailor\b", re.I), "Quick tailor"),
    ("new application", re.compile(r"\bnew application\b", re.I), "Add job"),
    ("extract job", re.compile(r"\bextract job\b", re.I), "Save job"),
    ("dot optional", re.compile(r"·\s*optional\b"), "(optional)"),
    ("e.g.", re.compile(r"\be\.g\.", re.I), "no examples in UI copy; say 'such as' in a hint"),
    ("three dots", re.compile(r"\w\.\.\.(?:\s|$)"), "the ellipsis character …"),
    ("em dash joiner", re.compile(r"[A-Za-z.,)'’] — (?!Maestro CS)[A-Za-z]"), "two sentences or a colon"),
    (
        "slash for or",
        re.compile(r"(?<![\w/.:#@-])(?!AI/ML\b|UI/UX\b)[A-Za-z]{2,}/[A-Za-z]{2,}(?![\w/])"),
        "pick one word",
    ),
    ("spaced slash", re.compile(r"[A-Za-z)] / [A-Za-z(]"), "pick one word"),
    ("abbreviation", re.compile(r"\b(?:yrs|pts|Avg|Min|Apps|vs\.?)(?=\W|$)"), "spell it out"),
    ("semicolon", re.compile(r"[a-z)]; [a-z]"), "two sentences"),
    ("chat model", re.compile(r"\bChat model\b"), "Assistant model"),
    ("retire", re.compile(r"\bretir(?:e|ed|es|ing)\b", re.I), "Not used"),
    ("title case", re.compile(r"\bBase Resumes\b"), "Base resumes"),
    ("career record", re.compile(r"\bcareer (?:record|facts|data)\b", re.I), "career history"),
    ("KB point", re.compile(r"\b(?:draft|approved|career|new|unapproved) points?\b|\bpoint\(s\)", re.I), "bullet"),
    ("entry", re.compile(r"\bentr(?:y|ies)\b", re.I), "item"),
    ("library", re.compile(r"\blibrary\b", re.I), "career history (the sidebar group is Career library)"),
    ("posting", re.compile(r"\bpostings?\b", re.I), "job or job post"),
    ("as-is", re.compile(r"\bas-is\b", re.I), "as is"),
    ("could not", re.compile(r"\b(?:Could not|Cannot)\b"), "Couldn't or Can't"),
    ("extract", re.compile(r"\bextract(?:s|ed|ion|ing)?\b", re.I), "save, read, or find"),
    ("evidence", re.compile(r"\bevidence\b", re.I), "say what shows it"),
    ("versioned", re.compile(r"\bversioned\b", re.I), "you can undo it"),
)

# (file, phrase): deliberate exceptions. Each must still occur, so the list shrinks.
_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        # The ONE sentence that says what the Companion is (appendix A8):
        # "Companion, the Maestro CS browser extension".
        ("frontend/components/settings/connected-agents-card.tsx", "browser extension"),
        # The sidebar group that holds Career history, Base resumes and Templates.
        ("frontend/components/app-sidebar.tsx", "library"),
        # A legal waiver box the Companion may tick (extension/shared/policy.js),
        # not the health check's "waive".
        ("frontend/components/settings/autofill-section.tsx", "waiver"),
        # Load-order errors for a developer; the panel never shows them.
        ("extension/panel/actions.js", "panel/actions"),
        ("extension/panel/stages.js", "panel/stages"),
    }
)

_GENERIC_ARROW = re.compile(r"<\s*[A-Z]\w*\s*(?:extends\b|,)")
_TYPE_ALIAS = re.compile(r"\btype\s+\w+(?:<[^=]*>)?\s*=")
_REEXPORT = re.compile(r"export \{[^}]*\} from")
_PROSE = re.compile(r"[A-Za-z]\s+[A-Za-z(]|^[A-Z][a-z]+$")


def _is_prose(text: str) -> bool:
    return bool(_PROSE.search(text.strip()))


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch in "_$"


def _silences(tag: str | None) -> bool:
    """A frame whose strings never reach the screen: a class list or a console call."""
    if tag is None:
        return False
    return tag in _CLASS_ATTRS or tag.rsplit(".", 1)[-1] in _CLASS_CALLS or tag in _SILENT_CALLS


class _Scanner:
    """A small hand tokenizer: enough of TS/TSX/JS to find what a user reads."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.found: list[tuple[int, str]] = []  # (offset, text)
        # Frames: (opener, callee or attribute) for ( [ { and JSX attributes.
        self.frames: list[tuple[str, str | None]] = []
        # Comment spans already passed, so a look-back can step over them.
        self.comments: list[tuple[int, int]] = []

    # -- helpers -----------------------------------------------------------
    def _after(self, needle: str, i: int) -> int:
        """Index after the next `needle` from i, or the end of the source."""
        at = self.src.find(needle, i)
        return len(self.src) if at < 0 else at + len(needle)

    def _comment_end(self, i: int) -> int | None:
        """Index after a comment starting at i (recorded), else None."""
        if self.src.startswith("//", i):
            newline = self.src.find("\n", i)
            end = len(self.src) if newline < 0 else newline
        elif self.src.startswith("/*", i):
            end = self._after("*/", i + 2)
        else:
            return None
        self.comments.append((i, end))
        return end

    def _last_significant(self, i: int) -> int:
        """Index of the last character before i that is neither space nor comment, or -1."""
        j = i - 1
        while j >= 0:
            if self.src[j].isspace():
                j -= 1
                continue
            span = next((a for a, b in reversed(self.comments) if a <= j < b), None)
            if span is None:
                return j
            j = span - 1
        return j

    def _prev_significant(self, i: int) -> str:
        """The token before i: a whole word, or one punctuation character."""
        j = self._last_significant(i)
        if j < 0:
            return ""
        if not _is_word(self.src[j]):
            return self.src[j]
        k = j
        while k >= 0 and _is_word(self.src[k]):
            k -= 1
        return self.src[k + 1 : j + 1]

    def _callee(self, i: int) -> str:
        """The dotted name before the `(` at i (`console.warn`, `cn`), or ""."""
        j = i - 1
        while j >= 0 and self.src[j].isspace():
            j -= 1
        k = j
        while k >= 0 and (_is_word(self.src[k]) or self.src[k] == "."):
            k -= 1
        return self.src[k + 1 : j + 1]

    def _name_end(self, j: int, extra: str) -> int:
        while j < len(self.src) and (self.src[j].isalnum() or self.src[j] in extra):
            j += 1
        return j

    def _add(self, at: int, text: str) -> None:
        if not any(_silences(tag) for _o, tag in self.frames):
            self.found.append((at, text))

    # -- literals ------------------------------------------------------------
    def _quoted(self, i: int) -> int:
        quote = self.src[i]
        j = i + 1
        buf: list[str] = []
        while j < len(self.src) and self.src[j] != quote:
            if self.src[j] == "\\":
                nxt = self.src[j + 1 : j + 2]
                buf.append(_ESCAPES.get(nxt, nxt))
                j += 2
                continue
            if self.src[j] == "\n":  # unterminated: not a string (an apostrophe in text)
                return i + 1
            buf.append(self.src[j])
            j += 1
        self._add(i, "".join(buf))
        return j + 1

    def _template(self, i: int) -> int:
        j = i + 1
        buf: list[str] = []
        while j < len(self.src) and self.src[j] != "`":
            if self.src[j] == "\\":
                nxt = self.src[j + 1 : j + 2]
                buf.append(_ESCAPES.get(nxt, nxt))
                j += 2
            elif self.src.startswith("${", j):
                self._add(i, "".join(buf))
                buf = []
                j = self._code(j + 2, stop="}")
            else:
                buf.append(self.src[j])
                j += 1
        self._add(i, "".join(buf))
        return j + 1

    def _regex(self, i: int) -> int:
        j, in_class = i + 1, False
        while j < len(self.src) and self.src[j] != "\n":
            ch = self.src[j]
            if ch == "\\":
                j += 2
                continue
            if ch in "[]":
                in_class = ch == "["
            elif ch == "/" and not in_class:
                return j + 1
            j += 1
        return i + 1

    # -- JSX -------------------------------------------------------------------
    def _jsx_can_start(self, i: int) -> bool:
        nxt = self.src[i + 1 : i + 2]
        if not (nxt.isalpha() or nxt in (">", "/")):
            return False
        if _GENERIC_ARROW.match(self.src, i):  # `= <T extends string>(` or `<T,>(`
            return False
        prev = self._prev_significant(i)
        return prev == "" or prev in _KEYWORDS_BEFORE_EXPR or prev in _BEFORE_JSX

    def _jsx(self, i: int) -> int:
        """From `<` of an element; returns the index after the matching close."""
        depth = 0
        j = i
        while j < len(self.src):
            if self.src.startswith("</", j):  # closing tag
                j = self._after(">", j)
                depth -= 1
                if depth <= 0:
                    return j
                j = self._jsx_text(j)
                continue
            if self.src[j] == "<":
                j, self_closing = self._jsx_tag(j)
                if self_closing and depth == 0:
                    return j
                depth += 0 if self_closing else 1
                j = self._jsx_text(j)
                continue
            j += 1
        return j

    def _skip_type_args(self, j: int) -> int:
        """<Combobox.Root<Item, true> …>: step over the type argument."""
        if self.src[j : j + 1] != "<":
            return j
        level = 0
        while j < len(self.src):
            level += (self.src[j] == "<") - (self.src[j] == ">")
            j += 1
            if level == 0:
                break
        return j

    def _jsx_tag(self, i: int) -> tuple[int, bool]:
        """Parse `<Name attr=… >`; returns (index after `>`, self-closing)."""
        j = self._skip_type_args(self._name_end(i + 1, "._-$:"))
        attr: str | None = None
        while j < len(self.src):
            j, attr, closed = self._tag_step(j, attr)
            if closed is not None:
                return j, closed
        return j, True

    def _tag_step(self, j: int, attr: str | None) -> tuple[int, str | None, bool | None]:
        """One step inside a tag: (next index, current attribute, closed-how or None)."""
        ch = self.src[j]
        end = self._comment_end(j)
        if end is not None:
            return end, attr, None
        if self.src.startswith("/>", j):
            return j + 2, attr, True
        if ch == ">":
            return j + 1, attr, False
        if ch.isalpha() or ch == "_":
            k = self._name_end(j, "_-:")
            return k, self.src[j:k], None
        if ch in "\"'{":
            return self._attr_value(j, attr), attr, None
        return j + 1, attr, None

    def _attr_value(self, j: int, attr: str | None) -> int:
        self.frames.append(("attr", attr))
        j = self._quoted(j) if self.src[j] != "{" else self._code(j + 1, stop="}")
        self.frames.pop()
        return j

    def _jsx_text(self, i: int) -> int:
        j = i
        start = i
        while j < len(self.src) and self.src[j] != "<":
            if self.src[j] == "{":
                self._add(start, self.src[start:j])
                j = self._code(j + 1, stop="}")
                start = j
                continue
            j += 1
        self._add(start, self.src[start:j])
        return j

    # -- code ------------------------------------------------------------------
    def _token(self, j: int) -> int | None:
        """Consume a comment, literal, regex or JSX element at j; None if j is plain code."""
        end = self._comment_end(j)
        if end is not None:
            return end
        ch = self.src[j]
        if ch in "\"'":
            return self._quoted(j)
        if ch == "`":
            return self._template(j)
        if ch == "/" and self._prev_significant(j) in _BEFORE_REGEX:
            return self._regex(j)
        if ch == "<" and self._jsx_can_start(j):
            return self._jsx(j)
        return None

    def _closes(self, ch: str, stop: str | None, depth: int) -> bool:
        """True when `ch` ends the `${…}` or `{…}` being scanned; else pops its frame."""
        if ch == stop and depth == 0:
            return True
        if self.frames:
            self.frames.pop()
        return False

    def _code(self, i: int, stop: str | None = None) -> int:
        j = i
        depth = 0
        while j < len(self.src):
            nxt = self._token(j)
            if nxt is not None:
                j = nxt
                continue
            ch = self.src[j]
            if ch in "([{":
                self.frames.append((ch, self._callee(j) if ch == "(" else None))
                depth += 1
            elif ch in ")]}":
                if self._closes(ch, stop, depth):
                    return j + 1
                depth -= 1
            j += 1
        return j

    def run(self) -> list[tuple[int, str]]:
        self._code(0)
        return self.found


def _non_ui_line(line: str) -> bool:
    s = line.lstrip()
    return (
        s.startswith(("import ", "export * from", '"use client"', "'use client'"))
        or bool(_REEXPORT.match(s))
        or bool(_TYPE_ALIAS.match(s.removeprefix("export ")))
    )


def _strip_non_ui(src: str) -> str:
    """Blank out lines whose strings are never shown: imports, re-exports,
    directives and type aliases. Offsets and line numbers stay put."""
    return "".join(
        re.sub(r"[^\n]", " ", line) if _non_ui_line(line) else line for line in src.splitlines(keepends=True)
    )


def _files() -> Iterator[Path]:
    for root, suffixes in _ROOTS:
        for path in sorted((_REPO / root).rglob("*")):
            if path.suffix in suffixes and ".test." not in path.name and "node_modules" not in path.parts:
                yield path


def _html_text(src: str) -> list[tuple[int, str]]:
    return [(m.start(1), m.group(1)) for m in re.finditer(r">([^<>]+)<", src)]


def _read_prose(src: str) -> list[str]:
    """Prose a snippet puts on screen, whitespace collapsed (for the scanner's own cases)."""
    texts = (" ".join(t.split()) for _a, t in _Scanner(_strip_non_ui(src)).run())
    return [t for t in texts if _is_prose(t)]


def ui_strings() -> Iterator[tuple[str, int, str]]:
    """(repo-relative file, line, text) for every prose string a user can read."""
    for path in _files():
        rel = path.relative_to(_REPO).as_posix()
        src = path.read_text(encoding="utf-8")
        found = _html_text(src) if path.suffix == ".html" else _Scanner(_strip_non_ui(src)).run()
        for at, text in found:
            text = " ".join(text.split())
            if text and _is_prose(text):
                yield rel, src.count("\n", 0, at) + 1, text


def _matches(text: str) -> Iterator[tuple[str, str, str]]:
    """(rule name, phrase, why) for each banned word in one string."""
    for name, pattern, why in _RULES:
        for match in pattern.finditer(text):
            yield name, match.group(0).strip(), why


def violations() -> list[tuple[str, int, str, str, str]]:
    return [
        (rel, line, name, text, why)
        for rel, line, text in ui_strings()
        for name, phrase, why in _matches(text)
        if (rel, phrase) not in _ALLOWED
    ]


def _counts() -> Counter[str]:
    return Counter(rel for rel, *_rest in violations())


def test_ui_words_follow_the_glossary():
    bad = violations()
    assert not bad, "banned UI words (docs/frontend-conventions.md, Canonical terms):\n" + "\n".join(
        f"{rel}:{line}: [{name}] {text!r} -> {why}" for rel, line, name, text, why in bad
    )


def test_allowlist_is_current():
    live = {(rel, phrase) for rel, _l, text in ui_strings() for _n, phrase, _w in _matches(text)}
    stale = sorted(f"{rel} :: {phrase}" for rel, phrase in _ALLOWED - live)
    assert not stale, stale


@pytest.mark.parametrize(
    "src,seen,unseen",
    [
        ('toast.success("Synced to KB")', ["Synced to KB"], []),
        ("<p>Open your Career KB</p>", ["Open your Career KB"], []),
        ('<p className="text-muted-foreground render">Hi there</p>', ["Hi there"], ["text-muted-foreground render"]),
        ('cn("flex gap-2", ok && "re-render x")', [], ["re-render x"]),
        ('// the KB cache\nconst k = ["kb", id];', [], ["the KB cache", "kb"]),
        ("const m = new Map<string, number>(); // KB stuff\nconst s = `Sync ${n} to KB`;", ["Sync", "to KB"], ["KB stuff"]),
        ("x = a.replace(/\"/g, \"'\"); y = \"Two words\"", ["Two words"], []),
        ('{open ? <span>Hide it</span> : "Show it"}', ["Hide it", "Show it"], []),
        ('if (a < b && c > d) { t = "Plain text" }', ["Plain text"], []),
        (
            'return (\n  // a note about the KB\n  <span className="group/title flex">Rename it</span>\n);',
            ["Rename it"],
            ["group/title flex", "a note about the KB"],
        ),
        (
            "<Combobox.Root<Item, true>\n  multiple\n  // compares by id, not the KB row\n  value={v}\n>\n"
            "  <b>Pick one</b>\n</Combobox.Root>",
            ["Pick one"],
            ["compares by id, not the KB row"],
        ),
        (
            "const row = <T extends string>(k: T) => {\n  // the KB order\n  return <p>Row text</p>;\n};",
            ["Row text"],
            ["the KB order"],
        ),
        (
            '<div\n  /* the shell\'s one id: the KB note */\n  id="main"\n>Skip here</div>',
            ["Skip here"],
            ["the shell's one id: the KB note"],
        ),
        (
            'console.warn("Failed to close the tailoring session", e); toast("Saved it")',
            ["Saved it"],
            ["Failed to close the tailoring session"],
        ),
        # Found at Task 16: an escaped newline is a space on screen, never the letter n.
        ('const t = "The last try failed.\\n\\nOpen the report."', ["The last try failed. Open the report."], []),
        # Found at Task 16: a type alias's string union is never shown.
        ('export type Tone = "Plain words" | "Other words";\nconst a = "Shown words";', ["Shown words"], ["Plain words"]),
        # Found at Task 16: an unterminated comment or tag must end the scan, not loop.
        ('const a = "Shown words"; /* open comment', ["Shown words"], []),
    ],
)
def test_the_scanner_reads_ui_text_and_skips_code(src: str, seen: list[str], unseen: list[str]):
    texts = [t.strip() for t in _read_prose(src)]
    for want in seen:
        assert want.strip() in texts, (want, texts)
    for not_want in unseen:
        assert not_want not in texts, (not_want, texts)


def test_a_rule_names_what_to_say_instead():
    hits = {name for name, _p, _w in _matches("Sync to KB, then re-render the JD · optional")}
    assert {"KB", "render", "JD", "dot optional"} <= hits


if __name__ == "__main__":  # prints the per-file counts for the tree as it is now
    for rel, n in sorted(_counts().items()):
        print(f'    "{rel}": {n},')
