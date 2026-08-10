"""The metrics half of scripts/template_parity.py, exercised on the seeds."""
import json
import os
import shutil
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from scripts import template_parity
from scripts.template_parity import (
    golden_verdict,
    normalized_word_sequence,
    pdf_metrics,
    render_template_pdf,
)

# The parity CLI resolves `scripts.template_parity` relative to the backend
# package root; tests must not depend on pytest's CWD (repo root is canonical).
_BACKEND_DIR = Path(__file__).resolve().parents[1]

# Anchored on this file, never on the CWD: these run at COLLECTION time, so a
# relative path makes `pytest` from the repo root fail before a single test.
BACKEND_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"
EXAMPLE_PATH = BACKEND_DIR.parent / "base_resumes" / "example.json"
EXAMPLE = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

# Spelled out rather than imported from the script: the shape of a skipped row
# is the contract these tests exist to pin, so it gets an independent literal.
FAILURE_ROW = {
    "pages_latex": -1,
    "pages_typst": -1,
    "words_only_latex": -1,
    "words_only_typst": -1,
    "joined_latex": -1,
    "joined_typst": -1,
    "missing_src_latex": -1,
    "missing_src_typst": -1,
    "em_dashes_template_latex": -1,
    "em_dashes_template_typst": -1,
    "em_dashes_source": -1,
    "ok": False,
}


def _example_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    shutil.copyfile(EXAMPLE_PATH, corpus_dir / "example.json")
    return corpus_dir


def _stub_corpus(tmp_path, words=("same",), summary=None):
    """A corpus whose source text is exactly known.

    The corpus tests below stub the RENDER, so the resume on disk still drives
    the source-anchored columns (missing_src_*, em_dashes_*). Building the
    resume out of `words` keeps those columns at 0 unless the test is aiming at
    them, instead of leaking example.json's 230 source tokens into every
    assertion.
    """
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    resume = {
        "contact": {
            "name": " ".join(words),
            # Every token in the address repeats words[0], so the contact block
            # contributes no source token beyond `words`.
            "email": f"{words[0]}@{words[0]}.{words[0]}",
        }
    }
    if summary is not None:
        resume["summary"] = summary
    (corpus_dir / "example.json").write_text(
        json.dumps(resume), encoding="utf-8"
    )
    return corpus_dir


def _pdf_with_text(path, text):
    """A one-page PDF holding `text` — no LaTeX/Typst compile involved.

    Built with `tests.pdf_fixtures`, which exists for exactly this and is
    already typst-backed. It previously used PyMuPDF (`fitz`) — AGPL-3.0,
    never a declared dependency, and incompatible with this project's Apache
    2.0 licence — which also meant these tests only passed where someone
    happened to have it installed.
    """
    from tests import pdf_fixtures

    path = Path(path)
    path.write_bytes(
        pdf_fixtures.text_pdf_bytes(text) if text else pdf_fixtures.blank_pdf_bytes()
    )
    return path


def _metrics(*, pdfplumber_words, pdfium_words, pages=1, em_dashes=0):
    return {
        "pages": pages,
        "line_count": 1,
        "left": 1.0,
        "width": 1.0,
        "font_sizes": [10.0],
        "fontnames": ["TestFont"],
        "section_tops": {"summary": 1.0},
        "words_pdfplumber": pdfplumber_words,
        "words_pdfium": pdfium_words,
        "em_dashes": em_dashes,
        "joined_suspects": 0,
    }


def _stub_corpus_render(monkeypatch, metrics_by_engine):
    def fake_render(source, engine, resume, formatting, out_dir, stem):
        return out_dir / f"{engine}.pdf"

    monkeypatch.setattr(template_parity, "render_template_pdf", fake_render)
    monkeypatch.setattr(
        template_parity,
        "pdf_metrics",
        lambda path: metrics_by_engine[path.stem],
    )


def test_metrics_extraction_on_latex_seed(tmp_path):
    pdf = render_template_pdf(
        (TEMPLATE_DIR / "resume.tex.j2").read_text(), "latex", EXAMPLE, None,
        tmp_path, "seed_latex",
    )
    m = pdf_metrics(pdf)
    assert m["pages"] >= 1
    assert m["line_count"] > 20
    assert m["left"] > 0 and m["width"] > 400
    assert m["section_tops"]  # dict of lowercase section title -> top
    assert m["em_dashes"] == 0
    assert isinstance(m["words_pdfplumber"], list) and m["words_pdfplumber"]
    assert isinstance(m["words_pdfium"], list) and m["words_pdfium"]


def test_metrics_extraction_on_typst_seed(tmp_path):
    pdf = render_template_pdf(
        (TEMPLATE_DIR / "typst_classic.typ").read_text(), "typst", EXAMPLE, None,
        tmp_path, "seed_typst",
    )
    m = pdf_metrics(pdf)
    assert m["pages"] >= 1
    assert m["line_count"] > 20


def test_corpus_report_contains_counts_and_flags_only(tmp_path):
    corpus_dir = _example_corpus(tmp_path)

    report = template_parity.run_corpus(corpus_dir)

    assert set(report) == {"example"}
    assert set(report["example"]) == {
        "pages_latex",
        "pages_typst",
        "words_only_latex",
        "words_only_typst",
        "joined_latex",
        "joined_typst",
        "missing_src_latex",
        "missing_src_typst",
        "em_dashes_template_latex",
        "em_dashes_template_typst",
        "em_dashes_source",
        "ok",
    }
    assert all(type(value) in {int, bool} for value in report["example"].values())
    assert report["example"]["ok"] is True
    # The absolute source check passes on a REAL pair of renders, not just on
    # stubs: every source word of example.json reaches both PDFs.
    assert report["example"]["missing_src_latex"] == 0
    assert report["example"]["missing_src_typst"] == 0


def test_empty_corpus_is_evidence_unavailable(tmp_path, capsys):
    corpus_dir = tmp_path / "empty"
    corpus_dir.mkdir()

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report == {}
    assert captured.out.splitlines()[-1] == "EVIDENCE UNAVAILABLE"
    assert "CLEAN" not in captured.out


def test_invalid_corpus_warning_does_not_expose_resume_text(tmp_path, capsys):
    corpus_dir = tmp_path / "invalid"
    corpus_dir.mkdir()
    secret = "Private Person private.person@example.test"
    (corpus_dir / "private.json").write_text(secret)

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report == {"private": FAILURE_ROW}
    assert captured.err == "warning: private: invalid resume; skipped\n"
    assert captured.out.splitlines()[-1] == "1 resumes flagged"
    assert secret not in captured.out + captured.err
    assert "CLEAN" not in captured.out


def test_render_failure_is_generic_and_removes_temporary_artifacts(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _example_corpus(tmp_path)
    secret = "Private Person compiler diagnostic private.person@example.test"
    artifacts = []

    def failing_render(source, engine, resume, formatting, out_dir, stem):
        artifact = out_dir / "rendered-source-with-pii.tex"
        artifact.write_text(secret)
        artifacts.append(artifact)
        raise RuntimeError(secret)

    monkeypatch.setattr(template_parity, "render_template_pdf", failing_render)

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report == {"example": FAILURE_ROW}
    assert captured.err == "warning: example: render failed; skipped\n"
    assert captured.out.splitlines()[-1] == "1 resumes flagged"
    assert secret not in captured.out + captured.err
    assert artifacts and not artifacts[0].parent.exists()


def test_corpus_aggregates_evidence_from_both_extractors(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _stub_corpus(tmp_path)
    _stub_corpus_render(
        monkeypatch,
        {
            "latex": _metrics(
                pdfplumber_words=["same", "pdf-only", "dataEngineer"],
                pdfium_words=["same", "fitz-only", "dataEngineer"],
            ),
            "typst": _metrics(
                pdfplumber_words=["same", "pdf-typst"],
                pdfium_words=["same", "fitz-typst"],
            ),
        },
    )

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    # words_only_* is now the MAX over the two extractors, not their sum (it
    # was 4/2 when summed). Each extractor independently reads the SAME pair
    # of documents and sees the same 2-for-1 divergence, so summing reported
    # one divergence twice; joined_* and the em-dash counts already used max.
    assert report["example"] == {
        "pages_latex": 1,
        "pages_typst": 1,
        "words_only_latex": 2,
        "words_only_typst": 1,
        "joined_latex": 1,
        "joined_typst": 0,
        "missing_src_latex": 0,
        "missing_src_typst": 0,
        "em_dashes_template_latex": 0,
        "em_dashes_template_typst": 0,
        "em_dashes_source": 0,
        "ok": False,
    }
    assert captured.out.splitlines()[-1] == "1 resumes flagged"


def test_corpus_compares_normalized_token_sequences_not_multisets(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _stub_corpus(tmp_path, words=("one", "two"))
    _stub_corpus_render(
        monkeypatch,
        {
            "latex": _metrics(
                pdfplumber_words=["one", "two"],
                pdfium_words=["one", "two"],
            ),
            "typst": _metrics(
                pdfplumber_words=["two", "one"],
                pdfium_words=["two", "one"],
            ),
        },
    )

    report = template_parity.run_corpus(corpus_dir)

    # 1, not 2: max over the extractors (see the aggregation note above). A
    # reordering is still one word moved on each side, so both stay nonzero.
    assert report["example"]["words_only_latex"] == 1
    assert report["example"]["words_only_typst"] == 1
    assert report["example"]["ok"] is False
    assert capsys.readouterr().out.splitlines()[-1] == "1 resumes flagged"


def test_normalized_word_sequence_ignores_separator_glyph_differences():
    assert normalized_word_sequence(
        ["March", "2022", "--", "Present", "GitHub"]
    ) == normalized_word_sequence(
        ["March", "2022", "\N{EN DASH}", "Present", "GitHub"]
    )


def test_joined_suspects_exclude_source_camelcase_and_flag_new_joins():
    assert template_parity._joined_suspect_count(
        ["GitHub", "OpenTelemetry", "TypeScript", "dataEngineer"],
        source_words={"GitHub", "OpenTelemetry", "TypeScript"},
    ) == 1


def test_corpus_prints_clean_only_for_zero_evidence(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _stub_corpus(tmp_path)
    clean = _metrics(
        pdfplumber_words=["same"],
        pdfium_words=["same"],
    )
    _stub_corpus_render(monkeypatch, {"latex": clean, "typst": clean})

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report["example"]["ok"] is True
    assert captured.out.splitlines()[-1] == "CLEAN"


def test_corpus_charges_only_template_introduced_em_dashes(
    tmp_path, monkeypatch, capsys
):
    # The resume's OWN text carries one em dash and one ASCII "---". pdflatex's
    # ligature promotes the "---" to a second em-dash glyph; Typst leaves it as
    # three hyphens. Both renders are faithful, so neither may be flagged.
    corpus_dir = _stub_corpus(
        tmp_path,
        words=("alpha", "beta"),
        summary="alpha \N{EM DASH} beta and alpha --- beta",
    )
    words = ["alpha", "beta", "and"]
    _stub_corpus_render(
        monkeypatch,
        {
            "latex": _metrics(
                pdfplumber_words=words, pdfium_words=words, em_dashes=2
            ),
            "typst": _metrics(
                pdfplumber_words=words, pdfium_words=words, em_dashes=1
            ),
        },
    )

    report = template_parity.run_corpus(corpus_dir)

    assert report["example"]["em_dashes_template_latex"] == 0
    assert report["example"]["em_dashes_template_typst"] == 0
    assert report["example"]["em_dashes_source"] == 1
    assert report["example"]["ok"] is True
    assert capsys.readouterr().out.splitlines()[-1] == "CLEAN"


def test_corpus_flags_an_em_dash_the_template_introduced(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _stub_corpus(
        tmp_path,
        words=("alpha", "beta"),
        summary="alpha \N{EM DASH} beta and alpha --- beta",
    )
    words = ["alpha", "beta", "and"]
    _stub_corpus_render(
        monkeypatch,
        {
            # One more em dash than the source can account for on LaTeX.
            "latex": _metrics(
                pdfplumber_words=words, pdfium_words=words, em_dashes=3
            ),
            "typst": _metrics(
                pdfplumber_words=words, pdfium_words=words, em_dashes=1
            ),
        },
    )

    report = template_parity.run_corpus(corpus_dir)

    assert report["example"]["em_dashes_template_latex"] == 1
    assert report["example"]["em_dashes_template_typst"] == 0
    assert report["example"]["ok"] is False
    assert capsys.readouterr().out.splitlines()[-1] == "1 resumes flagged"


def test_corpus_flags_source_text_both_engines_dropped(
    tmp_path, monkeypatch, capsys
):
    # The cross-engine columns are blind here by construction: the two renders
    # are IDENTICAL, so words_only_* is 0. Only the absolute source-anchored
    # check can see that "beta" never reached either PDF.
    corpus_dir = _stub_corpus(tmp_path, words=("alpha", "beta"))
    dropped = _metrics(pdfplumber_words=["alpha"], pdfium_words=["alpha"])
    _stub_corpus_render(monkeypatch, {"latex": dropped, "typst": dropped})

    report = template_parity.run_corpus(corpus_dir)

    assert report["example"]["words_only_latex"] == 0
    assert report["example"]["words_only_typst"] == 0
    assert report["example"]["missing_src_latex"] == 1
    assert report["example"]["missing_src_typst"] == 1
    assert report["example"]["ok"] is False
    assert capsys.readouterr().out.splitlines()[-1] == "1 resumes flagged"


def test_corpus_does_not_flag_a_hyphenation_split_word(
    tmp_path, monkeypatch, capsys
):
    # "distributed" broken across a line break reaches the extractor as
    # "dis-" + "tributed"; the merge pass must recognize it as delivered.
    corpus_dir = _stub_corpus(tmp_path, words=("alpha",), summary="distributed")
    words = ["alpha", "dis-", "tributed"]
    hyphenated = _metrics(pdfplumber_words=words, pdfium_words=words)
    _stub_corpus_render(monkeypatch, {"latex": hyphenated, "typst": hyphenated})

    report = template_parity.run_corpus(corpus_dir)

    assert report["example"]["missing_src_latex"] == 0
    assert report["example"]["missing_src_typst"] == 0
    assert report["example"]["ok"] is True
    assert capsys.readouterr().out.splitlines()[-1] == "CLEAN"


def test_corpus_flags_a_real_rendered_divergence_end_to_end(
    tmp_path, monkeypatch, capsys
):
    """The one flagged-path test that renders for real.

    Every other flagged-path test stubs pdf_metrics, so the gate had only ever
    been proven against synthetic numbers. Here the Typst template genuinely
    stops printing each job's location, and the corpus has to notice.
    """
    corpus_dir = _example_corpus(tmp_path)
    latex_source, typst_source = template_parity._bundled_sources()
    # Blank the location cell rather than deleting it: the grid stays
    # well-formed, so this is a content divergence and not a compile error.
    divergent = typst_source.replace(
        "emph(job.role), emph(job.location),",
        "emph(job.role), [],",
    )
    assert divergent != typst_source
    monkeypatch.setattr(
        template_parity, "_bundled_sources", lambda: (latex_source, divergent)
    )

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report["example"]["ok"] is False
    assert report["example"]["words_only_latex"] > 0
    # The absolute check sees it independently: a location left the Typst PDF
    # entirely, while the untouched LaTeX side stays clean.
    assert report["example"]["missing_src_typst"] > 0
    assert report["example"]["missing_src_latex"] == 0
    assert captured.out.splitlines()[-1] == "1 resumes flagged"
    assert "Morgan" not in captured.out + captured.err


def test_pdf_metrics_rejects_a_wordless_page(tmp_path):
    blank = _pdf_with_text(tmp_path / "blank.pdf", "")

    with pytest.raises(ValueError, match="no words extracted"):
        pdf_metrics(blank)


def test_corpus_reports_a_wordless_render_instead_of_crashing(
    tmp_path, monkeypatch, capsys
):
    corpus_dir = _example_corpus(tmp_path)

    def blank_render(source, engine, resume, formatting, out_dir, stem):
        return _pdf_with_text(out_dir / f"{stem}.pdf", "")

    monkeypatch.setattr(template_parity, "render_template_pdf", blank_render)

    report = template_parity.run_corpus(corpus_dir)

    captured = capsys.readouterr()
    assert report == {"example": FAILURE_ROW}
    assert captured.err == "warning: example: render failed; skipped\n"
    assert captured.out.splitlines()[-1] == "1 resumes flagged"


def test_example_reports_when_no_section_title_matches(
    tmp_path, monkeypatch, capsys
):
    def flat_render(source, engine, resume, formatting, out_dir, stem):
        return _pdf_with_text(out_dir / f"{stem}.pdf", "no heading here at all")

    monkeypatch.setattr(template_parity, "render_template_pdf", flat_render)

    exit_code = template_parity._run_example(EXAMPLE)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no rendered line matched a known section title" in captured.err
    # It stops BEFORE printing deltas that would have had no anchor.
    assert captured.out == ""


def test_source_em_dash_counts_separate_literal_from_ascii():
    assert template_parity._source_em_dash_counts(
        {"summary": "x \N{EM DASH} y", "bullets": ["p --- q", "r -- s"]}
    ) == (1, 1)


def test_cli_compare_mode_diffs_two_arbitrary_source_files(tmp_path):
    """--compare works on ANY latex/typst pair, not just the bundled ones.

    This is the feedback loop for porting an uploaded .tex to typst: render
    both, dump aligned per-line deltas. Same output contract as --example.
    """
    import subprocess

    latex = tmp_path / "mini.tex.j2"
    latex.write_text(
        "\\documentclass[letterpaper,11pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\\pagestyle{empty}\n"
        "\\begin{document}\n"
        "\\section*{Summary}\n"
        "((( resume.summary|latex_escape )))\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    typst = tmp_path / "mini.typ"
    typst.write_text(
        '#let r = json(bytes(sys.inputs.resume))\n'
        '#set page(paper: "us-letter", margin: 1in)\n'
        '= Summary\n'
        '#r.summary\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.template_parity",
         "--compare", str(latex), str(typst)],
        capture_output=True, text=True, env=os.environ.copy(), check=False,
        cwd=_BACKEND_DIR,
    )
    # The mini pair is NOT parity-matched; the tool must still report, not fail.
    assert result.returncode == 0, result.stderr
    assert "latex: pages=" in result.stdout
    assert "typst: pages=" in result.stdout
    assert "latex | typst" in result.stdout


def test_source_tokens_skip_fields_no_bundled_template_renders():
    dump = {
        "education": [{"field": "Astrophysics", "degree": "BS Physics"}],
        "projects": [{"link": "example.test/orbital", "name": "Orbital Notes"}],
    }
    tokens = template_parity._source_tokens(dump)

    # Neither bundled template typesets education.field or projects[].link, so
    # requiring them in the PDF would flag every resume that has them.
    assert "astrophysics" not in tokens
    assert "orbital" in tokens  # from the project NAME, which IS rendered
    assert {"physics", "notes"} <= tokens


def test_source_tokens_and_dash_expectations_skip_disabled_entries():
    # The render path never hands enabled=False sections/entries to a
    # template ("Disabled sections/entries contribute nothing"), so their
    # text is not source the render owes us. Before this filter, 6 of the
    # 8 real base resumes flagged falsely on tokens from disabled entries.
    dump = {
        "experience": [
            {"company": "Livewire", "bullets": ["Shipped telemetry"], "enabled": True},
            {
                "company": "Ghostship",
                "bullets": ["Confidential moonshot --- retired"],
                "enabled": False,
            },
        ],
        "extra_sections": [
            {"type": "bullets", "key": "hidden", "enabled": False,
             "bullets": ["Invisible \u2014 content"]},
        ],
    }
    tokens = template_parity._source_tokens(dump)
    assert {"livewire", "shipped", "telemetry"} <= tokens
    assert "ghostship" not in tokens
    assert "confidential" not in tokens
    assert "invisible" not in tokens

    literal, ascii_triple = template_parity._source_em_dash_counts(dump)
    assert literal == 0  # the U+2014 lives in a disabled section
    assert ascii_triple == 0  # the "---" lives in a disabled entry


def test_missing_source_tokens_counts_only_what_never_arrived():
    # A line-break hyphen split "distributed" in two; it still arrived.
    assert (
        template_parity._missing_source_tokens({"distributed"}, ["dis-", "tributed"])
        == 0
    )
    # A GENUINE compound hyphen keeps contributing its own two tokens, because
    # the merges are unioned with the unmerged ones rather than replacing them.
    assert (
        template_parity._missing_source_tokens(
            {"high", "throughput"}, ["high-", "throughput"]
        )
        == 0
    )
    assert (
        template_parity._missing_source_tokens(
            {"distributed", "absent"}, ["dis-", "tributed", "other"]
        )
        == 1
    )


def test_source_tokens_ignore_tokens_too_short_to_be_evidence():
    assert template_parity._source_tokens({"summary": "an ox ran far"}) == {
        "ran",
        "far",
    }


@pytest.mark.parametrize("corpus_state", ["empty", "missing", "invalid"])
def test_cli_without_rendered_entries_exits_nonzero(
    tmp_path, corpus_state
):
    env_corpus = _example_corpus(tmp_path)
    selected_dir = tmp_path / corpus_state
    if corpus_state != "missing":
        selected_dir.mkdir()
    if corpus_state == "invalid":
        (selected_dir / "private.json").write_text(
            "Private Person private.person@example.test"
        )
    env = os.environ.copy()
    env["BASE_RESUMES_DIR"] = str(env_corpus)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.template_parity",
            "--corpus",
            "--dir",
            str(selected_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=_BACKEND_DIR,
    )

    assert result.returncode != 0
    expected_verdict = (
        "1 resumes flagged"
        if corpus_state == "invalid"
        else "EVIDENCE UNAVAILABLE"
    )
    assert result.stdout.splitlines()[-1] == expected_verdict
    assert "CLEAN" not in result.stdout
    assert "Morgan" not in result.stdout + result.stderr


def test_cli_uses_base_resumes_dir_for_corpus(tmp_path):
    corpus_dir = _example_corpus(tmp_path)
    env = os.environ.copy()
    env["BASE_RESUMES_DIR"] = str(corpus_dir)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.template_parity", "--corpus"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=_BACKEND_DIR,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines()[1].startswith("example\t")
    assert result.stdout.splitlines()[-1] == "CLEAN"
    assert "Morgan" not in result.stdout + result.stderr


def test_cli_mixed_valid_and_invalid_corpus_exits_nonzero_without_pii(tmp_path):
    corpus_dir = _example_corpus(tmp_path)
    secret = "Private Person private.person@example.test"
    (corpus_dir / "private.json").write_text(secret)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.template_parity",
            "--corpus",
            "--dir",
            str(corpus_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=_BACKEND_DIR,
    )

    assert result.returncode != 0
    assert result.stdout.splitlines()[-1] == "1 resumes flagged"
    assert secret not in result.stdout + result.stderr


def test_cli_rejects_dir_without_corpus():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.template_parity",
            "--example",
            "--dir",
            "ignored",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=_BACKEND_DIR,
    )

    assert result.returncode != 0
    assert "--dir requires --corpus" in result.stderr


def test_golden_verdict_reports_missing_without_rendering(db_session, monkeypatch):
    monkeypatch.setattr(
        template_parity,
        "render_template_pdf",
        lambda *args, **kwargs: pytest.fail("missing row must not render"),
    )

    assert golden_verdict(db_session, EXAMPLE) == "missing"


def test_golden_verdict_compares_bundled_and_database_outputs(
    db_session, monkeypatch
):
    from app.models.template import Template

    bundled = (TEMPLATE_DIR / "user" / "xcharter_serif.tex.j2").read_text()
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source="database source",
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()

    def fake_render(source, engine, resume, formatting, out_dir, stem):
        return out_dir / f"{stem}.pdf"

    bundled_metrics = _metrics(
        pdfplumber_words=["same", "sequence"],
        pdfium_words=["same", "sequence"],
    )
    database_metrics = _metrics(
        pdfplumber_words=["different", "sequence"],
        pdfium_words=["different", "sequence"],
    )
    monkeypatch.setattr(template_parity, "render_template_pdf", fake_render)
    monkeypatch.setattr(
        template_parity,
        "pdf_metrics",
        lambda path: (
            bundled_metrics if path.stem == "bundled" else database_metrics
        ),
    )

    assert golden_verdict(db_session, EXAMPLE) == "different"
    assert bundled != "database source"


def test_golden_verdict_is_clean_for_real_bundled_database_output(db_session):
    from app.models.template import Template

    bundled = (TEMPLATE_DIR / "user" / "xcharter_serif.tex.j2").read_text()
    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source=bundled,
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()

    assert golden_verdict(db_session, EXAMPLE) == "clean"


def test_golden_verdict_rejects_a_punctuation_only_database_drift(
    db_session, monkeypatch
):
    """--golden must be no weaker than the pytest golden.

    The pytest golden compares sorted RAW words; --golden used to compare
    normalized ones, so a database row that swapped an en dash for a double
    hyphen printed GOLDEN CLEAN while the pytest golden failed on the same
    pair. The whole point of --golden is to be the ops-side stand-in for that
    test, so it compares raw words too.
    """
    from app.models.template import Template

    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source="database source",
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()

    bundled_words = ["March", "2022", "--", "Present"]
    database_words = ["March", "2022", "\N{EN DASH}", "Present"]
    # Not vacuous: the OLD normalized comparison saw these as identical.
    assert normalized_word_sequence(bundled_words) == normalized_word_sequence(
        database_words
    )

    bundled_metrics = _metrics(
        pdfplumber_words=bundled_words, pdfium_words=bundled_words
    )
    database_metrics = _metrics(
        pdfplumber_words=database_words, pdfium_words=database_words
    )
    monkeypatch.setattr(
        template_parity,
        "render_template_pdf",
        lambda source, engine, resume, formatting, out_dir, stem: out_dir
        / f"{stem}.pdf",
    )
    monkeypatch.setattr(
        template_parity,
        "pdf_metrics",
        lambda path: bundled_metrics if path.stem == "bundled" else database_metrics,
    )

    assert golden_verdict(db_session, EXAMPLE) == "different"


def test_golden_verdict_reports_render_failure_safely(db_session, monkeypatch):
    from app.models.template import Template

    db_session.add(
        Template(
            id="xcharter_serif",
            display_name="XCharter Serif",
            source="database source",
            status="ready",
            origin="mcp",
            engine="latex",
            is_default=True,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        template_parity,
        "render_template_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private")),
    )

    assert golden_verdict(db_session, EXAMPLE) == "render-failed"


@pytest.mark.parametrize(
    ("verdict", "expected_code", "expected_output"),
    [
        ("clean", 0, "GOLDEN CLEAN\n"),
        ("missing", 1, "GOLDEN UNAVAILABLE: missing template\n"),
        ("render-failed", 1, "GOLDEN UNAVAILABLE: render failed\n"),
        ("different", 1, "GOLDEN DIFFERENT\n"),
    ],
)
def test_golden_cli_verdict_and_exit_code(
    monkeypatch,
    capsys,
    verdict,
    expected_code,
    expected_output,
):
    monkeypatch.setattr(template_parity, "golden_verdict", lambda session, resume: verdict)

    exit_code = template_parity.main(
        ["--golden"],
        session_factory=lambda: nullcontext(object()),
    )

    assert exit_code == expected_code
    assert capsys.readouterr().out == expected_output


def test_import_is_silent_without_corpus_dispatch(tmp_path):
    sentinel_dir = tmp_path / "import-must-not-touch"
    env = os.environ.copy()
    env["BASE_RESUMES_DIR"] = str(sentinel_dir)

    result = subprocess.run(
        [sys.executable, "-c", "import scripts.template_parity"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=_BACKEND_DIR,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not sentinel_dir.exists()
    assert list(tmp_path.iterdir()) == []
