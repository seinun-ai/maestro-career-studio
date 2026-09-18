"""A Template inserted without `is_default` must come back False.

Pins the fix for a Postgres-ism that survived the SQLite port: a boolean
server_default written as the string "false" became TEXT on SQLite, so every
user-created template read as the default in Python while `IS 1` matched none.

Runs on the alembic-migrated `db_session`, not `Base.metadata.create_all`, so
it pins revision 871d0425b64c's server default (`sa.text('0')`) rather than
the model's: the two can drift, and the DB's is the one users get.
"""
import sqlalchemy as sa

from app.models.template import Template


def test_template_without_is_default_round_trips_false(db_session):
    # The kwargs template_registry passes on create: no is_default, so the
    # column takes its server default.
    db_session.add(
        Template(
            id="probe",
            display_name="Probe",
            source="x",
            engine="latex",
            status="draft",
            origin="frontend",
        )
    )
    db_session.commit()
    db_session.expunge_all()
    assert db_session.get(Template, "probe").is_default is False
    row = db_session.execute(sa.text("select typeof(is_default), is_default from templates")).one()
    assert tuple(row) == ("integer", 0)
