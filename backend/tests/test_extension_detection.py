"""The page-detection gate: what mounts, what does not, and what a miss costs.

`extension/content/detect.js` runs in every frame of every page, before any UI
exists, and answers one question: is there anything here this extension can
help with. The expensive half of that answer is the negative one. Design
section 5 states it as an absolute — on a miss the widget mounts nothing,
observes nothing and constructs no telemetry observation, not even a dot —
because the best-documented failure in this product category is ambient job
detection injected into pages it cannot act on: one competitor's experimental
detection broke a video site's own buttons, another is reported maxing CPU
"regardless of if it can fill out anything".

The tests come in two halves. Most pin what each tier recognises.
`test_the_widget_never_mounts_on_a_form_that_is_not_an_application`,
`test_a_page_with_none_of_the_signals_mounts_nothing` and
`test_a_miss_reads_the_page_exactly_this_many_times` pin what the gate declines
to do and what declining costs, and those are the ones worth keeping green.
The first of them is the one that matters most: the pages it covers — a card
payment form, a checkout, a signup, a personal site — all scored Tier B until
a review found them, because each sat one unanchored substring away from being
claimed. A page with nothing on it was never the hard case.

The return contract — `{tier, score, signals, form}` — is asserted by the
harness driver itself, on every run in this file.
"""

import re

import pytest

from tests.extension_harness import (
    ROOT,
    detect_fixture_names,
    load_detect_page,
    read_detect_fixture,
    run_detect,
    run_detect_fixture,
    run_node,
)

EXTENSION = ROOT / "extension"


# The three shapes JSON-LD is legally written in, all of which the gate has to
# walk. `@graph` is JSON-LD's own container for a set of nodes, a bare document
# is one node, and a document may also be a top-level array of them. Each case
# below buries the JobPosting behind a sibling of another type, so a walk that
# only ever looked at the first node would fail here rather than pass by luck.
_JSON_LD_SHAPES = [
    ("bare", ["JobPosting"]),
    ("array", ["WebSite", "JobPosting"]),
    ("graph", ["BreadcrumbList", "JobPosting"]),
]


def _signals(result: dict) -> set[str]:
    return set(result["signals"])


# ---------- the corpus ----------


def test_the_detection_corpus_is_not_empty():
    """`detect_fixture_names()` drives the round trip below and the PII guard in
    test_extension_fixture_corpus; an empty glob turns both into zero tests."""
    assert len(detect_fixture_names()) >= 10


@pytest.mark.parametrize("name", detect_fixture_names())
def test_every_detection_fixture_loads_and_runs(tmp_path, name):
    """A malformed page fixture fails HERE, naming itself, instead of surfacing
    as a baffling tier assertion in the test that consumes it."""
    read_detect_fixture(name)
    result = run_detect_fixture(tmp_path, name)
    assert result["tier"] in {"A", "B", "none"}
    assert result["score"] >= 0
    # `form` is the caller's half of the contract and may not contradict the
    # tier it was derived beside. Only Tier A is free to differ, which is the
    # whole reason it is returned.
    if result["tier"] == "B":
        assert result["form"] is True
    if result["tier"] == "none":
        assert result["form"] is False


# ---------- Tier A: job posting ----------


@pytest.mark.parametrize("shape,types", _JSON_LD_SHAPES, ids=[s for s, _ in _JSON_LD_SHAPES])
def test_a_json_ld_job_posting_is_tier_a_in_every_shape(tmp_path, shape, types):
    """A JobPosting record makes the page a job posting however it is nested."""
    page = {**load_detect_page("detect_lever_posting"),
            "jsonLd": [{"shape": shape, "types": types}]}
    result = run_detect(tmp_path, page=page)

    assert result["tier"] == "A"
    assert "job-posting" in _signals(result)


def test_a_posting_outranks_the_form_shaped_evidence_beside_it(tmp_path):
    """The Lever posting carries two points of Tier B evidence — the per-ATS
    container and an "Apply for this job" link — and is still Tier A.

    This is the ordering that matters in production, and not because of Lever.
    Tier B evidence is circumstantial: this page reaches the threshold on a
    marker and a link while holding no field at all, and every ATS posting does
    the same. A JobPosting record is the page declaring what it is, and nothing
    else can produce one — so scoring first would relabel postings as forms.

    The Tier B evidence is still reported, so a caller that wants to offer both
    actions can see it.
    """
    result = run_detect_fixture(tmp_path, "detect_lever_posting")

    assert result["tier"] == "A"
    assert result["form"] is True, (
        "the caller has to be able to see that the form evidence held too — "
        "that is the whole reason `form` is returned beside `tier`"
    )
    # Whole set, not a subset: `[data-ui="job-post"]` is the only marker this
    # page carries, so a subset assertion would let that clause be deleted.
    assert _signals(result) == {
        "ats:lever", "jsonld", "job-posting", "ats-dom-marker", "apply-affordance",
    }


def test_a_job_posting_type_may_be_one_of_several(tmp_path):
    """`"@type": ["JobPosting", "Thing"]` is a legal schema.org node and names a
    job posting. Reused from `extractJobPosting`, which already handles it."""
    page = {**load_detect_page("detect_lever_posting"),
            "jsonLd": [{"shape": "bare", "types": [["JobPosting", "Thing"]]}]}
    result = run_detect(tmp_path, page=page)

    assert result["tier"] == "A"


def test_both_copies_of_the_json_ld_walk_stay_identical():
    """The old twin is now one walk with an explicit presence-only mode.

    Detection asks whether the page declares a posting and accepts a node with
    no description. Extraction asks to read that posting and requires one.
    Keeping the historical test name makes the migration guard visible while
    converting its assertion from twin identity to one authoritative source.
    """
    module = EXTENSION / "content" / "job-posting.js"
    assert module.is_file(), "the shared JobPosting module has not been created"
    content_sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((EXTENSION / "content").glob("*.js"))
    }
    declarations = re.compile(
        r"(?:function\s+findJobPosting\s*\(|(?:const|let|var)\s+findJobPosting\s*=)")
    assert len(declarations.findall(content_sources["job-posting.js"])) == 1
    assert not {
        name: declarations.findall(source)
        for name, source in content_sources.items()
        if name != "job-posting.js" and declarations.search(source)
    }
    shared = module.read_text(encoding="utf-8")
    assert "presenceOnly" in shared
    assert "ns.findJobPostingInDocument = findJobPostingInDocument;" in shared
    assert "findJobPostingInDocument({ presenceOnly: true })" in (
        EXTENSION / "content" / "detect.js").read_text(encoding="utf-8")
    assert "findJobPostingInDocument({ presenceOnly: false })" in (
        EXTENSION / "content" / "agent.js").read_text(encoding="utf-8")


def test_the_shared_json_ld_walk_has_distinct_presence_and_extraction_modes(tmp_path):
    """Presence accepts a type-only node; extraction skips it for a described one."""
    driver = r"""
global.document = {
  querySelectorAll: () => spec.nodes.map((node) => ({
    textContent: JSON.stringify(node),
  })),
};
const ns = loadModules();
const present = ns.findJobPostingInDocument({ presenceOnly: true });
const extractable = ns.findJobPostingInDocument({ presenceOnly: false });
emit({ present: present?.marker ?? null, extractable: extractable?.marker ?? null });
"""
    source = (EXTENSION / "content" / "job-posting.js").read_text(encoding="utf-8")
    result = run_node(driver, {"nodes": [
        {"@type": "JobPosting", "marker": "type-only"},
        {"@type": "JobPosting", "description": "Readable", "marker": "described"},
    ]}, tmp_path, source=source)

    assert result == {"present": "type-only", "extractable": "described"}


def test_malformed_json_ld_does_not_stop_the_scan(tmp_path):
    """One unparseable script must not hide a good record behind it. Pages ship
    broken JSON-LD often enough that this is the common case, not the edge."""
    page = {**load_detect_page("detect_lever_posting"), "jsonLd": [
        {"malformed": True},
        {"shape": "bare", "types": ["JobPosting"]},
    ]}
    result = run_detect(tmp_path, page=page)

    assert result["tier"] == "A"


def test_json_ld_that_is_not_a_job_posting_is_not_a_job_page(tmp_path):
    """Almost every commercial page on the web carries JSON-LD. The Tier 0
    presence check is a gate on the parse, never a signal that this is a job
    page — otherwise the gate would mount on a recipe."""
    page = {**load_detect_page("detect_unrelated_page"),
            "jsonLd": [{"shape": "graph", "types": ["Organization", "VideoObject"]}]}
    result = run_detect(tmp_path, page=page)

    assert result["tier"] == "none"
    assert "job-posting" not in _signals(result)
    # It WAS seen — the miss is a verdict on the content, not on the lookup.
    assert "jsonld" in _signals(result)


# ---------- Tier B: application form ----------


def test_a_greenhouse_application_form_is_tier_b(tmp_path):
    """The resume input and the identity cluster are each worth one point, so
    this form clears the threshold on those two alone — which is why the
    fixture deliberately carries no self-identification text.

    The signal set is asserted whole rather than as a subset, so that every
    clause this page exercises is load-bearing: `#application_form` is the only
    marker it carries, and a subset assertion would let that clause be deleted
    while the other four kept the test green.
    """
    result = run_detect_fixture(tmp_path, "detect_greenhouse_application_form")

    assert result["tier"] == "B"
    assert result["form"] is True
    assert _signals(result) == {
        "ats:greenhouse", "resume-input", "identity-cluster",
        "ats-dom-marker", "apply-affordance",
    }


def test_self_identification_text_alone_is_tier_b(tmp_path):
    """Statutory self-identification wording is near-certain evidence of an
    application form, so it is the one signal weighted to clear the threshold by
    itself — on a page with no ATS host, no JSON-LD and no identity field.

    A page asking whether you are a protected veteran, or how you would
    describe your disability status, is asking an applicant and nobody else.
    """
    result = run_detect_fixture(tmp_path, "detect_eeo_self_identification")

    assert result["tier"] == "B"
    assert _signals(result) == {"self-identification"}, (
        "nothing else on this page may score, or it stops testing the weight"
    )


# Each row isolates ONE alternative of the two text regexes, so deleting any
# alternative fails a test here rather than passing on a neighbour's wording.
@pytest.mark.parametrize("text,signal,weight", [
    ("Voluntary self-identification. Completion is optional.", "self-identification", 2),
    ("Are you a protected veteran? Select the veteran status that applies.",
     "self-identification", 2),
    ("How would you describe your disability status?", "self-identification", 2),
    # Boilerplate. Real evidence, but it is the sentence at the foot of a job
    # description, in a corporate footer, and in a blog post explaining the law.
    ("Acme is an equal employment opportunity employer.", "eeo-boilerplate", 0),
    ("Acme is an EEO employer and follows the guidance.", "eeo-boilerplate", 0),
    # \b, and this is what it is for: three letters inside a longer run are a
    # brand or an identifier, never a statement about hiring.
    ("Our SPEEOX platform ships weekly.", None, 0),
    ("We hire brilliant people and pay them well.", None, 0),
])
def test_the_hiring_vocabulary_is_read_at_two_strengths(tmp_path, text, signal, weight):
    """Treating the whole vocabulary as near-certain put the widget on every
    page of any company carrying one line in its footer. The self-identification
    block is decisive on its own; the boilerplate around it does not score at
    all — it is reported and never counted."""
    page = {
        "url": "https://example-co.test/careers",
        "text": text,
        # A <select> is here only to open the text gate — the read is behind
        # `form, select` so it never happens on the miss path.
        "elements": [{"tag": "select", "attrs": {"name": "country"}}],
    }
    result = run_detect(tmp_path, page=page)

    assert _signals(result) == ({signal} if signal else set())
    assert result["score"] == weight


@pytest.mark.parametrize("attrs", [
    # A drag-and-drop uploader declaring no `accept` at all: the name is the
    # only thing left saying what it wants, which is why the design calls the
    # name clauses the strongest single signal.
    {"type": "file", "name": "resume_upload"},
    {"type": "file", "name": "cv_file"},
    # ...and the accept clause, for the input named something generic.
    {"type": "file", "name": "attachment", "accept": "application/pdf"},
])
def test_each_way_of_declaring_a_resume_upload_scores(tmp_path, attrs):
    """Three clauses, three independent reasons to fire. Deleting any one of
    them fails exactly one row."""
    page = {
        "url": "https://careers.example.test/apply",
        "text": "Attach your CV.",
        "elements": [{"tag": "input", "attrs": attrs}],
    }
    assert "resume-input" in _signals(run_detect(tmp_path, page=page))


def test_the_identity_cluster_reads_autocomplete_as_well_as_names(tmp_path):
    """A framework that generates opaque field names still has to tell the
    browser what to autofill, so the autocomplete tokens are the only handle on
    a form whose `name` attributes say nothing."""
    page = {
        "url": "https://careers.example.test/apply",
        "text": "About you.",
        "elements": [
            {"tag": "input", "attrs": {"type": "text", "name": "f_0", "autocomplete": "given-name"}},
            {"tag": "input", "attrs": {"type": "text", "name": "f_1", "autocomplete": "family-name"}},
            {"tag": "input", "attrs": {"type": "email", "name": "f_2"}},
        ],
    }
    assert "identity-cluster" in _signals(run_detect(tmp_path, page=page))


def test_a_submit_input_carries_its_label_in_its_value(tmp_path):
    """`<input type="submit">` has no text between its tags — its visible label
    IS its value attribute, so reading only `textContent` would miss every form
    built the older way."""
    page = {
        "url": "https://careers.example.test/apply",
        "text": "One more step.",
        "elements": [
            {"tag": "input", "attrs": {"type": "submit", "value": "Submit application"}},
        ],
    }
    assert "apply-affordance" in _signals(run_detect(tmp_path, page=page))


def test_two_identity_fields_are_not_a_cluster(tmp_path):
    """Three, not two. An email box beside a name box is a newsletter signup,
    a mailing-list form, a checkout — the shapes a two-field rule would mount
    the widget on all day."""
    page = {
        "url": "https://news.example.test/subscribe",
        "text": "Get the weekly digest.",
        "elements": [
            {"tag": "input", "attrs": {"type": "text", "name": "first_name"}},
            {"tag": "input", "attrs": {"type": "email", "name": "email"}},
        ],
    }
    result = run_detect(tmp_path, page=page)

    assert "identity-cluster" not in _signals(result)
    assert result["tier"] == "none"


def test_a_third_identity_field_completes_the_cluster(tmp_path):
    """The other side of the threshold, so a rule that never fires cannot pass
    the test above."""
    page = {
        "url": "https://careers.example.test/apply",
        "text": "Tell us about yourself.",
        "elements": [
            {"tag": "input", "attrs": {"type": "text", "name": "first_name"}},
            {"tag": "input", "attrs": {"type": "email", "name": "email"}},
            {"tag": "input", "attrs": {"type": "tel", "name": "phone"}},
        ],
    }
    result = run_detect(tmp_path, page=page)

    assert "identity-cluster" in _signals(result)


def test_an_upload_that_takes_no_document_is_not_a_resume_field(tmp_path):
    """A file input is everywhere. The signal is a file input that wants a PDF,
    or a control that says resume or CV in its name — not any upload at all."""
    page = {
        "url": "https://photos.example.test/upload",
        "text": "Drag your photos here.",
        "elements": [
            {"tag": "input", "attrs": {"type": "file", "accept": "image/png,image/jpeg",
                                       "name": "photo_upload"}},
        ],
    }
    result = run_detect(tmp_path, page=page)

    assert "resume-input" not in _signals(result)
    assert result["tier"] == "none"


@pytest.mark.parametrize("text,fires", [
    ("Apply", True),
    ("Apply for this job", True),
    ("Submit Application", True),
    # Anchored at the start of the control's own text, which is what makes the
    # signal mean "the control that applies" rather than "the word appears".
    ("How to apply", False),
    ("Reapply next season", False),
    ("Applicant privacy notice", False),
    # `continue` is gone from the regex. It is the label on every wizard,
    # checkout and onboarding step ever built, and an ATS step that uses it
    # carries its vendor's marker and its identity fields anyway.
    ("Continue", False),
    ("Continue to payment", False),
])
def test_the_apply_affordance_is_the_control_not_the_word(tmp_path, text, fires):
    page = {
        "url": "https://careers.example.test/roles",
        "text": "Open roles.",
        "elements": [{"tag": "button", "attrs": {"type": "button"}, "text": text}],
    }
    result = run_detect(tmp_path, page=page)

    assert ("apply-affordance" in _signals(result)) is fires


# ---------- Tier 0: the host list ----------


@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/acme/jobs/701", "ats:greenhouse"),
    ("https://acme.greenhouse.io/jobs/701", "ats:greenhouse"),
    ("https://acme.wd5.myworkdayjobs.com/en-US/careers", "ats:workday"),
    ("https://jobs.lever.co/acme/9f1c", "ats:lever"),
    ("https://jobs.ashbyhq.com/acme/9f1c", "ats:ashby"),
    ("https://acme.smartrecruiters.com/roles", "ats:smartrecruiters"),
    ("https://apply.workable.com/acme/j/9F1C", "ats:workable"),
    ("https://acme.recruitee.com/o/analyst", "ats:recruitee"),
    ("https://acme.bamboohr.com/careers/12", "ats:bamboohr"),
    ("https://ats.rippling.com/acme/jobs/9f1c", "ats:rippling"),
    ("https://acme.rippling-ats.com/jobs/9f1c", "ats:rippling"),
    ("https://jobs.jobvite.com/acme/job/9f1c", "ats:jobvite"),
    ("https://careers-acme.icims.com/jobs/701/analyst", "ats:icims"),
    ("https://acme.taleo.net/careersection/jobdetail.ftl", "ats:taleo"),
    ("https://acme.successfactors.com/career", "ats:successfactors"),
    # A host list matched by substring is a host list that trusts anyone who
    # buys the right domain. These must all miss.
    ("https://greenhouse.io.attacker.test/acme", None),
    ("https://notgreenhouse.io/acme", None),
    ("https://myworkdayjobs.com.attacker.test/", None),
    ("https://jobs.lever.co.attacker.test/", None),
    ("https://www.example-video.test/watch", None),
])
def test_the_ats_host_list_matches_on_the_domain_not_the_string(tmp_path, url, expected):
    result = run_detect(tmp_path, page={"url": url, "text": "", "elements": []})

    hits = [signal for signal in result["signals"] if signal.startswith("ats:")]
    assert hits == ([expected] if expected else [])


def test_an_ats_host_alone_is_never_enough_to_mount(tmp_path):
    """A Workday tenant's search page: the right host, per-ATS markers on every
    node, and nothing to do. Design section 5 — "a host hit is a scoring signal
    and selects the per-ATS field map; it is never sufficient alone".

    Read together with the Greenhouse form, which is on an ATS host too: the
    host is what tells the fill engine WHICH page it is on, never whether it
    should be there.
    """
    result = run_detect_fixture(tmp_path, "detect_workday_job_search")

    assert "ats:workday" in _signals(result), "the host was not even recognised"
    assert result["tier"] == "none"
    assert result["score"] < 2


# ---------- the negative rule ----------


@pytest.mark.parametrize("name", [
    "detect_payment_card_form",
    "detect_checkout_shipping",
    "detect_signup_wizard",
    "detect_portfolio_contact",
    "detect_careers_contact_footer",
])
def test_the_widget_never_mounts_on_a_form_that_is_not_an_application(tmp_path, name):
    """The negative rule where it is actually hard.

    Every one of these pages scored Tier B before the review that found them.
    They matter far more than the video page below, which was never going to
    match anything: these are FORMS, collecting a name and an email and a phone
    number, sitting one substring away from being claimed.

    * payment — `[name*="cv" i]` matched `cardCvv`, so a card form scored the
      extension's strongest signal. An autofill widget on a payment page is the
      worst false positive this product can produce.
    * checkout and signup — three identity fields plus a control labelled
      Continue. Both signals were real; the conclusion was not.
    * portfolio — `[name*="resume" i]` matched an `<a name="resume">` bookmark
      anchor, which is how in-page anchors were written for twenty years.
    * careers contact — a contact form under an equal-opportunity footer line.
      The last one standing, because it needed no substring bug at all: two
      genuine signals, one of them worth a point it had not earned. See
      `test_boilerplate_is_reported_but_can_never_reach_the_threshold`.

    The fix in each case was to require CONTEXT rather than accept a bare
    match: a resume field is a file input, `continue` is not an apply
    affordance, and an equal-opportunity line is not evidence of a form.
    """
    result = run_detect_fixture(tmp_path, name)

    assert result["tier"] == "none", f"signals: {result['signals']}"
    assert result["form"] is False
    assert result["score"] < 2


def test_a_cvv_field_is_not_a_resume_field(tmp_path):
    """The substring, isolated, so the payment fixture cannot go green because
    something unrelated about it changed."""
    page = {
        "url": "https://shop.example.test/pay",
        "text": "Card details.",
        "elements": [{"tag": "input", "attrs": {"type": "text", "name": "cardCvv"}}],
    }
    assert "resume-input" not in _signals(run_detect(tmp_path, page=page))


def test_a_page_with_none_of_the_signals_mounts_nothing(tmp_path):
    """The single most important test here. Design section 5's negative rule:
    mount nothing, observe nothing, construct no telemetry observation.

    `tier: "none"` is how the gate says that, and an empty `signals` is how it
    says it has nothing to report about the page either — there is no partial
    state in which a dot appears.
    """
    result = run_detect_fixture(tmp_path, "detect_unrelated_page")

    assert result["tier"] == "none"
    assert result["score"] == 0
    assert result["signals"] == []


def test_a_miss_reads_the_page_exactly_this_many_times(tmp_path):
    """What a miss costs, in full, as a decision someone has to change on
    purpose rather than a number that drifts.

    Paying nothing on pages it cannot help with is the property that separates
    this widget from every complaint in the research, and this content script
    runs in EVERY frame and re-runs on every SPA route change — so the cost
    below is paid per frame per navigation, not once.

    Three things this list is asserting, none of which survives as a comment:

    * the ld+json selector appears ONCE. Tier 0's presence check is a gate on
      Tier A's parse, so a page declaring none is never enumerated, never
      parsed, and no graph is ever walked.
    * `body.textContent` does not appear at all. Flattening the whole document
      into a string is the most expensive thing this module can do, and it sits
      behind `form, select` precisely so the miss path never reaches it.
    * only two of the four identity probes run. Once two have missed, three
      matches are unreachable and the remaining probes cannot change the
      answer.
    """
    result = run_detect_fixture(tmp_path, "detect_unrelated_page")

    assert result["queries"] == [
        'script[type="application/ld+json"]',
        'input[type="file"][accept*="pdf" i], input[type="file"][name*="resume" i], '
        'input[type="file"][name*="cv" i]',
        'input[name*="first_name" i], input[name*="firstname" i], [autocomplete="given-name"]',
        'input[name*="last_name" i], input[name*="lastname" i], [autocomplete="family-name"]',
        "form, select",
        '#application_form, [data-ui="job-post"], [data-automation-id]',
        'button, input[type="submit"], input[type="button"], a[role="button"]',
    ]

    # …and when the hit path DOES flatten the page, it reads the one string
    # property with no layout cost: `textContent`, never `innerText`, which
    # forces style/layout on a page that may be mid-load. (Ported from the
    # deleted applied-detection suite, which was the only source-level pin.)
    detect = (EXTENSION / "content" / "detect.js").read_text(encoding="utf-8")
    assert "document.body.textContent" in detect
    assert "document.body.innerText" not in detect


# ---------- known imprecision ----------


def test_boilerplate_is_reported_but_can_never_reach_the_threshold(tmp_path):
    """The equal-opportunity line scores zero — reported, never decisive.

    It is the same treatment `ats:<vendor>` gets, for the same reason: it says
    something true about the page and nothing about whether there is a form on
    it. That line sits in a corporate footer, under every job description, and
    in any blog post explaining the law.

    At weight 1 it reached the threshold in company with any single weak
    partner, which is what this page is: an ordinary contact form under a
    footer. At 0 the page falls out, and nothing legitimate is lost, because
    the boilerplate is never load-bearing for a real application form —
    `test_a_real_application_form_reaches_the_threshold_without_boilerplate`
    walks the three routes it takes instead.

    The signal stays in `signals` throughout. A caller combining this with Tier
    C can still see that the page talks about hiring.
    """
    result = run_detect_fixture(tmp_path, "detect_careers_contact_footer")

    assert result["tier"] == "none"
    assert result["form"] is False
    assert "eeo-boilerplate" in _signals(result)
    # ...and the one point comes entirely from the identity cluster, so this
    # fails if the boilerplate starts scoring again.
    assert result["score"] == 1


@pytest.mark.parametrize("name,route", [
    ("detect_greenhouse_application_form", "an upload plus an identity cluster"),
    ("detect_workday_job_search", None),
    ("detect_eeo_self_identification", "the self-identification block alone"),
])
def test_a_real_application_form_reaches_the_threshold_without_boilerplate(
    tmp_path, name, route
):
    """The argument for scoring the boilerplate at zero, checked rather than
    asserted in prose: no genuine application form depends on it.

    A form arrives at the threshold three other ways — an upload plus an
    identity cluster, a vendor marker plus an apply control, or the
    self-identification block by itself — and none of them is a text signal.
    The Workday row is the control: it carries neither route and must still
    miss, so this cannot pass by scoring everything.
    """
    result = run_detect_fixture(tmp_path, name)

    assert "eeo-boilerplate" not in _signals(result)
    assert result["form"] is (route is not None), route


def test_an_ats_posting_page_with_an_apply_button_reads_as_a_form(tmp_path):
    """CHARACTERISATION, not an endorsement. A Workday posting stamps
    `data-automation-id` on every node and renders an Apply control, which is
    two points of Tier B evidence on a page holding no form at all.

    It is left as it is because the cost is small and the alternative is worse:
    both signals come from design section 5's list, and the widget resolves its
    primary action from the job record (design section 4.1), so the page still
    mounts as the job page it is. What this pins is that the imprecision is
    bounded to ATS hosts — the same two signals cannot co-occur off one, since
    the markers are per-ATS.

    A posting that also carries a JobPosting record is unaffected: Tier A wins.
    """
    page = {**load_detect_page("detect_workday_job_search"),
            "url": "https://acme.wd5.myworkdayjobs.com/careers/job/Austin/Analyst_R-482",
            "elements": [
                {"tag": "div", "attrs": {"data-automation-id": "jobPostingHeader"}},
                {"tag": "a", "attrs": {"role": "button",
                                       "data-automation-id": "adventureButton"},
                 "text": "Apply"},
            ]}
    result = run_detect(tmp_path, page=page)

    assert result["tier"] == "B"
    assert _signals(result) == {"ats:workday", "ats-dom-marker", "apply-affordance"}
