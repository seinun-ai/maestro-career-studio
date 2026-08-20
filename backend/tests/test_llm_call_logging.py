"""What the LLM call log is allowed to keep.

SEC-08, 2026-08-19 audit. `_log_call` wrote the full prompt and the full
response as JSON on EVERY attempt, and it sits outside the
`tracing.generation` context manager, so it ran whether or not Langfuse was
configured. Those files are a permanent second copy of every resume, job
description, work-authorization answer and generated screening answer — in a
directory any backup sweeps up, with no rotation, no retention, no `0600`, and
no way for the user to purge it.

For a product whose whole claim is local-first privacy, that default was the
loudest contradiction in the repo.

The default is now metadata: what was called, how long it took, whether it
worked, and a hash. Content capture is opt-in, announced, and still nobody's
default. Rotation, a purge endpoint and a UI control are deliberately NOT here
— they are P2, and the default flip plus file permissions are what make the
SHIPPED default honest.
"""

import json
import os
import stat
from pathlib import Path

import pytest

from app.services import llm


# Stand-ins for the four kinds of thing that must never land in a log file by
# default. Each is a real category from the audit's asset list.
RESUME_TEXT = "Morgan Example led the SEINUN-CANARY migration at Acme"
JD_TEXT = "We are hiring a data scientist to own the CANARY-JD pipeline"
ANSWER_TEXT = "I am authorized to work in the CANARY-COUNTRY without sponsorship"
PROMPT = f"{RESUME_TEXT}\n\n{JD_TEXT}"


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(llm.settings, "logs_dir", str(tmp_path))
    return tmp_path / "llm_calls"


def _entries(log_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(log_dir.glob("*.json"))]


def test_the_default_log_keeps_no_prompt_and_no_response(log_dir, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_log_content", False)

    llm._log_call(PROMPT, "gpt-5.6-luna", ANSWER_TEXT, 1)

    entries = _entries(log_dir)
    assert len(entries) == 1
    blob = json.dumps(entries[0])
    for secret in ("SEINUN-CANARY", "CANARY-JD", "CANARY-COUNTRY"):
        assert secret not in blob, f"{secret} reached the log file"
    assert "prompt" not in entries[0]
    assert "response" not in entries[0]


def test_the_default_log_still_says_enough_to_debug_with(log_dir, monkeypatch):
    """Metadata-only must not mean useless — this is the operational half."""
    monkeypatch.setattr(llm.settings, "llm_log_content", False)

    llm._log_call(PROMPT, "gpt-5.6-luna", ANSWER_TEXT, 2)

    entry = _entries(log_dir)[0]
    assert entry["model"] == "gpt-5.6-luna"
    assert entry["attempt"] == 2
    assert entry["prompt_chars"] == len(PROMPT)
    assert entry["response_chars"] == len(ANSWER_TEXT)
    assert entry["timestamp"]
    # A hash lets you prove two calls sent the same prompt without keeping it.
    assert len(entry["prompt_sha256"]) == 64
    assert len(entry["response_sha256"]) == 64


def test_the_hash_identifies_a_prompt_without_storing_it(log_dir, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_log_content", False)

    llm._log_call(PROMPT, "m", "a", 1)
    llm._log_call(PROMPT, "m", "b", 1)
    llm._log_call("a different prompt entirely", "m", "c", 1)

    first, second, third = _entries(log_dir)
    assert first["prompt_sha256"] == second["prompt_sha256"]
    assert third["prompt_sha256"] != first["prompt_sha256"]


def test_opting_in_captures_content(log_dir, monkeypatch):
    """The debug mode still has to work, or people will patch it back out."""
    monkeypatch.setattr(llm.settings, "llm_log_content", True)

    llm._log_call(PROMPT, "gpt-5.6-luna", ANSWER_TEXT, 1)

    entry = _entries(log_dir)[0]
    assert entry["prompt"] == PROMPT
    assert entry["response"] == ANSWER_TEXT


@pytest.mark.parametrize("opted_in", [False, True])
def test_log_files_are_readable_only_by_their_owner(log_dir, monkeypatch, opted_in):
    """Whatever is in them, nobody else on the machine gets to read it."""
    monkeypatch.setattr(llm.settings, "llm_log_content", opted_in)

    llm._log_call(PROMPT, "m", ANSWER_TEXT, 1)

    path = next(log_dir.glob("*.json"))
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"mode was {mode:o}"


def test_content_logging_is_off_unless_asked_for():
    """The SHIPPED default is the only one most people will ever run."""
    from app.config import Settings

    assert Settings.model_fields["llm_log_content"].default is False
