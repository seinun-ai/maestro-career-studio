"""The Reasoning model role on Settings > AI & models > Models (source pins; the browser review is separate)."""

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_MODELS = " ".join((_FRONTEND / "components/settings/models-section.tsx").read_text().split())
_TYPES = " ".join((_FRONTEND / "lib/types.ts").read_text().split())


def test_the_reasoning_model_is_a_fourth_role_that_saves_alone():
    assert 'key: "reasoning_model", label: "Reasoning model",' in _MODELS
    assert (
        'hint: "Used only when the Companion is stuck. Strong models reason better, and cheaper ones cost less.",'
    ) in _MODELS
    assert "patch: (v: string) => ({ reasoning_model: v })," in _MODELS
    assert "reasoning_model?: string;" in _MODELS and "reasoning_model: string;" in _TYPES


def test_the_four_roles_fit_the_card_at_a_narrow_width():
    # Two across from the card's 2xl width, four from 4xl; never three (the fourth would sit alone).
    assert "@2xl/setting:grid-cols-2 @4xl/setting:grid-cols-4" in _MODELS
    assert "@2xl/setting:grid-cols-3" not in _MODELS


def test_the_reasoning_picker_lists_every_catalog_model_not_a_filtered_few():
    # Every role reads the same list, so claude-haiku-5-5 and gpt-6-luna are selectable for it.
    assert "options={info.model_options}" in _MODELS
    assert not re.search(r"model_options\.filter", _MODELS)
    catalog = (_FRONTEND.parent / "backend/app/services/model_settings.py").read_text()
    assert 'ModelOption("gpt-6-luna"' in catalog and 'ModelOption("claude-haiku-5-5"' in catalog


def test_the_reasoning_model_is_probed_and_warned_like_the_other_roles():
    role = _MODELS[_MODELS.index("function RoleModel(") :]
    assert "const model = info[role.key];" in role
    assert "keyWarning(role.label, model, info)" in role
