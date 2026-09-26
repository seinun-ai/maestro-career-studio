"""/sections — which profile list each repeating section holds, and how many of
its entries the profile can fill (fill-engine plan Task 7)."""

import pytest

from app.schemas.autofill_fill import PageSection, SectionsRequest
from app.services import autofill_catalog, autofill_sections, llm, model_settings
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA
from tests.test_autofill_choose_jev import _answer, jev_on  # noqa: F401  (fixture)
from tests.test_autofill_fill_router import _post, profile  # noqa: F401  (fixture)
from tests.test_autofill_router import _seed_base

FACTS = autofill_catalog.build(
    {"personal": {"website": "https://ada.dev", "github": "https://github.com/ada",
                  "linkedin": "https://linkedin.com/in/ada"},
     "education": [{"school": "State University", "degree": "MS"}, {"degree": "BS"}, {"school": "City College"}]},
    [{"employer": "Acme", "title": "Analyst", "start_date": "Aug 2021", "current": True},
     {"employer": "Initech", "title": "Intern"},
     {"employer": "Globex"}],  # no title: an entry the page would require it for
    ["Python"])
# Every value above that could reach a model if the catalog leaked.
VALUES = ("ada.dev", "github.com/ada", "linkedin", "State University", "City College", "Acme", "Analyst",
          "Initech", "Intern", "Globex", "Python")
HEADINGS = {"w": "Work Experience", "e": "Education", "s": "Websites", "l": "Languages",
            "c": "Certifications", "x": "Resume/CV"}


def sections(headings=HEADINGS):
    return [PageSection(sid=sid, heading=h, entries=1, filled=[False]) for sid, h in headings.items()]


def fake_jev(monkeypatch, kinds):
    calls = []

    def decide(questions, state, session=None):
        calls.append({"questions": questions, "state": state})
        return {sid: _answer(q["criteria"], *kinds.get(sid, ("none", 0.95))) for sid, q in questions.items()}

    monkeypatch.setattr(autofill_sections.jev, "decide", decide)
    return calls


def fake_llm(monkeypatch, answer):
    prompts = []

    def call_openai(**kw):
        prompts.append(kw)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(autofill_sections.llm, "call_openai", call_openai)
    return prompts


KINDS = {"w": ("experience", 0.9), "e": ("education", 0.9), "s": ("websites", 0.9), "l": ("languages", 0.9),
         "c": ("certifications", 0.9), "x": ("none", 0.9)}


@pytest.mark.usefixtures("jev_on")
def test_sections_maps_headings_to_profile_lists(db_session, monkeypatch):
    calls = fake_jev(monkeypatch, KINDS)
    got = autofill_sections.plan(sections(), FACTS, db_session)
    assert {sid: (p.kind, p.wanted) for sid, p in got.items()} == {
        # Two jobs have an employer AND a title; Globex has no title.
        "w": ("experience", 2),
        # Two schools; the BS entry names none.
        "e": ("education", 2),
        # A personal website and a GitHub profile; LinkedIn has its own box.
        "s": ("websites", 2),
        # No language or certification facts exist yet (languages: Task 10).
        "l": ("languages", 0), "c": ("certifications", 0),
        "x": ("none", 0),
    }
    [call] = calls
    assert set(call["questions"]) == set(HEADINGS)
    q = call["questions"]["w"]
    assert q["type"] == "choice"
    assert set(q["criteria"]) == {"experience", "education", "languages", "websites", "certifications", "none"}
    assert "Work Experience" in q["instructions"] and _PAGE_TEXT_IS_DATA in q["instructions"]


@pytest.mark.usefixtures("jev_on")
def test_the_model_sees_headings_and_counts_never_values(db_session, monkeypatch):
    calls = fake_jev(monkeypatch, KINDS)
    autofill_sections.plan(sections(), FACTS, db_session)
    blob = repr(calls)
    assert "Websites" in blob
    assert not [v for v in VALUES if v in blob]


@pytest.mark.usefixtures("jev_on")
def test_a_kind_below_the_floor_is_none(db_session, monkeypatch):
    fake_jev(monkeypatch, {"w": ("experience", 0.55)})
    got = autofill_sections.plan(sections({"w": "Work History"}), FACTS, db_session)
    assert (got["w"].kind, got["w"].wanted) == ("none", 0)


@pytest.mark.usefixtures("jev_on")
def test_a_refused_jev_answer_is_none(db_session, monkeypatch):
    monkeypatch.setattr(autofill_sections.jev, "decide", lambda *a, **k: {"w": {"choice": "experience"}})
    got = autofill_sections.plan(sections({"w": "Work Experience"}), FACTS, db_session)
    assert (got["w"].kind, got["w"].wanted) == ("none", 0)


@pytest.mark.usefixtures("jev_on")
def test_a_jev_failure_falls_back_to_the_fast_model_with_the_same_floor(db_session, monkeypatch):
    def down(*a, **k):
        raise llm.LLMProviderError("Jev could not be reached.")

    monkeypatch.setattr(autofill_sections.jev, "decide", down)
    prompts = fake_llm(monkeypatch, {"sections": {"w": {"key": "experience", "confidence": 0.9},
                                                  "e": {"key": "education", "confidence": 0.5},
                                                  "s": {"key": "cooking", "confidence": 0.99},
                                                  "zz": {"key": "education", "confidence": 0.99}}})
    got = autofill_sections.plan(sections({"w": "Work Experience", "e": "Education", "s": "Websites"}),
                                 FACTS, db_session)
    assert {sid: (p.kind, p.wanted) for sid, p in got.items()} == {
        "w": ("experience", 2), "e": ("none", 0), "s": ("none", 0)}
    [p] = prompts
    assert p["trace_name"] == "autofill-sections" and _PAGE_TEXT_IS_DATA in p["prompt"]
    assert not [v for v in VALUES if v in p["prompt"]]


def test_the_fast_engine_asks_only_the_fast_model(db_session, monkeypatch):
    model_settings.set_autofill_engine(db_session, "fast")
    monkeypatch.setattr(autofill_sections.jev, "decide", lambda *a, **k: pytest.fail("Jev was asked"))
    fake_llm(monkeypatch, {"sections": {"w": {"key": "experience", "confidence": 0.8}}})
    got = autofill_sections.plan(sections({"w": "Employment"}), FACTS, db_session)
    assert (got["w"].kind, got["w"].wanted) == ("experience", 2)


def test_unreadable_fast_json_is_every_section_none(db_session, monkeypatch):
    model_settings.set_autofill_engine(db_session, "fast")
    fake_llm(monkeypatch, ["not", "a", "map"])
    got = autofill_sections.plan(sections({"w": "Work Experience"}), FACTS, db_session)
    assert (got["w"].kind, got["w"].wanted) == ("none", 0)


def test_no_profile_entries_want_nothing():
    facts = autofill_catalog.build({"personal": {"linkedin": "https://linkedin.com/in/ada"}}, [], [])
    assert [autofill_sections.wanted(k, facts) for k in autofill_sections.KINDS] == [0] * 6


def test_the_request_carries_headings_and_counts_only():
    with pytest.raises(ValueError):
        SectionsRequest.model_validate({"sections": [{"sid": "f-s1", "heading": "Websites", "entries": 0,
                                                      "filled": [], "values": ["https://ada.dev"]}]})
    with pytest.raises(ValueError):
        SectionsRequest.model_validate({"sections": []})


# ---------- the route


@pytest.mark.usefixtures("profile")
def test_the_route_counts_from_the_selected_resume(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    seen = {}

    def plan(secs, facts, session):
        seen.update(facts=facts, sections=secs)
        return {s.sid: autofill_sections.SectionPlan(kind="experience", wanted=autofill_sections.wanted(
            "experience", facts)) for s in secs}

    monkeypatch.setattr(autofill_sections, "plan", plan)
    r = _post(db_session, "/api/autofill/sections",
              {"base": slug, "sections": [{"sid": "f-s1", "heading": "Work Experience", "entries": 1,
                                           "filled": [True]}]})
    assert r.status_code == 200
    got = r.json()["sections"]["f-s1"]
    assert got["kind"] == "experience" and got["wanted"] >= 1
    assert set(got) == {"kind", "wanted"}  # a kind and a count, never a value
    assert "experience.0.employer" in seen["facts"]


def test_the_route_404s_an_unknown_application(db_session):
    from uuid import uuid4

    r = _post(db_session, "/api/autofill/sections",
              {"application_id": str(uuid4()), "sections": [{"sid": "f-s1", "heading": "Education", "entries": 0}]})
    assert r.status_code == 404
