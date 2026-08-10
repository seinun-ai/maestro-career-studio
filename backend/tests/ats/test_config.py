import pytest

from app.services.ats import config


def test_load_config_returns_versioned_config():
    cfg = config.load_config()
    assert cfg.weights["composite_weights"]["keyword"] > 0
    assert abs(sum(cfg.weights["composite_weights"].values()) - 1.0) < 1e-9
    assert isinstance(cfg.version, str) and len(cfg.version) == 12
    # deterministic: same call, same version
    assert config.load_config().version == cfg.version


def test_engine_version_constant():
    # Bumped from 2.2.0 because folding Latin accents changes which terms match,
    # so scores produced before and after the matcher change are not comparable;
    # compare() must refuse to mix them (SYSTEM.md §4 compare() guard).
    assert config.ENGINE_VERSION == "ats-2.5.0"


def test_phase2_extra_section_evidence_config_is_explicit_and_versioned():
    cfg = config.load_config()
    assert cfg.weights["scoring_config_version"] == "ats-config-4"
    extras = cfg.weights["extra_section_evidence"]
    assert extras == {
        "placement_tier": "extra_only",
        "placement_multiplier": 0.8,
        "evidence_fields": {
            "entries": ["heading", "subheading", "bullets"],
            "bullets": ["bullets"],
        },
    }
    # Uncalibrated default stays conservatively below dated project/work prose.
    assert (
        cfg.weights["placement_multipliers"]["undated_only"]
        < extras["placement_multiplier"]
        < cfg.weights["placement_multipliers"]["experience_only"]
    )


def test_config_version_changes_when_extra_evidence_weight_changes(monkeypatch):
    import copy

    baseline = config.load_config().version
    real_load_yaml = config._load_yaml

    def fake_load_yaml(name):
        data = real_load_yaml(name)
        if name == "weights.yaml":
            data = copy.deepcopy(data)
            data["extra_section_evidence"]["placement_multiplier"] = 0.7
        return data

    monkeypatch.setattr(config, "_load_yaml", fake_load_yaml)
    config.load_config.cache_clear()
    try:
        assert config.load_config().version != baseline
    finally:
        config.load_config.cache_clear()


@pytest.mark.parametrize(
    ("multiplier", "ok"),
    [
        (0.7, True),      # a normal conservative value passes
        (0.8, True),      # the shipped default
        (0.999, True),    # just under the ceiling is fine
        (1.0, False),     # == experience_only tier: rejected (must be STRICTLY < 1)
        (1.5, False),     # above 1: rejected
        (0.0, False),     # not > 0: rejected
        (-0.1, False),    # negative: rejected
        (True, False),    # bool is an int subclass; must NOT sneak through as 1.0
        (False, False),   # bool, also == 0.0: rejected
        ("0.8", False),   # non-numeric: rejected
    ],
)
def test_placement_multiplier_must_be_strictly_between_0_and_1(monkeypatch, multiplier, ok):
    import copy

    real_load_yaml = config._load_yaml

    def fake_load_yaml(name):
        data = real_load_yaml(name)
        if name == "weights.yaml":
            data = copy.deepcopy(data)
            data["extra_section_evidence"]["placement_multiplier"] = multiplier
        return data

    monkeypatch.setattr(config, "_load_yaml", fake_load_yaml)
    config.load_config.cache_clear()
    try:
        if ok:
            cfg = config.load_config()
            assert cfg.weights["extra_section_evidence"]["placement_multiplier"] == multiplier
        else:
            with pytest.raises(ValueError, match=r"placement_multiplier must be a number in \(0, 1\)"):
                config.load_config()
    finally:
        config.load_config.cache_clear()


def test_load_config_rejects_arbitrary_extra_evidence_fields(monkeypatch):
    import copy

    real_load_yaml = config._load_yaml

    def fake_load_yaml(name):
        data = real_load_yaml(name)
        if name == "weights.yaml":
            data = copy.deepcopy(data)
            data["extra_section_evidence"]["evidence_fields"]["entries"].append("date")
        return data

    monkeypatch.setattr(config, "_load_yaml", fake_load_yaml)
    config.load_config.cache_clear()
    try:
        with pytest.raises(ValueError, match="unsupported extra-section evidence fields"):
            config.load_config()
    finally:
        config.load_config.cache_clear()


def test_semantic_config_block():
    cfg = config.load_config()
    semantic = cfg.weights["semantic"]
    assert semantic["model"] == "BAAI/bge-small-en-v1.5"
    assert 0.0 < semantic["match_threshold"] < 1.0
    # semantic credit sits strictly between adjacency (0.5) and exact (1.0)
    assert 0.5 < semantic["match_credit"] < 1.0


def test_semantic_two_threshold_config():
    semantic = config.load_config().weights["semantic"]
    # generic-anchor floor is stricter than the base match threshold (Task 8)
    assert semantic["generic_anchor_threshold"] > semantic["match_threshold"]
    assert 0.0 < semantic["generic_anchor_threshold"] < 1.0
    anchors = semantic["generic_anchors"]
    assert isinstance(anchors, list) and "data" in anchors
    # 'statistical' is deliberately NOT generic — it anchors real variants
    assert "statistical" not in anchors


def test_composite_weights_include_semantic_fit():
    cfg = config.load_config()
    assert "semantic_fit" in cfg.weights["composite_weights"]
    assert abs(sum(cfg.weights["composite_weights"].values()) - 1.0) < 1e-9


def test_config_version_changes_when_semantic_model_changes(monkeypatch):
    import copy

    baseline = config.load_config().version
    real_load_yaml = config._load_yaml

    def fake_load_yaml(name):
        data = real_load_yaml(name)
        if name == "weights.yaml":
            data = copy.deepcopy(data)
            data["semantic"]["model"] = "some/other-model-rev2"
        return data

    monkeypatch.setattr(config, "_load_yaml", fake_load_yaml)
    config.load_config.cache_clear()
    try:
        # model id is version-relevant: swapping it must invalidate comparability
        assert config.load_config().version != baseline
    finally:
        config.load_config.cache_clear()


def test_load_config_rejects_bad_composite_weights(monkeypatch):
    real_load_yaml = config._load_yaml

    def fake_load_yaml(name):
        if name == "weights.yaml":
            return {"composite_weights": {"keyword": 0.5, "title": 0.4}}
        return real_load_yaml(name)

    monkeypatch.setattr(config, "_load_yaml", fake_load_yaml)
    config.load_config.cache_clear()
    try:
        with pytest.raises(ValueError, match="composite_weights"):
            config.load_config()
    finally:
        config.load_config.cache_clear()
