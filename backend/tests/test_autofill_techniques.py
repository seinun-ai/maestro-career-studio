"""The technique cards: one short card per widget kind, never per site."""

import pytest

from app.schemas.autofill_fill import StepRequest
from app.services.autofill_techniques import CARDS

KINDS = {"popup", "search", "multi", "group", "select", "date"}


def test_every_widget_kind_has_a_card_and_only_those():
    assert set(CARDS) == KINDS
    for kind in KINDS:  # and the schema accepts each
        assert StepRequest(fid="f", question="Q", route="slot", kind=kind,
                           candidates=[{"mid": "open", "describe": "Open"}]).kind == kind


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_a_card_is_short_enough_for_a_prompt_that_runs_on_every_step(kind):
    assert 0 < len(CARDS[kind]) <= 700


def test_a_card_names_the_moves_that_exist_and_no_site():
    assert "search:term" in CARDS["search"] and "search:word:N" in CARDS["search"]
    assert "scroll" in CARDS["popup"] and "open" in CARDS["popup"]
    every = " ".join(CARDS.values()).lower()
    for site in ("workday", "greenhouse", "lever", "ashby", "icims"):
        assert site not in every
