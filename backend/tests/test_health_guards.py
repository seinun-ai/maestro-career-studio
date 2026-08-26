from app.services.health_guards import guard_violations, guarded_rewrite


ORIGINAL = "Responsible for ETL pipelines processing 2M rows daily using Spark and Airflow."


def test_clean_rewrite_passes():
    rewrite = "Built ETL pipelines processing 2M rows daily using Spark and Airflow."
    assert guard_violations(ORIGINAL, rewrite) == []


def test_new_number_is_fabrication():
    rewrite = "Built ETL pipelines processing 2M rows daily, cutting latency 40%."
    violations = guard_violations(ORIGINAL, rewrite)
    assert any("number" in v for v in violations)


def test_candidate_supplied_number_is_allowed_with_equivalent_formatting():
    violations = guard_violations(
        "Served users with the platform.",
        "Served 5,000 users with the platform.",
        supplied="served 5000 users",
    )
    assert violations == []


def test_candidate_supplied_number_can_correct_original_quantity():
    violations = guard_violations(
        "Data leader with 10+ years of experience.",
        "Data leader with 6 years of experience.",
        supplied="6 years",
    )
    assert violations == []


def test_number_absent_from_original_and_candidate_context_is_fabrication():
    violations = guard_violations(
        "Served users with the platform.",
        "Served 5,000 users with the platform, cutting latency 40%.",
        supplied="served 5000 users",
    )
    assert any("40%" in violation for violation in violations)


def test_placeholder_rejected():
    violations = guard_violations(ORIGINAL, "Built pipelines, improving throughput by [X]%.")
    assert any("placeholder" in v for v in violations)


def test_dropped_entity_rejected():
    # deletes '2M' and the tool names → information loss
    violations = guard_violations(ORIGINAL, "Built data pipelines that saved time.")
    assert any("lost" in v for v in violations)


def test_candidate_context_does_not_allow_dropped_original_entities():
    violations = guard_violations(
        "Built ETL pipelines using Spark.",
        "Built 5 pipelines.",
        supplied="5 pipelines",
    )
    assert any("ETL" in violation and "Spark" in violation for violation in violations)


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


def test_guarded_rewrite_accepts_candidate_supplied_number(db_session, monkeypatch):
    from app.services import health_guards as hg

    rewrite = "Served 5,000 users with the platform."

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        assert "CANDIDATE CONTEXT OVERRIDE" in prompt
        assert "may be added to the rewrite" in prompt
        assert "may replace the original number" in prompt
        return {"rewrite": rewrite}

    monkeypatch.setattr(hg.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda session: "test-model")

    assert (
        guarded_rewrite(
            db_session,
            "Served users with the platform.",
            context="served 5000 users",
        )
        == rewrite
    )


def test_unattended_rewrite_is_cached_on_content_hash(db_session, monkeypatch):
    from app.models.bullet_rewrite import BulletRewrite
    from app.services import health_guards as hg

    good = "Built ETL pipelines processing 2M rows daily using Spark and Airflow."
    calls = 0

    def fake_call_openai(**kwargs):
        nonlocal calls
        calls += 1
        return {"rewrite": good}

    monkeypatch.setattr(hg.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")

    first = guarded_rewrite(db_session, ORIGINAL, context="")
    db_session.commit()
    assert first == good
    assert calls == 1
    chash = hg.bullet_classify.content_hash(ORIGINAL)
    row = db_session.get(BulletRewrite, chash)
    assert row is not None
    assert row.rewrite_text == good

    monkeypatch.setattr(
        hg.llm, "call_openai",
        lambda **k: (_ for _ in ()).throw(AssertionError("rewrite LLM should not be reached")),
    )
    assert guarded_rewrite(db_session, ORIGINAL, context="") == good
    assert calls == 1


def test_guard_rejected_unattended_rewrite_is_cached_as_none(db_session, monkeypatch):
    from app.models.bullet_rewrite import BulletRewrite
    from app.services import health_guards as hg

    calls = 0

    def fake_call_openai(**kwargs):
        nonlocal calls
        calls += 1
        return {"rewrite": "Improved things by 90%."}

    monkeypatch.setattr(hg.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")

    assert guarded_rewrite(db_session, ORIGINAL, context="") is None
    db_session.commit()
    assert calls == 2
    chash = hg.bullet_classify.content_hash(ORIGINAL)
    row = db_session.get(BulletRewrite, chash)
    assert row is not None
    assert row.rewrite_text is None

    monkeypatch.setattr(
        hg.llm, "call_openai",
        lambda **k: (_ for _ in ()).throw(AssertionError("rewrite LLM should not be reached")),
    )
    assert guarded_rewrite(db_session, ORIGINAL, context="") is None
    assert calls == 2


def test_answered_rewrite_is_not_cached_on_bullet_rewrite(db_session, monkeypatch):
    from app.models.bullet_rewrite import BulletRewrite
    from app.services import health_guards as hg

    rewrite = "Served 5,000 users with the platform."
    monkeypatch.setattr(hg.llm, "call_openai", lambda **k: {"rewrite": rewrite})
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")

    original = "Served users with the platform."
    assert guarded_rewrite(db_session, original, context="served 5000 users") == rewrite
    db_session.commit()
    assert db_session.get(BulletRewrite, hg.bullet_classify.content_hash(original)) is None


def test_condense_objective_appends_code_side_block(db_session, monkeypatch):
    from app.services import health_guards as hg

    good = "Built ETL pipelines processing 2M rows daily using Spark and Airflow."
    seen = []

    def fake_call_openai(*, prompt, model, response_format, trace_name):
        seen.append(prompt)
        return {"rewrite": good}

    monkeypatch.setattr(hg.llm, "call_openai", fake_call_openai)
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")

    assert guarded_rewrite(db_session, ORIGINAL, objective="condense") == good
    assert seen and "CONDENSE OBJECTIVE" in seen[0]
    assert "one sentence of at most ~30 words" in seen[0]


def test_condense_still_vetoes_dropped_entities(db_session, monkeypatch):
    from app.services import health_guards as hg

    monkeypatch.setattr(
        hg.llm, "call_openai",
        lambda **k: {"rewrite": "Built data pipelines that saved time."},
    )
    monkeypatch.setattr(hg.model_settings, "get_smart_model", lambda s: "test-model")
    assert guarded_rewrite(db_session, ORIGINAL, objective="condense") is None
