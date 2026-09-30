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
     "education": [{"school": "State University", "degree": "MS"}, {"degree": "BS"}, {"school": "City College"}],
     "languages": [{"language": "Spanish", "read": "Fluent"}, {"read": "Basic"}]},
    [{"employer": "Acme", "title": "Analyst", "start_date": "Aug 2021", "current": True},
     {"employer": "Initech", "title": "Intern"},
     {"employer": "Globex"}],  # no title: an entry the page would require it for
    ["Python"])
# Every value above that could reach a model if the catalog leaked.
VALUES = ("ada.dev", "github.com/ada", "linkedin", "State University", "City College", "Acme", "Analyst",
          "Initech", "Intern", "Globex", "Python", "Spanish", "Fluent")
HEADINGS = {"w": "Work Experience", "e": "Education", "s": "Websites", "l": "Languages",
            "c": "Certifications", "x": "Resume/CV"}


def sections(headings=HEADINGS):
    return [PageSection(sid=sid, heading=h, entries=1, filled=[False], held=[[]]) for sid, h in headings.items()]


def held_section(sid, heading, *held):
    """A section whose entries hold these committed values (one list per entry)."""
    return PageSection(sid=sid, heading=heading, entries=len(held), filled=[bool(h) for h in held],
                       held=[list(h) for h in held])


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
        # The page's entry takes State University; the BS entry names no
        # school (an added entry would leave its required School empty), so
        # the Add brings City College, past it.
        "e": ("education", 2),
        # A personal website and a GitHub profile; LinkedIn has its own box.
        "s": ("websites", 2),
        # The page's entry takes Spanish; the entry naming no language is
        # not a language. No certification facts exist.
        "l": ("languages", 1), "c": ("certifications", 0),
        "x": ("none", 0),
    }
    # Jobs, schools, languages and websites are placed entry by entry (the
    # page's one entry, then the one to add); other lists name no entry.
    assert {sid: p.order for sid, p in got.items()} == {
        "w": [0, 1], "e": [0, 2], "s": [0, 1], "l": [0], "c": None, "x": None}
    [call] = calls
    assert set(call["questions"]) == set(HEADINGS)
    q = call["questions"]["w"]
    assert q["type"] == "choice"
    assert set(q["criteria"]) == {"experience", "education", "languages", "websites", "certifications", "none"}
    assert "Work Experience" in q["instructions"] and _PAGE_TEXT_IS_DATA in q["instructions"]


HELD = ("Initech Inc.", "Intern", "2020-01", "held-secret-value")


@pytest.mark.usefixtures("jev_on")
def test_the_model_sees_headings_and_counts_never_values(db_session, monkeypatch):
    """Neither the profile's values nor what the page's entries HOLD (`held`,
    sent to this local backend only for reconciliation) reach the model."""
    calls = fake_jev(monkeypatch, KINDS)
    secs = [*sections(), held_section("h", "Employment", HELD)]
    autofill_sections.plan(secs, FACTS, db_session)
    blob = repr(calls)
    assert "Websites" in blob
    assert not [v for v in (*VALUES, *HELD) if v in blob]
    model_settings.set_autofill_engine(db_session, "fast")
    prompts = fake_llm(monkeypatch, {"sections": {}})
    autofill_sections.plan(secs, FACTS, db_session)
    assert not [v for v in (*VALUES, *HELD) if v in prompts[0]["prompt"]]


# ---------- entries already holding data: each is PLACED at the profile entry
# it holds (`order`, one per page entry, then one per entry to add), and the
# empty ones take the profile entries no entry holds, in page order.

JOBS3 = autofill_catalog.build({}, [{"employer": "Acme", "title": "Analyst"},
                                    {"employer": "Initech", "title": "Intern"},
                                    {"employer": "Globex", "title": "Lead"}], [])


def planned(db_session, monkeypatch, facts, *held, sid="w", heading="Work Experience", kind="experience"):
    fake_jev(monkeypatch, {sid: (kind, 0.9)})
    return autofill_sections.plan([held_section(sid, heading, *held)], facts, db_session)[sid].model_dump()


@pytest.mark.usefixtures("jev_on")
def test_an_empty_entry_before_a_held_one_gets_the_next_job_never_a_duplicate(db_session, monkeypatch):
    """[empty, job #1]: by page order the empty entry would be given job #1
    again. Placed, it gets job #2, and the Add brings job #3."""
    assert planned(db_session, monkeypatch, JOBS3, [], ["Acme"]) == {
        "kind": "experience", "wanted": 3, "reason": None, "order": [1, 0, 2]}


@pytest.mark.usefixtures("jev_on")
def test_an_empty_entry_before_job_one_with_nothing_to_add_gets_job_two(db_session, monkeypatch):
    """[empty, job #1] when the page already has as many entries as the
    profile can fill (Globex has no title): no Add, and the empty entry is
    job #2 — never job #1 a second time (evaluation carry note)."""
    assert planned(db_session, monkeypatch, FACTS, [], ["Acme"]) == {
        "kind": "experience", "wanted": 2, "reason": None, "order": [1, 0]}


@pytest.mark.usefixtures("jev_on")
def test_entries_prefilled_out_of_profile_order_keep_what_they_hold(db_session, monkeypatch):
    """Both entries pre-filled, job #2 above job #1: each entry is placed at
    the job it holds, nothing is added (evaluation carry note)."""
    assert planned(db_session, monkeypatch, FACTS, ["Intern", "Initech"], ["Analyst", "Acme"]) == {
        "kind": "experience", "wanted": 2, "reason": None, "order": [1, 0]}


@pytest.mark.usefixtures("jev_on")
def test_a_job_the_parser_dropped_is_added_in_its_place(db_session, monkeypatch):
    """Workday's parser filled jobs #1 and #3 and dropped #2: one Add, and
    the new entry gets job #2."""
    assert planned(db_session, monkeypatch, JOBS3, ["Acme", "Analyst"], ["Globex"]) == {
        "kind": "experience", "wanted": 3, "reason": None, "order": [0, 2, 1]}


@pytest.mark.usefixtures("jev_on")
def test_an_entry_holding_a_later_job_is_placed_and_the_rest_added(db_session, monkeypatch):
    """The page's only entry holds job #2: the Add brings job #1. Globex has
    no title (an added entry would leave it empty), so it is never added."""
    assert planned(db_session, monkeypatch, FACTS, ["Intern", "INITECH, Inc."]) == {
        "kind": "experience", "wanted": 2, "reason": None, "order": [1, 0]}


@pytest.mark.usefixtures("jev_on")
def test_entries_holding_the_first_jobs_in_order_leave_the_rest_to_add(db_session, monkeypatch):
    facts = autofill_catalog.build({}, [{"employer": "Acme Corp", "title": "Analyst"},
                                        {"employer": "Initech", "title": "Intern"},
                                        {"employer": "Globex LLC", "title": "Lead"}], [])
    # Punctuation, case and company suffixes are not a difference.
    assert planned(db_session, monkeypatch, facts, ["acme"], ["Intern", "Initech, Ltd."]) == {
        "kind": "experience", "wanted": 3, "reason": None, "order": [0, 1, 2]}


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("held", [
    (["Somewhere Else"],),                  # a job the profile does not have
    (["Yes"],),                             # held, but nothing names the employer
    (["Somewhere Else"], []),               # the empty entry too: it may be the foreign one's job again
    ([], ["Acme"], ["TCS"]),                # a matching entry in the same section
])
def test_a_section_holding_a_foreign_entry_is_left_to_the_user(db_session, monkeypatch, held):
    """An entry holding a job the profile does not have may be a profile job
    under another name: nothing in its section is placed (every entry null),
    nothing is added, and the report says so even when nothing would have been."""
    assert planned(db_session, monkeypatch, JOBS3, *held) == {
        "kind": "experience", "wanted": len(held), "reason": "held_unmatched", "order": [None] * len(held)}


@pytest.mark.usefixtures("jev_on")
def test_a_foreign_entry_is_reported_when_nothing_was_to_be_added(db_session, monkeypatch):
    """One job in the profile, the page [TCS, empty]: by placement the empty
    entry would get job #1 — which may be the TCS entry, spelled another way."""
    one = autofill_catalog.build({}, [{"employer": "Acme", "title": "Analyst"}], [])
    assert planned(db_session, monkeypatch, one, ["TCS"], []) == {
        "kind": "experience", "wanted": 2, "reason": "held_unmatched", "order": [None, None]}


@pytest.mark.usefixtures("jev_on")
def test_two_entries_holding_one_job_add_nothing(db_session, monkeypatch):
    assert planned(db_session, monkeypatch, JOBS3, ["Acme"], ["ACME Inc."]) == {
        "kind": "experience", "wanted": 2, "reason": "held_twice", "order": [0, None]}
    # Nothing to add anyway: the second holding is still placed nowhere, silently.
    one = autofill_catalog.build({}, [{"employer": "Acme", "title": "Analyst"}], [])
    assert planned(db_session, monkeypatch, one, ["Acme"], ["ACME Inc."]) == {
        "kind": "experience", "wanted": 2, "reason": None, "order": [0, None]}


@pytest.mark.usefixtures("jev_on")
def test_entries_past_the_profile_are_placed_nowhere(db_session, monkeypatch):
    assert planned(db_session, monkeypatch, JOBS3, [], [], [], []) == {
        "kind": "experience", "wanted": 4, "reason": None, "order": [0, 1, 2, None]}


@pytest.mark.usefixtures("jev_on")
def test_jobs_at_one_employer_are_told_apart_by_title(db_session, monkeypatch):
    """Two profile jobs at the same employer: the employer alone cannot say
    which one an entry holds, so its title must match too."""
    facts = autofill_catalog.build({}, [{"employer": "Acme", "title": "Analyst"},
                                        {"employer": "ACME Inc.", "title": "Senior Analyst"},
                                        {"employer": "Globex", "title": "Lead"}], [])
    assert planned(db_session, monkeypatch, facts, ["Acme", "Senior Analyst"])["order"] == [1, 0, 2]
    assert planned(db_session, monkeypatch, facts, ["Acme", "analyst"])["order"] == [0, 1, 2]
    assert planned(db_session, monkeypatch, facts, ["Acme"]) == {
        "kind": "experience", "wanted": 1, "reason": "held_unmatched", "order": [None]}


@pytest.mark.usefixtures("jev_on")
def test_education_is_placed_by_the_school(db_session, monkeypatch):
    facts = autofill_catalog.build({"education": [{"school": "State University"}, {"school": "City College"}]}, [], [])
    kw = {"sid": "e", "heading": "Education", "kind": "education"}
    assert planned(db_session, monkeypatch, facts, ["State University", "MS"], **kw) == {
        "kind": "education", "wanted": 2, "reason": None, "order": [0, 1]}
    assert planned(db_session, monkeypatch, facts, ["City College"], **kw) == {
        "kind": "education", "wanted": 2, "reason": None, "order": [1, 0]}
    assert planned(db_session, monkeypatch, facts, ["Old School"], **kw)["reason"] == "held_unmatched"


LEVELS = {"read": "Fluent", "speak": "Fluent", "write": "Basic"}


@pytest.mark.usefixtures("jev_on")
def test_languages_are_placed_by_the_language(db_session, monkeypatch):
    """A Workday Language entry holds the language and its levels: it is the
    profile language it names, and the rest are added after it."""
    facts = autofill_catalog.build({"languages": [{"language": "Spanish", **LEVELS},
                                                  {"language": "French", **LEVELS}]}, [], [])
    kw = {"sid": "l", "heading": "Languages", "kind": "languages"}
    assert planned(db_session, monkeypatch, facts, **kw) == {
        "kind": "languages", "wanted": 2, "reason": None, "order": [0, 1]}
    assert planned(db_session, monkeypatch, facts, ["french", "Basic", "Basic", "Basic"], **kw) == {
        "kind": "languages", "wanted": 2, "reason": None, "order": [1, 0]}
    assert planned(db_session, monkeypatch, facts, ["German", "Fluent"], **kw)["reason"] == "held_unmatched"
    assert planned(db_session, monkeypatch, facts, ["Spanish"], ["Spanish"], **kw)["reason"] == "held_twice"


@pytest.mark.usefixtures("jev_on")
def test_a_language_without_all_three_levels_is_never_added(db_session, monkeypatch):
    """Workday's Read / Speak / Write popups are REQUIRED ("Read Fluent
    Required"), and an added entry's fields are required: a profile language
    missing a level is never Added. One the page already holds is still that
    language, never a foreign one."""
    facts = autofill_catalog.build({"languages": [{"language": "Spanish", **LEVELS},
                                                  {"language": "French"},
                                                  {"language": "Hindi", "read": "Fluent", "speak": "Basic"},
                                                  {"language": "Tamil", **LEVELS}]}, [], [])
    kw = {"sid": "l", "heading": "Languages", "kind": "languages"}
    assert planned(db_session, monkeypatch, facts, **kw) == {
        "kind": "languages", "wanted": 2, "reason": None, "order": [0, 3]}
    assert planned(db_session, monkeypatch, facts, ["French"], **kw) == {
        "kind": "languages", "wanted": 3, "reason": None, "order": [1, 0, 3]}


@pytest.mark.usefixtures("jev_on")
def test_an_add_skips_a_profile_entry_missing_a_required_fact(db_session, monkeypatch):
    """Placed by profile entry, an Add need not stop at a gap: education
    [A, (no school), C] on an empty page adds A and C, never the one with no
    school."""
    facts = autofill_catalog.build({"education": [{"school": "A"}, {"degree": "BS"}, {"school": "C"}]}, [], [])
    fake_jev(monkeypatch, {"e": ("education", 0.9)})
    got = autofill_sections.plan([PageSection(sid="e", heading="Education", entries=0)], facts, db_session)
    assert got["e"].model_dump() == {"kind": "education", "wanted": 2, "reason": None, "order": [0, 2]}


def test_place_names_its_parts():
    got = autofill_sections.place(held_section("w", "Work Experience", [], ["Acme"]), "experience", JOBS3)
    assert got == autofill_sections.Placement(order=[1, 0], free=[2], safe=True, foreign=False)


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("held, employer", [
    ("Acme Corporation", "ACME"), ("Acme Co.", "Acme"), ("Acme Company", "acme"), ("Acme Limited", "Acme Ltd."),
    ("Acme PLC", "Acme"), ("Acme GmbH", "Acme"), ("Acme LLP", "Acme"), ("Acme L.L.C.", "Acme, LLC"),
])
def test_company_suffixes_and_dotted_forms_are_not_a_difference(db_session, monkeypatch, held, employer):
    facts = autofill_catalog.build({}, [{"employer": employer, "title": "Analyst"},
                                        {"employer": "Initech", "title": "Intern"}], [])
    fake_jev(monkeypatch, {"w": ("experience", 0.9)})
    got = autofill_sections.plan([held_section("w", "Work Experience", [held])], facts, db_session)
    assert (got["w"].wanted, got["w"].reason, got["w"].order) == (2, None, [0, 1])


@pytest.mark.usefixtures("jev_on")
def test_a_held_value_that_normalizes_to_nothing_matches_nothing(db_session, monkeypatch):
    """"Inc." normalizes to "" — and an employer that ALSO normalizes to ""
    must not match it."""
    facts = autofill_catalog.build({}, [{"employer": "Co.", "title": "Analyst"},
                                        {"employer": "Initech", "title": "Intern"}], [])
    fake_jev(monkeypatch, {"w": ("experience", 0.9)})
    got = autofill_sections.plan([held_section("w", "Work Experience", ["Inc.", "Analyst"])], facts, db_session)
    assert (got["w"].wanted, got["w"].reason, got["w"].order) == (1, "held_unmatched", [None])


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


@pytest.mark.usefixtures("jev_on")
def test_no_profile_entries_want_nothing(db_session, monkeypatch):
    facts = autofill_catalog.build({"personal": {"linkedin": "https://linkedin.com/in/ada"}}, [], [])
    fake_jev(monkeypatch, {kind: (kind, 0.9) for kind in autofill_sections.KINDS})
    got = autofill_sections.plan([PageSection(sid=kind, heading=kind, entries=0) for kind in autofill_sections.KINDS],
                                 facts, db_session)
    assert [p.wanted for p in got.values()] == [0] * 6


def test_the_request_carries_headings_and_counts_only():
    with pytest.raises(ValueError):
        SectionsRequest.model_validate({"sections": [{"sid": "f-s1", "heading": "Websites", "entries": 0,
                                                      "filled": [], "values": ["https://ada.dev"]}]})
    with pytest.raises(ValueError):  # held: at most 10 values an entry, 200 characters each
        PageSection(sid="f-s1", heading="Websites", entries=1, held=[["x" * 201]])
    with pytest.raises(ValueError):
        SectionsRequest.model_validate({"sections": []})


# ---------- the route


@pytest.mark.usefixtures("profile")
def test_the_route_counts_from_the_selected_resume(db_session, monkeypatch, tmp_path):
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    seen = {}

    def plan(secs, facts, session):
        seen.update(facts=facts, sections=secs)
        return {s.sid: autofill_sections.SectionPlan(kind="experience", wanted=2) for s in secs}

    monkeypatch.setattr(autofill_sections, "plan", plan)
    r = _post(db_session, "/api/autofill/sections",
              {"base": slug, "sections": [{"sid": "f-s1", "heading": "Work Experience", "entries": 1,
                                           "filled": [True]}]})
    assert r.status_code == 200
    got = r.json()["sections"]["f-s1"]
    assert got["kind"] == "experience" and got["wanted"] >= 1
    # A kind, a count, a word and profile entry NUMBERS, never a value.
    assert set(got) == {"kind", "wanted", "reason", "order"}
    assert "experience.0.employer" in seen["facts"]


def test_the_route_404s_an_unknown_application(db_session):
    from uuid import uuid4

    r = _post(db_session, "/api/autofill/sections",
              {"application_id": str(uuid4()), "sections": [{"sid": "f-s1", "heading": "Education", "entries": 0}]})
    assert r.status_code == 404


# ---------- two sections read as one placed kind (owner, 2026-09-27)


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("kind, first, second", [("experience", "Volunteer Experience", "Work Experience"),
                                                 ("education", "Education", "Certificates and Courses"),
                                                 ("languages", "Languages", "Spoken languages")])
def test_two_sections_of_one_placed_kind_are_both_left_to_the_user(db_session, monkeypatch, kind, first, second):
    """Which one is misread cannot be told: neither is placed, neither grows,
    and each says why. Sections of other kinds are planned as before."""
    fake_jev(monkeypatch, {"a": (kind, 0.9), "b": (kind, 0.9), "s": ("websites", 0.9),
                           "o": ("education" if kind != "education" else "experience", 0.9)})
    other = "Education" if kind != "education" else "Work Experience"
    got = autofill_sections.plan([held_section("a", first, []), held_section("b", second, ["Acme"], []),
                                  held_section("s", "Websites", []), held_section("o", other, [])],
                                 FACTS, db_session)
    assert got["a"].model_dump() == {"kind": kind, "wanted": 1, "reason": "ambiguous_kind", "order": [None]}
    assert got["b"].model_dump() == {"kind": kind, "wanted": 2, "reason": "ambiguous_kind", "order": [None, None]}
    assert (got["s"].reason, got["s"].wanted) == (None, 2)
    assert got["o"].reason is None and got["o"].order[0] == 0


@pytest.mark.usefixtures("jev_on")
def test_two_websites_sections_are_an_ambiguous_kind(db_session, monkeypatch):
    """Websites are placed by profile entry too: two sections read as websites
    are both left to the user, like two job lists."""
    fake_jev(monkeypatch, {"s": ("websites", 0.9), "t": ("websites", 0.9)})
    got = autofill_sections.plan([held_section("s", "Websites", []), held_section("t", "Links", [])], FACTS, db_session)
    assert {sid: p.reason for sid, p in got.items()} == {"s": "ambiguous_kind", "t": "ambiguous_kind"}


# ---------- websites: profile entry k is the k-th URL the profile holds
# (personal.website, then personal.github), placed like a job (live CarMax,
# 2026-09-30: an unplaced second entry was mapped the website again and left empty).

WEB = {"sid": "s", "heading": "Websites", "kind": "websites"}


@pytest.mark.usefixtures("jev_on")
def test_websites_are_placed_in_profile_order_and_added_only_for_urls_the_profile_holds(db_session, monkeypatch):
    assert planned(db_session, monkeypatch, FACTS, **WEB) == {
        "kind": "websites", "wanted": 2, "reason": None, "order": [0, 1]}
    github_only = autofill_catalog.build({"personal": {"github": "https://github.com/ada"}}, [], [])
    assert planned(db_session, monkeypatch, github_only, [], [], **WEB) == {
        "kind": "websites", "wanted": 2, "reason": None, "order": [0, None]}
    none = autofill_catalog.build({"personal": {"linkedin": "https://linkedin.com/in/ada"}}, [], [])
    assert planned(db_session, monkeypatch, none, [], **WEB) == {
        "kind": "websites", "wanted": 1, "reason": None, "order": [None]}


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("held", ["https://github.com/ada", "GitHub.com/ada/", "http://www.github.com/ada#top"])
def test_a_websites_entry_holding_a_profile_url_is_that_url(db_session, monkeypatch, held):
    """An entry already holding the GitHub is the GitHub (a URL is the same
    whatever its scheme, `www.`, host case, trailing slash or #fragment): the
    website goes into the entry added after it, never doubled."""
    assert planned(db_session, monkeypatch, FACTS, [held], **WEB) == {
        "kind": "websites", "wanted": 2, "reason": None, "order": [1, 0]}


@pytest.mark.usefixtures("jev_on")
def test_a_websites_entry_holding_another_url_is_foreign(db_session, monkeypatch):
    assert planned(db_session, monkeypatch, FACTS, ["https://example.org/someone-else"], **WEB) == {
        "kind": "websites", "wanted": 1, "reason": "held_unmatched", "order": [None]}


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("linkedin", ["https://linkedin.com/in/ada", "www.LinkedIn.com/in/ada/"])
def test_a_websites_entry_holding_the_profiles_own_linkedin_is_left_but_not_foreign(db_session, monkeypatch,
                                                                                    linkedin):
    """A resume-parsed Workday page often puts the applicant's LinkedIn in a
    Websites entry. It is theirs, so the section is not foreign: that entry is
    placed nowhere (left as it is) and the website and GitHub still go in."""
    assert planned(db_session, monkeypatch, FACTS, [linkedin], **WEB) == {
        "kind": "websites", "wanted": 3, "reason": None, "order": [None, 0, 1]}
    assert planned(db_session, monkeypatch, FACTS, [], [linkedin], **WEB) == {
        "kind": "websites", "wanted": 3, "reason": None, "order": [0, None, 1]}
