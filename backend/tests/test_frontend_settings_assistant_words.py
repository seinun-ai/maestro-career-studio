"""Pins for Settings, Profile, the Assistant and setup speaking plainly (UX IA
and copy plan, Task 21; appendix D6, D7 and the D10 bugs in those groups).

The words themselves are held by the vocabulary, error-words and placeholder
ratchets. These pin the behaviour behind the words: a toast that names the
switch that moved, a hint that makes no false promise, a chip that says what
the Assistant is doing, a delete that asks first, a count that agrees with its
noun, and the consent wording that keeps every promise.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services import llm

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _flat(src: str) -> str:
    return " ".join(src.split())


def _between(src: str, start: str, end: str) -> str:
    at = src.index(start)
    return src[at : src.index(end, at)]


_AUTOFILL = _read("components/settings/autofill-section.tsx")
_CHAT = _read("components/chat/chat-page.tsx")


# --- Settings and Profile (D6) ------------------------------------------------


def test_the_role_models_are_fast_smart_and_assistant():
    models = _read("components/settings/models-section.tsx")
    for label in ("Fast model", "Smart model", "Assistant model"):
        assert f'label: "{label}"' in models, label
    assert "Chat model" not in models


def test_each_consent_switch_announces_itself():
    """D10.1: both switches share one mutation, whose toast read only `enabled`,
    so ticking the agreement-box switch announced the diversity state."""
    assert "EEO standing consent" not in _AUTOFILL
    shared = _between(_AUTOFILL, "const saveConsent = useMutation({", "\n  });")
    assert "toast.success(" not in shared
    diversity = _between(_AUTOFILL, "const setEeoConsentEnabled = ", "\n  };")
    assert '"The Companion can now answer diversity questions"' in diversity
    assert '"The Companion won\'t answer diversity questions"' in diversity
    boxes = _between(_AUTOFILL, "const setConsentFormsEnabled = ", "\n  };")
    assert '"The Companion can now tick agreement boxes"' in boxes
    assert '"The Companion won\'t tick agreement boxes"' in boxes


def test_the_consent_words_keep_every_promise():
    """Shortened, never dropped: no AI, no signing, no submitting, no passwords
    or ID numbers, and the switch can be turned off (Goal Card)."""
    flat = _flat(_AUTOFILL.replace('"\n          + "', ""))
    for promise in (
        "It never guesses and never uses AI for these.",
        "Tax-credit questions, signatures and legal statements stay with you.",
        "It never signs and never submits.",
        "Signatures, initials, passwords and government ID numbers are never filled",
        "Check every form before you submit it.",
        "Let the Companion answer the voluntary diversity questions?",
    ):
        assert promise in flat, promise
    assert flat.count("You can turn this off anytime.") == 2
    # "Decline the rest": it fills only the questions still unanswered (D10.17).
    assert "Decline the rest" in _AUTOFILL and "Decline all" not in _AUTOFILL


def test_the_custom_server_hint_never_promises_local_only():
    """D10.2: OpenRouter is a hosted service, so "nothing leaves this machine" was false."""
    endpoint = _read("components/settings/llm-endpoint.tsx")
    assert "nothing leaves this machine" not in endpoint
    assert "OpenRouter" not in endpoint
    # The warning for a remote address stays.
    assert "Your API key and resume will be sent to this server." in _flat(endpoint)


def test_every_prompt_has_words_on_screen():
    """An advanced prompt was titled only by its raw key (`extract_jd`)."""
    section = _read("components/settings/prompts-section.tsx")
    keys = sorted(p.stem for p in (_ROOT / "backend/app/prompts").glob("*.txt"))
    assert keys, "the prompt files moved"
    titled = set(re.findall(r'key: "(\w+)",\s*title:', section)) | set(re.findall(r'\["(\w+)", \{ title:', section))
    assert sorted(set(keys) - titled) == []


def test_work_location_has_one_no_preference():
    """"Not specified" and "Any" meant the same; a stored "any" reads No preference."""
    prefs = _read("components/settings/job-preferences-section.tsx")
    assert 'const REMOTE_OPTIONS = ["remote", "hybrid", "onsite"] as const;' in prefs
    assert '"Any"' not in prefs and "Not specified" not in prefs
    assert "preferences.remote && isRemoteOption(preferences.remote) ? preferences.remote : NO_PREFERENCE" in prefs


def test_about_links_to_the_update_guide():
    about = _read("components/settings/about-section.tsx")
    assert "./scripts/update.sh" not in about
    guide = (_ROOT / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    heading = re.search(r"^## (7\. Keeping .+)$", guide, re.M).group(1)
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
    assert "/blob/main/docs/GETTING_STARTED.md\";" in about
    assert f"const UPDATE_GUIDE_URL = `${{GUIDE}}#{slug}`;" in about
    # The build details stay for support, behind a disclosure.
    assert "Technical details" in about and "hidden={!open}" in about


# --- The Assistant (D7.3, D7.4) --------------------------------------------------


def test_the_assistant_names_what_it_is_doing():
    """D10.12: the working chips printed the model's tool names (`get_resume`)."""
    assert "TOOL_PHRASES" in _CHAT and '"Working…"' in _CHAT
    assert '<Wrench className="size-3" /> {name}' not in _CHAT
    assert "toolPhrases(streaming.tools).map((phrase) =>" in _CHAT
    # Every tool the Assistant can call has words.
    tools = (_ROOT / "backend/app/services/chat_tools.py").read_text(encoding="utf-8")
    names = set(re.findall(r'"name": "(\w+)"', tools))
    assert names
    phrased = set(re.findall(r'\["(\w+)", "[^"]+…"\]', _between(_CHAT, "const TOOL_PHRASES", "]);")))
    assert sorted(names - phrased) == []


def test_deleting_a_chat_asks_first():
    """D10.13: one click deleted a chat with no confirm and no undo."""
    delete = _between(_CHAT, "const deleteChat = async (", "\n  };")
    asked = delete.index("await confirm({")
    assert "destructive: true" in delete and "You can't undo this." in delete
    # Cancel keeps the chat: the answer gates the delete, not only precedes it.
    assert asked < delete.index("if (!ok) return;") < delete.index("removeSession.mutate(id);")
    # Both history lists (the rail and the sheet) go through it.
    assert _CHAT.count("onDelete={deleteChat}") == 2
    assert "removeSession.mutate(id)}" not in _CHAT


def test_a_chip_never_prints_a_raw_path():
    picker = _read("components/chat/scope-picker.tsx")
    assert "KB entity" not in picker and "`[${selection.index}]`" not in picker
    assert "`${name} ${selection.index + 1}`" in picker
    assert 'aria-label={`Remove ${label}`}' in picker


def test_the_capture_card_links_the_one_drafts_anchor():
    """D10.19: `/career#inbox` named nothing; the upload dialog uses `#kb-inbox`."""
    card = _read("components/chat/kb-capture-card.tsx")
    assert 'href="/career#kb-inbox"' in card and "#inbox\"" not in card
    assert 'id="kb-inbox"' in _read("app/career/page.tsx")


# --- Setup (D7.2) ----------------------------------------------------------------


def test_setup_counts_agree_with_their_nouns():
    """D10.8: "1 base resumes · 14 KB entries"."""
    steps = _read("components/setup/setup-steps.ts")
    assert "base resumes · " not in steps and "KB entries" not in steps
    assert 'count(bases, "base resume", "base resumes")' in steps
    assert 'count(items, "item", "items")} in your career history' in steps
    assert "return `${n} ${n === 1 ? one : many}`;" in steps


def test_the_template_step_names_the_template():
    steps = _read("components/setup/setup-steps.ts")
    assert '"default_template_name"' in steps and '"default_template_id"' not in steps
    assert '"Default template chosen"' in steps


# --- The lane 9 review and first-read pass ---------------------------------------


def _joined(src: str) -> str:
    """Source with `"…" + "…"` string joins and JSX line breaks folded to one line."""
    return _flat(re.sub(r'"\s*\+\s*"', "", src))


def test_the_agreement_box_consent_lists_what_it_unlocks():
    """C1: `consent_forms` unlocks every family in the extension's CONSENT_FORMS
    (extension/shared/policy.js), not only terms and acknowledgements."""
    flat = _joined(_AUTOFILL)
    assert (
        "This covers an application's own agreement boxes: terms, acknowledgements, "
        "certifications, arbitration and waivers. It ticks a box."
    ) in flat
    assert "Terms, certifications, arbitration and waiver boxes." in flat
    assert "Terms and acknowledgement boxes only." not in flat
    policy = (_ROOT / "extension/shared/policy.js").read_text(encoding="utf-8")
    consent = _between(policy, "const CONSENT_FORMS = [", "];")
    for family in ("terms", "acknowledge", "certif", "arbitration", "waiver"):
        assert family in consent, family


def test_the_consent_switches_keep_their_promises():
    """M3, M4: each switch's hint keeps what it never does."""
    flat = _joined(_AUTOFILL)
    assert "It never signs or submits, and never fills signatures, passwords or ID numbers." in flat
    assert "Tax-credit questions and signatures are always yours to fill." in flat
    assert "(WOTC)" not in _AUTOFILL
    # M21: the group says the questions are voluntary.
    assert 'title: "Diversity questions (voluntary)",' in _AUTOFILL


def test_the_diversity_switch_points_at_the_answers_below():
    """I1: the switch sits above the diversity questions, so "below" is where they are."""
    flat = _joined(_AUTOFILL)
    assert "Uses only your exact answers below." in flat
    assert "using only your exact answers below." in flat
    assert "answers above" not in flat
    eeo = _AUTOFILL.index('{group.key === "eeo" && (\n            // A permission, not a field.')
    assert eeo < _AUTOFILL.index('id="eeo-standing-consent"') < _AUTOFILL.index("{group.fields.map((field) =>")


def test_decline_the_rest_fills_only_blank_answers():
    """M22: it declines the questions still unanswered and never overwrites one."""
    decline = _between(_AUTOFILL, "const declineAllEeo = () => {", "\n  };")
    assert 'if (field.type !== "select" || !isBlank(eeo[field.key])) return [];' in decline
    assert "eeo: { ...groupValues(current, \"eeo\"), ...declines }," in decline
    flat = _joined(_AUTOFILL)
    # What it does in the words of the answer it writes (first-read pass).
    assert "Fills your blank diversity questions with “Decline to answer”. Select Save answers to keep it." in flat
    assert "aria-describedby={declineHintId}" in _AUTOFILL


def test_turning_a_switch_off_keeps_the_agreement_time():
    """M20: a yes is stamped by the server (null sent); a no keeps the stamp it had."""
    assert "acknowledged_at: enabled ? null : consent.acknowledged_at," in _AUTOFILL
    assert "acknowledged_at: consentForms ? null : consent.acknowledged_at," in _AUTOFILL


def test_a_consent_opens_on_cancel():
    """Enter must never grant a standing permission: both consent confirms open on Cancel."""
    dialog = _read("components/confirm-dialog.tsx")
    assert "initialFocus={opts?.destructive || opts?.consent ? cancelRef : confirmRef}" in dialog
    for name in ("setEeoConsentEnabled", "setConsentFormsEnabled"):
        body = _between(_AUTOFILL, f"const {name} = ", "\n  };")
        assert "consent: true," in body, name
        assert 'confirmLabel: "Allow",' in body, name


def test_the_agreement_box_switch_has_its_own_box():
    """It governs every application form, not the diversity answers it sat among."""
    flat = _joined(_AUTOFILL)
    assert "Companion permissions </p>" in flat
    # Rendered first in the editor, above Personal details.
    editor = _between(_AUTOFILL, "function AutofillEditor(", "\nfunction AgreedOn(")
    assert editor.index("<CompanionPermissions") < editor.index("{GROUPS.map((group) => {")
    boxes = _between(_AUTOFILL, "function CompanionPermissions(", "\n}\n")
    assert 'id="consent-forms"' in boxes and 'id="eeo-standing-consent"' not in boxes
    eeo = _between(_AUTOFILL, '{group.key === "eeo" && (\n            // A permission, not a field.', "</CardSection>")
    assert 'id="consent-forms"' not in eeo


def test_fill_from_career_history_says_why_it_waits():
    """It reads career history (GET /api/kb/profile), and a disabled reason is text, not a hover."""
    assert '{isFillingFromResume ? "Filling…" : "Fill from career history"}' in _AUTOFILL
    assert '"Fill from resume"' not in _AUTOFILL
    assert "<TooltipContent>{resumeDisabledReason}</TooltipContent>" not in _AUTOFILL
    assert "aria-describedby={contactReady ? undefined : fillHintId}" in _AUTOFILL
    assert "<p id={fillHintId}" in _AUTOFILL
    # Race sits in a voluntary group, so its label carries no "(optional)" of its own;
    # it stays optional for readiness (test_autofill_groups_parity.py).
    assert "<Label htmlFor={id} optional={field.optional && group.key !== \"eeo\"}>" in _AUTOFILL


def test_sentences_say_the_companion():
    """Planner decision 20: "the Companion" in a sentence, bare "Companion" only in a label."""
    for rel, sentence in (
        ("components/settings/autofill-section.tsx", 'description="The Companion uses these to fill job applications."'),
        ("components/settings/autofill-section.tsx", 'title: "Let the Companion tick agreement boxes?",'),
        ("components/settings/prompts-section.tsx", '"How the Companion picks answers for form choices."'),
        ("components/settings/connected-agents-card.tsx", "and the Companion, the Maestro CS browser extension,"),
    ):
        assert sentence in _flat(_read(rel)), (rel, sentence)


# The words each prompt shows (I3), checked against what the prompt file does.
_PROMPT_WORDS = (
    ("gap_tailor", "Tailoring from your answers", "How your answers from gap analysis go into a tailored resume."),
    ("base_resume_instruct", "Ask for changes", "How the resume editor suggests edits."),
    ("tailoring_skill", "Tailoring rules", "The honesty and wording rules for every tailoring edit."),
    ("kb_entity_resolve", "Matching items", "How roles and projects on your resumes are matched to career history items."),
    ("gap_enrichment", "Gap suggestions",
     "Suggested wording and a question for you on each gap. It never claims a skill your resume doesn't show."),
)


def test_the_prompt_words_say_what_each_prompt_does():
    section = _flat(_read("components/settings/prompts-section.tsx"))
    for key, title, description in _PROMPT_WORDS:
        row = f'["{key}", {{ title: "{title}", description: "{description}" }}]'
        essential = f'key: "{key}", title: "{title}", description: "{description}",'
        assert row in section or essential in section, key
    # gap_enrichment is told never to assert a skill the resume lacks.
    prompt = (_ROOT / "backend/app/prompts/gap_enrichment.txt").read_text(encoding="utf-8")
    assert "NEVER assert the candidate has a skill" in prompt
    # The editor says which words to keep: every prompt fills `$name` or `${name}`.
    assert "Keep every word that starts with $. The app fills them in." in section
    assert "aria-describedby={hintId}" in section


def test_a_rejected_file_names_the_types_its_picker_takes():
    """I4 (M29): a resume picker takes JSON and LaTeX, a document picker images;
    the message reads the caller's own `accept` (lib/upload-accept.test.ts)."""
    dropzone = _read("components/setup/dropzone.tsx")
    assert "reason: `This file type isn't supported. Use ${acceptedTypesLabel(accept)}.`," in dropzone
    assert "Use PDF, Word, Markdown or text." not in dropzone
    accept = _read("lib/upload-accept.ts")
    assert "export function acceptedTypesLabel(accept: string): string {" in accept


def test_the_assistant_promises_only_resume_undo():
    """I2: a resume edit makes a version you can restore; a template change does not."""
    assert "Edit a resume, draft project bullets or work on a template. You can undo any resume edit." in _CHAT
    assert "You can undo any edit." not in _CHAT


def test_a_stream_error_never_shows_raw_server_text():
    """M30: the ratchet can't see through `reason`, so the guard is pinned here."""
    error = _between(_CHAT, '} else if (event.type === "error") {', "\n        }")
    assert "const reason = event.detail;" in error
    # Through errorDetail: plain sentences only, and a refused or missing key says the fix.
    assert 'toast.error(errorDetail(new Error(reason)) ?? "The Assistant couldn\'t finish. Try again.");' in error
    assert error.count("reason") == 2


def test_the_endpoint_hints_say_which_choice_fixes_what():
    endpoint = _flat(_read("components/settings/llm-endpoint.tsx"))
    # M19: with no address, Gemini models run on Gemini too.
    assert "Leave empty to use OpenAI and Gemini." in endpoint
    assert '"Not set. Models run on OpenAI and Gemini."' in endpoint
    assert "Structured replies" not in endpoint
    assert "<Label htmlFor={jsonModeId}>Strict reply format</Label>" in endpoint
    assert "Leave on Auto. If your server shows errors, choose Off." in endpoint


def test_a_model_test_names_the_model_and_the_real_cause():
    models = _read("components/settings/models-section.tsx")
    probe = _between(models, "const probe = useMutation({", "\n  });")
    # The model's name on screen, never its id.
    assert "const name = modelName(info.data?.model_options ?? [], report.model);" in probe
    assert "report.model}" not in probe
    unreachable = _flat(_between(models, "function unreachableText(", "\n}\n"))
    # No custom server: the provider's key is the only thing to check.
    assert "`Couldn't reach ${provider}, so ${name} wasn't tested. Check your ${provider} API key, then try again.`" in unreachable
    assert "`Couldn't reach your AI server, so ${name} wasn't tested. Check the server address, then try again.`" in unreachable
    # A custom local server needs no key.
    assert 'description="Lets the app use OpenAI or Gemini. You need one unless you use a custom AI server."' in models
    assert "You need at least one." not in models


def test_the_key_fields_say_where_a_key_comes_from():
    models = _flat(_read("components/settings/models-section.tsx"))
    for host, prefix in (("platform.openai.com", "sk-"), ("aistudio.google.com", "AIza")):
        assert f">{host}</NewTabLink>. It starts with {prefix}." in models, host


def test_catalog_ids_show_only_when_they_add_something():
    """Lane 4's rule: the id is a second line only when it says more than the name."""
    catalog = _read("lib/model-catalog.ts")
    body = _between(catalog, "export function showsModelId(", "\n}\n")
    assert "comparable(option.label)" in body and "comparable(option.id)" in body


def test_profile_and_agent_limits_speak_plainly():
    """Minor: the words match what the server does (routers and services/proposals.py)."""
    for rel, words in (
        ("components/settings/market-section.tsx", "Sets the default currency for jobs you save and which diversity questions apply."),
        ("components/settings/persona-section.tsx", "It sets the tone of tailoring, cover letters and answers, and never adds facts to your resume."),
        ("components/settings/persona-section.tsx", "Draft from my career history"),
        ("components/settings/auto-apply-section.tsx", 'label: "Jobs per search",'),
        ("components/settings/auto-apply-section.tsx", 'hint: "Connected agents are told to file no more than this from one search.",'),
        ("components/settings/auto-apply-section.tsx", 'label: "Move unreviewed jobs to History after (days)",'),
        ("components/settings/auto-apply-section.tsx", 'hint: "Counts from when the job was filed. Queued jobs stay.",'),
        ("components/settings/auto-apply-section.tsx", 'hint: "Each application you say yes to submit counts for 24 hours.",'),
        ("components/settings/auto-apply-section.tsx",
         "hint: `${ATS_SCORE_LEAD_ALL_JOBS} Below this, connected agents ask you which base resume to use.`,"),
        ("components/settings/auto-apply-section.tsx",
         "Connected agents pick a base resume on their own only when its ATS score leads the next one by this many points."),
    ):
        assert words in _flat(_read(rel)), (rel, words)
    assert "Proposals per hunt" not in _read("components/settings/auto-apply-section.tsx")


def test_the_connected_agents_card_is_exact_about_bullets_and_yeses():
    card = _flat(_read("components/settings/connected-agents-card.tsx"))
    assert (
        "<li> Approve bullets, or mark them Not used, in your career history. They&apos;re told to do "
        "this only after you say yes. That&apos;s a rule they&apos;re given, not a lock. </li>"
    ) in card
    assert "The app records each yes but can&apos;t stop an agent, so stay with it while it applies." in card
    assert "audit trail" not in card
    hints = _flat(_read("components/settings/mcp-workflow-section.tsx"))
    assert "so Claude or Codex can go from scoring to tailoring to applying without being told each step." in hints
    assert "minimal" not in hints and "walk the" not in hints


def test_links_that_leave_the_app_say_so():
    """A visible icon and "opens in a new tab" for a screen reader, on every new-tab link in these files."""
    cue = _read("components/new-tab-link.tsx")
    assert '<ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />' in cue
    assert '<span className="sr-only"> (opens in a new tab)</span>' in cue
    for rel in (
        "app/settings/page.tsx",
        "components/settings/about-section.tsx",
        "components/settings/connected-agents-card.tsx",
        "components/settings/models-section.tsx",
        "components/chat/markdown.tsx",
    ):
        src = _read(rel)
        assert src.count('target="_blank"') == src.count("<NewTabCue />"), rel


def test_errors_and_setup_speak_plainly():
    assert "This page didn&apos;t load. Anything you saved is safe." in _read("app/error.tsx")
    steps = _read("components/setup/setup-steps.ts")
    for words in (
        'title: "Add your answers for job forms",',
        'title: "Describe yourself as a candidate (persona)",',
        '"PDF creation is ready."',
        '"PDF creation is ready. A few templates need extra software to look their best."',
        '`${count(bases, "base resume", "base resumes")}, ${count(items, "item", "items")} in your career history`',
    ):
        assert words in steps, words
    card = _read("components/setup/getting-started-card.tsx")
    # A PDF step with nothing to do is not a step.
    assert '!(row.id === "engines" && row.done && status.engines.pdflatex.available)' in card
    strip = _flat(_read("components/setup/setup-status-strip.tsx"))
    assert '<span className="text-muted-foreground text-xs font-medium">Setup steps:</span>' in strip
    assert '<Check aria-hidden="true" className="size-3" />' in strip
    assert "<DialogTitle>Import resumes and documents</DialogTitle>" in _read("components/setup/upload-dialog.tsx")


def test_a_missing_or_refused_key_says_what_to_do():
    """Every caller routes errors through errorDetail(); the server's key errors
    hold OPENAI_API_KEY or a provider's 401, which no plain-sentence check lets
    through, so they are named (lib/error-text.test.ts has the cases)."""
    text = _read("lib/error-text.ts")
    assert '"Add an API key in Settings › AI & models."' in text
    assert "refused your API key. Check it in Settings › AI & models." in text
    # The server's own no-key sentences (lane 10 rewrote them) still meet the
    # frontend's MISSING_KEY pattern, so both sides move together.
    missing = re.search(r"const MISSING_KEY = /(.+)/i;", text)
    assert missing, "MISSING_KEY moved"
    for message in (llm.NO_KEY_MESSAGE, llm.NO_GEMINI_KEY_MESSAGE):
        assert re.search(missing.group(1), message, re.I), message


# --- The Assistant: typed text, focus and state (first-read) -----------------------


def test_a_failed_send_gives_the_message_back():
    """Never lose typed text: with no API key the send failed before the server
    saved anything, and the box had already been cleared."""
    send = _between(_CHAT, "const send = async () => {", "\n  };")
    assert 'if (event.type === "message" && event.role === "user") {\n          // Stored: from here the thread holds it, whatever happens next.\n          saved = true;' in send
    restore = _between(send, "if (!saved) {", "\n      }")
    assert "setInput((current) => current || content);" in restore
    assert "setAttachments((current) => (current.length ? current : sentAttachments));" in restore


def test_a_model_problem_points_at_settings():
    """A 422 before the stream is a setup problem (no key, or a model that can't
    use tools): said in words beside the composer, with the way to fix it."""
    send = _between(_CHAT, "const send = async () => {", "\n  };")
    assert "if (err instanceof ApiError && err.status === 422) {" in send
    assert 'setSetupProblem(errorDetail(err) ?? "The Assistant can\'t use the chosen model. Choose another in Settings › AI & models.");' in _flat(send)
    notice = _flat(_between(_CHAT, "{setupProblem ? (", ") : null}"))
    assert '<p role="alert"' in notice
    assert '<Link href={anchorHref("/settings", "api-keys")}' in notice


def test_the_composer_never_remounts():
    """The first message switches the empty layout to the thread; a composer in
    each branch remounted and dropped focus to <body>."""
    assert _CHAT.count("{composer}") == 1
    main = _between(_CHAT, "<main tabIndex={-1}", "</main>")
    slot = main.index("{composer}")
    assert main.rindex(") : hasThread ? (", 0, slot) < main.rindex("{!threadFailed && (", 0, slot)


def test_deleting_a_chat_hands_focus_to_the_next_one():
    """M13, M14: focus goes to the next chat (else the previous, else New chat) as
    the confirm closes; Cancel keeps it on Delete."""
    delete = _between(_CHAT, "const deleteChat = async (", "\n  };")
    assert 'const neighbour = row?.nextElementSibling ?? row?.previousElementSibling;' in delete
    assert 'const successor = neighbour ? focusSuccessor(row, "button") : () => null;' in delete
    assert 'row?.closest("[data-chat-history]")?.querySelector<HTMLElement>("[data-new-chat]")' in delete
    assert "returnFocus: () => (confirmed ? (successor() ?? newChat) : null)," in delete
    assert delete.index("if (!ok) return;") < delete.index("confirmed = true;")
    assert _CHAT.count("data-new-chat") == 3 and _CHAT.count("data-chat-history") == 3
    # The rows sit in a wrapper of their own, so a neighbour is a row, never the heading.
    assert '<div className="space-y-0.5">\n        {sessions?.map' in _CHAT


def test_chat_history_says_when_it_did_not_load():
    """Backend down: the rail read as "no chats", not as a failure."""
    history = _between(_CHAT, "function SessionList(", "\n}\n")
    assert "if (isLoadFailure(query)) {" in history
    assert 'title="Couldn\'t load your chats."' in history
    assert "onRetry={() => void query.refetch()}" in history
    assert _CHAT.count("query={sessions}") == 2


def test_the_reply_in_progress_is_announced_and_shows_your_message():
    working = _between(_CHAT, "{streaming && (", "<div ref={bottomRef} />")
    assert '<div role="status" className="space-y-2">' in working
    assert '<span className="sr-only">The Assistant is replying…</span>' in working
    # Your message shows at once, and once only: hidden when the saved thread holds it.
    assert "{showPending ? (" in working
    assert (
        "streaming !== null && !detail.data?.messages.some((m) => m.id === streaming.userMessageId)"
    ) in _CHAT
    # The thread is refetched before the streaming block goes, so nothing flickers back to empty.
    finally_ = _between(_CHAT, "    } finally {\n      if (!saved) {", "\n    }\n  };")
    assert finally_.index("await qc.invalidateQueries({ queryKey: [\"chat-session\", activeSession] });") < finally_.index("setStreaming(null);")


def test_a_model_test_without_a_key_blames_the_key():
    """Browser pass: with no key the probe "reaches" nothing but reports three Nos,
    and the toast said the model can't do anything "Everything else works"."""
    models = _read("components/settings/models-section.tsx")
    probe = _between(models, "const probe = useMutation({", "\n  });")
    assert "const keyProblem = keyProblemIn(report);" in probe
    assert "toast.error(`Couldn't test ${name}. ${keyProblem}`);" in probe
    assert probe.index("keyProblem)") < probe.index("missing.length === 0")
    # A refused key never reads "Couldn't reach OpenAI": the key is checked before reachability.
    assert probe.index("if (keyProblem) {") < probe.index("if (report.reachable === false) {")
    # "Everything else works" only when something did.
    assert 'missing.length < CAPABILITY_LABELS.length ? " Everything else works." : ""' in probe
    # A capability's reason is words, never the provider's raw error.
    mark = _between(models, "function CapabilityMark(", "\n}\n")
    assert "${error ??" not in mark and "errorDetail(new Error(error))" in mark


def test_the_key_is_checked_before_the_model_capability():
    """No key: every capability is recorded as No, so the key is the real cause and says so first."""
    router = (_ROOT / "backend/app/routers/chat.py").read_text(encoding="utf-8")
    send = _between(router, "def send_message(", "def event_stream():")
    assert send.index("client = get_chat_client(model)") < send.index('llm_capabilities.require(db, model, "tools")')


def test_a_key_in_the_wrong_shape_is_refused_at_save():
    """First-read pass: "hello" saved as an OpenAI key with "API keys saved" and no word of
    doubt. The shape is checked before anything is sent; a saved key is "checked on first
    use", never called working (lib/api-key-format.test.ts has the cases)."""
    fmt = _read("lib/api-key-format.ts")
    assert 'openai: { prefix: "sk-", named: "An OpenAI" },' in fmt
    assert 'gemini: { prefix: "AIza", named: "A Gemini" },' in fmt
    assert 'if (!typed || (provider === "openai" && customServer)) return undefined;' in fmt
    assert "API key starts with ${prefix}. Check that you copied the whole key." in fmt


def test_a_wrong_key_is_never_sent_and_its_field_says_why():
    models = _read("components/settings/models-section.tsx")
    save = _between(models, "  const onSave = (customServer: boolean) => {", "\n  };")
    assert save.index("if (openaiWrong || geminiWrong) {") < save.index("saveKeysOnce(")
    assert "return;" in save[save.index("if (openaiWrong || geminiWrong) {"):save.index("saveKeysOnce(")]
    assert "toast.success(keysSavedText(patch));" in models
    assert '"API keys saved"' not in models
    # The refusal is the field's description, so focus on the field reads it.
    assert "aria-describedby={problem ? `${problemId} ${hintId}` : hintId}" in models


def test_a_saved_key_is_checked_on_first_use():
    from tests.node_ts import ts_map

    assert ts_map("./lib/api-key-format.ts", "keysSavedText", [
        {"openai_api_key": "sk-a"}, {"gemini_api_key": None},
        {"openai_api_key": "sk-a", "gemini_api_key": "AIza"},
    ]) == [
        "API key saved. We'll check it on first use.", "API key removed.",
        "API keys saved. We'll check them on first use.",
    ]


def test_no_screen_says_an_ats_rates_the_resume():
    """Task 24 found two: an ATS score is our estimate of how a system WOULD rate it
    (ATS_SCORE_LEAD in lib/ats-words.ts), never a reading from an employer's system."""
    root = Path(__file__).resolve().parents[2] / "frontend"
    hits = [
        p.relative_to(root).as_posix()
        for d in ("app", "components", "lib")
        for p in (root / d).rglob("*.ts*")
        if "tracking system rates" in p.read_text(encoding="utf-8")
    ]
    assert not hits


def _exported_regex(name: str):
    """`export const NAME = /source/flags;` from lib/error-text.ts, compiled as Python reads it."""
    src = _read("lib/error-text.ts")
    m = re.search(rf"export const {name} =\s*/(.+?)/([a-z]*);", src)
    assert m, f"{name} is no longer an exported regex literal (the Companion's copy is pinned to it)"
    return re.compile(m.group(1), re.I if "i" in m.group(2) else 0)


def test_the_web_app_recognises_every_key_sentence_the_server_writes():
    """The coordinator's Companion pass: a refused key read as a generic failure because
    REFUSED_KEY did not know the server's own sentence. Every sentence llm.py writes for a
    missing or refused key, and the providers' raw 401s, match the exported patterns."""
    from app.services import llm

    missing, refused = _exported_regex("MISSING_KEY"), _exported_regex("REFUSED_KEY")
    for text in (llm.NO_KEY_MESSAGE, llm.NO_GEMINI_KEY_MESSAGE, "GEMINI_API_KEY is required for Gemini models"):
        assert missing.search(text), text
    sentences = [str(llm._no_answer(llm._KEY_REFUSED, "detail", provider=who))
                 for who in ("OpenAI", "Gemini", "Your AI server")]
    sentences.append("The AI model didn't answer (your key was refused). Try again, or check your key in "
                     "Settings › AI & models.")
    sentences += ["Error code: 401 - {'error': {'code': 'invalid_api_key'}}",
                  'Gemini models.list failed: 400 {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}']
    for text in sentences:
        assert refused.search(text), text
    # Not every sentence that names a key is a refusal.
    assert not refused.search("The Assistant needs an API key. Add one in Settings › AI & models.")


def test_every_setup_chip_marks_done_or_not_done():
    strip = _read("components/setup/setup-status-strip.tsx")
    assert '<Circle aria-hidden="true" className="size-3" />' in strip
    assert 'return `${step.label}, ${step.done ? "done" : "not done"}`;' in strip
