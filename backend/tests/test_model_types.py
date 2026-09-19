"""app.models.types: the one place a column type is chosen."""
import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.models.types import JSONDoc, UTCDateTime, UUIDType


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    stamped: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=sa.func.now())
    doc: Mapped[dict | None] = mapped_column(JSONDoc)
    ref: Mapped[uuid.UUID | None] = mapped_column(UUIDType(as_uuid=True))


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite://", future=True)
    _Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_aware_datetime_round_trips_as_utc(session):
    ist = timezone(timedelta(hours=5, minutes=30))
    session.add(_Row(id=1, at=datetime(2026, 9, 17, 12, 0, tzinfo=ist)))
    session.commit()
    session.expunge_all()
    got = session.get(_Row, 1).at
    assert got.tzinfo == UTC
    assert got == datetime(2026, 9, 17, 6, 30, tzinfo=UTC)


def test_naive_datetime_is_refused(session):
    session.add(_Row(id=2, at=datetime(2026, 1, 1)))
    with pytest.raises(sa.exc.StatementError, match="naive datetime"):
        session.commit()


def test_non_datetime_is_refused(session):
    # date is not a datetime subclass; without the guard it would reach the
    # tzinfo check and fail with an unrelated AttributeError.
    session.add(_Row(id=5, at=date(2026, 1, 1)))
    with pytest.raises(sa.exc.StatementError, match="expects datetime"):
        session.commit()


def test_server_default_reads_back_aware(session):
    session.add(_Row(id=3))
    session.commit()
    session.expunge_all()
    got = session.get(_Row, 3).stamped
    assert got.tzinfo == UTC
    assert abs(datetime.now(UTC) - got) < timedelta(minutes=5)


def test_json_and_uuid_round_trip(session):
    ref = uuid.uuid4()
    session.add(_Row(id=4, doc={"b": [1, 2], "a": None}, ref=ref))
    session.commit()
    session.expunge_all()
    row = session.get(_Row, 4)
    assert row.doc == {"b": [1, 2], "a": None}
    assert row.ref == ref and isinstance(row.ref, uuid.UUID)
    # The on-disk shape the design relies on: CHAR(32) hex text, not a blob.
    on_disk = session.execute(sa.text("select ref, typeof(ref) from rows where id = 4")).one()
    assert on_disk == (ref.hex, "text")
