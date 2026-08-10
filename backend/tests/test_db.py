def test_session_factory_creates_session():
    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s is not None
