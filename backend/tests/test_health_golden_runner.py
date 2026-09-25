"""The golden runner's setup path, with the LLM faked below `call_openai`.

The runner evaluates on its own throwaway SQLite file. The session it passes is not the only
reader: `llm.call_openai` reads `llm.json_mode`, the API keys and the base URL through
`app.db.SessionLocal`. Run from a shell with no migrated DATABASE_URL, that global engine names
a file with no tables, and the run died on "no such table: settings" before its first call.
"""
import json
import re
from types import SimpleNamespace

import pytest

from app.db import SessionLocal, make_engine
from app.services import llm
from scripts import health_golden

_ID = re.compile(r'"id": "([0-9a-f]{16})"')


@pytest.fixture
def unmigrated_app_db(tmp_path):
    """Point the app's global SessionLocal at an EMPTY file, as an unset DATABASE_URL does."""
    previous = SessionLocal.kw.get("bind")
    empty = make_engine(f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}")
    SessionLocal.configure(bind=empty)
    try:
        yield empty
    finally:
        SessionLocal.configure(bind=previous)
        empty.dispose()


class _FakeCompletions:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        ids = _ID.findall(kwargs["messages"][0]["content"])
        body = {"classifications": [
            {"id": i, "level": "adjacent", "evidence": [], "question": None,
             "ask_kind": "detail", "reason": "fake", "confidence": 0.9} for i in ids]}
        message = SimpleNamespace(content=json.dumps(body))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def test_runner_reads_settings_from_its_own_database(unmigrated_app_db, monkeypatch, capsys):
    completions = _FakeCompletions()
    monkeypatch.setattr(llm, "_get_client",
                        lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    monkeypatch.setattr(llm, "_is_gemini_model", lambda _model: False)
    monkeypatch.delenv("LOGS_DIR", raising=False)
    monkeypatch.setattr("sys.argv", ["health_golden.py", "--split", "dev", "--trials", "1"])
    logs_before = llm.settings.logs_dir

    code = health_golden.main()

    report = json.loads(capsys.readouterr().out)
    assert code in (0, 1)   # the verdict is the fake's business; finishing is the test
    assert report["trials"] == 1 and report["rubric_version"] >= 2
    assert report["overall"]["n"] == 40
    # One batched call for the 40 bullets, then one per dispute; each went through the
    # json_mode read (auto + no base URL = JSON mode on).
    assert len(completions.calls) == 1 + 12
    assert all(c.get("response_format") == {"type": "json_object"} for c in completions.calls)
    # The app's own engine and log dir are handed back untouched.
    assert SessionLocal.kw["bind"] is unmigrated_app_db
    assert llm.settings.logs_dir == logs_before
