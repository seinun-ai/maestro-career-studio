from app.services import model_settings


def test_the_answer_level_defaults_to_backed_by_history(db_session):
    assert model_settings.get_answer_level(db_session) == "history"
    assert model_settings.get_autofill_low_stakes(db_session) is True


def test_each_level_round_trips_and_facts_only_turns_low_stakes_off(db_session):
    for level in ("facts", "history", "queued"):
        model_settings.set_answer_level(db_session, level)
        assert model_settings.get_answer_level(db_session) == level
    model_settings.set_answer_level(db_session, "facts")
    assert model_settings.get_autofill_low_stakes(db_session) is False


def test_the_options_endpoint_reads_and_writes_the_level(client):
    assert client.get("/api/settings/autofill-options").json() == {"answer_level": "history"}
    response = client.put("/api/settings/autofill-options", json={"answer_level": "queued"})
    assert response.status_code == 200 and response.json() == {"answer_level": "queued"}


def test_the_options_endpoint_refuses_an_unknown_level_or_the_old_key(client):
    assert client.put("/api/settings/autofill-options", json={"answer_level": "yolo"}).status_code == 422
    assert client.put("/api/settings/autofill-options", json={"low_stakes": True}).status_code == 422
