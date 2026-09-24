"""Pins for the settings and profile cards (UX IA and copy plan, Tasks 11 and 12; appendix C7, C8).

Kept apart from `test_frontend_settings_pages.py`, which pins the pages, tabs and deep links, so the
two halves of the settings work never edit the same file.

- **Models**: the old Models card held pickers, the endpoint, a capability table and the catalog. It
  is three cards now: Models (a picker per role, each with its measured capabilities and a named Test),
  Available models (words, not API keys, and focus that survives a removal) and Custom AI server
  (collapsed until used, and a collapse keeps the typed address).
- **Rhythm**: one spacing rhythm on every card (grid gaps, never margins; columns by the card's width;
  headed groups, never rules; default-size labels), every explicit Save keeps focus and asks before
  leaving, and a row that leaves hands focus on.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


# --- Models ------------------------------------------------------------------

_MODELS = _read("components/settings/models-section.tsx")
_CATALOG = _read("components/settings/model-catalog-panel.tsx")
_ENDPOINT = _read("components/settings/llm-endpoint.tsx")
_MODEL_LIB = _read("lib/model-catalog.ts")


def test_models_catalog_and_endpoint_are_three_cards():
    # Mutants: the catalog or the endpoint folded back into the Models card.
    assert 'id="models"' in _MODELS and 'id="api-keys"' in _MODELS
    # `<SettingCardAction` also starts with "<SettingCard", so the shell is matched with its id.
    assert re.search(r'<SettingCard\s+id="model-catalog"', _CATALOG)
    assert re.search(r'<SettingCard\s+id="custom-endpoint"', _ENDPOINT)
    assert "<ModelCatalogPanel" not in _MODELS and "<EndpointControls" not in _MODELS
    assert "CapabilityMatrix" not in _ENDPOINT + _MODELS
    assert "border-t" not in _MODELS + _CATALOG + _ENDPOINT


def test_the_cards_are_titled_in_plain_words():
    # Planner decision 20: "Custom endpoint" and "Model catalog" read as internals.
    assert 'title="Available models"' in _CATALOG
    assert 'title="Custom AI server"' in _ENDPOINT
    assert 'title="Model catalog"' not in _CATALOG and 'title="Custom endpoint"' not in _ENDPOINT


def test_the_role_models_are_fast_smart_and_assistant():
    # Owner decision 13: the chat role is the Assistant model (glossary, appendix D0).
    assert 'label: "Assistant model"' in _MODELS
    assert '"Chat model' not in _MODELS
    assert 'label: "Fast model"' in _MODELS and 'label: "Smart model"' in _MODELS


def test_each_chosen_model_shows_its_capabilities_and_a_named_test():
    assert "<ModelCapability" in _MODELS
    test = _MODELS[_MODELS.index("function ModelCapability") :]
    assert "aria-label={`Test ${name}`}" in test
    assert "focusableWhenDisabled" in test and "data-disabled:opacity-50" in test
    # The label stays: a bare spinner left the button with no name while it probed.
    assert "Test\n" in test[test.index("aria-label={`Test ${name}`}") :]


def test_a_role_hint_sits_between_its_label_and_its_picker():
    # Mutant: the hint packed into the label again ("Chat model · needs streaming tool calls").
    for fn in ("function FreeTextModel(", "function ModelSelect("):
        body = _MODELS[_MODELS.index(fn) :]
        hint = body.index('<p id={hintId} className="text-muted-foreground text-xs">')
        assert body.index("<Label htmlFor={id}>") < hint < body.index("aria-describedby={hintId}"), fn


def test_the_catalog_reads_words_not_keys():
    assert "capitalize" not in _CATALOG
    assert '" · seed"' not in _CATALOG and '" · in use"' not in _CATALOG
    assert "providerLabel(option.provider)} · {sourceLabel(option.source)}" in _CATALOG
    assert "showsModelId(option) ?" in _CATALOG and "showsModelId(option) ?" in _MODELS
    assert "rounded-lg border p-3" not in _CATALOG  # second containment level is tonal
    assert "discovery —" not in _CATALOG
    assert "import " not in _MODEL_LIB
    assert '{ openai: "OpenAI", gemini: "Gemini" }' in _MODEL_LIB
    assert 'return "Built-in";' in _MODEL_LIB
    assert "return option.label.trim() !== option.id;" in _MODEL_LIB


def test_sync_lives_in_the_card_header():
    header = _CATALOG[_CATALOG.index("<SettingCardAction>") : _CATALOG.index("</SettingCardAction>")]
    assert "sync.mutate(provider)" in header and "focusableWhenDisabled" in header
    assert "Find {providerLabel(provider)} models" in header


def test_a_removed_model_hands_focus_to_a_neighbour_or_the_list():
    assert "<RemoveButton" in _CATALOG and "label={`Remove ${option.id}`}" in _CATALOG
    assert "text-destructive size-7" not in _CATALOG
    assert "leaving.current = () => (neighbour?.isConnected ? neighbour : listRef.current);" in _CATALOG
    assert "focusIfDropped(next());" in _CATALOG
    assert '<ul ref={listRef} tabIndex={-1} aria-label="Available models"' in _CATALOG


def test_an_added_model_keeps_its_button_and_focus():
    # The + used to unmount for an "Added" span, taking focus to <body>.
    at = _CATALOG.index("onClick={() => add.mutate(model)}")
    add = _CATALOG[_CATALOG.rfind("<Button", 0, at) : _CATALOG.index("</Button>", at)]
    assert "focusableWhenDisabled" in add
    assert "aria-label={model.in_catalog ? `${model.id} added` : `Add ${model.id}`}" in add


def test_the_endpoint_starts_collapsed_and_keeps_its_draft():
    assert 'useState(Boolean(info.base_url) || info.json_mode !== "auto")' in _ENDPOINT
    assert "aria-expanded={open}" in _ENDPOINT and "aria-controls={panelId}" in _ENDPOINT
    assert "hidden={!open}" in _ENDPOINT


# --- Rhythm (Task 12, appendix C8) ---------------------------------------------

_SETTINGS = sorted((_FRONTEND / "components/settings").glob("*.tsx"))


def test_settings_cards_share_one_rhythm():
    """R2 to R9. Spacing is gap on a grid, never margins; columns follow the card's width, not
    the viewport's; groups are headed, never ruled; a label takes no size override."""
    assert len(_SETTINGS) >= 15
    for path in _SETTINGS:
        src = path.read_text()
        name = path.name
        assert "AutosaveRow" not in src, name
        assert re.search(r'className="[^"]*\bm[tby]-\d', src) is None, name
        assert re.search(r"\b(?:sm|md|lg):grid-cols-", src) is None, name
        assert "border-t" not in src, name
        assert re.search(r"<Label\b[^>]*className=\"[^\"]*text-(?:xs|sm)\b", src) is None, name
        for match in re.finditer(r"space-y-\d", src):
            tag = src[src.rfind("<", 0, match.start()) : match.start()]
            assert tag.startswith("<fieldset"), f"{name}: space-y outside a fieldset"
    card = _read("components/settings/setting-card.tsx")
    assert '<CardContent className="@container/setting">' in card


def test_autofill_groups_are_headed_not_ruled():
    src = _read("components/settings/autofill-section.tsx")
    assert "fieldset~fieldset>legend]:border-t" not in src
    assert 'const LEGEND = cn(GROUP_HEADING, "flex w-full items-center justify-between gap-2");' in src
    # A fieldset stays block flow: a legend is not a grid item, so gap never reaches it.
    assert re.search(r"<fieldset[^>]*className=\"[^\"]*\bgrid\b", src) is None
    assert '<div className="grid gap-8">' in src


def test_autofill_removes_are_named_and_hand_focus_to_add():
    src = _read("components/settings/autofill-section.tsx")
    # "Remove education entry" on every row named none of them; a removed row took focus with it.
    assert "label={`Remove school ${i + 1}`}" in src and "label={`Remove custom question ${i + 1}`}" in src
    assert "armFocus(addEducationRef);" in src and "armFocus(addQuestionRef);" in src
    assert "const armFocus = useFocusOnNextCommit();" in src
    assert src.count("ref={addEducationRef}") == 1 and src.count("ref={addQuestionRef}") == 1
    # The question gets a visible label, not only an aria-label.
    assert "<Label htmlFor={`af-custom-${i}-question`}>Question</Label>" in src
    assert "id={`af-custom-${i}-question`}" in src


def test_prompt_editors_stay_mounted_and_say_whether_they_are_open():
    src = _read("components/settings/prompts-section.tsx")
    assert "{advancedOpen && (" not in src  # collapsing dropped drafts and their leave guard
    assert "hidden={!advancedOpen}" in src
    assert src.count("aria-expanded=") == 2
    assert src.count("aria-controls=") == 2


def test_switch_rows_and_about_rows_share_their_geometry():
    layout = _read("components/settings/setting-layout.tsx")
    assert 'className="flex min-h-11 items-center justify-between gap-4 py-1.5"' in layout
    for rel in ("quick-tailor-section.tsx", "mcp-workflow-section.tsx", "appearance-section.tsx"):
        assert "<SwitchRow" in _read(f"components/settings/{rel}"), rel
    about = _read("components/settings/about-section.tsx")
    assert '<dl className="divide-y">' in about and "wrap-anywhere" in about
    remove = layout[layout.index("export function RemoveButton") :]
    # Muted at rest, destructive on hover/focus; focusable while every Remove is disabled.
    for cls in ("text-muted-foreground", "hover:text-destructive", "focus-visible:text-destructive"):
        assert cls in remove, cls
    assert "focusableWhenDisabled" in remove and "data-disabled:opacity-50" in remove


def test_every_explicit_save_row_is_the_shared_actions_row():
    # Save sits last, right-aligned, secondary first (R8).
    for rel in ("models-section.tsx", "auto-apply-section.tsx", "persona-section.tsx",
                "prompts-section.tsx", "autofill-section.tsx"):
        assert "className={ACTION_ROW}" in _read(f"components/settings/{rel}"), rel
    auto = _read("components/settings/auto-apply-section.tsx")
    row = auto[auto.index("className={ACTION_ROW}") :]
    # Nothing is cancelled: the button drops unsaved edits, as Persona's Discard does.
    assert row.index("Discard") < row.index("Save")
    assert ">\n            Cancel\n" not in auto


def test_explicit_save_cards_ask_before_leaving():
    # Planner decision 18 (C-Q8): both drafts survive a tab switch, and a navigation dropped them.
    auto = _read("components/settings/auto-apply-section.tsx")
    keys = _read("components/settings/models-section.tsx")
    assert "useLeaveGuard(draft !== null);" in auto
    assert "useLeaveGuard(openaiKey !== null || geminiKey !== null);" in keys


def test_the_blocklist_remove_is_a_named_target():
    # The × was a ~16px bare button; an IconButton is 24px, 44px on a coarse pointer.
    auto = _read("components/settings/auto-apply-section.tsx")
    assert 'size="icon-xs"' in auto and "label={`Remove ${name} from blocklist`}" in auto
    assert "rounded-full px-1" not in auto
    # The removed company takes its focused × with it; focus goes to the add field.
    assert "focusNext(blockInputRef);" in auto and "ref={blockInputRef}" in auto


def _button_at(src: str, marker: str) -> str:
    at = src.index(marker)
    return src[src.rfind("<Button", 0, at) : src.index("</Button>", at)]


def test_a_save_that_disables_itself_keeps_focus():
    # A native `disabled` Save dropped focus to <body> the moment it was pressed.
    cases = [
        ("models-section.tsx", "save.mutate({\n"),
        ("auto-apply-section.tsx", "onClick={() => draft && save.mutate(draft)}"),
        ("autofill-section.tsx", "save.mutate({ value: profileRef.current, revision: editRevision.current })"),
        ("prompts-section.tsx", "onClick={() => save.mutate()}"),
        ("prompts-section.tsx", "onClick={() => reset.mutate()}"),
        ("persona-section.tsx", "onClick={() => save.mutate(value)}"),
    ]
    for rel, marker in cases:
        button = _button_at(_read(f"components/settings/{rel}"), marker)
        assert "focusableWhenDisabled" in button, (rel, marker)
        assert "data-disabled:opacity-50" in button, (rel, marker)


def test_a_row_that_unmounts_on_save_or_discard_hands_focus_on():
    # Persona's Save row and Auto-apply's Discard leave with the edit; focus went with them.
    persona = _read("components/settings/persona-section.tsx")
    success = persona[persona.index("onSuccess: (result) => {") : persona.index("const draft = useMutation(")]
    discard = _button_at(persona, "setValue(saved);")
    assert "focusNext(textareaRef);" in success and "focusNext(textareaRef);" in discard
    assert "ref={textareaRef}" in persona
    auto = _read("components/settings/auto-apply-section.tsx")
    assert "focusNext(saveRef);" in auto and "ref={saveRef}" in auto
