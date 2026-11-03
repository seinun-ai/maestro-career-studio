"""The form-question catalog (data/form_questions.yaml) and the set resolved for one user.

Domain data, like markets.yaml: the questions Profile, Setup and setup readiness ask, in the words
they ask them. Loaded on first use, then cached, and validated; a malformed file fails that first
load, which a test makes (tests/test_form_questions.py), not a user's first Profile visit. The MCP
server's write schema (`mcp_server/server.py`: `CountryAnswers`, `CefrLevel`) reads it at import,
and the app imports that server at startup, so a broken file fails the app's boot.
"""

from collections.abc import Container
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.schemas.form_questions import (
    Catalog,
    CitizenshipRule,
    CountryQuestions,
    Field,
    Group,
    QuestionSet,
)
from app.services import markets

_FILE = Path(__file__).parent / "data" / "form_questions.yaml"


@cache
def catalog() -> Catalog:
    return Catalog.model_validate(yaml.safe_load(_FILE.read_text(encoding="utf-8")))


def _for_home(field: Field, home: str, chosen: bool) -> Field:
    """An address line resolved by where you live (`byHome`). The state line is named by the home's
    `state_label` and counted where its addresses need one (`asks_state`); the postal code keeps its
    label and is counted where they have one (`asks_postcode`). With no country chosen there is no
    address rule: the state line keeps its own label and is never required, and the postal code is
    the catalog's."""
    if field.byHome == "state":
        if not chosen:
            return field.model_copy(update={"optional": True})
        m = markets.get(home)
        return field.model_copy(
            update={"label": m["state_label"] or field.label, "optional": m["asks_state"] is False}
        )
    if field.byHome == "postcode" and chosen and markets.get(home)["asks_postcode"] is False:
        return field.model_copy(update={"optional": True})
    return field


def _shown(field: Field, packs: Container[str]) -> bool:
    """A field with no pack is asked everywhere; a pack's, only while `packs` names it."""
    return field.pack is None or field.pack in packs


def required_fields(fields: list[Field]) -> list[Field]:
    """The fields setup readiness counts: every field not `optional`."""
    return [f for f in fields if not f.optional]


def required_keys(fields: list[Field]) -> list[str]:
    """The keys of `required_fields`."""
    return [f.key for f in required_fields(fields)]


def _market(key: str | None) -> dict | None:
    """A supported market's data, or None: unlike `markets.get`, never the default market's, so
    an unknown market takes no country's statuses or answers."""
    return markets.get(key) if markets.is_supported(key) else None


def status_values(market: str | None) -> list[str]:
    """The `work_auth_by_country[market].status` values a market takes: its `work_status` list,
    in order; [] for a market with no list (the UK) or one Maestro does not keep."""
    m = _market(market)
    if not (m and m["work_status"]):
        return []
    return [o.value for o in catalog().statuses[m["work_status"]].options]


def all_status_values() -> set[str]:
    """Every market's status values together: what a status read for no market may be."""
    return {o.value for statuses in catalog().statuses.values() for o in statuses.options}


def answer_keys(market: str | None) -> list[str]:
    """The `answers_by_country[market]` keys a market takes, in catalog order: every country
    answer with no pack or a pack the market names (`current_ctc` in India only); [] for a market
    Maestro does not keep."""
    m = _market(market)
    return [f.key for f in catalog().answers if _shown(f, m["packs"])] if m else []


def answer_fills(market: str | None) -> dict[str, str]:
    """`answer_keys(market)`, each with the flat slot it fills on that country's jobs (`fills`,
    "preferences.desired_salary"), in catalog order; {} for a market Maestro does not keep."""
    keys = set(answer_keys(market))
    return {f.key: f.fills for f in catalog().answers if f.key in keys and f.fills}


def status_labels(market: str | None) -> dict[str, str]:
    """A market's statuses in its own words (`work_status` list: value to label); {} for a market
    with no list or one Maestro does not keep."""
    m = _market(market)
    if not (m and m["work_status"]):
        return {}
    return {o.value: o.label for o in catalog().statuses[m["work_status"]].options}


@cache
def _by_slot() -> dict[str, list[Field]]:
    """Every catalog field under the fill slot it answers, unindexed: a group field as
    `section.key`, a country answer as its `fills`, a language field as `languages.key`. A slot may
    have two (`expected_pay` fills `preferences.desired_salary`): the group's comes first."""
    cat = catalog()
    out: dict[str, list[Field]] = {}
    pairs = [
        *((f"{g.key}.{f.key}", f) for g in cat.groups for f in g.fields),
        *((f.fills, f) for f in cat.answers if f.fills),
        *((f"languages.{f.key}", f) for f in cat.language_fields),
    ]
    for slot, f in pairs:
        out.setdefault(slot, []).append(f)
    return out


def describe_for(slot: str) -> str | None:
    """What the fill loop reads for the answer in `slot` (unindexed, "languages.cefr"), as the
    catalog words it (`describe`), or None where it says nothing (the fill's own rule)."""
    return next((f.describe for f in _by_slot().get(slot, ()) if f.describe), None)


def policy_for(slot: str) -> str | None:
    """How strictly a picked option must match the answer in `slot` (unindexed), as the catalog
    sets it (`policy`), or None where it sets none (the slot's section decides)."""
    return next((f.policy for f in _by_slot().get(slot, ()) if f.policy), None)


def citizenship_rule(code: str, market: str) -> CitizenshipRule | None:
    """The rule under which a citizen of `code` (ISO, "GB") may work in `market` (a market key,
    "UK") with no permit, or None: their own country's, else the first `citizenship` rule that
    lists both. The own-country rule settles `citizen`, where the market's status list has it."""
    if code == markets.country_code(market):
        return CitizenshipRule(citizens=[code], markets=[market], status="citizen", source="own country")
    cit = catalog().citizenship
    return next((r for r in cit.rules if code in cit.members(r) and market in r.markets), None)


_EXPIRY = "authorization_expires_on"


def _permits(m: dict[str, Any]) -> list[Field]:
    """A market's work-permit questions: its status question first when it has a status list
    (`work_status`), in that list's words, then its wording's knockout questions and the expiry,
    which is hidden while the status is one that never runs out (`noExpiry`). New lists and copies
    only: the catalog's are shared."""
    cat = catalog()
    wording = cat.permits[m["work_auth_vocab"]]
    statuses = cat.statuses[m["work_status"]] if m["work_status"] else None
    if statuses is None:
        return list(wording)
    status = Field(
        key="status",
        label=statuses.label,
        type="select",
        options=list(statuses.options),
        optional=not statuses.required,
    )
    lasting = [o.value for o in statuses.options if o.noExpiry]
    return [
        status,
        *(
            f.model_copy(update={"unless": ("status", lasting)}) if f.key == _EXPIRY and lasting else f
            for f in wording
        ),
    ]


def _answers(m: dict[str, Any], home: bool) -> list[Field]:
    """A market's own answers (those of its packs), expected pay in its own words (`pay`). The
    home's pay is `preferences.desired_salary`, the figure readiness has always counted, so it is
    required; every other country's stays optional."""
    pay = m["pay"]
    return [
        f.model_copy(
            update={
                "label": pay["label"],
                "hint": pay["hint"] or f.hint,
                "optional": f.optional and not home,
            }
        )
        if f.key == "expected_pay"
        else f
        for f in catalog().answers
        if _shown(f, m["packs"])
    ]


def _country(market: str, profile: Any, *, home: bool) -> CountryQuestions:
    from app.services import autofill_derive  # it reads this module: imported here, not above

    m = markets.get(market)
    return CountryQuestions(
        market=market,
        label=m["label"],
        home=home,
        permits=_permits(m),
        answers=_answers(m, home),
        derived=autofill_derive.derived_in_effect(profile, market),
    )


def resolve(*, home: str, apply_in: list[str], chosen: bool, profile: Any) -> QuestionSet:
    """The questions for someone who lives in `home` and applies in `apply_in`. Callers pass a
    validated `MarketSetting`'s `home`, `apply_in` and `chosen` (upper-cased market keys); an
    unknown key falls back to the default market's (US) wording, as `markets.get` does. Empty
    `apply_in` reads as `[home]`, the setting's own rule.

    - Facts about you (`groups`) are asked once: a pack's field while any apply-in country names
      the pack, saying whose forms ask it (`askedBy`), the address lines resolved for `home`.
    - Each apply-in country (`countries`, in order) gets its permits, its own answers, and the
      permit answers a citizenship in `profile` (the user's form answers, a read view; None for
      none) settles there, unless a given answer differs (`autofill_derive.derived_in_effect`).
      None of a country's own fields says who asks it: its set is under its name.
    - The country you live in, when you apply in it, is marked `home`, and its pay is asked there,
      required: it is the desired salary, so Start and pay no longer asks it (`_start_and_pay`).
    - `language_fields` are the fields on each language that a country's pack asks (CEFR), saying
      whose forms ask them.

    `chosen` and `profile` have no default, so a caller that forgets one fails rather than getting
    a country's set, or every country's with nothing derived.
    Unchosen (`MarketSetting.chosen` false) is the generic set: no country is applied in, so no
    pack, no country questions (a permit answer belongs to a country), no diversity set, and the
    state line is optional."""
    apply_in = (apply_in or [home]) if chosen else []
    asked_by = _asked_by(apply_in)
    return QuestionSet(
        groups=_groups(home, chosen, apply_in, asked_by),
        countries=[_country(m, profile, home=m == home) for m in apply_in],
        language_fields=[
            _marked(f, asked_by) for f in catalog().language_fields if _shown(f, asked_by)
        ],
        offers_eeo=any(markets.offers_eeo(m) for m in apply_in),
        chosen=chosen,
    )


def _groups(
    home: str, chosen: bool, apply_in: list[str], asked_by: dict[str, str]
) -> list[Group]:
    """The facts about you, each asked once: a pack's field while a country you apply in names it
    (`asked_by`), saying whose forms ask it, the address lines resolved for `home` (`_for_home`),
    and the desired salary where Start and pay still asks it (`_start_and_pay`)."""
    out = []
    for g in catalog().groups:
        shown = [_for_home(f, home, chosen) for f in g.fields if _shown(f, asked_by)]
        asked = (_start_and_pay(f, home, chosen, apply_in) for f in shown)
        fields = [_marked(f, asked_by) for f in asked if f]
        out.append(Group(key=g.key, title=g.title, fields=fields))
    return out


_HOME_PAY = "desired_salary"
_HOME_PAY_ABROAD_HINT = "For jobs whose country Maestro can't tell."


def _start_and_pay(field: Field, home: str, chosen: bool, apply_in: list[str]) -> Field | None:
    """The desired salary is the home country's pay. With no country chosen it is the one figure,
    asked as always. Once the home is a country you apply in, that country's set asks it
    (`_answers`), so Start and pay does not. A home you don't apply in has no set, and the figure is
    read only for a job whose country can't be told: still asked here, optional, saying so."""
    if field.key != _HOME_PAY or not chosen:
        return field
    if home in apply_in:
        return None
    return field.model_copy(update={"optional": True, "hint": _HOME_PAY_ABROAD_HINT})


def _asked_by(apply_in: list[str]) -> dict[str, str]:
    """Each pack a country you apply in names, with the sentence that says whose forms ask its
    questions: those countries, in apply-in order, as a sentence names them (markets.yaml
    `in_text`), so "the Netherlands" needs no article rule here or in the frontend."""
    names: dict[str, list[str]] = {}
    for market in apply_in:
        m = markets.get(market)
        for pack in m["packs"]:
            names.setdefault(pack, []).append(m["in_text"])
    return {pack: f"Asked by forms in {_joined(countries)}." for pack, countries in names.items()}


def _joined(names: list[str]) -> str:
    """Names as a list reads them: "A", "A and B", "A, B and C"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _marked(field: Field, asked_by: dict[str, str]) -> Field:
    """A pack's field with the sentence naming whose forms ask it; any other field as it is."""
    return field.model_copy(update={"askedBy": asked_by[field.pack]}) if field.pack else field
