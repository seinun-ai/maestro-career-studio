"""Contract tests for the conservative near-identity matcher (design §4b).

Pure unit tests: no DB, no LLM, no fixtures. Candidate dicts are built with the
production ``identity_key`` so the keys under test are exactly the keys the
``_existing_*_index`` helpers put in their dicts. Values are opaque sentinels —
the matcher reads only the keys and hands the value back.

The load-bearing case is ``test_azure_fundamentals_vs_data_fundamentals_never_match``:
a false merge destroys evidence, a false fork costs one click in the merge UI.
"""

from app.services.kb_consolidation import (
    _cert_signature, find_near_identity, identity_key,
)


def _candidates(section, *entries):
    """{identity_key: sentinel} built the way the real indexes are built."""
    return {identity_key(section, e): f"entity:{i}" for i, e in enumerate(entries)}


def _exp(company, role, start="2022-07", end=None):
    return {"company": company, "role": role, "start_date": start, "end_date": end}


def _proj(name):
    return {"name": name}


# --- experience ------------------------------------------------------------


def test_richer_role_title_matches_same_company_and_start():
    poor = _exp("TCS", "Data Analyst")
    rich = _exp("TCS", "Data Analyst, British Airways Account")

    # incoming poorer, stored richer
    assert find_near_identity("experience", poor, _candidates("experience", rich)) == "entity:0"
    # incoming richer, stored poorer
    assert find_near_identity("experience", rich, _candidates("experience", poor)) == "entity:0"


def test_different_company_never_matches():
    incoming = _exp("TCS", "Data Analyst")
    stored = _candidates("experience", _exp("Infosys", "Data Analyst, British Airways Account"))
    assert find_near_identity("experience", incoming, stored) is None


def test_different_start_date_never_matches():
    incoming = _exp("TCS", "Data Analyst", start="2022-07")
    stored = _candidates("experience", _exp("TCS", "Data Analyst, British Airways Account", start="2023-01"))
    assert find_near_identity("experience", incoming, stored) is None


def test_disjoint_role_tokens_never_match():
    incoming = _exp("TCS", "Data Analyst")
    stored = _candidates("experience", _exp("TCS", "Software Engineer"))
    assert find_near_identity("experience", incoming, stored) is None


def test_partial_role_overlap_without_subset_never_matches():
    # shares "analyst" but neither token set contains the other
    incoming = _exp("TCS", "Data Analyst")
    stored = _candidates("experience", _exp("TCS", "Business Analyst"))
    assert find_near_identity("experience", incoming, stored) is None


def test_blank_role_never_matches():
    incoming = _exp("TCS", "")
    stored = _candidates("experience", _exp("TCS", "Data Analyst"))
    assert find_near_identity("experience", incoming, stored) is None


def test_dateless_experience_never_matches():
    # Both sides dateless: same company + subset roles would otherwise be the
    # loosest path in the matcher. An empty start on the incoming side refuses;
    # a dateless duplicate costs one manual merge (fork over fuse).
    incoming = _exp("TCS", "Data Analyst", start="")
    stored = _candidates(
        "experience", _exp("TCS", "Data Analyst, British Airways Account", start="")
    )
    assert find_near_identity("experience", incoming, stored) is None


def test_ambiguous_candidates_return_none():
    # two stored roles at the same company+start both contain the incoming role
    incoming = _exp("TCS", "Analyst")
    stored = _candidates(
        "experience",
        _exp("TCS", "Analyst, British Airways Account"),
        _exp("TCS", "Analyst, Retail Account"),
    )
    assert find_near_identity("experience", incoming, stored) is None


# --- certifications --------------------------------------------------------


def test_exam_code_parenthetical_is_noise():
    stored = _candidates("certifications", "AWS Certified AI Practitioner")
    assert find_near_identity(
        "certifications", "AWS Certified AI Practitioner (AIF-C01)", stored
    ) == "entity:0"


def test_certified_and_vendor_prefix_are_noise():
    stored = _candidates("certifications", "AWS Certified AI Practitioner")
    assert find_near_identity("certifications", "AWS AI Practitioner", stored) == "entity:0"


def test_azure_fundamentals_vs_data_fundamentals_never_match():
    """THE CONTRACT. AZ-900 and DP-900 are different exams."""
    stored = _candidates("certifications", "Microsoft Certified: Azure Fundamentals (AZ-900)")
    assert find_near_identity(
        "certifications", "Microsoft Certified: Azure Data Fundamentals (DP-900)", stored
    ) is None
    # and the other direction
    stored2 = _candidates("certifications", "Microsoft Certified: Azure Data Fundamentals (DP-900)")
    assert find_near_identity(
        "certifications", "Microsoft Certified: Azure Fundamentals (AZ-900)", stored2
    ) is None


def test_google_professional_certificate_suffix_is_noise():
    stored = _candidates("certifications", "Google Data Analytics Professional Certificate")
    assert find_near_identity("certifications", "Google Data Analytics", stored) == "entity:0"


def test_certified_is_noise_anywhere_in_the_title():
    stored = _candidates("certifications", "Kubernetes Administrator")
    assert find_near_identity(
        "certifications", "Certified Kubernetes Administrator", stored
    ) == "entity:0"


def test_vendor_token_only_dropped_when_leading():
    # "amazon" leads, so the vendor tokens "aws"/"google" are ordinary tokens
    # and the two titles keep their distinguishing word.
    stored = _candidates("certifications", "Amazon AWS Practitioner")
    assert find_near_identity("certifications", "Amazon Google Practitioner", stored) is None
    # dropping a non-leading vendor would also collapse this pair:
    stored2 = _candidates("certifications", "Amazon Practitioner")
    assert find_near_identity("certifications", "Amazon AWS Practitioner", stored2) is None


def test_different_leading_vendors_never_match():
    # Both shed a leading vendor token; without a vendor guard the remainders
    # would be equal and two different vendors' certs would fuse.
    stored = _candidates("certifications", "Google Certified AI Practitioner")
    assert find_near_identity("certifications", "AWS Certified AI Practitioner", stored) is None


def test_cert_of_only_noise_tokens_never_matches():
    stored = _candidates("certifications", "Kubernetes Administrator")
    assert find_near_identity("certifications", "Professional Certificate", stored) is None


def test_differing_org_parentheticals_never_match():
    """The stored cert key is ``_cert_string`` = "title (org)" — the ISSUER
    rides in a parenthetical. Stripping every parenthetical as noise fused two
    different vendors' certs, and the leading-vendor guard cannot see it
    because the org never becomes a leading token."""
    stored = _candidates("certifications", "AI Practitioner (Google)")
    assert find_near_identity("certifications", "AI Practitioner (AWS)", stored) is None


def test_matching_org_parentheticals_match():
    stored = _candidates("certifications", "Certified AI Practitioner (AWS)")
    assert find_near_identity("certifications", "AI Practitioner (AWS)", stored) == "entity:0"


def test_one_sided_org_parenthetical_does_not_block():
    # Incoming carries no org parenthetical; the stored key does. A one-sided
    # org must not veto — the token rules still decide.
    stored = _candidates("certifications", "AWS Certified AI Practitioner (Amazon Web Services)")
    assert find_near_identity(
        "certifications", "AWS Certified AI Practitioner", stored
    ) == "entity:0"
    # ...and the mirror direction
    stored2 = _candidates("certifications", "AWS Certified AI Practitioner")
    assert find_near_identity(
        "certifications", "AWS Certified AI Practitioner (Amazon Web Services)", stored2
    ) == "entity:0"


def test_exam_code_and_org_parentheticals_are_told_apart():
    """The classification itself: a code yields no org, an issuer does."""
    # Hyphenated letter+digit runs are exam codes.
    assert _cert_signature("ai practitioner (aif-c01)")[2] is None
    assert _cert_signature("ai practitioner (az-900)")[2] is None
    assert _cert_signature("ai practitioner (dp-203i)")[2] is None
    assert _cert_signature("ai practitioner (saa-c03)")[2] is None
    # Plain words are issuers.
    assert _cert_signature("ai practitioner (aws)")[2] == "aws"
    assert _cert_signature("ai practitioner (amazon web services)")[2] == "amazon web services"
    # Code-SHAPED issuers are unhyphenated, so they stay identity.
    assert _cert_signature("security certification (isc2)")[2] == "isc2"
    assert _cert_signature("network fundamentals (3m)")[2] == "3m"
    assert _cert_signature("mobile engineer certificate (o2)")[2] == "o2"
    # Accepted consequence: an unhyphenated exam code reads as an org. Its
    # worst case is a fork, which is the safe direction.
    assert _cert_signature("ai practitioner (az900)")[2] == "az900"
    # A code carries no org, so it is always the one-sided case and matches.
    stored = _candidates("certifications", "AI Practitioner (AWS)")
    assert find_near_identity("certifications", "AI Practitioner (AIF-C01)", stored) == "entity:0"


def test_code_shaped_issuers_never_fuse():
    """Reading an org AS a code permits a false merge; the reverse only forks.

    Every real exam code in play is hyphenated and every code-shaped issuer is
    not, so the hyphen is what keeps these three pairs apart.
    """
    isc2 = _candidates("certifications", "Security Certification (CompTIA)")
    assert find_near_identity("certifications", "Security Certification (ISC2)", isc2) is None

    mmm = _candidates("certifications", "Network Fundamentals (Google)")
    assert find_near_identity("certifications", "Network Fundamentals (3M)", mmm) is None

    o2 = _candidates("certifications", "Mobile Engineer Certificate (Vodafone)")
    assert find_near_identity("certifications", "Mobile Engineer Certificate (O2)", o2) is None


def test_unhyphenated_exam_code_forks_rather_than_fuses():
    # "(AZ900)" reads as an org. Against a different one it forks -- safe.
    stored = _candidates("certifications", "Azure Fundamentals (DP900)")
    assert find_near_identity("certifications", "Azure Fundamentals (AZ900)", stored) is None


def test_exam_code_is_noise_even_when_not_the_trailing_parenthetical():
    # "title (CODE) (org)": the org is parsed off the end, the code is still
    # dropped from what remains.
    stored = _candidates("certifications", "AI Practitioner (AWS)")
    assert find_near_identity(
        "certifications", "AI Practitioner (AIF-C01) (AWS)", stored
    ) == "entity:0"


def test_nested_parentheses_leave_residue_and_fork():
    """Fail-safe: ``_CERT_ORG_RE`` uses ``[^()]+`` so a nested parenthetical
    never parses as an org. The residue becomes ordinary tokens and the pair
    forks — the safe direction, since a fork costs one merge click."""
    stored = _candidates("certifications", "AI Practitioner")
    assert find_near_identity("certifications", "AI Practitioner (Amazon (AWS))", stored) is None


# --- projects --------------------------------------------------------------


def test_project_name_subset_within_two_extra_tokens_matches():
    stored = _candidates("projects", _proj("Resume Tailor Web App"))
    assert find_near_identity("projects", _proj("Resume Tailor"), stored) == "entity:0"


def test_project_name_subset_beyond_two_extra_tokens_does_not():
    stored = _candidates("projects", _proj("Resume Tailor Web App Redesign"))
    assert find_near_identity("projects", _proj("Resume Tailor"), stored) is None


def test_project_disjoint_names_never_match():
    stored = _candidates("projects", _proj("Churn Prediction Model"))
    assert find_near_identity("projects", _proj("Resume Tailor"), stored) is None


# --- scope -----------------------------------------------------------------


def test_education_and_extra_return_none():
    edu = {"institution": "MIT", "degree": "BSc Computer Science"}
    edu_stored = _candidates("education", {"institution": "MIT", "degree": "BSc"})
    assert find_near_identity("education", edu, edu_stored) is None

    extra = {"section_key": "awards", "section_type": "entries", "title": "Dean's List 2021"}
    extra_stored = _candidates(
        "extra", {"section_key": "awards", "section_type": "entries", "title": "Dean's List"}
    )
    assert find_near_identity("extra", extra, extra_stored) is None


def test_exact_key_present_is_not_this_functions_job():
    """Pinned semantic: the matcher does not check for an exact hit.

    Callers must consult the index first and only call this on a miss. Called
    with an entry whose exact key IS present, the matcher returns that
    candidate — equality is the degenerate case of subset — rather than
    raising or returning None.
    """
    entry = _exp("TCS", "Data Analyst")
    stored = _candidates("experience", _exp("TCS", "Data Analyst"))
    assert identity_key("experience", entry) in stored
    assert find_near_identity("experience", entry, stored) == "entity:0"


def test_empty_candidates_return_none():
    assert find_near_identity("experience", _exp("TCS", "Data Analyst"), {}) is None


def test_precomputed_identity_key_is_accepted():
    """Consumers holding a Group.key pass the tuple straight through."""
    stored = _candidates("experience", _exp("TCS", "Data Analyst, British Airways Account"))
    key = identity_key("experience", _exp("TCS", "Data Analyst"))
    assert find_near_identity("experience", key, stored) == "entity:0"
