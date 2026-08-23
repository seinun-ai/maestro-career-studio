from app.services.explore_skills import classify_skill_rows


def _row(name: str, n: int, *, required: int = 0, preferred: int = 0, mentioned: int = 0):
    return {
        "skill_name": name,
        "skill_category": "language",
        "n": n,
        "n_required": required,
        "n_preferred": preferred,
        "n_mentioned": mentioned,
    }


def test_classify_top_thirty_percent_by_rank():
    rows = [_row(f"Skill{i}", 10 - i) for i in range(10)]
    result = classify_skill_rows(rows, total_jobs=10)

    top = [row for row in result if row["tier"] == "top"]
    below = [row for row in result if row["tier"] == "below"]

    assert len(top) == 3
    assert len(below) == 7
    assert [row["skill_name"] for row in top] == ["Skill0", "Skill1", "Skill2"]


def test_classify_core_vs_preferred_within_top_tier():
    rows = [
        _row("Python", 10, required=8, preferred=2),
        _row("PyTorch", 9, required=2, preferred=7),
        _row("SQL", 8, required=4, preferred=4),
        *[_row(f"Tail{i}", 1) for i in range(7)],
    ]
    result = classify_skill_rows(rows, total_jobs=10)

    by_name = {row["skill_name"]: row for row in result}
    assert by_name["Python"]["bucket"] == "core"
    assert by_name["PyTorch"]["bucket"] == "preferred_top"
    assert by_name["SQL"]["bucket"] == "core"
    assert by_name["Tail0"]["bucket"] == "below_threshold"


def test_classify_assigns_rank_percentile():
    rows = [_row("A", 3), _row("B", 2), _row("C", 1)]
    result = classify_skill_rows(rows, total_jobs=3)

    assert result[0]["rank"] == 1
    assert result[0]["rank_percentile"] == 100.0
    assert result[-1]["rank_percentile"] == 33.33


def test_classify_flags_low_sample_when_skill_n_below_five():
    rows = [_row("Python", 10), _row("Rare", 2), _row("Once", 1)]
    result = classify_skill_rows(rows, total_jobs=10)
    by_name = {row["skill_name"]: row for row in result}
    assert by_name["Python"]["low_sample"] is False
    assert by_name["Rare"]["low_sample"] is True
    assert by_name["Once"]["low_sample"] is True


def test_classify_flags_every_row_when_corpus_is_below_five():
    rows = [_row("Python", 3), _row("SQL", 2)]
    result = classify_skill_rows(rows, total_jobs=3)
    assert all(row["low_sample"] is True for row in result)
