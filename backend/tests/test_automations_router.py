import inspect

from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def test_catalog_endpoint_shape():
    r = client.get("/api/automations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"cards", "apps"}
    card = data["cards"][0]
    assert set(card) == {"id", "title", "summary", "kind", "needs", "never", "body"}
    app_ = data["apps"][0]
    assert set(app_) == {"id", "label", "reachable", "preamble", "attended_preamble", "note"}


def test_startup_validates_the_cards():
    assert "automation_prompts.load_cards()" in inspect.getsource(main.lifespan)
