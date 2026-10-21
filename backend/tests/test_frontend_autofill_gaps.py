"""The Settings known-gaps line: its words are node-tested; the card must render and clear them."""

from pathlib import Path

from tests.node_ts import run_node_test

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CARD = (FRONTEND / "components/settings/form-filling-section.tsx").read_text()
COVERAGE = (FRONTEND / "components/settings/autofill-coverage-card.tsx").read_text()


def test_the_line_words_node():
    result = run_node_test("lib/autofill-gaps.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_form_filling_card_reads_the_gaps_summary_and_shows_no_host():
    assert '"/api/autofill/gaps/summary"' in CARD
    assert "<KnownGapsLine />" in CARD
    assert ".top" not in CARD and "host" not in CARD.split("function KnownGapsLine")[1].split("/** Jev")[0]


def test_the_gaps_line_and_the_coverage_card_share_the_fill_log_off_wording():
    """FILL_LOG_OFF_TEXT is the coverage card's empty text, sentence for sentence."""
    lib = (FRONTEND / "lib/autofill-gaps.ts").read_text()
    for sentence in ("No data yet. The fill log is off unless you turn it on.",
                     "To turn it on, right-click the Companion's toolbar icon, choose Options, "
                     "and tick Keep a fill log."):
        assert sentence in lib
        assert sentence in COVERAGE
