"""Pins for the settings and profile cards (UX IA and copy plan, Tasks 11 and 12; appendix C7, C8).

Kept apart from `test_frontend_settings_pages.py`, which pins the pages, tabs and deep links, so the
two halves of the settings work never edit the same file.

- **Models**: the old Models card held pickers, the endpoint, a capability table and the catalog. It
  is three cards now: Models (a picker per role, each with its measured capabilities and a named Test),
  Available models (words, not API keys, and focus that survives a removal) and Custom AI server
  (collapsed until used, and a collapse keeps the typed address).
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
