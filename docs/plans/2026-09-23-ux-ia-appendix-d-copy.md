> **Appendix D (copy) to the 2026-09-23 UX IA and copy plan.** This is a research brief. It was written
> read-only against `8cac7cf9` (branch `claude/ux-ia-copy-plan`, equal to local main). It consolidates the
> three copy audits in `docs/ux/copy-audit/` (local-only: part 1 jobs and tracking, part 2 resumes and career,
> part 3 settings, chat, shell and the Companion panel; about 1,060 findings) under the owner's binding
> decisions. Where an audit and an owner decision differ, the owner decision wins and this appendix says so.
> Line numbers are at `8cac7cf9`; re-locate each quote before you edit. Appendices A (Agent inbox), B (sticky
> lists and the cap notice) and C (Settings and Profile) run first; this appendix edits their words only
> where an owner decision requires it, and each such row says "after A", "after B" or "after C".

# Implementation brief: D0–D11, one plain vocabulary everywhere

No repo file was changed except this one. Paths are relative to `frontend/` unless they start with
`backend/`, `extension/`, `docs/` or `SYSTEM.md`.

**Goal (for this appendix).** A new job seeker reads every screen, toast, error and Companion note without
meeting an internal word, a raw key, an example in a blank field or a developer instruction. One word names
each thing, and the same word is used on every surface, including what the server writes. The principles:
- **The glossary is the contract** (D0). Two ratchets enforce it: a vocabulary scan of every string a user
  can read, and the placeholder scan flipped to "no text in a blank field".
- **Safety and consent wording keeps every promise.** Shorten it; never drop a clause. "Nothing is submitted
  without your yes", "never signs, never submits", "never fills passwords or ID numbers", "never uses AI for
  these", "You can't undo this" (only where it is true), and the honesty warnings stay.
- **Machine words stay machine words.** Stored values, API fields, MCP tool names, status keys and CSS class
  names never change. A string that code compares (one exists: the gap page matches the server's "No actionable
  resolutions to tailor", D3 and D9) changes on both sides or not at all. A backend message an MCP agent reads changes only when its
  meaning for the agent survives (D9).
- **Copy changes are copy changes.** A row that changes behaviour (a confirm, a retry, a disclosure, a date
  format, a merged option) is marked **[behaviour]**; the bug fixes among them are indexed in D10.

**How this was made.**
- The audit rows were re-read against the code at `8cac7cf9`; each owner decision was applied row by row.
- Every test pin was found by a script that grepped each audit row's current text across `backend/tests`,
  `backend/mcp_server/tests` and `frontend/**/*.test.ts`, then read by hand.
- The vocabulary ratchet (D0) was run against the tree: it reads 2,609 prose strings in 236 files and flags
  477 violations in 105 files, with no false positive left after the fixes described in its docstring. Its
  14 scanner cases pass. The flipped placeholder ratchet (D1.4) passes 28/28 at `8cac7cf9` with the pending
  sets below, and the error-words ratchet (D1.3) passes its two ratchet tests with its pending counts. The
  `lib/error-text.ts` node test passes 3/3.
- The Companion panel table (D8) and the backend inventory (D9) were verified string by string against the
  panel harness tests and the MCP server.
- No browser was driven for this brief. The browser checks are for the implementer.

---

## Suggested task split

Every lane runs **after** appendices A, B and C have landed (their wave-1 lanes touch many of the same
files; see *Files also touched by A–C*). L0 goes first; L1–L8 then run in parallel, because their files are
disjoint.

| Lane | Sections | Files (owner) | Size | Depends on |
|---|---|---|---|---|
| **L0 Foundation** | D0, D1 | `components/ui/label.tsx`, new `lib/error-text.ts` (+ test), `lib/api.ts` (messages only), `components/load-error-state.tsx`, `docs/frontend-conventions.md` (the D1 bullets), new `backend/tests/test_frontend_vocabulary.py`, `backend/tests/test_frontend_placeholders.py` (rule flip, pending sets, scanner tests), new `backend/tests/test_frontend_error_words.py` | M | A, B, C |
| **L1 Jobs and tracking** | D2 | tracker, job page, `/new`, Referrals, Analytics, job components, proposals words A leaves | L | L0 |
| **L2 Gap page** | D3 | `app/jobs/[id]/tailor/**`, `components/gap-analysis/**` | M | L0 |
| **L3 Resumes, studios, health, templates** | D4 | `app/base-resumes/**`, `app/templates/**`, `app/applications/[id]/resume/**`, `components/{base-resumes,resume-editor,resume-health,resume-versions,templates}/**`, the resume `lib/` files | L (split L3a studios and base resumes, L3b health, versions and templates) | L0 |
| **L4 Career history** | D5 | `app/career/**`, `components/career/**`, `components/kb-sync-pill.tsx` | M | L0 |
| **L5 Settings and Profile** | D6 | `components/settings/**`, `app/settings`, `app/profile` (strings only) | M | L0 |
| **L6 Assistant, shell, setup** | D7 | `components/chat/**`, `app/chat`, `app-sidebar.tsx`, `components/setup/**`, error pages, `version-banner.tsx`, `components/ui/**` defaults | M | L0 |
| **L7 Companion** | D8 | `extension/panel/**`, `extension/shared/guided-run.js`, the panel harness tests | M | L0 |
| **L8 Server words** | D9 | the backend services and routers listed in D9 | M | L0 (independent of L1–L7) |
| **L9 Docs** | D11 | README, GETTING_STARTED, SYSTEM.md sweep queue | S | L1–L8 |

Each lane deletes its own `_PENDING_Lx` block in `test_frontend_vocabulary.py` and its own
`_PENDING_EXAMPLES_Lx` set in `test_frontend_placeholders.py` when it lands. The blocks are separate so two
lanes never edit the same lines.

---

## Global constraints (every lane)

- **React Compiler lint runs at error level.** No `setState` in an effect or during render, no
  `ref.current` read during render. Copy changes rarely touch this; the new helpers are pure functions.
- **`lib/*.ts` imports only relative paths or bare packages, and only `import type` across lib files**
  (`node --test` strips types; `@/` does not resolve there). Node tests are not in CI, so every new `lib`
  behaviour also gets a pytest source pin.
- **Plurals.** A count and its noun agree: `${n} ${n === 1 ? "bullet" : "bullets"}`, as 57 sites already
  do. The five that do not are bugs (D10).
- **Contractions:** "Couldn't", "can't", "don't", "won't". A JSX text node writes the apostrophe as
  `&apos;` (the lint rule `react/no-unescaped-entities`); a string literal writes `'`.
- **Sentence case** for labels, buttons, headings and chips. Proper names keep their case: Maestro CS,
  Companion, Assistant, Quick tailor, Agent inbox, Career history (as the page name), LinkedIn, GitHub,
  OpenAI, Gemini, OPT, H-1B, WOTC.
- **No em dash as a clause joiner, no semicolon, no "/" for "or" or "and", no "e.g."** in UI text (the
  vocabulary ratchet enforces all four). The `—` character stays for an empty cell (`{value ?? "—"}`) and
  inside composed labels (`${company} — ${role}`, a page `<title>`).
- **Mutation-check every pin you add or change**: break the string it guards, watch exactly that pin fail,
  restore from a backup copy (never `git stash`).
- **SYSTEM.md is at its cap.** Queue SYSTEM.md edits for the docs sweep (D11). `docs/frontend-conventions.md`
  changes in the same commit as the code it describes.

---

## D0. Glossary and the vocabulary ratchet

### D0.1 The glossary (becomes the Microcopy rules bullet "Canonical terms", D1.1)

| Canonical term | Banned variants | Notes |
|---|---|---|
| **Career history** (page and sidebar item); "your career history" in prose | Career KB, KB, Career Knowledge Base, Knowledge Base, library, career record, career facts, career data, KB profile, evidence (as a noun for what is stored) | The sidebar group **Career library** stays; it holds Career history, Base resumes and Templates. The kilobytes unit "KB" on file sizes stays. |
| **item** (one record in career history: a role, project, school, certification or other section entry) | entity, entities, record, entry | "career item" only where nothing else names the context (a toast on another page). |
| **bullet** (one line inside an item or a resume entry) | point, career point, approved point, draft point, fact, phrasing | Bullet states: **Draft**, **Approved**, **Not used** (verbs: Approve, Stop using, Use again). "Bullet style" stays for the formatting glyph; its hint says "The symbol before each bullet." so the two never read alike. Score points stay "points" ("up to +4 points"). |
| **item** (one row inside a resume section) | entry | "Add item", "Item spacing", "Item added". |
| **Add to career history** (resume → career history), **Add from career history** (career history → resume), **Add to a resume** (an item → a resume), **Copy to another resume** (between resumes), **Import resumes** (files) | Sync to KB, Import from Career KB, Send to resume, Port, Ported | The studio pill reads "Add to career history (3)". |
| **ATS score**; spelled out once per surface where it first appears: "ATS score (how an applicant tracking system rates a resume for this job)" | composite, ATS composite, fit score, match score, ATS points, Fit | After the first mention on a surface, "ATS score" or "score". Lift is **Score gain**. The Companion ring reads "ATS score". |
| **job description** (the text); **job** (the thing you apply to); **job link** (its URL); **careers page** (a company's jobs page, Referrals) | JD, raw JD, posting, job posting, Source URL, Application URL, Careers URL | "job post" is allowed in a short label when "job description" does not fit. |
| **Add job** (the sidebar button, the tracker button, the `/new` title "Add a job"), **Save job** (the `/new` submit) | New application, Extract job, Extract | A job is not an application until you tailor or apply. |
| **Refresh details** | Re-extract, re-run JD extraction, re-extracted | Reads the job description again. |
| **gap analysis** | session, tailoring session, analysis (alone), resolution | Handling a gap: **answer** (you), **filled in** (automatic), **done** (counts). |
| **tailor**; **Quick tailor** (feature name, capital Q, always) | quick tailor, one-shot tailoring, Fast tailor, quick-tailor defaults, saved defaults | Its settings are **Quick tailor settings**. |
| **Create PDF**, **Update PDF**; "PDF" in prose; status "Updating PDF…" | Generate PDF, Regenerate PDF, Render PDF, render, rendered, re-render, Recompile, compile | The template editor's button is **Update preview**. |
| **Update score**; status "Updating score…" | Re-score, re-scored, Re-scoring | |
| **Hide**, **Show**, **Hidden** (an entry switched off on a resume) | Disable, Enable, Archived (for entries), unhide, (disabled) | |
| **Archive**, **Restore** (a base resume or template) | Unarchive | |
| **Other sections** | Extra sections, Custom sections, custom section, extra-section | |
| **Must fix**, **Mark as OK**, **Undo** (health gates and waivers) | gate, Gates, Structural gates, Blocker, Blocked, fatal, Waive, Unwaive, waiver, waived | The badge "Blocked" becomes "Must fix". |
| **Check health**, **Check again** | Analyze, Re-analyze, analysis (health) | Page: **Health report**. |
| **Check template** | Certify, certified, Re-validate, validation, Not validated | |
| **Version 12**, **Version history** | v12, History (menu item) | |
| **skill group**; field label **Group name** | Skills group, Category (for a skill group), Skill inventory | |
| **School** | Institution | |
| **Couldn't** + what + what to do next | Could not, Cannot, Failed to, failed, raw server text, JSON, schema paths, status codes | D1.3 helper. |
| **On-site** | Onsite, onsite | |
| **years, points, Average, Minimum, Applications** | yrs, pts, Avg, Min, Apps, vs, ≈ | |
| **Assistant** (the in-app chat feature and sidebar item); **chat** (one conversation: "New chat", "Chat history") | Chat (the sidebar item), Chat assistant, chat agent, the assistant (lower case) | |
| **connected agent(s)** (external MCP clients); **Connected agents** (Settings tab) | agent (bare), hunt swarm, lane, MCP (outside the Connected agents explainer) | "hunt" stays as the name of a connected agent's search run (appendix A5). |
| **Companion** (the Chrome extension; proper name, no article needed) | extension, browser extension, the companion, Maestro CS Companion (except once, in full) | The one sentence that says what it is ("Companion, the Maestro CS browser extension") lives on the Connected agents tab (appendix A8); the lane that writes it adds its `_ALLOWED` row. |
| **Suggested edit(s)**, **Suggested project** | Proposed project, Propose, proposal (for chat cards) | "Proposal" means only a job an agent filed. |
| **Agent inbox** (`/proposals`) | Agent Proposals, proposals page | |
| Inbox lanes **Needs you · To review · Queued · Applying · History**; chips **Proposed → Queued → Approved → Applied**, or **Skipped**; also **Needs you**, **Expired**, **Check if sent** | Triage, In flight, Submitted, Submission uncertain, Accepted (for the queued state), Captured | The funnel and Analytics use the same words; "Captured" becomes **Found**. |
| **In progress** (Analytics: applied, interviewing or offer) | In flight | |
| **Offer** | offered | |
| **Role** | Role family, Role category, track | |
| **Employment type** | Employment | |
| **Diversity questions (voluntary)** | EEO, voluntary disclosures, self-identification, EEO standing consent | Keep "voluntary". |
| **resume** (no accents); US English | résumé, behaviour, colour, organisation, honours | |
| **(optional)** on the label | "· optional", a hand-written span | GOV.UK style. |
| one word for "or" or "and" | "/" in prose or labels | Ratios read "3 of 5". "/ 100" beside a score and date formats like "06/2026" are fine. |
| **Persona** (kept) | | Its placeholder goes; its description gains one line saying what it is (D6). |
| **Fast model**, **Smart model**, **Assistant model** | Chat model | One-line hint each (D6). |
| **Settings › AI & models**, **Profile › Autofill** (a path in prose) | Settings → Models, "in Settings" for a Profile setting | "›" is the path separator in prose. |
| **base resume** | base, bases, career-track resume, source resume | Plain "resume" in actions ("Use resume as is"). |
| **tailored resume** | draft (for the tailored copy) | "draft" stays for unapproved bullets, a template's status and a draft application. |
| **small sample** | directional only, n=… | |

### D0.2 The vocabulary ratchet: `backend/tests/test_frontend_vocabulary.py` (new, L0)

It reads what reaches the screen: string literals, template-literal text and JSX text in `frontend/app`,
`frontend/components`, `frontend/lib` and `extension/panel`. It skips comments, import specifiers,
directives, type aliases, `className` values, the arguments of `cn(`, `clsx(`, `cva(` and `twMerge(`, and
`console.*` output, and it judges only prose (a space between two letters, or one capitalized word), so keys, paths and enum values never
trip it. It was run against `8cac7cf9`: 17/17 pass with the pending blocks, and every flagged string maps to a
row in D2–D8. The five false positives the first version produced (a comment between JSX attributes, a
comment before a `return (` JSX, `<Combobox.Root<Item, true>`, `<T extends string>(` arrow generics, and a
`console.warn` message) are the scanner's last five cases.

The pending counts are at `8cac7cf9`. A–C change some of these files first, so **regenerate the numbers
when L0 lands** (`cd backend && python tests/test_frontend_vocabulary.py` prints them) and split them into
the lane blocks with the file-to-lane table in *File ownership*.

```python
"""Vocabulary ratchet: the words a user reads follow the glossary.

docs/frontend-conventions.md, Microcopy rules, "Canonical terms", is the
glossary. This test reads what reaches the screen and refuses the banned
variants. It reads:

- string literals ('…', "…") and the text chunks of template literals
  (outside `${…}`, whose expressions are scanned as code);
- JSX text (between a tag's `>` and the next `<` or `{`).

It skips comments, `import`/`export … from` specifiers, `"use client"`,
TypeScript type positions it can see (`type X = "a" | "b"`), `className=`
values, the arguments of `cn(`, `clsx(`, `cva(` and `twMerge(`, and
`console.*(` output.

Only PROSE is judged: JSX text, or a literal that holds a space between two
letters, or one capitalized word (`"Knobs"`). Keys, paths, query keys and enum
values (`"kb_inbox"`, `"/api/kb/entities"`, `"on_site"`) have neither, so a
code string never trips a word rule.

`_ALLOWED` lists the deliberate exceptions as (file, phrase). A phrase that no
longer matches anything fails `test_allowlist_is_current`, so the list only
shrinks. The same scan covers the Companion panel (extension/panel).
"""

from __future__ import annotations

import re
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
    ("slash for or", re.compile(r"(?<![\w/.:#@-])(?!AI/ML\b|UI/UX\b)[A-Za-z]{2,}/[A-Za-z]{2,}(?![\w/])"), "pick one word"),
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
        # Kilobytes in a file size, not the product.
        ("frontend/components/career/documents-panel.tsx", "KB"),
        # The ONE place that says what the Companion is. The lane that writes
        # that sentence adds its (file, "browser extension") row here.
        # The sidebar group that holds Career history, Base resumes and Templates.
        ("frontend/components/app-sidebar.tsx", "library"),
        # Load-order errors for a developer; the panel never shows them.
        ("extension/panel/actions.js", "panel/actions"),
        ("extension/panel/stages.js", "panel/stages"),
    }
)

_GENERIC_ARROW = re.compile(r"<\s*[A-Z]\w*\s*(?:extends\b|,)")
_TYPE_ALIAS = re.compile(r"\btype\s+\w+(?:<[^=]*>)?\s*=")
_PROSE = re.compile(r"[A-Za-z]\s+[A-Za-z(]|^[A-Z][a-z]+$")


def _is_prose(text: str) -> bool:
    return bool(_PROSE.search(text.strip()))


class _Scanner:
    """A small hand tokenizer: enough of TS/TSX/JS to find what a user reads."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.found: list[tuple[int, str]] = []  # (offset, text)
        # Frames: (opener, callee or attribute) for ( [ { and JSX tags.
        self.frames: list[tuple[str, str | None]] = []
        # Comment spans already passed, so a look-back can step over them.
        self.comments: list[tuple[int, int]] = []

    # -- helpers -----------------------------------------------------------
    def _comment_end(self, i: int) -> int | None:
        """Index after a comment starting at i (recorded), else None."""
        if self.src.startswith("//", i):
            nl = self.src.find("\n", i)
            end = len(self.src) if nl < 0 else nl
        elif self.src.startswith("/*", i):
            close = self.src.find("*/", i + 2)
            end = len(self.src) if close < 0 else close + 2
        else:
            return None
        self.comments.append((i, end))
        return end

    def _prev_significant(self, i: int) -> str:
        j = i - 1
        while j >= 0:
            if self.src[j].isspace():
                j -= 1
                continue
            span = next((a for a, b in reversed(self.comments) if a <= j < b), None)
            if span is None:
                break
            j = span - 1
        if j < 0:
            return ""
        if self.src[j].isalnum() or self.src[j] in "_$":
            k = j
            while k >= 0 and (self.src[k].isalnum() or self.src[k] in "_$"):
                k -= 1
            return self.src[k + 1 : j + 1]
        return self.src[j]

    def _callee(self, i: int) -> str:
        """The dotted name before the `(` at i (`console.warn`, `cn`), or ""."""
        j = i - 1
        while j >= 0 and self.src[j].isspace():
            j -= 1
        k = j
        while k >= 0 and (self.src[k].isalnum() or self.src[k] in "_$."):
            k -= 1
        return self.src[k + 1 : j + 1]

    def _in_class_context(self) -> bool:
        return any(
            tag is not None
            and (tag in _CLASS_ATTRS or tag.rsplit(".", 1)[-1] in _CLASS_CALLS or tag in _SILENT_CALLS)
            for _o, tag in self.frames
        )

    def _add(self, at: int, text: str) -> None:
        if not self._in_class_context():
            self.found.append((at, text))

    # -- literals ------------------------------------------------------------
    def _quoted(self, i: int) -> int:
        quote = self.src[i]
        j = i + 1
        buf: list[str] = []
        while j < len(self.src) and self.src[j] != quote:
            if self.src[j] == "\\":
                buf.append(self.src[j + 1 : j + 2])
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
                buf.append(self.src[j + 1 : j + 2])
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
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
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
        if prev == "" or prev in _KEYWORDS_BEFORE_EXPR:
            return True
        return prev in ("(", ",", "=", "?", ":", "{", "[", "&", "|", "}", ">", ";")

    def _jsx(self, i: int) -> int:
        """From `<` of an element; returns the index after the matching close."""
        depth = 0
        j = i
        while j < len(self.src):
            if self.src.startswith("</", j):  # closing tag
                j = self.src.find(">", j) + 1
                depth -= 1
                if depth <= 0:
                    return j
                j = self._jsx_text(j)
                continue
            if self.src[j] == "<":
                j, self_closing = self._jsx_tag(j)
                if not self_closing:
                    depth += 1
                    j = self._jsx_text(j)
                elif depth == 0:
                    return j
                else:
                    j = self._jsx_text(j)
                continue
            j += 1
        return j

    def _jsx_tag(self, i: int) -> tuple[int, bool]:
        """Parse `<Name attr=… >`; returns (index after `>`, self-closing)."""
        j = i + 1
        while j < len(self.src) and (self.src[j].isalnum() or self.src[j] in "._-$:"):
            j += 1
        if self.src[j : j + 1] == "<":  # <Combobox.Root<Item, true> …>: a type argument
            level = 0
            while j < len(self.src):
                level += (self.src[j] == "<") - (self.src[j] == ">")
                j += 1
                if level == 0:
                    break
        attr: str | None = None
        while j < len(self.src):
            ch = self.src[j]
            end = self._comment_end(j)
            if end is not None:
                j = end
                continue
            if ch == "/" and self.src[j + 1 : j + 2] == ">":
                return j + 2, True
            if ch == ">":
                return j + 1, False
            if ch.isalpha() or ch == "_":
                k = j
                while k < len(self.src) and (self.src[k].isalnum() or self.src[k] in "_-:"):
                    k += 1
                attr = self.src[j:k]
                j = k
                continue
            if ch in "\"'":
                self.frames.append(("attr", attr))
                j = self._quoted(j)
                self.frames.pop()
                continue
            if ch == "{":
                self.frames.append(("attr", attr))
                j = self._code(j + 1, stop="}")
                self.frames.pop()
                continue
            j += 1
        return j, True

    def _jsx_text(self, i: int) -> int:
        j = i
        start = i
        while j < len(self.src):
            ch = self.src[j]
            if ch == "<":
                break
            if ch == "{":
                self._add(start, self.src[start:j])
                j = self._code(j + 1, stop="}")
                start = j
                continue
            j += 1
        self._add(start, self.src[start:j])
        return j

    # -- code ------------------------------------------------------------------
    def _code(self, i: int, stop: str | None = None) -> int:
        j = i
        depth = 0
        while j < len(self.src):
            ch = self.src[j]
            end = self._comment_end(j)
            if end is not None:
                j = end
                continue
            if ch in "\"'":
                j = self._quoted(j)
                continue
            if ch == "`":
                j = self._template(j)
                continue
            if ch == "/" and self._prev_significant(j) in ("(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";", "", "return"):
                j = self._regex(j)
                continue
            if ch == "<" and self._jsx_can_start(j):
                j = self._jsx(j)
                continue
            if ch in "([{":
                callee = self._callee(j) if ch == "(" else None
                self.frames.append((ch, callee))
                depth += 1
                j += 1
                continue
            if ch in ")]}":
                if stop and ch == stop and depth == 0:
                    return j + 1
                if self.frames:
                    self.frames.pop()
                depth -= 1
                j += 1
                continue
            j += 1
        return j

    def run(self) -> list[tuple[int, str]]:
        self._code(0)
        return self.found


def _strip_non_ui(src: str) -> str:
    """Blank out lines whose strings are never shown: imports, re-exports,
    directives and type aliases. Offsets and line numbers stay put."""
    out = []
    for line in src.splitlines(keepends=True):
        s = line.lstrip()
        if (
            s.startswith(("import ", "export * from", "\"use client\"", "'use client'"))
            or re.match(r"export \{[^}]*\} from", s)
            or _TYPE_ALIAS.match(s.removeprefix("export "))
        ):
            out.append(re.sub(r"[^\n]", " ", line))
        else:
            out.append(line)
    return "".join(out)


def _files() -> Iterator[Path]:
    for root, suffixes in _ROOTS:
        for path in sorted((_REPO / root).rglob("*")):
            if path.suffix in suffixes and ".test." not in path.name and "node_modules" not in path.parts:
                yield path


def _html_text(src: str) -> list[tuple[int, str]]:
    return [(m.start(1), m.group(1)) for m in re.finditer(r">([^<>]+)<", src)]


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


def violations() -> list[tuple[str, int, str, str, str]]:
    out = []
    for rel, line, text in ui_strings():
        for name, pattern, why in _RULES:
            for match in pattern.finditer(text):
                phrase = match.group(0).strip()
                if (rel, phrase) in _ALLOWED:
                    continue
                out.append((rel, line, name, text, why))
    return out


# Files a copy lane has not swept yet: {file: violations left}. One block per
# lane of docs/plans/2026-09-23-ux-ia-appendix-d-copy.md, so two lanes never
# edit the same lines. A lane deletes its block when it lands; the last lane
# deletes `_PENDING` itself. Counts are at 8cac7cf9: regenerate them when L0
# lands (`python tests/test_frontend_vocabulary.py` from backend/ prints them).
_PENDING_L0: dict[str, int] = {
    "frontend/lib/api.ts": 3,
}
_PENDING_L1: dict[str, int] = {
    "frontend/app/analytics/page.tsx": 7,
    "frontend/app/applications/page.tsx": 4,
    "frontend/app/jobs/[id]/page.tsx": 7,
    "frontend/app/new/page.tsx": 7,
    "frontend/app/proposals/page.tsx": 1,
    "frontend/app/referrals/page.tsx": 6,
    "frontend/components/analytics/analytics-overview.tsx": 5,
    "frontend/components/analytics/autofill-coverage-card.tsx": 5,
    "frontend/components/analytics/base-summary-cards.tsx": 3,
    "frontend/components/analytics/gap-tiers-panel.tsx": 18,
    "frontend/components/application-panel.tsx": 1,
    "frontend/components/ats-compare-panel.tsx": 6,
    "frontend/components/ats-score-panel.tsx": 3,
    "frontend/components/charts/ats-over-time-chart.tsx": 1,
    "frontend/components/charts/heatmap-chart.tsx": 1,
    "frontend/components/explore/explore-overview.tsx": 4,
    "frontend/components/job-extracted-fields.tsx": 4,
    "frontend/components/job-extraction-summary.tsx": 1,
    "frontend/components/job-knockout-card.tsx": 4,
    "frontend/components/job-tracking-url-field.tsx": 1,
    "frontend/components/proposals/proposal-agent-panel.tsx": 1,
    "frontend/components/proposals/proposals-section.tsx": 7,
    "frontend/components/proposals/triage-actions.tsx": 4,
    "frontend/components/qa-tab.tsx": 5,
}
_PENDING_L2: dict[str, int] = {
    "frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx": 19,
    "frontend/components/gap-analysis/gap-card.tsx": 12,
    "frontend/components/gap-analysis/resolution-controls.tsx": 16,
}
_PENDING_L3: dict[str, int] = {
    "frontend/app/base-resumes/page.tsx": 5,
    "frontend/app/templates/[id]/page.tsx": 7,
    "frontend/app/templates/page.tsx": 1,
    "frontend/components/base-resumes/base-resume-thumbnail.tsx": 3,
    "frontend/components/base-resumes/new-base-resume-dialog.tsx": 13,
    "frontend/components/resume-editor/diff-review.tsx": 10,
    "frontend/components/resume-editor/editor-body.tsx": 4,
    "frontend/components/resume-editor/extra-sections-editor.tsx": 5,
    "frontend/components/resume-editor/formatting-panel.tsx": 1,
    "frontend/components/resume-editor/instruct-sheet.tsx": 2,
    "frontend/components/resume-editor/kb-import-drawer.tsx": 10,
    "frontend/components/resume-editor/pdf-pages-preview.tsx": 1,
    "frontend/components/resume-editor/project-editor.tsx": 1,
    "frontend/components/resume-editor/project-port-dialog.tsx": 2,
    "frontend/components/resume-editor/tailored-resume-studio.tsx": 6,
    "frontend/components/resume-health/finding-cards.tsx": 27,
    "frontend/components/resume-health/health-badges.tsx": 2,
    "frontend/components/resume-health/health-report-page.tsx": 4,
    "frontend/components/resume-versions/version-diff-view.tsx": 1,
    "frontend/components/resume-versions/version-history-sheet.tsx": 1,
    "frontend/components/role-category-picker.tsx": 2,
    "frontend/components/templates/requires-tex-badge.tsx": 2,
    "frontend/components/templates/template-gallery.tsx": 2,
    "frontend/components/templates/template-thumbnail.tsx": 1,
    "frontend/lib/describe-edit.ts": 5,
    "frontend/lib/extra-sections.ts": 1,
    "frontend/lib/health-report.ts": 4,
    "frontend/lib/render-note.ts": 1,
    "frontend/lib/resume-schema.ts": 2,
    "frontend/lib/studio.ts": 2,
}
_PENDING_L4: dict[str, int] = {
    "frontend/app/career/page.tsx": 5,
    "frontend/components/career/capture-box.tsx": 1,
    "frontend/components/career/documents-panel.tsx": 8,
    "frontend/components/career/entity-detail.tsx": 4,
    "frontend/components/career/exports-card.tsx": 1,
    "frontend/components/career/first-run-import-card.tsx": 2,
    "frontend/components/career/inbox-panel.tsx": 5,
    "frontend/components/career/merge-entity-dialog.tsx": 6,
    "frontend/components/career/new-entity-dialog.tsx": 15,
    "frontend/components/career/points-list.tsx": 9,
    "frontend/components/career/profile-panel.tsx": 2,
    "frontend/components/career/resume-import-dialog.tsx": 5,
    "frontend/components/career/send-to-resume-dialog.tsx": 10,
    "frontend/components/kb-sync-pill.tsx": 12,
}
_PENDING_L5: dict[str, int] = {
    "frontend/app/settings/page.tsx": 1,
    "frontend/components/settings/auto-apply-section.tsx": 2,
    "frontend/components/settings/autofill-section.tsx": 14,
    "frontend/components/settings/job-preferences-section.tsx": 2,
    "frontend/components/settings/llm-endpoint.tsx": 3,
    "frontend/components/settings/market-section.tsx": 1,
    "frontend/components/settings/model-catalog-panel.tsx": 1,
    "frontend/components/settings/models-section.tsx": 8,
    "frontend/components/settings/persona-section.tsx": 2,
    "frontend/components/settings/prompts-section.tsx": 2,
    "frontend/components/settings/quick-tailor-section.tsx": 7,
}
_PENDING_L6: dict[str, int] = {
    "frontend/app/error.tsx": 1,
    "frontend/app/global-error.tsx": 1,
    "frontend/components/app-sidebar.tsx": 4,
    "frontend/components/chat/chat-page.tsx": 1,
    "frontend/components/chat/kb-capture-card.tsx": 1,
    "frontend/components/chat/scope-picker.tsx": 8,
    "frontend/components/setup/getting-started-card.tsx": 3,
    "frontend/components/setup/setup-steps.ts": 4,
    "frontend/components/setup/upload-dialog.tsx": 8,
    "frontend/components/version-banner.tsx": 1,
}
_PENDING_L7: dict[str, int] = {
    "extension/panel/actions/fill.js": 3,
    "extension/panel/actions/job.js": 3,
    "extension/panel/actions/pause.js": 2,
    "extension/panel/actions/qna.js": 3,
    "extension/panel/actions/resume.js": 3,
    "extension/panel/actions/track.js": 2,
    "extension/panel/panel.js": 4,
    "extension/panel/stages/fill.js": 4,
    "extension/panel/stages/job.js": 3,
    "extension/panel/stages/resume.js": 3,
    "extension/panel/stages/score.js": 2,
    "extension/panel/stages/track.js": 1,
}
_PENDING: dict[str, int] = {
    **_PENDING_L0, **_PENDING_L1, **_PENDING_L2, **_PENDING_L3,
    **_PENDING_L4, **_PENDING_L5, **_PENDING_L6, **_PENDING_L7,
}


def test_ui_words_follow_the_glossary():
    bad = [v for v in violations() if v[0] not in _PENDING]
    assert not bad, "banned UI words (see Microcopy rules, Canonical terms):\n" + "\n".join(
        f"{rel}:{line}: [{name}] {text!r} -> {why}" for rel, line, name, text, why in bad
    )


def test_pending_files_only_shrink():
    now: dict[str, int] = {}
    for rel, *_rest in violations():
        now[rel] = now.get(rel, 0) + 1
    grew = {rel: (now.get(rel, 0), cap) for rel, cap in _PENDING.items() if now.get(rel, 0) > cap}
    done = sorted(rel for rel, cap in _PENDING.items() if now.get(rel, 0) < cap)
    assert not grew, f"new banned words in a file not yet swept: {grew}"
    assert not done, f"lower these _PENDING counts (or delete the row at 0): {done}"


def test_allowlist_is_current():
    live = {(rel, m.group(0).strip()) for rel, _l, text in ui_strings() for _n, p, _w in _RULES for m in p.finditer(text)}
    stale = sorted(f"{rel} :: {phrase}" for rel, phrase in _ALLOWED - live)
    assert not stale, stale


@pytest.mark.parametrize(
    "src,seen,unseen",
    [
        ('toast.success("Synced to KB")', ["Synced to KB"], []),
        ("<p>Open your Career KB</p>", ["Open your Career KB"], []),
        ('<p className="text-muted-foreground render">Hi there</p>', ["Hi there"], ["text-muted-foreground render"]),
        ("cn(\"flex gap-2\", ok && \"re-render x\")", [], ["re-render x"]),
        ('// the KB cache\nconst k = ["kb", id];', [], ["the KB cache", "kb"]),
        ("const m = new Map<string, number>(); // KB stuff\nconst s = `Sync ${n} to KB`;", ["Sync ", " to KB"], ["KB stuff"]),
        ("x = a.replace(/\"/g, \"'\"); y = \"Two words\"", ["Two words"], []),
        ('{open ? <span>Hide it</span> : "Show it"}', ["Hide it", "Show it"], []),
        ("if (a < b && c > d) { t = \"Plain text\" }", ["Plain text"], []),
        ("return (\n  // a note about the KB\n  <span className=\"group/title flex\">Rename it</span>\n);",
         ["Rename it"], ["group/title flex", "a note about the KB"]),
        ("<Combobox.Root<Item, true>\n  multiple\n  // compares by id, not the KB row\n  value={v}\n>\n  <b>Pick one</b>\n</Combobox.Root>",
         ["Pick one"], ["compares by id, not the KB row"]),
        ("const row = <T extends string>(k: T) => {\n  // the KB order\n  return <p>Row text</p>;\n};",
         ["Row text"], ["the KB order"]),
        ("<div\n  /* the shell's one id: the KB note */\n  id=\"main\"\n>Skip here</div>", ["Skip here"], ["the shell's one id: the KB note"]),
        ('console.warn("Failed to close the tailoring session", e); toast("Saved it")', ["Saved it"],
         ["Failed to close the tailoring session"]),
    ],
)
def test_the_scanner_reads_ui_text_and_skips_code(src: str, seen: list[str], unseen: list[str]):
    texts = [" ".join(t.split()) for _a, t in _Scanner(_strip_non_ui(src)).run()]
    texts = [t for t in texts if _is_prose(t)]
    for want in seen:
        assert want.strip() in [t.strip() for t in texts], (want, texts)
    for not_want in unseen:
        assert not_want not in texts, (not_want, texts)


if __name__ == "__main__":  # prints the _PENDING dict for the tree as it is now
    counts: dict[str, int] = {}
    for rel, *_rest in violations():
        counts[rel] = counts.get(rel, 0) + 1
    for rel, n in sorted(counts.items()):
        print(f'    "{rel}": {n},')
```

**Why a pending count per file, not a list of strings.** A lane rewrites dozens of strings per file; a
per-string list would conflict line by line. The count only moves down (`test_pending_files_only_shrink`),
so a new banned word in an unswept file still fails.

**Mutation checks (L0).** Add `toast.success("Saved to KB")` to `app/applications/page.tsx` after L1 lands
(its block gone): `test_ui_words_follow_the_glossary` fails naming the line. Put the same string in a file
still pending: `test_pending_files_only_shrink` fails with "grew". Delete a pending string: it fails with
"lower these _PENDING counts".

---

## D1. Conventions, shared primitives and the pins they move (lane L0)

### D1.1 `docs/frontend-conventions.md`: exact new text

**a. Microcopy rules, the *Placeholder* bullet (`:855-870`). Replace the whole bullet with:**

> - *Placeholder*: none in a blank field. No example value, no sample text, no URL cue, no instruction, no
>   statement about the field and no restated label. A format, a constraint, a default or a consequence is
>   hint text, between the label and the control (`aria-describedby`). A field whose placeholder was its only
>   visible name gets a visible `Label` first. The one exception is a short `…` prompt in a search box, the
>   Assistant composer or a chip add-row (the ratchet's `_PROMPTS` list). This follows GOV.UK's text-input
>   guidance: a placeholder vanishes as you type, not every screen reader reads it, and an example in an empty
>   field reads as a value already filled in. The ratchet (`backend/tests/test_frontend_placeholders.py`)
>   fails closed: a value it cannot read, such as a concatenation, a call or a prop from another file, fails
>   unless it is on its pass-through list.

**b. Form conventions (`:825-831`). Replace the first sentence ("optionality lives on the LABEL … (see
Microcopy rules);") with:**

> - Form conventions: optionality lives on the LABEL as a muted "(optional)" (`<Label optional>`, one
>   definition in `components/ui/label.tsx`; GOV.UK's wording), never a placeholder, a hand-written span or
>   a "· optional" suffix; a blank field holds no placeholder (see Microcopy rules); page subtitles are one
>   clause; every `SelectValue` gets children

(the rest of the bullet is unchanged).

**c. Microcopy rules: four new bullets after *The em dash is not a clause joiner* (`:872-876`):**

> - *Canonical terms* (one word per thing; `backend/tests/test_frontend_vocabulary.py` refuses the banned
>   variants in every string a user can read, including the Companion panel):
>   Career history (never Career KB, KB, Knowledge Base or library; the sidebar group stays Career library),
>   item (never entity, record or entry), bullet (never point; states Draft, Approved, Not used; "Bullet style"
>   is the glyph setting), ATS score (spelled out once per surface: "how an applicant tracking system rates a
>   resume for this job"; never composite or fit score; lift is Score gain), job description (never JD or
>   posting), Add job and Save job (never New application or Extract), Refresh details, gap analysis (never
>   session), Quick tailor, Create PDF and Update PDF (never render or compile), Update score (never
>   re-score), Hide, Show and Hidden, Archive and Restore, Other sections, Must fix, Mark as OK and Undo,
>   Check health and Check again, Check template, Version 12 and Version history, skill group, School,
>   On-site, Assistant (the in-app chat; one conversation is a chat), connected agents, Companion, Suggested
>   edit, Agent inbox (lanes Needs you, To review, Queued, Applying, History; chips Proposed, Queued,
>   Approved, Applied, Skipped), In progress, Offer, Role, Employment type, Diversity questions (voluntary),
>   resume (no accents), US English. A deliberate exception goes on the ratchet's `_ALLOWED` list with its
>   reason.
> - *Errors*: "Couldn't <what failed>." then what to do next. Build it with `couldnt(what, err)` from
>   `lib/error-text.ts`; a load error passes `errorDetail(err)`. A server's `detail` reaches the screen only
>   when it is a plain sentence written for the user (`isPlainSentence`); raw server text, JSON, schema paths
>   (`experience.2.bullets.0`), status codes and developer steps never do. `lib/api.ts` writes the
>   can't-reach-the-server text for a desktop user and logs its developer detail with `console.error`.
>   Pinned by `test_frontend_error_words.py`.
> - *Separators and marks*: `·` separates facts only in a dense metadata row (a card's meta line, a chip
>   row); never inside a label, a hint, a status line or a sentence, and never for "and", "then" or
>   "optional". No "/" for "or" or "and" (pick one word); a ratio in prose reads "3 of 5". No semicolon: two
>   sentences. Abbreviations are spelled out (years, points, Average, Minimum, Applications).
> - *Toasts*: a success toast names its object ("Template deleted", never "Deleted"); an error toast says what
>   failed (see *Errors*). A count and its noun agree ("1 bullet", "3 bullets").

**d. The autosave paragraph (`:919-920`):** "an edit there reads Save failed and keeps the leave guard"
becomes "an edit there reads Not saved and keeps the leave guard" (the gap page now says what
`AutosaveStatus` says; D3).

**e. The studio's *Empty preview* bullet (`:175-180`):** replace the quoted strings and verbs:

> names the action enabled right now: "No PDF yet. Save to create one." with unsaved edits, otherwise "No
> PDF yet. Choose Create PDF in the ⋯ menu." (the ⋯ trigger's accessible name, "More resume actions", is
> never quoted in visible text). Save is dirty-gated, so a clean studio with no PDF (after Create draft or
> Start over) cannot save, and ⋯ Create PDF is disabled while edits are unsaved or a PDF is updating.

**f. Sidebar bullet (`:794-796`), after appendix A10's edit:** "**Job search** (Applications, Agent inbox,
Referrals), **Career library** (Career history, Base resumes, Templates), **Tools** (Assistant,
Analytics); the pinned button above the groups is **Add job**."

**g. Naming bullet (`:808-816`), append:** "The add-a-job flow is **Add job** (sidebar, tracker, `/new`'s
title "Add a job") and **Save job** (its submit); a job becomes an application when you tailor or apply. The
Agent inbox's lanes are Needs you, To review, Queued, Applying and History, and its chips come from
`PROPOSAL_STATUS_CHIP` (Proposed, Queued, Approved, Applied, Skipped, Needs you, Expired, Check if sent);
the funnel and Analytics use the same words."

**h. Derived setup guidance (`:936-955`):** "a disabled Extract whose `aria-describedby` points at it"
becomes "a disabled Save job whose …"; "offers Import resumes (Run ATS scoring could only return an empty
list)" becomes "offers Import resumes (Score my resumes could only return an empty list)". The quoted "No
ATS scores yet." stays (D2 keeps it).

**i. Spelling sweep.** The conventions doc writes "résumé" 18 times ("New base résumé", "Send to
résumé"). Replace each with the UI's own words ("New base resume", "Add to a resume"), so the doc quotes
what the screen says.

### D1.2 `components/ui/label.tsx`: "(optional)"

Current (`:7-13`, `:30-32`):
```tsx
/**
 * `optional` renders the project's optionality convention (SYSTEM.md §8): a
 * muted " · optional" suffix on the LABEL, never a placeholder reading
 * "Optional" — a placeholder disappears the moment you type, which is exactly
 * when you would want to know the field can be left empty. It lives here so
 * the suffix has one definition; it was written out by hand in three places.
 */
…
      {optional && (
        <span className="text-muted-foreground font-normal">· optional</span>
      )}
```
New:
```tsx
/**
 * `optional` renders the project's optionality convention
 * (docs/frontend-conventions.md, Form conventions): a muted "(optional)" on
 * the LABEL, GOV.UK's wording, never a placeholder. A placeholder disappears
 * the moment you type, which is exactly when you would want to know the field
 * can be left empty. It lives here so the marker has one definition; never
 * write it by hand.
 */
…
      {optional && (
        <span className="text-muted-foreground font-normal">(optional)</span>
      )}
```
The hand-written markers move onto `<Label optional>` in their own lanes: `career/profile-panel.tsx`
(`:135-149`, `:218`, `:372`), `career/entity-detail.tsx:294-318`, `career/new-entity-dialog.tsx:342-376`
(L4); `base-resumes/new-base-resume-dialog.tsx:525`, `resume-health/metric-ask-input.tsx:130`,
`resume-health/finding-cards.tsx:241` (L3); the gap page `:798` and `resolution-controls.tsx:495` (L2).

**Pins.** No test reads "· optional" (searched). `test_frontend_referrals.py:95-99` and
`test_frontend_first_run.py:141` read `<Label … optional>` and still pass. Add to
`test_frontend_error_words.py` (below): `assert '(optional)</span>' in label and '· optional' not in label`.

### D1.3 Errors: `lib/error-text.ts` (new), `lib/api.ts`, `components/load-error-state.tsx`

**New `lib/error-text.ts`** (no imports; node-testable):
```ts
/**
 * The words for a failure (docs/frontend-conventions.md, Microcopy rules,
 * *Errors*): what failed, then what to do. A thrown message is shown only when
 * it is a plain sentence written for the user: the server's plain details
 * (appendix D9 rewrote every one a user can reach), the sentences lib/api.ts
 * writes for a network failure or a rejected form, and the app's own
 * `throw new Error("Choose a file first.")`. JSON, schema paths, status codes,
 * lowercase developer text and stack words never are.
 */

/** Starts with a capital, ends with a stop, and holds nothing that looks like code. */
export function isPlainSentence(text: string): boolean {
  const t = text.trim();
  return t.length > 0 && t.length <= 240 && /^[A-Z][^{}[\]<>_`|\\]*[.!?]$/.test(t);
}

/** The part of an error a user may read, or undefined. For a load error's `detail`. */
export function errorDetail(err: unknown): string | undefined {
  const message = err instanceof Error ? err.message.trim() : "";
  return isPlainSentence(message) ? message : undefined;
}

/** "Couldn't save the resume. <detail or Try again.>" for a toast. */
export function couldnt(what: string, err: unknown): string {
  return `Couldn't ${what}. ${errorDetail(err) ?? "Try again."}`;
}
```

**New `lib/error-text.test.ts`:**
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { couldnt, errorDetail, isPlainSentence } from "./error-text.ts";

test("a plain sentence passes; code, JSON and fragments do not", () => {
  assert.equal(isPlainSentence("This resume no longer exists."), true);
  assert.equal(isPlainSentence("slug must be lowercase alphanumeric with underscores"), false);
  assert.equal(isPlainSentence('[{"loc":["body","title"],"msg":"field required"}]'), false);
  assert.equal(isPlainSentence("experience.2.bullets.0: String must contain at least 1 character(s)"), false);
  assert.equal(isPlainSentence("Application not found"), false);
});

test("couldnt names what failed, then the plain detail or Try again", () => {
  assert.equal(couldnt("save the resume", new Error("A section with this name already exists.")),
    "Couldn't save the resume. A section with this name already exists.");
  assert.equal(couldnt("save the resume", new Error("Request failed: 500")), "Couldn't save the resume. Try again.");
  assert.equal(couldnt("save the resume", "boom"), "Couldn't save the resume. Try again.");
});

test("errorDetail hides what is not for the user", () => {
  assert.equal(errorDetail(new Error("Target entity not found")), undefined);
  assert.equal(errorDetail(null), undefined);
});
```

**`lib/api.ts`** (L0; appendix A adds one body field elsewhere in this file, no overlap):

`:79-93` `networkErrorMessage` becomes:
```ts
/** A failed fetch, in words for a desktop user. The developer detail (the
 * base URL and the browser's own message) goes to the console, not the screen. */
function networkErrorMessage(original: string): string {
  if (original !== "Failed to fetch" && !original.includes("NetworkError")) {
    return original;
  }
  console.error("apiFetch: network error", { base: getApiBase() || "same-origin /api", original });
  return "Maestro CS isn't responding. Check that it's running, then try again.";
}
```
`:120-131` (the non-ok branch) becomes:
```ts
    const detailRaw =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : undefined;
    if (typeof detailRaw !== "string") {
      console.error("apiFetch: request failed", { path, status: response.status, body });
    }
    const message =
      typeof detailRaw === "string"
        ? detailRaw
        : Array.isArray(detailRaw)
          ? "Some details weren't accepted. Check them and try again."
          : "Something went wrong. Try again.";
    throw new ApiError(response.status, message, body);
```
`:602` (chat attachment): `let detail = res.status === 413 ? "This file is too large." : "Couldn't upload the file.";`
`:633` (chat stream): `let detail = "The Assistant couldn't reply. Try again.";`

The raw body stays on `ApiError.body` for callers that need it (the gap page's 409, the health 409s).

**`components/load-error-state.tsx:72`:**
`{shownDetail ?? "The request failed. It may just be the backend restarting."}` →
`{shownDetail ?? "Check that Maestro CS is running, then try again."}`
(`test_load_error_state_shows_the_remembered_detail` still reads `{shownDetail ?? `.)

**Every call site** passes words through the helpers: `onError: (err) => toast.error(couldnt("delete the
job", err))` and `detail={errorDetail(query.error)}`. Each group below lists its sites with the `what`
phrase. `components/settings/setting-card.tsx:98` `detail={firstMessage(queries)}` becomes
`detail={errorDetail(firstError(queries))}` (L5, after C6 rewrites that file).

**New `backend/tests/test_frontend_error_words.py`** (L0; lanes delete their pending blocks):
```python
"""Error words: a failure says what failed and what to do, never raw text.

A toast or a load error goes through lib/error-text.ts (`couldnt`,
`errorDetail`), which shows a thrown message only when it is a plain sentence
for the user. lib/api.ts writes the network and rejected-form sentences and
logs the developer detail to the console. Node tests cover error-text.ts; they
are not in CI, so the branches that matter are pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# `toast.error(err.message)`, `toast.error(String(e))`, `detail={(q.error as Error)?.message}`, …
_RAW = re.compile(
    r"toast\.(?:error|warning)\(\s*(?:\w+\.message\b|String\(\w+\)|\w+ instanceof Error\s*\?\s*\w+\.message|event\.detail\b)"
    r"|detail=\{\s*(?:\(?\w+(?:\.\w+)*(?:\s+as\s+Error(?:\s*\|\s*null)?)?\)?\??\.message|\w+ instanceof Error \? \w+\.message)"
    r"|firstMessage\(",
    re.S,
)

# Raw-message sites a lane has not converted yet, at 8cac7cf9 (133 in all).
# One block per lane of appendix D; a lane deletes its block when it lands.
_PENDING_L1: dict[str, int] = {
    "app/applications/[id]/page.tsx": 1,
    "app/applications/page.tsx": 5,
    "app/jobs/[id]/page.tsx": 4,
    "app/new/page.tsx": 1,
    "app/referrals/page.tsx": 4,
    "components/analytics/autofill-coverage-card.tsx": 1,
    "components/application-panel.tsx": 3,
    "components/ats-compare-panel.tsx": 2,
    "components/ats-score-panel.tsx": 4,
    "components/job-tracking-url-field.tsx": 1,
    "components/proposals/proposal-agent-panel.tsx": 1,
    "components/proposals/proposals-section.tsx": 1,
    "components/proposals/triage-actions.tsx": 3,
    "components/qa-tab.tsx": 7,
}
_PENDING_L2: dict[str, int] = {
    "app/jobs/[id]/tailor/[sessionId]/page.tsx": 6,
}
_PENDING_L3: dict[str, int] = {
    "app/applications/[id]/resume/page.tsx": 1,
    "app/base-resumes/[slug]/page.tsx": 1,
    "app/base-resumes/page.tsx": 4,
    "app/templates/[id]/page.tsx": 5,
    "app/templates/page.tsx": 7,
    "components/base-resumes/new-base-resume-dialog.tsx": 2,
    "components/resume-editor/editable-title.tsx": 1,
    "components/resume-editor/editor-body.tsx": 2,
    "components/resume-editor/instruct-sheet.tsx": 2,
    "components/resume-editor/kb-import-drawer.tsx": 1,
    "components/resume-editor/project-port-dialog.tsx": 1,
    "components/resume-editor/tailored-resume-studio.tsx": 4,
    "components/resume-health/batch-ask-dialog.tsx": 1,
    "components/resume-health/health-report-page.tsx": 3,
    "components/resume-health/report-errors.ts": 1,
    "components/resume-versions/version-history-sheet.tsx": 1,
    "components/role-category-picker.tsx": 1,
}
_PENDING_L4: dict[str, int] = {
    "components/career/capture-box.tsx": 2,
    "components/career/documents-panel.tsx": 3,
    "components/career/entity-detail.tsx": 2,
    "components/career/exports-card.tsx": 1,
    "components/career/first-run-import-card.tsx": 1,
    "components/career/inbox-panel.tsx": 3,
    "components/career/merge-entity-dialog.tsx": 1,
    "components/career/new-entity-dialog.tsx": 1,
    "components/career/points-list.tsx": 2,
    "components/career/profile-panel.tsx": 1,
    "components/career/resume-import-dialog.tsx": 1,
    "components/career/send-to-resume-dialog.tsx": 3,
    "components/kb-sync-pill.tsx": 1,
}
_PENDING_L5: dict[str, int] = {
    "app/profile/page.tsx": 1,
    "components/settings/auto-apply-section.tsx": 1,
    "components/settings/autofill-section.tsx": 3,
    "components/settings/job-preferences-section.tsx": 1,
    "components/settings/mcp-workflow-section.tsx": 1,
    "components/settings/model-catalog-panel.tsx": 3,
    "components/settings/models-section.tsx": 2,
    "components/settings/persona-section.tsx": 2,
    "components/settings/prompts-section.tsx": 2,
    "components/settings/quick-tailor-section.tsx": 1,
    "components/settings/setting-card.tsx": 2,
}
_PENDING_L6: dict[str, int] = {
    "components/chat/change-card.tsx": 1,
    "components/chat/chat-page.tsx": 6,
    "components/chat/edit-proposal-card.tsx": 1,
    "components/chat/proposal-card.tsx": 1,
    "components/setup/getting-started-card.tsx": 1,
}
_PENDING: dict[str, int] = {
    **_PENDING_L1, **_PENDING_L2, **_PENDING_L3, **_PENDING_L4, **_PENDING_L5, **_PENDING_L6,
}


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for root in ("app", "components", "lib", "hooks"):
        for path in sorted((_FRONTEND / root).rglob("*.ts*")):
            if ".test." in path.name:
                continue
            n = len(_RAW.findall(path.read_text(encoding="utf-8")))
            if n:
                out[path.relative_to(_FRONTEND).as_posix()] = n
    return out


def test_no_raw_error_text_reaches_the_screen():
    bad = {rel: n for rel, n in _counts().items() if rel not in _PENDING}
    assert not bad, f"use couldnt(what, err) or errorDetail(err) (lib/error-text.ts): {bad}"


def test_pending_error_sites_only_shrink():
    now = _counts()
    grew = {rel: (now.get(rel, 0), cap) for rel, cap in _PENDING.items() if now.get(rel, 0) > cap}
    done = sorted(rel for rel, cap in _PENDING.items() if now.get(rel, 0) < cap)
    assert not grew, grew
    assert not done, f"lower these _PENDING counts (or delete the row at 0): {done}"


def test_the_server_unreachable_words_are_for_a_desktop_user():
    api = _read("lib/api.ts")
    assert '"Maestro CS isn\'t responding. Check that it\'s running, then try again."' in api
    for developer_word in ("docker compose", "curl ", "FastAPI", "port 8001", "Original error"):
        assert developer_word not in api, developer_word
    assert 'console.error("apiFetch: network error"' in api
    assert "JSON.stringify(detailRaw)" not in api
    assert "Request failed: ${" not in api
    assert '"Some details weren\'t accepted. Check them and try again."' in api
    assert "Upload failed (" not in api and "Chat request failed (" not in api


def test_the_load_error_default_names_the_next_step():
    src = _read("components/load-error-state.tsx")
    assert '{shownDetail ?? "Check that Maestro CS is running, then try again."}' in src
    assert "backend restarting" not in src


def test_error_text_shows_only_plain_sentences():
    src = _read("lib/error-text.ts")
    assert "^[A-Z][^{}[\\]<>_`|\\\\]*[.!?]$" in src
    assert "return `Couldn't ${what}. ${errorDetail(err) ?? \"Try again.\"}`;" in src
    assert not re.search(r"^import (?!type )", src, re.M)


def test_optional_reads_optional_in_brackets():
    label = _read("components/ui/label.tsx")
    assert "(optional)</span>" in label and "· optional" not in label
```

**Mutation checks.** Restore `JSON.stringify(detailRaw)`: the server-unreachable pin fails. Put
`toast.error(err.message)` back in a converted file: `test_no_raw_error_text_reaches_the_screen` fails with
the file name.

### D1.4 `backend/tests/test_frontend_placeholders.py`: the rule flips

Verified: with the changes below, the file passes 28/28 at `8cac7cf9`. Each lane then deletes its
`_PENDING_EXAMPLES_Lx` set and rewrites its own per-file functions (named in each group's pins).

1. **Docstring (`:1-7`)** becomes:
```python
"""Placeholder ratchet: a blank field holds no text.

No example values, no sample text, no URL cue: a format or constraint is hint
text (docs/frontend-conventions.md, Microcopy rules, *Placeholder*). The one
exception is a short ellipsis prompt in a search box, the Assistant composer or
a chip add-row, allowed only when the file and the exact string are on
``_PROMPTS``. ``SelectValue`` and image ``placeholder`` props are not inputs.
Placeholders a copy lane has not removed yet sit on that lane's
``_PENDING_EXAMPLES_*`` set, which may only shrink.
```
(the second and third paragraphs, about resolvable values and failing closed, stay).
2. **`:22-32`:** add `import pytest` after `from pathlib import Path`; delete `_URL_CUE = "https://" + _ELLIPSIS`.
3. **After `_PROMPTS` (`:54`)**, add the pending sets (at `8cac7cf9`; appendix A3 removes
   `proposals-section.tsx`'s "e.g. 50" first, so drop that row when L0 lands):
```python
# Example placeholders a copy lane has not removed yet (appendix D). One set
# per lane so lanes never edit the same lines; each lane deletes its set as
# it lands. At 8cac7cf9; the Agent inbox lane (appendix A3) removes
# proposals-section.tsx's "e.g. 50" before L0 lands, so drop that row then.
_PENDING_EXAMPLES_L1: frozenset[tuple[str, str]] = frozenset(
    {
        ('app/new/page.tsx', 'e.g. https://boards.example.com/job/123'),
        ('app/referrals/page.tsx', 'e.g. Acme Corp'),
        ('app/referrals/page.tsx', 'e.g. Jane Doe'),
        ('app/referrals/page.tsx', 'e.g. Met at the AWS meetup'),
        ('app/referrals/page.tsx', 'e.g. https://example.com/careers'),
        ('components/job-tracking-url-field.tsx', 'https://…'),
        ('components/proposals/proposals-section.tsx', 'e.g. 50'),
        ('components/proposals/triage-actions.tsx', 'e.g. hiring freeze announced'),
        ('components/qa-tab.tsx', 'e.g. Why this team?'),
    }
)
_PENDING_EXAMPLES_L2: frozenset[tuple[str, str]] = frozenset(
    {
        ('app/jobs/[id]/tailor/[sessionId]/page.tsx', 'e.g. emphasize leadership, keep it to one page, lead with the fintech project…'),
        ('components/gap-analysis/gap-card.tsx', 'e.g. Data scientist who ships forecasting models to production'),
        ('components/gap-analysis/resolution-controls.tsx', 'e.g. Built the ingestion pipeline in Python and Airflow'),
        ('components/gap-analysis/resolution-controls.tsx', 'e.g. PySpark'),
    }
)
_PENDING_EXAMPLES_L3: frozenset[tuple[str, str]] = frozenset(
    {
        ('app/base-resumes/page.tsx', 'e.g. Data Scientist (1 page)'),
        ('app/templates/page.tsx', 'e.g. classic_serif'),
        ('components/base-resumes/new-base-resume-dialog.tsx', 'e.g. Lead with production ML work, senior in tone'),
        ('components/base-resumes/new-base-resume-dialog.tsx', 'e.g. Machine Learning Engineer'),
        ('components/resume-editor/contact-form.tsx', 'e.g. you@example.com'),
        ('components/resume-editor/experience-editor.tsx', 'e.g. Jan 2023'),
        ('components/resume-editor/experience-editor.tsx', 'e.g. Mar 2025'),
        ('components/resume-editor/extra-sections-editor.tsx', 'e.g. 2025'),
        ('components/resume-editor/extra-sections-editor.tsx', 'e.g. Publications'),
        ('components/resume-editor/extra-sections-editor.tsx', 'https://…'),
        ('components/resume-editor/instruct-sheet.tsx', 'e.g. Tighten the summary and lead with the platform work'),
        ('components/resume-health/finding-cards.tsx', 'e.g. this metric lives in the next bullet'),
        ('components/resume-health/finding-cards.tsx', 'e.g. this template is certified elsewhere'),
        ('components/resume-health/metric-ask-input.tsx', 'e.g. 5,000'),
        ('components/resume-health/metric-ask-input.tsx', 'e.g. 6 months'),
        ('components/resume-health/metric-ask-input.tsx', 'e.g. tickets'),
        ('components/role-category-picker.tsx', 'e.g. Data Scientist'),
    }
)
_PENDING_EXAMPLES_L4: frozenset[tuple[str, str]] = frozenset(
    {
        ('components/career/capture-box.tsx', 'e.g. This week I shipped…'),
        ('components/career/entity-detail.tsx', 'e.g. Acme Labs'),
        ('components/career/entity-detail.tsx', 'e.g. Jan 2025'),
        ('components/career/entity-detail.tsx', 'e.g. Mar 2025'),
        ('components/career/new-entity-dialog.tsx', 'e.g. AWS Solutions Architect'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Acme Corp'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Amazon Web Services'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Best Paper Award'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Fraud detection pipeline'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Jan 2025'),
        ('components/career/new-entity-dialog.tsx', 'e.g. MSc Computer Science'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Mar 2025'),
        ('components/career/new-entity-dialog.tsx', 'e.g. NeurIPS 2024'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Publications, Volunteer Work'),
        ('components/career/new-entity-dialog.tsx', 'e.g. Senior Data Scientist'),
        ('components/career/new-entity-dialog.tsx', 'e.g. University of Toronto'),
        ('components/career/profile-panel.tsx', 'e.g. ML Ops'),
    }
)
_PENDING_EXAMPLES_L5: frozenset[tuple[str, str]] = frozenset(
    {
        ('components/settings/auto-apply-section.tsx', 'e.g. Acme Corp'),
        ('components/settings/autofill-section.tsx', 'e.g. $120,000'),
        ('components/settings/autofill-section.tsx', 'e.g. 2 weeks'),
        ('components/settings/autofill-section.tsx', 'e.g. 2021'),
        ('components/settings/autofill-section.tsx', 'e.g. 2023'),
        ('components/settings/autofill-section.tsx', 'e.g. 3.8'),
        ('components/settings/autofill-section.tsx', 'e.g. Apt 4B'),
        ('components/settings/autofill-section.tsx', 'e.g. Asian'),
        ('components/settings/autofill-section.tsx', 'e.g. Data Science'),
        ('components/settings/autofill-section.tsx', 'e.g. Job board'),
        ('components/settings/autofill-section.tsx', 'e.g. Master of Science'),
        ('components/settings/autofill-section.tsx', 'e.g. Why do you want to work here?'),
        ('components/settings/job-preferences-section.tsx', 'e.g. $140,000'),
        ('components/settings/job-preferences-section.tsx', 'e.g. 6'),
        ('components/settings/job-preferences-section.tsx', 'e.g. Chicago, IL\nNew York, NY'),
        ('components/settings/llm-endpoint.tsx', 'e.g. http://host.docker.internal:11434/v1'),
        ('components/settings/models-section.tsx', 'e.g. AIza...'),
        ('components/settings/models-section.tsx', 'e.g. llama3.2:3b'),
        ('components/settings/models-section.tsx', 'e.g. sk-...'),
        ('components/settings/persona-section.tsx', 'e.g.\nVision: build data products that actually ship.\nStrengths: pragmatic ML, clear writing, fast prototyping.\nGoals: senior DS/MLE role on a product team.\nHow I work: bias to shipping, evidence over opinion.'),
        ('components/settings/quick-tailor-section.tsx', 'e.g. keep bullets under two lines'),
    }
)
_PENDING_EXAMPLES = _PENDING_EXAMPLES_L1 | _PENDING_EXAMPLES_L2 | _PENDING_EXAMPLES_L3 | _PENDING_EXAMPLES_L4 | _PENDING_EXAMPLES_L5
```
4. **`_MUST_SEE` (`:77-90`)** shrinks to the two real indirect prompts that stay:
```python
# Real indirect values the scanner must keep reading (a default parameter,
# a prop). The synthetic cases in test_scanner_reads_indirect_placeholder_values
# cover object fields, ternaries and joined constants.
_MUST_SEE = (
    ("components/ui/chip-input.tsx", "Add" + _ELLIPSIS),
    ("components/role-picker.tsx", "Search roles, or type your own" + _ELLIPSIS),
)
```
5. **`_allowed` and `_passes` (`:371-396`):**
```python
def _allowed(value: str) -> bool:
    return value == ""
…
def _passes(rel: str, value: str | None, expr: str) -> bool:
    if value is None:
        return (rel, expr) in _PASS_THROUGH
    return (
        _allowed(value)
        or ((rel, value) in _PROMPTS and value.endswith(_ELLIPSIS))
        or (rel, value) in _PENDING_EXAMPLES
    )
```
6. **Tests `:411-424`** become:
```python
def test_blank_fields_hold_no_text_but_a_named_prompt():
    bad = violations()
    assert not bad, "a placeholder other than a named search, composer or chip prompt:\n" + "\n".join(bad)


def test_pending_examples_only_shrink():
    stale = sorted(f"{rel} :: {value!r}" for rel, value in _PENDING_EXAMPLES - _seen())
    assert not stale, f"removed; delete these _PENDING_EXAMPLES rows: {stale}"


@pytest.mark.parametrize(
    "src,value",
    [
        ('const FIELDS = [{ key: "a", placeholder: "Search jobs…" }];', "Search jobs…"),
        ('function F({ placeholder = "Add…" }) { return <input placeholder={placeholder} />; }', "Add…"),
        ('<Input placeholder={open ? "Add…" : "Search…"} />', "Search…"),
        ('const P = ["Add", "more…"].join(" ");\n<Input placeholder={P} />', "Add more…"),
    ],
    ids=["object-field", "default", "ternary", "join"],
)
def test_scanner_reads_indirect_placeholder_values(src: str, value: str):
    scan = _Scan(src)
    seen = {hit[1] for at, tag in scan.sites if tag not in _SKIP_TAGS for hit in scan.values_at(at)}
    assert value in seen, seen


def test_scanner_still_reads_the_real_indirect_prompts():
    seen = _seen()
    missing = [
        f"{rel} :: {prefix!r}"
        for rel, prefix in _MUST_SEE
        if not any(path == rel and (value or "").startswith(prefix) for path, value in seen)
    ]
    assert not missing, "scanner missed:\n" + "\n".join(missing)
```
7. **`test_conventions_record_the_govuk_deviation` (`:446-455`)** becomes:
```python
def test_conventions_record_the_no_placeholder_rule():
    doc = (Path(__file__).resolve().parents[2] / "docs/frontend-conventions.md").read_text()
    assert "*Placeholder*: none in a blank field." in doc
    assert "The one exception is a short `…` prompt" in doc
    assert "fails closed" in doc
    for retired in ("prefixed `e.g.`", "This deviates from GOV.UK on purpose", "a placeholder may hold only an"):
        assert retired not in doc, retired
    assert re.search(r"optionality lives on the LABEL as a muted\s+\"\(optional\)\"", doc)
```
8. **`_PASS_THROUGH` (`:58-66`).** L3 drops the `placeholder` prop from `resume-editor/field.tsx` and
   `contact-form.tsx`, and L5 drops `placeholder` from the autofill field table, so their three rows become
   stale; each lane deletes its row(s) (`test_pass_through_list_is_current` fails until it does). The
   `role-picker.tsx` and `preview-thumbnail.tsx` rows stay.
9. **`_PROMPTS`**: unchanged, except that appendix A may move Applications' search into `ListSearch` (its
   open question 12); whichever lane does that moves the row.

The per-file functions that assert an `e.g.` today, and the lane that rewrites each (new text in that
group's pins): `test_question_constraint_is_a_hint` (L1), `test_file_import_name_defaults_in_a_hint`,
`test_metric_units_are_examples`, `test_demonstrate_skill_has_a_visible_label_and_no_placeholder`,
`test_experience_end_date_empty_means_current`, `test_template_slug_rule_stays_on_screen` (L3),
`test_summary_placeholder_is_an_example_and_the_consequence_stays_visible` (L2),
`test_new_entity_placeholders_are_examples`, `test_entity_dates_are_examples_not_the_ongoing_word`,
`test_profile_and_notes_statements_are_hints` (L4), `test_saved_key_is_a_hint_not_a_placeholder`,
`test_custom_answer_has_a_visible_label_not_a_placeholder` (L5). `test_retired_non_examples_are_not_placeholder_values`
stays (it only refuses old values).

10. **Delete `test_bare_examples_are_prefixed` (`:673-703`) in L0.** It asserts `e.g.` examples in seven
    files owned by four lanes; the pending sets now carry that obligation (a removed example must leave its
    set, and a new one fails the main test), so no lane has to edit a shared function.

Also `backend/tests/test_frontend_referrals.py:102-105` (L1):
```python
def test_create_form_has_no_placeholders():
    assert "placeholder=" not in _FORM
```

---

## D2. Jobs and tracking (lane L1)

Tracker, job page (header, Overview, Score and tailor, Resume, Q&A), `/new`, the Agent inbox words appendix A
leaves, Referrals, Analytics and the job market tab. Source: audit part 1 §2.1–2.5, §2.7–2.10. "After A" or
"after B" means the file's structure or other strings change there first; re-locate the quote.

### D2.1 Tracker (`app/applications/page.tsx`, `components/status-chip.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| app/applications/page.tsx:397 | "Every job you've captured, from saved to signed." | "Every job you've saved or applied to." | "captured" is internal; marketing tone (jargon, verbose) |
| app/applications/page.tsx:409, :522 | "New application" (header and empty-state buttons) | "Add job" | owner decision; `/new` makes a Saved job (inconsistent-term) |
| app/applications/page.tsx:421 | aria-label "Search applications" | "Search jobs" | the list holds saved jobs too. After B (the toolbar moves into `ListToolbar`, or `ListSearch` per A3) |
| app/applications/page.tsx:422 | placeholder "Search company or role…" | keep | a named search prompt (`_PROMPTS`) |
| app/applications/page.tsx:94 | Agent-inbox filter option "Proposed" | "To review" | the same rows sit in the inbox's To review lane (inconsistent-term) |
| app/applications/page.tsx:508 | "Capture a job description to get started." | "Add a job to get started." | jargon |
| app/applications/page.tsx:542 | column "Base" | "Resume" | bare "Base" (jargon) |
| app/applications/page.tsx:154 | dates "2026-09-14" (Applied, Added) | "Sep 14", with the year when it is not this year | ISO reads as machine output. **[behaviour]** display format only; add `formatShortDate` to `lib/format-date.ts` beside `formatAbsoluteDateTime` |
| app/applications/page.tsx:666 | "{company} · {title}. The job description and extracted metadata will be removed." | "{company} · {title}. This deletes the job and everything saved with it." | jargon, passive (tone) |
| app/applications/page.tsx:682 | "{company} · {title}. Its tailored resume, Q&A history, and rendered PDF will be removed. The job stays saved." | "{company} · {title}. This deletes its tailored resume, answers and PDF. The job stays saved." | one wording per object; keep "The job stays saved." (jargon, tone) |
| app/applications/page.tsx:209, :220, :234, :245 | `toast.error(err.message)` | `couldnt("change the status", err)`, `couldnt("delete the application", err)`, `couldnt("queue the job", err)`, `couldnt("delete the job", err)` | D1.3 (tone) |
| app/applications/page.tsx:230, :461, :590-593, :636 | toast, "Agent lane", the Bot mark, "Queue for agent apply" | appendix A5 rows 15–18 and A9 | after A; no further change |
| components/status-chip.tsx:58 | `statusLabel`: `?? status` | `?? "Unknown"` | a status the map lacks printed its key (raw-value) |
| components/status-chip.tsx:133 | proposal chip "Submitted" | "Applied" | owner chips: Proposed, Queued, Approved, Applied, Skipped |
| components/status-chip.tsx:134 | proposal chip "Submission uncertain" | "Check if sent" | says what to do (jargon, tone) |
| components/status-chip.tsx:137 | `proposalStatusLabel`: `?? status` | `?? "Unknown"` | raw-value |

### D2.2 Job page header and Overview (`app/jobs/[id]/page.tsx`, `components/job-*.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| app/jobs/[id]/page.tsx:78 | tab "Score &amp; Tailor" | "Score and tailor" | case, ampersand; same text at the gap page :656, :660 (D3) and `job-extraction-summary.tsx:103` |
| app/jobs/[id]/page.tsx:143 | toast "Job re-extracted" | "Job details refreshed" | jargon |
| app/jobs/[id]/page.tsx:147, :160, :185 | `toast.error(err.message)` | `couldnt("refresh the job details", err)`, `couldnt("queue the job", err)`, `couldnt("delete the job", err)` | D1.3 |
| app/jobs/[id]/page.tsx:195 | confirm title "Re-run JD extraction?" | "Refresh the job details?" | jargon |
| app/jobs/[id]/page.tsx:197 | "All extracted fields and skill rows for this job will be replaced." | "This reads the job description again and replaces the job details and skills." | jargon, passive |
| app/jobs/[id]/page.tsx:198 | confirm label "Re-extract" | "Refresh details" | jargon |
| app/jobs/[id]/page.tsx:208 | "Re-extracting…" / "Re-extract" | "Refreshing…" / "Refresh details" | jargon |
| app/jobs/[id]/page.tsx:221 | `detail={(error as Error)?.message}` | `detail={errorDetail(error)}` | D1.3 |
| app/jobs/[id]/page.tsx:228 | "Back to Applications" | "Back to applications" | matches `:316` (case) |
| app/jobs/[id]/page.tsx:338 | subtitle joins raw `job.work_mode`, `job.level` | run both through `humanizeEnum` | printed "onsite · senior" (raw-value) |
| app/jobs/[id]/page.tsx:362 | A5 row 8: "Accepted. A connected agent can apply to it now." | "Queued. A connected agent can apply to it now." | after A; owner chips say Queued for this state |
| app/jobs/[id]/page.tsx:368 | button "Accept" | "Queue" | the result is a Queued chip (inconsistent-term). After A |
| app/jobs/[id]/page.tsx:420 | icon label "Open application URL" | "Open job link" | one name for the field |
| app/jobs/[id]/page.tsx:444 | "Its application, ATS scores, tailoring sessions, and Q&A history will go with it." | "This also deletes its application, ATS scores, gap analyses and answers." | jargon |
| app/jobs/[id]/page.tsx:503 | "See before/after comparison on the Resume tab" | "Compare with your base resume on the Resume tab" | slash, verbose |
| components/job-extracted-fields.tsx:94-96 | "{n} yrs", "{n}–{m} yrs", "{n}+ yrs", "up to {n} yrs" | "years" in each | abbreviation |
| components/job-extracted-fields.tsx:108-112 | `ENUM_LABELS` = full_time, part_time, on_site | add `onsite: "On-site"` (the stored value; drop `on_site`), `citizen_or_gc_required: "Citizen or green card required"`, `no_sponsorship: "No sponsorship"`, `sponsorship_available: "Sponsorship available"`, `stem_opt_ok: "STEM OPT accepted"`, `unstated: "Not stated"`, `unknown: "Not stated"` | **bug** (D10.4): the map keyed `on_site`, but `extract_jd.txt:10` and `job_preferences.py:80` store `onsite`, so every on-site job read "Onsite" (raw-value) |
| components/job-extracted-fields.tsx:233, :294 | "Pay scale linked" | "See pay range" | a link names where it goes |
| components/job-extracted-fields.tsx:240 | chip title "Role family" | "Role" | one name (Analytics said "Role category") |
| components/job-extracted-fields.tsx:257 | "Extracted job description" | "Job description" | jargon |
| components/job-extracted-fields.tsx:261 | "Extracted fields" | "Job details" | jargon |
| components/job-extracted-fields.tsx:304 | "Years experience" | "Years of experience" | grammar |
| components/job-extracted-fields.tsx:363 | "Hide raw JD" / "Show raw JD" | "Hide full job description" / "Show full job description" | JD |
| components/job-knockout-card.tsx:15 | "Knock-out conflict" | "You may not qualify" | jargon. After C (C3 changes this file's link) |
| components/job-knockout-card.tsx:16 | "A stated requirement contradicts your profile." | "The job lists a requirement your profile doesn't meet." | jargon |
| components/job-knockout-card.tsx:21 | "Stated requirements clear" | "You meet the listed requirements" | jargon |
| components/job-knockout-card.tsx:23 | "Work authorization, OPT, salary, and experience match your profile where the posting states them." | "Your work authorization, OPT, pay and experience match what the job lists." | posting, verbose |
| components/job-knockout-card.tsx:28 | "Profile can’t answer a stated requirement" | "Your profile is missing an answer" | curly apostrophe, verbose |
| components/job-knockout-card.tsx:29 | "Fill the missing answer in your profile to screen this posting." | "Add it to your profile to check this job." | posting, jargon |
| components/job-knockout-card.tsx:35 | "No screening requirements stated" | "No requirements listed" | jargon |
| components/job-knockout-card.tsx:37 | "The posting states no work-authorization, OPT, salary, or experience screens — that’s absence of signal, not a green light." | "The job doesn't mention work authorization, OPT, pay or experience. That doesn't mean you qualify." | em dash; keep the caution |
| components/job-knockout-card.tsx:99 | "Complete your autofill profile" | "Complete your profile" | the link lands on Profile › Autofill (after C3) |
| components/job-knockout-card.tsx:89 | `KnockoutCheck.message` shown verbatim | unchanged here; D9 rewrites the server text | |
| components/job-tracking-url-field.tsx:23 | label "Application URL" | "Job link" | three names for one field |
| components/job-tracking-url-field.tsx:24 | hint "Job posting or employer portal. Open it to check status." | "The job post or employer portal where you check your status." | posting |
| components/job-tracking-url-field.tsx:92 | placeholder "https://…" | remove | owner: the URL cue goes; the hint names it |
| components/job-tracking-url-field.tsx:54 | `toast.error(err.message)` | `couldnt("save the job link", err)` | D1.3 |
| components/proposals/proposal-agent-panel.tsx:87 | Reason shows `data.reason` ("declined by user") | map through `REASON_LABEL` (Skip dialog's labels) | the stored value leaked (raw-value). After A (A9 rewrites this card) |
| components/proposals/proposal-agent-panel.tsx:132 | "Evidence" | "Screenshots" | they are step screenshots (jargon). After A |
| components/proposals/proposal-agent-panel.tsx:45 | `detail={(error as Error)?.message}` | `detail={errorDetail(error)}` | D1.3. After A |

### D2.3 Score and tailor tab (`components/ats-score-panel.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| components/ats-score-panel.tsx:~416 (new line above the cards, and in the empty state at :400) | none | `<p className="text-muted-foreground text-sm">An ATS score (0 to 100) is how an applicant tracking system would rate each resume for this job.</p>` | owner: spell out "ATS score" once where it first appears. **[behaviour]** one new line |
| components/ats-score-panel.tsx:39 | "Placement &amp; recency" | "Recent experience" | jargon, ampersand; same at `ats-compare-panel.tsx:25` |
| components/ats-score-panel.tsx:40 | "Semantic fit" | "Overall match" | jargon; same at `ats-compare-panel.tsx:26` |
| components/ats-score-panel.tsx:41 | "Title" | "Job title" | ambiguous alone |
| components/ats-score-panel.tsx:133-135 | "Only {m} of {n} JD skills recognized ({p}% coverage)." | "We recognized only {m} of the job's {n} skills ({p}%)." | JD; the gap page says the same (D3) |
| components/ats-score-panel.tsx:148 | "Resume gap analysis ({n} resolved)" | "Continue gap analysis ({n} done)" | "Resume" read as the noun; one word for handled gaps |
| components/ats-score-panel.tsx:172 | "Analyze gaps &amp; tailor" | "Find gaps and tailor" | ampersand |
| components/ats-score-panel.tsx:183 | "Applied with base resume" | "Mark applied without tailoring" | a button is a verb |
| components/ats-score-panel.tsx:275 | toast "Recorded as applied with the base resume" | "Marked as applied" | verbose |
| components/ats-score-panel.tsx:286 | confirm "Applied with base resume?" | "Mark as applied without tailoring?" | |
| components/ats-score-panel.tsx:288-290 | "Records an application using {name} as-is and marks it Applied. Any tailored draft for this job and base is replaced by the base content (version history keeps every prior draft), and any open agent proposal for this job is closed." (A5 row 33 changes its last clause) | "This marks the job Applied with {name}, unchanged. It replaces any tailored draft (Version history keeps it) and closes any open proposal in your Agent inbox for this job." | verbose, as-is; keeps all three consequences and A5's words |
| components/ats-score-panel.tsx:350 | "Couldn't load ATS scores." | keep | owner: "ATS score" is the term |
| components/ats-score-panel.tsx:351 | `detail={(scores.error as Error)?.message}` | `detail={errorDetail(scores.error)}` | D1.3 |
| components/ats-score-panel.tsx:390-392 | "Import the resumes you already have. Each becomes a base resume, and this job is scored against all of them." | "Import your resumes to score this job against each one." | verbose |
| components/ats-score-panel.tsx:402 | "No ATS scores yet." | keep | the lead line above now explains it; pin `test_frontend_query_error_states.py:80` unchanged |
| components/ats-score-panel.tsx:406 | "Scoring…" / "Run ATS scoring" | "Scoring…" / "Score my resumes" | jargon |
| components/ats-score-panel.tsx:425 | "Re-scoring…" / "Re-score base resumes" | "Updating scores…" / "Update scores" | re-score |
| components/ats-score-panel.tsx:246, :258, :281 | `toast.error(err.message)` | `couldnt("score your resumes", err)`, `couldnt("start the gap analysis", err)`, `couldnt("mark the job applied", err)` | D1.3 |
| components/ats-score-panel.tsx:121, :129 | `gate_warnings`, `coverage_warning` shown verbatim | unchanged here; D9 | |

### D2.4 Resume tab (`components/application-panel.tsx`, `components/ats-compare-panel.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| components/application-panel.tsx:144 | "Its Q&A history and rendered PDF will be removed. The underlying job is preserved." | "This deletes its tailored resume, answers and PDF. The job stays saved." | same object as the tracker's confirm; it left out the tailored resume |
| components/application-panel.tsx:284 | toast "PDF generated" | "PDF ready" | one PDF verb |
| components/application-panel.tsx:294 | "PDF ready. Review it below or download it." | "Your PDF is ready." | verbose |
| components/application-panel.tsx:296 | "Draft ready. Generate a PDF to preview and download it here." | "Draft ready. Create a PDF to preview it." | Create PDF |
| components/application-panel.tsx:297 | "No tailored resume yet. Run the Fit workflow to create a draft." | "No tailored resume yet. Start on the Score and tailor tab." | "Fit workflow" is a stale name |
| components/application-panel.tsx:327 | "Generating…" / "Regenerate PDF" / "Generate PDF" | "Creating…" / "Update PDF" / "Create PDF" | one PDF verb |
| components/application-panel.tsx:360 | "The PDF preview is unavailable. Regenerate the PDF to try again." | "Couldn't show the preview. Update the PDF to try again." | error form |
| components/application-panel.tsx:366 | "No PDF yet. Generate one to preview it here." | "No PDF yet." | repeats `:296` |
| components/application-panel.tsx:367 | "Build a tailored draft before generating a PDF." | "No tailored resume yet." | repeats `:297`; a third PDF verb |
| components/application-panel.tsx:85, :99, :286 | `toast.error(err.message)` | `couldnt("update the application", err)`, `couldnt("delete the application", err)`, `couldnt("create the PDF", err)` | D1.3 |
| components/ats-compare-panel.tsx:25-26 | "Placement &amp; recency", "Semantic fit" | "Recent experience", "Overall match" | as D2.3 |
| components/ats-compare-panel.tsx:75, :86 | badges "matched", "missing" | "Matched", "Missing" | case |
| components/ats-compare-panel.tsx:78 | `row.placement` printed | map: dual → "Skills and experience", experience_only → "Experience", skills_list_only → "Skills list only", undated_only → "Undated item", extra_only → "Other section", credential_only → "Certification" (one `PLACEMENT_LABELS` in `lib/`, shared with the gap card, D3) | raw keys (`backend/app/services/ats/layers.py:44`) |
| components/ats-compare-panel.tsx:89 | `row.fix_hint` printed (`absent`, `mirror_wording`, `dual_place`, `resurface_recent`) | map: absent → "Add it", mirror_wording → "Use the job's words", dual_place → "Show it in your experience too", resurface_recent → "Show a recent use" | raw-value |
| components/ats-compare-panel.tsx:130 | toast "Both phases re-scored" | "ATS scores updated" | re-score |
| components/ats-compare-panel.tsx:139 | toast "Tailored resume re-scored" | "ATS score updated" | re-score |
| components/ats-compare-panel.tsx:155, :188 | "ATS before / after" | "ATS score before and after" | slash |
| components/ats-compare-panel.tsx:171 | "Re-score both phases" | "Update both scores" | re-score |
| components/ats-compare-panel.tsx:199 | "Re-scoring…" / "Re-score" | "Updating…" / "Update score" | re-score |
| components/ats-compare-panel.tsx:234 | column "JD skill" | "Skill" | JD |
| components/ats-compare-panel.tsx:271 | "No skill rows to compare." | "No skill changes." | `skill_diff` holds only changed rows |
| components/ats-compare-panel.tsx:133, :142 | `toast.error(err.message)` | `couldnt("update the scores", err)`, `couldnt("update the score", err)` | D1.3 |

### D2.5 Q&A tab (`components/qa-tab.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| components/qa-tab.tsx:78 | thrown "No questions to ask" | "Type at least one question." | says what to do |
| components/qa-tab.tsx:89 | toast "Answers generated" | "Answers ready" | |
| components/qa-tab.tsx:105 | toast "Cover letter generated" | "Cover letter ready" | |
| components/qa-tab.tsx:194 | card title "Ask questions" | "Application questions" | you paste the form's questions |
| components/qa-tab.tsx:201 | aria-label "Questions to ask" | "Application questions" | |
| components/qa-tab.tsx:203 | placeholder "e.g. Why this team?" | remove | owner rule; the hint "One question per line." stays |
| components/qa-tab.tsx:245 | "Generating…" / "Generate cover letter" | "Writing…" / "Write cover letter" | matches "Answer questions" |
| components/qa-tab.tsx:257 | "Couldn't load Q&A." | "Couldn't load your answers." | |
| components/qa-tab.tsx:258 | `detail={(error as Error)?.message}` | `detail={errorDetail(error)}` | D1.3 |
| components/qa-tab.tsx:263 | "No Q&amp;A entries yet." | "No answers yet." | entry |
| components/qa-tab.tsx:288 | confirm "Delete this Q&A entry?" | "Delete this answer?" | entry |
| components/qa-tab.tsx:291 | "The question and its answer will be removed from history." | "This deletes the question and its answer." | passive |
| components/qa-tab.tsx:292 | "The {kind} will be removed from history." (fallback "entry") | "This deletes the cover letter." | passive, entry |
| components/qa-tab.tsx:390 | icon label "Copy to clipboard" | "Copy" | verbose |
| components/qa-tab.tsx:400 | icon label "Render PDF" | "Create PDF" | render |
| components/qa-tab.tsx:430 | icon label "Delete entry" | "Delete" | entry |
| components/qa-tab.tsx:92, :108, :115, :128, :147, :187 | `toast.error(err.message)` | `couldnt("answer the questions", err)`, `couldnt("write the cover letter", err)`, `couldnt("delete the answer", err)`, `couldnt("write a new version", err)`, `couldnt("save the cover letter", err)`, `couldnt("create the PDF", err)` | D1.3 |
| components/qa-tab.tsx:147 | toast "Saved" | "Cover letter saved" | a toast names its object |

### D2.6 Add a job (`app/new/page.tsx`, `components/job-extraction-summary.tsx`)

`app/new/page.tsx` is also edited by appendix C3 (the Add API key link): **after C**.

| file:line | current | new | why (category) |
|---|---|---|---|
| app/new/page.tsx:89 | title "New application" | "Add a job" | owner decision |
| app/new/page.tsx:69 | toast "Already tracked. This job matches one you saved earlier." | "You already saved this job." | verbose |
| app/new/page.tsx:71 | toast "Job extracted. Listed under Saved." | "Job saved." | jargon |
| app/new/page.tsx:74 | `toast.error(err.message)` | `couldnt("save the job", err)` | D1.3 |
| app/new/page.tsx:96 | "Extract reads the posting with a model, so it needs a provider API key." | "Saving a job reads its description with AI, so it needs an API key." | jargon ("API key" matches the Settings field) |
| app/new/page.tsx:122 | label "Source URL" | "Job link" | one name |
| app/new/page.tsx:125 | placeholder "e.g. https://boards.example.com/job/123" | remove | owner rule |
| app/new/page.tsx:142 | "Extracting…" / "Extract job" | "Saving…" / "Save job" | owner decision |
| app/new/page.tsx:146 | "Add an API key to extract." | remove (the `<p>` renders only when a key exists) | repeats the amber notice, which the disabled button already names in `aria-describedby` |
| app/new/page.tsx:147 | "The job is listed under Saved. Scoring comes next." | "Saved jobs appear in Applications, ready to score." | tense before anything is saved |
| components/job-extraction-summary.tsx:52 | "Already tracked. This job matches one you saved earlier." | "You already saved this job." | duplicate of the toast |
| components/job-extraction-summary.tsx:56 | "Extracted. Appears under Saved" | "Saved to Applications." | jargon, no stop |
| components/job-extraction-summary.tsx:103 | "Score &amp; tailor" | "Score and tailor" | ampersand |

### D2.7 Agent inbox words appendix A leaves (`components/proposals/*`), after A

A1–A9 rename the page, the error title, the empty state, the toolbar, the Role filter's raw keys (A3; the
bug the audit found) and the by-line. These rows are the owner's lane and chip words, which A does not
change.

| file:line | current | new | why (category) |
|---|---|---|---|
| components/proposals/proposals-section.tsx:497 | lane "Triage · {n}" | "To review · {n}" | owner lanes |
| components/proposals/proposals-section.tsx:499 | "Nothing pending triage." | "Nothing to review." | jargon |
| components/proposals/proposals-section.tsx:565 | lane "In flight · {n}" | "Applying · {n}" | owner lanes; holds Approved chips |
| components/proposals/proposals-section.tsx:764 | title "Extraction flagged this posting as disqualifying for OPT" | "This job may not accept OPT" | jargon; keep "OPT" |
| components/proposals/proposals-section.tsx:772 | "possible duplicate" | "Possible duplicate" | case |
| components/proposals/proposals-section.tsx:777 | row meta joins raw `job.work_mode` | `humanizeEnum(job.work_mode)` | printed "onsite" |
| components/proposals/proposals-section.tsx:785 | "{baseName} · {score}" | "{baseName} · ATS score {score}" | an unlabeled number |
| components/proposals/proposals-section.tsx:799 | row icon label "Accept" | "Queue" | the result is Queued |
| components/proposals/triage-actions.tsx:40-44 | reason labels "skipped by you", "no longer relevant", "position closed", "duplicate" | "Not interested", "No longer relevant", "Position closed", "Duplicate" | display only; the stored values stay (agent vocabulary). A reason "skipped by you" for skipping was circular |
| components/proposals/triage-actions.tsx:103 | fallback "already terminal" | "already closed" | jargon |
| components/proposals/triage-actions.tsx:105 | A5: "{n} of {m} could not be {verb}: {sample}" | "Couldn't {verb} {n} of {m}. {errorDetail(sample) ?? "Try again."}" with verb "queue" or "skip" | "Could not"; a raw server detail |
| components/proposals/triage-actions.tsx:75, :108, :129 | `toast.error(err.message)` | `couldnt("update the proposal", err)`, `couldnt("update the proposals", err)`, `couldnt("delete the proposal", err)` | D1.3 |
| components/proposals/triage-actions.tsx:116 | "Its evidence screenshots are removed. Submitted proposals cannot be deleted." | "This also deletes its screenshots." | the second sentence never applies (Delete is offered only where it works) |
| components/proposals/triage-actions.tsx:159 | "Skip this posting?" | "Skip this job?" | posting |
| components/proposals/triage-actions.tsx:161 | "Skips only this posting. The company is not affected." | "Other jobs at this company aren't affected." | posting, passive |
| components/proposals/triage-actions.tsx:185 | "Custom reason · optional" | `<Label optional>Other reason</Label>` | "Custom" reads as a setting; D1.2 |
| components/proposals/triage-actions.tsx:189 | placeholder "e.g. hiring freeze announced" | remove | owner rule |
| components/proposals/triage-actions.tsx:245 | bulk bar "Accept" | "Queue" | the result is Queued |
| components/analytics/agent-pipeline-card.tsx:14 | stage "Captured" | "Found" | jargon; the funnel moved here (A2) |
| components/analytics/agent-pipeline-card.tsx:16 | stage "Accepted" | "Queued" (A5 row 32 does this) | after A; no further change |
| components/analytics/agent-pipeline-card.tsx:18 | stage "Submitted" | "Applied" | owner chips |
| components/analytics/agent-pipeline-card.tsx:40 | "Agent pipeline" | keep | A5 keeps it as a proper name |
| components/analytics/agent-pipeline-card.tsx:41 | "What the hunt swarm captured and how far each stage got." | A5 row 31: "Jobs your connected agents saved, and how far each one got." | after A; no further change |
| components/analytics/agent-pipeline-card.tsx:68 | "Cap {a}/{b} today · {r} remaining" | keep A2's "Cap today {a}/{b}" | the owner's words (A2) |
| components/proposals/funnel-strip.tsx (all rows) | | dropped | A2 deletes the file; its words live in `agent-pipeline-card.tsx` (rows above) |

### D2.8 Referrals (`app/referrals/page.tsx`)

B7 edits `:325-327` (the sticky header) only; these rows are elsewhere. **After B.**

| file:line | current | new | why (category) |
|---|---|---|---|
| app/referrals/page.tsx:167, :200 | description "A company where someone can refer you." | remove | repeats the page subtitle |
| app/referrals/page.tsx:269 | placeholder "e.g. Acme Corp" | remove | owner rule |
| app/referrals/page.tsx:274, :330, :520 | "Careers URL" (label, column, aria-label) | "Careers page" | jargon |
| app/referrals/page.tsx:280 | placeholder "e.g. https://example.com/careers" | remove | owner rule |
| app/referrals/page.tsx:292, :528 | placeholder "e.g. Jane Doe" | remove; drop the `min-w-32` that existed to fit it at `:528` | owner rule |
| app/referrals/page.tsx:304, :539 | placeholder "e.g. Met at the AWS meetup" | remove | owner rule |
| app/referrals/page.tsx:333 | column "Apps" | "Applications" | abbreviation |
| app/referrals/page.tsx:396 | "Referral for {c} will be removed. Applications already linked to it are unaffected." | "Applications linked to it won't change." | the title already says what is deleted |
| app/referrals/page.tsx:438 | icon label "Edit" | "Edit referral" | matches "Delete referral" (`:444`) |
| app/referrals/page.tsx:118, :389, :487 | `toast.error(err.message)` | `couldnt("add the referral", err)`, `couldnt("delete the referral", err)`, `couldnt("save the referral", err)` | D1.3 |
| app/referrals/page.tsx:146 | `detail={(referrals.error as Error \| null)?.message}` | `detail={errorDetail(referrals.error)}` | D1.3 |

### D2.9 Analytics and the job market tab

| file:line | current | new | why (category) |
|---|---|---|---|
| app/analytics/page.tsx:171 | "Your job search, quantified." | "How your job search is going." | marketing tone |
| app/analytics/page.tsx:141 | filter "Role category" | "Role" | one name |
| app/analytics/page.tsx:147 | Level options printed raw | `humanizeEnum` | raw-value |
| app/analytics/page.tsx:150 | filter "Employment", options raw (`full_time`) | "Employment type", `humanizeEnum` | raw-value |
| app/analytics/page.tsx:179 | tab "Gaps &amp; growth" | "Skill gaps" | ampersand; also the button at `analytics-overview.tsx:175` |
| app/analytics/page.tsx:193-194 | "Skills ranked by how often they appear. Top 30% are mandatory; the rest follow below." | "Skills ranked by how many jobs ask for them." | **bug** (D10.3): the top 30% is by frequency, not a requirement |
| app/analytics/page.tsx:205 | "Skill coverage by role category" | "Skills by role" | |
| app/analytics/page.tsx:214 | "Role mix over time" | "Roles over time" | |
| app/analytics/page.tsx:229 | "ATS score over time" | keep | first ATS mention on this tab; the description below spells it out |
| app/analytics/page.tsx:230-231 | "Weekly average ATS composite. Tailored resumes are solid lines, base resumes dashed." | "Weekly average ATS score (how an applicant tracking system rates a resume for a job)." | composite; the chart caption keeps the line key |
| app/analytics/page.tsx:241 | "Base → tailored lift" | "Score gain from tailoring" | owner: Score gain |
| app/analytics/page.tsx:242-243 | "Average ATS composite before and after tailoring, by role category." | "Average ATS score before and after tailoring, by role." | composite |
| app/analytics/page.tsx:253 | "Fit score distribution" | "ATS scores by resume" | fit score |
| app/analytics/page.tsx:267-268 | "Split by what would actually fix them: skills to learn vs. evidence to move. From your best-scoring resume per job. Wording-only mismatches sit in a footnote — they don’t move your score." | "Skills to learn, and skills to show better. Based on your best-scoring resume for each job." | vs., em dash, evidence |
| components/analytics/analytics-overview.tsx:85, :148, :189 | raw error message | "Couldn't load this." + `errorDetail(error) ?? "Try again."` and a Try again button | tone; no retry |
| components/analytics/analytics-overview.tsx:90 | "Submitted · last 7 days" | "Applied · last 7 days" | owner chips; pin `test_frontend_query_error_states.py:66` |
| components/analytics/analytics-overview.tsx:95 | "In flight" | "In progress" | owner decision; also `base-summary-cards.tsx:103` |
| components/analytics/analytics-overview.tsx:97 | "applied · interviewing · offered" | "Applied, interviewing or offer" | the chip labels |
| components/analytics/analytics-overview.tsx:100 | "At interview stage+" | "Reached interviews" | a symbol for words |
| components/analytics/analytics-overview.tsx:108 | "currently, of {n} submitted" | "of {n} applications" | grammar |
| components/analytics/analytics-overview.tsx:109 | "no submissions yet" | "No applications yet" | |
| components/analytics/analytics-overview.tsx:113 | "Avg tailoring lift" | "Average score gain" | owner: Score gain |
| components/analytics/analytics-overview.tsx:115 | "ATS points over {n} tailored" / "nothing tailored yet" | "points across {n} tailored resumes" / "Nothing tailored yet" | |
| components/analytics/analytics-overview.tsx:152 | "Score some jobs to see what you keep lacking." | "Score a few jobs to see which skills come up most." | tone |
| components/analytics/analytics-overview.tsx:182 | "Quick wins from your Career KB" | "Quick wins from your career history" | KB |
| components/analytics/analytics-overview.tsx:192-193 | "No in-demand skills are sitting unused in your Career KB right now." | "No unused skills in your career history match what jobs ask for." | KB |
| components/analytics/analytics-overview.tsx:199-200 | chip "in your KB" | "In your career history" | KB |
| components/analytics/analytics-overview.tsx:211 | "See all build areas" | "See all skill gaps" | jargon |
| components/analytics/activity-chart.tsx:67 | aria-label "Activity granularity" | "Group by" | jargon |
| components/analytics/activity-chart.tsx:89 | "No application activity in this window yet." | "No activity in this period yet." | |
| components/analytics/activity-chart.tsx:97 | x ticks "09-14" | "Sep 14" | date format. **[behaviour]** display only |
| components/analytics/base-summary-cards.tsx:58 | `row.display_name ?? row.slug` | `row.display_name ?? baseResumeLabel(row.slug, …)` | raw slug fallback |
| components/analytics/base-summary-cards.tsx:73 | "Health {grade}" / title "Health {n}/100" | "Health {grade}" / title "Health score {n} of 100" | keep "Health" (the feature name, D4); ratio |
| components/analytics/base-summary-cards.tsx:84 | "Avg base ATS" | "Average ATS score" | abbreviation |
| components/analytics/base-summary-cards.tsx:92 | "Avg lift" | "Average score gain" | |
| components/analytics/base-summary-cards.tsx:101 | "{n} sent · {m} total" | "{n} applied · {m} total" | one word |
| components/analytics/base-summary-cards.tsx:103 | "In flight" | "In progress" | owner decision |
| components/analytics/gap-tiers-panel.tsx:28 | "Not in your KB" | "Not in your career history" | KB |
| components/analytics/gap-tiers-panel.tsx:29 | title "No Career KB evidence for this skill." | "Not in your career history." | KB, evidence |
| components/analytics/gap-tiers-panel.tsx:33 | "In your KB" | "In your career history" | KB |
| components/analytics/gap-tiers-panel.tsx:34 | title "Evidence exists in your Career KB. Send it to a resume." | "It's in your career history. Add it to a resume." | KB |
| components/analytics/gap-tiers-panel.tsx:38 | "Ported before" | "Used before" | port |
| components/analytics/gap-tiers-panel.tsx:99-100 | "No true skill gaps — nothing here is a skill you have to go learn. The work is in Surface below: documentation, not learning." (and the variant without the last sentence) | "No skills to learn. The ones below are already yours and just need showing." | em dash |
| components/analytics/gap-tiers-panel.tsx:105 | tier "Build" | "Skills to learn" | jargon |
| components/analytics/gap-tiers-panel.tsx:106 | "Nothing on your resume and nothing in your Career KB. These are the ones you actually have to go learn or earn." | "Not on your resumes or in your career history." | KB, verbose |
| components/analytics/gap-tiers-panel.tsx:113 | tier "Surface" | "Skills to show" | jargon |
| components/analytics/gap-tiers-panel.tsx:114 | "Not skills to learn — the evidence is usually already there, in your Career KB or on a resume. Each row names what it actually needs." | "You likely have these already. Each row says what's needed." | em dash, KB |
| components/analytics/gap-tiers-panel.tsx:173 | `row.requirement_level` lowercase key | "Required" / "Preferred" / "Mentioned" | raw-value |
| components/analytics/gap-tiers-panel.tsx:198-199 | "Missing in {n} jobs · ≈{x} ATS pts each" | "Missing in {n} jobs · about {x} points each" | abbreviation |
| components/analytics/gap-tiers-panel.tsx:202 | " · evidence: {names}" | " · in: {names}" | evidence |
| components/analytics/gap-tiers-panel.tsx:217-219 | "Wording only: {n} skills where your resume already matches at full credit and only the JD’s literal token is missing. Adding it will not change your score — quick tailor mirrors these for you while “Mirror JD wording” is on." | "Wording only: {n} skills your resume already covers. Using the job's exact words won't change your ATS score. Quick tailor adds them when “Use the job description's wording” is on." | JD, em dash, case; the setting's new name is D6 |
| components/analytics/autofill-coverage-card.tsx:56, :199 | `row.kind` printed (tooltip, axis, table) | map field kinds to words (`text` → "Text", `select` → "Choice", `radio` → "Choice", `checkbox` → "Checkbox", `file` → "File upload", `date` → "Date", other → "Other") | raw-value |
| components/analytics/autofill-coverage-card.tsx:58 | "{p}% · {s} filled or corrected vs {f} failed" | "{p}% · {s} filled, {f} missed" | vs |
| components/analytics/autofill-coverage-card.tsx:98-101 | A5 row 45: "This deletes {n} recorded field shapes across {m} sites, including which sites they were seen on and when. It cannot be undone. Capture stays on. Turn it off in the Companion's ⋯ menu." | "This deletes what was recorded about {n} form fields on {m} sites. You can't undo this. Recording stays on. Turn it off in Companion's ⋯ menu." | after A; jargon, "cannot"; keep "can't undo" and "stays on" |
| components/analytics/autofill-coverage-card.tsx:120 | A5 row 46: "What real application forms ask, and where the Companion's fill pipeline fails." | "What application forms ask, and where Companion's autofill misses." | after A; jargon |
| components/analytics/autofill-coverage-card.tsx:124 | A5 row 47: "No telemetry yet. Fill an application with the Companion to start capturing." | "No data yet. Use Companion on an application form to start." | after A; jargon |
| components/analytics/autofill-coverage-card.tsx:142 | "Observations" | "Times seen" | jargon |
| components/analytics/autofill-coverage-card.tsx:184 | column "Kind" | "Type" | |
| components/analytics/autofill-coverage-card.tsx:188 | column "Failure share" | "Missed" | jargon |
| components/analytics/autofill-coverage-card.tsx:231 | "New-field share, last {n} capture sessions." | "New questions, last {n} forms." | jargon; the server `recommendation` after it is D9 |
| components/analytics/autofill-coverage-card.tsx:84 | `toast.error(err.message)` | `couldnt("clear the data", err)` | D1.3 |
| components/charts/top-skills-chart.tsx:26 | "{n} job descriptions" | "{n} jobs" | |
| components/charts/top-skills-chart.tsx:37 | "…· Rank #{r} · directional only" | "…· Rank {r} · small sample" | jargon (7 sites say "directional only"; all below) |
| components/charts/top-skills-chart.tsx:91 | "No skills in this tier." | "No skills here." | |
| components/charts/top-skills-chart.tsx:122 | "No data yet." also shown on a failed fetch | a failed fetch shows `LoadErrorState` with Try again | a failure read as empty. **[behaviour]** |
| components/charts/top-skills-chart.tsx:129 | subtitle "Mandatory" | "Most asked for" | **bug** (D10.3) |
| components/charts/top-skills-chart.tsx:139 | "Rest" | "Others" | |
| components/charts/heatmap-chart.tsx:61-62 | "Top-30% skills by rank; cell = % of jobs in that role mentioning the skill." | "Share of jobs in each role that ask for each skill." | semicolon, jargon |
| components/charts/fit-distribution-chart.tsx:22 | buckets "0-20" … "80-100" | "0–20" … "80–100" | en dash for ranges |
| components/charts/fit-distribution-chart.tsx:59 | "Some resumes have fewer than 5 scores · those series are directional only." | "Some resumes have fewer than 5 scores, so treat those lines as rough." | |
| components/charts/ats-over-time-chart.tsx:110-111 | "Solid = tailored · dashed = base. Weekly average ATS composite (0–100)." | "Solid lines: tailored. Dashed: base." | composite; the second sentence repeats the card |
| components/charts/ats-over-time-chart.tsx:113 | " Weeks with fewer than 5 scores are directional only." | " Weeks with fewer than 5 scores are rough." | |
| components/charts/ats-over-time-chart.tsx:116 | "…Pick a role category above to see the other {n}." | "…Pick a role above to see the other {n}." | pin `test_frontend_analytics.py:40` |
| components/charts/tailoring-lift-chart.tsx:73 | "…across {n} applications · directional only." | "…across {n} applications (small sample)." | |
| components/charts/tailoring-lift-chart.tsx:78 | "Some roles have fewer than 5 applications · those bars are directional only." | "Some roles have fewer than 5 applications, so treat those bars as rough." | |
| components/charts/tailoring-lift-chart.tsx:84 | "No per-role tailoring pairs yet." | "No tailored resumes to compare yet." | |
| components/explore/low-sample-hint.tsx:7 | "based on {n} {unit} · directional only" | "Based on only {n} {unit}" | |
| components/explore/low-sample-hint.tsx:31 | badge "n={n}" | "only {n}" | statistics notation |
| components/explore/explore-overview.tsx:97 | "Failed to load overview." | "Couldn't load job market data." + Try again | error form; no retry |
| components/explore/explore-overview.tsx:104 | "No job descriptions yet. Capture a few to see the dashboard." | "Add a few jobs to see this." | jargon |
| components/explore/explore-overview.tsx:118 | "mixed" | "Mixed currencies" | a bare word |
| components/explore/explore-overview.tsx:131 | "Job descriptions" | "Jobs" | |
| components/explore/explore-overview.tsx:133 | "Since 2026-07-01" | "Since Jul 1" | date format |
| components/explore/explore-overview.tsx:136, :170 | "Role categories", "Role category mix" | "Roles" | one name |
| components/explore/explore-overview.tsx:140 | "Onsite" | "On-site" | |
| components/explore/explore-overview.tsx:145 | "Avg yearly salary" | "Average yearly pay" | abbreviation |
| components/explore/explore-overview.tsx:193 | "No required skills tagged" | "No required skills found" | |
| components/explore/explore-overview.tsx:203, :215 | Work mode and Level bars print raw keys | `humanizeEnum` | raw-value |
| components/explore/explore-overview.tsx:211 | "Free text, so values may be inconsistent." | "As written in each job." | |
| components/explore/explore-overview.tsx:226, :238 | "No locations extracted", "No countries extracted" | "No locations found", "No countries found" | extract |
| components/explore/explore-overview.tsx:245 | "OPT &amp; sponsorship" | "OPT and sponsorship" | ampersand |
| components/explore/explore-overview.tsx:250, :256 | OPT and work-authorization bars print raw keys | `humanizeEnum` (the D2.2 labels) | raw-value |
| components/explore/explore-overview.tsx:264 | "Salary by track (yearly)" | "Yearly pay by role" | jargon |
| components/explore/explore-overview.tsx:268 | "Multiple currencies in scope, so rows are per currency rather than blended." | "Shown per currency, since jobs use more than one." | |
| components/explore/explore-overview.tsx:274-275 | "No pay numbers yet. Most postings omit salary, and that is normal." | "No pay data yet. Most jobs don't list pay." | posting |
| components/explore/explore-overview.tsx:292 | "{n} disclosed" | "{n} jobs" | jargon |
| app/applications/[id]/page.tsx:60 | `detail={lastError instanceof Error ? lastError.message : undefined}` | `detail={errorDetail(lastError)}` | D1.3 |

**Dropped from part 1, with the reason.**
- `job-extracted-fields.tsx:136`, `proposal-agent-panel.tsx:208`, `proposals-section.tsx:694` (uppercase
  eyebrows): the conventions keep the tracked uppercase style for group headings on purpose.
- `app/jobs/[id]/page.tsx:83` "Q&A" tab: kept; the owner did not rename it and it is widely understood.
- `app/proposals/page.tsx:9`, `proposals-section.tsx:392,439,445,453,457,461,471,476`,
  `app/jobs/[id]/page.tsx:155,401`, `proposal-agent-panel.tsx` titles, `funnel-strip.tsx`: appendix A
  rewrites them (A1, A3, A5, A6, A9). A3 names the board filter "Job board"; the audit's "Site" is dropped
  in its favour.
- `components/status-chip.tsx:35` "Offer": already right; Analytics now matches it.
- `lib/render-note.ts:54`, `hooks/use-refresh-failed-notice.ts:18`: shared helpers owned by L3 and L2.

### D2.10 Pins (L1)

| test | old | new |
|---|---|---|
| `test_frontend_query_error_states.py:66` | `("components/analytics/analytics-overview.tsx", "Submitted · last 7 days")` | `("components/analytics/analytics-overview.tsx", "Applied · last 7 days")` |
| `test_frontend_query_error_states.py:74` | `("components/qa-tab.tsx", "No Q&amp;A entries yet.")` | `("components/qa-tab.tsx", "No answers yet.")` |
| `test_frontend_plain_words.py:179` | `'["Role family", job.role_category ? roleLabelOf(job.role_category) : null],'` | `'["Role", job.role_category ? roleLabelOf(job.role_category) : null],'` |
| `test_frontend_plain_words.py:184-188` | comment "`full_time`, `on_site`" | "`full_time`, `onsite`"; add `assert 'onsite: "On-site"' in _read("components/job-extracted-fields.tsx")` and `assert "on_site:" not in …` (the D10.4 pin) |
| `test_frontend_first_run.py:137` | `"The job is listed under Saved. Scoring comes next." in page` | `"Saved jobs appear in Applications, ready to score." in page` |
| `test_frontend_first_run.py:144` | `"Add an API key to extract." in page` | `"Add an API key to extract." not in page` and `"Saving a job reads its description with AI, so it needs an API key." in page` |
| `test_frontend_qa_tab.py:132` | `flat.index('"Generate cover letter"')` | `flat.index('"Write cover letter"')` |
| `test_frontend_placeholders.py:494-504` `test_question_constraint_is_a_hint` | `'aria-label="Questions to ask"'`, the `placeholder="e.g. Why this team?"` order step | `'aria-label="Application questions"' in src`; `_order(src, "One question per line.", "aria-describedby={questionsHintId}")`; `"placeholder=" not in src` |
| `test_frontend_placeholders.py` | `_PENDING_EXAMPLES_L1` | delete the set |
| `test_frontend_referrals.py:102-105` | `test_create_form_placeholders_are_examples` | `test_create_form_has_no_placeholders` (D1.4) |
| `test_frontend_analytics.py:40` | `"Pick a role category above to see the other ${hidden.length}."` | `"Pick a role above to see the other ${hidden.length}."` |
| `test_frontend_agent_words.py` (appendix A5) | row `("components/analytics/autofill-coverage-card.tsx", "with the extension to start capturing", "with the Companion to start capturing")` | present becomes `"Use Companion on an application form to start."` |
| `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_L1` blocks | delete them |
| new, `test_frontend_plain_words.py` | none | `test_analytics_never_calls_the_top_skills_mandatory`: `"mandatory" not in _read("app/analytics/page.tsx").lower()` and `'subtitle="Mandatory"' not in _read("components/charts/top-skills-chart.tsx")` (D10.3) |
| new, same file | none | `test_status_maps_never_print_a_key`: `'?? "Unknown"' in _read("components/status-chip.tsx")` twice, and `"?? status;" not in` it |

`test_frontend_focus.py:409` keeps passing (its comment "# Extract job on /new" should read "# Save job on
/new").

### D2.11 Browser checks (L1)

1. `/applications` (empty tracker, fresh DB): the header and empty state say "Add job"; the empty state
   reads "Add a job to get started."; the Agent-inbox filter group lists "To review". Dark mode, 375px: no
   label overflows.
2. `/new` with no API key: the amber notice reads "Saving a job reads its description with AI, so it needs
   an API key."; the disabled "Save job" is named by it (`read_page`); no placeholder in Job link. With a
   key: paste a posting, Save job, toast "Job saved.", the summary says "Saved to Applications.".
3. A job with `work_mode = onsite` (any extracted job): the header subtitle and the Overview chip both read
   "On-site"; the OPT and work-authorization chips read words ("STEM OPT accepted", "Not stated").
4. Score and tailor: the lead line explains the ATS score; "Update scores" re-runs; a base card's button
   reads "Find gaps and tailor"; the compare card on the Resume tab reads "ATS score before and after" with
   "Matched"/"Missing" badges and placement words, never `experience_only`.
5. Stop the backend and click "Update scores": the toast reads "Couldn't score your resumes. Maestro CS isn't
   responding. Check that it's running, then try again." and the console holds the developer detail.
6. `/analytics`: the Top skills card says "Most asked for", never "Mandatory"; Overview reads "In progress",
   "Average score gain"; the Level and Employment type filters show words, not `full_time`.

---

## D3. Gap page (lane L2)

`app/jobs/[id]/tailor/[sessionId]/page.tsx` (written `tailor page` below) and `components/gap-analysis/*`.
Source: audit part 1 §2.6. The server writes the category titles and gap details this page shows; D9 rewrites
them. No appendix A–C file overlaps this lane.

**The one string code compares.** `tailor page:404` matches the server's `"No actionable resolutions to
tailor"` exactly to choose its own message. That server string stays (D9, *Kept*); only the message the page
shows changes.

| file:line | current | new | why (category) |
|---|---|---|---|
| tailor page:102 | save state "Save failed" | "Not saved" | the same state `AutosaveStatus` calls Not saved (inconsistent-term; D1.1d) |
| tailor page:164 | badge "{done}/{total}" | "{done} of {total}" | a bare ratio beside a heading (slash) |
| tailor page:293 | `toast.error(error.message)` on a 409 | `toast.error(errorDetail(error) ?? "This gap analysis is out of date. Start a new one.")` | the server's stale sentence is plain after D9; never raw |
| tailor page:297 | `error instanceof Error ? error.message : "Failed to save resolutions"` | `couldnt("save your answers", error)` | D1.3 (jargon, tone) |
| tailor page:361 | "{n} answers were not saved to your Career KB" | "{n} answers weren't added to your career history" | KB (the reasons under it are D9's write-back skip rows) |
| tailor page:393 | "This session is no longer open. Refreshing." | "This gap analysis was closed. Reloading." | session |
| tailor page:407-408 | "Your quick-tailor defaults had nothing they were allowed to add here. Answer a gap yourself, or use the base resume as-is." | "Quick tailor had nothing to add here. Answer a gap yourself, or use your resume as is." | one name for Quick tailor; as-is |
| tailor page:412, :479, :494 | `toast.error(error.message)` | `couldnt("tailor your resume", error)`, `couldnt("use your resume as is", error)`, `couldnt("start over", error)` | D1.3 |
| tailor page:460, :487 | thrown "Session not loaded" | "Still loading. Try again in a moment." | session |
| tailor page:552 | "Resolve at least one gap first. Skips alone give the tailor nothing to do." | "Answer at least one gap first. Skipped gaps change nothing." | jargon, tone |
| tailor page:561 | "Open gaps are left as-is. The tailored resume reflects only the resolutions you made." | "Open gaps stay as they are. Only your answers go into the tailored resume." | as-is, jargon |
| tailor page:584 | "Applies your saved quick-tailor defaults to every gap you haven't answered, then tailors. Gaps you've already resolved are left exactly as they are. Every change is listed with its source in the review step afterward, and can be reverted one at a time." | "Fills every open gap from your Quick tailor settings, then tailors. Your answers stay as they are. You can review and undo each change afterward." | verbose; keeps the review-and-undo promise (the consent surface) |
| tailor page:594 | `useRefreshFailedNotice(session, "this tailoring session")` | `useRefreshFailedNotice(session, "this gap analysis")` | session; the hook's own sentence ("Couldn't refresh … Your edits on screen are kept.") stays |
| tailor page:607 | "Tailoring session not found" | "This gap analysis no longer exists" | session |
| tailor page:621 | "Couldn't load this tailoring session." | "Couldn't load this gap analysis." | session |
| tailor page:622 | `detail={sessionError instanceof Error ? sessionError.message : undefined}` | `detail={errorDetail(sessionError)}` | D1.3 |
| tailor page:651 | "This session is already tailored" | "This gap analysis is done" | session |
| tailor page:652 | "The tailored resume lives on the job's application." | "Your tailored resume is on the job's Resume tab." | says where to look |
| tailor page:654 | "This gap analysis was superseded" | "A newer gap analysis replaced this one" | jargon |
| tailor page:656 | "A newer session replaced it. Continue from the job's Score & Tailor tab." | "Continue from the job's Score and tailor tab." | repeats the heading; the tab's new name (D2) |
| tailor page:660 | "Start a fresh analysis anytime from the job's Score & Tailor tab." | "Start a new one from the job's Score and tailor tab." | |
| tailor page:695 | "This analysis is out of date: {reason} since it was created. Saving and tailoring are disabled." | "This gap analysis is out of date because {reason}. Your changes here won't be saved. Start a new one to keep going." | grammar ("…no longer exists since it was created"); keeps "won't be saved". The reasons are D9's |
| tailor page:728-729 | header "{n} of {total} gaps addressed" | remove | the sticky footer shows the same counts. **[behaviour]** one line fewer |
| tailor page:744 | `coverage_warning` shown verbatim | unchanged here; D9 | |
| tailor page:747 | "Only {m} of {n} skills in this posting were recognized ({p}% coverage)." | "We recognized only {m} of the job's {n} skills ({p}%)." | same as the Score tab (D2) |
| tailor page:758 | "This resume already covers the JD well. Sharpen your value proposition in the summary below, then tailor." | "This resume already fits the job well. Strengthen your summary below, then tailor." | JD, jargon |
| tailor page:759 | "This resume already covers the JD well. Tailor as-is." | "This resume already fits the job well." | "Tailor as-is" read two ways |
| tailor page:769-770 | "{n} gaps auto-resolved from your own evidence — review below." | "{n} gaps were filled in from your resumes and career history. Review them below." | em dash, evidence |
| tailor page:775-780 | "Nothing here could be resolved automatically — these gaps need your judgment. Add keyword places the JD's exact term, Answer feeds the tailor your real experience, and Skip leaves a gap as-is." | "These gaps need your input. Add keyword uses the job's exact words, Answer adds your real experience, and Skip leaves a gap as it is." | em dash, JD, as-is |
| tailor page:798 | label "Anything specific about how this should be tailored? (optional)" | `<Label optional>Tailoring notes</Label>` with hint "What to stress, or limits like page count." | a question as a label; hand-written marker (D1.2) |
| tailor page:806 | placeholder "e.g. emphasize leadership, keep it to one page, lead with the fintech project…" | remove | owner rule; the hint above carries it |
| tailor page:815 | footer "{a} addressed · {s} skipped · {o} open" | "{a} done · {s} skipped · {o} open" | one word for handled gaps (a dense status row, so `·` stays) |
| tailor page:833 | "This job already has a tailored resume draft. Using the base as-is replaces it and removes its rendered PDF. Version history keeps the old draft." | "Using your base resume as is replaces this job's tailored resume and its PDF. Version history keeps the old one." | render, as-is; keeps the Version history promise |
| tailor page:844 | "Use base resume as-is" | "Use resume as is" | as-is; plain "resume" in an action |
| tailor page:854 | title "Fill the open gaps from your saved defaults, then tailor" | "Fill open gaps from your Quick tailor settings, then tailor" | one name |
| tailor page:868 | "Tailoring, about 30s" | "Tailoring… about 30 seconds" | abbreviation, progress ellipsis |
| gap-analysis/gap-card.tsx:129 | "Title alignment" | "Job title" | jargon |
| gap-card.tsx:130 | "Experience gate" | "Experience requirement" | gate |
| gap-card.tsx:132 | fallback "Responsibility coverage" | "Job duty" | jargon |
| gap-card.tsx:144 | "up to +{x} pts" | "up to +{x} points" | abbreviation |
| gap-card.tsx:170, :190 | fallback label `saved.section` (skills, extra) | the section's word ("Skills", "Other section") through the resume's section-label map | raw-value |
| gap-card.tsx:183 | "unhide “{name}” from your {section}" | "show hidden “{name}”" | one verb for hidden items |
| gap-card.tsx:184 | "unhide a hidden {section} entry" | "show a hidden item" | read "a hidden projects entry" (grammar, raw-value) |
| gap-card.tsx:193-194 | "add “{w}” from your Career KB → {label}" (and without the arrow) | "add “{w}” from your career history to {label}" / "add “{w}” from your career history" | KB; the arrow is read aloud |
| gap-card.tsx:213 | "Auto-resolved from your library by enabling {name}" | "Filled in: showed {name} from your resume" | library, jargon |
| gap-card.tsx:214 | "Auto-resolved from your library" | "Filled in from your resume" | library |
| gap-card.tsx:217 | "Auto-resolved from your Career KB profile" | "Filled in from your career history" | KB |
| gap-card.tsx:220 | "Auto-added the JD's exact term — this skill is already evidenced on your resume" | "Added the job's exact words. Your resume already shows this skill." | JD, em dash |
| gap-card.tsx:222 | "Auto-resolved from your Career KB" | "Filled in from your career history" | KB |
| gap-card.tsx:259 | "matched via {match_form} (“{term}”)" | "Matches “{term}”" | `match_form` is an engine key |
| gap-card.tsx:263 | `placement.replace(/_/g, " ")` | the shared `PLACEMENT_LABELS` (D2.4) | "skills list only", "dual" |
| gap-card.tsx:265 | "title tier: {tier}" | remove | raw engine value (jargon) |
| gap-card.tsx:518 | "{title} — can't confirm" | "{title}: can't confirm" | reads as prose |
| gap-card.tsx:532 | "{title} — skipped" | "{title}: skipped" | |
| gap-card.tsx:558 | "Change" | "Edit" | the resolved row beside it says Edit (`:585`) |
| gap-card.tsx:600 | `requirement_level` badge ("required", "preferred") | "Required", "Preferred", "Mentioned" | raw-value, case |
| gap-card.tsx:607 | title "Coarse upper bound if this were the only fix. A relative signal, not an exact promise." | "The most this fix could add on its own. An estimate." | jargon |
| gap-card.tsx:630 | "Exact-token hygiene: helps recruiter keyword search, but will not change the score." | "Uses the job's exact words. Helps recruiter searches, but won't change your ATS score." | jargon |
| gap-card.tsx:631 | "Semantic match: adding the literal JD token adds keyword credit." | "Your resume says this differently. Using the job's exact words raises your ATS score." | JD, jargon |
| gap-card.tsx:705 | "Rewrite your summary as a JD-aligned value proposition. This refreshes the summary section." | "Rewrite your summary for this job. This replaces your current summary." | JD |
| gap-card.tsx:709 | "What's your actual experience with this?" | "What's your experience with this?" | filler |
| gap-card.tsx:713 | placeholder "e.g. Data scientist who ships forecasting models to production" | remove | owner rule; the field is usually prefilled |
| gap-analysis/resolution-controls.tsx:57 | "Enable entry" | "Show hidden item" | never rendered today (`SEGMENT_ACTIONS` filters it); fix for consistency |
| resolution-controls.tsx:58 | "Use KB evidence" | "Use from career history" | never rendered; same reason |
| resolution-controls.tsx:64 | "Saved so you won't be asked again; never used as evidence." | "We won't ask again, and it won't go on your resume." | semicolon, evidence; keeps the "never used" promise |
| resolution-controls.tsx:256 | aria-label "Resolution action" | "How to handle this gap" | jargon |
| resolution-controls.tsx:334 | tag "recent" | "Recent" | case |
| resolution-controls.tsx:348 | "Unverified. You have no evidence of this skill on your resume. Only add skills you genuinely have, because recruiters may ask." | "Your resume doesn't show this skill. Add it only if you have it. Recruiters may ask." | **safety honesty warning: shortened, every clause kept** |
| resolution-controls.tsx:379 | "Loading placement options…" | "Loading…" | jargon |
| resolution-controls.tsx:405 | group "Custom" | "Other sections" | glossary |
| resolution-controls.tsx:416 | "Where should this keyword live?" | "Where should it go?" | idiom |
| resolution-controls.tsx:444 | placeholder "e.g. PySpark" | remove | owner rule; prefilled with the suggested wording |
| resolution-controls.tsx:456 | placeholder "e.g. Built the ingestion pipeline in Python and Airflow" | remove | owner rule; the hint "Only what you write here is used." stays |
| resolution-controls.tsx:495 | "Which role, project, or custom section was this? (optional)" | `<Label optional>Where did you do this?</Label>` | verbose; one marker (D1.2) |
| resolution-controls.tsx:547 | "Hidden entry" | "Hidden item" | entry |
| resolution-controls.tsx:548 | "{name} (disabled)" | "{name} (hidden)" | one word |
| resolution-controls.tsx:550 | chip "KB profile" | "Career history skills" | KB |
| resolution-controls.tsx:554 | fallback "Career KB item" | "Career history item" | KB |
| resolution-controls.tsx:555 | "KB: {text}" | "{text}" | the "Found in…" heading names the source |
| resolution-controls.tsx:579-580 | "Found in your library" | "Found in your resumes and career history" | library |
| resolution-controls.tsx:597-598 | "Evidence from your own resume entries and Career KB. Picking one that can't be ported directly drops its text into the answer box for you to edit." | "Pick one to use it. If it can't be added directly, its text goes into your answer to edit." | KB, port, evidence |
| resolution-controls.tsx:637-638 | "Attach an existing project as evidence for this skill." | "Pick a project that shows this skill." | evidence |

**Dropped.** `resolution-controls.tsx:345` "Additional Skills": it is written into the resume as a section
heading, where Title Case is the resume's own style. `tailor page:347` toast "ATS score: {a} → {b} ({d})":
kept, since "ATS score" is the owner's term (the audit proposed "Score:").

### D3.1 Pins (L2)

| test | old | new |
|---|---|---|
| `test_frontend_gap_autosave.py:122` | `assert "Save failed" in _INDICATOR` | `assert "Not saved" in _INDICATOR and "Save failed" not in _INDICATOR` (the comment at `:150` reads "keeps "Not saved" up") |
| `test_frontend_query_error_states.py:392` | `'useRefreshFailedNotice(session, "this tailoring session");'` | `'useRefreshFailedNotice(session, "this gap analysis");'` |
| `test_frontend_placeholders.py:537-550` `test_summary_placeholder_is_an_example_and_the_consequence_stays_visible` | asserts the `e.g.` summary placeholder, "This refreshes the summary section.", `_order(controls, "Exact wording", 'placeholder="e.g. PySpark"')` | rename `test_summary_field_has_no_placeholder_and_the_consequence_stays_visible`: `"placeholder=" not in gap`; `"This replaces your current summary." in gap`; `"This becomes your summary." not in gap`; `"Only what you write here is used.\n" in controls`; `"placeholder=" not in controls`; `"Exact wording" in controls`; `"Exact wording to add" not in controls` |
| `test_frontend_placeholders.py` | `_PENDING_EXAMPLES_L2` | delete |
| `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_L2` | delete |
| new, `test_frontend_plain_words.py` | none | `test_the_gap_page_still_matches_the_server_quick_tailor_answer`: `assert 'error.message === "No actionable resolutions to tailor"' in _read("app/jobs/[id]/tailor/[sessionId]/page.tsx")`, with a comment that D9 keeps that server string because this line compares it |

### D3.2 Browser checks (L2)

1. Open a gap analysis: category headers and gap details read D9's words; no "JD", "session" or "Career KB"
   anywhere (read_page). The honesty warning appears when you add a skill the resume does not show.
2. Type in Tailoring notes: no placeholder; the label reads "Tailoring notes (optional)" with the hint under
   it. Tab through: the hint is announced (`aria-describedby`).
3. Force a save failure (DevTools offline, then edit an answer): the status reads "Not saved"; back online,
   Try again recovers.
4. Quick tailor on a job whose settings allow nothing: the toast reads "Quick tailor had nothing to add
   here. Answer a gap yourself, or use your resume as is."
5. Edit the base resume in another tab, then return: the banner reads "This gap analysis is out of date
   because the base resume was edited. Your changes here won't be saved. Start a new one to keep going."
6. 375px, dark mode: the footer "{a} done · {s} skipped · {o} open" fits one line or wraps cleanly.

---

## D4. Resumes, studios, health and templates (lane L3; split L3a and L3b)

**L3a** owns the base resumes list and dialog, both studios and the shared editor parts, `lib/studio.ts`,
`lib/formatting.ts`, `lib/extra-sections.ts`, `lib/resume-schema.ts`, `lib/describe-edit.ts`,
`lib/render-note.ts` and `components/role-category-picker.tsx`. **L3b** owns the health report
(`components/resume-health/*`, `lib/health-report.ts`), Version history and Templates. Source: audit part 2
(all of it except Career KB) and part 3 §2.13. Owner changes to part 2: the resume line is a **bullet** (part
2 said "point"), so "Bullets", "Add bullet" and "No bullets" stay; records are **items**; the Career KB is
**Career history**. No appendix A–C file overlaps this lane except `instruct-sheet.tsx` (A5 rows 36–39,
after A).

### D4.1 Base resumes list (`app/base-resumes/page.tsx`, `components/base-resumes/*`)

| file:line | current | new | why (category) |
|---|---|---|---|
| app/base-resumes/page.tsx:122 | title "Base Resumes" | "Base resumes" | case; the sidebar item too (D7) |
| app/base-resumes/page.tsx:123 | "One source of truth per career track. Edits auto-render a fresh PDF." | "One resume for each kind of job you apply for." | render, jargon, two sentences |
| app/base-resumes/page.tsx:128 | aria-label "Show archived base resumes" | remove (the visible "Show archived" wraps the switch) | name and label differ |
| app/base-resumes/page.tsx:186 | "No career-track resumes yet." | "No base resumes yet. Create one to start." | a third name; empty state points to the action |
| app/base-resumes/page.tsx:201 | "Duplicate {dupSource}" | "Duplicate {display name}" (`useBaseResumeLabel`) | printed the slug |
| app/base-resumes/page.tsx:207 | placeholder "e.g. Data Scientist (1 page)" | remove | owner rule; prefilled "<name> (copy)" |
| app/base-resumes/page.tsx:238 | "Delete {deleteTarget?.slug}?" | "Delete {display name}?" | printed the slug |
| app/base-resumes/page.tsx:240-241 | "This removes the resume, its rendered PDF, and the JSON file. This can't be undone." | "This deletes the resume and its PDF. You can't undo this. To keep it out of the way instead, archive it." | render, JSON; the irreversibility stays (a delete has no version history) |
| app/base-resumes/page.tsx:330 | "Unarchive" / "Archive" | "Restore" / "Archive" | the toast already says Restored |
| app/base-resumes/page.tsx:98 | toast "Deleted" | "Resume deleted" | a toast names its object |
| app/base-resumes/page.tsx:113 | toast "Restored" / "Archived" | "Resume restored" / "Resume archived" | |
| app/base-resumes/page.tsx:91, :103, :116 | `toast.error(err.message)` | `couldnt("duplicate the resume", err)`, `couldnt("delete the resume", err)`, `couldnt("archive the resume", err)` (Restore: "restore the resume") | D1.3 |
| app/base-resumes/page.tsx:71 | thrown "missing source slug" | "Choose a resume to copy." | raw-value |
| app/base-resumes/page.tsx:145 | `detail={(resumes.error as Error)?.message}` | `detail={errorDetail(resumes.error)}` | D1.3 |
| app/base-resumes/[slug]/page.tsx:35 | `detail={(query.error as Error \| null)?.message}` | `detail={errorDetail(query.error)}` | D1.3 |
| app/base-resumes/[slug]/page.tsx:40 | "Back to list" | "Back to base resumes" | name the destination |
| app/base-resumes/[slug]/health/page.tsx:17 | "Back to editor" | "Back to resume" | |
| components/base-resumes/base-resume-gallery.tsx:50 | title "{display_name} · {slug}" | "{display_name}" | slug |
| components/base-resumes/base-resume-gallery.tsx:69 | title "This resume has no target role, so it is missing from role-based grouping. Set one in the editor." | "No target role. Set one in the resume to group it by role." | jargon |
| components/base-resumes/base-resume-thumbnail.tsx:39 | "Not rendered yet" | "No PDF yet" | render |
| components/base-resumes/base-resume-thumbnail.tsx:43 | chip "Render failed" | "PDF out of date" | what the user sees |
| components/base-resumes/base-resume-thumbnail.tsx:44 | title "The last render failed, so this preview is the previous version.\n\n{render_error}" | "The last PDF update failed. This is the previous version. Open the resume to see why." | render; the raw engine log leaves the tooltip |

### D4.2 New base resume dialog (`components/base-resumes/new-base-resume-dialog.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| :132-134 | "Build it from your Career Knowledge Base, copy one you already have, parse a resume file, or start from an empty document." | "Start from your career history, a copy, a file or a blank page." | KB, parse |
| :265 | toast.warning "Imported with gaps: {warnings}" | "Imported. Some parts need checking: {warnings}" | "gaps" means skill gaps elsewhere |
| :282 | toast.warning "Nothing was selected. Pick entries yourself below." | "No suggestions for this role. Pick items below." | entry, passive |
| :285, :424 | `toast.error(err.message)` | `couldnt("suggest items", err)`, `couldnt("create the resume", err)` | D1.3 |
| :474 | tab "From Career KB" | "From career history" | KB |
| :475 | tab "From existing" | "Copy a resume" | names the object |
| :494 | placeholder "e.g. Machine Learning Engineer" (ternary, non-file modes) | remove | owner rule |
| :525 | "(optional)" span in the Target role label | `<Label optional>` | one marker (D1.2) |
| :541 | label "How should this resume be shaped?" | `<Label optional>Focus</Label>` | vague |
| :543-544 | hint "Steers which entries are picked and the tone of the summary. Your bullets are used exactly as written." | "Guides which items are picked and the tone of the summary. Your bullets are never rewritten." | entry; keeps the promise |
| :551 | placeholder "e.g. Lead with production ML work, senior in tone" | remove | owner rule |
| :574 | "Suggest again" / "Suggest a selection" | "Suggest again" / "Suggest items" | vague |
| :584 | "Loading Career KB…" | "Loading your career history…" | KB |
| :586-587 | "Your Career KB has no entries with approved points yet. Import a resume first." | "Nothing to pick yet. Import a resume into your career history first." | KB, entry, point |
| :601 | "{kind} · {org} · {n} point(s)" | "{kind} · {org} · {n} bullet" / "bullets" | owner: bullet; plural |
| :619 | "Left off" | "Not included" | idiom |
| :623 | "{title} — {reason}" | "{title}: {reason}" | em dash |
| :628 | "Tick any of these above to put them back on." | "Select any above to include it." | "Tick" |
| :643 | hint "Left blank on purpose. A wrong summary is worse than none." | "Check this summary, or clear it." | **bug** (D10.5): the field is prefilled from the plan's drafted summary (`base_from_kb_plan.py:165`), so "Left blank on purpose" was false |
| :664 | SelectValue "Choose a base resume" | "Choose a resume" | a select prompt, not a placeholder (`_NOT_INPUTS`) |
| :668, :676 | `{display_name ?? slug}` in the Copy from list | `{display_name ?? baseResumeLabel(slug, …)}` | slug fallback (raw-value) |
| :712 | "Starts as the source resume's tag. Typing a Name that matches the catalog pre-fills a suggestion you can clear." | "Copied from the original. Typing a name may suggest a new role." | jargon |
| :725 | Dropzone hint "PDF, DOCX, Markdown, text, or the app's own JSON · one file, up to 10 MB" | "PDF, Word or text file, up to 10 MB" | jargon; the JSON import stays, unannounced (docs) |
| :747 | "The file is parsed into this app's resume structure and becomes a new base resume you can edit. Your Career KB is not changed — use the resume's Sync to KB pill later if you want it there too." | "We'll turn the file into a resume you can edit. It won't be added to your career history. You can add it later from the resume." | KB, em dash; keeps "not added" |
| :775 | "Close" | "Cancel" | every other dialog here says Cancel |
| :784 | "Parsing…" / "Create" | "Reading file…" / "Create" | parse |

### D4.3 Both studios and the shared editor parts (`components/resume-editor/*`)

| file:line | current | new | why (category) |
|---|---|---|---|
| editor-body.tsx:213, tailored-resume-studio.tsx:630, raw-json-toggle.tsx:91 | save error "{path.join('.')}: {zod message}" joined with "; " | "Some fields need fixing: {section words}." (map each path's first segments through `describe-edit`'s section words: `experience.2.bullets.0` → "Experience, item 3, bullet 1"); the raw path stays only inside the code view | schema paths (raw-value) |
| editor-body.tsx:252, :271 | `toast.error(err.message)` | `couldnt("save the resume", err)`, `couldnt("create the PDF", err)` | D1.3 |
| editor-body.tsx:445-448 | "Generating…" / "Regenerate PDF" / "Generate PDF" | "Creating…" / "Update PDF" / "Create PDF" | owner canon |
| editor-body.tsx:469-470 | "Import from Career KB" | "Add from career history…" | KB; opens a sheet |
| editor-body.tsx:482-487 | "Copy slug: {slug}", toasts "Copied {slug}", "Could not copy slug" | "Copy resume ID", toasts "Resume ID copied", `couldnt("copy the resume ID", err)` | slug; the item exists so a connected agent can be told which resume (keep it) |
| editor-body.tsx:530, tailored studio tabs, diff-review.tsx:63, lib/formatting.ts:67 | "Extra sections", "Custom sections" | "Other sections" | glossary (grep: `rg -n '"(Extra\|Custom) sections"' frontend/components frontend/lib`, 4 sites) |
| editor-body.tsx:685 | "No summary" | "No summary yet" | |
| lib/studio.ts:27 | "Rendering PDF…" | "Updating PDF…" | render |
| lib/studio.ts:28 | "Re-scoring…" | "Updating score…" | re-score |
| lib/studio.ts:40 | "No PDF yet. Save to render one." | "No PDF yet. Save to create one." | render |
| lib/studio.ts:41 | "No PDF yet. Generate one from More resume actions (⋯)." | "No PDF yet. Choose Create PDF in the ⋯ menu." | **bug** (D10.9): names the menu by its screen-reader label, which sighted users never see |
| studio-overflow.tsx:82 | "Form view" / "Edit raw JSON" | "Back to form" / "Edit as code (advanced)" | jargon |
| studio-overflow.tsx:86 | "History" | "Version history" | the sheet's title |
| editable-title.tsx:64 | `toast.error(err.message)` | `couldnt("rename the resume", err)` | D1.3 |
| editable-title.tsx:84 | aria-label "Display name" | "Resume name" | data-model word |
| editable-title.tsx:108 | title falls back to `{slug}` | "Untitled resume" | slug |
| editable-card.tsx:88, :97 | aria-labels "Edit", "More actions" | "Edit {item title}", "More actions for {item title}" | repeated names (WCAG 2.4.6) |
| editor-scaffold.tsx:109-110 | "{n} active · {n} archived" | "{n} shown · {n} hidden" | one word for switched-off entries |
| editor-scaffold.tsx:118 | "Disable" / "Enable" | "Hide from resume" / "Show on resume" | |
| experience-editor.tsx:71, project-editor.tsx:83 | badge "Archived" | "Hidden" | |
| bullet-list.tsx:31 | aria "{label} {i} of {n}" → "Bullets 2 of 5" | "Bullet 2 of 5" (singular item label) | **bug** (D10.8) plural label in a singular slot |
| bullet-list.tsx:45, :54 | aria "Move bullets 2 up/down" | "Move bullet 2 up" / "Move bullet 2 down" | same bug |
| bullet-list.tsx:63 | aria "Delete bullets 2" | "Delete bullet 2" | same bug |
| experience-editor.tsx:99, project-editor.tsx:109, extra-sections-editor.tsx:372 | "No bullets" | "No bullets yet" | an empty state invites action |
| experience-editor.tsx:128, :134 | placeholders "e.g. Jan 2023", "e.g. Mar 2025" | remove; Start date gains hint "Month and year, like Jan 2023." | owner rule; the format moves to a hint |
| experience-editor.tsx:135 | hint "Leave empty for a current role." | "Leave empty if you still work here." | plainer |
| project-editor.tsx:65 | menu "Port to another base resume" | "Copy to another resume" | port |
| project-editor.tsx:118-133 | labels "Name" "Tech" "Link" "Date" | "Name" "Tools used" "Link" "Date" | "Tech" is engineer shorthand |
| project-editor.tsx:128 vs extra-sections-editor.tsx:409 | Link: no cue vs "https://…" | both: no placeholder; hint "Starts with https://" on both | owner rule; one treatment |
| project-port-dialog.tsx:69 | toast "Copied to {name} as archived" | "Copied to {name}. It's hidden there until you show it." | one word |
| project-port-dialog.tsx:89 | "Port project" | "Copy project to another resume" | port |
| project-port-dialog.tsx:92 | "Copy {project} to another base resume. It will be added as archived (disabled) so you can enable and edit it there later." | "It's added hidden, so you can check it before showing it." | the title says the rest |
| project-port-dialog.tsx:97 | label "Target base resume" | "Copy to" | |
| project-port-dialog.tsx:107 | Select prompt "Choose base resume" | "Choose a resume" | grammar; update `_NOT_INPUTS` |
| project-port-dialog.tsx:132, :138 | "Porting…" / "Port" | "Copying…" / "Copy" | port |
| project-port-dialog.tsx:76 | `toast.error(err.message)` | `couldnt("copy the project", err)` | D1.3 |
| education-editor.tsx:94-129 | "Institution" "Degree" "Field" "Location" "Start date" "End date" "Graduation" "GPA" | "School" … "Field of study" … "Graduation date"; Graduation date gains hint "Shown instead of the start and end dates." | glossary; two date inputs with no rule |
| contact-form.tsx:21 | placeholder "e.g. you@example.com" | remove; drop the `placeholder` field from the contact field table and the `Field` prop (D1.4 item 8) | owner rule |
| lib/resume-schema.ts:4 | "Name is required" | "Enter your name" | GOV.UK error pattern |
| lib/resume-schema.ts:5 | "Invalid email" | "Enter an email address like name@example.com" | says what to enter (an error message, not a placeholder) |
| lib/resume-schema.ts:88 | "Title collides with a core section header. Choose a different title." | "A section with this name already exists. Choose another name." | jargon |
| lib/resume-schema.ts:99 | "section key must be a lowercase slug (alphanumeric, '_' or '-'), e.g. 'publications'" | "Section key: use lowercase letters, numbers, - and _ only." | slug, e.g.; reached only in the code view |
| skills-editor.tsx:33 | "Untitled" | "Untitled group" | |
| skills-editor.tsx:49 | "No items" | "No skills yet" | |
| skills-editor.tsx:57 | label "Category" | "Group name" | glossary |
| skills-editor.tsx:65 | label "Items" | "Skills" | |
| extra-sections-editor.tsx:78-79 | "Enabled custom sections contribute undated ATS evidence; their dates do not count as employment recency." | "Dates here don't count as work history." | semicolon, evidence |
| extra-sections-editor.tsx:85 | "No custom sections yet." | "No other sections yet." | glossary |
| extra-sections-editor.tsx:228 | aria "Disable section" / "Enable section" | "Hide section" / "Show section" | the badge says Hidden |
| extra-sections-editor.tsx:255, :264, :273 | "Move section up" / "Move section down" / "Delete section" | "Move {title} up" / "Move {title} down" / "Delete {title}" | name the section |
| extra-sections-editor.tsx:277 | confirm 'Delete "{title}"?' | "Delete {title}?" | straight quotes |
| extra-sections-editor.tsx:279 | "This removes the section and all its content from this resume. This can't be undone." | "This deletes the section and everything in it. Version history keeps your saved versions, so you can restore it." | **bug** (D10.10): it can be undone; say how |
| extra-sections-editor.tsx:339 | "Untitled entry" | "Untitled item" | entry |
| extra-sections-editor.tsx:402 | placeholder "e.g. 2025" | remove | owner rule |
| extra-sections-editor.tsx:409 | placeholder "https://…" | remove; hint "Starts with https://" | owner rule |
| extra-sections-editor.tsx:422 | "Add entry" | "Add item" | entry |
| extra-sections-editor.tsx:497 | placeholder "e.g. Publications" | remove | the presets above show examples |
| extra-sections-editor.tsx:511 | label "Type" | "Layout" | |
| extra-sections-editor.tsx:515-522, lib/extra-sections.ts:60-61 | "Entries" / "Titled items with details and bullets"; "Bullets" / "A simple bulleted list" | "Items" / "Each with a title, details and bullets"; "List" / "A simple list" | entry |
| lib/extra-sections.ts:105-112 | preset chips "Presentations & Talks" … "Professional Affiliations" | chip `label` in sentence case ("Talks and presentations", "Volunteer experience", "Awards and honors", "Security clearance", "Professional affiliations"); the `title` written onto the PDF keeps Title Case | case, ampersand; pin `health-report.test.ts:236-238` reads the title "Awards & Honors" (unchanged) |
| formatting-panel.tsx:45 | tooltip "Selected template doesn't support this" | "This template doesn't support this setting" | |
| formatting-panel.tsx:297 | "Customized" | "Changed" | |
| formatting-panel.tsx:318 | "Formatting stays locked until it loads, so an edit can't overwrite a setting you already saved." | "You can change formatting once it loads." | verbose |
| formatting-panel.tsx:327 | "Inherited from base resume" | "Same as base resume" | jargon |
| formatting-panel.tsx:328 | "Overriding base resume formatting" | "Changed from base resume" | jargon |
| formatting-panel.tsx:337 | "Revert to base" | "Match base resume" | jargon |
| formatting-panel.tsx:343 | group "Content Style" | "Content style" | case |
| formatting-panel.tsx:380 | "Bullet style", options "•" "–" | keep the label; add hint "The symbol before each bullet." and option names "Dot" / "Dash" (`aria-label`) | owner: disambiguate the glyph setting from the bullets on the same screen |
| formatting-panel.tsx:392 | "Hide section divider" | "Hide section lines" | |
| formatting-panel.tsx:408 | "Header alignment" | "Name alignment" | "header" reads as section headers |
| lib/formatting.ts:125-126 | "Inline" / "Bulleted" | "One line" / "List" | jargon |
| formatting-panel.tsx:444 | group "Spacing & Margin" | "Spacing and margins" | case, ampersand |
| formatting-panel.tsx:457-465 | "Entry spacing", "Top & bottom margin" | "Item spacing", "Top and bottom margins" | entry, ampersand |
| formatting-panel.tsx:468 | "Align text left & right" | "Justify text" | ampersand |
| pdf-pages-preview.tsx:118-119 | "Preview is stale: the last PDF render failed. Fix the content or template, then save or regenerate the PDF." | "This preview is out of date because the PDF couldn't be updated. Check your last change, then save again." | render, stale |
| raw-json-toggle.tsx:134 | confirm "Discard your JSON edits?" | "Discard your code edits?" | JSON |
| raw-json-toggle.tsx:135 | "The JSON you typed has not been applied. This can't be undone." | "Your changes haven't been applied yet. You can't get them back." | JSON |
| raw-json-toggle.tsx:159 | "Apply JSON" | "Apply" | JSON |
| instruct-sheet.tsx:32-36 | starters "Tighten the summary to two sentences" "Lead each role with its highest-impact bullet" "Reposition this toward data engineering" "Which areas are weakest for a senior data scientist target?" "What roles could this resume pivot to?" | "Shorten the summary" "Put the strongest bullet first" "Aim this at data engineering" "What's weakest for a senior data scientist?" "What other roles fit this resume?" | plain and short |
| instruct-sheet.tsx:83, :107 | `toast.error(err.message)` | `couldnt("suggest edits", err)`, `couldnt("apply the edits", err)` | D1.3 |
| instruct-sheet.tsx:101 | toast "Applied {n} edit(s). PDF re-rendered." | "Applied {n} edit" / "edits". "PDF updated." | render; plural |
| instruct-sheet.tsx:122-125 | after A5 row 36: "Describe an edit, or ask for ideas. Nothing changes until you apply a suggestion, and the model may not invent facts that are not on the resume." | "Describe a change or ask a question. Nothing changes until you apply it. AI won't add facts that aren't on your resume." | after A; "the model", "may not" (ambiguous); keeps both promises |
| instruct-sheet.tsx:131 | label "Instruction" | "What should change?" | pin `test_frontend_dialog_drafts.py` reads the field id, not the label (checked) |
| instruct-sheet.tsx:135 | placeholder "e.g. Tighten the summary and lead with the platform work" | remove | owner rule; the starter chips give examples |
| instruct-sheet.tsx:174 | after A5 row 37: "Thinking…" / "Suggest again" / "Suggest edits" | "Working…" / "Suggest again" / "Suggest edits" | after A; "Thinking" |
| instruct-sheet.tsx:193-195, :204-205 | A5 rows 38–39 | keep A's text | after A |
| kb-import-drawer.tsx:120 | staleLabel "The resume" → `render-note` toast | see `lib/render-note.ts:54` below | |
| kb-import-drawer.tsx:122 | toast "Imported {n} entity/entities and {n} skill group(s) · {n} duplicate(s) skipped" | "Added {n} item" / "items" " and {n} skill group" / "groups". "Skipped {n} already on the resume." | entity; plural |
| kb-import-drawer.tsx:127 | `toast.error(error.message)` | `couldnt("add from career history", error)` | D1.3 |
| kb-import-drawer.tsx:171 | title "Import from Career KB" | "Add from career history" | KB |
| kb-import-drawer.tsx:172-173 | "Choose exact approved points. The import is one versioned operation." | "Choose the bullets to add. You can undo this from Version history." | point, versioned |
| kb-import-drawer.tsx:180 | "Loading Career KB…" | "Loading your career history…" | KB |
| kb-import-drawer.tsx:194 | tab "Basics" | "Summary and skills" | hides what is inside |
| kb-import-drawer.tsx:203 | "No {kind} in the Career KB." | "No {kind} in your career history yet." | KB |
| kb-import-drawer.tsx:238 | "No Career KB summary is available." | "Your career history has no summary." | KB |
| kb-import-drawer.tsx:265, :347 | badge "Already in this resume" | "Already added" | |
| kb-import-drawer.tsx:291 | "Importing…" / "Import selected" | "Adding…" / "Add selected" | the sheet's verb |
| kb-import-drawer.tsx:333 | badge `{entity.status}` via CSS `capitalize` | the career status labels map ("Ongoing", "Completed", "Archived") | raw-value |
| kb-import-drawer.tsx:336 | "{n} drafts excluded" | "{n} unapproved bullet not shown" / "bullets" | **bug** (D10.8) "1 drafts"; "drafts" is internal |
| kb-import-drawer.tsx:351-352 | tooltip "A matching structured entry already exists in the target resume." | "This is already on your resume." | jargon |
| kb-import-drawer.tsx:356 | "Loading approved points…" | "Loading bullets…" | point |
| kb-import-drawer.tsx:362-363 | "Structured entry only, no approved points." | "No approved bullets. Only the title and dates will be added." | point, jargon |
| lib/render-note.ts:54 | "{X} kept its previous PDF: the re-render failed." | "{X}: the PDF couldn't be updated, so it shows the previous version. Save again to retry." | render (every caller's `staleLabel` stays) |

### D4.4 Tailored studio (`app/applications/[id]/resume/page.tsx`, `tailored-resume-studio.tsx`, `diff-review.tsx`)

| file:line | current | new | why (category) |
|---|---|---|---|
| app/applications/[id]/resume/page.tsx:42 | `detail={(query.error as Error \| null)?.message}` | `detail={errorDetail(query.error)}` | D1.3 |
| tailored-resume-studio.tsx:195 | toast "Tailored resume re-scored" | "ATS score updated" | re-score; pin `test_frontend_studio.py:161` |
| tailored-resume-studio.tsx:197, :224, :306, :677 | `toast.error(err.message)` | `couldnt("update the ATS score", err)`, `couldnt("update the PDF", err)`, `couldnt("create the draft", err)`, `couldnt("save the resume", err)` | D1.3 |
| tailored-resume-studio.tsx:304 | toast "Draft built from the base resume" | "Draft created from your base resume" | |
| tailored-resume-studio.tsx:334 | "Stored resume data is invalid. Rebuild from the base resume to replace it." | "This resume couldn't be opened. Start over from your base resume." | jargon; the rebuild still replaces content |
| tailored-resume-studio.tsx:339 | "No tailored resume yet. Build a draft from your base resume, then refine it here and generate a PDF." | "No tailored resume yet. Start with a copy of your base resume." | verbose |
| tailored-resume-studio.tsx:348 | "Building…" / "Build draft from base resume" | "Creating…" / "Create draft" | |
| tailored-resume-studio.tsx:503 | toast "Couldn't revert this change automatically — it no longer matches the draft. Edit the section directly." | "Couldn't undo this change because the text has changed since. Edit it yourself." | em dash, revert |
| tailored-resume-studio.tsx:531 | toast "Review checks failed — try again." | "Couldn't run the checks. Try again." | em dash; "failed" read as the resume failing |
| tailored-resume-studio.tsx:542 | toast "Couldn't locate the flagged text — it may have been edited. Apply it manually." | "Couldn't find that text. It may have changed. Make the fix yourself." | em dash |
| tailored-resume-studio.tsx:757 | "This replaces the editor with the newer saved copy and discards your unsaved edits. This can't be undone." | "Your unsaved edits will be lost. You can't undo this." | verbose; true (unsaved edits have no version) |
| tailored-resume-studio.tsx:838 | title "Save your edits first. Re-scoring runs on the saved resume." | "Save first to update the ATS score." | re-score |
| tailored-resume-studio.tsx:847 | "Re-scoring…" / "Re-score" | "Updating…" / "Update score" | re-score |
| tailored-resume-studio.tsx:886-889 | "Generating…" / "Regenerate PDF" / "Generate PDF" | "Creating…" / "Update PDF" / "Create PDF" | owner canon |
| tailored-resume-studio.tsx:896 | confirm "Rebuild from base resume?" | "Start over from your base resume?" | |
| tailored-resume-studio.tsx:898 | "This erases the tailored resume content, the rendered PDF, and any unsaved edits in the studio. This can't be undone." | "This replaces the tailored resume and its PDF with a fresh copy of your base resume, and drops unsaved edits. Version history keeps the saved version." | **bug** (D10.10): `materialize-resume` records a version (`application_writes.stage_resume_update`), so the saved content can be restored |
| tailored-resume-studio.tsx:899, :912 | "Rebuild from base" / "Rebuilding…" | "Start over" / "Starting over…" | |
| diff-review.tsx:28 | provenance chip "KB auto" | "From your career history" | KB |
| diff-review.tsx:56-63, :78-92 | "Summary rewritten" "Contact details changed" "Bullet added/removed/reworded" "Entry added/removed" "Entry unhidden/hidden" "Skills group changed" "Section added/removed/changed/unhidden/hidden" | "…", "Bullet added" (kept), "Item added", "Item removed", "Item shown", "Item hidden", "Skill group changed", "Section shown", "Section hidden"; "Extra sections" → "Other sections" | entry, unhidden, skills group |
| diff-review.tsx:398 | title "Applied from your own library/Career KB evidence" | "Taken from your career history" | slash, KB, library, evidence |
| diff-review.tsx:400 | title "Came from a gap resolution you made" | "From an answer you gave" | jargon |
| diff-review.tsx:401 | title "Wording the tailoring model chose" | "Wording written by AI" | "model" |
| diff-review.tsx:428 | "reverted — unsaved" | "Undone. Not saved yet." | em dash |
| diff-review.tsx:444 | "Revert" | "Undo" | |
| diff-review.tsx:451-454 | "Reads as a fragment" "Tense mismatch" "Summary out of sync" "Dangling reference" | "Incomplete sentence" "Mixed tenses" "Summary doesn't match" "Refers to something missing" | jargon |
| diff-review.tsx:538-541 | "Not assessed" "Blocker" "Serious" | "Not checked" "Must fix" "Serious" | glossary; the health report uses the same words |
| diff-review.tsx:562-563 | eyebrow "Structural gates" | "Must fix" | gate |
| diff-review.tsx:587 | "Hygiene" | "Clean-up" | |
| diff-review.tsx:653 | "Coherence" | "Flow and consistency" | |
| diff-review.tsx:686 | "No differences from your base resume." | "No changes from your base resume." | the header says changes |
| diff-review.tsx:718-721 | "Checking…" / "Re-run review checks" / "Run review checks" | "Checking…" / "Check again" / "Check wording" | |

### D4.5 Health report (`components/resume-health/*`, `lib/health-report.ts`), L3b

The backend writes each finding's label, issue, how and question, and each gate's label, detail and fix
hint; D9 rewrites them (with the finding-id caution in D9.1).

| file:line | current | new | why (category) |
|---|---|---|---|
| health-report-page.tsx:320 | title "Resume health report" | "Health report" | one name |
| health-report-page.tsx:60-63 | filters "All" "Fix" "Ask" "Notes" | "All" "Fixes" "Questions" "Notes" | mixed parts of speech |
| health-report-page.tsx:178 | toast "Analyzed. Grade {g}." | "Check done. Grade {g}." | |
| health-report-page.tsx:180 | `toast.error(err.message)` | `couldnt("check the resume", err)` | D1.3 |
| health-report-page.tsx:231, :332 | load-error details | `errorDetail(…)` | D1.3 |
| health-report-page.tsx:281 | jump item "Gates" | "Must fix" | gate |
| health-report-page.tsx:304 | "Analyzing…" / "Re-analyze" / "Analyze" | "Checking…" / "Check again" / "Check health" | glossary |
| health-report-page.tsx:342-343 | "Not enough evidence to grade" | "Too little to grade" | evidence |
| lib/health-report.ts:480-506 | delta "+2 bullets in Experience entered at direct; 1 finding resolved; 1 classification changed." | "2 new bullets in Experience. 1 issue fixed. 1 rating changed." (the level key never prints) | raw-value (`entered at direct`), semicolons |
| health-report-page.tsx:386 | badge `{body.tier}` | early → "Early career", experienced → "Experienced", unknown → no badge | raw-value (`health_zones.compute_tier`) |
| lib/health-report.ts:67, :69 | "mean evidence 88 · capped to 69 by one serious gate" / "mean evidence 88" | "Score limited to 69 by one must-fix problem" / no line | jargon, case |
| finding-cards.tsx:316-329 | count chips "{n} Gate" "{n} Critical" "{n} Ask" "{n} Note" | "{n} must fix" "{n} critical" "{n} question" / "questions" "{n} note" / "notes" | **bug** (D10.8) "3 Note"; gate |
| health-report-page.tsx:410-412 | "{n} to address · resume v{n}" | "{n} left to fix · version {n}" | v12 |
| health-report-page.tsx:465 | "Ran against v{n} · the resume has changed since — re-analyze for current results" | "Your resume changed since this check. Check again to update it." | em dash, v12, re-analyze |
| health-report-page.tsx:481 | "No issues found. This resume looks solid." | "No issues found." | filler |
| health-report-page.tsx:486 | "The resume content couldn't be loaded, so findings can't be shown with their source text here. Open the editor to work through them." | "Couldn't load your resume text. Open the resume to fix these." | |
| health-report-page.tsx:494 | heading "Weakest evidence first" | "Biggest problems first" | evidence |
| health-report-page.tsx:571-572 | "No health report yet. Run an analysis to check this resume against general best practices. No job description needed." | "No health report yet. This checks your resume on its own, without a job description." | verbose; keeps "No health report yet." (pin `test_frontend_query_error_states.py:82`) |
| health-report-page.tsx:582 | "{n} change(s) applied · Re-analyze to update your grade" | "{n} change" / "changes" " applied. Check again to update your grade." | case, re-analyze |
| health-badges.tsx:31, :33 | "{n} gate · {n} critical · {n} ask · {n} note" / "no findings" | "{n} must fix, {n} critical, {n} questions, {n} notes" (plurals) / "No issues" | raw keys, plurals (aria-label and title) |
| health-badges.tsx:101-102, :147 | "Grade {g} · score {n} · {counts} — open report", "Grade {g} · score {n} — open report" | "Grade {g}, score {n}. Open report." | em dash |
| health-badges.tsx:146 | "Blocked — a fatal health gate is failing. Open the report." | "Has a must-fix problem. Open the report." | gate, fatal, em dash |
| health-badges.tsx:162 | chip "Blocked" | "Must fix" | glossary |
| finding-cards.tsx:83-87, :545 | levels "Direct/Outcome evidence" "Analogue/Scale evidence" "Adjacent/Specific, no metric" "Implied/Contribution is vague" "Unaddressed/Duty, not achievement" | "Shows a result" "Shows scale" "Specific, no number" "Vague" "Lists a duty" (the details become the labels) | scorer taxonomy, slash |
| finding-cards.tsx:190-191 | toasts "Automatic classification restored" / "Classification updated and report re-analyzed" | "Back to automatic rating" / "Rating changed. Report updated." | |
| finding-cards.tsx:195, :770, :1148, :1242, :1286, batch-ask-dialog.tsx:149, report-errors.ts:25 | `toast.error(err.message \| String(err))` | `couldnt("change the rating", err)`, `couldnt("apply the fix", err)`, `couldnt("mark it as OK", err)`, `couldnt("undo", err)`, `couldnt("check the template", err)`, `couldnt("write new wording", err)`; report-errors: `couldnt("apply the change", err)` | D1.3 |
| finding-cards.tsx:210, :300 | "Override classification" | "Change rating" | jargon |
| finding-cards.tsx:220 | aria "Evidence level" | "Rating" | evidence |
| finding-cards.tsx:236 | "Current: {label}. Saving re-runs the report." | "Now: {label}. Saving updates the report." | |
| finding-cards.tsx:241 | aria "Reason for overriding the evidence level · optional" | `<Label optional>Reason</Label>` | evidence, "· optional" |
| finding-cards.tsx:245 | placeholder "e.g. this metric lives in the next bullet" | remove | owner rule |
| finding-cards.tsx:258, :266 | "Re-analyzing…" / "Save override" | "Saving…" / "Save" | |
| finding-cards.tsx:292 | "More actions" | "More actions for this issue" | |
| finding-cards.tsx:336, :341 | type chips "Fix" / "Ask" | "Fix" / "Question" | |
| finding-cards.tsx:427-428 | "Custom-section bullets can't be applied from health yet — copy the rewrite into the editor." | "Can't apply this here yet. Copy the new wording into the resume." | em dash |
| finding-cards.tsx:520 | aria "Rewritten bullet" | "New wording" | |
| finding-cards.tsx:593, components/attention-zone.tsx:26 | badge "weighted higher" | "Counts more" | jargon, case |
| finding-cards.tsx:596 | "+{n} pts" | "+{n} points" | abbreviation |
| finding-cards.tsx:809-810 | "Saved draft is stale — the bullet changed" | "This bullet changed after you answered. Write the new wording again." | em dash, stale |
| finding-cards.tsx:859 | "Drafting…" / "Draft rewrite with this" | "Writing…" / "Write new wording" | |
| finding-cards.tsx:951 | heading "No score impact ({n})" | "Notes ({n}). These don't change your score." | matches the filter |
| finding-cards.tsx:1048 | "Condense" | "Shorten" | pin `test_frontend_health_report.py:90` |
| finding-cards.tsx:1145 | toast "Gate waived" | "Marked as OK" | waive |
| finding-cards.tsx:1168, :1293 | "Blocker" / "Not assessed" | "Must fix" / "Not checked" | glossary |
| finding-cards.tsx:1181-1182 | "Waiving lifts this gate's score cap for this resume. It doesn't change the resume. The gate stays waived across future edits until you unwaive it here." | "Your score won't be limited by this any more. Your resume isn't changed. You can undo this here." | keeps "doesn't change the resume" |
| finding-cards.tsx:1187 | aria "Reason for waiving this gate" | "Why is this OK?" | waive |
| finding-cards.tsx:1190 | placeholder "e.g. this template is certified elsewhere" | remove | owner rule, certify |
| finding-cards.tsx:1200, :1207 | "Waiving…" / "Confirm waive" | "Saving…" / "Mark as OK" | |
| finding-cards.tsx:1214 | "Waive…" | "Mark as OK…" | |
| finding-cards.tsx:1239 | toast "Waiver removed" | "Check turned back on" | |
| finding-cards.tsx:1248 | "{label} (waived)" | "{label} (marked OK)" | |
| finding-cards.tsx:1255 | "…" / "Unwaive" | "Undoing…" / "Undo" | a bare ellipsis said nothing to a screen reader |
| finding-cards.tsx:1261 | "Waiver reason: " | "Reason: " | |
| finding-cards.tsx:1280 | thrown "No template on this resume" | "This resume has no template selected." | |
| finding-cards.tsx:1284 | toast "Template certified. Re-running the report." | "Template checked. Updating the report." | certify |
| finding-cards.tsx:1298 | "{label} — not checked. This template hasn't been certified." | "{label} wasn't checked because this template hasn't been checked yet." | em dash, certify |
| finding-cards.tsx:1309 | "Certifying…" / "Certify" | "Checking…" / "Check template" | glossary |
| finding-cards.tsx:1378 | "Resolved · {label}" | "Fixed: {label}" | |
| lib/health-report.ts:31 | STALE_APPLY_HINT "This text changed since the analysis — re-analyze before applying." | "This text changed. Check again before applying." | em dash |
| lib/health-report.ts:34 | CONTENT_CHANGED_HINT "This text changed since the analysis — re-analyze to get fresh suggestions" | "This text changed. Check again for new suggestions." | em dash, no stop |
| report-errors.ts:13 | toast action "Re-analyze" | "Check again" | |
| lib/health-report.ts:223-232 | rule titles "Listed but never demonstrated" "Trailing punctuation on a skill" "Trailing punctuation on a certification" "Skill listed in more than one group" "Duplicate certification" "Skill reads like a sentence" "Bullet is too long" "Bullet is too short" "Too many bullets" "Summary is missing" | "Skill not shown in any bullet" "Extra punctuation after a skill" "Extra punctuation after a certification" "Skill in more than one group" "Certification listed twice" "Skill reads like a sentence" "Bullet is too long" "Bullet is too short" "Too many bullets" "No summary" | jargon; bullet stays (owner) |
| lib/health-report.ts:354-360 | units "users" "rows" "%" "hours saved" "minutes saved" "$" "other" | drop "rows"; "Other" | jargon; the unit ids stay |
| metric-ask-input.tsx:95, :122, :131 | placeholders "e.g. 5,000", "e.g. tickets", "e.g. 6 months"; names only by `aria-label` | remove all three; give each a visible `Label`: "Number", "Unit" (the custom one: "Your unit"), "Time period (optional)" | owner rule; these fields had no visible label |
| metric-ask-input.tsx:130 | aria "Timeframe (optional)" | `<Label optional>Time period</Label>` | one marker |
| batch-ask-dialog.tsx:245 | "Couldn't safely rewrite" | "Couldn't rewrite this one. Edit it yourself." | next step |
| batch-ask-dialog.tsx:249 | "Stale — re-analyze" | "Changed. Check again." | em dash |
| batch-ask-dialog.tsx:301 | "Drafting…" / "Draft {n} rewrite(s)" | "Writing…" / "Write {n} new version" / "versions" | |
| demonstrate-skill-dialog.tsx:155 | "Demonstrate {skill}" | "Show where you used {skill}" | scorer word |
| demonstrate-skill-dialog.tsx:158 | "Pick one bullet, then one line on how {skill} shows up there." | "Pick a bullet, then say in one line how you used {skill} there." | missing verb |
| demonstrate-skill-dialog.tsx:211 | label "How {skill} shows up in this bullet" | "How you used {skill} in this bullet" | plainer; pin `test_frontend_placeholders.py:556` |
| demonstrate-skill-dialog.tsx:255, :267 | "Drafting…" / "Draft rewrite" | "Writing…" / "Write new wording" | |

### D4.6 Version history (`components/resume-versions/*`), L3b

| file:line | current | new | why (category) |
|---|---|---|---|
| version-history-sheet.tsx:24-30 | sources "Created" "Manual edit" "Edit" "Chat" "Tailored" "Import" "Restore" | "Created" "Your edit" "Suggested edit" "Assistant" "Tailored" "Imported" "Restored" | mixed parts of speech; "Chat" is the Assistant |
| version-history-sheet.tsx:111 | `toast.error(err.message)` | `couldnt("restore the version", err)` | D1.3 |
| version-history-sheet.tsx:138 | "v{n}" (mono) | "Version {n}" | v12 |
| version-history-sheet.tsx:151 | "current" | "Current" | case |
| version-history-sheet.tsx:155 | `new Date().toLocaleString()` | `formatAbsoluteDateTime` | the app's date format. **[behaviour]** display only |
| version-history-sheet.tsx:158 | `v.summary` (server-written) | unchanged here; D9 rewrites the summaries | |
| version-history-sheet.tsx:198 | "Could not load history." | `LoadErrorState` "Couldn't load Version history." with Try again | error form; no retry. **[behaviour]** adds a retry |
| version-history-sheet.tsx:223 | "▸ {n} manual edits (v3–v7)" | "{n} edits (versions 3 to 7)", the glyph replaced by a chevron icon with `aria-expanded` | the glyph was read aloud |
| version-diff-view.tsx:25 | "No content changes." | "No changes to the text." | formatting-only saves land here |
| version-diff-view.tsx:72 | "Loading diff…" | "Loading changes…" | diff |
| version-diff-view.tsx:75 | "Could not load this version." | "Couldn't load this version." | contraction |

### D4.7 Templates (`app/templates/**`, `components/templates/*`), L3b

The template editor is an expert code surface; engine names (LaTeX, Typst) stay there and leave the rest of
the app.

| file:line | current | new | why (category) |
|---|---|---|---|
| app/templates/page.tsx:84, :110, :125, :139, :152, :162 | `toast.error(err.message)` | `couldnt("create the template", err)`, `couldnt("duplicate the template", err)`, `couldnt("set the default template", err)`, `couldnt("check the template", err)`, `couldnt("archive the template", err)`, `couldnt("delete the template", err)` | D1.3 |
| app/templates/page.tsx:199 | load-error detail | `errorDetail(templates.error)` | D1.3 |
| app/templates/page.tsx:107 | toast "Duplicated" | "Template duplicated" | names its object |
| app/templates/page.tsx:122 | toast "Default updated" | "Default template changed" | |
| app/templates/page.tsx:136 | toast "Re-validated" | "Template checked" | |
| app/templates/page.tsx:137 | toast "Validation failed" | "This template has errors. Open it to see them." | next step |
| app/templates/page.tsx:149 | toast "Restored" / "Archived" | "Template restored" / "Template archived" | |
| app/templates/page.tsx:159 | toast "Deleted" | "Template deleted" | |
| app/templates/page.tsx:169 | "This removes the template source and its compiled assets. This can't be undone." | "This deletes the template. Resumes using it switch to the default template. You can't undo this." | compile; states the consequence (verified: `template_registry` falls back to the default) |
| app/templates/page.tsx:185 | aria-label "Show archived templates" | remove | as on Base resumes |
| app/templates/page.tsx:232 | "Re-validate" | "Check again" | |
| app/templates/page.tsx:277 | label "ID" | "Short name" | jargon (the field stays) |
| app/templates/page.tsx:284 | placeholder "e.g. classic_serif" | remove | the hint states the format; pin `test_template_slug_rule_stays_on_screen` |
| app/templates/page.tsx:291 | "That ID has a character that isn't allowed." | "That short name has a character that isn't allowed." | the field's new name; the error keeps naming the problem while the hint above states the rule (the decision `test_template_slug_rule_stays_on_screen` records) |
| app/templates/page.tsx:296 | label "Display name" | "Name" | |
| components/templates/template-gallery.tsx:39-40 | engine chips "LaTeX" / "Typst" | hide on the gallery; show in the editor only | engine talk |
| template-gallery.tsx:75 | title "A strict PDF text extractor joins words in this template's output, so some ATS may misread it. Prefer a certified template." | "Applicant tracking systems may read some words in this template as joined together. Pick another template to be safe." | certify, jargon |
| template-gallery.tsx:77 | badge "⚠ ATS spacing" | "ATS may misread" with the ⚠ as an `aria-hidden` icon | the glyph was read aloud; pin `test_frontend_color_roles.py:730` |
| template-gallery.tsx:130 | tooltip "{name} · {id}" | "{name}" | id |
| template-gallery.tsx:219 | aria-label `{name ?? id}` | `{name ?? "Untitled template"}` | id fallback |
| template-gallery.tsx:132 | tooltip "Knobs {n}/{m}" | "Supports {n} of {m} formatting options" | knobs, ratio |
| template-gallery.tsx:157-159 | `{template.last_error}` on the card and in its title | "Has errors. Open to fix." | raw compiler output on a card |
| components/templates/requires-tex-badge.tsx:13 | title "TeX is not installed where the backend runs. A resume using this template renders through a Typst template instead, and the render says so, until TeX is installed." | "This template needs extra software that isn't installed. Resumes using it use a similar template for now." | render, engine names |
| requires-tex-badge.tsx:15 | badge "requires TeX" | "Needs setup" | pin `test_frontend_color_roles.py:729` |
| components/templates/template-thumbnail.tsx:45 | alt "{name} preview, rendered with a sample resume" | "Preview of {name} with a sample resume" | render |
| template-thumbnail.tsx:46 | "Not validated" | "No preview yet" | update `_NOT_INPUTS` |
| template-thumbnail.tsx:51 | chip "needs re-validation" | "Preview out of date" | case, jargon |
| template-thumbnail.tsx:53 | "Edited since its last validation, so the preview shows the previous design. Use Re-validate in the card menu to refresh." | "Changed since this preview. Choose Check again in the ⋯ menu to update it." | jargon |
| template-select.tsx:195 | fallback "server default" | "Default" | "server" |
| template-select.tsx:203 | "Every ready template is archived. Restore one from Templates to pick it here." | "All templates are archived. Restore one on the Templates page." | |
| app/templates/[id]/page.tsx:82 | toast "Saved" | "Template saved" | |
| app/templates/[id]/page.tsx:84, :121, :139, :184 | `toast.error(err.message)` | `couldnt("save the template", err)`, `couldnt("update the preview", err)`, `couldnt("save the default formatting", err)`, `couldnt("set the default template", err)` | D1.3 |
| app/templates/[id]/page.tsx:116 | toast "Compiled" | "Preview updated" | compile |
| app/templates/[id]/page.tsx:118 | toast "LaTeX error. See the preview panel." | "The template has an error. See the preview for details." | wrong for Typst templates |
| app/templates/[id]/page.tsx:194 | load-error detail | `errorDetail(tq.error)` | D1.3 |
| app/templates/[id]/page.tsx:258 | h1 `{display_name ?? id}` | `{display_name ?? "Untitled template"}` | id |
| app/templates/[id]/page.tsx:267 | "unsaved" | "Unsaved changes" | the studio's words; pin `test_frontend_color_roles.py:731` |
| app/templates/[id]/page.tsx:271 | tab "Knobs" | "Formatting" | its panel's heading |
| app/templates/[id]/page.tsx:288 | "Recompiling…" / "Recompile" | "Updating…" / "Update preview" | compile |
| app/templates/[id]/page.tsx:298, app/templates/page.tsx:238 | "Set default" | "Make default" | |
| app/templates/[id]/page.tsx:325 | "Defaults for this theme. A resume that selects it inherits these, then layers its own overrides on top." | "Starting settings for resumes that use this template. Each resume can change them." | "theme", jargon |
| app/templates/[id]/page.tsx:360-361 | "Last compile failed. Fix the source and Recompile." | "The template has an error. Fix the code, then update the preview." | compile |
| app/templates/[id]/page.tsx:371, :374-375 | "Recompile to generate a preview." | "Update the preview to see it." | compile |

### D4.8 Shared pieces (`role-category-picker.tsx`, `lib/describe-edit.ts`)

| file:line | current | new | why (category) |
|---|---|---|---|
| role-category-picker.tsx:129 | `toast.error(err.message)` | `couldnt("set the role", err)` | D1.3 |
| role-category-picker.tsx:137 | title "Suggested — click to confirm or pick another" | "Suggested. Confirm it or pick another." | em dash, "click" |
| role-category-picker.tsx:166 | placeholder "e.g. Data Scientist" | remove | owner rule (`"aria-label": ariaLabel = "Target role"` names it; pin `test_every_role_picker_input_has_a_name` unchanged) |
| role-category-picker.tsx:224 | "What this resume is for. It labels generated files and tells the tracker which roles you already have a base resume for." | "The kind of job this resume is for." | jargon |
| lib/describe-edit.ts:144, :210 | "a custom section", "Add a custom section" | "another section", "Add another section" | glossary |
| lib/describe-edit.ts:155-156, :175, :180, :182 | "an entry in {section}", "Add an entry to …", "Edit an entry in …", "Remove an entry from …" | "an item in …", "Add an item to …", "Edit an item in …", "Remove an item from …" | entry |
| lib/describe-edit.ts:186 | "Replace a skills group" | "Replace a skill group" | glossary |
| lib/describe-edit.ts:197 | "Add {item} to a new {cat} skills group" | "Add {item} to a new {cat} skill group" | glossary |
| lib/describe-edit.ts:206 | "Remove every certification" | "Remove all certifications" | |

**Dropped from part 2, with the reason.** Rows marked `ok` whose optional polish does not touch a glossary
term ("Send to resume" chips, "Back to application", "Download PDF", zoom labels, `Label`s already plain);
`kb-sync-pill.tsx` (L4, D5); `components/setup/dropzone.tsx` (L6, D7); "Bullets" group label, "Add bullet"
and the describe-edit "bullet" wording (the owner chose bullet, so part 2's point rows are dropped);
`lib/extra-sections.ts` titles on the PDF (Title Case is the resume's style).

### D4.9 Pins (L3a, L3b)

| test | old | new |
|---|---|---|
| `frontend/lib/studio.test.ts:47` | `"Rendering PDF…"` | `"Updating PDF…"` |
| `frontend/lib/studio.test.ts:48` | `"Re-scoring…"` | `"Updating score…"` |
| `frontend/lib/studio.test.ts:52` | `"No PDF yet. Save to render one."` | `"No PDF yet. Save to create one."` |
| `frontend/lib/studio.test.ts:55` | `"No PDF yet. Generate one from More resume actions (⋯).",` | `"No PDF yet. Choose Create PDF in the ⋯ menu.",` |
| `test_frontend_studio.py:130` | `'"Regenerate PDF"' in _BASE` | `'"Update PDF"' in _BASE and '"Regenerate PDF"' not in _BASE` |
| `test_frontend_studio.py:161` | `'if (opts?.announce) toast.success("Tailored resume re-scored");'` | `'if (opts?.announce) toast.success("ATS score updated");'` |
| `test_frontend_studio.py:195` | `"No PDF yet. Generate one from More resume actions (⋯)." in _STUDIO_LIB` | `"No PDF yet. Choose Create PDF in the ⋯ menu." in _STUDIO_LIB` and `"More resume actions" not in _STUDIO_LIB` (D10.9) |
| `test_frontend_studio.py:206` | `'"No PDF yet. Save to render one."'` | `'"No PDF yet. Save to create one."'` |
| `test_frontend_studio.py:425` | `"Discard your JSON edits?" in _RAW_JSON` | `"Discard your code edits?" in _RAW_JSON` |
| `test_frontend_focus.py:291` | `'<Button onClick={apply}>Apply JSON</Button> <Button ref={cancelRef} …'` | the same with `>Apply</Button>` |
| `test_frontend_health_report.py:24` | `"Not enough evidence to grade"` | `"Too little to grade"` |
| `test_frontend_health_report.py:32` | `"Weakest evidence first"` | `"Biggest problems first"` |
| `test_frontend_health_report.py:39` | `"Override classification"` | `"Change rating"` |
| `test_frontend_health_report.py:44-45` | `"Not assessed"`, `"hasn&apos;t been certified" … or "hasn't been certified"` | `"Not checked"`, `"hasn&apos;t been checked yet" … or "hasn't been checked yet"` |
| `test_frontend_health_report.py:59` | `"re-analyze for current results"` | `"Check again to update it."` |
| `test_frontend_health_report.py:73` | `"Re-analyze to update your grade"` | `"Check again to update your grade."` |
| `test_frontend_health_report.py:79` | `"Blocked" in _BADGES` | `"Must fix" in _BADGES` |
| `test_frontend_health_report.py:90` | `"Condense" in _CARDS` | `"Shorten" in _CARDS` |
| `frontend/lib/health-report.test.ts:40, :49` | `"mean evidence 88 · capped to 69 by one serious gate"`, `"mean evidence 88"` | `"Score limited to 69 by one must-fix problem"`, and the uncapped case returns `null`, so the page renders no line. **[behaviour]** `scoreCompositionLine` may now return `null`; `health-report-page.tsx` renders nothing then |
| `frontend/lib/health-report.test.ts:123, :275` | `"Listed but never demonstrated"` | `"Skill not shown in any bullet"` |
| `frontend/lib/health-report.test.ts:238` | `"+2 bullets in Awards & Honors entered at implied."` | `"2 new bullets in Awards & Honors."` |
| `frontend/lib/describe-edit.test.ts:61` | `"Add AWS to a new Cloud skills group"` | `"Add AWS to a new Cloud skill group"` |
| `frontend/lib/describe-edit.test.ts:90` | `"Remove an entry from Projects"` | `"Remove an item from Projects"` (the test title "names no entry" becomes "names no item") |
| `test_frontend_color_roles.py:729-731` | `"requires TeX"`, `"⚠ ATS spacing"`, `">unsaved<"` | `"Needs setup"`, `"ATS may misread"`, `">Unsaved changes<"` (the contrast cases keep measuring the same chips) |
| `test_frontend_query_error_states.py:76` | `("app/base-resumes/page.tsx", "No career-track resumes yet.")` | `("app/base-resumes/page.tsx", "No base resumes yet. Create one to start.")` |
| `test_frontend_placeholders.py:68-75` `_NOT_INPUTS` | `"Choose a base resume"`, `"Choose base resume"`, `"Not rendered yet"`, `"Not validated"` | `"Choose a resume"`, `"No PDF yet"`, `"No preview yet"` |
| `test_frontend_placeholders.py:522-534` `test_file_import_name_defaults_in_a_hint` | last step `'placeholder={mode === "file" ? undefined : "e.g. Machine Learning Engineer"}'` | drop that step; add `"placeholder=" not in src` |
| `test_frontend_placeholders.py:553-557` `test_demonstrate_skill_has_a_visible_label_and_no_placeholder` | `"How {skill} shows up in this bullet" in src` | `"How you used {skill} in this bullet" in src` |
| `test_frontend_placeholders.py:560-567` `test_metric_units_are_examples` | the three `e.g.` asserts | rename `test_metric_fields_have_visible_labels`: `"placeholder=" not in src`; `">Number</Label>" in src`; `">Your unit</Label>" in src`; `"optional>Time period</Label>" in src`; the `tickets`/`unit` asserts stay |
| `test_frontend_placeholders.py:644-654` `test_experience_end_date_empty_means_current` | `'placeholder="e.g. Jan 2023"'`, `'placeholder="e.g. Mar 2025"'`, `'hint="Leave empty for a current role."'` | `"placeholder=" not in editor`; `'hint="Month and year, like Jan 2023."' in editor`; `'hint="Leave empty if you still work here."' in editor` |
| `test_frontend_placeholders.py:657-670` `test_template_slug_rule_stays_on_screen` | the `placeholder="e.g. classic_serif"` step; `"That ID has a character that isn&apos;t allowed."` | drop the placeholder step and add `"placeholder=" not in src`; the last step becomes `"That short name has a character that isn&apos;t allowed."`; the count check stays |
| `test_frontend_placeholders.py` `_PASS_THROUGH` | `("components/resume-editor/field.tsx", "placeholder")`, `("components/resume-editor/contact-form.tsx", "placeholder")` | delete both rows (the prop is gone) |
| `test_frontend_placeholders.py`, `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_EXAMPLES_L3`, `_PENDING_L3` | delete |
| new, `test_frontend_plain_words.py` | none | `test_a_bullet_label_is_singular_in_its_slot`: `bullet-list.tsx` passes an item label ("Bullet") separate from the group label ("Bullets"), and `"Move ${label.toLowerCase()}"` no longer lowercases the group label (D10.8) |
| new, same file | none | `test_new_base_summary_hint_matches_a_prefilled_field`: `"Left blank on purpose" not in _read("components/base-resumes/new-base-resume-dialog.tsx")` and `"Check this summary, or clear it." in` it (D10.5) |
| new, same file | none | `test_undo_claims_match_version_history`: `"You can't undo this." not in` the tailored studio's Start over confirm and the extra-section delete confirm; `"Version history keeps" in` both (D10.10) |

### D4.10 Browser checks (L3)

1. Base studio: the header pill says "Add to career history (n)" (D5), the ⋯ menu has "Add from career
   history…", "Version history", "Copy resume ID", "Update PDF"; with no PDF the preview says "No PDF yet.
   Choose Create PDF in the ⋯ menu." With VoiceOver, the bullet list reads "Bullet 2 of 5", "Move bullet 2
   up".
2. Formatting panel: "Bullet style" shows its hint and the options are announced "Dot" and "Dash"; "Item
   spacing", "Spacing and margins".
3. Tailored studio: ⋯ Start over confirm names Version history; confirm, then open Version history: the
   previous content is there and restorable (the claim is true).
4. Health report: "Check health" → "Check again"; gate cards say "Must fix"; waive flow reads "Mark as OK",
   then "Undo"; the tier badge reads "Early career" or "Experienced"; a metric question shows three visible
   labels and no placeholder.
5. Templates: the gallery hides LaTeX and Typst chips; the editor's tabs read "Formatting" and "Code"; the
   header shows "Unsaved changes" in the amber style (contrast pin still passes); Update preview works.
6. 375px, dark mode: New base resume dialog tabs ("From career history", "Copy a resume", "From file",
   "Blank") scroll inside the row (C5) without clipping.

---

## D5. Career history pages and dialogs (lane L4)

`app/career/**`, `components/career/**` and `components/kb-sync-pill.tsx`. Source: audit part 2 (Career KB
list, item page, KB dialogs, shared pieces) and part 3 §2.4 (the resume import panel). Owner decisions
applied: **Career history** (page and prose), **item** (never entity or record), **bullet** (never point;
states Draft, Approved, Not used), "Career library" stays as the sidebar group. `points-list.tsx`'s two
origin labels are appendix A5 rows 20–21: **after A**. Code identifiers (`entity`, `KBPointOut`, `kb-inbox`,
routes `/career`, API `/api/kb/*`) stay.

**Mechanical renames in this lane** (one row each below where the sentence changes; these are the pure
swaps, checked with `rg -n 'Career KB|Knowledge Base|KB profile' frontend/app/career frontend/components/career
frontend/components/kb-sync-pill.tsx`: 21 hits at `8cac7cf9`):
- "Career KB" → "career history" in prose, "Career history" as a name or at a sentence start;
- "point(s)" → "bullet(s)" where it names a stored line; "career point" → "bullet";
- "entity/entities", "entry" (a stored record) → "item(s)".

| file:line | current | new | why (category) |
|---|---|---|---|
| app/career/page.tsx:63 | title "Career Knowledge Base" | "Career history" | owner decision |
| app/career/page.tsx:64 | subtitle "Your living record of roles, projects, education, and credentials." | "Your jobs, projects, education and certifications, in one place." | marketing tone |
| app/career/page.tsx:76 | "Add documents" (opens the upload dialog, which starts on its Resumes tab) | "Add files" | **bug** (D10.6): the button named documents but opened the resume import; the dialog title becomes "Add files" too (D7) |
| app/career/page.tsx:82 | "New entity" | "Add item" | entity |
| app/career/page.tsx:106 | tab "Basics" | "Profile" | holds Career profile and Exports |
| app/career/page.tsx:26-30 | tab "Custom sections" | "Other sections" | glossary |
| app/career/page.tsx:197-198 | "Custom sections (publications, awards, volunteer work, certifications) and the career facts connected to them." | "Publications, awards, volunteering and more." | said certifications live here (they have their own tab); "career facts" |
| app/career/page.tsx:201, :226 | "Add custom section" | "Add section" | glossary |
| app/career/page.tsx:206 | aria "Loading custom sections" | "Loading other sections" | |
| app/career/page.tsx:213, :221 | "Couldn't load custom sections." / "No custom sections yet" | "Couldn't load other sections." / "No other sections yet" | pin `test_frontend_query_error_states.py:70` |
| app/career/page.tsx:222-223 | "Add custom sections like publications, awards, presentations, or clearances to your Career Knowledge Base." | "Add publications, awards, talks and more." | KB, verbose |
| app/career/page.tsx:278 | "{title} and the career facts connected to them." | remove | restates the tab name |
| app/career/page.tsx:303 | "Capture a career update and let the AI create one, or add your first {singular} manually." | "Use Quick capture above, or add one yourself." | vague |
| career/first-run-import-card.tsx:47 | "Couldn't check your career data." | "Couldn't check your career history." | career data |
| career/first-run-import-card.tsx:48 | load-error detail | `errorDetail(entities.error)` | D1.3 |
| career/first-run-import-card.tsx:64-65 | "Each one becomes a base resume, and their shared history becomes your Career Knowledge Base." | "Each becomes a base resume, and your career history is built from them." | KB |
| career/capture-box.tsx:132 | "Type a recent win, or drop a certification or project doc and let it fill itself in." | "Type a recent win or add a document." | vague |
| career/capture-box.tsx:139, :145 | sr-only label "Career update"; placeholder "e.g. This week I shipped…" | make the label visible: "What did you do?"; remove the placeholder | owner rule; the field had no visible label |
| career/capture-box.tsx:163 | "Nothing is published to a resume until you approve it." | "Nothing goes on a resume until you approve it." | keeps the promise |
| career/capture-box.tsx:186 | "From document" | "Add document" | |
| career/capture-box.tsx:196 | "Capturing…" / "Add to inbox" | "Adding…" / "Add to drafts" | the card is "Drafts to review" now; pin `test_frontend_kb_editors.py:187` |
| career/capture-box.tsx:37 | toast "{n} point(s) added to inbox for {title}" | "{n} draft bullet" / "bullets" " added to {title}" | point |
| career/capture-box.tsx:50-55 | toast 'Created/Matched "{title}" ({entity_kind}) · {n} points to review' / "document attached" | "Added to {title}. {n} bullet" / "bullets" " to review." / "Document attached." | raw kind, "Matched" |
| career/capture-box.tsx:42, :69 | `toast.error(error.message)` | `couldnt("save your update", error)`, `couldnt("read the document", error)` | D1.3 |
| career/capture-box.tsx:102 | toast "Using the first file only." | "Only one file at a time. Using the first." | |
| career/inbox-panel.tsx:169 | "Draft inbox" | "Drafts to review" | "inbox" now names the Agent inbox |
| career/inbox-panel.tsx:185 | "{n} with unsaved edits skipped — save or discard them first." | "{n} with unsaved edits were skipped. Save or discard them first." | em dash |
| career/inbox-panel.tsx:192-193 | "Review AI-written points before they become part of your career record." | "Check AI-written bullets before they're added to your career history." | point, career record |
| career/inbox-panel.tsx:216 | "Inbox clear" | "Nothing to review" | pin `test_frontend_query_error_states.py:71` |
| career/inbox-panel.tsx:218 | "Captures and rewritten consolidation points will appear here." | "New bullets from Quick capture and imports appear here." | jargon |
| career/inbox-panel.tsx:125 | confirm "Approve {n} point(s)?" | "Approve {n} bullet" / "bullets" "?" | point |
| career/inbox-panel.tsx:128 | "They join your career record. {n} draft(s) with unsaved edits is/are not included." | "They'll be added to your career history. {n} with unsaved edits won't be." | career record, slash-like "is/are" |
| career/inbox-panel.tsx:129 | "They join your career record. You can still edit them there afterwards." | "They'll be added to your career history. You can still edit them later." | |
| career/inbox-panel.tsx:144 | toast "Approved {n} point(s)" | "Approved {n} bullet" / "bullets" | |
| career/inbox-panel.tsx:150 | toast "Approved {a} of {n} — {f} failed: {detail}" | "Approved {a} of {n}. Couldn't approve {f}. {errorDetail ?? "Try again."}" | em dash, raw detail |
| career/inbox-panel.tsx:158, :280, :291 | `toast.error(err.message)` | `couldnt("approve the bullets", err)`, `couldnt("save the draft", err)`, `couldnt("discard the draft", err)` | D1.3 |
| career/inbox-panel.tsx:320 | toast "Point approved" | "Bullet approved" | |
| career/inbox-panel.tsx:328-329 | sr label "Edit draft point" | "Edit draft bullet" | |
| career/inbox-panel.tsx:384 | "Original resume phrasings" | "Wording from your resumes" | |
| career/inbox-panel.tsx:392 | "{source.resume_key} · {source.section}" | "{resume name} · {section word}" (`useBaseResumeLabel`, the section-label map) | printed the slug and `extra_sections` |
| career/inbox-panel.tsx:408 | sr "Reassign draft" | "Move to another item" | jargon |
| career/inbox-panel.tsx:417 | toast "Draft reassigned to {title}" | "Moved to {title}" | |
| career/entity-card.tsx:55 | fallback `{entity.status \|\| "Unknown"}` (unmapped status prints raw) | map through the status labels, else "Unknown" | raw-value |
| career/entity-card.tsx:82 | fallback "Independent" | render nothing (no second line) | **bug** (D10.7): a claim the user never made |
| career/entity-card.tsx:46-50 | kind "Custom section" | "Other section" | glossary |
| career/entity-card.tsx:127 | "{n} points" | "{n} bullet" / "bullets" | **bug** (D10.8) "1 points"; point |
| career/entity-card.tsx:129 | "{n} drafts" | "{n} draft" / "drafts" | same bug |
| career/entity-card.tsx:131 | "{n} docs" | "{n} document" / "documents" | same bug; abbreviation |
| career/profile-panel.tsx:41 | "Couldn't load your KB profile." | "Couldn't load your profile." | KB |
| career/profile-panel.tsx:106 | `toast.error(err.message)` | `couldnt("save your profile", err)` | D1.3 |
| career/profile-panel.tsx:122, :266 | "Shared identity, skills, and generation context." | "Your contact details and skills, shared by all your resumes." | jargon |
| career/profile-panel.tsx:135-149, :218, :372 | hand-written "· optional" spans | `<Label optional>` | D1.2 |
| career/profile-panel.tsx:157 | label "Skill inventory" | "Skills" | the read view says Skills |
| career/profile-panel.tsx:158 | hint "Named groups can be merged into base resumes." | "Group your skills. You can add a group to any resume." | jargon |
| career/profile-panel.tsx:176 | label "Category" | "Group name" | glossary |
| career/profile-panel.tsx:185 | placeholder "e.g. ML Ops" | remove | owner rule |
| career/profile-panel.tsx:218, :341 | "Identity notes" | "Private notes" | jargon |
| career/profile-panel.tsx:221 | hint "Private context such as visa timeline, target roles, location constraints." | "Only you and the AI see these, such as visa timing or where you can work." | says who sees it (no "e.g.") |
| career/profile-panel.tsx:345 | "No private identity notes added." | "No private notes." | |
| career/exports-card.tsx:26 | toast "career.md refreshed" | "Career history file updated" | raw file name |
| career/exports-card.tsx:28 | `toast.error(err.message)` | `couldnt("update the file", err)` | D1.3 |
| career/exports-card.tsx:35 | "Exports" | "Download" | |
| career/exports-card.tsx:37 | "A portable Markdown snapshot derived from your Career KB." | "A text file of your whole career history." | KB, jargon |
| career/exports-card.tsx:53 | "career.md" | "Career history file" (the download name stays `career.md`) | |
| career/exports-card.tsx:56 | "Generated {date}" / "Not generated yet" | "Updated {date}" / "Not created yet" | |
| career/exports-card.tsx:78 | "Refresh" | "Update" | |
| career/entity-detail.tsx:97-111 | "This permanently removes the entity, its points, source documents, and provenance history." | "This permanently deletes the item, its bullets and documents. You can't undo this." | entity, point; keeps "permanently" |
| career/entity-detail.tsx:102, :252 | `toast.error(err.message)` | `couldnt("delete the item", err)`, `couldnt("save the item", err)` | D1.3 |
| career/entity-detail.tsx:138, :170 | "Back to Career KB", back link "Career KB" | "Back to career history", "Career history" | KB |
| career/entity-detail.tsx:176 | "Send to resume" | "Add to a resume" | glossary |
| career/entity-detail.tsx:74-79 | kind "Custom section" | "Other section" | |
| career/entity-detail.tsx:294-318 | hand-written "· optional" | `<Label optional>` | D1.2 |
| career/entity-detail.tsx:300 | placeholder "e.g. Acme Labs" | remove | owner rule |
| career/entity-detail.tsx:312, :324 | placeholders "e.g. Jan 2025", "e.g. Mar 2025" | remove; Start date gains hint "Month and year, like Jan 2025." | owner rule |
| career/points-list.tsx:37-49 | states "Draft" "Approved" "Retired" | "Draft" "Approved" "Not used" | owner decision |
| career/points-list.tsx:56-62 | origins "Manual" "Document" (A5: "Assistant") "Consolidated" (A5: "Connected agent") "Gap answer" "Base sync" | "You" "Document" "Assistant" "Merged" "Connected agent" "Your answer" "From a resume" | after A; pipeline names on every bullet |
| career/points-list.tsx:66-69 | provenance "Authored" "Stated" "Derived" "Can't confirm" | "You wrote it" "You said it" "AI inferred" "Not confirmed" | jargon |
| career/points-list.tsx:94-95 | "Career points" | "Bullets" | point |
| career/points-list.tsx:100-101 | "Approved points are ready to send to a resume." | "Approved bullets are ready to add to a resume." | |
| career/points-list.tsx:107 | "No career points yet" | "No bullets yet" | |
| career/points-list.tsx:109 | "Capture an update or upload a source document to get started." | "Add an update or a document to start." | |
| career/points-list.tsx:142-176 | toasts "Point updated" "Point deleted" "Point moved to drafts" "Point restored" "Point approved" "Point retired" | "Bullet updated" "Bullet deleted" "Bullet moved to drafts" "Bullet restored" "Bullet approved" "Bullet no longer used" | owner decision |
| career/points-list.tsx:145, :154 | `toast.error(err.message)` | `couldnt("update the bullet", err)`, `couldnt("delete the bullet", err)` | D1.3 |
| career/points-list.tsx:183 | confirm "Delete this point?" | "Delete this bullet?" | |
| career/points-list.tsx:186 | "Its prior resume usage stays in historical resume versions, but this provenance link will be removed." | "Resumes that used it keep their text." | jargon |
| career/points-list.tsx:187 | "This permanently removes the point from the Career KB." | "This permanently deletes the bullet. You can't undo this." | KB |
| career/points-list.tsx:188 | "Delete point" | "Delete bullet" | |
| career/points-list.tsx:204-205 | sr "Edit career point" | "Edit bullet" | |
| career/points-list.tsx:250-301 | "Edit point" "Approve point" "Retire point" "Restore point" "Delete point" | "Edit bullet" "Approve bullet" "Stop using" "Use again" "Delete bullet" | owner decision |
| career/points-list.tsx:322 | title "Used in: {resume_key, …}" | "Used in: {resume names}" (`useBaseResumeLabel`) | printed slugs |
| career/points-list.tsx:324 | "in {n} resume(s)" | "On {n} resume" / "resumes" | |
| career/points-list.tsx:330 | title "At least one resume still has an older phrasing" | "A resume still uses older wording." | |
| career/points-list.tsx:332 | chip "Drifted" | "Wording differs" | jargon |
| career/points-list.tsx:345 | title "This point predates groundedness labels" | "Added before we tracked where bullets come from." | jargon |
| career/points-list.tsx:350 | "unlabeled" | "Unknown source" | case, jargon |
| career/points-list.tsx:375 | aria "Point state: {s}. Change state" | "Status: {s}. Change status" | "state" vs "status" |
| career/notes-editor.tsx:51 | toast "Context notes saved" | "Notes saved" | |
| career/notes-editor.tsx:53 | toast "Notes not saved: {message}" | `couldnt("save your notes", err)` | error form |
| career/notes-editor.tsx:122 | "Context notes" | "Notes" | jargon |
| career/notes-editor.tsx:124 | "Private context for future AI-generated career materials." | "Private details that help AI write about this. Never shown on a resume." | says who sees it |
| career/notes-editor.tsx:150 | hint "Stack, scale, constraints, collaborators, and what you owned." | "Tools, team size, limits, who you worked with, and what you owned." | "Stack" |
| career/notes-editor.tsx:187, :189 | "No context notes yet" / "Add details that do not belong on a resume." | "No notes yet" / "Add details that don't belong on a resume." | |
| career/notes-editor.tsx:114, :198 | lines starting "⚠ stale?", heading "Review possibly stale facts" | strip the marker in display; heading "Check these: they may be out of date" | machine marker shown verbatim |
| career/documents-panel.tsx:44 | toast "Document uploaded and drafts minted" | "Document added. New bullets are ready to review." | mint |
| career/documents-panel.tsx:45 | toast "Document uploaded ({ingest_status})" | "Document added" | raw status |
| career/documents-panel.tsx:50, :59, :68 | `toast.error(err.message)` | `couldnt("add the document", err)`, `couldnt("read the document again", err)`, `couldnt("delete the document", err)` | D1.3 |
| career/documents-panel.tsx:56 | toast "Document reprocessed" | "Document read again" | |
| career/documents-panel.tsx:65 | toast "Source document deleted" | "Document deleted" | |
| career/documents-panel.tsx:84 | "The source file will be removed. Points already minted from it remain in the Career KB." | "Bullets made from it stay." | mint, KB |
| career/documents-panel.tsx:95 | "Source documents" | "Documents" | |
| career/documents-panel.tsx:100 | "Evidence that can mint reviewable draft points." | "We read these to suggest bullets for you to review." | mint, evidence |
| career/documents-panel.tsx:115, :120 | aria "Upload source document", "Drop a source file" | "Upload document", "Drop a file here" | |
| career/documents-panel.tsx:121 | "PDF, DOCX, image, text, or Markdown · 10 MB max" | "PDF, Word, image or text, up to 10 MB" | jargon |
| career/documents-panel.tsx:129 | "Extracting and minting…" | "Reading…" | mint |
| career/documents-panel.tsx:135-136 | "No source documents yet" / "Uploads and their extraction status appear here." | "No documents yet" / remove | |
| career/documents-panel.tsx:162 | `ingest_summary` (server-written) | unchanged here; D9 | |
| career/documents-panel.tsx:176 | "Re-mint" | "Read again" | mint |
| career/documents-panel.tsx:222 | status chip `{status}` via CSS capitalize ("Minted", "Extracted", "Failed") | minted → "Done", extracted → "Read, no bullets", failed → "Couldn't read" | raw status |
| career/timeline-panel.tsx:31-32 | "Timeline" / "Recent changes to this career item." | "Activity" / remove | restates the title |
| career/timeline-panel.tsx:38 | "Changes will appear here as they happen." | remove | filler |
| career/timeline-panel.tsx:44 | event labels (server-written) | unchanged here; D9 ("— added by mcp") | |
| career/new-entity-dialog.tsx:189 | "New career item" | "Add item" | |
| career/new-entity-dialog.tsx:191 | "Add a career record manually." | remove | career record |
| career/new-entity-dialog.tsx:196 | label "Category" | "Type" | also the skill-group label |
| career/new-entity-dialog.tsx:38-42 | kind "Custom section" | "Other section" | |
| career/new-entity-dialog.tsx:220 | "Section presets" | "Common sections" | jargon |
| career/new-entity-dialog.tsx:259 | placeholder "e.g. Publications, Volunteer Work" | remove | owner rule |
| career/new-entity-dialog.tsx:272 | "Section type" | "Layout" | |
| career/new-entity-dialog.tsx:285-286 | "Entries" / "Titled items with heading & details" | "Items" / "Each with a title and details" | entry, ampersand |
| career/new-entity-dialog.tsx:304-305 | "Bullets" / "Simple list of bullet points" | "List" / "A simple list" | |
| career/new-entity-dialog.tsx:316 | "Entry Heading" / "Project Name" / "Title / Role" | "Heading" / "Project name" / "Job title" | case, slash |
| career/new-entity-dialog.tsx:324-331 | five title placeholders ("e.g. Best Paper Award" … "e.g. Senior Data Scientist") | remove all | owner rule |
| career/new-entity-dialog.tsx:341 | "Subheading / Issuer" / "Organization" | "Issued by" / "Organization" | slash |
| career/new-entity-dialog.tsx:342-376 | hand-written "· optional" | `<Label optional>` | D1.2 |
| career/new-entity-dialog.tsx:350-355 | four organization placeholders | remove all | owner rule |
| career/new-entity-dialog.tsx:370, :382 | "e.g. Jan 2025", "e.g. Mar 2025" | remove; Start date hint "Month and year, like Jan 2025." | owner rule |
| career/new-entity-dialog.tsx:411-412 | "Creating this bullet-list section entity in the Knowledge Base. You can add and approve bullet points on it after creation." | "You can add bullets after you create it." | entity, KB |
| career/new-entity-dialog.tsx:424 | "Close" | "Cancel" | |
| career/new-entity-dialog.tsx:434 | "Adding…" / "Add career item" | "Adding…" / "Add item" | |
| career/new-entity-dialog.tsx:154 | toast "{title} added to Career KB" | "{title} added" | KB |
| career/new-entity-dialog.tsx:161 | `toast.error(err.message)` | `couldnt("add the item", err)` | D1.3 |
| career/merge-entity-dialog.tsx:91 | toast "Merged into {title} — {n} point(s) moved" | "Merged into {title}. Moved {n} bullet" / "bullets" | em dash |
| career/merge-entity-dialog.tsx:99 | `toast.error(err.message)` | `couldnt("merge the items", err)` | D1.3 |
| career/merge-entity-dialog.tsx:121 | kindLabel raw `source.kind` or "custom section" | the kind labels map ("other section") | raw-value |
| career/merge-entity-dialog.tsx:156 | "Moves {n} points and {n} documents onto {target}; {source} is removed. This cannot be undone." | "{n} bullets and {n} documents move to {target}, and {source} is deleted. You can't undo this." | semicolon, "cannot" |
| career/merge-entity-dialog.tsx:157 | "Fold {source} into another {kind} entry. Its points and documents move across; it is removed." | "Combine {source} with another {kind}. Its bullets and documents move over." | jargon, semicolon |
| career/merge-entity-dialog.tsx:170 | aria "Filter merge targets by title" | "Search by title" | jargon (the placeholder "Search by title…" stays, a named prompt) |
| career/merge-entity-dialog.tsx:190-191 | "Nothing to merge into — a target has to be another active entry under/of the same kind." | "Nothing to combine with. You need another {kind} that isn't archived." | em dash, entry |
| career/merge-entity-dialog.tsx:225 | live region "{n} target(s) matching "{q}"" | "{n} result" / "results" | jargon |
| career/merge-entity-dialog.tsx:258 | "Merging…" / "Merge" | keep | "Merge" is the menu item's word |
| career/send-to-resume-dialog.tsx:56 | chip "Kept as-is" | "Kept as is" | as-is |
| career/send-to-resume-dialog.tsx:132 | toast "Added entity" / "Ported {n} point(s) · {n} duplicate(s) skipped" | "Added to {resume}. {n} bullets added, {n} already there." | entity, port |
| career/send-to-resume-dialog.tsx:164, :193, :212 | `toast.error(error.message)` | `couldnt("add to the resume", error)`, `couldnt("adapt the bullets", error)`, `couldnt("add to the resume", error)` | D1.3 |
| career/send-to-resume-dialog.tsx:280 | "Send to resume" / "Review adapted points" | "Add to a resume" / "Review new wording" | glossary |
| career/send-to-resume-dialog.tsx:284 | "Copy approved facts from {title} into one base resume. Adapt rewrites them to match that resume's voice; send as-is copies them verbatim." | "Copy bullets from {title} to a base resume. Adapt rewrites them to fit it. Add as is copies them exactly." | facts, semicolon, as-is |
| career/send-to-resume-dialog.tsx:285 | "Only checked bullets are applied to {target} as a new entry / 's matching entry. Edit any bullet before applying." | "Only checked bullets are added. You can edit any of them first." | entry |
| career/send-to-resume-dialog.tsx:292 | label "Target base resume" | "Resume" | |
| career/send-to-resume-dialog.tsx:322 | "No base resumes are available." | "You have no base resumes yet." | |
| career/send-to-resume-dialog.tsx:328 | legend "Approved points" | "Approved bullets" | |
| career/send-to-resume-dialog.tsx:330-331 | "This item has no approved points. Its structured fields can still be added." | "No approved bullets. Its title and dates can still be added." | jargon |
| career/send-to-resume-dialog.tsx:358 | aria "Edit point text" | "Edit bullet text" | |
| career/send-to-resume-dialog.tsx:413 | "From point:" | "From bullet:" | |
| career/send-to-resume-dialog.tsx:456 | "Left out, already covered by this resume" | "Already on this resume" | |
| career/send-to-resume-dialog.tsx:466 | "Unknown point" | "Unknown bullet" | |
| career/send-to-resume-dialog.tsx:512-515 | "Sending…" / "Send as-is" / "Send to resume" | "Adding…" / "Add as is" / "Add to resume" | as-is, glossary |
| career/send-to-resume-dialog.tsx:525 | "Adapting…" / "Adapt & preview" | "Adapting…" / "Adapt and preview" | ampersand |
| career/send-to-resume-dialog.tsx:549-550 | "Applying…" / "Apply {n} to resume" | "Adding…" / "Add {n} to resume" | |
| career/resume-import-dialog.tsx:92 | `toast.error(err.message / String(err))` | `couldnt("import the resumes", err)` | D1.3 |
| career/resume-import-dialog.tsx:127 | hint "PDF, DOCX, Markdown, text, or the app's own JSON · up to 10 files, 10 MB each" | "PDF, Word or text files. Up to 10 files, 10 MB each." | jargon |
| career/resume-import-dialog.tsx:163 | "Building your Career KB…" | "Adding to your career history…" | KB |
| career/resume-import-dialog.tsx:219-228 | "Created {n} base resume(s) and added {n} approved point(s) to your Career KB." | "Created {n} base resume" / "resumes" " and added {n} approved bullet" / "bullets" " to your career history." | keeps "approved" (the disclosure) |
| career/resume-import-dialog.tsx:233-234 | "Confirm the target role for each — suggestions are guesses." | "Check the role for each. These are our best guesses." | em dash |
| career/resume-import-dialog.tsx:292-294 | "Each file becomes a base resume you can tailor, and its content is added to your Career Knowledge Base." | "Each file becomes a base resume, and its content is added to your career history." | keeps both effects |
| kb-sync-pill.tsx:57-61 | "new point" "new project point" "new education entry" "new certification" "new extra-section entry" | "new bullet" "new project bullet" "new education item" "new certification" "new item in other sections" (each pluralized) | point, entry |
| kb-sync-pill.tsx:80 | "{n} drifted (will be recorded)" | "{n} reworded (we'll note the change)" | jargon |
| kb-sync-pill.tsx:123-127 | toast "Synced {n} new · {n} drifted · {n} skills. Review drafts" | "Added {n} new bullets to your career history. Review drafts" | jargon |
| kb-sync-pill.tsx:138 | `toast.error(err.message)` | `couldnt("add to your career history", err)` | D1.3 |
| kb-sync-pill.tsx:148 | title "Couldn't check Career KB sync. Try again." | "Couldn't check your career history. Try again." | KB |
| kb-sync-pill.tsx:150 | "KB sync unavailable" | "Career history unavailable" | KB |
| kb-sync-pill.tsx:166 | aria "Checking Career KB sync" | "Checking career history" | KB |
| kb-sync-pill.tsx:189-190 | title "Career KB up to date · synced {ago}" | "Career history up to date, last updated {ago}" | KB; pin `test_kb_sync_frontend.py:52` |
| kb-sync-pill.tsx:195-196 | "KB synced" | "Career history up to date" | KB |
| kb-sync-pill.tsx:208-209 | "Sync to KB ({n})" | "Add to career history ({n})" | owner decision |
| kb-sync-pill.tsx:221-222 | "To sync into the Career KB" | "Not yet in your career history" | KB |
| kb-sync-pill.tsx:236 | "{n} drift note(s) already recorded" | "{n} wording change" / "changes" " already noted" | jargon |
| kb-sync-pill.tsx:245 | "Syncing…" / "Sync now" | "Adding…" / "Add now" | pin `test_kb_sync_frontend.py:47` |
| kb-sync-pill.tsx:250-251 | "Career KB →" | "Open career history" | the arrow was read aloud |

**Dropped.** `entity-card.tsx:29-39` statuses "Ongoing", "Completed", "Archived": kept (an item's status;
the owner did not rename it). `capture-box.tsx:129` "Quick capture": a feature name, kept.

### D5.1 Pins (L4)

| test | old | new |
|---|---|---|
| `test_kb_sync_frontend.py:47` | `assert "Sync now" in source` | `assert "Add now" in source` |
| `test_kb_sync_frontend.py:50-52` | comment "its "KB synced" label"; `source.index("Career KB up to date")` | comment "its "Career history up to date" label"; `source.index("Career history up to date, last updated")` (the title, which comes after the error branch) |
| `test_frontend_kb_editors.py:187` | `flat.index('"Capturing…" : "Add to inbox"')` | `flat.index('"Adding…" : "Add to drafts"')` |
| `test_frontend_query_error_states.py:70` | `("app/career/page.tsx", "No custom sections yet")` | `("app/career/page.tsx", "No other sections yet")` |
| `test_frontend_query_error_states.py:71` | `("components/career/inbox-panel.tsx", "Inbox clear")` | `("components/career/inbox-panel.tsx", "Nothing to review")` |
| `test_frontend_query_error_states.py:67` | `("components/career/profile-panel.tsx", "No skill groups yet.")` | unchanged |
| `test_frontend_placeholders.py:593-608` `test_new_entity_placeholders_are_examples` | the `_ENTITY_EXAMPLES` table and its `e.g.` asserts | rename `test_new_item_dialog_has_no_placeholders`: `"placeholder=" not in src`; the `retired` loop stays; delete `_ENTITY_EXAMPLES` |
| `test_frontend_placeholders.py:611-616` `test_entity_dates_are_examples_not_the_ongoing_word` | `'placeholder="e.g. Acme Labs"'` and the two date examples | `"placeholder=" not in src`; `'Month and year, like Jan 2025.' in src` |
| `test_frontend_placeholders.py:619-641` `test_profile_and_notes_statements_are_hints` | `'placeholder="e.g. ML Ops"' in profile`; the old notes hints | `"e.g." not in profile`; the notes `_order` step reads `"Only you and the AI see these, such as visa timing or where you can work."` and `"Tools, team size, limits, who you worked with, and what you owned."` |
| `test_frontend_agent_words.py` (A5) | `('components/career/points-list.tsx', 'chat: "Capture",', 'chat: "Assistant",')` and the `mcp` row | unchanged (this lane keeps A's two labels) |
| `test_frontend_placeholders.py`, `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_EXAMPLES_L4`, `_PENDING_L4` | delete |
| new, `test_frontend_plain_words.py` | none | `test_an_item_without_org_or_dates_claims_nothing`: `'"Independent"' not in _read("components/career/entity-card.tsx")` (D10.7) |
| new, same file | none | `test_item_counts_agree_with_their_nouns`: `entity-card.tsx` has no `label="points"`, `label="drafts"` or `label="docs"` literal; each Metric takes a singular and a plural (D10.8) |
| new, same file | none | `test_add_files_names_what_it_opens`: `"Add documents" not in _read("app/career/page.tsx")` and `"Add files" in` it, and `"Add files"` is the Upload dialog's title (D10.6) |

### D5.2 Browser checks (L4)

1. `/career`: the title reads "Career history"; the header has "Add files" and "Add item"; "Add files"
   opens a dialog titled "Add files" with Resumes and Other documents tabs.
2. An item with no organization and no dates: the card shows no second line (no "Independent"). An item with
   one bullet: "1 bullet", "1 document".
3. A bullet's chips: "Approved" status, "You" or "Document" origin; "Stop using" moves it to "Not used";
   "Use again" restores it.
4. Base studio header after editing a bullet: "Add to career history (1)"; press it: toast "Added 1 new
   bullet to your career history." with Review drafts; the pill then reads "Career history up to date".
5. Quick capture: a visible label "What did you do?", no placeholder; submit shows "Added to {title}. 2
   bullets to review.".
6. Send an item to a resume: dialog "Add to a resume", buttons "Add as is" and "Adapt and preview"; 375px
   dark: the buttons wrap without clipping.

---

## D6. Settings and Profile cards (lane L5), after C and A

`components/settings/**` plus the two page subtitles. Appendix C restructures every card (tabs, header
status, the Models split into Models, Model catalog and Custom endpoint, the rhythm) and appendix A5 and A8
rewrite the agent words and add the Connected agents card. **This lane runs after both.** Its rows are
either strings neither appendix touches, or a **delta on C** or a **delta on A** where an owner decision
changes their words (each says which). Source: audit part 3 §2.1, §2.5–2.9.

### D6.1 AI & models tab: API keys, Models, Available models, Custom AI server, AI instructions

| file:line | current | new | why (category) |
|---|---|---|---|
| models-section.tsx:218 | description "Provider credentials. Leave a field blank to fall back to .env." | "Lets the app use OpenAI or Gemini. You need at least one." | jargon, `.env` |
| models-section.tsx:219 | "Couldn't load your API key status." | "Couldn't load your API keys." | |
| models-section.tsx:230, :239 | `placeholderUnset="e.g. sk-..."`, `"e.g. AIza..."` | drop the `placeholderUnset` prop; `KeyField` takes `hintUnset`: "Starts with sk-." and "Starts with AIza.", shown (with `aria-describedby`) while no key is saved; the saved-key hint stays | owner rule; the format moves to a hint |
| models-section.tsx:305 | "Configured · from .env" / "Configured · in-app" | "Set outside the app" / "Saved" | `.env` means nothing in the desktop build; keep the span's classes byte-identical (pin `test_frontend_color_roles.py:833`) |
| models-section.tsx:308 | "Not configured" | "Not added" | |
| models-section.tsx:266 | "Save API keys" / "Saving…" | "Save" / "Saving…" | the card names what is saved |
| models-section.tsx:69, :106 | `toast.error(err.message)` | `couldnt("save your model settings", err)`, `couldnt("test the model", err)` | D1.3 |
| models-section.tsx:249 | "Leave blank to use defaults from .env." | appendix C8 deletes it | after C; no further change |
| models-section.tsx `ROLES` (C7) | C7: `"Fast model"` / "Reads postings and runs bulk work." | "Fast model" / "Reads job descriptions and documents, and picks form answers." | **delta on C**: "postings"; the hint says what it does (`jd_extraction`, `kb_ingest`, `autofill_choose`, `gap_enrichment`) |
| models-section.tsx `ROLES` (C7) | C7: `"Smart model"` / "Tailors resumes and finds gaps." | "Smart model" / "Tailors resumes and writes drafts." | **delta on C**: accuracy (`tailoring_session`, `persona`, `kb_adapt`, `base_from_kb_plan`) |
| models-section.tsx `ROLES` (C7; today :139 "Chat model · needs streaming tool calls, so test it") | C7: `"Chat model"` / "Runs the in-app assistant, which needs tool calls." | "Assistant model" / "Runs the Assistant. Use Test to check it works." | **delta on C**: owner decision (only Chat model is renamed) |
| models-section.tsx:182 | "Which models did you measure?" | "Which model should I pick?" | says what the user wants to know |
| models-section.tsx:186-193 | "Two measured profiles, one per key: GPT-5.6 Luna on every tier (the default — most thorough JD extraction we tested, about a penny per application, slower) or Gemini 3.7 Flash on every tier (fastest, under 3¢ per application, promo pricing doubles Jan 2027). In our tests the Fast model decided extraction coverage and score honesty; the Smart choice barely moved the result. Prices and tiers move constantly — treat this as a starting point, not a recommendation with a shelf life." | "GPT-5.6 Luna gives the most thorough results (about 1¢ per application, slower). Gemini 3.7 Flash is the fastest (under 3¢). In our tests the Fast model mattered most. Prices change often, so treat this as a starting point." | em dashes, JD, semicolon, "tier" |
| models-section.tsx (C7 keeps) "Measured, not assumed. A model that cannot call tools still works everywhere except chat." | | "Test a model to see what it can do. A model that fails the Assistant test still works everywhere else." | **delta on C**: jargon, "chat" |
| capability chips `CAPABILITY_LABELS` (moved to `models-section.tsx` by C7; today `llm-endpoint.tsx:18-23`) | labels "Text", "JSON", "Tools"; `gates` "cover letters, screening answers", "extraction, tailoring, health, KB ingest", A5 row 23: "the Assistant in Chat" | labels "Writing", "Structured answers", "Assistant"; `gates` "cover letters and answers", "reading jobs, tailoring, health checks and career history", "the Assistant" | jargon; **delta on A5 row 23** (the sidebar item is now Assistant, D7) |
| models-section.tsx:95-96 | toast "Could not reach the API, so {model} was not tested: {why}. Check the API key and endpoint, then test again." | "Couldn't reach {OpenAI \| Gemini \| your AI server}, so {model} wasn't tested. Check your API key and server address, then try again." | "Could not", jargon |
| models-section.tsx:99 | toast "{model} supports everything" | "{model} works with every feature" | |
| models-section.tsx:102 | toast "{model} cannot do: text, json, tools. Other surfaces still work." | "{model} can't do {Writing, Structured answers, Assistant}. Everything else works." (the chip labels) | raw keys |
| models-section.tsx:393 | placeholder "e.g. llama3.2:3b" (C: "stays") | remove; hint "The model name your server uses." | **delta on C**: owner rule |
| models-section.tsx:447 | "«{value}» · unavailable" | "{value} (no longer available)" | guillemets, `·` |
| model-catalog-panel.tsx (C7 card) | title "Model catalog"; description "The models the pickers offer: built-in ones, plus any you add with Sync." | title "Available models"; description "Models you can pick above: the built-in ones and any you add." | **delta on C**: "catalog", "Sync" (C pins the card's `id`, not its title) |
| model-catalog-panel.tsx:118, :131 | "Sync OpenAI" / "Sync Gemini" | "Find OpenAI models" / "Find Gemini models" | **delta on C** (C moves them to the header) |
| model-catalog-panel.tsx:39-40 | toast "Found {n} {provider} models" / "No chat-like {provider} models returned" (provider lowercase) | "Found {n} {OpenAI \| Gemini} models" / "No {OpenAI \| Gemini} models found" (C7's `providerLabel`) | raw-value |
| model-catalog-panel.tsx:68, :91 | toast "Added {id}" / "Removed {id}" | "Added {label}" / "Removed {label}" | |
| model-catalog-panel.tsx:43, :70, :93 | `toast.error(err.message)` | `couldnt("find models", err)`, `couldnt("add the model", err)`, `couldnt("remove the model", err)` | D1.3 |
| model-catalog-panel.tsx:150-152 | "OpenAI discovery — + adds to the catalog; then choose it under Fast, Smart, or Chat." (C7 rewrites the line's frame) | "Select + to add a model, then choose it above." | **delta on C**: em dash, semicolon, "Chat" |
| llm-endpoint.tsx (C7 card) | title "Custom endpoint"; toast "Endpoint settings saved" | "Custom AI server"; "Server settings saved" | **delta on C**: "endpoint" |
| llm-endpoint.tsx:74 | label "OpenAI-compatible endpoint" (optional) | `<Label optional>Server address</Label>` | jargon |
| llm-endpoint.tsx:77-78 | hint "Point at Ollama, LM Studio, vLLM or OpenRouter and nothing leaves this machine. Leave empty for the OpenAI API." | "The address of a model server on your computer, such as Ollama or LM Studio. It usually ends in /v1. Leave empty to use OpenAI." | **bug** (D10.2): OpenRouter is a remote service, so "nothing leaves this machine" was false |
| llm-endpoint.tsx:84 | placeholder "e.g. http://host.docker.internal:11434/v1" (C: "stays") | remove | **delta on C**: owner rule; the hint states the format |
| llm-endpoint.tsx:102-103 | "Your API key and resume text will be sent to this server. Only point it somewhere you trust." | "Your API key and resume will be sent to this server. Use one you trust." | keeps the warning |
| llm-endpoint.tsx:112 | "JSON mode" | "Structured replies" | jargon |
| llm-endpoint.tsx:115-116 | "Auto sends response_format only to the OpenAI API. Some servers reject the field outright." | "Leave on Auto unless your server shows errors." | raw field name |
| llm-endpoint.tsx:163-164 | "Measured, not assumed. A model that cannot call tools still works everywhere except chat." | moved by C7; see the delta above | |
| prompts-section.tsx:53 | "Prompts" | "AI instructions" | jargon |
| prompts-section.tsx:54 | "Override the voice used for cover letters, outreach, Q&A, and chat." | "Change how the AI writes cover letters, answers, tailoring and Assistant replies." | accuracy: listed "outreach", missed tailoring |
| prompts-section.tsx:22-23 | "Voice and structure of generated cover letters." | "Tone and structure of cover letters." | |
| prompts-section.tsx:27-28 | "Application Q&A" / "How free-response application questions are answered in your voice." | "Application questions" / "How your written answers to application questions sound." | |
| prompts-section.tsx:32-33 | "Gap tailoring" / "How resolved gap answers get folded into a tailored resume." | "Tailoring from your answers" / "How your gap answers go into a tailored resume." | jargon |
| prompts-section.tsx:37-38 | "Chat assistant" / "System behavior for the main chat assistant." | "Assistant" / "How the Assistant behaves." | owner vocabulary |
| prompts-section.tsx:55 | "Couldn't load your prompts." | "Couldn't load your AI instructions." | |
| prompts-section.tsx:87 | "Advanced prompts ({n})" | "More instructions ({n})" | |
| prompts-section.tsx:169, :179 | an advanced prompt is titled only by its raw key (`extract_jd`, …) | a `PROMPT_TITLES` map, title and one line each: autofill_choose "Autofill choices" / "How Companion picks answers for form choices."; base_from_kb_plan "New base resume plan" / "How items are picked for a new base resume."; base_resume_instruct "Ask for changes" / "How the studio suggests edits."; coherence_check "Wording checks" / "How a tailored resume is checked for flow."; extract_jd "Reading job descriptions" / "How a job description becomes job details."; gap_enrichment "Gap suggestions" / "How gaps get suggested answers."; kb_adapt "Rewording bullets" / "How bullets are reworded for a resume."; kb_capture "Quick capture" / "How an update becomes draft bullets."; kb_cluster_points "Merging bullets" / "How similar bullets are combined."; kb_document_ingest "Reading documents" / "How a document becomes draft bullets."; kb_entity_resolve "Matching items" / "How a new bullet finds its item."; kb_mint "Drafting bullets" / "How bullets are drafted from a document."; kb_resume_parse "Reading resume files" / "How an imported resume is read."; persona_draft "Persona draft" / "How your persona is drafted."; resume_bullet_classify "Rating bullets" / "How the health check rates each bullet."; resume_bullet_rewrite "Rewriting bullets" / "How the health check writes new wording."; resume_finding_verify "Checking issues" / "How the health check confirms an issue."; tailoring_skill "Tailoring skills" / "How skills are added while tailoring." The key stays as a small secondary line only for keys the map lacks | raw keys as titles |
| prompts-section.tsx:173 | "Collapse" / "Expand" | "Hide" / "Edit" | says what opens |
| prompts-section.tsx:186 | aria "{name} prompt text" | "{name} instructions" | |
| prompts-section.tsx:138, :151 | `toast.error(err.message)` | `couldnt("save the instructions", err)`, `couldnt("reset the instructions", err)` | D1.3 |

### D6.2 Tailoring, Connected agents, Appearance, About

| file:line | current | new | why (category) |
|---|---|---|---|
| quick-tailor-section.tsx:50 | A5 row 40: "What one-shot tailoring is allowed to change. Used by Quick tailor on the gap analysis page and by the Companion browser extension's Fast tailor." | "What Quick tailor may change on your resume, here and in Companion." | **delta on A**: the button reads "Quick tailor", not "Fast tailor" (`extension/panel/panel.js:280`); "browser extension" appears once, in setup |
| quick-tailor-section.tsx:51 | "Couldn't load your quick-tailor profile." | "Couldn't load Quick tailor settings." | "profile" clashes with the Profile page |
| quick-tailor-section.tsx:24 | "Add missing JD keywords to skills" | "Add missing job description keywords to Skills" | JD |
| quick-tailor-section.tsx:28 | "Mirror JD wording where evidence exists" | "Use the job description's wording when your experience backs it up" | JD, evidence; Analytics quotes this name (D2.9) |
| quick-tailor-section.tsx:32 | "Refresh summary / title alignment" | "Match your summary and title to the job" | slash |
| quick-tailor-section.tsx:36 | "Allow placements into projects" | "Add keywords to projects" | jargon |
| quick-tailor-section.tsx:118 | "Standing instruction" (optional) | `<Label optional>Extra instruction</Label>` + hint "Used every time Quick tailor runs." | jargon |
| quick-tailor-section.tsx:123 | placeholder "e.g. keep bullets under two lines" | remove | owner rule |
| quick-tailor-section.tsx:79 | `toast.error(err.message)` | `couldnt("save Quick tailor settings", err)` | D1.3 |
| auto-apply-section.tsx:33 | "Daily submission cap" | "Applications per day" | jargon (A5 row 27 rewrites its hint) |
| auto-apply-section.tsx:48-49 | "Unreviewed proposal expiry (days)" / "Accepted proposals never expire." | "Clear unreviewed proposals after (days)" / "Queued proposals stay." | jargon; owner chips (accepted reads Queued) |
| auto-apply-section.tsx:55-56 | "Auto-pick score floor" / "Minimum ATS score to auto-pick a base resume." | "Lowest ATS score to pick a resume" / "Below this, you choose the base resume." | "floor" |
| auto-apply-section.tsx:62-63 | "Auto-pick margin" / "Points the top base must beat the runner-up by." | "Lead needed to pick a resume" / "How many points the best base resume must lead the next one by." | bare "base" |
| auto-apply-section.tsx:162 | "Company blocklist" | "Companies to skip" | jargon |
| auto-apply-section.tsx:164-165 | A5 row 30: "A connected agent never saves or proposes these companies. Skipping one posting does not block its company." | "Connected agents never suggest jobs at these companies. Skipping one job doesn't block its company." | **delta on A**: "posting" |
| auto-apply-section.tsx:177 | aria "Remove {name} from blocklist" | "Remove {name}" | |
| auto-apply-section.tsx:197 | placeholder "e.g. Acme Corp" | remove | owner rule |
| auto-apply-section.tsx:222 | "Cancel" (drops unsaved edits) | "Discard" | Persona uses Discard for the same action |
| auto-apply-section.tsx:110 | `toast.error(err.message)` | `couldnt("save auto-apply settings", err)` | D1.3 |
| mcp-workflow-section.tsx:48 | `toast.error(err.message)` | `couldnt("save this setting", err)` | D1.3 (A5 rows 24–26 own its words) |
| appearance-section.tsx:51-52 | "Defaults to your system setting until you choose here." | "Follows your device until you change it." | |
| about-section.tsx:50-51 | "What this install is running. A local build reads dev here." | "Your app version." | jargon |
| about-section.tsx:60-63 | rows "Frontend", "Backend", "Schema revision", "Git SHA", "not recorded" | one row "Version"; the four rows move under a "Technical details" disclosure | **[behaviour]** a disclosure; the details stay for support |
| about-section.tsx:65, :16-17 | "Update" with the code `./scripts/update.sh` | "How to update", a link to `docs/GETTING_STARTED.md`'s update section | **[behaviour]** the desktop build has no script |
| settings-card.tsx:98 (C6 rewrites the file) | `detail={firstMessage(queries)}` | `detail={errorDetail(firstError(queries))}` | D1.3 |
| app/settings/page.tsx:48 (C2 hoists it) | "Getting started guide" | "Setup guide" | |
| app/profile/page.tsx (C2 keeps) | subtitle "Who you are as a candidate, and the answers autofill uses." | "About you, and your answers for job forms." | **delta on C**: jargon |

### D6.3 Profile: About you (Persona, Market, Job preferences)

| file:line | current | new | why (category) |
|---|---|---|---|
| persona-section.tsx:47 | "Persona" | keep | owner decision |
| persona-section.tsx:48 | "Vision, strengths, goals, and how you work. Shapes the voice of tailoring, Q&A, and outreach. Never adds facts to your resume." | "How you'd describe yourself as a candidate: your goals, strengths and how you work. It sets the tone of tailoring and answers, and never adds facts to your resume." | owner: say what Persona is in one line; "outreach" does not exist; keeps "never adds facts" |
| persona-section.tsx:16-22 | the five-line `e.g.` placeholder ("Vision: … Goals: senior DS/MLE role … How I work: … evidence over opinion.") | remove | owner decision (slash, jargon, an example as text) |
| persona-section.tsx:98, :115 | `toast.error(err.message)` | `couldnt("save your persona", err)`, `couldnt("draft your persona", err)` | D1.3 |
| market-section.tsx:58 | "Market" | "Where you apply" | jargon |
| market-section.tsx:75 | label "Where you apply" | "Country" | the title now says it |
| market-section.tsx:78-79 | "Sets the default currency for captured jobs and which voluntary disclosures apply." | "Sets the currency for jobs and which diversity questions apply." | jargon |
| market-section.tsx:96 | "{label} · {currency}" | "{label} ({currency})" | `·` |
| market-section.tsx:52 | toast "Could not save your market" | `couldnt("save your country", err)` | error form |
| market-section.tsx:61 | "Couldn't load your market." | "Couldn't load your country." | |
| market-section.tsx:105-109 | "Maestro CS has no verified voluntary-disclosure question set for {country}, so it does not ask for one. Those categories are not interchangeable between countries, and answering the wrong country's form would put inaccurate information under your name." | "Maestro CS has no verified diversity questions for {country}, so it won't ask them. Another country's questions could put wrong information under your name." | keeps the reason (a trust statement) |
| job-preferences-section.tsx:73 | "Roles and conditions you're targeting. Drives base-resume suggestions." | "The jobs you want. Used to suggest base resumes." | |
| job-preferences-section.tsx:148 | "Favored roles" (optional) | "Roles you want" (optional) | |
| job-preferences-section.tsx:170 | placeholder "e.g. 6" | remove | owner rule |
| job-preferences-section.tsx:190 | label "Remote" | "Work location" | the options include On-site |
| job-preferences-section.tsx:204, :211, :47 | "Not specified" plus option "Any" | one option "No preference" (writes `null`; a stored `"any"` also reads "No preference") | two options meant the same. **[behaviour]** one option fewer; no value migrates |
| job-preferences-section.tsx:233 | placeholder "e.g. Chicago, IL\nNew York, NY" | remove | the hint "One location per line." stays (pin `test_locations_hint_is_between_the_label_and_the_field`) |
| job-preferences-section.tsx:250 | "Min salary" | "Minimum salary" | abbreviation |
| job-preferences-section.tsx:255 | placeholder "e.g. $140,000" | remove | owner rule |
| job-preferences-section.tsx:268 | "Employment types" | "Job types" | |
| job-preferences-section.tsx:115 | `toast.error(err.message)` | `couldnt("save your job preferences", err)` | D1.3 |

### D6.4 Profile: Autofill (`autofill-section.tsx`)

Consent wording keeps every promise: never signs, never submits, never fills passwords or ID numbers, never
guesses or uses AI for diversity answers, WOTC and signatures stay with you, "voluntary", "You can turn this
off anytime".

| line | current | new | why (category) |
|---|---|---|---|
| :442 | "Autofill profile" | "Answers for job forms" | jargon (the tab is Autofill) |
| :443 | A5 row 41: "Preset answers the Companion browser extension uses to fill job-application forms." | "Companion uses these to fill job applications." | **delta on A**: "browser extension" once, in setup |
| :444 | "Couldn't load your autofill profile." | "Couldn't load your form answers." | |
| :707-710 | tooltips "Loading your career profile…" / "Could not load your career profile." / "Add usable contact details to your career profile first." | "Loading your career history…" / "Couldn't load your career history." / "Add your contact details to your career history first." | a fourth name for Career history; "usable" |
| :655 | toast "Nothing new to fill" | "Nothing new to add" | |
| :664 | toast "Filled {n} fields from your career profile" | "Filled {n} fields from your career history" | |
| :666 | toast "Could not load your career profile" | `couldnt("load your career history", err)` | |
| :573, :687 | `toast.error(err.message)` | `couldnt("save your consent", err)`, `couldnt("save your answers", err)` | D1.3 |
| :71 | placeholder "e.g. Apt 4B" | remove; drop the `placeholder` key from the field table (D1.4 item 8) | owner rule |
| :76-77 | "LinkedIn URL" / "GitHub URL" | "LinkedIn profile link" / "GitHub link" | |
| :78 | "Portfolio / website" | "Website" | slash |
| :87 | "Current work authorization status" | "Work authorization status" | verbose; keeps the forms' term |
| :109 | "Do you require sponsorship now?" | "Do you need visa sponsorship now?" | gloss "sponsorship" |
| :116 | "Will you require sponsorship in the future?" | "Will you need visa sponsorship later?" | |
| :125 | "Voluntary disclosures (EEO)" | "Diversity questions (voluntary)" | owner decision; keeps "voluntary" |
| :165 | "Race / ethnicity" (optional) | "Race or ethnicity" (optional) | slash |
| :167 | placeholder "e.g. Asian" | remove | owner rule |
| :188 | "Are you 18 years of age or older?" | "Are you 18 or older?" | |
| :196 | "Previously employed by the company you are applying to?" | "Have you worked for the company you're applying to?" | grammar |
| :216 | "Desired salary" + placeholder "e.g. $120,000" | remove the placeholder | owner rule |
| :217 | "Notice period" + placeholder "e.g. 2 weeks" | remove; hint "How long before you can start." | owner rule |
| :226 | "How did you hear about us?" + placeholder "e.g. Job board" | label "How did you hear about the job?"; remove the placeholder | "us" is the employer; owner rule |
| :247 | "School / university" | "School" | slash |
| :248 | "Degree" + placeholder "e.g. Master of Science" | remove the placeholder | |
| :249 | "Discipline / major" + placeholder "e.g. Data Science" | "Major"; remove the placeholder | slash |
| :250 | "GPA" + placeholder "e.g. 3.8" | remove the placeholder | |
| :251-252 | "Start year" / "Graduation year" + placeholders "e.g. 2021" / "e.g. 2023" | remove both | |
| :567-570 | one shared `onSuccess` toast: `result.value.enabled ? "EEO standing consent enabled" : "EEO standing consent turned off"` | remove the toast from the shared `onSuccess`; each switch passes its own: `saveConsent.mutate(next, { onSuccess: () => toast.success(next.enabled ? "Companion can now answer diversity questions" : "Companion won't answer diversity questions") })` and, for the agreement-box switch, `"Companion can now tick agreement boxes"` / `"Companion won't tick agreement boxes"` | **bug** (D10.1): the agreement-box switch shares the mutation, so toggling it announced the diversity-questions state. **[behaviour]** |
| :579 | confirm title "Let autofill answer voluntary EEO questions?" | "Let Companion answer the voluntary diversity questions?" | EEO; keeps "voluntary" |
| :580-585 | "Maestro CS Companion will fill self-identification fields (race/ethnicity, gender, veteran status, disability) using only the exact answers stored below. Answers are never inferred or authored by an AI. WOTC, signatures, and legal attestations stay manual. You can turn this off anytime." | "Maestro CS Companion will fill race, ethnicity, gender, veteran and disability questions using only your exact answers below. It never guesses and never uses AI for these. Tax-credit (WOTC) questions, signatures and legal statements stay with you. You can turn this off anytime." | slash, jargon; **every clause kept** (the full name "Maestro CS Companion" once, as today) |
| :586 | confirmLabel "Allow EEO fill" | "Allow" | the title names it |
| :621 | confirm title "Let autofill tick agreement boxes?" | "Let Companion tick agreement boxes?" | |
| :622-628 | "This covers an application's own terms and conditions, acknowledgements and attestations. It ticks a box; it never signs and never submits. Signature and initials fields stay manual, and passwords and government ID numbers are never filled whatever you choose here. Review every form before you submit it. You can turn this off anytime." | "This covers only an application's own terms and acknowledgement boxes. It ticks a box. It never signs and never submits. Signatures, initials, passwords and government ID numbers are never filled, whatever you choose here. Check every form before you submit it. You can turn this off anytime." | semicolon; **every promise kept** |
| :629 | confirmLabel "Allow ticking boxes" | "Allow" | |
| :729 | "Decline all" | "Decline the rest" | accuracy: it fills only unanswered questions (`:530-545`) |
| :755 | A5 row 42: "Allow the Companion to fill these answers" | "Let Companion fill these answers" | **delta on A**: proper name, no article (glossary) |
| :758-759 | "Standing consent for exact-match autofill only. Off by default; WOTC and signatures stay manual." | "Uses only your exact answers above. Off by default. Tax-credit (WOTC) questions and signatures are always yours to fill." | jargon, semicolon; keeps both promises |
| :777 | A5 row 43: "Allow the Companion to tick agreement boxes" | "Let Companion tick agreement boxes" | **delta on A** |
| :780-782 | "Terms and conditions, acknowledgements and attestations. It ticks a box; it never signs and never submits. Signatures, passwords and government ID numbers are never filled." | "Terms and acknowledgement boxes only. It never signs or submits, and never fills signatures, passwords or ID numbers." | semicolon, "attestations"; every promise kept |
| :794-795 | "Acknowledged {date} · policy {version}" | "You agreed on {date} (policy {version})" | `·` |
| :822 | SelectValue placeholder "—" | "Choose" | a select reads better with a verb |
| :854 | A5 row 44: "Most recent first, matching the Companion's repeated form blocks." | "Most recent first." | **delta on A**: jargon |
| :886 | C8: `Remove education entry ${i + 1}` | `Remove school ${i + 1}` | **delta on C**: entry |
| :900 | "Custom questions" | "Your own questions" | |
| :902-903 | "Recurring form questions with your standard answers (matched by question text)." | "Questions you get often, with your usual answers." | jargon |
| :910-911 | question field: aria-label only + placeholder "e.g. Why do you want to work here?" (C8 adds the visible "Question" label) | remove the placeholder | owner rule |
| :966 | "Save autofill profile" / "Saving…" | "Save answers" / "Saving…" | jargon |
| :685 | toast "Autofill profile saved" | "Answers saved" | |

**Not changed this plan (open questions):** the Gender options (`:148-167`, Male, Female, Decline) and
"Subject to a non-compete or restrictive covenant?" (`:204`; "restrictive covenant" covers more than a
non-compete). The owner decides.

### D6.5 Pins (L5)

| test | old | new |
|---|---|---|
| `test_frontend_placeholders.py:507-519` `test_saved_key_is_a_hint_not_a_placeholder` (C8 already changed its grid regex) | `'placeholderUnset="e.g. sk-..."'`, `'placeholderUnset="e.g. AIza..."'`, `_order(…, "placeholder={configured ? undefined : placeholderUnset}")` | `'hintUnset="Starts with sk-."' in src`, `'hintUnset="Starts with AIza."' in src`, `"placeholder=" not in src`; `_order(src, "Type a new key to replace the saved one.", "aria-describedby={hintId}")` |
| `test_frontend_placeholders.py:570-580` `test_custom_answer_has_a_visible_label_not_a_placeholder` (C8 adds the Question label) | unchanged asserts | add `"e.g. Why do you want to work here?" not in src` |
| `test_frontend_placeholders.py` `_PASS_THROUGH` | `("components/settings/autofill-section.tsx", "field.placeholder")` | delete |
| `test_frontend_agent_words.py` (appendix A5) | rows for `quick-tailor-section.tsx` ("the Companion browser extension's Fast tailor"), `autofill-section.tsx` ("Allow the Companion to fill these answers", "Allow the Companion to tick agreement boxes"), `llm-endpoint.tsx` (`gates: "the Assistant in Chat"`) | present becomes "What Quick tailor may change on your resume, here and in Companion.", "Let Companion fill these answers", "Let Companion tick agreement boxes", and `gates: "the Assistant"` (now in `models-section.tsx`, C7) |
| `test_frontend_settings_pages.py` (appendix C, section "Models") | none pins the role labels or card titles (checked: C pins ids, `aria-label`s and classes) | add `test_the_role_models_are_fast_smart_and_assistant`: `'label: "Assistant model"' in _MODELS and '"Chat model"' not in _MODELS` |
| new, `test_frontend_error_words.py` | none | `test_each_consent_switch_announces_itself`: in `autofill-section.tsx`, `"EEO standing consent" not in src`; `"Companion can now tick agreement boxes" in src`; `"Companion can now answer diversity questions" in src`; the shared `saveConsent` `onSuccess` block holds no `toast.success(` (D10.1) |
| new, `test_frontend_plain_words.py` | none | `test_the_custom_server_hint_never_promises_local_only`: `"nothing leaves this machine" not in _read("components/settings/llm-endpoint.tsx")` and `"OpenRouter" not in` it (D10.2) |
| `test_frontend_placeholders.py`, `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_EXAMPLES_L5`, `_PENDING_L5` | delete |

`test_frontend_unsaved_surfaces.py` (Persona) and `test_frontend_settings_autosave.py` ("Saves
automatically") are unchanged.

### D6.6 Browser checks (L5)

1. Settings › AI & models: API keys has no placeholder; with no key saved, "Starts with sk-." sits under
   the label; the status reads "Saved" after a save. The Models card lists Fast, Smart and Assistant models,
   each with its hint; a capability row reads "Writing · Structured answers · Assistant".
2. Custom AI server (expand Advanced): the hint no longer names OpenRouter or promises that nothing leaves
   the machine; the address field has no placeholder.
3. Profile › Autofill: toggle "Let Companion tick agreement boxes" on (confirm) and off. The toasts read
   "Companion can now tick agreement boxes" and "Companion won't tick agreement boxes", never the diversity
   wording. Then the diversity switch: its own two toasts.
4. Profile › About you: Persona's description explains it in one line; the field is empty with no example.
   Job preferences: "Work location" shows one "No preference".
5. Screen reader on the diversity confirm: the title says "voluntary"; the body keeps "never uses AI".
6. 375px, dark mode: long labels ("Use the job description's wording when your experience backs it up")
   wrap inside their switch rows.

---

## D7. Assistant, shell, errors and setup (lane L6)

The sidebar, the chat page and its cards, the error pages, the version banner, the `components/ui`
defaults, and `components/setup/*`. Source: audit part 3 §2.1–2.4, §2.10–2.12. The shared error helpers are
D1 (lane L0). **Also touched first:** `app-sidebar.tsx` by A3 (the Agent inbox item and its count),
`setup-steps.ts` and `getting-started-card.tsx` by C lane A (deep links), `chat/proposal-card.tsx` and
`chat/edit-proposal-card.tsx` by A5. This lane runs after them.

### D7.1 Sidebar and shell

| file:line | current | new | why (category) |
|---|---|---|---|
| components/app-sidebar.tsx:49 | "Agent Proposals" | "Agent inbox" (A1) | after A; no further change |
| components/app-sidebar.tsx:56 | "Career KB" | "Career history" | owner decision; the group stays "Career library" |
| components/app-sidebar.tsx:57 | "Base Resumes" | "Base resumes" | case |
| components/app-sidebar.tsx:64 | "Chat" | "Assistant" | owner decision (A's open question 4, now decided) |
| components/app-sidebar.tsx:136 | "New application" (the pinned button) | "Add job" | owner decision |
| components/app-sidebar.tsx:88, sidebar-reveal-trigger.tsx:56 | title "Toggle sidebar (⌘B)" | "Hide sidebar (⌘B)" when open, "Show sidebar (⌘B)" when hidden | names the result |
| components/ui/sidebar.tsx:280 | sr-only "Toggle sidebar" | "Hide sidebar" / "Show sidebar" by state | same |
| components/ui/sidebar.tsx:292-295 | `SidebarRail` aria-label and title "Toggle Sidebar" | "Hide sidebar" | case; unused today |
| components/ui/sidebar.tsx:199-200 | sr-only "Sidebar" / "Displays the mobile sidebar." | "Menu" / remove the description | the description restated the title |
| app/chat/page.tsx:5 | `<title>` "Chat — Maestro CS" | "Assistant — Maestro CS" | owner decision (a composed title; the em dash is typography) |
| app/error.tsx:35-37 | "Something went wrong" / "This page failed to render. Your data is untouched, so retrying is safe." | "Something went wrong" / "This page didn't load. Your data is safe." | render |
| app/error.tsx:46 | "Reference: {digest}" | "Error code: {digest}" | |
| app/error.tsx:58 | "Back to Applications" | "Back to applications" | matches the job page (D2) |
| app/global-error.tsx:43-46 | "Maestro CS failed to start" / "The application shell could not render. Reloading is safe." | "Maestro CS couldn't open" / "Try again, or reload the page." | render, "could not" |
| app/global-error.tsx:50 | "Reference:" | "Error code:" | |
| app/not-found.tsx:15-18 | "Page not found" / "That URL doesn't exist here. It may have been renamed, or the record behind it was deleted." | "Page not found" / "It may have moved or been deleted." | "URL", "record" |
| components/guarded-link.tsx:18 | "Changes you haven't saved on this page will be lost." | "Your unsaved changes will be lost." | shorter; the pinned title "Leave without saving?" stays (`test_frontend_leave_guard.py:61,65`) |
| components/confirm-dialog.tsx:112, :119 | default labels "Cancel" / "Confirm" | keep "Cancel"; remove the "Confirm" default, so `confirmLabel` is required | a button names its action. **[behaviour]** a type change; every caller already passes a verb (checked: `rg -n "confirm\(\{" frontend` and each has `confirmLabel`) |
| components/version-banner.tsx:35-37 | "Your frontend ({a}) and backend ({b}) are different versions. One image is stale — run ./scripts/update.sh." | "Maestro CS didn't finish updating. See How to update in Settings › About." | frontend, backend, image, em dash; the About card's link (D6) says how for each install |

### D7.2 Setup: Getting started, the Profile strip, the steps (after C)

| file:line | current | new | why (category) |
|---|---|---|---|
| setup/setup-steps.ts:102 | "Add a provider API key" | "Add an API key" | "provider" |
| setup/setup-steps.ts:103 | "Nothing extracts, tailors or chats without one." | "Needed to read jobs, tailor resumes and use the Assistant." | extract, chat |
| setup/setup-steps.ts:113 | `${n} base resumes · ${m} KB entries` | `${n} base resume` / `resumes` `, ${m} career history item` / `items` | **bug** (D10.8) "1 base resumes"; KB, entry |
| setup/setup-steps.ts:121-123 | "Autofill 40% · personal details" | "Autofill: 40% done" | the group name belongs in the detail |
| setup/setup-steps.ts:124 | "Complete autofill" | "Add your form answers" | jargon |
| setup/setup-steps.ts:126 | "Readiness 40% — personal details incomplete" | "40% done. Personal details are missing." | em dash, jargon |
| setup/setup-steps.ts:47-50 | GROUP_LABELS "personal details", "work authorization", "voluntary disclosures", "preferences" (no "eligibility") | "personal details", "work authorization", "diversity questions", "preferences", and add `eligibility: "eligibility"` | the renamed group (D6.4) |
| setup/setup-steps.ts:144-145 | "Persona" / "Write your persona" | keep | owner decision |
| setup/setup-steps.ts:152-156 | "Default: {default_template_id}" (fallback "Default: set") | "Default: {template name}" (fallback "Default template chosen") | printed the template id |
| setup/setup-steps.ts:163-167 | "PDF engines" / "Typst ready · TeX {version}" / "Typst ready · TeX not found (LaTeX templates render with Typst until it is installed)" | "PDF output" / "Ready" / "Ready. A few templates need extra software to look their best." | engine names, render |
| setup/getting-started-card.tsx:86-88 | "Required steps first. The rest can wait until you need them." | "Do the required steps first." | verbose |
| setup/getting-started-card.tsx:94 | aria "Dismiss getting started checklist" | "Hide getting started" | |
| setup/getting-started-card.tsx:29 | "Complete autofill" | "Add answers" | |
| setup/getting-started-card.tsx:31 | "Write persona" | keep | owner decision |
| setup/getting-started-card.tsx:71 | load-error detail | `errorDetail(setupStatus.error)` | D1.3 |
| setup/getting-started-card.tsx:166-167 | "You target these roles but have no base resume for them. Choose the Career KB entries that belong on each one." | "You want these roles but have no base resume for them yet." | KB, entry; the dialog explains the choosing |
| setup/getting-started-card.tsx:182 | "Compose from KB" | "Build from career history" | KB |
| setup/upload-dialog.tsx:160 | title "Add your documents" | "Add files" | pairs with the Career history button (D10.6) |
| setup/upload-dialog.tsx:162-163 | "Resumes become base resumes you can tailor. Everything else becomes evidence in your Career Knowledge Base." | "Resumes become base resumes. Other documents add detail to your career history." | KB, evidence |
| setup/upload-dialog.tsx:38-40 | "Each file is read for evidence about your career and filed against the matching Career KB entry, as draft points you review. These do not become base resumes." | "We add what we find to your career history as draft bullets for you to review. These don't become base resumes." | keeps the outcome-before-upload promise |
| setup/upload-dialog.tsx:48 | "PDF, DOCX, Markdown, text, or images · up to 10 files, 10 MB each" | "PDF, Word, Markdown, text or images. Up to 10 files, 10 MB each." | jargon, `·` |
| setup/upload-dialog.tsx:61-62 | "New experience “Acme” · 3 draft points" / "Matched …" | "Added to Acme (new): 3 draft bullets" / "Added to Acme: 3 draft bullets" | point, "Matched", raw kind |
| setup/upload-dialog.tsx:78-80 | "Stopped with 3 files left. Anything already added is saved. Retry picks up where it stopped." | "Stopped with 3 files left. What was added is saved." | the Retry button says the rest |
| setup/upload-dialog.tsx:86-92 | "Added 12 draft points across 4 entries · 1 skipped. Review them." | "Added 12 draft bullets to 4 items (1 skipped). Review them." | point, entry |
| setup/upload-dialog.tsx:115-120 | "Retry 3" | "Retry 3 files" | no noun |
| setup/upload-dialog.tsx:127-128 | "Read one at a time, a few seconds each, so the same role is never created twice." | "Files are read one at a time, a few seconds each." | the why is internal |
| setup/dropzone.tsx:11-13 | "0 Bytes", "Bytes" | "0 bytes", "bytes" | case |
| setup/dropzone.tsx:58 | "larger than 10 MB" | "Too large (over 10 MB)" | a fragment after "file.pdf:" |
| setup/dropzone.tsx:82 | "unsupported format (expected .pdf, .docx, …)" | "This file type isn't supported. Use PDF, Word, Markdown or text." | jargon |
| setup/dropzone.tsx:92 | "exceeds limit of 10 files" | "Too many files (limit 10)" | |
| setup/dropzone.tsx:183 | "Choose or drop files" / "Drop files here" | "Choose or drop a file" / "Drop a file here" when `maxFiles` is 1 | grammar (the New base resume dialog takes one file) |

### D7.3 Assistant page (`components/chat/chat-page.tsx`)

| line | current | new | why (category) |
|---|---|---|---|
| :715 | "Edit a resume, draft project points, or work on a template. Every edit is versioned." | "Edit a resume, draft project bullets or work on a template. You can undo any edit." | point, versioned |
| :480 | placeholder "Ask about your resume…" | "Ask the Assistant…" | an allowed composer prompt; the Assistant also edits templates and career history (update `_PROMPTS`) |
| :453, :521, :531 | aria "Pinned resume" / "No pinned resume" | "Resume to edit" / "No resume chosen" | "pin" named two things here |
| :546 | "Context" | "Add context" | matches the dialog title |
| :647 | "Couldn't load this conversation." | "Couldn't load this chat." | one word |
| :648 | load-error detail | `errorDetail(detail.error)` | D1.3 |
| :671 | tool chip `{name}` (raw tool name, e.g. `get_resume`) | a `TOOL_PHRASES` map (below), fallback "Working…" | **bug** (D10.12): engineer identifiers in the live thread |
| :756-758 | sr-only "Chat history" / "Browse and switch between past chats." | keep the title; remove the description | restates it |
| :823 | aria "Delete chat" deletes at once | keep the label; ask first: `confirm({ title: "Delete this chat?", description: "This deletes the chat and its messages. You can't undo this.", confirmLabel: "Delete", destructive: true })` | **[behaviour]** (D10.13): one click deleted with no undo |
| :287, :296 | `toast.error(err.message)` | `couldnt("start a new chat", err)`, `couldnt("delete the chat", err)` | D1.3 |
| :412 | `toast.error(event.detail)` (raw server error) | `toast.error(isPlainSentence(event.detail) ? event.detail : "The Assistant couldn't finish. Try again.")` | raw server text |
| :416 | `err instanceof Error ? err.message : "Chat failed"` | `couldnt("get a reply from the Assistant", err)` | tone |
| :441 | toast "Attached {file} ({n} chars)" | "Attached {file}" | a character count means nothing |
| :443 | toast "Upload failed" | `couldnt("attach the file", err)` | |

`TOOL_PHRASES` (a small map beside the chip; the tool names are the model's identifiers and stay; list
verified against the chat tool registry):

| tools | phrase |
|---|---|
| `list_base_resumes` | "Looking at your resumes…" |
| `get_resume` | "Reading your resume…" |
| `edit_resume` | "Editing your resume…" |
| `propose_edits`, `propose_project` | "Drafting a change for you to review…" |
| `read_attachment` | "Reading your attachment…" |
| `kb_list_entities`, `kb_get_entity`, `get_career_context` | "Reading your career history…" |
| `kb_capture` | "Saving to your career history…" |
| `analytics_activity`, `analytics_gap_frequency`, `analytics_base_summaries` | "Looking at your job search numbers…" |
| `list_templates`, `get_template` | "Looking at templates…" |
| `create_template_draft`, `update_template_draft`, `duplicate_template` | "Working on a template…" |
| `validate_template` | "Checking the template…" |
| `set_default_template` | "Setting your default template…" |
| `delete_template` | "Deleting a template…" |
| anything else | "Working…" |

The same phrase shows once even when the tool runs twice in a row (a `Set` of phrases, in order).

### D7.4 Assistant cards and the context dialog (`components/chat/*`)

| file:line | current | new | why (category) |
|---|---|---|---|
| change-card.tsx:40 | toast "Reverted. The previous content is current again." | "Undone. The previous version is back." | revert |
| change-card.tsx:42 | `toast.error(err.message)` | `couldnt("undo the edit", err)` | D1.3 |
| change-card.tsx:58-59 | "v{n} · {k} changes" | "Version {n}, {k} change" / "changes" | v12 |
| change-card.tsx:64 | "Diff" | "See changes" | jargon |
| change-card.tsx:73 | "Revert" / "Reverting…" | "Undo" / "Undoing…" | |
| change-card.tsx:84 | dialog "Changes in v{n} · {resume}" | "Changes in version {n} of {resume}" | |
| proposal-card.tsx:67 | "Proposed project" | "Suggested project" (A5 row 34) | after A |
| proposal-card.tsx:70, edit-proposal-card.tsx:118 | "→ {target}" | "For {target}" | the arrow was read aloud |
| proposal-card.tsx:56 | toast "Project merged into the resume" | "Project added to the resume" | |
| proposal-card.tsx:58 | `toast.error(err.message)` | `couldnt("add the project", err)` | D1.3 |
| proposal-card.tsx:85 | "Merged" / "Discarded" | "Added" / "Discarded" | |
| proposal-card.tsx:104 | "Merge into resume" / "Merging…" | "Add to resume" / "Adding…" | |
| edit-proposal-card.tsx:90 | toast "Suggestion applied to the resume" | "Edits applied" | matches "Suggested edits" and "Apply edits" |
| edit-proposal-card.tsx:94 | `toast.error(err.message)` | `couldnt("apply the edits", err)` | D1.3 |
| kb-capture-card.tsx:13 | badge "Career KB" | "Career history" | KB |
| kb-capture-card.tsx:15 | "Saved {n} drafts for {entity}" | "Saved {n} draft bullet" / "bullets" " to {item}" | "drafts" alone was ambiguous |
| kb-capture-card.tsx:19-20 | "Review inbox" → `/career#inbox` | "Review drafts" → `/career#kb-inbox` (the id the upload dialog uses) | "inbox" names the Agent inbox; one anchor |
| scope-picker.tsx:168-169 | "Resume chips limit what can be edited. Career KB chips add background the assistant reads first." | "Resume parts limit what the Assistant edits. Career history items give it background." | chips, KB, case |
| scope-picker.tsx:173-174 | tabs "Resume" / "Career KB" | "Resume" / "Career history" | KB |
| scope-picker.tsx:179 | "Loading Career KB…" | "Loading your career history…" | KB |
| scope-picker.tsx:182 | raw `error.message` | `LoadErrorState` "Couldn't load your career history." with Try again | raw; no retry. **[behaviour]** adds a retry |
| scope-picker.tsx:186 | "No Career KB entities yet." | "Nothing in your career history yet." | KB, entity |
| scope-picker.tsx:205 | aria "Pin {title}" | "Add {title}" | "Pin" vs "Add … to scope" in one dialog |
| scope-picker.tsx:236-239 | "Loading the pinned resume…" / "Couldn't load the pinned resume." / "Pin a resume in the composer to scope its sections." | "Loading your resume…" / "Couldn't load this resume." / "Choose a resume below the message box to pick its parts." | composer, scope |
| scope-picker.tsx:253 | "+ whole section" | "Add whole section" | |
| scope-picker.tsx:276 | aria "Show bullets" (never changes) | "Show bullets" / "Hide bullets" by state, plus `aria-expanded` | **[behaviour]** a11y state |
| scope-picker.tsx:294, :313 | aria "Add {label} to scope" / "Add bullet to scope" | "Add {label}" / "Add bullet {n}" | scope |
| scope-picker.tsx:40-41 | chip fallback "KB entity" / `experience[2]` | "Career history item" / "Experience 3" | raw index |
| scope-picker.tsx:46 | aria "Remove scope" | "Remove {label}" | |
| scope-picker.tsx:106 | "Untitled entry" | "Untitled item" | entry |

**Dropped from part 3, with the reason.** `persona-section.tsx`, `setup-steps.ts:144-145` and
`getting-started-card.tsx:31` "Goals and strengths": the owner keeps "Persona". `models-section.tsx`
"Reading model" and "Writing model": the owner keeps Fast and Smart (D6). The "match score" term: the
owner's term is "ATS score". `lib/humanize-slug.ts` "AI/ML", "UI/UX": kept (industry role names; the
ratchet exempts them). `components/load-error-state.tsx:39`, `:83`, `retry-chip.tsx:44`, `dialog.tsx`,
`sheet.tsx` "Close": already right.

### D7.5 Pins (L6)

| test | old | new |
|---|---|---|
| `test_frontend_chat_layout.py:65` | `_tag('aria-label="Pinned resume"')` | `_tag('aria-label="Resume to edit"')` |
| `test_frontend_placeholders.py:43` `_PROMPTS` | `("components/chat/chat-page.tsx", "Ask about your resume" + _ELLIPSIS)` | `("components/chat/chat-page.tsx", "Ask the Assistant" + _ELLIPSIS)` |
| `frontend/lib/nav.test.ts:26` | test title "…marks Agent Proposals instead" | appendix A1 renames it; unchanged here |
| `test_frontend_query_error_states.py:83` | `("components/setup/getting-started-card.tsx", "Getting started")` | unchanged (the title stays) |
| `test_frontend_vocabulary.py`, `test_frontend_error_words.py` | `_PENDING_L6` | delete |
| new, `test_frontend_plain_words.py` | none | `test_the_assistant_names_what_it_is_doing`: `"TOOL_PHRASES" in chat` and `'"Working…"' in chat`, and the chip no longer renders `{name}` directly (`"<Wrench className=\"size-3\" /> {name}" not in chat`) (D10.12) |
| new, same file | none | `test_deleting_a_chat_asks_first`: the Delete chat button's `onClick` awaits `confirm(` with `destructive: true` before `onDelete(` (D10.13) |
| new, same file | none | `test_setup_counts_agree_with_their_nouns`: `setup-steps.ts` has no `` `${…} base resumes · `` template and no "KB entries" (D10.8) |
| new, `test_frontend_sidebar_nav.py` | none | `test_the_sidebar_uses_the_glossary_names`: `'label: "Career history"'`, `'label: "Base resumes"'`, `'label: "Assistant"'` and `"Add job"` in `app-sidebar.tsx`; `"Career KB"`, `"Base Resumes"`, `'label: "Chat"'` and `"New application"` not in it |

### D7.6 Browser checks (L6)

1. Sidebar (1280 and 375, light and dark): Applications, Agent inbox, Referrals; Career history, Base
   resumes, Templates; Assistant, Analytics; the pinned button reads "Add job". The toggle's tooltip says
   "Hide sidebar (⌘B)" when open.
2. Assistant: ask for an edit. While it works, chips read "Reading your resume…" then "Drafting a change for
   you to review…", never `get_resume`. The page title in the tab is "Assistant — Maestro CS".
3. Delete a chat from the history rail: a confirm asks first; Cancel keeps it and focus returns to the
   Delete button; Delete removes it.
4. The context dialog: tabs "Resume" and "Career history"; the chips read "Experience 3", never
   `experience[2]`.
5. Stop the backend and reload any page: the load error reads "Maestro CS isn't responding. Check that it's
   running, then try again." with Try again; nothing mentions docker, curl or port 8001 (the console does).
6. Profile's strip and Getting started with one base resume: "1 base resume, 14 career history items".

---

## D8. Companion side panel (lane L7)

`extension/panel/**` and one shared file (`extension/shared/guided-run.js`). Source: audit part 3 §2.14,
re-verified string by string at `8cac7cf9`, plus a sweep for what it missed. Appendix C9 edits one string
here (`actions/fill.js:91`, "Profile → Autofill"); the owner wants "›", so this lane owns that line after C.
Apostrophes: keep each file's existing character (curly ’ in `pause.js`, `qna.js:129`, `stages/fill.js:111`,
`stages/resume.js:209`; straight elsewhere).

**Corrections to the audit.** `panel.js:1070-1071` is a template (the " at {url}" part appears once settings
load). "No base resume(s) yet" is two strings: `stages/score.js:59` says "resumes", `actions/qna.js:102` and
`actions/resume.js:159` say "resume" (now one sentence). `actions/score.js:98` and `stages/resume.js:186`
fall back to the slug.

### D8.1 Changes

| file:line | current (exact) | new | why (category) |
|---|---|---|---|
| panel.js:275 | "Add job" | "Save job" | owner: Save job |
| panel.js:276 | "Score all bases" | "Score base resumes" | bare "bases" |
| panel.js:286 | "Start fill" | "Fill this form" | says what it does |
| panel.js:320 | "Skipped — using base as-is" | "Skipped. Using your base resume as is." | em dash, bare base, as-is |
| panel.js:1070-1071 | `` `Maestro CS is not reachable${settings ? ` at ${backendUrl}` : ""}: ${result.error}` `` | "Couldn't reach Maestro CS. Check that it's running." | raw URL and error |
| panel.js:1508 | `` `Application · ${status ?? "draft"}` `` | draft → "Draft application"; otherwise the web label: "Applied", "Interviewing", "Offer", "Accepted", "Rejected", "Withdrawn" (`status-chip.tsx`) | raw status |
| panel.js:1510 | "In library" | "Saved" | "library"; matches the web's Saved |
| panel.js:1541 | empty ring label "ATS" | "ATS score" | the owner's term; it fits (11px under a 44px ring, like "Tailored") |
| panel.js:1544 | "score after adding the job" | "not scored yet" | also shows when the job is saved but unscored |
| panel.js:1832 | `` `Could not copy: ${String(err?.message ?? err)}` `` | "Couldn't copy the answer. Select it and copy it yourself." | raw error |
| panel.js:3516 | `String(err?.message ?? err)` ("no window is focused") | "Couldn't find the active tab. Click the page, then open Companion again." | raw error (missed by the audit) |
| stages/job.js:49 | `` `JD grabbed from this page · ${n} words` `` | `` `Job description found (${n} words)` `` | JD |
| stages/job.js:51 | "The companion cannot see this page — reload the tab." | "Companion can't read this page. Reload the tab." | name case, em dash |
| stages/job.js:97, :154 | "Untitled" | "Untitled job" | matches `panel.js:1563` (missed) |
| stages/job.js:100 | `` `${company} · ${title} · ${status}` `` | `` `${company} · ${title} · ${statusLabel}` `` ("… · Draft") | raw status |
| stages/job.js:157 | `` `${company} · ${title} · ${status}` `` | `` `${company} · ${title}` `` | the list is drafts only (`panel.js:3294`) |
| stages/job.js:201 | "Recent drafts — pick one to work on here" | "Recent drafts" | em dash, verbose |
| stages/score.js:59 | "No base resumes yet — build one in Maestro CS." | "No base resumes yet. Add one in Maestro CS." | em dash |
| stages/score.js:64 | "Not scored against this job yet — “Score all bases” runs it." | "Not scored for this job yet. Select Score base resumes below." | em dash, bases |
| stages/score.js:66-67 | `` `${plural(n,"base resume")} scored against this JD${engine ? ` · engine ${engine}` : ""}` `` | `` `${plural(n,"base resume")} scored for this job` `` | JD, engine id; `engineOf` (`:45-55`) becomes dead code, delete it |
| stages/resume.js:65 | "Custom in Studio ↗" | "Tailor in Maestro CS ↗" | "Studio" is internal |
| stages/resume.js:83 | "Stop using base as-is" | "Stop using the base resume" | |
| stages/resume.js:186 | `` `Using ${facts.baseSlug \|\| "your base resume"} as-is` `` | `` `Using ${displayName \|\| "your base resume"} as is` `` with `displayName = facts.resumes.find((r) => r.slug === baseSlug)?.display_name` | slug, as-is |
| stages/resume.js:190 | "Use base as-is" | "Use base resume as is" | |
| stages/resume.js:208-210 | "Custom opens the gap-filling tailor page; this panel picks the result up when it’s rendered." | "Tailor in Maestro CS opens the full tailor page. Companion picks up the tailored resume when its PDF is ready." | jargon, render, semicolon |
| stages/fill.js:48 | "Rules only" / "Rules + AI assist" | "Saved answers only" / "Saved answers + AI" | jargon |
| stages/fill.js:111 | `` `${n} didn’t stick` `` | `` `${n} not accepted` `` | |
| stages/fill.js:115 | "Profile fields" | "Saved answers" | the name used in Profile › Autofill |
| stages/fill.js:156, :159, :162 | "Voluntary disclosures" | "Diversity questions" | owner decision |
| stages/fill.js:159 | "skipped — EEO off" | "turned off in Profile › Autofill" | EEO, em dash |
| stages/fill.js:224-225 | `` `This page has ${boxes(n)} — attach your resume by hand ` `` + "so it goes to the right one." | `` `This page has ${boxes(n)}. Attach your resume yourself so it goes in the right one.` `` | em dash |
| stages/fill.js:350 | `` `one of: ${options.join(" · ")}` `` | `` `Options: ${options.join(" · ")}` `` | fragment; `·` stays (options can contain commas) |
| stages/fill.js:375-376 | "Already in your profile — the field refused the write, not the answer." | "Already in your saved answers. The page didn’t accept it, so check it and fill again." | em dash, jargon |
| stages/fill.js:537 | "Paste any question for a grounded answer" | "Paste a question to answer from your resume" | "grounded" |
| stages/fill.js:591-592 | "No application form on this page — open the employer's Apply page; filling starts there." | "No application form here. Open the employer's Apply page to start filling." | em dash, semicolon |
| stages/fill.js:663 | "Fills what your profile answers for. Nothing is sent to a model." | "Uses only your saved answers. Nothing goes to the AI." | keeps the privacy promise |
| stages/fill.js:664-665 | "Fills what your profile answers for, then asks for the rest. Identity fields are never sent." | "Uses your saved answers, then asks the AI for the rest. Your personal details never go to the AI." | keeps the privacy promise |
| stages/track.js:38 | "Still a draft — mark it Applied below once you have submitted it." | "Still a draft. Mark it Applied below after you submit it." | em dash |
| stages/track.js:43 | "Marked applied. The applied date is recorded." | "Marked applied." | the date is on the line below |
| stages/track.js:57-59 | "This page was filled from your base resume, and nothing has been written down for it. Open Maestro CS to save the job and an application." | "Filled from your base resume, but not tracked yet. Open Maestro CS to save the job and track it." | verbose |
| stages/track.js:60-61 | "This page was filled from your base resume, and nothing has been written down for it." | "Filled from your base resume, but not tracked yet." | (missed) |
| stages/track.js:94 | `` `${evidence.pdfName} rendered` `` | `` `${evidence.pdfName} ready` `` | render |
| stages/track.js:135 | `` `Status: ${status}. Change it in Maestro CS.` `` | `` `Status: ${statusLabel}. Change it in Maestro CS.` `` ("Status: Interviewing.") | raw status |
| actions/during.js:78 | `String(err?.message ?? err)` for every failed round trip | one sentence per call site (next table); a message the panel wrote itself (marked `err.shown = true`) still passes through | raw error (missed) |
| actions/job.js:49 | "Nothing to save yet — add a title, or open a job posting." | "Nothing to save yet. Add a title or open a job page." | em dash, posting |
| actions/job.js:69 | "Already tracked. This posting was saved earlier." | "Already saved in Maestro CS." | posting |
| actions/job.js:70 | `` `Saved with ${plural(skills,"skill")} extracted.` `` | `` `Saved. Found ${plural(skills,"skill")}.` `` | extract |
| actions/score.js:52, actions/resume.js:69 | "Add the job first." | "Save the job first." | Save job |
| actions/score.js:98-99 | `` `Best match: ${best.display_name \|\| best.slug} · ATS ${n}.` `` | `` `Best match: ${name} (ATS score ${n}).` `` | ATS score |
| actions/score.js:104 | "Scored, but no base resume came back with a number." | "Scored, but no base resume got an ATS score." | |
| actions/resume.js:94-96 | `` `${warning}Nothing to tailor. No gap this profile is allowed to resolve. Attach the base resume instead, or open it in Maestro CS.` `` | `` `${warning}Quick tailor has nothing to change for this job. Use your base resume as is, or tailor it in Maestro CS.` `` | jargon |
| actions/resume.js:114-115 | `` `${warning}Tailored, but the PDF render failed. Open it in Maestro CS to see why and re-render.` `` | `` `${warning}Tailored, but couldn't create the PDF. Open it in Maestro CS and select Create PDF.` `` | render; the web says Create PDF (D2) |
| actions/resume.js:159, actions/qna.js:102 | "No base resume yet — build one in Maestro CS." | "No base resumes yet. Add one in Maestro CS." | em dash; one sentence with `score.js:59` |
| actions/qna.js:103-104 | "Add the job first — an answer is grounded in your resume and this posting." | "Save the job first. Answers come from your resume and this job." | em dash, grounded, posting |
| actions/qna.js:130 | "Answered from your base resume and this posting." | "Answered from your base resume and this job." | posting (missed) |
| actions/fill.js:91-92 | "No autofill profile yet. Fill it in under Profile in Maestro CS." (C9: "…under Profile → Autofill in Maestro CS.") | "No saved answers yet. Add them in Maestro CS under Profile › Autofill." | **delta on C9**: "›" |
| actions/fill.js:308-310 | "The rules ran; the page stopped answering before the questions could be collected. What they filled is below — reload the tab to finish the rest." | "Couldn't finish filling this page. Reload the tab to fill the rest." | semicolon, em dash, error form |
| actions/fill.js:421-422 | "The tailored PDF is not rendered anymore. Open it in Maestro CS and generate it again." | "Couldn't find the tailored PDF. Open it in Maestro CS and select Create PDF." | render |
| actions/fill.js:453 | "No upload box on this page took the file. Attach it by hand." | "Couldn't attach your resume. No upload box took it, so attach it yourself." | error form |
| actions/fill.js:454-455 | "This page's upload boxes changed while you were pressing, so nothing was attached." | "Couldn't attach your resume. The page's upload boxes changed, so check them and try again." | error form |
| actions/pause.js:234-235 | "This one is never filled from here — signatures, passwords and government IDs are yours to type." | "Companion never fills this. Signatures, passwords and ID numbers are yours to type." | em dash; keeps the promise |
| actions/pause.js:289 | " Saved to your profile." | " Saved to Profile › Autofill." | where it lives |
| actions/pause.js:290 | " Remembered — this one won’t ask again." | " Saved. It won’t ask again." | em dash |
| actions/pause.js:298-299 | `` ` Filled, but not remembered: ${String(err?.message ?? err)}` `` | " Couldn’t save the answer, so it will ask again." | raw error (missed) |
| actions/pause.js:309 | "That answer didn’t match any of the options — try one of them verbatim." | "Couldn’t fill that. Type one of the options exactly as shown." | em dash, "verbatim" |
| actions/pause.js:310 | "The field wouldn’t take that value. Try it on the page." | "Couldn’t fill that field. Type it on the page yourself." | error form |
| actions/track.js:104 | `` `Status updated to ${status}.` `` | `` `Status updated to ${statusLabel}.` `` | raw status |
| actions/track.js:144 | "Nothing to track yet — this page's job is not in the library." | "Nothing to track yet. Save this job first." | em dash, library |
| actions/track.js:171 | "Tracked. Mark it applied when you have submitted it." | "Tracked. Mark it Applied after you submit it." | the status label |
| shared/guided-run.js:69-72 (`NO_FRAME_REACHED`) | "Can't reach this page. Reload the tab, then try again. The page script loads with the page, so a tab that was already open when the extension last reloaded does not have it." | "Couldn't reach this page. Reload the tab, then try again. Tabs that were open before Companion updated need a reload." | "extension", error form |

**The per-call-site failure sentences** (replacing the raw text at `actions/during.js:78`); each gets "Check
that Maestro CS is running." when `err.status` is undefined (no HTTP answer), else "Try again.":

| call site | sentence |
|---|---|
| addJob (`actions/job.js:57`) | "Couldn't save the job." |
| pickApplication (`actions/pick.js:148`; a 404 still becomes the deleted-draft note) | "Couldn't open that draft." |
| scoreAllBases (`actions/score.js:56`) | "Couldn't score your base resumes." |
| quickTailor (`actions/resume.js:81`) | "Couldn't tailor your resume. Open the job in Maestro CS to see why." |
| startFill (`actions/fill.js:262`) | "Couldn't fill this form." |
| attachResume (`actions/fill.js:403`) | "Couldn't attach your resume." |
| submitAnswer (`actions/pause.js:268`) | "Couldn't fill that field." |
| askQuestion (`actions/qna.js:108`) | "Couldn't answer that question." (a 400: "Couldn't answer from this base resume. Open it in Maestro CS to check it.") |
| setStatus (`actions/track.js:75`) | "Couldn't update the status." |
| trackThis (`actions/track.js:149`) | "Couldn't track this application." |

**Machine keys (do not rename).** Status keys (`draft`, `applied`, …) drive `STATUS_OPTIONS`, the PATCH
body, `TRACK_NOTES[status]`, the `draft-on` class and `?status=draft`; labels are display-only. Fill-mode
values `"rules"`/`"assist"` are stored in `chrome.storage.sync`; only the labels change. `baseSlug` stays the
API key. `PREVIEW_FIELDS` "Title"/"Company"/"Location" (`panel.js:1094-1096`) are parsing keys matched
against the agent's `Title: …` lines. `pick.js` relies on `err.status === 404`, so keep `status` on errors.
`extension/sw.js:84` still `JSON.stringify`s a non-string `detail`; the call-site sentences above keep it
off the panel.

**Kept on purpose.** `panel.html:5` "Maestro CS"; the rail names Job, Score, Resume, Fill, Track and their
states; "Quick tailor" and "Tailor"; "Open application ↗", "Open in Maestro CS ↗"; the "New" chip; "Base" and
"Tailored" ring labels; "tailor to raise it"; "Untitled job"; the Draft/Applied segment; the select prompt
"Choose a draft application…"; "Stop using this draft"; "No job description found on this page."; the fill
counters and question words listed as fine in the audit; "Paste one question…" (a composer prompt); "Ready
to autofill from your base resume." (`shared/decisions.js:147`); the load-order throws in `stages.js:100`
and `actions.js:108` (developer text, allowlisted in D0); "⚠ {health_warning}" (server-written, D9).

### D8.2 Pins (L7)

Test drivers that click by label text throw when a label is missing (`test_extension_panel_resume.py:70`
`press(label)`, `:562/:570/:581`; `test_extension_panel_fill.py:85` `mode=`), so change these first.

| test file:line | old | new |
|---|---|---|
| `test_extension_panel.py:884, :1589, :1604`; `test_extension_panel_job.py:1467` | "Add job" / `["Add job"]` | "Save job" / `["Save job"]` |
| `test_extension_panel.py:958` | `startswith("Maestro CS is not reachable")` | `startswith("Couldn't reach Maestro CS")` |
| `test_extension_panel.py:1010, :1599` | `"not reachable" in …` | `"Couldn't reach Maestro CS" in …` |
| `test_extension_panel.py:1025` | `== "no window is focused"` | `== "Couldn't find the active tab. Click the page, then open Companion again."` |
| `test_extension_panel.py:1498-1499, :1505-1506` | "Maestro CS is not reachable at http://localhost:8001: Failed to fetch" / "Maestro CS is not reachable: Failed to fetch" | "Couldn't reach Maestro CS. Check that it's running." plus `"localhost" not in` and `"Failed to fetch" not in`; rename the test (it pinned the opposite) and drop its stale "§11.4" citation |
| `test_extension_panel.py:1148`; `test_extension_panel_resume.py:262, :322, :687` | "Skipped — using base as-is" | "Skipped. Using your base resume as is." |
| `test_extension_panel.py:1538, :1773`; `test_extension_panel_job.py:794, :863, :882, :2227, :2393, :2414, :2472` | "Application · draft" | "Draft application" |
| `test_extension_panel.py:1897`; `test_extension_panel_track.py:450` | "Application · applied" | "Applied" |
| `test_extension_panel_track.py:306, :485` | "Application · interviewing" | "Interviewing" |
| `test_extension_panel.py:2347, :2352`; `test_extension_panel_fill.py:436, :505`; `test_extension_panel_job.py:1337` | "Start fill" | "Fill this form" |
| `test_extension_panel.py:2348, :2722` | "Score all bases" | "Score base resumes" |
| `test_extension_panel_job.py:164, :1606, :1631, :1659, :1688, :1748, :1884, :1956` | "JD grabbed from this page · 11 words" | "Job description found (11 words)" |
| `test_extension_panel_job.py:1534` (`RELOAD_LINE`) | "The companion cannot see this page — reload the tab." | "Companion can't read this page. Reload the tab." |
| `test_extension_panel_job.py:675` | `"Recent drafts — pick one to work on here" in labels` | `"Recent drafts" in labels` |
| `test_extension_panel_job.py:383` | "the backend is unreachable" | "Couldn't save the job. Check that Maestro CS is running." |
| `test_extension_panel_job.py:861` | "the backend is unreachable" | "Couldn't open that draft. Check that Maestro CS is running." |
| `test_extension_panel_job.py:496` | "Saved with 3 skills extracted." | "Saved. Found 3 skills." |
| `test_extension_panel_job.py:516` | "Already tracked. This posting was saved earlier." | "Already saved in Maestro CS." |
| `test_extension_panel_job.py:2303` (`_claims_an_application`) | `"Application" in chip` | check the chip's `app` class (the old check passes vacuously once the word goes) |
| `test_extension_panel_job.py:448`; `test_extension_panel_score.py:680`; `test_extension_panel_resume.py:518` (race tests) | old raw text not in the JSON | also assert the new sentence is absent ("Couldn't save the job", "Couldn't score", "Couldn't tailor") |
| `test_extension_panel_score.py:146, :767, :744` | "2 base resumes scored against this JD · engine ats-2.3.0" / "…against this JD" | "2 base resumes scored for this job"; fold or delete the two engine tests (their subject is gone) |
| `test_extension_panel_score.py:612` | "Not scored against this job yet — “Score all bases” runs it." | "Not scored for this job yet. Select Score base resumes below." |
| `test_extension_panel_score.py:628` | "Best match: AI/ML Engineer · ATS 72." | "Best match: AI/ML Engineer (ATS score 72)." |
| `test_extension_panel_score.py:640` | "the backend is unreachable" | "Couldn't score your base resumes. Check that Maestro CS is running." |
| `test_extension_panel_resume.py:170, :778` | `["Use base as-is", "Tailor"]` | `["Use base resume as is", "Tailor"]` |
| `test_extension_panel_resume.py:184-185, :726-727` | `[…"Use base as-is"…"Custom in Studio ↗"]` | `[…"Use base resume as is"…"Tailor in Maestro CS ↗"]` |
| `test_extension_panel_resume.py:198, :229, :701; :374` (dict key) | "Custom in Studio ↗" | "Tailor in Maestro CS ↗" |
| `test_extension_panel_resume.py:199` | `startswith("Custom opens")` | `startswith("Tailor in Maestro CS opens")` |
| `test_extension_panel_resume.py:208-210` | the old sentence | "Tailor in Maestro CS opens the full tailor page. Companion picks up the tailored resume when its PDF is ready." |
| `test_extension_panel_resume.py:243; :371` (dict key); `:258, :286, :319, :822` (`press=`); `:830` (not in) | "Use base as-is" | "Use base resume as is" |
| `test_extension_panel_resume.py:327-328`; `test_extension_panel_fill.py:473-474, :2679-2680` | "No application form on this page — open the employer's Apply page; filling starts there." | "No application form here. Open the employer's Apply page to start filling." |
| `test_extension_panel_resume.py:437` | "409: health gate" | "Couldn't tailor your resume. Open the job in Maestro CS to see why." |
| `test_extension_panel_resume.py:458-460` | "⚠ Base resume health is C Tailored, but the PDF render failed. Open it in Maestro CS to see why and re-render." | "⚠ Base resume health is C Tailored, but couldn't create the PDF. Open it in Maestro CS and select Create PDF." (the warning prefix is D9's; update it with D9 if L8 lands first) |
| `test_extension_panel_resume.py:479` | `startswith("Nothing to tailor.")` | `startswith("Quick tailor has nothing to change")` |
| `test_extension_panel_resume.py:486` | `["In library"]` | `["Saved"]` |
| `test_extension_panel_resume.py:581` (JS driver); `:672, :702, :827` | "Stop using base as-is" | "Stop using the base resume" |
| `test_extension_panel_resume.py:670, :826` (in); `:722, :780` (not in) | "Using ai_ml_engineer as-is" | "Using AI/ML Engineer as is" (check the fixture loads `resumes`, else "your base resume") |
| `test_extension_panel_fill.py:429, :503; :519, :651` (`mode=`) | "Rules only", "Rules + AI assist" | "Saved answers only", "Saved answers + AI" |
| `test_extension_panel_fill.py:432-433` | `endswith("then asks for the rest. Identity fields are never sent.")` | `endswith("then asks the AI for the rest. Your personal details never go to the AI.")` |
| `test_extension_panel_fill.py:530-531` | "Fills what your profile answers for. Nothing is sent to a model." | "Uses only your saved answers. Nothing goes to the AI." |
| `test_extension_panel_fill.py:596, :811, :861-862` | ("Profile fields", "2 filled · 1 already filled · 1 didn’t stick") | ("Saved answers", "2 filled · 1 already filled · 1 not accepted") |
| `test_extension_panel_fill.py:868, :920` | ("Profile fields", "1 filled") | ("Saved answers", "1 filled") |
| `test_extension_panel_fill.py:600, :812, :869, :922` | ("Voluntary disclosures", "skipped — EEO off") | ("Diversity questions", "turned off in Profile › Autofill") |
| `test_extension_panel_fill.py:687-688, :697-698` | `["Voluntary disclosures"]` | `["Diversity questions"]` |
| `test_extension_panel_fill.py:818-821; :877; :969` | "The rules ran; … finish the rest." / `startswith("The rules ran;")` / `"The rules ran" not in` | "Couldn't finish filling this page. Reload the tab to fill the rest." / `startswith("Couldn't finish filling")` / `"Couldn't finish filling" not in` |
| `test_extension_panel_fill.py:968, :989, :1595`; `test_extension_guided_fill.py:454` | `startswith("Can't reach this page.")` | `startswith("Couldn't reach this page.")` |
| `test_extension_panel_fill.py:1312-1314` | "Filled “how did you hear about us?”. Saved to your profile. 1 field still needs you." | "Filled “how did you hear about us?”. Saved to Profile › Autofill. 1 field still needs you." |
| `test_extension_panel_fill.py:1457 / :1458` | `"Remembered" not in` / `"profile" not in` | `"won’t ask again" not in` / `"Profile" not in` |
| `test_extension_panel_fill.py:1550-1551` | "Already in your profile — the field refused the write, not the answer." | "Already in your saved answers. The page didn’t accept it, so check it and fill again." |
| `test_extension_panel_fill.py:1580-1581` | "That answer didn’t match any of the options — try one of them verbatim." | "Couldn’t fill that. Type one of the options exactly as shown." |
| `test_extension_panel_fill.py:1619-1621` | "…Filled, but not remembered: 500: settings unavailable 1 field still needs you." | "…Couldn’t save the answer, so it will ask again. 1 field still needs you." |
| `test_extension_panel_fill.py:1762-1764` | `["This one is never filled from here — signatures, passwords and government IDs are yours to type."] * 3` | `["Companion never fills this. Signatures, passwords and ID numbers are yours to type."] * 3` |
| `test_extension_panel_fill.py:1805` | "one of: LinkedIn · A friend" | "Options: LinkedIn · A friend" |
| `test_extension_panel_fill.py:2197` | "Paste any question for a grounded answer Ask" | "Paste a question to answer from your resume Ask" |
| `test_extension_panel_fill.py:2287` | "Answered from your base resume and this posting." | "Answered from your base resume and this job." |
| `test_extension_panel_fill.py:2297` | `startswith("Add the job first")` | `startswith("Save the job first")` |
| `test_extension_panel_fill.py:2315` | "No base resume yet — build one in Maestro CS." | "No base resumes yet. Add one in Maestro CS." |
| `test_extension_panel_fill.py:2335` | `== detail` (the backend's 400 text) | add `"status": 400` to the fixture at `:2331`, then "Couldn't answer from this base resume. Open it in Maestro CS to check it." (the test's purpose changes) |
| `test_extension_panel_fill.py:2410` | `startswith("Could not copy:")` | `== "Couldn't copy the answer. Select it and copy it yourself."` |
| `test_extension_panel_fill.py:2768 / :2785` | `"upload boxes changed while you were pressing" in` / `…not in` | `"upload boxes changed"` |
| `test_extension_panel_fill.py:2783, :2860` | `"No upload box on this page took the file" in` | `"No upload box took it" in` |
| `test_extension_panel_fill.py:2883 / :2929` | `"not rendered anymore"` in / not in | `"Couldn't find the tailored PDF"` |
| `test_extension_panel_track.py:199` | `"mark it Applied below" in` | `"Mark it Applied below" in` |
| `test_extension_panel_track.py:232, :466` | "📎 tailored-resume.pdf rendered · applied 2026-08-18" | "📎 tailored-resume.pdf ready · applied 2026-08-18" |
| `test_extension_panel_track.py:307, :486` | `"Status: interviewing" in` | `"Status: Interviewing" in` |
| `test_extension_panel_track.py:286, :713` | `"filled from your base resume" in` | `"Filled from your base resume" in` |
| `test_extension_panel_track.py:407` | `"nothing has been written down" in` | `"not tracked yet" in` |
| `test_extension_panel_track.py:545` | "the tracker is unreachable" | "Couldn't update the status. Check that Maestro CS is running." |
| `test_extension_panel_track.py:760` | "the tracker is unreachable" | "Couldn't track this application. Check that Maestro CS is running." |
| `test_frontend_vocabulary.py` | `_PENDING_L7` | delete |

Still matching (no change): `extension_panel_harness.py:562` `NOTHING_TO_SAVE = "Nothing to save yet"`,
"Marked applied", "Tracked", "Still a draft", "This page has 2 upload boxes", "Open Maestro CS".

### D8.3 Harness and browser checks (L7)

1. From `backend/`: `pytest tests/test_extension_panel.py tests/test_extension_panel_job.py
   tests/test_extension_panel_score.py tests/test_extension_panel_resume.py tests/test_extension_panel_fill.py
   tests/test_extension_panel_track.py tests/test_extension_guided_fill.py -q`. Before the pin edits, the
   only failures are the rows above.
2. Identity strip: `-k test_a_loaded_page_renders_as_itself_from_end_to_end` with a temporary print of the
   identity region: "Draft application", the rings; the footer carries "Save job"; the empty ring reads "ATS
   score" over "not scored yet".
3. Fill stage: `-k "test_the_progress_rows_are_the_runs_own_report or test_the_eeo_row_says_what_the_backend_consented_to"`:
   "Saved answers", "Diversity questions", "turned off in Profile › Autofill"; the mode segment reads "Saved
   answers only | Saved answers + AI".
4. Errors: `-k "unreachable_line or tailor_that_fails or status_write_that_fails or refused_ask or page_that_stopped_answering"`:
   every note is a "Couldn't … ." sentence with no "localhost", "409", "Failed to fetch" or backend detail.
5. Real Chrome: load `extension/` unpacked against a worktree backend, open a Greenhouse posting, drag the
   panel to 320px. "Saved answers only | Saved answers + AI" and "ATS score" under the empty ring do not
   wrap badly; "Score base resumes" and "Fill this form" sit beside the Draft/Applied segment.

---

## D9. Server-written words the UI shows (lane L8)

Backend services and routers whose text the web app (or Companion) prints. Source: audit part 1 §2.12,
the part 2 note, part 3 §2.13, and a full read of the modules below. **Consumers.** Every HTTP error
`detail` also reaches MCP agents word for word (`mcp_server/client.py:239-243` wraps it as `"Backend returned
{status}: {body}"`, `server.py:91` raises it as a ToolError). Agents read and relay these; except for the
strings under *Kept on purpose*, none is branched on, so a plain rewrite keeps the agent's meaning. Stored
copies (health `report_json`, each gap analysis's `gaps_json`, `AtsScore.subscores_json`,
`KBDocument.ingest_summary`, `ResumeVersion.summary`) keep their old words until they are recomputed; where
a key exists (a category `key`, a note `rule`, a gate `id`) the frontend maps by key so old rows read the
new words too. `main.py:87` is a server log line and never reaches the UI (no change needed; C9 may still
align it).

### D9.1 Before any health wording changes: keep finding ids stable [behaviour]

`resume_lint._fid` (`:83-85`) hashes `(type, location, issue)`, and saved number answers
(`HealthAskAnswer`, keyed on `finding_id`, `routers/resume_lint.py:283`) match by that id. Rewording an
`issue` would silently drop every saved answer for it. **Add an `id_key` parameter to `_finding`**
(`"id": _fid(ftype, location, id_key or issue)`) and pass, for every rule whose `issue` changes below, the
old text formatted exactly as today, kept as a constant beside the new text (for example
`_ID_KEY_SCALE = "Has a scale metric, but not a business outcome."`). Ids stay byte-identical; no data
migrates. Pin: `test_resume_lint.py::test_reworded_findings_keep_their_ids` builds each changed rule's
finding and asserts `finding["id"] == _fid(type, location, <old issue>)`.

### D9.2 Health report (`resume_lint.py`, `health_gates.py`, `health_zones.py`)

Reaches the health report (label, issue, why and how group headers, question, gate label, detail and fix
hint) and the tailored review (gate label and detail, hygiene issue and how); MCP `run_health_check`,
`get_health_report`. Gate `why` is agent-only (the web filters gate findings, `health-report-page.tsx:259`).

| file:line | current | new | why (category) |
|---|---|---|---|
| resume_lint.py:69 | "What number measures this — users, rows, %, time saved?" | "What number measures this: users, rows, percent or time saved?" (keep the prefix "What number measures this": `METRIC_ASK_NEEDLE`, `health-report.ts:334`, matches it) | em dash |
| resume_lint.py:72 | "Has a scale metric, but not a business outcome." | "Has a number for size, but not for the result." | jargon (id key, D9.1) |
| resume_lint.py:193, :196; health_gates.py:88 | `f"{company} — {role}"`, `f"{institution} — {degree}"` ("?" when missing) | `"{role} · {company}"`, `"{degree} · {institution}"`, dropping a missing part (matches `groupTitle`, `health-report.ts:205`) | punctuation, "?" |
| resume_lint.py:220 | `f" — {heading}"` | `" · {heading}"` | |
| resume_lint.py:322 (S1) | label "Parse fidelity" | "PDF text is readable" | jargon |
| resume_lint.py:323 | "Could not certify the template's PDF text extraction." | "Couldn't check whether applicant tracking systems can read this template's PDF." | certify |
| resume_lint.py:326 | "The template's PDF round-trips through a strict extractor intact." | "Applicant tracking systems can read all of this template's PDF." | jargon |
| resume_lint.py:330-331 | "The template's PDF drops text under a strict extractor: " + probe list | "Applicant tracking systems can't read some of this template's text. Pick another template." | jargon; the probe list leaves the UI |
| resume_lint.py:339-340 (S2) | "Contact reachable" / "No email address in the resume — recruiters can't reach you." | "Email is readable" / "Your resume has no email address, so recruiters can't reach you." | em dash |
| resume_lint.py:343-344 | "Your email is in the data but the template's PDF renders it where a strict extractor drops it." | "Your email is on your resume, but applicant tracking systems can't read it in this template's PDF." | render |
| resume_lint.py:347 | "Email present in data; template extraction not certified." | "Your email is on your resume. Couldn't check whether this template keeps it readable." | semicolon, certify |
| resume_lint.py:350 | "Email present and survives PDF extraction." | "Your email is on your resume and readable in the PDF." | |
| resume_lint.py:354-355 (S4) | "Standard headers" / "Template header extraction not certified." | "Standard section headings" / "Couldn't check this template's section headings." | certify |
| resume_lint.py:360-361 | "These standard section headers didn't survive extraction: " + "experience, education" | "Applicant tracking systems can't read these section headings: Experience, Education." | raw lowercase keys |
| resume_lint.py:364 | "Standard section headers are present and extractable." | "Your section headings are standard and readable." | |
| resume_lint.py:388 (C1) | "Hot-zone evidence floor" | "Strong opening" | jargon |
| resume_lint.py:389-390 | `f"Top-of-resume evidence averages {e_hot:.2f} (floor {HOT_ZONE_FLOOR}); a dead opening sharply cuts the odds of a deep read."` | "Your summary and newest role are weak, so a recruiter may stop reading before your best work." | raw decimals, semicolon |
| resume_lint.py:401 (C2) | "Claim/date consistency" | "Years match your dates" | slash |
| resume_lint.py:402-403 | `f"Summary claims {claimed}+ years; the dates support ~{actual}."` | "Your summary says {n}+ years, but your dates add up to about {m}." (whole numbers; today it prints "8.0+") | raw value, semicolon |
| resume_lint.py:454-455 | "Ambiguous — this may be missing a number." / "The classifier couldn't decide; usually that means a metric is almost there." | "This may be missing a number." / "We couldn't tell how strong this is. Usually a number is almost there." | em dash, semicolon, jargon |
| resume_lint.py:520-522 | `f"{m}-month gap between {a} and {b} — {c} months covered by your education; {u} months unaccounted."` | "{m}-month gap between {a} and {b}. Your education covers {c} months, leaving {u} unexplained." | em dash, semicolon |
| resume_lint.py:532 | "Unexplained gaps cost ~45% of callbacks; one line of explanation recovers most of it." | "Unexplained gaps cost about 45% of callbacks. One line of explanation wins most of that back." | "~", semicolon |
| resume_lint.py:644-647 | "Evidence concentrated in projects" / `f"{p} project bullets vs {j} employment bullets."` / "…project-heavy evidence can read junior." / "Lead with employment; move projects below." | "Projects outweigh your jobs" / "{p} project bullets and {j} job bullets." / "With your experience, a resume led by projects can read as junior." / "Lead with your jobs and move projects below them." | evidence, vs, semicolon |
| resume_lint.py:665 | "Your highest-evidence bullet is below the high-attention zone." | "Your strongest bullet sits below the part recruiters read first." | jargon |
| resume_lint.py:718 | "Add 2–3 lines: role identity, years, strongest proof points." | "Add 2 to 3 lines: your role, your years and your strongest results." | jargon |
| resume_lint.py:729 | "Past ~7 bullets, each extra one dilutes the others." | "After about 7 bullets, each extra one weakens the others." | "~" |
| resume_lint.py:779-780 | "Keyword credit only; an LLM screener sees no evidence behind it." / "Show it in a bullet, or accept it as keyword-only." | "It earns keyword credit only. AI screeners see no proof of it." / "Show it in a bullet, or leave it as a keyword." | semicolon, jargon |
| health_gates.py:32, :36 (`why`, agents only) | "…This blocks tailoring until fixed or waived." | "…You can't start a gap analysis until you fix it or mark it as OK." | glossary (agent meaning kept: blocked until fixed or waived) |
| health_gates.py:33, :45 (`fix_hint`) | "…then validate it again." / "…then validate the template again." | "…then check it again." / "…then check the template again." | glossary |
| health_gates.py:57 | "…or waive the gate with a recorded reason if the dates intentionally omit work." | "…or mark it as OK with a reason if your dates leave out work on purpose." | waive |
| health_gates.py:95, :97 | `f"{name}: start date unparseable"` / "…end date unparseable" | "{role} · {company}: can't read the start date" / "…the end date" | jargon |
| health_gates.py:99-100 | "Dates parseable" / "No unparseable experience dates found." | "Dates are readable" / "All your job dates are readable." | jargon |
| health_gates.py:151 (S5) | "No placeholders"; detail = `"; ".join(hits)` of schema paths (`experience[0].bullet[2]`, `extra[awards].entry[1].heading`, from `_iter_texts` `:113-139`) | "No placeholder text"; the places in words, joined with ", ": "Summary", "{role} · {company}, bullet 3", "{section title}: {heading}" | schema paths (raw-value) |
| health_zones.py:134 | tier `"early"` / `"experienced"` | keep the values; the frontend maps them (D4.5) | machine-read |

`health_guards.py`, `health_verify.py`, `health_score.py` and `coherence_check.py` write nothing the web
shows directly (prompt text, LLM context, or enums the frontend maps: `ISSUE_LABELS`, `diff-review.tsx:450`).

### D9.3 Knock-out checks and the job-search brief (deltas on C9)

`knockout.py` messages show on the job page's knock-out card (`job-knockout-card.tsx:89`) and in MCP
`get_job`. No test pins them. Appendix C9 fixes the wrong page on `:63`, `:81`, `:125` with "→"; these rows
replace C9's text for those three (**delta on C9**: "›", no slash, no semicolon) and add the rest.

| line | current | new | why |
|---|---|---|---|
| :63 | "Posting requires citizen/green-card status; set your work authorization in Settings." | "This job requires US citizenship or a green card. Add your work authorization in Profile › Autofill." | wrong page, slash, semicolon |
| :67 | "Posting requires US citizen or green-card status." | "This job requires US citizenship or a green card." | tone |
| :76 | `f"Posting offers no sponsorship; your profile needs sponsorship {timing}."` | "This job doesn't sponsor visas, and you need sponsorship {now \| in the future}." | semicolon |
| :81 | "Posting offers no sponsorship; answer the sponsorship questions in Settings." | "This job doesn't sponsor visas. Answer the sponsorship questions in Profile › Autofill." | wrong page |
| :96 (pass; agents only) | "Posting offers sponsorship." | "This job sponsors visas." | tone |
| :125 | "Posting states an OPT policy; set your work authorization in Settings." | "This job states an OPT policy. Add your work authorization in Profile › Autofill." | wrong page |
| :131 | `f"Posting {policy}."` ("does not accept OPT", "accepts STEM OPT only") | "This job doesn't accept OPT." / "This job accepts STEM OPT only." | tone |
| :183 | "Posted range tops out below your desired salary." | "The posted pay tops out below your desired salary." | |
| :210-211 | `f"Posting asks {n}+ years; your profile states {y}."` | "This job asks for {n}+ years. Your profile says {y}." | semicolon |
| job_search_brief.py:72-74 (MCP only) | "…Fix it in Settings before filtering jobs on it" (and raw keys `authorized_to_work / requires_sponsorship`) | "Your work authorization answers are incomplete. Fix them in Profile › Autofill before filtering jobs on them. The brief never guesses." | wrong page, raw keys (C9 missed this line) |
| job_search_brief.py:78-81 (MCP only; C9 has `:80`) | "…correct the autofill profile in Settings before relying on them." (with `authorized_to_work='no'`) | "Your work authorization answers are contradictory: not authorized to work, and no sponsorship needed. The brief passes them on unchanged. Correct them in Profile › Autofill before relying on them." | wrong page; keep "incomplete" and "contradictory" (`test_job_search_brief.py:161, 212, 236, 338`) |

### D9.4 Gap page, ATS, tailoring, job market, PDF notes, document summaries

**`gap_analysis.py`** (gap page headers and details; MCP `create_tailoring_session`, `get_tailoring_session`,
`quick_tailor`; gap `detail` also feeds the tailor prompt). Stored in `gaps_json`: the frontend maps
category titles and descriptions by `category.key`.

| line | current | new | tests |
|---|---|---|---|
| :11 | "Missing skills" / "JD skills with no evidence on the resume" | "Missing skills" / "Skills the job asks for that your resume doesn't show" | `test_explore_gaps.py:96` (fixture) |
| :12 | "Wording mismatches" / "Matched semantically but the literal JD token is missing" | "Different wording" / "Your resume says it differently from the job description" | |
| :13 | "Placement upgrades" / "In the skills list but not corroborated in any dated entry" | "Skills with no example" / "In your skills list, but no job or project shows it" | |
| :14 | "Stale evidence" / "Matched, but the latest evidence is old or undated" | "Old or undated examples" / "Your resume shows it, but only in older or undated work" | |
| :15 | "Adjacent skills" / "Transferable skills that could be surfaced explicitly" | "Related skills" / "Related skills you could name directly" | |
| :16 | "Uncovered responsibilities" / "JD responsibilities your resume prose does not clearly cover" | "Job duties not covered" / "Duties in the job description your resume doesn't clearly cover" | `test_gap_analysis.py:136` |
| :17 | "Title &amp; structure" / "Title alignment, experience gate, format lint" | "Title and format" / "Your job title, the experience the job asks for, and format checks" | |
| :169 | "Resume prose does not clearly cover this responsibility" | "Your resume doesn't clearly show this duty." | `test_gap_analysis.py:143` |
| :178 | "Resume title/headline does not directly match the JD title" | "Your resume title doesn't match the job title." | |
| :183 | "Refresh the summary as a JD-aligned value proposition" | "Rewrite your summary for this job." | `test_gap_analysis.py:118` |
| :195 | "{flag}. Fix this in the base resume." | keep | |

**`ats/layers.py`, `ats/engine.py`** (the Score tab's badges and warnings, the gap page; MCP `score_ats`;
stored in `subscores_json`).

| line | current | new | tests |
|---|---|---|---|
| layers.py:669 | `f"JD asks for {n}+ years; dated entries show {y:.1f}"` | "The job asks for {n}+ years. Your dates show about {y}." (whole number) | |
| layers.py:677-679 | `f"JD asks for a {a} degree; resume shows {s}. This is normally an application-form question — answer it honestly; your score is unaffected."` | "The job asks for a {a} degree and your resume shows a {s}. Employers usually ask this on the application form. Answer honestly. It doesn't change your ATS score." | |
| layers.py:691 | "Some experience dates failed to parse (use 'Jul 2022' format)" | "Some job dates can't be read. Write them like Jul 2022." | `test_gap_analysis.py:330` |
| layers.py:695 | "Contact block missing name, email, or phone" | "Your contact details are missing a name, email or phone." | `test_gap_analysis.py:310, 332, 344` |
| layers.py:700, :723 | "Section missing or empty: {section}", "{pct} of skills-section items have no supporting evidence in any entry" | **keep** (Kept 6: `gap_analysis._format_flag_actionable` routes on these prefixes). Reword only after the flags carry codes: then "Your resume has no {Summary} section." and "{pct} of your skills aren't shown in any job or project." | `test_gap_analysis.py:333-353`, `test_extra_sections_ats_evidence.py:202` |
| engine.py:13 | "I could not read this posting — treat this score as unreliable" | "Couldn't read enough of this job description. Treat this ATS score as a rough guide." | `mcp_server/tests/test_workflow.py:49-52` (fixtures) |

**`ats_score.py`, `ats/jd_normalizer.py`, `routers/tailoring_sessions.py`** (the Score tab's 422 notice,
`ats-compare-panel.tsx:158`, MCP `score_ats`, `compare_ats`, Companion's score note).

| line | current | new | tests |
|---|---|---|---|
| ats_score.py:29 | `f"Job has no extracted_json: {job_id}"` | "This job's description hasn't been read yet. Choose Refresh details on the job page." | |
| ats_score.py:45 | "Application has no customized_json to score (materialize it first)" | "This application has no tailored resume yet. Tailor it first." | |
| ats_score.py:179 | "No base resumes could be scored for this job" | "None of your base resumes could be scored against this job." | |
| ats_score.py:284-287 | "Scores were produced by different engine/config versions; re-run scoring for both phases before comparing" | "These ATS scores came from different versions of the scorer. Score both again to compare them." | |
| jd_normalizer.py:45 | "Job has no extracted skills; ATS scoring needs extracted_json.skills" | "No skills were found in this job's description. Check the description, then choose Refresh details." | `test_jd_normalizer.py:42` (`match=`) |
| routers/tailoring_sessions.py:195-197 | `f"tailoring succeeded; scores not comparable: {exc} — re-run scoring and GET /api/applications/{id}/ats-compare"` | "Your resume is tailored, but the before and after ATS scores couldn't be compared. Score both again from the job page." | `test_tailoring_sessions_router.py:2462`; the old text leaked an API path into a toast (`page.tsx:355`); `server.py:1519` tells the agent to relay it, which still reads right |

**`tailoring_session.py`, `quick_tailor.py`** (gap page, Score tab toasts, MCP tailoring tools, Companion's
Quick tailor note).

| line | current | new | tests |
|---|---|---|---|
| :69, :71, :75, :77 | stale reasons "the base resume no longer exists" / "the base resume was edited" / "the job no longer exists" / "the job description was re-extracted" | "the base resume was deleted" / keep / "the job was deleted" / "the job description was read again" | composed into D3's banner |
| :87-88 | `f"This gap analysis is stale — {reason} since it was created. Start a new analysis (it will supersede this one)."` | "This gap analysis is out of date because {reason}. Start a new gap analysis. It replaces this one." | |
| :171-174 | "Health report is stale (ran against v{a}; resume is now v{b}) — re-analyze." | "Your health report is out of date. Choose Check again on the health report before you tailor." | `test_tailoring_sessions_router.py:489` |
| :194-196 | "Base resume has failing structural gate(s): " + ids + ". Fix or waive them in the health check before tailoring." | "Your base resume has a must-fix problem: {problem labels}. Fix it or mark it as OK in the health report, then start the gap analysis." (labels, not `S1`; add "gate ids are in get_health_report `gates[].id`" to the `waive_health_gate` docstring so agents keep the id path) | `test_tailoring_sessions_router.py:440, 651`; `test_quick_tailor.py:497` |
| :200-201 | `f"Base resume health is {s} ({g}); tailoring a weak base produces weak output."` | "Your base resume's health score is {s} ({g}). Tailoring a weak resume gives weak results." | `test_quick_tailor.py:446` |
| :326, :814, :1369 | `f"Tailoring session {id} is not open (status={status!r})"` | "This gap analysis is closed. Start a new one." | |
| :1222-1224 | "Placement target(s) no longer point at a valid destination on the base resume (gap_ids: [...]). … — start a new analysis." | "Some answers point to parts of your base resume that changed. Start a new gap analysis." | |
| :1022-1023 | "the answer is under {N} characters — too short to keep as evidence" | "the answer is under {N} characters, too short to save" | `test_writeback_skip_visibility.py:107` (still holds) |
| :1033, :1041 | "the answer isn't attached to an experience or project entry" | "the answer isn't placed on a job or project" | `test_writeback_skip_visibility.py:118` |
| :1052 | "the target entry has no title to match a Career KB entity" | "that job or project has no title to match in your career history" | |
| :1065 | `f"no Career KB entity titled “{t}”"` | `f"your career history has no item called “{t}”"` | `:136` (still holds) |
| :1075 | `f"an equivalent point already exists on “{t}”"` | `f"“{t}” already has a bullet like this"` | `:179` (still holds) |
| :1416 | "No actionable resolutions to tailor" | **keep** (Kept 2: the gap page compares it) | 4 tests |
| quick_tailor.py:281-284 | "An in-progress tailoring session with saved resolutions exists for this job and base resume. Finish or close it in the web app, or run quick tailor after discarding it." | "A gap analysis for this job and resume is in progress. Finish or close it in Maestro CS first, then use Quick tailor." | `test_quick_tailor.py:328` |

**`explore_overview.py`** (job market signal cards only; not MCP).

| line | current | new | tests |
|---|---|---|---|
| :58 | `f"{p}% of JDs explicitly accept OPT"` | "{p}% of jobs say they accept OPT" | |
| :65-66 | `f"Top location: {k} ({n})"` / "More JDs name this location than any other." | "Most common location: {k} ({n} jobs)" / "More jobs list this location than any other." | |
| :73-74 | `f"Top required skill: {s} ({p}% of JDs)"` / `f"Required in {n} of {t} JDs, more than any other skill."` | "Most required skill: {s} ({p}% of jobs)" / "Required in {n} of {t} jobs, more than any other skill." | `test_explore_router.py:484` |
| :87 | `f"Best-paying track: {label}"` | "Best-paying role: {label}" | `test_explore_router.py:459, 466-467, 473-474` |
| :90, :97, :109 | "…from {n} JDs that list pay." / `f"{p}% of JDs state no salary"` / `f"Only {r} of {t} JDs are remote."` | "…from {n} jobs that list pay." / "{p}% of jobs don't list pay" / "Only {r} of {t} jobs are remote." | `:430` unchanged |

**`pdf_render.py`** (`render_note` toasts through `lib/render-note.ts:24`; MCP `render_pdf` and the base
resume tools). `render_error` is stored; the frontend no longer prints it on a card (D4.1).

| line | current | new | tests |
|---|---|---|---|
| :555-558 | "This template needs TeX, which is not installed on this machine. Install TeX or pick a Typst template." | "This template needs a tool that isn't installed. Pick another template." | `test_render_fallback.py:177, 700, 705, 736, 739, 794, 799, 839` |
| :561-565 | "TeX is not installed on this machine; rendered with {sub} instead of {req}." | "Your {req} template can't be used on this computer, so this PDF uses {sub}." | `test_render_fallback.py:129, 223, 251, 291, 303, 336, 403, 406` |
| :283-289, :485-491 | "This resume has custom section(s) [{keys}] but the selected template cannot render custom sections, so they would be silently dropped. Choose a template that supports custom sections, or disable those sections before rendering." | "This template can't show your other sections ({titles}). Pick a template that can, or hide those sections." | `test_render_fallback.py:338`; the "custom section" asserts in the base resumes and applications router tests change to "other sections" |
| :371-376 | template-authoring errors ("pdflatex is not installed…") | keep (Kept 11: the template editor, where engine names are expected) | `test_render_fallback.py:71, 77, 89` |

**Document summaries** (`documents-panel.tsx:162`, the timeline; MCP `kb_get_entity`; stored).

| file:line | current | new | tests |
|---|---|---|---|
| kb_ingest.py:58 | "no extractable text" | "No text could be read from this file." | |
| kb_ingest.py:75, :79 | `f"mint failed: {exc}"`, "mint returned non-object" | "Couldn't draft bullets from this file. Try again." | |
| kb_ingest.py:103, :324 | `f"{m} points minted, {s} skipped as duplicates"` | "{m} draft bullet" / "bullets" " added, {s} skipped as duplicates" | `test_kb_doc_ingest.py:116` |
| routers/career_kb.py:537 | stores raw `str(exc)` | the `:58` sentence | |

### D9.5 Career history timeline and version summaries

| file:line | current | new | tests |
|---|---|---|---|
| career_kb.py:437 | `f"{text} — added by {origin_detail or origin}"` ("— added by mcp") | `f"Added by {who}: {text}"`, with `who` the client label (A9's mapper: "Claude", "Codex"), else "a connected agent" for `mcp`, "the Assistant" for `chat` | `test_kb_write_origin.py:107-108` (still holds); appendix A found-by-reading 5 |
| career_kb.py:457 | `f"Entity created by {origin_detail or origin}"` / "Entity created" | "Item created by {who}" / "Item created" | `test_kb_write_origin.py:106, 124` |
| career_kb.py:463 | "Points minted" | "Draft bullets added" | |
| career_kb.py:480 | `f"→ {log.resume_key}"` (a slug or an application UUID) | "Added to {resume display name}" | slug |
| routers/applications.py:118 | `f"Rebuilt from base resume {slug}"` | "Rebuilt from {display name}" | slug |
| routers/applications.py:127 | `f"Created from base resume {slug}"` | "Created from {display name}" | |
| routers/applications.py:473 | `f"Materialized from base resume {slug}"` | "Copied from {display name}" | jargon, slug |
| routers/base_resumes.py:679 | `f"Ported project from {slug}"` | "Copied a project from {display name}" | port |
| routers/base_resumes.py:752 | `f"Duplicated from {slug}"` | "Duplicated from {display name}" | slug |
| services/career_kb.py:1096 | `f"Ported {n} item(s) from Career KB"` | "Added 1 item" / "{n} items" " from career history" | port, KB |
| services/kb_adapt.py:410 | `f"Adapted {n} point(s) from Career KB"` | "Added 1 reworded bullet" / "{n} reworded bullets" " from career history" | `test_kb_adapt.py:312` (`"Adapted 3 point(s)"` becomes `"3 reworded bullets"`) |
| services/resume_versions.py:117 | "Restored version {n}" | keep | |

These summaries are stored per version and also returned by MCP `list_resume_versions`; old rows keep the
old words (history is not rewritten).

### D9.6 Errors a web or Companion user can reach

**Form of a server sentence.** The web wraps it: `couldnt(what, err)` (D1.3) prints "Couldn't <what>." and
then the server's sentence when it is plain. So a server `detail` states the cause and the next step as one
or two plain sentences with a final stop, and never starts with its own "Couldn't …" (D9.4 follows the same
form). An agent reading the same text over MCP gets the same cause and step.

| file:line | current | new | tests |
|---|---|---|---|
| persona.py:43 | "Career KB is empty — import a resume first, then draft." | "Your career history is empty. Import a resume first." | |
| base_from_kb_plan.py:83 | "Career KB is empty — import a resume first." | "Your career history is empty. Import a resume first." | |
| llm.py:92-97 | "No OpenAI API key configured. Add one under Settings → Models in the web app, or set OPENAI_API_KEY in .env and restart the backend. To use a local model instead, set an OpenAI-compatible endpoint under Settings → Models." | "No API key is set. Add one in Settings › AI & models › API keys. To use a model on your computer instead, add its address in Settings › AI & models › Custom AI server." (the `.env` line stays in the log and docs, not the UI) | **delta on C9** ("›", the card's D6 name); `test_llm.py:210-211` (`"Settings" in message`) still holds |
| llm.py:120, :198 | "GEMINI_API_KEY is required for Gemini models" | "No Gemini API key is set. Add one in Settings › AI & models." | raw env name |
| llm.py:232, :304 | `f"Gemini API request failed: {code} {body}"` / `f"OpenAI API request failed: {exc}"` (a 502 via `main.py:167`, and the Assistant's error event, `chat_agent.py:269`) | "The AI model didn't answer ({short provider reason}). Try again, or check your key in Settings › AI & models." | fixtures only |
| llm.py:455-456 | "No Gemini API key configured. Add one under Settings → Models." | "No Gemini API key is set. Add one in Settings › AI & models." | **delta on C9** |
| llm_capabilities.py:238-243 | `f"{model!r} does not support {capability}: {reason}. Choose a {capability}-capable model in Settings — the fast, smart and chat models are configured separately, so a local model can keep doing the rest."` | "{model} can't {write text \| return structured answers \| use tools} ({reason}). Pick a different model in Settings › AI & models. The Fast, Smart and Assistant models are set separately." | **delta on C9**; raw key, em dash; `test_llm_capabilities.py:99-102` still holds |
| model_settings.py:373 | "chat needs a model that passes the streaming tool-call test — run Test" | "The Assistant model has to pass the tool test. Press Test next to it first." | `test_settings_router.py:400`, `test_model_catalog.py:83` |
| model_settings.py:161-163 | the URL example error | "Enter a full address that starts with http:// or https://." | |
| model_settings.py:317 | "Model {id} is already in the catalog" | "That model is already in your list." | `test_model_catalog.py:39` |
| model_settings.py:342-344 | "Model {id} is in use by Fast, Smart, or Chat — change that role first" | "{id} is your Fast, Smart or Assistant model. Pick another model for that first." | em dash, Chat |
| routers/jobs.py:579-580 | "Job has no raw JD text to re-extract from (captured via pre-extracted ingest); re-ingest it instead." | "This job was saved without its original text, so it can't be read again. Add the job again from its job page." | JD, jargon |
| routers/qa.py:177, :180 | "Only cover_letter entries can be rendered" / "Entry has no text to render" | "Only cover letters can be made into a PDF." / "This cover letter is empty." | render |
| routers/resume_lint.py:174 (and applications.py:235, :274) | "Application has no tailored resume yet — materialize it first" | "This application has no tailored resume yet. Tailor it first." | jargon, em dash |
| routers/resume_lint.py:199 | "A waiver reason is required" | "Add a reason before you mark this as OK." | waive |
| routers/career_kb.py:274 | "This entity was merged by another request; refresh and retry" | "This item was just merged elsewhere. Refresh the page and try again." | entity |
| routers/career_kb.py:433 | "Target entity not found" | "That item no longer exists." | |
| routers/career_kb.py:495-496 | `f"Couldn't read the document ({e}). Create the entity manually and attach the file from its page."` | "Couldn't read this file. Create the item yourself, then attach the file on its page." | `test_kb_doc_ingest.py:123` |
| routers/proposals.py:102 | "company is blocklisted" | "This company is on your Companies to skip list in Settings › Connected agents." | |
| routers/proposals.py:149 | "job was declined — delete the rejected proposal to re-propose" | "You skipped this job before. Delete the skipped proposal in the Agent inbox to queue it again." | em dash, raw status words |
| routers/proposals.py:298 | "cannot delete a submitted proposal — it is the submission audit trail" | "This proposal was submitted, so its record is kept as proof." | |
| services/proposals.py:94 | `f"cannot go {status} -> {new}"` | "This proposal is already {status label} and can't be changed." | raw statuses (the bulk toast, D2.7) |
| routers/templates.py:107 | "engine is immutable after creation — create a new template instead" | "A template's type can't change. Create a new template instead." | |
| routers/base_resumes.py:229, :730 | "A base resume with this slug was deleted; choose a different slug to preserve history" | "A deleted resume used this name. Pick a different name." | slug |
| routers/base_resumes.py:231, :732 | "Base resume already exists" / "Target slug already exists" | "A base resume with this name already exists. Pick a different name." | |
| routers/base_resumes.py:407-411 | (no approved points in the picked items) | "None of the items you picked has approved bullets." | point |
| services/career_kb.py:592, :600-602, :607-609, :613 | "Cannot merge an entity into itself", "Cannot merge a {kind} entity into a {kind} entity; …", "Cannot merge extra section {key!r} into {key!r}; …", "Target entity is archived; unarchive it first, then merge" | "Pick a different item to merge with.", "You can only merge items of the same type.", "Both items must be in the same section.", "The item you picked is archived. Restore it first." | entity, raw keys |
| services/career_kb.py:949-951; kb_adapt.py:61-67, :82, :298-300, :327-329, :336-337, :356-357 | the send-to-resume errors ("certification entities port verbatim…", "no approved points to adapt", "…re-run adapt", raw kind plus "Career KB porting") | one pattern: "{Reason in plain words}. Try again." using item and bullet (for example "This item has no approved bullets to reword.") | entity, port, point |
| chat.py:133 | `f"Card already resolved as {existing!r}"` | "This change was already {applied \| discarded}." | raw value |
| chat.py:152; attachment_extract.py:153-155, :160 | "Attachment exceeds 10 MB limit"; "Unsupported attachment type: {f!r} ({mime}). Supported: .pdf, …"; "…" | "This file is over 10 MB."; "Use a PDF, Word, text or image file."; "No text could be read in {f}." | |
| chat_agent.py:261 | "(Stopped: too many consecutive tool calls in one turn.)" (persisted in the transcript) | "I stopped because this took too many steps. Try asking for one thing at a time." | jargon |
| base_resume_instruct.py:113 | "The model could not produce edits that apply to this resume: {correction}" | "That change couldn't be made. Try rewording it." | |
| template_registry.py:743, :756 | "Only a 'ready' template can become the default", "Cannot delete the default template" | "Only a template that passed its check can be the default.", "This is your default template. Make another one the default first." | |
| script_guard.py:83-87 | the unsupported-script message | "This {resume \| job description} uses {script} script. Maestro CS supports English in Latin script (accented Latin letters, such as in Zürich, work)." | keep "accented Latin" (`test_script_guard.py:23`) |
| routers/career_kb.py:822, kb_import.py:240 | raw `str(exc)` in the import report | plain reasons ("Couldn't read this file.", "This file type isn't supported.") | |

**Validators kept precise on purpose** (only API and MCP callers or the model reach them; the web maps a
422 array to "Some details weren't accepted. Check them and try again.", D1.3): `placement_targets.py` and
`resume_edit.py` op errors; `chat_tools.py` ToolErrors (they go to the model); `routers/ats.py:19`,
`autofill.py:247`, `career_kb.py:681/688`, `qa.py:39/43`, `proposals.py:399/432/437/441`,
`resume_versions.py:125`; `base_resumes.py:82, 108-121, 139, 393`; `resume_lint.py:197` (gate id) and the
`:251/:254/:258` 422s (the web maps those at `finding-cards.tsx:767` and `batch-ask-dialog.tsx:243`); the
`schemas/career_kb.py` validators; `kb_ingest` LLM-shape errors; `ats/config.py`; db and config errors.

### D9.7 Kept on purpose (machine-read or agent-facing)

1. "content changed since analysis…" (`routers/resume_lint.py:80`, `services/resume_edit.py:56`): the
   frontend matches its prefix (`health-report.ts:28, 53`); about 8 tests pin it. Only the frontend hint
   changes (D4.5).
2. "No actionable resolutions to tailor" (`tailoring_session.py:1416`): the gap page compares it (D3).
3. "PDF not found" (applications, base resumes, qa routers): `mcp_server/client.py:816` compares it.
4. The prefix "What number measures this" (`resume_lint.py:69`): `METRIC_ASK_NEEDLE`.
5. "this bullet" in `LADDER_COPY` `how`: the `hoistBlurb` regex (`health-report.ts:162`) rewrites it.
6. The format-flag prefixes "Section missing or empty:" and "…skills-section items have no supporting
   evidence": `gap_analysis._format_flag_actionable` routes on them.
7. "proposal already linked to an application" (`services/proposals.py:207`): `routers/proposals.py:355`
   checks "already linked".
8. Finding ids (D9.1).
9. Enum values and identifiers: tool names, gate ids, `tier`, category, rule, kind, result and reason codes,
   `ingest_status`, origins, status values. The display maps live in the frontend.
10. Agent-only text: gate `why`, the job-search brief warnings (D9.3 rewrites them anyway, keeping their key
    words), "Unknown gate id", the chat ToolErrors.
11. Template-authoring errors (`pdf_render.py:371-376`): the template editor is the one place engine names
    belong.

### D9.8 Pins (L8)

| test | old | new |
|---|---|---|
| `test_resume_dates.py:120` | `== "Acme — Analyst: end date unparseable"` | `== "Analyst · Acme: can't read the end date"` |
| `test_health_gates.py:52` | `== "No unparseable experience dates found."` | `== "All your job dates are readable."` |
| `test_tailoring_sessions_router.py:440, :651`; `test_quick_tailor.py:497` | `"S1" in detail` | `"PDF text is readable" in detail` (fixtures that store the old label read `"Parse fidelity"`; assert on the fixture's own label) |
| `test_tailoring_sessions_router.py:489` | `"Health report is stale (ran against v…"` | `"health report is out of date" in …` |
| `test_tailoring_sessions_router.py:2462` | `"different engine/config versions" in compare_error` | `"couldn't be compared" in compare_error` |
| `test_quick_tailor.py:446` | the exact "Base resume health is 42 (F); tailoring a weak base…" | "Your base resume's health score is 42 (F). Tailoring a weak resume gives weak results." |
| `test_quick_tailor.py:328` | the in-progress sentence | the new sentence |
| `ats/test_gap_analysis.py:118, :136, :143` | the summary, coverage title and coverage detail | the new copy |
| `ats/test_jd_normalizer.py:42` | `match="no extracted skills"` | `match="No skills were found"` |
| `test_explore_router.py:459, :466-467, :473-474, :484` | "Best-paying track:", "Top required skill: sql (100% of JDs)" | "Best-paying role:", "Most required skill: sql (100% of jobs)" |
| `test_render_fallback.py` (the 16 lines listed above), `:338` | "TeX is not installed", "needs TeX", "cannot render custom sections" | "can't be used on this computer", "needs a tool", "can't show your other sections" |
| `test_kb_doc_ingest.py:116, :123` | "1 points minted, 1 skipped", "Couldn't read the document" | "1 draft bullet added, 1 skipped", "Couldn't read this file" |
| `test_kb_write_origin.py:106, :124` | "Entity created by ChatGPT", "Entity created" | "Item created by ChatGPT", "Item created" |
| `test_writeback_skip_visibility.py:118` | "experience or project entry" | "job or project" |
| `test_settings_router.py:400`; `test_model_catalog.py:83` | "streaming tool-call test" | "tool test" |
| `test_model_catalog.py:39` | "already in the catalog" | "already in your list" |
| `test_kb_adapt.py:312` | `"Adapted 3 point(s)" in versions[0].summary` | `"3 reworded bullets" in versions[0].summary` |
| base resumes and applications router tests asserting "custom section" in the PDF error | "custom section" | "other sections" |
| new, `test_resume_lint.py` | none | `test_reworded_findings_keep_their_ids` (D9.1) |
| new, `test_knockout.py` | none | `test_knockout_points_to_profile_autofill`: every message that names a place says "Profile › Autofill"; none says "in Settings" |
| `frontend/lib/health-report.test.ts:81-95, 119, 175, 255-261, 318-334, 344` | fixtures copying old backend strings | optional refresh; they still pass |

Unchanged and still passing: `test_llm.py:210-211`, `test_llm_capabilities.py:99-102`,
`test_job_search_brief.py:161, 212, 236, 338`, `test_script_guard.py:23`.

### D9.9 Checks (L8)

1. `pytest backend -q` (the SQLite test DB per SYSTEM.md §9); `pytest backend/mcp_server -q`.
2. MCP spot check: through a connected client, call `get_job` on a job with a sponsorship knock-out: the
   message reads "…Answer the sponsorship questions in Profile › Autofill." `tailor_session` on a stale
   analysis relays the new compare sentence.
3. Web: open a health report computed before this lane: old ask answers still attach to their findings
   (D9.1). Click Check again: the new words appear and the answers are still there.
4. Web: a job whose description was never read (`extracted_json` missing): Score shows "This job's
   description hasn't been read yet. Choose Refresh details on the job page."

---

## D10. Real bugs the audits found in copy (index)

Each is fixed by the row named, pinned by the test named. **[behaviour]** marks a change beyond words.

| # | Bug | Fix (row) | Pin |
|---|---|---|---|
| D10.1 | Profile › Autofill: toggling "tick agreement boxes" shows "EEO standing consent enabled/turned off", because both switches share one mutation whose toast reads only `enabled` (`autofill-section.tsx:567-570`) | each switch toasts its own words (D6.4) **[behaviour]** | `test_frontend_error_words.py::test_each_consent_switch_announces_itself` |
| D10.2 | The custom server hint says "OpenRouter … and nothing leaves this machine", but OpenRouter is remote (`llm-endpoint.tsx:77`) | a hint naming only local servers (D6.1) | `test_frontend_plain_words.py::test_the_custom_server_hint_never_promises_local_only` |
| D10.3 | Analytics labels the top 30% of skills "Mandatory"; the cut is by frequency (`app/analytics/page.tsx:194`, `top-skills-chart.tsx:129`) | "Skills ranked by how many jobs ask for them.", "Most asked for" (D2.9) | `test_frontend_plain_words.py::test_analytics_never_calls_the_top_skills_mandatory` |
| D10.4 | `ENUM_LABELS` keys `on_site`, but the stored value is `onsite` (`extract_jd.txt:10`, `job_preferences.py:80`), so every on-site job reads "Onsite" (`job-extracted-fields.tsx:108-112`) | key `onsite`, plus the work-authorization and OPT labels (D2.2) | `test_frontend_plain_words.py` (the `onsite` asserts in D2.10) |
| D10.5 | New base resume: "Left blank on purpose" under a summary the plan pre-filled (`new-base-resume-dialog.tsx:643`; `base_from_kb_plan.py:165`) | "Check this summary, or clear it." (D4.2) | `test_frontend_plain_words.py::test_new_base_summary_hint_matches_a_prefilled_field`: `"Left blank on purpose" not in` the dialog |
| D10.6 | Career history's "Add documents" opens the upload dialog on its Resumes tab (`app/career/page.tsx:76`) | button and dialog title "Add files" (D5, D7.2) | `test_frontend_plain_words.py::test_add_files_names_what_it_opens` |
| D10.7 | An item with no organization and no dates reads "Independent", a claim the user never made (`entity-card.tsx:82`) | no second line (D5) | `test_frontend_plain_words.py::test_an_item_without_org_or_dates_claims_nothing` |
| D10.8 | Plural bugs: "1 base resumes" (`setup-steps.ts:113`), "1 points", "1 drafts", "1 docs" (`entity-card.tsx:127-131`), "1 drafts excluded" (`kb-import-drawer.tsx:336`), "3 Note", "1 Gate" (`finding-cards.tsx:316`), "2 gate · 1 note" (`health-badges.tsx:31`), "Bullets 2 of 5", "Move bullets 2 up", "Delete bullets 2" (`bullet-list.tsx:31-63`) | each count agrees with its noun (D4.3, D4.5, D5, D7.2) | `test_a_bullet_label_is_singular_in_its_slot`, `test_item_counts_agree_with_their_nouns`, `test_setup_counts_agree_with_their_nouns` |
| D10.9 | The empty studio preview points at "More resume actions (⋯)", the screen-reader name sighted users never see (`lib/studio.ts:41`) | "No PDF yet. Choose Create PDF in the ⋯ menu." (D4.3) | `test_frontend_studio.py:195` (new assert) and `studio.test.ts:55` |
| D10.10 | "This can't be undone" where Version history restores: the extra-section delete (`extra-sections-editor.tsx:279`) and Rebuild from base (`tailored-resume-studio.tsx:898`, which records a version through `application_writes.stage_resume_update`) | say where to restore it (D4.3, D4.4) | `test_frontend_plain_words.py::test_undo_claims_match_version_history` |
| D10.11 | The Agent inbox Role filter prints raw keys (`proposals-section.tsx:439, 446`); `test_no_role_key_reaches_the_screen` misses it | appendix A3 (no change here) | A's pins |
| D10.12 | The Assistant's working chips print raw tool names (`chat-page.tsx:671`) | `TOOL_PHRASES`, fallback "Working…" (D7.3) | `test_frontend_plain_words.py::test_the_assistant_names_what_it_is_doing` |
| D10.13 | Deleting a chat has no confirm and no undo (`chat-page.tsx:823`) | a destructive confirm (D7.3) **[behaviour]** | `test_frontend_plain_words.py::test_deleting_a_chat_asks_first` |
| D10.14 | Rewording a health finding's `issue` would drop the user's saved number answers (`resume_lint._fid` hashes the text) | `id_key` keeps ids stable (D9.1) **[behaviour]** | `test_resume_lint.py::test_reworded_findings_keep_their_ids` |
| D10.15 | A tailor with incomparable scores toasts a raw API path ("…GET /api/applications/{id}/ats-compare") (`routers/tailoring_sessions.py:195-197`) | a plain sentence (D9.4) | `test_tailoring_sessions_router.py:2462` |
| D10.16 | A base resume card's tooltip prints the raw PDF engine log (`base-resume-thumbnail.tsx:44`), and a template card prints `last_error` (`template-gallery.tsx:157-159`) | plain words; the log stays in the editor (D4.1, D4.7) | covered by the vocabulary ratchet (render) |
| D10.17 | "Decline all" fills only the unanswered diversity questions (`autofill-section.tsx:729`, `:530-545`) | "Decline the rest" (D6.4) | none needed (copy) |
| D10.18 | The Prompts and Persona descriptions promise "outreach", which has no prompt (`prompts-section.tsx:54`, `persona-section.tsx:48`) | accurate lists (D6.1, D6.3) | covered by review |
| D10.19 | The Assistant's capture card links `/career#inbox` while the upload dialog links `/career#kb-inbox` (`kb-capture-card.tsx:19`) | one anchor, `#kb-inbox` (D7.4) | none needed |
| D10.20 | Knock-out and job-brief messages send the user to Settings for answers that live on Profile › Autofill (`knockout.py:63, 81, 125`; `job_search_brief.py:72-81`) | C9, with D9.3's deltas | `test_knockout.py::test_knockout_points_to_profile_autofill` |

---

## D11. Docs (lane L9, after L1–L8)

**User docs** (the words the screens now use; appendix A10 and C9 already change the Agent inbox and
"Settings → Models" lines, with "›" per D9):
- `README.md:74, :265, :275, :303, :600`: "Career KB" → "Career history"; "points" (stored lines) →
  "bullets"; `:303` "New base resume → From Career KB" → "New base resume › From career history";
  `:307` (a screenshot comment) "Import from Career KB" → "Add from career history"; `:364` "**Chat** (the
  in-app assistant)" → "**Assistant** (the in-app Assistant)" in the three model roles; `:399` quotes a
  backend string, update it to D9's words.
- `docs/GETTING_STARTED.md:21, :128, :131, :142, :151-152`: the same renames; `:136` "Click **New
  application**" → "Click **Add job**"; "Base Resumes → New → From Career KB" → "Base resumes › New base
  resume › From career history".
- `extension/README.md`, `extension/INTERNALS.md` (C9 lines): "Profile → Autofill" → "Profile › Autofill".

**`UBIQUITOUS_LANGUAGE.md`** lists "item" and "bullet" as aliases to avoid (for KB Entity and KB Point) and
names the store "Career KB". Those are the code's domain terms and stay; add a column "On screen" (Career
history, item, bullet, Add to a resume, Must fix, Mark as OK, Check template, Other sections, ATS score) so
the next agent does not "fix" the UI back to the code words.

**Queued for the SYSTEM.md sweep (it is at its cap):**
- §5 step 7 (`:202-206`): "**Generate PDF** renders … (Regenerate refreshes it)" → "**Create PDF** makes …
  (Update PDF refreshes it)".
- §5 step 9 (`:211-214`): "a `Sync to KB (N)` toolbar pill … its **Sync now**" → "an `Add to career history
  (N)` toolbar pill … its **Add now**".
- §8 index line: add "canonical terms and the vocabulary ratchet (`test_frontend_vocabulary.py`)".
- §12, a new dated entry (≤3 lines): "2026-09-23: rewording a health `issue` silently orphans saved ask
  answers → `_fid` hashes the text → pass `id_key` (D9.1)."

---

## File ownership

**New files:** `frontend/lib/error-text.ts`, `frontend/lib/error-text.test.ts`,
`backend/tests/test_frontend_vocabulary.py`, `backend/tests/test_frontend_error_words.py` (all L0).

**Shared test files, one block or function per lane:** `test_frontend_vocabulary.py` (`_PENDING_Lx`),
`test_frontend_error_words.py` (`_PENDING_Lx`), `test_frontend_placeholders.py` (`_PENDING_EXAMPLES_Lx` and
the per-file functions named in each group), `test_frontend_plain_words.py` and
`test_frontend_query_error_states.py` (each lane appends its own functions or edits its own rows).

| Lane | Files it owns |
|---|---|
| L0 | `components/ui/label.tsx`; `lib/api.ts` (message strings only); `lib/error-text.ts` (+ test); `components/load-error-state.tsx`; `docs/frontend-conventions.md` (D1.1); the new test files; `test_frontend_placeholders.py` (D1.4) |
| L1 | `app/applications/page.tsx`, `app/applications/[id]/page.tsx`, `app/jobs/[id]/page.tsx`, `app/new/page.tsx`, `app/referrals/page.tsx`, `app/analytics/page.tsx`; `components/{status-chip,job-extracted-fields,job-knockout-card,job-tracking-url-field,job-extraction-summary,ats-score-panel,ats-compare-panel,application-panel,qa-tab}.tsx`; `components/proposals/*`; `components/analytics/*`; `components/charts/*`; `components/explore/*`; `lib/format-date.ts`; `test_frontend_referrals.py`, `test_frontend_qa_tab.py`, `test_frontend_analytics.py`, `test_frontend_first_run.py` |
| L2 | `app/jobs/[id]/tailor/**`; `components/gap-analysis/*`; `test_frontend_gap_autosave.py` |
| L3a | `app/base-resumes/**`; `app/applications/[id]/resume/**`; `components/base-resumes/*`; `components/resume-editor/*`; `components/role-category-picker.tsx`; `lib/{studio,formatting,extra-sections,resume-schema,describe-edit,render-note}.ts` (+ their `.test.ts`); `test_frontend_studio.py`, `test_frontend_focus.py` (the Apply JSON row) |
| L3b | `components/resume-health/*`; `components/attention-zone.tsx`; `lib/health-report.ts` (+ test); `components/resume-versions/*`; `app/templates/**`; `components/templates/*`; `test_frontend_health_report.py`, `test_frontend_color_roles.py` (`_AMBER_LABELS` only) |
| L4 | `app/career/**`; `components/career/*`; `components/kb-sync-pill.tsx`; `test_kb_sync_frontend.py`, `test_frontend_kb_editors.py` |
| L5 | `components/settings/*`; `app/settings/page.tsx` and `app/profile/page.tsx` (strings only) |
| L6 | `app/chat/page.tsx`, `app/error.tsx`, `app/global-error.tsx`, `app/not-found.tsx`; `components/chat/*`; `components/app-sidebar.tsx`, `components/sidebar-reveal-trigger.tsx`; `components/ui/{sidebar,confirm-dialog}.tsx`; `components/{guarded-link,version-banner}.tsx`; `components/setup/*`; `test_frontend_chat_layout.py`, `test_frontend_sidebar_nav.py` |
| L7 | `extension/panel/**`; `extension/shared/guided-run.js`; `backend/tests/test_extension_panel*.py`, `test_extension_guided_fill.py` |
| L8 | the backend files in D9 (`services/{resume_lint,health_gates,knockout,job_search_brief,gap_analysis,tailoring_session,quick_tailor,ats_score,explore_overview,pdf_render,kb_ingest,career_kb,kb_adapt,persona,base_from_kb_plan,llm,llm_capabilities,model_settings,proposals,chat_agent,attachment_extract,base_resume_instruct,template_registry,script_guard,kb_import}.py`, `services/ats/{layers,engine,jd_normalizer}.py`, `routers/{applications,base_resumes,career_kb,jobs,qa,resume_lint,proposals,templates,tailoring_sessions,chat}.py`) and their tests; `mcp_server/server.py` (one docstring line, D9.4) |
| L9 | `README.md`, `docs/GETTING_STARTED.md`, `extension/README.md`, `extension/INTERNALS.md`, `UBIQUITOUS_LANGUAGE.md`; the SYSTEM.md sweep queue |

**File-to-lane rule for the pending blocks:** `extension/**` → L7; `app/jobs/[id]/tailor/**` and
`components/gap-analysis/**` → L2; the L3a and L3b paths → L3; `app/career/**`, `components/career/**`,
`kb-sync-pill.tsx` → L4; `app/{settings,profile}/**`, `components/settings/**`, `components/role-picker.tsx`
→ L5; `app/{chat,error,global-error,not-found}`, `components/{chat,setup,ui}/**`, the sidebar, guard,
banner and confirm files → L6; `label.tsx`, `lib/api.ts`, `load-error-state.tsx` → L0; everything else → L1.

### Files also touched by appendices A–C (so every copy lane runs after them)

| File | Appendix and what it changes | This appendix |
|---|---|---|
| `components/app-sidebar.tsx` | A1, A4 (Agent inbox item, Needs-you count) | L6 renames three items and the button |
| `app/proposals/page.tsx`, `components/proposals/{proposals-section,proposal-agent-panel,triage-actions}.tsx`, deleted `funnel-strip.tsx` | A1, A2, A3, A5, A6, A7, A9 | L1: lanes, chips, reasons, queue verb, a few words |
| `components/analytics/agent-pipeline-card.tsx` | A2 (hook), A5 rows 31–32 | L1: "Found", "Applied" |
| `app/jobs/[id]/page.tsx` | A1, A5 rows 6–10, A9 | L1: tab name, refresh words, toasts, "Queue" |
| `app/applications/page.tsx` | A5 rows 15–18, A9; B6 (toolbar, sticky header), B10 (cap notice) | L1: header, empty state, column, confirms, toasts |
| `app/referrals/page.tsx` | B7 (`:325-327` sticky header) | L1: placeholders, labels, confirm |
| `components/source-toggle.tsx`, `components/career/points-list.tsx` | A5 rows 19–21 | L4: the other points-list words |
| `components/ats-score-panel.tsx`, `components/chat/{proposal-card,edit-proposal-card}.tsx`, `components/resume-editor/instruct-sheet.tsx` | A5 rows 33–39 | L1, L6, L3a: the other words |
| `components/analytics/autofill-coverage-card.tsx` | A5 rows 45–47 | L1: deltas on those rows |
| `components/settings/*` (all) | C6, C7, C8 (structure, Models split, rhythm), A5 rows 23–30, 40–44, A8 (Connected agents card) | L5: deltas on their words and the rest |
| `app/settings/page.tsx`, `app/profile/page.tsx` | C2 (tabs, subtitles) | L5: the Profile subtitle, "Setup guide" |
| `components/setup/setup-steps.ts`, `components/setup/getting-started-card.tsx`, `components/job-knockout-card.tsx`, `app/new/page.tsx` | C3 (deep links) | L6, L1: words |
| `components/ui/tabs.tsx` | C5 | none |
| `backend/app/services/{llm,llm_capabilities,knockout,job_search_brief}.py`, `backend/app/main.py`, `extension/panel/actions/fill.js` | C9 | L8, L7: deltas ("›", fuller rewrites) |
| `backend/app/services/career_kb.py` | A found-by-reading 5 (not scheduled by A) | L8 does it |
| `backend/tests/test_frontend_placeholders.py` | A3 ("e.g. 50"), C7 (KeyField regex) | L0 flips the rule; lanes rewrite their functions |
| `backend/tests/test_frontend_query_error_states.py` | A6 (proposals marker), C7 (`_SETTINGS_CARDS`) | L1, L2, L3, L4 rows |
| `backend/tests/test_frontend_agent_words.py` (new in A) | A5 | L1, L5 update four "present" strings |
| `docs/frontend-conventions.md` | A10, B11, C9 | L0 (D1.1 bullets) |
| `README.md`, `docs/GETTING_STARTED.md` | A10, C9 | L9 |

---

## Open questions (only real ones)

1. **The "Needs you" lane.** The owner's lane list is "To review · Queued · Applying · History", but the
   inbox also has a "Needs you" lane (`needs_decision`, `needs_human`) that appendix A4 counts in the
   sidebar. This appendix keeps it as a fifth lane. Merge it into To review instead?
2. **Gender options** (`autofill-section.tsx:148-167`: Male, Female, Decline) and **"restrictive
   covenant"** (`:204`): not changed this plan, per the owner. Real forms often offer more gender options,
   and "restrictive covenant" covers more than a non-compete.
3. **"Custom endpoint" and "Model catalog"** (appendix C7's card titles): this appendix renames them "Custom
   AI server" and "Available models" (the audit's words; "endpoint" and "catalog" are jargon). C pins only
   their ids, so either choice is cheap. Keep C's titles?
4. **"Q&A" as the job tab's name**: kept (widely understood). The audit offered "Answers".
5. **The chat delete confirm** (D10.13) is a behaviour change. An Undo toast instead of a confirm would
   also meet the need; the confirm is proposed because it matches every other delete in the app.
6. **The finding-id key (D9.1)**: keep ids stable with a legacy `id_key` (proposed, no data moves), or re-key
   `_fid` on `(type, location, rule)` and accept that saved number answers ask again once?
7. **Stored history keeps old words**: version summaries, timeline events and document summaries written
   before L8 keep "Ported …", "Materialized …", "points minted". Rewrite them with a one-off data migration,
   or let them age out (proposed)?
8. **Companion with or without "the"**: this appendix writes "Companion" as a bare proper name ("Let
   Companion fill these answers"); appendix A5 wrote "the Companion". One style should win; the ratchet
   does not check it.

## Findings dropped, with the reason (summary)

- Every audit row marked `ok` or "Keep", unless its text uses a banned glossary word (those rows are in the
  groups above).
- Part 3's renames the owner overruled: Persona → "Goals and strengths", Fast and Smart → "Reading" and
  "Writing", "match score", and "Career KB" kept with a gloss. Part 2's "point" for a resume line (the
  owner chose "bullet").
- Rows appendix A, B or C already rewrite with words the owner accepts (listed as "after A/B/C, no further
  change" in each group).
- Deliberate styles: uppercase tracked group headings (conventions), Title Case section headings written
  onto the PDF ("Additional Skills", the extra-section presets' titles), "OPT", "H-1B" and the visa names,
  the "AI/ML" and "UI/UX" role names, LaTeX and Typst inside the template editor.
- `resume-schema.ts` and `raw-json-toggle.tsx` path messages stay as they are inside the code view only
  (they are mapped to words everywhere else, D4.3).
- Named prompts in chip add-rows and search boxes ("Add certification…", "Add course…", "Add skill…",
  "Add skills…", "Search company or role…", "Search by title…", "Search roles, or type your own…"): the
  owner keeps them.
- Rows that use "bullet" for a resume line (`bullet-list.tsx:11` "Bullets", `demonstrate-skill-dialog.tsx:105`
  "Pick a bullet first", `:187` "{entry} · bullet {n}", `describe-edit.ts:139, 159-169`): the owner chose
  bullet, so part 2's "point" rows are dropped.
- Rows appendix C7 already rewrites to words the owner accepts: `models-section.tsx:112` "Models" (C keeps
  the title), `:113` (C's description), `:456-458` and `model-catalog-panel.tsx:203-205` (C's
  `showsModelId`, `providerLabel` and `sourceLabel`).
- Rows appendix A5 already rewrites: `auto-apply-section.tsx:40, :79`, `mcp-workflow-section.tsx:54, :55,
  :68`, `agent-pipeline-card.tsx:41`.
- Persona rows (`persona-section.tsx:49, :96, :133, :140`): the owner keeps "Persona", so they stay.
