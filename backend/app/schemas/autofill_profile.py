from pydantic import BaseModel


class WorkAuth(BaseModel):
    """The two-part question US applications actually ask.

    `sponsorship_now` and `sponsorship_future` are separate because the form
    asks them separately and the answers legitimately differ — an OPT holder
    needs no sponsorship now and will need it later. The single timeless boolean
    this replaces could not express that, and answered one of the two questions
    wrongly every time.

    `status` is one of its market's own statuses (form_questions.yaml `statuses`,
    by the market's `work_status`): the typed reader
    (`autofill_profile.typed_work_auth`) keeps only a value of that list, so the
    type here is a string.

    All fields optional. An unknown answer must STAY unknown: the extension
    reports `missing_source` and the user is asked, which is always better than
    a confident guess on a knockout question.
    """

    status: str | None = None
    authorized_now: bool | None = None
    sponsorship_now: bool | None = None
    sponsorship_future: bool | None = None
    authorization_expires_on: str | None = None
    countries_authorized: list[str] = []


# Work-permit answers per country, keyed by MARKET ("UK", the market setting's key, not the ISO
# "GB"): `work_auth_by_country` in the autofill profile (services/autofill_profile,
# services/autofill_country). `countries_authorized` is derived from the keys whose
# `authorized_now` is Yes.
WorkAuthByCountry = dict[str, WorkAuth]
