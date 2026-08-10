import pytest
from app.services import prompts

KB_KEYS = ["kb_mint", "kb_capture", "kb_entity_resolve", "kb_cluster_points", "kb_resume_parse"]

@pytest.mark.parametrize("key", KB_KEYS)
def test_kb_prompt_registered_and_nonempty(key):
    assert key in prompts.VALID_PROMPTS
    text = prompts._file_default(key)
    assert text.strip(), f"{key} prompt file is empty"

def test_kb_prompt_placeholders_present():
    # spot-check that key placeholders exist in the files (guards against typos the services rely on)
    assert "$entity_context" in prompts._file_default("kb_mint")
    assert "$document_text" in prompts._file_default("kb_mint")
    assert "$entity_list" in prompts._file_default("kb_capture")
    assert "$dump_text" in prompts._file_default("kb_capture")
    assert "$groups" in prompts._file_default("kb_entity_resolve")
    assert "$bullets" in prompts._file_default("kb_cluster_points")
    assert "$resume_text" in prompts._file_default("kb_resume_parse")
