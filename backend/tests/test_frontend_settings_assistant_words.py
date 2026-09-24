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
    assert '"Companion can now answer diversity questions"' in diversity
    assert '"Companion won\'t answer diversity questions"' in diversity
    boxes = _between(_AUTOFILL, "const setConsentFormsEnabled = ", "\n  };")
    assert '"Companion can now tick agreement boxes"' in boxes
    assert '"Companion won\'t tick agreement boxes"' in boxes


def test_the_consent_words_keep_every_promise():
    """Shortened, never dropped: no AI, no signing, no submitting, no passwords
    or ID numbers, and the switch can be turned off (Goal Card)."""
    flat = _flat(_AUTOFILL.replace('"\n          + "', ""))
    for promise in (
        "It never guesses and never uses AI for these.",
        "Tax-credit (WOTC) questions, signatures and legal statements stay with you.",
        "It never signs and never submits.",
        "Signatures, initials, passwords and government ID numbers are never filled",
        "Check every form before you submit it.",
        "Let Companion answer the voluntary diversity questions?",
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
    assert 'count(items, "career history item", "career history items")' in steps
    assert "return `${n} ${n === 1 ? one : many}`;" in steps


def test_the_template_step_names_the_template():
    steps = _read("components/setup/setup-steps.ts")
    assert '"default_template_name"' in steps and '"default_template_id"' not in steps
    assert '"Default template chosen"' in steps
