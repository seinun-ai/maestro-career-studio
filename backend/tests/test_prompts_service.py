from app.models.setting import Setting
from app.services import prompts


def test_get_prompt_seeds_from_file(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "PROMPT_DIR", tmp_path)
    (tmp_path / "qa.txt").write_text("Question prompt ${questions}", encoding="utf-8")

    result = prompts.get_prompt("qa", db_session)

    assert result == "Question prompt ${questions}"
    assert db_session.get(Setting, "prompt.qa").value == "Question prompt ${questions}"


def test_set_prompt_upserts_value(db_session):
    prompts.set_prompt("gap_tailor", "custom tailor prompt", db_session)
    prompts.set_prompt("gap_tailor", "updated tailor prompt", db_session)

    assert db_session.get(Setting, "prompt.gap_tailor").value == "updated tailor prompt"


def test_reset_prompt_restores_file_default(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "PROMPT_DIR", tmp_path)
    (tmp_path / "cover_letter.txt").write_text("default cover letter", encoding="utf-8")
    prompts.set_prompt("cover_letter", "custom", db_session)

    result = prompts.reset_prompt("cover_letter", db_session)

    assert result == "default cover letter"
    assert db_session.get(Setting, "prompt.cover_letter").value == "default cover letter"


def test_unknown_prompt_key_raises(db_session):
    try:
        prompts.get_prompt("../bad", db_session)
    except KeyError as exc:
        assert "Unknown prompt key" in str(exc)
    else:
        raise AssertionError("Expected KeyError")


def test_tailoring_skill_is_a_valid_prompt_key():
    assert "tailoring_skill" in prompts.VALID_PROMPTS


def test_tailoring_skill_file_default_loads(db_session):
    text = prompts.get_prompt("tailoring_skill", db_session)
    assert "No em dashes" in text
    assert "terse tokens" in text


def test_cold_message_prompt_retired():
    # Removed 2026-07-21: outreach is a free-form Q&A question now. Registry and
    # file must go together (seed_prompts reads a file per registered key).
    assert "cold_message" not in prompts.VALID_PROMPTS
    assert not (prompts.PROMPT_DIR / "cold_message.txt").exists()
