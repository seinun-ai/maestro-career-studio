import re

from app.services import prompt_assembly


def test_build_extraction_prompt_injects_raw_jd(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Extract this:\n${raw_jd}",
    )

    result = prompt_assembly.build_extraction_prompt("Senior data role")

    assert "Senior data role" in result


def test_build_gap_tailor_prompt_injects_user_prompt(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Resume=${resume_json}\nJD=${jd_json}${user_prompt_section}",
    )

    result = prompt_assembly.build_gap_tailor_prompt(
        {"summary": "Builder"},
        {"title": "ML Engineer"},
        resolutions=[],
        skipped_gaps=[],
        user_prompt="Emphasize RAG experience.",
    )

    assert '"summary": "Builder"' in result
    assert "Emphasize RAG experience." in result
    assert "USER PROMPT" in result


def test_build_gap_tailor_prompt_omits_empty_user_prompt(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Resume=${resume_json}${user_prompt_section}",
    )

    result = prompt_assembly.build_gap_tailor_prompt(
        {}, {}, resolutions=[], skipped_gaps=[], user_prompt="   "
    )

    # The gap_tailor body (after the prepended skill preamble + "---" separator)
    # ends here with no USER PROMPT section appended for a whitespace-only prompt.
    assert result.endswith("Resume={}")
    assert "USER PROMPT" not in result


def test_gap_tailor_prompt_allows_only_targeted_extra_section(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: (prompt_assembly.prompts.PROMPT_DIR / f"{key}.txt").read_text(
            encoding="utf-8"
        ),
    )
    target = {
        "section": "extra",
        "section_key": "volunteer",
        "index_or_category": 0,
    }

    result = prompt_assembly.build_gap_tailor_prompt(
        {
            "extra_sections": [
                {
                    "key": "volunteer",
                    "title": "Volunteer Work",
                    "type": "entries",
                    "entries": [{"heading": "Mentor", "bullets": ["Coached students"]}],
                }
            ]
        },
        {"title": "ML Engineer"},
        resolutions=[
            {
                "gap_id": "skill:pytorch",
                "action": "add_keyword",
                "payload": {"placement_target": target},
            }
        ],
        skipped_gaps=[],
    )

    assert '"section_key": "volunteer"' in result
    assert '"section": "extra"' in result
    assert "Edit a custom section ONLY when" in result
    assert "one `replace_extra_section` op" in result
    assert "A MISSING\n  skill can never target a custom section" in result


def test_build_qa_prompt_numbers_questions(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Questions:\n${questions}",
    )

    result = prompt_assembly.build_qa_prompt({}, {}, "", ["Why us?", "Can you relocate?"])

    assert "1. Why us?" in result
    assert "2. Can you relocate?" in result


def test_build_cover_letter_prompt_injects_tone(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Tone=${tone}\n${resume_json}\n${jd_json}\n${memory}",
    )

    result = prompt_assembly.build_cover_letter_prompt(
        {"summary": "Builder"}, {"company": "Acme"}, "Mention RAG.", "balanced"
    )

    assert "Tone=balanced" in result
    assert '"summary": "Builder"' in result
    assert '"company": "Acme"' in result
    assert "Mention RAG." in result


def test_build_gap_enrichment_prompt_injects_blocks(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Resume=${resume_json}\nJD=${jd_json}\nGaps=${gaps_json}",
    )

    result = prompt_assembly.build_gap_enrichment_prompt(
        {"summary": "Builder"}, {"title": "Data Scientist"}, {"gaps": [{"gap_id": "skill:aws"}]}
    )

    assert '"summary": "Builder"' in result
    assert '"title": "Data Scientist"' in result
    assert '"gap_id": "skill:aws"' in result


def test_persona_block_prepended_when_set(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Questions:\n${questions}",
    )

    result = prompt_assembly.build_qa_prompt(
        {}, {}, "", ["Why us?"], persona="Vision: ship data products."
    )

    assert "CANDIDATE PERSONA" in result
    assert "Vision: ship data products." in result
    assert result.index("CANDIDATE PERSONA") < result.index("1. Why us?")


def test_persona_block_absent_when_empty(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Questions:\n${questions}",
    )

    result = prompt_assembly.build_qa_prompt({}, {}, "", ["Why us?"], persona="   ")

    assert "CANDIDATE PERSONA" not in result


def test_gap_tailor_prompt_injects_persona(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Resume=${resume_json}${user_prompt_section}",
    )

    result = prompt_assembly.build_gap_tailor_prompt(
        {}, {}, resolutions=[], skipped_gaps=[], persona="Voice: direct."
    )

    assert "CANDIDATE PERSONA" in result
    assert "Voice: direct." in result


def test_gap_tailor_prompt_prepends_skill_doc(db_session):
    # Uses the real prompts.get_prompt (no monkeypatch); db_session guarantees the
    # test DB is available so the tailoring_skill key lazy-seeds from its file.
    p = prompt_assembly.build_gap_tailor_prompt({"summary": "x"}, {"skills": []}, [], [])

    assert "JUDGMENT RULES FOR RESUME TAILORING" in p
    assert p.index("JUDGMENT RULES FOR RESUME TAILORING") < p.index("You are tailoring a resume")


def test_gap_enrichment_prompt_prepends_skill_doc(db_session):
    p = prompt_assembly.build_gap_enrichment_prompt({"summary": "x"}, {"skills": []}, {"gaps": []})

    assert "JUDGMENT RULES FOR RESUME TAILORING" in p


def test_build_qa_prompt_injects_referral_section(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Memory=${memory}${referral_section}\nQuestions:\n${questions}",
    )

    result = prompt_assembly.build_qa_prompt(
        {},
        {},
        "ctx",
        ["Why us?"],
        referral={"company": "Acme", "contact_name": "Sam Lee", "notes": "met at PyData"},
    )

    assert "KNOWN CONTACT for this application: Sam Lee at Acme." in result
    assert "met at PyData" in result


def test_build_qa_prompt_omits_referral_section_when_absent(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Questions:\n${questions}${referral_section}",
    )

    result = prompt_assembly.build_qa_prompt({}, {}, "", ["Why us?"])

    assert "KNOWN CONTACT" not in result
    assert result.endswith("1. Why us?")


def test_referral_section_renders_outreach_only_guardrail(monkeypatch):
    # The linked contact is injected into EVERY application-level QA batch; the
    # rendered section must tell the model to keep the contact out of ordinary
    # screening answers.
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "${referral_section}",
    )

    result = prompt_assembly.build_qa_prompt(
        {},
        {},
        "",
        ["Why us?"],
        referral={"company": "Acme", "contact_name": "Sam Lee"},
    )

    assert "outreach-style requests only" in result
    assert (
        "never mention or address the contact in ordinary screening answers"
        in result
    )


def test_referral_section_guardrail_absent_without_referral(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Q:${referral_section}",
    )

    result = prompt_assembly.build_qa_prompt({}, {}, "", ["Why us?"])

    assert "outreach-style requests only" not in result


def test_qa_prompt_file_has_referral_placeholder_and_anti_fabrication_rule():
    # Transplanted from the retired outreach prompt before its deletion (design doc Item 1).
    text = (prompt_assembly.prompts.PROMPT_DIR / "qa.txt").read_text(encoding="utf-8")
    assert "${referral_section}" in text
    assert "never invent experience" in text


def test_qa_prompt_prepends_immutable_output_contract(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts, "get_prompt", lambda key: "Just answer:\n${questions}"
    )

    result = prompt_assembly.build_qa_prompt(
        {}, {}, "", ["Why us?"], persona="Voice: direct."
    )

    assert result.startswith(prompt_assembly.QA_OUTPUT_CONTRACT)
    assert "plain text" in prompt_assembly.QA_OUTPUT_CONTRACT.lower()
    assert "never restate" in prompt_assembly.QA_OUTPUT_CONTRACT.lower()
    assert "fabricate" in prompt_assembly.QA_OUTPUT_CONTRACT.lower()
    assert result.index(prompt_assembly.QA_OUTPUT_CONTRACT) < result.index(
        "CANDIDATE PERSONA"
    )
    assert "1. Why us?" in result


def test_cover_letter_prompt_prepends_immutable_output_contract(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts,
        "get_prompt",
        lambda key: "Tone=${tone}\nWrite the letter.",
    )

    result = prompt_assembly.build_cover_letter_prompt(
        {}, {}, "", "balanced", persona="Voice: direct."
    )

    assert result.startswith(prompt_assembly.COVER_LETTER_OUTPUT_CONTRACT)
    assert result.index(prompt_assembly.COVER_LETTER_OUTPUT_CONTRACT) < result.index(
        "CANDIDATE PERSONA"
    )
    assert "Tone=balanced" in result


def test_cover_letter_output_contract_forbids_fabrication_and_dashes():
    contract = prompt_assembly.COVER_LETTER_OUTPUT_CONTRACT.lower()
    assert "never" in contract
    assert "fabricat" in contract or "absent" in contract
    assert "em-dash" in contract or "em dash" in contract
    assert "en-dash" in contract or "en dash" in contract
    assert "plain" in contract
    assert "tone" in contract


def test_qa_output_contract_requires_numbering_without_number_prohibition():
    # The contract must REQUIRE the numbered-answer format that qa.py's
    # _split_numbered_answers relies on for multi-question batches — and must
    # NOT carry the old bare "Never ... number" prohibition that contradicted it.
    contract = prompt_assembly.QA_OUTPUT_CONTRACT.lower()
    assert "numbered list" in contract
    assert re.search(r"never[^.\n]*\bnumber", contract) is None


def test_build_qa_prompt_carries_numbering_requirement(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts, "get_prompt", lambda key: "${questions}"
    )

    result = prompt_assembly.build_qa_prompt({}, {}, "", ["Why us?", "Relocate?"]).lower()

    assert "numbered list" in result
    assert re.search(r"never[^.\n]*\bnumber", result) is None


def test_the_choose_contract_is_prepended_and_demands_abstention(db_session):
    # Uses the real prompts.get_prompt (no monkeypatch); db_session guarantees
    # the test DB is available so the autofill_choose key lazy-seeds from its
    # file, same pattern as test_gap_tailor_prompt_prepends_skill_doc above.
    prompt = prompt_assembly.build_autofill_choose_prompt(
        profile={"personal": {"first_name": "Sample"}},
        memory="",
        fields=[
            {
                "qid": "a-0",
                "label": "Notice period",
                "kind": "text",
                "options": [],
                "known_value": None,
            }
        ],
    )
    assert prompt.startswith(prompt_assembly.CHOOSE_OUTPUT_CONTRACT)
    assert "null" in prompt.lower()


def test_options_and_known_value_reach_the_prompt_verbatim(db_session):
    """The model sees the strings the PAGE rendered, not a normalized form."""
    prompt = prompt_assembly.build_autofill_choose_prompt(
        profile={},
        memory="",
        fields=[
            {
                "qid": "a-0",
                "label": "Country",
                "kind": "combobox",
                "options": ["USA (US)", "United Kingdom (UK)"],
                "known_value": "United States",
            }
        ],
    )
    assert "USA (US)" in prompt and "United States" in prompt


def test_every_qid_appears_so_the_model_can_key_its_reply(db_session):
    prompt = prompt_assembly.build_autofill_choose_prompt(
        profile={},
        memory="",
        fields=[
            {"qid": "a-0", "label": "x", "kind": "text", "options": [], "known_value": None},
            {"qid": "a-1", "label": "y", "kind": "text", "options": [], "known_value": None},
        ],
    )
    assert "a-0" in prompt and "a-1" in prompt
