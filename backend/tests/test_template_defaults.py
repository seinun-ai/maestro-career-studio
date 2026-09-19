"""A Template inserted without `is_default` must come back False.

Pins the fix for a Postgres-ism that survived the SQLite port: a boolean
server_default written as the string "false" became TEXT on SQLite, so every
user-created template read as the default in Python while `IS 0` matched none.

Runs on the alembic-migrated `db_session`, not `Base.metadata.create_all`, so
it pins revision 871d0425b64c's server default (`sa.text('0')`) rather than
the model's: the two can drift, and the DB's is the one users get.
"""
import sqlalchemy as sa
from sqlalchemy import select

from app.models.template import Template


def _template(**overrides) -> Template:
    # The kwargs template_registry passes on create: no is_default, so the
    # column takes its server default.
    fields = dict(display_name="Probe", source="x", engine="latex", status="draft", origin="frontend")
    fields.update(overrides)
    return Template(**fields)


def _stored(db_session, template_id: str) -> tuple:
    row = db_session.execute(
        sa.text("select typeof(is_default), is_default from templates where id = :id"),
        {"id": template_id},
    ).one()
    return tuple(row)


def test_template_without_is_default_round_trips_false(db_session):
    db_session.add(_template(id="probe"))
    db_session.commit()
    db_session.expunge_all()
    assert db_session.get(Template, "probe").is_default is False
    assert _stored(db_session, "probe") == ("integer", 0)


def test_template_with_is_default_true_is_stored_as_integer_one(db_session):
    # The write path: the Boolean type binds True as 1, not as the text "true".
    db_session.add(_template(id="flagged", is_default=True))
    db_session.commit()
    db_session.expunge_all()
    assert db_session.get(Template, "flagged").is_default is True
    assert _stored(db_session, "flagged") == ("integer", 1)


def test_is_false_query_finds_the_default_less_row(db_session):
    # The user-visible symptom of the TEXT default: `is_default IS 0` matched
    # nothing, so every user-created template was invisible to "not default".
    db_session.add_all([_template(id="probe"), _template(id="flagged", is_default=True)])
    db_session.commit()
    db_session.expunge_all()
    rows = db_session.execute(select(Template).where(Template.is_default.is_(False))).scalars()
    assert [t.id for t in rows] == ["probe"]
