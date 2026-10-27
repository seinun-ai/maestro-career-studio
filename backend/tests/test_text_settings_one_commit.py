"""`text_settings.one_commit`: one transaction under SQLite's write lock, one commit at the end, the
file mirrors written only after it."""

import pytest

from app.config import settings
from app.models.setting import Setting
from app.services import text_settings


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def test_writes_land_together_and_the_mirrors_follow_the_commit(db_session, settings_dir):
    with text_settings.one_commit(db_session):
        text_settings.set_text("example_a", "a.md", "first", db_session)
        text_settings.set_text("example_b", "b.md", "second", db_session)
        assert not (settings_dir / "a.md").exists()  # not before the commit
    assert (settings_dir / "a.md").read_text() == "first"
    assert (settings_dir / "b.md").read_text() == "second"
    db_session.expire_all()
    assert db_session.get(Setting, "example_b").value == "second"


def test_a_rolled_back_block_leaves_the_row_and_its_mirror_as_they_were(db_session, settings_dir):
    text_settings.set_text("example", "example.md", "before", db_session)
    with pytest.raises(ValueError, match="refused"):
        with text_settings.one_commit(db_session):
            text_settings.set_text("example", "example.md", "after", db_session)
            raise ValueError("refused")
    assert (settings_dir / "example.md").read_text() == "before"
    db_session.expire_all()
    assert db_session.get(Setting, "example").value == "before"


@pytest.mark.parametrize("helper", ["commit", "seeding read"])
def test_a_helper_that_commits_inside_the_block_is_refused(db_session, settings_dir, helper):
    """A commit inside the block releases the write lock, so another writer could land between the
    block's read and its write; the block refuses rather than pass that off as one transaction."""
    with pytest.raises(RuntimeError, match="committed inside"):
        with text_settings.one_commit(db_session):
            text_settings.set_text("example", "example.md", "after", db_session)
            if helper == "commit":
                db_session.commit()
            else:
                text_settings.get_text("never_seeded", "never_seeded.md", db_session)  # seeds and commits
    assert not (settings_dir / "example.md").exists()  # no mirror for a block that was refused
