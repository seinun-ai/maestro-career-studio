"""Pins: the first run, a four-step Setup (design refresh, Task 7.1; board "Setup in four steps").

`/setup` (app/setup/page.tsx, components/setup/setup-flow.tsx and one file per step) writes through
endpoints that already exist: Settings' key save, model test and recommended models; the resume
import; the market, job preferences, the autofill profile and the diversity consent (through Profile's
own consent hook, components/profile/diversity-consent.tsx); it reads career history's contact block to
fill contact fields in place. No route was added for it, and Setup
stores no progress: which step is done is read from what each step wrote (docs/entities/others.md,
"Setup status"). The words and decisions are pure (lib/setup-flow.ts, its node suite) and the flow is
rendered with seeded reads (components/setup/setup-flow.test.mjs).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

_STEP_FILES = (
    "components/setup/setup-model-step.tsx",
    "components/setup/setup-resume-step.tsx",
    "components/setup/setup-where-step.tsx",
    "components/setup/setup-answers-step.tsx",
    "components/setup/setup-done.tsx",
)
# Profile's modules Setup shares (design refresh Task 7.2): the consent flow and Fill from career history.
_SHARED_FILES = ("components/profile/diversity-consent.tsx", "components/profile/contact.tsx")
_SETUP_FILES = ("app/setup/page.tsx", "components/setup/setup-flow.tsx", *_STEP_FILES, *_SHARED_FILES)


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _setup_src() -> str:
    return "\n".join(_read(rel) for rel in _SETUP_FILES)


# Every endpoint Setup reads or writes, and how. Each is an existing route (asserted against the app).
_CALLS = {
    ("GET", "/api/setup/status"),
    ("GET", "/api/settings/openai"),
    ("PUT", "/api/settings/openai"),
    ("POST", "/api/settings/openai/probe"),
    ("GET", "/api/settings/models/recommended"),
    ("PUT", "/api/settings/models/recommended"),
    ("GET", "/api/settings/market"),
    ("PUT", "/api/settings/market"),
    ("GET", "/api/settings/job-preferences"),
    ("PUT", "/api/settings/job-preferences"),
    ("GET", "/api/settings/autofill"),
    ("PUT", "/api/settings/autofill"),
    # The diversity consent, only through Profile's own flow (the same confirm, the server's stamp).
    ("GET", "/api/settings/eeo-consent"),
    ("PUT", "/api/settings/eeo-consent"),
    # Career history's contact block, for Fill from career history.
    ("GET", "/api/kb/profile"),
}
# The resume import goes through the import dialog's own hook and lib/api.ts's two calls.
_IMPORT_CALLS = {("POST", "/api/kb/import"), ("POST", "/api/kb/import/consolidate")}


def _routes() -> set[tuple[str, str]]:
    """Every (method, path) the app serves, as its schema lists them."""
    from app.main import app

    return {(method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item}


def test_setup_adds_no_backend_route():
    setup = {(m, p) for m, p in _routes() if p.startswith("/api/setup")}
    assert setup == {
        ("GET", "/api/setup/status"),
        ("GET", "/api/setup/connect"),
        ("GET", "/api/setup/connect/bundle"),
    }


def test_every_call_setup_makes_is_an_existing_route():
    routes = _routes()
    missing = sorted((_CALLS | _IMPORT_CALLS) - routes)
    assert not missing, missing


def test_setup_calls_only_the_pinned_endpoints():
    src = _setup_src()
    called = set(re.findall(r'apiFetch<[^(]*>\(\s*"(/api/[^"?]+)"', src))
    assert called == {path for _, path in _CALLS}, called ^ {path for _, path in _CALLS}
    # Each write names its method beside its path.
    for method, path in _CALLS:
        if method == "GET":
            continue
        assert re.search(rf'"{re.escape(path)}",\s*\{{\s*method: "{method}"', src), (method, path)
    # No other way out: no fetch of its own, and the import is the dialog's (one copy of that flow).
    assert not re.search(r"(?<![\w.])fetch\(", src)
    importer = _read("components/setup/use-resume-import.ts")
    assert "kbImportResume(file, false)" in importer and "kbImportConsolidate(" in importer
    assert "useResumeImport()" in _read("components/career/resume-import-dialog.tsx")
    assert "useResumeImport()" in _read("components/setup/setup-resume-step.tsx")


def test_a_key_turns_on_its_providers_recommended_models_only_after_it_passes():
    model = _read("components/setup/setup-model-step.tsx")
    probe = model.index('"/api/settings/openai/probe"')
    recommended = model.index('"/api/settings/models/recommended", {')
    assert probe < recommended
    assert "if (passed && plan.change)" in model
    # The chips are Settings › Basics' everyday jobs, one vocabulary (lib/model-catalog.ts).
    assert "EVERYDAY_JOBS.map(" in model
    # It says what it chose.
    assert "planWords(" in model


def test_the_four_steps_and_the_rail():
    flow = _read("components/setup/setup-flow.tsx")
    assert "SETUP_STEPS.map(" in flow
    assert 'role="progressbar"' in flow
    assert 'aria-current={i === step ? "step" : undefined}' in flow
    # Back is free: every rail step is a button, done or not.
    assert "onClick={() => go(i)}" in flow


def test_skip_for_now_and_back_on_every_step():
    flow = _read("components/setup/setup-flow.tsx")
    # One nav row under whichever of the four steps shows, never inside one step's own file.
    assert "{step < SETUP_STEPS.length ? <StepNav {...nav} onSkip={() => go(step + 1)} /> : null}" in flow
    nav = flow[flow.index("function StepNav(") :]
    assert "Skip for now" in nav and "Back" in nav and "Continue" in nav
    for rel in _STEP_FILES:
        assert "Skip for now" not in _read(rel), rel
    # Back is free: every step but the first has one (the rail reaches any step).
    assert "onBack: step > 0 ? () => go(step - 1) : undefined" in flow


def test_provider_cards_name_providers_in_text_and_hold_no_image():
    src = _setup_src()
    assert "<img" not in src and "next/image" not in src
    model = _read("components/setup/setup-model-step.tsx")
    assert '"Your own server"' in model
    assert "providerLabel(" in model
    for provider in ("anthropic", "openai", "gemini", "openrouter"):
        assert f'"{provider}"' in model, provider


def test_each_work_permit_question_carries_its_country():
    answers = _read("components/setup/setup-answers-step.tsx")
    # The card's heading is the country, and every question's group is named by it AND the question.
    assert "{question.label}" in answers
    assert "aria-labelledby={`${countryId} ${questionId}`}" in answers
    # In that country's own words (its market's work_auth_vocab, the visa status only for us_visa), from the
    # one table Profile asks from (lib/autofill-options.ts).
    assert "permitQuestions(question.vocab).map(" in answers
    assert "vocab: byKey.get(market)?.work_auth_vocab," in _read("lib/setup-flow.ts")
    # Each answer is that country's own entry, sent without the one-set work_auth view.
    assert "withPermitAnswer(current, question.market, q.key, option.value)" in answers
    lib = _read("lib/setup-answers.ts")
    assert "return forSaving(withPermit(profile, market, key, value));" in lib
    # No link to Profile's set of another country (the old "Answer in Profile" edited the home one).
    assert "Answer in Profile" not in answers and '"autofill-work_auth"' not in _read("components/setup/setup-done.tsx")
    assert 'anchorHref("/profile", `af-permit-${q.market}-${open.key}`)' in _read("components/setup/setup-done.tsx")


def test_diversity_only_for_a_country_with_a_set_and_only_through_consent():
    answers = _read("components/setup/setup-answers-step.tsx")
    lib = _read("lib/setup-flow.ts")
    assert "offers_eeo" in lib
    # Answer or decline in place, only through Profile's consent flow (the same confirm words and the
    # server-owned stamp, inv-eeo-standing-consent), and never an answer stored before that yes is on record.
    assert 'import { DiversityConsentSwitch, useDiversityConsent } from "@/components/profile/diversity-consent";' in answers
    pick = answers[answers.index("const pick = async (") : answers.index("\n  };", answers.index("const pick = async ("))]
    assert pick.index("const allowed = consent.enabled || (await setEeoConsentEnabled(true));") < pick.index(
        "if (!allowed) return;") < pick.index("withDiversityDeclined(current)")
    assert '{diversity === "answer" && consent.enabled ? (' in answers
    consent = _read("components/profile/diversity-consent.tsx")
    assert "await confirm(DIVERSITY_CONSENT_CONFIRM);" in consent
    assert "acknowledged_at: enabled ? null : consent.acknowledged_at," in consent
    # The switch sits beside the answers it covers (owner decision D10).
    block = answers[answers.index('{diversity === "answer" && consent.enabled ? ('):]
    assert block.index("<DiversityConsentSwitch") < block.index("<FieldGrid")
    # Setup writes no eeo key of its own: only the shared helpers do (lib/setup-answers.ts).
    assert not re.search(r"\beeo\s*:", "\n".join(_read(rel) for rel in _STEP_FILES))
    done = _read("components/setup/setup-done.tsx")
    assert 'anchorHref("/profile", "autofill-eeo")' in done
    assert "Answer them" in answers and "Decline them all" in answers


def test_the_done_screen_has_one_filled_action_and_two_others():
    done = _read("components/setup/setup-done.tsx")
    assert '<LeadCard' in done
    assert 'label: "Add your first job"' in done and 'href: "/new"' in done
    assert "Connect an agent app" in done and "CONNECTED_AGENTS_SETTINGS" in done
    assert "Add the Companion" in done and "COMPANION_GUIDE_URL" in done


def test_the_companion_guide_link_points_at_its_heading():
    links = _read("lib/agent-links.ts")
    assert 'COMPANION_GUIDE_URL = `${REPO}/docs/GETTING_STARTED.md#4-the-companion-browser-extension-optional`' in links
    guide = (_FRONTEND.parent / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "## 4. The Companion browser extension (optional)" in guide


def test_a_brand_new_install_opens_setup_once_and_today_points_at_it():
    today = _read("app/today/page.tsx")
    assert "useOpenSetupOnFirstLaunch(setup.data)" in today
    first = _read("components/setup/use-first-run.ts")
    assert "opensSetup(status, seen())" in first and 'router.replace("/setup")' in first
    assert "markSetupSeen()" in _read("components/setup/setup-flow.tsx")
    card = _read("components/setup/setup-entry-card.tsx")
    assert 'href: "/setup"' in card
    assert "UploadDialog" not in card


def test_setup_words_node_suite():
    result = run_node_test("lib/setup-flow.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_setup_flow_node_suite():
    """The flow rendered with seeded reads: each step as the first one open, the rail, the done screen."""
    result = run_node_test("components/setup/setup-flow.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_progress_dot_says_done_only_for_an_answered_question():
    """Round means a state: a question passed by or skipped is not answered, so its dot is not green."""
    answers = _read("components/setup/setup-answers-step.tsx")
    dots = answers[answers.index("{questions.map((q, i) => (") : answers.index("))}", answers.index("{questions.map((q, i) => ("))]
    assert "i < question" not in dots
    assert 'questionAnswered(q, answers.value)\n                        ? "bg-success"' in dots


def test_blocked_storage_never_bounces_today_to_setup():
    """A browser that refuses storage reads as seen: Today's setup card leads instead of /setup on every visit."""
    first = _read("components/setup/use-first-run.ts")
    seen = first[first.index("function seen(): boolean {") : first.index("\n}\n", first.index("function seen()"))]
    assert seen.rstrip().endswith("return true;\n  }")


def test_setup_says_where_to_get_each_key_in_settings_words():
    model = _read("components/setup/setup-model-step.tsx")
    assert "{KEY_FIELDS[card.id as Provider].hint}" in model
    assert "source={info[KEY_FIELDS[card.id as Provider].source]}" in model
    assert "const SOURCE" not in model
