"""The served form-question sets the frontend's render tests seed (components/render-harness.mjs
`servedQuestions`): one file per scenario in tests/fixtures/served_questions/, each exactly what
GET /api/settings/autofill/questions serves for it (`form_questions.resolve`, dumped as the route
dumps it). A catalog change that alters one fails here. To regenerate, from backend/:

    MAESTRO_SERVED_QUESTIONS_WRITE=1 .venv/bin/python -m pytest tests/test_served_questions_fixtures.py

then rerun without the variable and commit the files. A render test that needs another scenario
adds it to SCENARIOS and regenerates.
"""

import json
import os
from pathlib import Path

import pytest

from app.config import settings
from app.services import form_questions

FIXTURES = Path(__file__).parent / "fixtures" / "served_questions"
REGENERATE = (
    "regenerate from backend/ with MAESTRO_SERVED_QUESTIONS_WRITE=1 .venv/bin/python -m pytest "
    "tests/test_served_questions_fixtures.py, rerun without it, and commit the files"
)

# (where you live, where you apply): the countries components/profile/profile-view.test.mjs and
# components/setup/setup-flow.test.mjs render.
SCENARIOS: list[tuple[str, list[str]]] = [
    ("DE", ["DE"]),
    ("DE", ["DE", "UK"]),
    ("DE", ["DE", "UK", "US"]),
    ("DE", ["UK"]),
    ("DE", ["US"]),
]


def fixture_name(home: str, apply_in: list[str]) -> str:
    """The harness builds the same name (render-harness.mjs `servedQuestions`)."""
    return f"lives-{home}_applies-{'-'.join(apply_in)}.json"


def served(home: str, apply_in: list[str]) -> dict:
    """The set as the route serves it: `response_model_exclude_defaults=True`, as JSON."""
    resolved = form_questions.resolve(home=home, apply_in=apply_in, chosen=True)
    return resolved.model_dump(mode="json", exclude_defaults=True)


def _dump(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def test_each_fixture_is_what_the_route_serves():
    names = {fixture_name(home, apply_in): (home, apply_in) for home, apply_in in SCENARIOS}
    if os.environ.get("MAESTRO_SERVED_QUESTIONS_WRITE") == "1":
        FIXTURES.mkdir(exist_ok=True)
        for stale in FIXTURES.glob("*.json"):
            if stale.name not in names:
                stale.unlink()
        for name, (home, apply_in) in names.items():
            (FIXTURES / name).write_text(_dump(served(home, apply_in)), encoding="utf-8")
        pytest.fail("fixtures written; rerun without the variable", pytrace=False)
    on_disk = {path.name for path in FIXTURES.glob("*.json")}
    assert on_disk == set(names), f"the fixtures are not SCENARIOS' files: {REGENERATE}"
    differing = [
        name
        for name, (home, apply_in) in names.items()
        if json.loads((FIXTURES / name).read_text(encoding="utf-8")) != served(home, apply_in)
    ]
    assert not differing, f"{differing} differ from form_questions.resolve: {REGENERATE}"


def test_the_dump_is_the_routes_own(client, tmp_path, monkeypatch):
    """`served` serializes as GET /api/settings/autofill/questions does, so a fixture is its body."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)  # the market's file mirror (SYSTEM.md §12)
    home, apply_in = "DE", ["DE", "UK", "US"]
    assert (home, apply_in) in SCENARIOS
    saved = client.put("/api/settings/market", json={"value": {"home": home, "apply_in": apply_in}})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/settings/autofill/questions").json() == served(home, apply_in)
