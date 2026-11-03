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
from typing import NamedTuple

import pytest

from app.config import settings
from app.services import form_questions

FIXTURES = Path(__file__).parent / "fixtures" / "served_questions"
REGENERATE = (
    "regenerate from backend/ with MAESTRO_SERVED_QUESTIONS_WRITE=1 .venv/bin/python -m pytest "
    "tests/test_served_questions_fixtures.py, rerun without it, and commit the files"
)

class Scenario(NamedTuple):
    home: str  # where you live
    apply_in: list[str]  # where you apply
    citizenships: tuple[str, ...] = ()  # the stored `personal.citizenships`
    chosen: bool = True  # unchosen: the generic set, the same wherever you live


# The countries components/profile/profile-view.test.mjs and components/setup/setup-flow.test.mjs
# render, the country questions' cases (Task 3.5 of
# docs/plans/2026-10-30-country-form-questions.md), and a US home applying in India and Ireland,
# whose pay is asked in its own set (docs/plans/2026-11-02-start-and-pay.md).
SCENARIOS: list[Scenario] = [
    Scenario("US", ["US", "IN", "IE"]),
    Scenario("DE", ["DE"]),
    Scenario("DE", ["DE", "UK"]),
    Scenario("DE", ["DE", "UK", "US"]),
    Scenario("DE", ["UK"]),
    Scenario("DE", ["US"]),
    Scenario("IN", ["IN", "AE", "DE", "NL"], ("IN",)),
    Scenario("AE", ["AE"]),
    Scenario("US", [], chosen=False),
]


def fixture_name(scenario: Scenario) -> str:
    """The harness builds the same name (render-harness.mjs `servedQuestions`): unchosen is
    `lives-none` (where you live changes nothing), and citizenships are named when there are any."""
    name = f"lives-{scenario.home}_applies-{'-'.join(scenario.apply_in)}" if scenario.chosen else "lives-none"
    if scenario.citizenships:
        name += f"_citizen-{'-'.join(scenario.citizenships)}"
    return f"{name}.json"


def served(scenario: Scenario) -> dict:
    """The set as the route serves it: `response_model_exclude_defaults=True`, as JSON, for form
    answers that hold only the scenario's citizenships."""
    resolved = form_questions.resolve(
        home=scenario.home,
        apply_in=scenario.apply_in,
        chosen=scenario.chosen,
        profile={"personal": {"citizenships": list(scenario.citizenships)}},
    )
    return resolved.model_dump(mode="json", exclude_defaults=True)


def _dump(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def test_each_fixture_is_what_the_route_serves():
    names = {fixture_name(scenario): scenario for scenario in SCENARIOS}
    assert len(names) == len(SCENARIOS), "two scenarios share a fixture name"
    if os.environ.get("MAESTRO_SERVED_QUESTIONS_WRITE") == "1":
        FIXTURES.mkdir(exist_ok=True)
        for stale in FIXTURES.glob("*.json"):
            if stale.name not in names:
                stale.unlink()
        for name, scenario in names.items():
            (FIXTURES / name).write_text(_dump(served(scenario)), encoding="utf-8")
        pytest.fail("fixtures written; rerun without the variable", pytrace=False)
    on_disk = {path.name for path in FIXTURES.glob("*.json")}
    assert on_disk == set(names), f"the fixtures are not SCENARIOS' files: {REGENERATE}"
    differing = [
        name
        for name, scenario in names.items()
        if json.loads((FIXTURES / name).read_text(encoding="utf-8")) != served(scenario)
    ]
    assert not differing, f"{differing} differ from form_questions.resolve: {REGENERATE}"


@pytest.mark.parametrize(
    "scenario",
    [Scenario("DE", ["DE", "UK", "US"]), Scenario("IN", ["IN", "AE", "DE", "NL"], ("IN",))],
    ids=fixture_name,
)
def test_the_dump_is_the_routes_own(client, tmp_path, monkeypatch, scenario):
    """`served` serializes as GET /api/settings/autofill/questions does, so a fixture is its body;
    the route reads the citizenships from the stored form answers."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)  # the settings' file mirrors (SYSTEM.md §12)
    assert scenario in SCENARIOS
    market = {"home": scenario.home, "apply_in": scenario.apply_in}
    saved = client.put("/api/settings/market", json={"value": market})
    assert saved.status_code == 200, saved.text
    citizenships = {"personal": {"citizenships": list(scenario.citizenships)}}
    saved = client.put("/api/settings/autofill", json={"value": citizenships})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/settings/autofill/questions").json() == served(scenario)


def test_unchosen_is_the_routes_own(client, tmp_path, monkeypatch):
    """Nothing stored: the route serves the generic set, `lives-none`."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    assert Scenario("US", [], chosen=False) in SCENARIOS
    assert client.get("/api/settings/autofill/questions").json() == served(Scenario("US", [], chosen=False))
