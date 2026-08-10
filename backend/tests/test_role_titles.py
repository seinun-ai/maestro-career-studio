from app.services.role_titles import generic_role_title


def test_generic_role_title_prefers_role_category():
    assert (
        generic_role_title(
            role_category="data_scientist",
            title="Junior LLM Data Scientist",
        )
        == "Data Scientist"
    )


def test_generic_role_title_prefers_job_title_over_base_slug():
    """The JOB decides the label: an ML-engineer posting tailored from the
    data_scientist base must not be filed as Data Scientist."""
    assert (
        generic_role_title(
            role_category="other",
            base_resume_role="data_scientist",
            title="Staff Machine Learning Engineer",
        )
        == "Machine Learning Engineer"
    )


def test_generic_role_title_hybrid_category_defers_to_title():
    assert (
        generic_role_title(
            role_category="hybrid",
            base_resume_role="data_scientist",
            title="Senior Data Engineer",
        )
        == "Data Engineer"
    )


def test_generic_role_title_base_resume_is_last_resort():
    """The last resort is the resume's DECLARED role, not its slug.

    This branch used to test the slug for membership in the job-role
    vocabulary, so it resolved only when a resume happened to be named after a
    category: `data_scientist` gave "Data Scientist" while `data_scientist_new`
    gave "Professional" despite targeting the same role, and every
    arbitrarily-named resume always fell through.
    """
    assert (
        generic_role_title(
            role_category="other",
            base_resume_role="data_analyst",
            title=None,
        )
        == "Data Analyst"
    )


def test_generic_role_title_no_longer_reads_the_slug():
    """A slug that merely LOOKS like a category must not resolve on its own."""
    assert (
        generic_role_title(role_category=None, base_resume_role=None, title=None)
        == "Professional"
    )


def test_arbitrarily_named_resume_still_gets_its_declared_role():
    """The case every new user hits: a slug that matches no category."""
    assert (
        generic_role_title(
            role_category=None, base_resume_role="data_scientist", title=None
        )
        == "Data Scientist"
    )


def test_generic_role_title_strips_seniority_and_niche_modifiers():
    assert generic_role_title(title="Junior LLM Data Scientist") == "Data Scientist"
    assert generic_role_title(title="Senior Applied NLP Scientist") == "Scientist"


def test_generic_role_title_recognizes_core_role_phrases():
    assert generic_role_title(title="Staff Machine Learning Engineer") == "Machine Learning Engineer"
    assert generic_role_title(title="Lead AI/ML Engineer") == "AI/ML Engineer"


def test_generic_role_title_defaults_when_unknown():
    assert generic_role_title(title="") == "Professional"
    assert generic_role_title(title=None) == "Professional"
