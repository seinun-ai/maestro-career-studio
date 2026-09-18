"""A Template inserted without `is_default` must come back False.

Pins the fix for a Postgres-ism that survived the SQLite port: a boolean
server_default written as the string "false" became TEXT on SQLite, so every
user-created template read as the default in Python while `IS 1` matched none.
"""
from sqlalchemy.orm import Session

from app.db import Base, make_engine
from app.models.template import Template


def test_template_without_is_default_round_trips_false(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            # The kwargs template_registry passes on create: no is_default, so
            # the column takes its server default.
            session.add(
                Template(
                    id="probe",
                    display_name="Probe",
                    source="x",
                    engine="latex",
                    status="draft",
                    origin="frontend",
                )
            )
            session.commit()
            session.expunge_all()
            assert session.get(Template, "probe").is_default is False
        with engine.connect() as conn:
            row = conn.exec_driver_sql("select typeof(is_default), is_default from templates").one()
            assert tuple(row) == ("integer", 0)
    finally:
        engine.dispose()
