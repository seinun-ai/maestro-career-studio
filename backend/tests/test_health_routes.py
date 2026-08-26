"""The two health routes, and the app-logger bootstrap.

Both exist because a fresh-install agent lost time to their absence: it
guessed /api/health twenty times before finding /health, and never saw the
"api key from settings" line because nothing gave app.* loggers a handler.
"""

import logging

from fastapi.testclient import TestClient

from app.main import _ensure_app_log_handler, app


def test_health_and_api_health_agree():
    client = TestClient(app)
    plain = client.get("/health")
    alias = client.get("/api/health")
    assert plain.status_code == 200
    assert alias.status_code == 200
    assert alias.json() == plain.json() == {"status": "ok"}


def _fresh(name: str) -> logging.Logger:
    # Real Logger instances detached from the live hierarchy, so the test
    # neither observes nor mutates whatever handlers pytest itself installed.
    return logging.Logger(name)


def test_log_handler_added_when_nothing_configured():
    app_logger, root = _fresh("app"), _fresh("root")
    assert _ensure_app_log_handler(app_logger, root) is True
    assert app_logger.handlers
    # INFO must actually pass — the dropped record this bootstrap exists for
    # (`api key from settings|env`) is emitted at INFO.
    assert app_logger.isEnabledFor(logging.INFO)


def test_log_handler_defers_to_existing_config():
    # A configured root (pytest, --log-config) means records already land
    # somewhere; adding our own handler would double-log every line.
    app_logger, root = _fresh("app"), _fresh("root")
    root.addHandler(logging.NullHandler())
    assert _ensure_app_log_handler(app_logger, root) is False
    assert not app_logger.handlers

    # And an already-handled app logger is left exactly as it is.
    app_logger2, root2 = _fresh("app"), _fresh("root")
    marker = logging.NullHandler()
    app_logger2.addHandler(marker)
    assert _ensure_app_log_handler(app_logger2, root2) is False
    assert app_logger2.handlers == [marker]
