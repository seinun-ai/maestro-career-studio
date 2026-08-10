from app.services.health_guards import guard_violations, guarded_rewrite


ORIGINAL = "Responsible for ETL pipelines processing 2M rows daily using Spark and Airflow."


def test_clean_rewrite_passes():
    rewrite = "Built ETL pipelines processing 2M rows daily using Spark and Airflow."
    assert guard_violations(ORIGINAL, rewrite) == []


def test_new_number_is_fabrication():
    rewrite = "Built ETL pipelines processing 2M rows daily, cutting latency 40%."
    violations = guard_violations(ORIGINAL, rewrite)
    assert any("number" in v for v in violations)


def test_placeholder_rejected():
    violations = guard_violations(ORIGINAL, "Built pipelines, improving throughput by [X]%.")
    assert any("placeholder" in v for v in violations)


def test_dropped_entity_rejected():
    # deletes '2M' and the tool names → information loss
    violations = guard_violations(ORIGINAL, "Built data pipelines that saved time.")
    assert any("lost" in v for v in violations)


def test_magnitude_inflation_and_drop_are_caught():
    assert guard_violations("Managed 2 servers.", "Managed 2M servers.") != []   # 2 -> 2M fabrication
    assert guard_violations("Cut spend by $2K.", "Cut spend by $2M.") != []       # 1000x inflation
    assert guard_violations("Processed 2M rows.", "Processed 2 rows.") != []       # magnitude dropped = loss


def test_magnitude_preserved_passes():
    assert guard_violations("Processed 2M rows daily.", "Streamed 2M rows daily.") == []


def test_curly_and_underscore_placeholders_caught():
    assert any("placeholder" in v for v in guard_violations("Improved X.", "Improved by {N}%."))
    assert any("placeholder" in v for v in guard_violations("Improved X.", "Improved by ___ percent."))


def test_company_name_with_xx_is_not_a_placeholder():
    violations = guard_violations("Led analytics at Exxon.", "Drove analytics at Exxon.")
    assert not any("placeholder" in v for v in violations)


def test_guarded_rewrite_reprompts_once_then_gives_up(db_session, monkeypatch):
    from app.services import health_guards as hg
    answers = iter([
        {"rewrite": "Improved things by 90%."},                     # fabricates → re-prompt
        {"rewrite": "Also improved other things a lot [X]."},      # still bad → None
    ])
    monkeypatch.setattr(hg.llm, "call_openai", lambda **k: next(answers))
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")
    assert guarded_rewrite(db_session, ORIGINAL, context="") is None


def test_guarded_rewrite_returns_passing_text(db_session, monkeypatch):
    from app.services import health_guards as hg
    good = "Built ETL pipelines processing 2M rows daily using Spark and Airflow."
    monkeypatch.setattr(hg.llm, "call_openai", lambda **k: {"rewrite": good})
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")
    assert guarded_rewrite(db_session, ORIGINAL, context="") == good
