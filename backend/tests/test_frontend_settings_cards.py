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


def _slice(src: str, start: str, end: str) -> str:
    """From `start` up to the next `end` after it (the end of a function, a mutation, a tag), or to
    the end of the file (the file's last function)."""
    at = src.index(start)
    stop = src.find(end, at + len(start))
    return src[at : stop if stop != -1 else len(src)]


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
    start = _MODELS.index("function ModelCapability")
    test = _MODELS[start : _MODELS.index("\nfunction ", start + 1)]
    assert "aria-label={`Test ${name}`}" in test
    assert "focusableWhenDisabled" in test and "data-disabled:opacity-50" in test
    # The label stays: a bare spinner left the button with no name while it probed.
    assert "Test\n" in test[test.index("aria-label={`Test ${name}`}") :]


def test_each_role_tests_and_reads_its_own_model():
    # Mutants: every Test spins, the other Tests stay live while one probes, the marks are read
    # by the role's key instead of the chosen model's id.
    role = _slice(_MODELS, "function RoleModel(", "\nfunction ")
    assert "const model = info[role.key];" in role
    assert "report={info.capabilities[model]}" in role
    assert "probing={probing === model}" in role and "busy={probing !== null}" in role
    assert "onProbe={() => onProbe(model)}" in role


def test_each_role_saves_its_own_field():
    # Mutant: every picker saved the Fast model.
    assert "onChange={(value) => value && save.mutate(role.patch(value))}" in _MODELS
    for key in ("fast_model", "smart_model", "chat_model"):
        assert re.search(rf'key: "{key}",[^}}]*patch: \(v: string\) => \(\{{ {key}: v \}}\)', _MODELS), key


def test_a_saved_key_leaves_nothing_to_guard():
    # Mutant: the typed keys kept after a save, so the leave guard asked about saved work.
    saved = _slice(_MODELS, "const saveKeys = useSaveModelSettings(() => {", "});")
    assert "setOpenaiKey(null);" in saved and "setGeminiKey(null);" in saved


def test_a_failed_capability_says_why_to_a_screen_reader():
    # The reason lived only in `title`, which neither a keyboard nor a screen reader reaches.
    mark = _slice(_MODELS, "function CapabilityMark(", "\nfunction ")
    assert '<span className="sr-only">{reason}</span>' in mark
    assert "title={reason}" in mark
    assert mark.count('aria-hidden="true"') == 3  # both icons and the visible chip label


def test_a_role_hint_sits_between_its_label_and_its_picker():
    # Mutant: the hint packed into the label again ("Chat model · needs streaming tool calls").
    for fn in ("function FreeTextModel(", "function ModelSelect("):
        body = _slice(_MODELS, fn, "\nfunction ")
        hint = body.index('<p id={hintId} className="text-muted-foreground text-xs">')
        assert body.index("<Label htmlFor={id}>") < hint < body.index("aria-describedby={hintId}"), fn


def test_the_catalog_reads_words_not_keys():
    assert "capitalize" not in _CATALOG
    for key in ('" · seed"', '" · in use"'):
        assert key not in _CATALOG, key
    assert "providerLabel(option.provider)} · {sourceLabel(option.source)}" in _CATALOG
    for src in (_CATALOG, _MODELS):
        assert "showsModelId(option) ?" in src
    assert "rounded-lg border p-3" not in _CATALOG  # second containment level is tonal
    assert "discovery —" not in _CATALOG


def test_the_model_words_live_in_one_import_free_helper():
    # `node --test` loads lib/model-catalog.ts, so it imports nothing (node tests are not in CI).
    assert "import " not in _MODEL_LIB
    assert 'new Map([\n  ["openai", "OpenAI"],\n  ["gemini", "Gemini"],\n]);' in _MODEL_LIB
    assert 'if (source === "configured") return "In use";' in _MODEL_LIB
    assert 'return "Built-in";' in _MODEL_LIB
    # The id shows only when it says more than the name (lib/model-catalog.test.ts has the cases).
    assert "if (name === id) return false;" in _MODEL_LIB


def test_an_unknown_provider_reads_as_a_word():
    # A plain-object lookup answered "constructor" with a function, and any other key with itself.
    label = _slice(_MODEL_LIB, "export function providerLabel(", "\n}\n")
    assert "PROVIDER_LABELS.get(provider) ?? titleCase(provider)" in label
    assert "PROVIDER_LABELS[provider]" not in _MODEL_LIB


def test_sync_lives_in_the_card_header():
    header = _CATALOG[_CATALOG.index("<SettingCardAction>") : _CATALOG.index("</SettingCardAction>")]
    assert "sync.mutate(provider)" in header and "focusableWhenDisabled" in header
    # One sync at a time: both Find buttons wait while either runs.
    assert "disabled={syncing !== null}" in header
    assert "Find {providerLabel(provider)} models" in header


def test_a_removed_model_hands_focus_to_a_neighbour_or_the_list():
    assert "<RemoveButton" in _CATALOG and "label={`Remove ${option.id}`}" in _CATALOG
    assert "text-destructive size-7" not in _CATALOG
    assert "next: () => (neighbour?.isConnected ? neighbour : listRef.current)," in _CATALOG
    assert "focusIfDropped(pending.next());" in _CATALOG
    assert '<ul ref={listRef} tabIndex={-1} aria-label="Available models"' in _CATALOG
    # Every Remove waits while one runs, so only one handoff is ever armed.
    assert "busy={remove.isPending}" in _CATALOG
    assert "disabled={busy}" in _slice(_CATALOG, "<RemoveButton", "/>")


def test_the_focus_handoff_waits_for_the_removed_row():
    # Mutants: the effect runs once and never again; an Add landing mid-removal re-renders the
    # list with the row still in it and uses the handoff up; a failed removal leaves it armed.
    effect = _slice(_CATALOG, "useEffect(() => {", "]);")
    assert effect.endswith("}, [info.model_options")
    assert "info.model_options.some((option) => option.id === pending.id)" in effect
    on_error = _slice(_slice(_CATALOG, "const remove = useMutation(", "\n  });"), "onError:", "},")
    assert "leaving.current = null;" in on_error


def test_an_added_model_keeps_its_button_and_focus():
    # The + used to unmount for an "Added" span, taking focus to <body>.
    at = _CATALOG.index("onClick={() => addOnce(model)}")
    add = _CATALOG[_CATALOG.rfind("<Button", 0, at) : _CATALOG.index("</Button>", at)]
    assert "focusableWhenDisabled" in add
    assert "aria-label={model.in_catalog ? `${model.id} added` : `Add ${model.id}`}" in add


def test_a_long_model_id_truncates_inside_the_card():
    # Wave-1 browser pass, 768 and 375: the list is a grid child (min-width:auto), so a long
    # fine-tuned id widened it past the card, `truncate` never applied, and the provider label and
    # Remove left the card. The whole id stays on hover and in the DOM a screen reader reads.
    assert '<ul ref={listRef} tabIndex={-1} aria-label="Available models" className="min-w-0 divide-y' in _CATALOG
    row = _slice(_CATALOG, "function CatalogRow(", "\n}\n")
    assert '<div className="min-w-0 flex-1">' in row
    assert '<p className="truncate text-sm font-medium" title={option.label}>' in row
    assert 'className="text-muted-foreground truncate font-mono text-xs" title={option.id}>' in row
    # The provider label and Remove never shrink; the name column does.
    assert '<span className="text-muted-foreground shrink-0 text-xs">' in row
    # The discovered list is a grid child too.
    assert '<CardSection className="grid min-w-0 gap-3">' in _CATALOG
    assert 'className="min-w-0 flex-1 truncate font-mono" title={model.id}>' in _CATALOG


def test_a_role_picker_keeps_focus_while_its_pick_saves():
    # Wave-1 browser pass: every pick disabled all three pickers while it saved, and the trigger the
    # list closed onto dropped focus to <body> (RolePicker's rule: readOnly, not disabled).
    picker = _slice(_MODELS, "function ModelSelect(", "\n}\n")
    assert "<Select value={value} onValueChange={onChange} readOnly={saving}>" in picker
    assert "disabled={" not in picker.replace("<SelectItem value={value} disabled>", "")
    free = _slice(_MODELS, "function FreeTextModel(", "\n}\n")
    assert "readOnly={saving}" in free and "disabled=" not in free
    keys = _slice(_MODELS, "function KeyField(", "\n}\n")
    assert "readOnly={saving}" in keys and "disabled=" not in keys
    endpoint = _slice(_ENDPOINT, "function EndpointControls(", "\n}\n")
    assert endpoint.count("readOnly={saving}") == 2  # the address and JSON mode


def test_the_endpoint_starts_collapsed_and_keeps_its_draft():
    assert 'useState(Boolean(info.base_url) || info.json_mode !== "auto")' in _ENDPOINT
    assert "aria-expanded={open}" in _ENDPOINT and "aria-controls={panelId}" in _ENDPOINT
    # Hidden, never unmounted: a collapse keeps the typed address.
    assert re.search(r"<div id=\{panelId\} hidden=\{!open\}>\s*<EndpointControls ", _ENDPOINT)


def test_a_rejected_address_keeps_what_was_typed():
    # The draft cleared on click, so a 400 (ftp://nope) threw the typed address away. It clears in
    # the save's success, and only for a save of the address: a JSON mode pick keeps it.
    save = _button_at(_ENDPOINT, "onSave({ base_url: draft?.trim() || null })")
    assert "setDraft" not in save and "onDraft" not in save
    saved = _slice(_ENDPOINT, "const save = useSaveModelSettings((_info, patch) => {", "});")
    assert 'if ("base_url" in patch) setDraft(null);' in saved
    assert "onSave={saveOnce}" in _ENDPOINT


def test_a_typed_address_asks_before_leaving():
    # Wave-1 browser pass: the address survived a tab switch, and a sidebar link dropped it silently.
    assert "useLeaveGuard(draft !== null);" in _ENDPOINT
    # One draft, held beside its guard: the controls read and write it, never a copy of their own.
    assert _ENDPOINT.count("useState<string | null>(null)") == 1
    controls = _slice(_ENDPOINT, "function EndpointControls(", "\n}\n")
    assert "useState" not in controls and "onChange={(e) => onDraft(e.target.value)}" in controls


def test_a_local_server_raises_no_warning():
    # host.docker.internal is this machine seen from the backend container; `URL` keeps the IPv6
    # loopback in brackets, so a bare "::1" never matched.
    hosts = re.search(r"const LOCAL_HOSTS = new Set\(\[(.*)\]\);", _MODEL_LIB).group(1)
    assert '"host.docker.internal"' in hosts and '"[::1]"' in hosts
    assert "{isRemoteEndpoint(value) && (" in _ENDPOINT
    assert "function isRemoteEndpoint" not in _ENDPOINT


# --- Rhythm (Task 12, appendix C8) ---------------------------------------------

_SETTINGS = sorted((_FRONTEND / "components/settings").glob("*.tsx"))


def test_settings_cards_share_one_rhythm():
    """R2 to R9. Spacing is gap on a grid, never margins; columns follow the card's width, not
    the viewport's; groups are headed, never ruled; a label takes no size override."""
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


def test_every_card_body_is_the_container_its_columns_read():
    assert len(_SETTINGS) >= 15
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
    # Each ref on its own Add: swapped, a removed school focused Add question.
    assert "ref={addEducationRef}" in _button_at(src, "onClick={() => setEducation([...education, {}])}")
    assert "ref={addQuestionRef}" in _button_at(src, "onClick={() => setCustom([...custom, {")


def test_a_custom_question_has_a_visible_label():
    # Only an aria-label named it; a sighted user saw an unlabelled box.
    src = _read("components/settings/autofill-section.tsx")
    assert "<Label htmlFor={`af-custom-${i}-question`}>Question</Label>" in src
    assert "id={`af-custom-${i}-question`}" in src


def test_prompt_editors_stay_mounted_and_say_whether_they_are_open():
    src = _read("components/settings/prompts-section.tsx")
    assert "{advancedOpen && (" not in src  # collapsing dropped drafts and their leave guard
    assert "hidden={!advancedOpen}" in src
    assert src.count("aria-expanded=") == 2
    assert src.count("aria-controls=") == 2
    # Each aria-controls names an element that exists.
    assert '<div id={bodyId} className="grid gap-3 px-3 pb-3">' in src


def test_an_advanced_prompt_key_wraps_inside_its_row():
    # Wave-1 browser pass, 375 with Advanced prompts open: a key is one unbreakable word
    # (`resume_finding_verify`), so its row ran 262px in a 239px body and Expand left the card.
    src = _read("components/settings/prompts-section.tsx")
    assert '<p className="font-mono text-sm wrap-anywhere">{prompt.key}</p>' in src
    # Only a key PROMPT_TITLES lacks is shown at all (appendix D6.1); a titled one hides it.
    assert '<p className="text-muted-foreground font-mono text-xs wrap-anywhere">{prompt.key}</p>' not in src
    assert '<span className="text-muted-foreground shrink-0 text-xs">' in src  # Expand keeps its width


def test_switch_rows_and_about_rows_share_their_geometry():
    layout = _read("components/settings/setting-layout.tsx")
    row = _slice(layout, "export function SwitchRow(", "\n}\n")
    assert '<div className="flex min-h-11 items-center justify-between">' in row
    # The label fills the row (height, width and the gap), so a tap anywhere on it toggles.
    assert '<Label htmlFor={htmlFor} className="flex-1 self-stretch py-1.5 pr-4 leading-snug">' in row
    for rel in ("quick-tailor-section.tsx", "mcp-workflow-section.tsx", "appearance-section.tsx"):
        assert "<SwitchRow" in _read(f"components/settings/{rel}"), rel
    about = _read("components/settings/about-section.tsx")
    assert '<dl className="divide-y">' in about and "wrap-anywhere" in about


def test_a_remove_is_quiet_until_hovered_or_focused():
    layout = _read("components/settings/setting-layout.tsx")
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
    # A company typed but not yet added is typed text too (never lose typed text).
    assert 'useLeaveGuard(draft !== null || blockInput.trim() !== "");' in auto
    assert "useLeaveGuard(openaiKey !== null || geminiKey !== null);" in keys
    # A save clears the draft, so the guard stops asking about saved work.
    saved = _slice(auto, "onSuccess: (result) => {", "},")
    assert "setDraft(null);" in saved


def test_the_blocklist_remove_is_a_named_target():
    # The × was a ~16px bare button; an IconButton is 24px, 44px on a coarse pointer.
    auto = _read("components/settings/auto-apply-section.tsx")
    assert 'size="icon-xs"' in auto and "label={`Remove ${name}`}" in auto
    assert "rounded-full px-1" not in auto
    # The chip grows to hold the 44px coarse-pointer target, so wrapped rows never overlap.
    assert '"bg-muted inline-flex min-h-7 items-center' in auto
    # The removed company takes its focused × with it; focus goes to the add field.
    assert "focusNext(blockInputRef);" in auto and "ref={blockInputRef}" in auto


def _button_at(src: str, marker: str) -> str:
    at = src.index(marker)
    return src[src.rfind("<Button", 0, at) : src.index("</Button>", at)]


def test_a_save_that_disables_itself_keeps_focus():
    # A native `disabled` Save dropped focus to <body> the moment it was pressed.
    cases = [
        ("models-section.tsx", "saveKeysOnce({\n"),
        ("auto-apply-section.tsx", "onClick={() => draft && saveOnce(draft)}"),
        ("autofill-section.tsx", "saveOnce({ value: profileRef.current, revision: editRevision.current })"),
        ("prompts-section.tsx", "onClick={() => saveOnce()}"),
        ("prompts-section.tsx", "onClick={() => resetOnce()}"),
        ("persona-section.tsx", "onClick={() => saveOnce(value)}"),
        ("llm-endpoint.tsx", "onSave({ base_url: draft?.trim() || null })"),
        ("autofill-section.tsx", '{isFillingFromResume ? "Filling…" : "Fill from career history"}'),
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


# --- The card header (Task 10, appendix C6) -------------------------------------

_CARD = _read("components/settings/setting-card.tsx")
_ACTION = re.search(r'const ACTION =\s*"([^"]+)";', _CARD).group(1).split()


def test_an_empty_header_slot_takes_no_room():
    # Mutant: `empty:hidden` dropped, so a card with no action kept a gap beside its title.
    assert "empty:hidden" in _ACTION
    assert "<CardAction ref={setSlot} className={ACTION} />" in _CARD


def test_a_narrow_header_stacks_the_action_under_the_description():
    # Under 28rem the action leaves column 2 for its own row, starting at the left edge; the
    # title and description stay in column 1, so the description never flows into column 2.
    for cls in ("col-start-1", "row-span-1", "row-start-auto", "justify-self-start", "*:justify-start"):
        assert f"@max-md/card-header:{cls}" in _ACTION, cls
    assert '<CardDescription className="col-start-1">' in _CARD
    assert re.search(r'<CardTitle role="heading" aria-level=\{2\} className="col-start-1">', _CARD)


def test_a_header_action_renders_nowhere_until_the_slot_exists():
    # Mutant: the action rendered inline in the body for a frame, then jumped into the header.
    action = _slice(_CARD, "export function SettingCardAction(", "\n}\n")
    assert "return slot ? createPortal(children, slot) : null;" in action
