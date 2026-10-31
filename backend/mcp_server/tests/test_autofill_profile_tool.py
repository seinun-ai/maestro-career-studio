"""MCP autofill feed: EEO values are consent-gated.

When Profile standing consent (eeo_consent.enabled) is on, profile.eeo is
returned so Playwright agents can fill exact stored answers. When consent is
off or missing, EEO answer values stay stripped. Consent metadata is always
normalized to the standing-consent shape only. `questions` says what each country the user
applies in asks (GET /api/settings/autofill/questions, made compact).
"""

from mcp_server import server as srv


def test_get_autofill_profile_includes_eeo_when_consent_enabled(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "_request",
        lambda method, path, params=None, **kw: {
            "profile": {
                "personal": {"first_name": "A", "city": "Springfield"},
                "eeo": {"gender": "male", "race_ethnicity": ["asian"]},
                "work_auth": {"authorized": True},
            },
            "employment": None,
            "skills": ["Python"],
            "eeo_consent": {
                "enabled": True,
                "acknowledged_at": "2026-07-30T12:00:00+00:00",
                "policy_version": "1",
            },
        },
    )
    ctx = srv.get_autofill_profile()
    assert ctx["profile"]["eeo"] == {"gender": "male", "race_ethnicity": ["asian"]}
    assert ctx["profile"]["personal"]["city"] == "Springfield"
    assert ctx["skills"] == ["Python"]
    assert ctx["eeo_consent"] == {
        "enabled": True,
        "acknowledged_at": "2026-07-30T12:00:00+00:00",
        "policy_version": "1",
    }
    assert "gender" not in ctx["eeo_consent"]


def test_get_autofill_profile_strips_eeo_when_consent_disabled(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "_request",
        lambda method, path, params=None, **kw: {
            "profile": {
                "personal": {"first_name": "A", "city": "Springfield"},
                "eeo": {"gender": "x", "race": "y"},
                "work_auth": {"authorized": True},
            },
            "employment": None,
            "skills": ["Python"],
            "eeo_consent": {
                "enabled": False,
                "acknowledged_at": None,
                "policy_version": "1",
            },
        },
    )
    ctx = srv.get_autofill_profile()
    assert "eeo" not in ctx["profile"]
    assert ctx["eeo_consent"]["enabled"] is False


def test_get_autofill_profile_strips_eeo_when_consent_missing(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "_request",
        lambda method, path, params=None, **kw: {
            "profile": {
                "personal": {"first_name": "A"},
                "eeo": {"gender": "x"},
            },
            "employment": None,
            "skills": [],
        },
    )
    ctx = srv.get_autofill_profile()
    assert "eeo" not in ctx["profile"]


def test_get_autofill_profile_adds_source_and_canonical_identity(monkeypatch):
    monkeypatch.setattr(
        srv._client,
        "_request",
        lambda method, path, params=None, **kw: {
            "profile": {
                "personal": {
                    "first_name": "Sample",
                    "last_name": "Applicant",
                    "preferred_name": "Sam",
                    "email": "a@example.com",
                },
                "eeo": {"gender": "x"},
                "work_auth": {"authorized_now": True},
            },
            "employment": None,
            "skills": ["Python"],
            "eeo_consent": {"enabled": False, "policy_version": "1"},
        },
    )
    ctx = srv.get_autofill_profile()

    assert ctx["source"] == "profile"
    assert ctx["canonical_identity"] == {
        "legal_first": "Sample",
        "legal_last": "Applicant",
        "preferred": "Sam",
    }
    assert "eeo" not in ctx["profile"]
    assert ctx["profile"]["personal"]["first_name"] == "Sample"


def test_canonical_identity_uses_profile_personal_only(monkeypatch):
    """Identity comes from personal.* keys — never invented from other namespaces."""
    monkeypatch.setattr(
        srv._client,
        "_request",
        lambda method, path, params=None, **kw: {
            "profile": {
                "personal": {"first_name": "LegalFirst", "last_name": "LegalLast"},
                "eeo": {"gender": "ignored"},
            },
            "employment": [{"company": "Acme", "title": "Engineer"}],
            "skills": [],
            "eeo_consent": {"enabled": True, "policy_version": "1"},
        },
    )
    ctx = srv.get_autofill_profile()
    assert ctx["source"] == "profile"
    assert ctx["canonical_identity"]["legal_first"] == "LegalFirst"
    assert ctx["canonical_identity"]["legal_last"] == "LegalLast"
    assert ctx["canonical_identity"]["preferred"] is None
    # Consent on: eeo retained; identity still only from personal.
    assert ctx["profile"]["eeo"] == {"gender": "ignored"}


def test_tool_is_registered():
    assert "get_autofill_profile" in srv.list_registered_tool_names()


def test_get_autofill_profile_docstring_names_profile_as_identity_source():
    doc = srv.get_autofill_profile.__doc__ or ""
    assert "canonical_identity" in doc
    assert "takes precedence over ats-parsed" in doc.lower()


def test_get_autofill_profile_docstring_consent_gates_eeo_for_playwright():
    doc = (srv.get_autofill_profile.__doc__ or "").lower()
    assert "standing consent" in doc
    assert "playwright" in doc or "agent" in doc
    assert "infer" in doc or "inferred" in doc
    assert "paste" in doc or "re-dictate" in doc or "dictate" in doc


# ---------- what each country asks, and the job's view ----------

def _feed(monkeypatch, *, context, questions):
    """`_request` answering each of the two reads; `questions` an exception raises it."""
    def request(method, path, params=None, **kw):
        if path == "/api/autofill/context":
            return context
        assert path == "/api/settings/autofill/questions", path
        if isinstance(questions, Exception):
            raise questions
        return questions

    monkeypatch.setattr(srv._client, "_request", request)


def _served_set(apply_in, citizenships):
    """The set GET /api/settings/autofill/questions serves, from the real resolver and as served."""
    from app.services import form_questions

    resolved = form_questions.resolve(home="IN", apply_in=apply_in, chosen=bool(apply_in),
                                      profile={"personal": {"citizenships": citizenships}})
    return resolved.model_dump(mode="json", exclude_defaults=True)


def test_questions_name_each_markets_permits_answers_and_what_a_citizenship_settles(monkeypatch):
    from app.services import form_questions

    _feed(monkeypatch, context={"profile": {}, "eeo_consent": None},
          questions=_served_set(["AE", "DE"], ["FR"]))
    questions = srv.get_autofill_profile()["questions"]

    assert questions["chosen"] is True
    assert list(questions["countries"]) == ["AE", "DE"]
    germany = questions["countries"]["DE"]
    assert germany["permits"] == {
        "authorized_now": [True, False], "sponsorship_now": [True, False],
        "sponsorship_future": [True, False], "authorization_expires_on": "date"}
    # The pay answer in Germany's own words: what an agent saves there is a gross annual figure.
    assert germany["answers"] == {"expected_pay": "Expected gross annual salary (EUR)"}
    assert germany["derived"]["authorized_now"] == {"value": True, "via": "FR"}
    uae = questions["countries"]["AE"]
    assert uae["permits"]["status"] == form_questions.status_values("AE")
    assert set(uae["answers"]) == set(form_questions.answer_keys("AE"))
    assert "monthly" in uae["answers"]["expected_pay"]
    assert uae["derived"] == {}


def test_with_no_country_chosen_questions_say_so_and_ask_no_country(monkeypatch):
    _feed(monkeypatch, context={"profile": {}}, questions=_served_set([], []))
    assert srv.get_autofill_profile()["questions"] == {"chosen": False, "countries": {}}


def test_a_failed_questions_read_still_returns_the_profile(monkeypatch):
    from mcp_server.client import BackendError

    _feed(monkeypatch, context={"profile": {"personal": {"first_name": "A"}}},
          questions=BackendError("Backend returned 500: boom", status_code=500))
    ctx = srv.get_autofill_profile()
    assert ctx["questions"] is None
    assert ctx["profile"]["personal"] == {"first_name": "A"}


async def test_the_tool_says_how_citizenships_and_the_jobs_view_read():
    """`/context` serves citizenships as country names; a write takes either. With an application the
    profile is one job's view, its folded slots named by country_answered; without one, every market's own
    answers come under answers_by_country."""
    tool = next(t for t in await srv.mcp.list_tools() if t.name == "get_autofill_profile")
    doc = " ".join((tool.description or "").split())
    assert "`personal.citizenships` as country names" in doc
    assert "`questions` (`chosen`" in doc
    assert "current pay only while the user lets the Companion fill agreements" in doc
    application = tool.input_schema["properties"]["application_id"]["description"]
    for words in ("country_answered", "answers_by_country holds each market's own answers",
                  "not preferences"):
        assert words in application, words
    write = next(t for t in await srv.mcp.list_tools() if t.name == "set_autofill_profile")
    personal = write.input_schema["$defs"]["PersonalAnswers"]["description"]
    assert 'ISO codes ("IN") or English names' in personal and "shows names" in personal
