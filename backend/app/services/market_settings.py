"""Where the user lives and applies (`MarketSetting`): storage, plus the rules that read it."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.setting import Setting
from app.schemas.market_settings import MarketSetting
from app.schemas.money import MoneySettings
from app.services import countries, markets, text_settings
from app.services.json_settings import JsonSetting


class _Market(JsonSetting[MarketSetting]):
    def migrate(self, payload: Any) -> Any:
        # Stored before the mark (2026-10-30): that install kept the set it was shown. A row never
        # stored (`""`, also what `text_settings.get_text` seeds with no mirror) never reaches here:
        # it reads as `MarketSetting()`, unchosen, unless its permit answers say otherwise at
        # startup (`mark_answered_installs_chosen`). A corrupt stored row also reads as unchosen
        # (`parse`'s defaults) and is not repaired: its text is not empty.
        if isinstance(payload, dict) and "chosen" not in payload:
            return {**payload, "chosen": True}
        return payload

    def is_set(self, value: MarketSetting) -> bool:
        # The mark decides the form questions, never currency or dates: compared without it.
        return value.model_copy(update={"chosen": False}) != MarketSetting()


MARKET = _Market("market", "market.json", MarketSetting)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
MARKET_KEY = MARKET.key
MARKET_FILE = MARKET.filename
# This install has had its one startup check (`mark_answered_installs_chosen`). A local setting
# (`sync/registry.LOCAL_SETTING_PREFIXES`), never synced: the laptop checks its own answers once, and
# the always-on copy never checks (its row arrives from the laptop).
CHOSEN_CHECKED_FLAG = "market.chosen_checked"


def get_market(session: Session | None = None) -> MarketSetting:
    return MARKET.get(session)


def peek_market(session: Session | None = None) -> MarketSetting:
    """Non-mutating read — must not lazy-seed a Setting row or file mirror.

    `setup_status` reads through this, and a status request that writes would
    make the derived-not-stored contract a lie (SYSTEM.md §4 Setup status).
    """
    return MARKET.peek(session)


def mark_answered_installs_chosen(session: Session) -> bool:
    """Startup, once per install: a market never stored (empty text, row or mirror) on an install
    whose form answers hold a work-permit answer for the default country is stored as chosen, `home`
    and `apply_in` as an empty row reads them (the `MarketSetting()` defaults). An empty row means the
    picker was never changed, so that user has been answering for the default country: they chose it.
    The evidence is that they answered, never what they answered: no knockout answer is guessed. Only
    the default country's answers count (its `work_auth_by_country` entry and a legacy one-set
    `work_auth`): an answer for another country, which an agent or the Companion can store, is no
    choice of the default. An install with no such answer stays unchosen (Decision 1 of
    docs/plans/2026-10-30-country-form-questions.md).

    Once: `CHOSEN_CHECKED_FLAG` is set by the first run whatever it found, so a new install that
    answers later, still unchosen, is never marked at a later restart. A startup step, not a read-time
    rule: the form answers read the market for their home, so a market read that read them back would
    recurse. A stored market, an unchosen one included, is never rewritten. Both settings are peeked,
    never seeded. The always-on copy skips it: the laptop owns the profile, and its row arrives by
    sync. Returns whether it wrote the market."""
    from app.services import autofill_profile
    from app.services.sync import status

    if status.is_remote() or session.get(Setting, CHOSEN_CHECKED_FLAG) is not None:
        return False
    answered = not text_settings.peek_text(MARKET_KEY, MARKET_FILE, session).strip() and (
        autofill_profile.holds_work_permit_answer(MarketSetting().home, session)
    )
    session.add(Setting(key=CHOSEN_CHECKED_FLAG, value="1"))
    if answered:
        MARKET.set(MarketSetting(chosen=True), session)  # commits the flag with it
    else:
        session.commit()
    return answered


def set_market(setting: MarketSetting, session: Session | None = None) -> MarketSetting:
    """Store where you live and apply, marked `chosen`: every caller is the user's save (the PUT) or an
    agent's (`patch_place`). A move of `home` first pins a legacy one-set work-permit answer to the
    home it has been read as (`autofill_profile.pin_legacy_work_auth`), and, when the stored home
    was chosen, its pay to it (`autofill_profile.pin_home_pay`; unchosen, the one figure is the
    first home's to adopt), in the same session. The pins first, because on their own they change
    no read: a refusal or a failure before the move lands leaves both settings meaning what they
    meant."""
    from app.db import SessionLocal
    from app.services import autofill_profile

    owns_session = session is None
    session = session or SessionLocal()
    try:
        stored = peek_market(session)
        if setting.home != stored.home:
            autofill_profile.pin_legacy_work_auth(stored.home, session)
            if stored.chosen:
                autofill_profile.pin_home_pay(stored.home, session)
        return MARKET.set(setting.model_copy(update={"chosen": True}), session)
    finally:
        if owns_session:
            session.close()


# What an agent's save of where the user lives takes (`PATCH /api/settings/market`, MCP `set_markets`):
# the market setting's two fields and the money setting's currency, no other money field.
AGENT_FIELDS = frozenset({"home", "apply_in", "home_currency"})


def patch_place(changes: dict[str, Any], session: Session) -> MarketSetting:
    """An agent's save of where the user lives and applies, and of the currency pay reads in, as one
    transaction (`text_settings.one_commit`): `home` alone keeps `apply_in` as stored and the reverse,
    a None field is left as stored (an unchosen `apply_in` is the default, not a choice, so `home`
    alone then applies where you live), and `home_currency` changes only the money setting's currency
    ("" follows home again; every other money field stays). Both settings are validated before
    either is written (their own ValidationError, the words their PUTs use), so nothing lands unless
    everything does. No field: nothing is written. Returns the market setting as stored."""
    from app.services import money_settings

    refused = sorted(set(changes) - AGENT_FIELDS)
    if refused:
        raise ValueError(
            f"Not written by an agent's save: {', '.join(refused)}. The fields are "
            f"{', '.join(sorted(AGENT_FIELDS))}."
        )
    home, apply_in, currency = (changes.get(k) for k in ("home", "apply_in", "home_currency"))
    if home is None and apply_in is None and currency is None:
        return peek_market(session)
    with text_settings.one_commit(session):
        stored = peek_market(session)
        place = None
        if home is not None or apply_in is not None:
            kept_apply_in = stored.apply_in if stored.chosen else []
            place = MarketSetting.model_validate({
                "home": stored.home if home is None else home,
                "apply_in": kept_apply_in if apply_in is None else apply_in,
            })
        money = None
        if currency is not None:
            money = MoneySettings.model_validate(
                {**money_settings.peek_settings(session).model_dump(), "home_currency": currency or None}
            )
        if place is not None:
            set_market(place, session)
        if money is not None:
            money_settings.set_settings(money, session)
        saved = peek_market(session)
    return saved


def is_set(setting: MarketSetting) -> bool:
    """Whether the stored market differs from the default, for currency.

    A stored value equal to the default is indistinguishable from never having
    chosen, which is deliberate: both mean "no explicit opinion", and both
    should let HOME_CURRENCY answer for currency purposes. The `chosen` mark is
    ignored: it decides the form questions, never currency or dates.
    """
    return MARKET.is_set(setting)


def home_market_currency(session: Session | None = None) -> str:
    """The currency of where the user lives: the chosen home market's, else `HOME_CURRENCY`.

    Uses a NON-MUTATING read (capture runs it inside its transaction, and the seeding read would
    write a Setting row mid-capture). The market setting is user-chosen and visible in the UI; the
    env var is deployment config. With no market chosen yet (a stored value equal to the default
    counts as none), the env var still answers, so behaviour is unchanged until the user opts in.
    One source per answer, never both.
    """
    stored = peek_market(session)
    if is_set(stored):
        return markets.currency_for(stored.home)
    from app.config import settings

    return settings.home_currency


def default_currency_for_capture(
    session: Session | None = None, job_country_code: str | None = None
) -> str:
    """ISO 4217 default stamped on a newly captured job that states an amount but no currency.

    The job's own country first (`countries.currency`, data: a German job is posted in euros
    wherever the user lives), else the home currency (`home_market_currency`). Either way it is an
    assumption, and the caller marks it `salary_currency_assumed`.
    """
    return countries.currency(job_country_code) or home_market_currency(session)

