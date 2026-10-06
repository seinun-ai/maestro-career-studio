# Automations Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in this session) to implement this plan task by task.

**Goal:** Add an in-app Automations page. A user copies a prompt from it into their own agent
app (Claude Desktop, Codex, any MCP agent). The agent asks when to run, then does that job
against Maestro: mail status, job hunt, referral pages, tailor run, apply session.

**Owner's goal, in their words (2026-10-04):** "If we make an exclusive section in our
application where we can click copy to copy a prompt that users can paste inside their agentic
subscription accounts and create those schedules or workflows, that would be simpler and
reachable." And: "the scheduled timings and the customizations, leave that to the user… Their
own agent will ask them for those time." End state across all four phases: "our application
should support a fully automated job application if that's user's wish, with appropriate
settings to enable or disable."

**Design:** `docs/plans/2026-10-04-automations-page-design.md`. Read it first; it is the
source of truth for scope.

**Architecture:**
- The skill files move into the backend package and become the single source of the prompt
  text.
- `GET /api/automations` parses them (YAML frontmatter, with app fields under `metadata:`) and
  returns cards plus per-agent-app wrappers.
- The Next.js page renders the cards. Copy puts `wrapper + body` on the clipboard.
- Nothing about the user is inserted into the copied text. There is no cadence picker and no
  scheduler in Maestro.

**Tech stack:** FastAPI + Pydantic + PyYAML (already a dependency); Next.js 16 App Router +
React 19 + react-query + sonner + the repo's shadcn/Base UI components; pytest with source-pin
tests for the frontend.

**How much freedom the executor has:**

| Area | Freedom | Rule |
|---|---|---|
| API shape, field names, card ids, file paths | **Fixed** | Tests and the design pin them. |
| New skill prompt wording | **High** | Keep the step order, the tool names and every guardrail line the tests pin. Match the style of `job-hunt/SKILL.md`: short, imperative, tools named in backticks. |
| UI details | **Moderate** | Spacing, icon and exact layout can vary within `docs/design-system/` and `docs/frontend-conventions.md`. The pinned strings in Task 7 are fixed. |
| A blocker the plan doesn't cover | **Stop and report** | Say why. Don't work around a failing test. If a step is wrong, propose the change. |

**Environment:** a worktree. Read SYSTEM.md first. Follow the memory recipe:
- **Backend suite:** run from `backend/` with
  `/opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`.
- **Single test:** `/opt/anaconda3/bin/python3 -m pytest tests/<file>::<test> -q`.
- **Frontend:** `npm ci` once in `frontend/`. The gates are `npx tsc --noEmit`, `npm run lint`
  and `npm run build`.

---

### Task 1: Move the skills into the backend package and add card metadata

**Files:**
- Move: `docs/skills/{job-hunt,apply-session,agent-apply-execution,customize-job-skills}/` → `backend/app/automations/skills/<same>/`
- Create: `backend/app/automations/__init__.py` (empty)
- Modify: frontmatter of the four moved `SKILL.md` files
- Modify: `docs/skills/README.md` (rewrite as index), `docs/entities/others.md:567`, `backend/app/automations/skills/customize-job-skills/SKILL.md:10`, `backend/tests/test_frontend_agent_inbox.py:260`

**Step 1: Move with history**

```bash
mkdir -p backend/app/automations/skills
for s in job-hunt apply-session agent-apply-execution customize-job-skills; do
  git mv docs/skills/$s backend/app/automations/skills/$s
done
touch backend/app/automations/__init__.py
```

**Step 2: Add metadata to the frontmatter.** Keep `name` and `description` exactly as they
are, and add a `metadata:` block.

`job-hunt/SKILL.md`:
```yaml
metadata:
  title: Job hunt
  summary: Finds recent postings that fit your brief, saves and scores them, and proposes the best.
  kind: scheduled
  needs: [maestro, web]
  never: Never applies, submits or triages for you.
```
`apply-session/SKILL.md` (`kind` here is the fallback; the service decides it at request time,
see Task 3):
```yaml
metadata:
  title: Apply session
  summary: Works your queued jobs in a browser and fills each application.
  kind: attended
  needs: [maestro, browser]
  never: Never submits without your yes.
  include: [agent-apply-execution]
```
`customize-job-skills/SKILL.md`:
```yaml
metadata:
  title: Make your own
  summary: Builds automations around you from what your agent knows and your data in Maestro.
  kind: custom
  needs: [maestro]
```
`agent-apply-execution/SKILL.md` gets **no** `metadata` block. It isn't a card; the Apply card
appends it through `include`.

**Step 3: Rewrite `docs/skills/README.md` as an index.** Keep the opening paragraph's intent.
Update the table links to `../../backend/app/automations/skills/<name>/SKILL.md`. Add rows for
`mail-status`, `referral-pages` and `tailor-run`; their files are created in Task 2. Add one
line: "The app shows these on the Automations page, with a Copy button for each." Keep the
"Use one as-is" and "Make them yours" paragraphs, with paths updated.

**Step 4: Fix the deep links.**
- `docs/entities/others.md:567` → `backend/app/automations/skills/agent-apply-execution/SKILL.md`.
- `customize-job-skills/SKILL.md:10` should say the skills live in
  `backend/app/automations/skills/`, indexed at `docs/skills/README.md`.
- `backend/tests/test_frontend_agent_inbox.py:260`: `docs/skills/README.md` still exists, so
  the assertion stays true. Only change it if it fails.
- `git grep -n "docs/skills/[a-z-]*/SKILL.md"` must return nothing outside CHANGELOG history.

**Step 5: Run the affected tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_agent_inbox.py -q` (from `backend/`)
Expected: PASS

**Step 6: Commit**

```bash
git add -A backend/app/automations docs/skills docs/entities/others.md
git commit -m "refactor(skills): move agent skills into the backend package as automation prompts"
```

---

### Task 2: Write the three new skills

**Files:**
- Create: `backend/app/automations/skills/mail-status/SKILL.md`
- Create: `backend/app/automations/skills/referral-pages/SKILL.md`
- Create: `backend/app/automations/skills/tailor-run/SKILL.md`

The wording is yours to improve; keep each skill under ~40 lines. **Every sentence marked
`[pinned]` must appear verbatim**, because Task 3's tests assert it.

**`mail-status/SKILL.md`:**
```markdown
---
name: mail-status
description: Use to keep Maestro CS application statuses in step with the user's job email — confirmations, interview invites, rejections and offers. Works attended or as a scheduled run. Reads mail only.
metadata:
  title: Mail status
  summary: Reads your job email and moves each application to applied, interviewing, rejected or offered.
  kind: scheduled
  needs: [maestro, email]
  never: Never sends or replies to email, and never copies email into Maestro.
---

# Mail status

Keep the user's tracker in step with their inbox. You need Maestro CS over MCP and
read access to the user's email.

Never send, reply to, archive, label or delete email. [pinned]

1. **Window.** Read job-related mail from the last 3 days. Repeat runs are safe:
   statuses only move forward and notes are not duplicated.
2. **Sort.** Keep application confirmations, interview invitations, assessments,
   rejections and offers. Ignore job alerts, newsletters and cold outreach.
3. **Match.** Page through `list_applications` and match on company and role;
   confirm with `get_application`. Change nothing unless exactly one application
   matches. [pinned]
4. **Move the status** with `update_application`:
   - confirmation → `applied`, only from `draft`
   - interview invite → `interviewing`
   - rejection → `rejected`
   - offer → `offered`
   - an assessment adds a note but keeps the status.
   Never set `accepted` or `withdrawn`; those are the user's. [pinned]
5. **Note.** `update_application` replaces the notes field, so read the current
   notes first and append one line, `YYYY-MM-DD email: <subject>`, unless a line
   already names that subject.
6. **Digest.** End with what changed, the emails you could not match, and the
   applications marked `applied` more than 21 days ago with no reply.
```

**`referral-pages/SKILL.md`:**
```markdown
---
name: referral-pages
description: Use to check the careers pages of the user's referrals in Maestro CS for new roles that fit their Job Search Brief, capture and score them, and propose the best. Works attended or as a scheduled run.
metadata:
  title: Referral pages
  summary: Checks your referrals' careers pages for new roles that fit you and proposes them.
  kind: scheduled
  needs: [maestro, web]
  never: Never contacts a referral and never applies.
---

# Referral pages

A referral beats a cold application, so these pages come first. You need Maestro CS
over MCP and web access.

Never contact a referral, and never apply or submit. [pinned]

1. **Brief.** Call `get_job_search_brief` first. It holds the role categories,
   location, work authorization, blocklist and the per-run proposal ceiling.
2. **Pages.** `list_referrals` and keep each `careers_url`. Skip referrals without one.
3. **Look.** Open each careers page and list its current postings. Keep the ones
   that fit the brief.
4. **Filter.** Drop postings `find_job_by_url` already knows, blocklisted
   companies, and postings without a full job description.
5. **Capture and score** each survivor: `store_extracted_jd` with
   `source="agent"`, then `score_ats`. Extract only what the posting states.
6. **Propose** the best up to the ceiling with `propose_application`, passing the
   matching `referral_id`. Give each a one-line match reason.
7. **Digest.** End with the pages you checked, what you proposed (title, company,
   score, link), and any page that failed to load.
```

**`tailor-run/SKILL.md`.** Before writing it, read the docstrings of `quick_tailor`,
`tailor_session` and `render_pdf` in `backend/mcp_server/server.py` (around lines 1463, 1592
and 1034). Use their real argument names. If calling `tailor_session` without `ops` does not
run the backend's own honesty-prompted pass, **stop and report**; don't invent a different
sequence.
```markdown
---
name: tailor-run
description: Use to prepare tailored resumes for the user's queued Maestro CS jobs using only facts already saved in the app. Works attended or as a scheduled run. Never applies.
metadata:
  title: Tailor run
  summary: Prepares a tailored resume for each queued job using only facts you've already given.
  kind: scheduled
  needs: [maestro]
  never: Never adds a fact you haven't given, and never applies.
---

# Tailor run

Get each queued job ready to apply, using only what the user has already told the app.
You need Maestro CS over MCP.

Use only facts already saved in the app. Never write resume text or claims of your own. [pinned]

1. **Queue.** `list_proposals(status="accepted")`, paging with `offset` until you
   have them all.
2. **Skip** a job whose application already has a current tailored resume and PDF.
3. **Quick tailor.** `quick_tailor(job_id, base_resume)` with the proposal's base.
   It fills gaps from the user's saved profile and never writes prose.
4. **Needs you.** If gaps remain that only the user can answer, stop on that job
   and list its open questions in the digest. Never answer them yourself. [pinned]
5. **Tailor.** Otherwise `tailor_session(tailoring_session_id=...)` with no `ops`,
   so the app's own checked pass writes the resume. Then `render_pdf` for the
   application.
6. **Digest.** End with the jobs you tailored (title, company, score change), the
   jobs that need the user, and any failure.
```

**Step 1: Create the three files** with the content above, adjusted per the tailor-run check.

**Step 2: Commit**

```bash
git add backend/app/automations/skills/{mail-status,referral-pages,tailor-run}
git commit -m "feat(automations): mail-status, referral-pages and tailor-run skills"
```

---

### Task 3: The automations service (parse, validate, wrap)

**Files:**
- Create: `backend/app/services/automations.py`
- Test: `backend/tests/test_automations_service.py`

**Step 1: Write the failing tests**

```python
"""The Automations catalog (docs/plans/2026-10-04-automations-page-design.md)."""

from app.services import automations

CARD_IDS = ["mail-status", "job-hunt", "referral-pages", "tailor-run", "apply-session",
            "customize-job-skills"]


def test_cards_come_in_the_designed_order():
    assert [c.id for c in automations.catalog().cards] == CARD_IDS


def test_every_card_has_its_metadata_and_a_body():
    for card in automations.catalog().cards:
        assert card.title and card.summary and card.body.strip(), card.id
        assert "maestro" in card.needs, card.id
        assert not card.body.startswith("---"), f"{card.id}: frontmatter leaked into the body"


def test_the_technique_file_is_not_a_card_but_rides_on_apply():
    cards = {c.id: c for c in automations.catalog().cards}
    assert "agent-apply-execution" not in cards
    assert "# Apply session" in cards["apply-session"].body
    # The included technique file is appended after the apply skill.
    assert cards["apply-session"].body.index("# Apply session") < len(cards["apply-session"].body) // 2
    assert "agent-apply-execution" not in cards["apply-session"].body.split("\n", 1)[0]


def test_apply_is_attended_until_full_automation_exists():
    cards = {c.id: c for c in automations.catalog().cards}
    assert cards["apply-session"].kind == "attended"
    assert cards["apply-session"].never == "Never submits without your yes."


def test_scheduled_wrappers_leave_timing_to_the_user():
    for app in automations.catalog().apps:
        assert "how often" in app.preamble and "when" in app.preamble, app.id
        assert "how often" not in app.attended_preamble, app.id


def test_remote_only_apps_are_shown_but_unreachable():
    apps = {a.id: a for a in automations.catalog().apps}
    assert list(apps) == ["claude-desktop", "codex", "generic", "claude-web", "chatgpt"]
    assert {i for i, a in apps.items() if not a.reachable} == {"claude-web", "chatgpt"}
    assert all(apps[i].note for i in ("claude-web", "chatgpt", "codex"))


def test_guardrails_survive_rewording():
    cards = {c.id: c.body for c in automations.catalog().cards}
    assert "Never send, reply to, archive, label or delete email." in cards["mail-status"]
    assert "Change nothing unless exactly one application" in cards["mail-status"]
    assert "Never set `accepted` or `withdrawn`" in cards["mail-status"]
    assert "Never contact a referral, and never apply or submit." in cards["referral-pages"]
    assert "Never write resume text or claims of your own." in cards["tailor-run"]
    assert "Never answer them yourself." in cards["tailor-run"]


def test_a_card_missing_its_metadata_fails_loudly(tmp_path, monkeypatch):
    bad = tmp_path / "broken" / "SKILL.md"
    bad.parent.mkdir()
    bad.write_text("---\nname: broken\ndescription: x\nmetadata:\n  title: Broken\n---\nbody\n")
    monkeypatch.setattr(automations, "SKILLS_DIR", tmp_path)
    automations.load_cards.cache_clear()
    try:
        import pytest
        with pytest.raises(ValueError):
            automations.load_cards()
    finally:
        monkeypatch.undo()
        automations.load_cards.cache_clear()
```

**Step 2: Run the tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_service.py -q`
Expected: FAIL with `ImportError: cannot import name 'automations'`

**Step 3: Implement**

```python
"""Automations: prompts a user copies into their own agent app.

The skill files under app/automations/skills are the single source of the text
(docs/plans/2026-10-04-automations-page-design.md). A skill with a `metadata`
block is a card; one without (agent-apply-execution) rides on a card through
`include`. Nothing about the user is inserted: the agent reads the brief, caps
and preferences live over MCP, and asks the user when to run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

SKILLS_DIR = Path(__file__).resolve().parent.parent / "automations" / "skills"

CARD_ORDER = ("mail-status", "job-hunt", "referral-pages", "tailor-run", "apply-session",
              "customize-job-skills")

Kind = Literal["scheduled", "attended", "custom"]
Need = Literal["maestro", "email", "browser", "web"]


class _Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    summary: str
    kind: Kind
    needs: list[Need]
    never: str | None = None
    include: list[str] = []


class AutomationCard(BaseModel):
    id: str
    title: str
    summary: str
    kind: Kind
    needs: list[Need]
    never: str | None
    body: str


class AgentApp(BaseModel):
    id: str
    label: str
    reachable: bool
    preamble: str
    attended_preamble: str
    note: str | None


class AutomationCatalog(BaseModel):
    cards: list[AutomationCard]
    apps: list[AgentApp]


_ASK = "First ask me how often and when to run it, then set up the schedule."
_REMOTE = "Needs remote access to Maestro, which isn't available yet."

APPS: tuple[AgentApp, ...] = (
    AgentApp(
        id="claude-desktop", label="Claude Desktop", reachable=True,
        preamble=f"Using your Maestro Career Studio connector, set the job below up as a scheduled task. {_ASK}",
        attended_preamble="Using your Maestro Career Studio connector, do the job below with me now.",
        note=None,
    ),
    AgentApp(
        id="codex", label="Codex", reachable=True,
        preamble=("Using the Maestro Career Studio MCP server, do the job below. Then help me schedule it: "
                  "ask how often and when, and write a launchd or cron entry that runs `codex exec` with this prompt."),
        attended_preamble="Using the Maestro Career Studio MCP server, do the job below with me now.",
        note="Codex has no scheduler of its own. It can write a launchd or cron entry that runs codex exec on a timer.",
    ),
    AgentApp(
        id="generic", label="Any MCP agent", reachable=True,
        preamble=f"Using the Maestro Career Studio MCP server, set the job below up with your own scheduler. {_ASK}",
        attended_preamble="Using the Maestro Career Studio MCP server, do the job below with me now.",
        note=None,
    ),
    AgentApp(
        id="claude-web", label="Claude web", reachable=False,
        preamble=f"Using your Maestro Career Studio connector, set the job below up as a scheduled task. {_ASK}",
        attended_preamble="Using your Maestro Career Studio connector, do the job below with me now.",
        note=f"{_REMOTE} Use Claude Desktop for now.",
    ),
    AgentApp(
        id="chatgpt", label="ChatGPT", reachable=False,
        preamble=f"Using the Maestro Career Studio connector, set the job below up as a scheduled task. {_ASK}",
        attended_preamble="Using the Maestro Career Studio connector, do the job below with me now.",
        note=f"{_REMOTE} Use Codex or Claude Desktop for now.",
    ),
)


def _split(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError(f"{path}: unterminated frontmatter")
    return yaml.safe_load(head) or {}, body.lstrip("\n")


@lru_cache(maxsize=1)
def load_cards() -> tuple[AutomationCard, ...]:
    """Parse every skill once. Raises ValueError on any malformed or unknown card."""
    bodies: dict[str, str] = {}
    metas: dict[str, _Meta] = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        front, body = _split(path)
        skill_id = path.parent.name
        if front.get("name") != skill_id:
            raise ValueError(f"{path}: name {front.get('name')!r} must match its folder")
        bodies[skill_id] = body
        if "metadata" in front:
            try:
                metas[skill_id] = _Meta.model_validate(front["metadata"])
            except ValidationError as exc:
                raise ValueError(f"{path}: bad metadata: {exc}") from exc
    if tuple(metas) != tuple(sorted(CARD_ORDER)):
        raise ValueError(f"cards {sorted(metas)} != designed {sorted(CARD_ORDER)}")
    cards = []
    for skill_id in CARD_ORDER:
        meta = metas[skill_id]
        body = bodies[skill_id]
        for extra in meta.include:
            if extra not in bodies:
                raise ValueError(f"{skill_id}: include {extra!r} has no skill file")
            body = f"{body.rstrip()}\n\n{bodies[extra]}"
        cards.append(AutomationCard(id=skill_id, title=meta.title, summary=meta.summary,
                                    kind=meta.kind, needs=meta.needs, never=meta.never, body=body))
    return tuple(cards)


def apply_kind() -> Kind:
    """Attended until full automation mode (phase 4) adds the auto-submit setting.

    Phase 4 reads that setting here and switches the Apply card's kind, `never`
    line and body to the auto-submit prompt; the page needs no change.
    """
    return "attended"


def catalog() -> AutomationCatalog:
    cards = [c.model_copy(update={"kind": apply_kind()}) if c.id == "apply-session" else c
             for c in load_cards()]
    return AutomationCatalog(cards=cards, apps=list(APPS))
```

**Step 4: Run the tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_service.py -q`
Expected: 8 passed. If `test_the_technique_file_is_not_a_card_but_rides_on_apply` is brittle
against the real apply-session length, replace its position assertion with
`body.startswith("# Apply session")`. Keep the intent: apply first, technique appended.

**Step 5: Commit**

```bash
git add backend/app/services/automations.py backend/tests/test_automations_service.py
git commit -m "feat(automations): catalog service over the skill files"
```

---

### Task 4: `GET /api/automations` and startup validation

**Files:**
- Create: `backend/app/routers/automations.py`
- Modify: `backend/app/main.py` (the import list at lines 12–33, the `lifespan` at line 111, `include_router` near line 204)
- Test: `backend/tests/test_automations_router.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_catalog_endpoint_shape():
    r = client.get("/api/automations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"cards", "apps"}
    card = data["cards"][0]
    assert set(card) == {"id", "title", "summary", "kind", "needs", "never", "body"}
    app_ = data["apps"][0]
    assert set(app_) == {"id", "label", "reachable", "preamble", "attended_preamble", "note"}


def test_startup_validates_the_cards():
    from app import main
    import inspect
    assert "automations.load_cards()" in inspect.getsource(main.lifespan)
```

**Step 2: Run to verify it fails**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_router.py -q`
Expected: FAIL (404 on the GET)

**Step 3: Implement**

`backend/app/routers/automations.py`:
```python
"""GET /api/automations — the copy-prompt catalog for the Automations page.

Read-only and DB-free: the skill files are the source
(docs/plans/2026-10-04-automations-page-design.md).
"""

from fastapi import APIRouter

from app.services import automations
from app.services.automations import AutomationCatalog

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("", response_model=AutomationCatalog)
def get_automations() -> AutomationCatalog:
    return automations.catalog()
```

In `main.py`:
- add `automations,` to the `from app.routers import (...)` list (alphabetical);
- add `app.include_router(automations.router)` after `version.router`;
- in `lifespan`, before `yield`:

```python
    from app.services import automations as automation_prompts

    automation_prompts.load_cards()  # a malformed skill file fails startup, not a page
```

The name `automations` is already taken by the router module in `main.py`, so import the
service as an alias. Then update the test's string to `"automation_prompts.load_cards()"`.

**Step 4: Run the tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_automations_router.py tests/test_automations_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routers/automations.py backend/app/main.py backend/tests/test_automations_router.py
git commit -m "feat(automations): GET /api/automations; startup validates the skill files"
```

---

### Task 5: Frontend types and prompt composition

**Files:**
- Modify: `frontend/lib/types.ts` (append)
- Create: `frontend/lib/automations.ts`

**Step 1: Types** (append to `lib/types.ts`):

```ts
// ── Automations (GET /api/automations; backend/app/services/automations.py) ──
export type AutomationKind = "scheduled" | "attended" | "custom";
export type AutomationNeed = "maestro" | "email" | "browser" | "web";
export type AutomationCard = {
  id: string;
  title: string;
  summary: string;
  kind: AutomationKind;
  needs: AutomationNeed[];
  never: string | null;
  body: string;
};
export type AgentApp = {
  id: string;
  label: string;
  reachable: boolean;
  preamble: string;
  attended_preamble: string;
  note: string | null;
};
export type AutomationCatalog = { cards: AutomationCard[]; apps: AgentApp[] };
```

**Step 2: `lib/automations.ts`:**

```ts
import type { AgentApp, AutomationCard, AutomationNeed } from "@/lib/types";

/** The text Copy puts on the clipboard: the app's wrapper, then the skill. A
 * scheduled card's wrapper tells the agent to ask the user when to run; an
 * attended or custom card's wrapper runs it now. Nothing about the user is
 * inserted (docs/plans/2026-10-04-automations-page-design.md). */
export function promptFor(card: AutomationCard, app: AgentApp): string {
  const wrapper = card.kind === "scheduled" ? app.preamble : app.attended_preamble;
  return `${wrapper}\n\n${card.body}`;
}

export const NEED_LABELS: Record<AutomationNeed, string> = {
  maestro: "Maestro",
  email: "Email",
  browser: "Browser",
  web: "Web",
};

export const APP_STORE_KEY = "cs-automations-app";

export function readStoredApp(): string | null {
  try {
    return window.localStorage.getItem(APP_STORE_KEY);
  } catch {
    return null;
  }
}

export function storeApp(id: string): void {
  try {
    window.localStorage.setItem(APP_STORE_KEY, id);
  } catch {
    // Private windows and blocked storage: the picker just won't remember.
  }
}
```

**Step 3: Typecheck**

Run: `npx tsc --noEmit` (from `frontend/`)
Expected: no errors

**Step 4: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/automations.ts
git commit -m "feat(automations): frontend types and prompt composition"
```

---

### Task 6: The page, the card and the sidebar entry

**Files:**
- Create: `frontend/app/automations/page.tsx`
- Create: `frontend/components/automations/automation-card.tsx`
- Create: `frontend/components/automations/app-picker.tsx`
- Modify: `frontend/components/app-sidebar.tsx:47-55` (add the entry and the `Workflow` icon import)

Before writing, read `frontend/app/referrals/page.tsx` (`PageShell`, `PageHeader`,
`LoadErrorState`, `Skeleton`, react-query, `apiFetch`), `frontend/components/source-toggle.tsx`
(the segmented-control pattern) and `frontend/lib/agent-links.ts`. Match their idioms and the
design-system tokens.

**Step 1: The sidebar.** In the "Job search" group, directly after Agent inbox:
```ts
      { href: "/automations", label: "Automations", icon: Workflow },
```
and add `Workflow` to the `lucide-react` import.

**Step 2: `app-picker.tsx`.** A segmented control in the style of `SourceToggle`:
- `role="group"` with `aria-label="Agent app"`;
- one `button` per app, with `aria-pressed`;
- props `{ apps: AgentApp[]; value: string; onChange: (id: string) => void }`.

**Step 3: `automation-card.tsx`:**

```tsx
"use client";

import { useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NEED_LABELS, promptFor } from "@/lib/automations";
import type { AgentApp, AutomationCard as Card_ } from "@/lib/types";

const KIND_LABEL = { scheduled: "Scheduled", attended: "Attended", custom: "Custom" } as const;

export function AutomationCard({ card, app }: { card: Card_; app: AgentApp }) {
  const [open, setOpen] = useState(false);
  const text = promptFor(card, app);

  function copy() {
    navigator.clipboard
      .writeText(text)
      .then(() => toast.success(`Prompt copied. Paste it into ${app.label}.`))
      .catch(() => {
        setOpen(true);
        toast.error("Couldn't copy. Select the prompt below instead.");
      });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle>{card.title}</CardTitle>
        <Badge variant="outline">{KIND_LABEL[card.kind]}</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p>{card.summary}</p>
        <div className="flex flex-wrap gap-1" aria-label="Needs">
          {card.needs.map((n) => (
            <Badge key={n} variant="tonal">{NEED_LABELS[n]}</Badge>
          ))}
        </div>
        {card.never ? <p className="text-muted-foreground">{card.never}</p> : null}
        {card.id === "apply-session" && card.kind === "attended" ? (
          <p className="text-muted-foreground">Scheduled applying comes with full automation mode.</p>
        ) : null}
        <div className="flex items-center gap-2">
          <Button onClick={copy} disabled={!app.reachable}>
            <Copy /> Copy prompt
          </Button>
          <Button variant="ghost" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide prompt" : "Show prompt"}
          </Button>
        </div>
        {open ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border p-3 text-body-small select-all">
            {text}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}
```
Use the tokens and text classes the repo actually has; check `globals.css` and
`docs/frontend-conventions.md`. The ones above are placeholders if they don't exist.

**Step 4: `app/automations/page.tsx`:**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AppPicker } from "@/components/automations/app-picker";
import { AutomationCard } from "@/components/automations/automation-card";
import { LoadErrorState } from "@/components/load-error-state";
import { PageHeader, PageShell } from "@/components/page-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { CONNECT_AGENT_GUIDE_URL } from "@/lib/agent-links";
import { readStoredApp, storeApp } from "@/lib/automations";
import type { AutomationCatalog } from "@/lib/types";

const AUTOMATIONS_KEY = ["automations"] as const;

export default function AutomationsPage() {
  const query = useQuery({
    queryKey: AUTOMATIONS_KEY,
    queryFn: () => apiFetch<AutomationCatalog>("/api/automations"),
  });
  const [appId, setAppId] = useState("claude-desktop");
  useEffect(() => {
    const stored = readStoredApp();
    if (stored) setAppId(stored);
  }, []);

  const data = query.data;
  const app = data?.apps.find((a) => a.id === appId) ?? data?.apps[0];
  const cards = data?.cards.filter((c) => c.kind !== "custom") ?? [];
  const custom = data?.cards.find((c) => c.kind === "custom");

  return (
    <PageShell>
      <PageHeader
        title="Automations"
        subtitle="Copy a prompt into your own agent app. It asks when to run, then does these jobs with Maestro."
      />
      <p>
        Your agent needs the Maestro connector first.{" "}
        <a href={CONNECT_AGENT_GUIDE_URL} target="_blank" rel="noreferrer">How to connect an agent</a>
      </p>
      {query.isError ? (
        <LoadErrorState title="Couldn't load automations." onRetry={() => query.refetch()} />
      ) : !data || !app ? (
        <Skeleton className="h-64" />
      ) : (
        <>
          <AppPicker
            apps={data.apps}
            value={app.id}
            onChange={(id) => {
              setAppId(id);
              storeApp(id);
            }}
          />
          {app.note ? <p className="text-muted-foreground">{app.note}</p> : null}
          <div className="grid grid-cols-2 gap-4">
            {cards.map((card) => (
              <AutomationCard key={card.id} card={card} app={app} />
            ))}
          </div>
          {custom ? <AutomationCard card={custom} app={app} /> : null}
        </>
      )}
    </PageShell>
  );
}
```
Check `LoadErrorState`'s real props in `components/load-error-state.tsx` and adapt them.

**Step 5: Gates**

Run (from `frontend/`): `npx tsc --noEmit && npm run lint && npm run build`
Expected: all pass

**Step 6: Commit**

```bash
git add frontend/app/automations frontend/components/automations frontend/components/app-sidebar.tsx
git commit -m "feat(automations): the Automations page and sidebar entry"
```

---

### Task 7: Source pins for the page

**Files:**
- Create: `backend/tests/test_frontend_automations.py`

**Step 1: Write the test.** This is the repo's convention: there is no frontend runner in CI, so
backend tests read the source.

```python
"""Pins: the Automations page (docs/plans/2026-10-04-automations-page-design.md)."""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/automations/page.tsx")
_CARD = _read("components/automations/automation-card.tsx")
_LIB = _read("lib/automations.ts")
_NAV = _read("components/app-sidebar.tsx")


def test_the_sidebar_lists_automations_right_after_agent_inbox():
    inbox = _NAV.index('{ href: "/proposals", label: "Agent inbox"')
    auto = _NAV.index('{ href: "/automations", label: "Automations"')
    assert inbox < auto < _NAV.index('{ href: "/referrals"')


def test_the_page_reads_the_catalog_and_names_itself():
    assert 'apiFetch<AutomationCatalog>("/api/automations")' in _PAGE
    assert 'title="Automations"' in _PAGE
    assert "It asks when to run" in _PAGE
    assert "CONNECT_AGENT_GUIDE_URL" in _PAGE


def test_copy_is_disabled_for_an_unreachable_app_and_falls_back_to_selection():
    assert "disabled={!app.reachable}" in _CARD
    assert ".catch(" in _CARD and "setOpen(true)" in _CARD
    assert "select-all" in _CARD


def test_scheduled_cards_use_the_ask_when_wrapper():
    assert 'card.kind === "scheduled" ? app.preamble : app.attended_preamble' in _LIB


def test_no_cadence_picker_or_user_data_in_the_prompt():
    for src in (_PAGE, _CARD, _LIB):
        for banned in ("cadence", "cron(", "schedule_time", "profile."):
            assert banned not in src, banned


def test_storage_is_best_effort():
    assert _LIB.count("try {") >= 2 and _LIB.count("catch") >= 2
```

**Step 2: Run it**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_frontend_automations.py -q`
Expected: PASS. If a string differs because Task 6 adapted a component, update the pin to the
real string; don't loosen the intent.

**Step 3: Commit**

```bash
git add backend/tests/test_frontend_automations.py
git commit -m "test(automations): pin the page's copy, wrappers and fallbacks"
```

---

### Task 8: Docs

**Files:**
- Modify: `SYSTEM.md`:
  - §2: add `app/automations/skills/   the agent prompts (skills); Automations page source`
    under `backend/app/`;
  - §3/§7: the Automations page as an agent surface: `GET /api/automations`, copy-only, no
    scheduler.
- Modify: `README.md` (lines ~458, ~575, ~668): mention the Automations page. The links to
  `docs/skills/` stay valid.
- Modify: `docs/GETTING_STARTED.md:338`, `backend/mcp_server/README.md:204`: same.
- Modify: `CHANGELOG.md` (Unreleased): "Automations page: copy a prompt into Claude Desktop,
  Codex or any MCP agent…; skills moved to backend/app/automations/skills/; new mail-status,
  referral-pages and tailor-run skills."

**Step 1: Edit the docs** per the SYSTEM.md header contract: integrate in present tense, no
dated paragraphs outside §11–§13.

**Step 2: Run the hygiene gate**

Run (repo root): `/opt/anaconda3/bin/python3 scripts/check_system_md.py`
Expected: passes

**Step 3: Commit**

```bash
git add SYSTEM.md README.md docs/GETTING_STARTED.md backend/mcp_server/README.md CHANGELOG.md
git commit -m "docs: Automations page and the skills' new home"
```

---

### Task 9: Full verification

**Step 1: Backend suite.** From `backend/`:
`/opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`
Expected: all pass, including the MCP tool-docstring budget tests.

**Step 2: Frontend gates.** From `frontend/`:
`npx tsc --noEmit && npm run lint && npm run build`
Expected: all pass

**Step 3: Live check.** Use a fresh stack on spare ports, following the memory recipe (uvicorn
on a free port, `next dev -p 3100` via `preview_start`). At 1280 and 1024:
- open `/automations` from the sidebar;
- the cards appear in this order: Mail status, Job hunt, Referral pages, Tailor run, Apply
  session (Attended), then the "Make your own" card;
- Copy on a scheduled card puts text starting "Using your Maestro Career Studio connector, set
  the job below up as a scheduled task. First ask me how often and when…" on the clipboard,
  and the toast names Claude Desktop;
- switching to ChatGPT shows the remote-access note and disables every Copy button;
- reload: the picker remembers the app;
- Show prompt shows the same text, selectable.

Take screenshots of both widths.

**Step 4: Slop ratchet** (repo root):
`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend`
and `check frontend`. Re-baseline only with a stated reason.

**Step 5: Report back.** List the commits, the test counts, the screenshots, and every
deviation from this plan with its reason.
