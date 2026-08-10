from app.services.artifact_naming import artifact_stem


def test_artifact_stem_uses_name_and_role_only():
    # Date + company live in the folder name, so the stem is just name + role.
    assert artifact_stem(
        contact={"name": "John Doe"},
        role="Data Analyst",
        document_type="Resume",
    ) == "John_Doe_DataAnalyst_Resume"


def test_artifact_stem_sanitizes_symbols_and_cover_letter_suffix():
    assert artifact_stem(
        contact={"name": "Jane Q. Public"},
        role="AI/ML Engineer",
        document_type="CoverLetter",
    ) == "Jane_Public_AIMLEngineer_CoverLetter"


def test_artifact_stem_uses_neutral_fallbacks_for_missing_contact_and_role():
    assert artifact_stem(
        contact={},
        role=None,
        document_type="Resume",
    ) == "Candidate_Candidate_Role_Resume"
