"""MCP autofill feed: EEO values are consent-gated.

When Profile standing consent (eeo_consent.enabled) is on, profile.eeo is
returned so Playwright agents can fill exact stored answers. When consent is
off or missing, EEO answer values stay stripped. Consent metadata is always
normalized to the standing-consent shape only.
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
    assert "never prefer ATS-parsed" in doc.lower() or "never prefer ats-parsed" in doc.lower()


def test_get_autofill_profile_docstring_consent_gates_eeo_for_playwright():
    doc = (srv.get_autofill_profile.__doc__ or "").lower()
    assert "standing consent" in doc
    assert "playwright" in doc or "agent" in doc
    assert "infer" in doc or "inferred" in doc
    assert "paste" in doc or "re-dictate" in doc or "dictate" in doc
