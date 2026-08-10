"""Cross-engine template parity: render, measure, compare.

A library used by the tests, plus three CLI modes:

  --example  render the bundled XCharter pair on base_resumes/example.json and
             dump per-line top deltas
  --golden   compare the bundled LaTeX source against the xcharter_serif DB row
  --corpus   render a whole resume directory through both bundled engines and
             print counts and flags only

The corpus report is deliberately content-free: every row is counts, booleans
and ``slug`` -- and ``slug`` is the resume FILENAME STEM, printed verbatim, so
keep corpus filenames non-identifying.

Two of the corpus columns need explaining.

``em_dashes_template_*`` counts only the em dashes the TEMPLATE introduced,
per engine, because the engines disagree about the source text: pdflatex's
ligatures turn an ASCII ``---`` into an em dash (and ``--`` into an en dash),
while Typst typesets the JSON string verbatim. A resume that legitimately
contains em dashes therefore renders a nonzero raw count on both engines and
would fail a naive gate. The source's own em dashes are reported, ungated, as
``em_dashes_source``.

``missing_src_*`` is an ABSOLUTE per-engine check -- source words that never
reached that engine's PDF -- rather than a cross-engine diff, so it also
catches a defect both engines share (the historical XCharter word-joining bug
joined lowercase words, which the camelCase ``joined_*`` heuristic cannot
see). A token split by line-break hyphenation is rejoined with its successor
before comparison, but a hyphenation-heavy resume may still need re-triage
after the first real-corpus run.

Every CLI entry point must live under __main__ because typst_compiler spawns a
child that re-imports this module.
"""
from __future__ import annotations

import re
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.models.template import Template
from app.schemas.formatting import merge_formatting
from app.schemas.resume import ResumeData
from app.services.pdf_render import (
    build_typst_sys_inputs,
    compile_pdf,
    compile_typst_pdf,
    render_tex_from_source,
)

SECTION_TITLES = frozenset(
    {"summary", "experience", "projects", "technical skills", "education"}
)
_JOINED = re.compile(r"[a-z][A-Z][a-z]")
_NORMALIZED_TOKEN = re.compile(r"[a-z0-9]+")
_SOURCE_WORD = re.compile(r"[A-Za-z0-9]+")
# A word's ``top`` is the glyph-box top, not the baseline, so glyphs set at a
# smaller size on the SAME visual line report a lower top: LaTeX's ``$|$``
# separators land +0.3pt and its ``\vcenter`` bullets +1.9pt below the body
# text; Typst's 5pt list markers land +4.0pt below. Grouping on the raw top
# therefore invents phantom "lines" — and it did so unevenly per engine (18 in
# LaTeX vs 0 in Typst on example.json), so an equal raw line_count was a
# coincidence, not parity. Cluster instead: consecutive tops within
# LINE_CLUSTER_TOL of the cluster's first top are one visual line. The smallest
# real baseline pitch anywhere in the knob space is ~9.9pt (font_size 10 at
# line_spacing 0.9, both engines), so this tolerance has ~2x headroom.
LINE_CLUSTER_TOL = 5.0

# A source token shorter than this is too likely to be swallowed by an
# extractor's tokenization to be evidence of anything.
MIN_SOURCE_TOKEN_LEN = 3

# Model-dump keys whose strings neither bundled template typesets: pydantic's
# structural fields (``type`` discriminator, ``key`` slug, ``enabled`` flag)
# plus the two content fields the XCharter layout deliberately drops --
# ``education.field`` and ``projects[].link``. (An extra section's ``link`` IS
# rendered, but the key is shared, so it goes too; the cost is coverage, not
# correctness.) Requiring these to appear in the PDF would fail every resume
# that carries them: example.json's education field is "Information Systems",
# and "information" appears nowhere in either render. Only ``missing_src_*``
# uses this filter -- ``_source_words`` deliberately keeps the wider set,
# because there an over-broad allow-list is the SAFE direction.
_UNRENDERED_SOURCE_KEYS = frozenset({"type", "key", "enabled", "link", "field"})

_CORPUS_COLUMNS = (
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
)
# Derived from the column list so the two can never drift apart.
_FAILURE_METRICS: dict[str, int | bool] = {
    column: (False if column == "ok" else -1) for column in _CORPUS_COLUMNS
}


def normalized_word_sequence(words: list[str]) -> tuple[str, ...]:
    """Normalize extractor punctuation while preserving token order."""
    return tuple(
        token
        for word in words
        for token in _NORMALIZED_TOKEN.findall(word.casefold())
    )


def _sequence_difference_counts(
    latex_words: list[str],
    typst_words: list[str],
) -> tuple[int, int]:
    latex = normalized_word_sequence(latex_words)
    typst = normalized_word_sequence(typst_words)
    only_latex = 0
    only_typst = 0
    for operation, i1, i2, j1, j2 in SequenceMatcher(
        None,
        latex,
        typst,
        autojunk=False,
    ).get_opcodes():
        if operation in {"delete", "replace"}:
            only_latex += i2 - i1
        if operation in {"insert", "replace"}:
            only_typst += j2 - j1
    return only_latex, only_typst


def _source_strings(value: Any, skip_keys: frozenset[str] = frozenset()):
    """Yield every string in a resume model dump, skipping ``skip_keys``.

    A dict with ``enabled: False`` is skipped whole: the render path never
    hands disabled sections/entries to a template, so their text must not
    count as "source the render owes us" (real corpora use this flag heavily
    — 6 of 8 flagged falsely before this filter existed).
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        if value.get("enabled") is False:
            return
        for key, item in value.items():
            if key not in skip_keys:
                yield from _source_strings(item, skip_keys)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _source_strings(item, skip_keys)


def _source_words(value: Any) -> set[str]:
    return {
        word for text in _source_strings(value) for word in _SOURCE_WORD.findall(text)
    }


def _source_tokens(value: Any) -> set[str]:
    """Normalized source tokens that a faithful render must reproduce."""
    return {
        token
        for text in _source_strings(value, _UNRENDERED_SOURCE_KEYS)
        for token in _NORMALIZED_TOKEN.findall(text.casefold())
        if len(token) >= MIN_SOURCE_TOKEN_LEN
    }


def _source_em_dash_counts(value: Any) -> tuple[int, int]:
    """``(literal U+2014 count, ASCII "---" count)`` over the source strings.

    The second number is what pdflatex's ligature will silently PROMOTE to an
    em dash; Typst leaves it as three hyphens. Hence two numbers, and hence a
    per-engine expectation.
    """
    literal = 0
    ascii_triple = 0
    # Same filtered view as _source_tokens: disabled/unrendered content never
    # reaches a template, so it must not inflate the EXPECTED dash counts
    # (an inflated expectation would mask a template-introduced em dash).
    for text in _source_strings(value, _UNRENDERED_SOURCE_KEYS):
        literal += text.count("\N{EM DASH}")
        ascii_triple += text.count("---")
    return literal, ascii_triple


def _hyphenation_merges(words: list[str]) -> list[str]:
    """Rejoin each token ending in ``-`` with its successor.

    A line-break hyphen splits one source word across two extracted tokens
    ("dis-" + "tributed"). The merges are ADDITIVE -- callers union them with
    the unmerged tokens -- so a genuine compound hyphen ("high-throughput"
    broken at the hyphen) keeps contributing its own two tokens as well.
    """
    return [
        first[:-1] + second
        for first, second in zip(words, words[1:])
        if first.endswith("-")
    ]


def _extracted_tokens(*word_lists: list[str]) -> set[str]:
    tokens: set[str] = set()
    for words in word_lists:
        tokens.update(normalized_word_sequence(words))
        tokens.update(normalized_word_sequence(_hyphenation_merges(words)))
    return tokens


def _missing_source_tokens(
    source_tokens: set[str],
    *word_lists: list[str],
) -> int:
    """How many source tokens never reached this engine's extracted text."""
    extracted = _extracted_tokens(*word_lists)
    return sum(token not in extracted for token in source_tokens)


def _joined_suspect_count(
    *word_lists: list[str],
    source_words: set[str] | None = None,
) -> int:
    allowed = source_words or set()
    return max(
        (
            sum(
                bool(_JOINED.search(token)) and token not in allowed
                for word in words
                for token in _SOURCE_WORD.findall(word)
            )
            for words in word_lists
        ),
        default=0,
    )


def cluster_line_tops(words: list[dict], tol: float = LINE_CLUSTER_TOL) -> list[tuple]:
    """Group extracted words into visual lines (see ``LINE_CLUSTER_TOL``).

    Returns ``[(anchor_top, [word, ...]), ...]`` ordered top to bottom; a
    cluster spans strictly less than ``tol``, so clusters cannot chain.
    """
    by_top: dict[float, list] = {}
    for word in words:
        by_top.setdefault(round(word["top"], 1), []).append(word)
    clustered: list[list] = []
    for top in sorted(by_top):
        if clustered and top - clustered[-1][0] < tol:
            clustered[-1][1].extend(by_top[top])
        else:
            clustered.append([top, list(by_top[top])])
    return [(top, group) for top, group in clustered]


def render_template_pdf(source, engine, resume, formatting, out_dir, stem):
    fmt = merge_formatting(None, formatting).model_dump()
    if engine == "typst":
        sys_inputs = build_typst_sys_inputs(
            source, resume, fmt, enforce_extras_support=False
        )
        return compile_typst_pdf(source, out_dir, stem, sys_inputs=sys_inputs)
    tex = render_tex_from_source(
        source, resume, formatting=fmt, enforce_extras_support=False
    )
    return compile_pdf(tex, out_dir, stem=stem)


def pdf_metrics(pdf_path: Path) -> dict[str, Any]:
    # TWO INDEPENDENT EXTRACTORS, on purpose: `joined_suspects` and `em_dashes`
    # are only meaningful because two libraries read the same document and can
    # disagree. The second one was PyMuPDF (`fitz`) until 2026-08-08; it is
    # AGPL-3.0, was never a declared dependency, and this project ships under
    # Apache 2.0 — so the suite passed only on machines that happened to have
    # it installed, and a clean CI run had no `fitz` at all. pypdfium2 is
    # BSD-3-Clause/Apache-2.0, already a runtime dependency, and is a genuinely
    # different engine from pdfplumber, which is the property that matters.
    import pdfplumber
    import pypdfium2 as pdfium

    out: dict[str, Any] = {}
    with pdfplumber.open(pdf_path) as pdf:
        out["pages"] = len(pdf.pages)
        page = pdf.pages[0]
        words = page.extract_words(extra_attrs=["size", "fontname"])
        if not words:
            # A blank first page (template renders nothing, substitution
            # silently produced an empty document) would otherwise surface as
            # "min() arg is an empty sequence" from the geometry below. The
            # corpus and golden paths turn this into their generic
            # skipped/render-failed report; --example prints it and stops.
            raise ValueError("no words extracted from page 1")
        lines = cluster_line_tops(words)
        out["line_count"] = len(lines)
        out["left"] = min(w["x0"] for w in words)
        out["width"] = max(w["x1"] for w in words) - out["left"]
        out["font_sizes"] = sorted({round(w["size"], 1) for w in words})
        out["fontnames"] = sorted({w["fontname"] for w in words})
        gaps = [b[0] - a[0] for a, b in zip(lines, lines[1:])]
        out["max_line_gap"] = max(gaps) if gaps else 0.0
        out["min_line_gap"] = min(gaps) if gaps else 0.0
        sections = {}
        for t, group in lines:
            text = " ".join(
                w["text"] for w in sorted(group, key=lambda w: w["x0"])
            ).strip().lower()
            if text in SECTION_TITLES:
                sections[text] = t
        out["section_tops"] = sections
        text1 = "\n".join(p.extract_text() or "" for p in pdf.pages)
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        text2 = "\n".join(page.get_textpage().get_text_range() for page in doc)
    finally:
        doc.close()
    out["words_pdfplumber"] = text1.split()
    out["words_pdfium"] = text2.split()
    # MAX, not sum: the two extractors are two readings of ONE document, so
    # summing double-counts every dash and makes the number unusable as
    # "how many em dashes are in this PDF" -- which is exactly what the corpus
    # gate subtracts the source's own em dashes from.
    out["em_dashes"] = max(text1.count("—"), text2.count("—"))
    out["joined_suspects"] = _joined_suspect_count(
        out["words_pdfplumber"], out["words_pdfium"]
    )
    return out


def _align_logical_lines(latex_lines, typst_lines):
    def normalized_tokens(text):
        tokens = tuple(re.findall(r"[a-z0-9]+", text.casefold()))
        if not tokens and "•" in text:
            return ("bullet-marker",)
        return tokens

    def similarity(latex_text, typst_text):
        latex_tokens = normalized_tokens(latex_text)
        typst_tokens = normalized_tokens(typst_text)
        if not latex_tokens or not typst_tokens:
            return None
        if latex_tokens == typst_tokens:
            return 1.0
        shared = set(latex_tokens) & set(typst_tokens)
        containment = 0.0
        if len(shared) >= 2:
            containment = len(shared) / min(
                len(set(latex_tokens)), len(set(typst_tokens))
            )
        sequence = SequenceMatcher(
            None, " ".join(latex_tokens), " ".join(typst_tokens)
        ).ratio()
        score = max(containment, sequence)
        return score if score >= 0.48 else None

    gap_penalty = -0.35
    height = len(latex_lines) + 1
    width = len(typst_lines) + 1
    scores = [[0.0] * width for _ in range(height)]
    moves = [[""] * width for _ in range(height)]
    for i in range(1, height):
        scores[i][0] = scores[i - 1][0] + gap_penalty
        moves[i][0] = "latex-only"
    for j in range(1, width):
        scores[0][j] = scores[0][j - 1] + gap_penalty
        moves[0][j] = "typst-only"

    for i in range(1, height):
        for j in range(1, width):
            choices = [
                (scores[i - 1][j] + gap_penalty, "latex-only"),
                (scores[i][j - 1] + gap_penalty, "typst-only"),
            ]
            match_score = similarity(latex_lines[i - 1][1], typst_lines[j - 1][1])
            if match_score is not None:
                choices.append((scores[i - 1][j - 1] + match_score, "match"))
            scores[i][j], moves[i][j] = max(
                choices, key=lambda choice: (choice[0], choice[1] == "match")
            )

    aligned = []
    i, j = len(latex_lines), len(typst_lines)
    while i or j:
        move = moves[i][j]
        if move == "match":
            aligned.append((move, latex_lines[i - 1], typst_lines[j - 1]))
            i -= 1
            j -= 1
        elif move == "latex-only":
            aligned.append((move, latex_lines[i - 1], None))
            i -= 1
        else:
            aligned.append((move, None, typst_lines[j - 1]))
            j -= 1
    return list(reversed(aligned))


def _metrics_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["pages"] != right["pages"] or left["line_count"] != right["line_count"]:
        return False
    if abs(left["left"] - right["left"]) > 0.25:
        return False
    if abs(left["width"] - right["width"]) > 0.25:
        return False
    if left["font_sizes"] != right["font_sizes"]:
        return False
    if left["fontnames"] != right["fontnames"]:
        return False
    if left["section_tops"].keys() != right["section_tops"].keys():
        return False
    if any(
        abs(left["section_tops"][title] - right["section_tops"][title]) > 0.25
        for title in left["section_tops"]
    ):
        return False
    # RAW words, not normalized ones -- this mirrors the pytest golden
    # (test_bundled_latex_matches_original_golden), which compares
    # sorted(words_pdfplumber) verbatim. Normalizing here would let a
    # punctuation-only drift in the database row print GOLDEN CLEAN while the
    # pytest golden failed on the same pair.
    return all(
        sorted(left[extractor]) == sorted(right[extractor])
        for extractor in ("words_pdfplumber", "words_pdfium")
    )


def golden_verdict(session, resume: dict[str, Any] | ResumeData) -> str:
    """Compare bundled LaTeX output with the current database row."""
    row = session.get(Template, "xcharter_serif")
    if row is None:
        return "missing"
    if row.engine != "latex":
        return "engine-mismatch"

    backend_dir = Path(__file__).resolve().parents[1]
    bundled_source = (
        backend_dir / "app" / "templates" / "user" / "xcharter_serif.tex.j2"
    ).read_text(encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="template-parity-golden-") as tmp:
            out_dir = Path(tmp)
            bundled_metrics = pdf_metrics(
                render_template_pdf(
                    bundled_source,
                    "latex",
                    resume,
                    None,
                    out_dir,
                    "bundled",
                )
            )
            database_metrics = pdf_metrics(
                render_template_pdf(
                    row.source,
                    "latex",
                    resume,
                    None,
                    out_dir,
                    "database",
                )
            )
    except Exception:
        return "render-failed"
    return (
        "clean"
        if _metrics_equivalent(bundled_metrics, database_metrics)
        else "different"
    )


def _bundled_sources() -> tuple[str, str]:
    """The bundled XCharter ``(latex, typst)`` sources.

    A single seam so a test can substitute a deliberately divergent variant and
    prove the corpus gate fires on a REAL rendered difference.
    """
    user_dir = Path(__file__).resolve().parents[1] / "app" / "templates" / "user"
    return (
        (user_dir / "xcharter_serif.tex.j2").read_text(encoding="utf-8"),
        (user_dir / "xcharter_serif.typ").read_text(encoding="utf-8"),
    )


def run_corpus(base_resumes_dir: Path) -> dict[str, dict[str, int | bool]]:
    """Render a corpus through both bundled engines and report no resume text."""
    import json

    latex_source, typst_source = _bundled_sources()
    report: dict[str, dict[str, int | bool]] = {}

    for resume_path in sorted(base_resumes_dir.glob("*.json")):
        slug = resume_path.stem
        try:
            resume = ResumeData.model_validate(
                json.loads(resume_path.read_text(encoding="utf-8"))
            )
        except Exception:
            print(f"warning: {slug}: invalid resume; skipped", file=sys.stderr)
            report[slug] = dict(_FAILURE_METRICS)
            continue

        try:
            with tempfile.TemporaryDirectory(prefix="template-parity-") as tmp:
                out_dir = Path(tmp)
                latex_metrics = pdf_metrics(
                    render_template_pdf(
                        latex_source,
                        "latex",
                        resume,
                        None,
                        out_dir,
                        "latex",
                    )
                )
                typst_metrics = pdf_metrics(
                    render_template_pdf(
                        typst_source,
                        "typst",
                        resume,
                        None,
                        out_dir,
                        "typst",
                    )
                )
        except Exception:
            print(f"warning: {slug}: render failed; skipped", file=sys.stderr)
            report[slug] = dict(_FAILURE_METRICS)
            continue

        # MAX across the two extractors, matching ``joined_*`` (and
        # ``pdf_metrics``'s em-dash count). The extractors are two readings of
        # the SAME pair of documents, so summing reports one divergence twice
        # and the column stops meaning "how many words diverged".
        words_only_latex = 0
        words_only_typst = 0
        for extractor in ("words_pdfplumber", "words_pdfium"):
            only_latex, only_typst = _sequence_difference_counts(
                latex_metrics[extractor],
                typst_metrics[extractor],
            )
            words_only_latex = max(words_only_latex, only_latex)
            words_only_typst = max(words_only_typst, only_typst)

        dump = resume.model_dump()
        source_words = _source_words(dump)
        source_tokens = _source_tokens(dump)
        source_em_dashes, source_ascii_em_dashes = _source_em_dash_counts(dump)
        metrics: dict[str, int | bool] = {
            "pages_latex": latex_metrics["pages"],
            "pages_typst": typst_metrics["pages"],
            "words_only_latex": words_only_latex,
            "words_only_typst": words_only_typst,
            "joined_latex": _joined_suspect_count(
                latex_metrics["words_pdfplumber"],
                latex_metrics["words_pdfium"],
                source_words=source_words,
            ),
            "joined_typst": _joined_suspect_count(
                typst_metrics["words_pdfplumber"],
                typst_metrics["words_pdfium"],
                source_words=source_words,
            ),
            "missing_src_latex": _missing_source_tokens(
                source_tokens,
                latex_metrics["words_pdfplumber"],
                latex_metrics["words_pdfium"],
            ),
            "missing_src_typst": _missing_source_tokens(
                source_tokens,
                typst_metrics["words_pdfplumber"],
                typst_metrics["words_pdfium"],
            ),
            # pdflatex promotes a source "---" to an em dash, Typst does not,
            # so the two engines get different expectations subtracted. Clamped
            # at 0: an engine that renders FEWER em dashes than the source has
            # is a words_only/missing_src finding, not an em-dash one.
            "em_dashes_template_latex": max(
                0,
                latex_metrics["em_dashes"]
                - source_em_dashes
                - source_ascii_em_dashes,
            ),
            "em_dashes_template_typst": max(
                0, typst_metrics["em_dashes"] - source_em_dashes
            ),
            "em_dashes_source": source_em_dashes,
            "ok": False,
        }
        metrics["ok"] = (
            metrics["pages_latex"] == metrics["pages_typst"]
            and metrics["words_only_latex"] == 0
            and metrics["words_only_typst"] == 0
            and metrics["joined_latex"] == 0
            and metrics["joined_typst"] == 0
            and metrics["missing_src_latex"] == 0
            and metrics["missing_src_typst"] == 0
            and metrics["em_dashes_template_latex"] == 0
            and metrics["em_dashes_template_typst"] == 0
        )
        report[slug] = metrics

    # em_dashes_source is reported but NOT gated: em dashes the author wrote
    # are the author's business.
    print("slug\t" + "\t".join(_CORPUS_COLUMNS))
    for slug, metrics in report.items():
        print(
            slug
            + "\t"
            + "\t".join(str(metrics[column]) for column in _CORPUS_COLUMNS)
        )
    if not report:
        print("EVIDENCE UNAVAILABLE")
        return report
    flagged = sum(not metrics["ok"] for metrics in report.values())
    print("CLEAN" if flagged == 0 else f"{flagged} resumes flagged")
    return report


def _run_example(
    resume: dict[str, Any],
    sources: tuple[str, str] | None = None,
    *,
    strict_sections: bool = True,
) -> int:
    """Render a latex/typst source pair and dump aligned per-line deltas.

    ``sources`` defaults to the bundled pair (--example); --compare passes an
    arbitrary pair, where unknown section headings are tolerated because an
    uploaded template may not use the five stock titles.
    """
    import pdfplumber

    latex_source, typst_source = sources or _bundled_sources()

    with tempfile.TemporaryDirectory(prefix="template-parity-") as tmp:
        out_dir = Path(tmp)
        latex_pdf = render_template_pdf(
            latex_source,
            "latex",
            resume,
            None,
            out_dir,
            "latex",
        )
        typst_pdf = render_template_pdf(
            typst_source,
            "typst",
            resume,
            None,
            out_dir,
            "typst",
        )

        def line_dump(pdf_path):
            with pdfplumber.open(pdf_path) as pdf:
                words = pdf.pages[0].extract_words()
            return [
                (
                    top,
                    " ".join(
                        word["text"]
                        for word in sorted(group, key=lambda word: word["x0"])
                    ),
                )
                for top, group in cluster_line_tops(words)
            ]

        latex_lines = line_dump(latex_pdf)
        typst_lines = line_dump(typst_pdf)
        try:
            latex_metrics = pdf_metrics(latex_pdf)
            typst_metrics = pdf_metrics(typst_pdf)
        except ValueError as exc:
            # An empty page: report it instead of a bare min()/max() traceback.
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for engine, metrics in (
            ("latex", latex_metrics),
            ("typst", typst_metrics),
        ):
            section_tops = metrics["section_tops"]
            if not section_tops and strict_sections:
                print(
                    f"error: {engine}: no rendered line matched a known "
                    f"section title ({', '.join(sorted(SECTION_TITLES))}); "
                    "the per-line deltas below would have no anchor",
                    file=sys.stderr,
                )
                return 1
            section_base = min(section_tops.values()) if section_tops else 0.0
            relative_tops = {
                title: round(top - section_base, 1)
                for title, top in section_tops.items()
            }
            print(
                f"{engine}: pages={metrics['pages']} lines={metrics['line_count']} "
                f"left={metrics['left']:.1f} width={metrics['width']:.1f} "
                f"joined={metrics['joined_suspects']} "
                f"em_dashes={metrics['em_dashes']} sections={relative_tops}"
            )
        print("status       line  latex_top  typst_top  delta  latex | typst")
        for line_no, (status, latex_line, typst_line) in enumerate(
            _align_logical_lines(latex_lines, typst_lines), start=1
        ):
            if status == "match":
                latex_top, latex_text = latex_line
                typst_top, typst_text = typst_line
                print(
                    f"match {line_no:>10}  {latex_top:>9.1f}  {typst_top:>9.1f}"
                    f"  {typst_top - latex_top:>5.1f}"
                    f"  {latex_text} | {typst_text}"
                )
            elif status == "latex-only":
                latex_top, latex_text = latex_line
                print(
                    f"latex-only {line_no:>5}  {latex_top:>9.1f}"
                    f"         --   skip  {latex_text} | <unmatched>"
                )
            else:
                typst_top, typst_text = typst_line
                print(
                    f"typst-only {line_no:>5}         --  {typst_top:>9.1f}"
                    f"   skip  <unmatched> | {typst_text}"
                )
    return 0


def main(argv: list[str] | None = None, session_factory=None) -> int:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--example",
        action="store_true",
        help="render the bundled XCharter templates and dump per-line top deltas",
    )
    mode.add_argument(
        "--golden",
        action="store_true",
        help="compare bundled LaTeX output with the current database row",
    )
    mode.add_argument(
        "--corpus",
        action="store_true",
        help="render a corpus and print counts and flags only",
    )
    mode.add_argument(
        "--compare",
        nargs=2,
        metavar=("LATEX_FILE", "TYPST_FILE"),
        type=Path,
        help="diff an arbitrary latex/typst source pair (porting feedback loop)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        help="corpus directory (overrides BASE_RESUMES_DIR)",
    )
    args = parser.parse_args(argv)
    if args.dir is not None and not args.corpus:
        parser.error("--dir requires --corpus")

    backend_dir = Path(__file__).resolve().parents[1]
    if args.corpus:
        # Anchored fallback, not a CWD-relative "../base_resumes": the script
        # is runnable from anywhere, and a relative default silently reports
        # EVIDENCE UNAVAILABLE from the wrong directory instead of failing.
        corpus_dir = args.dir or Path(
            os.environ.get("BASE_RESUMES_DIR") or backend_dir.parent / "base_resumes"
        )
        report = run_corpus(corpus_dir)
        return 0 if report and all(row["ok"] for row in report.values()) else 1

    resume = json.loads(
        (backend_dir.parent / "base_resumes" / "example.json").read_text(
            encoding="utf-8"
        )
    )
    if args.golden:
        if session_factory is None:
            from app.db import SessionLocal

            session_factory = SessionLocal
        with session_factory() as session:
            verdict = golden_verdict(session, resume)
        output = {
            "clean": "GOLDEN CLEAN",
            "missing": "GOLDEN UNAVAILABLE: missing template",
            "engine-mismatch": "GOLDEN UNAVAILABLE: engine mismatch",
            "render-failed": "GOLDEN UNAVAILABLE: render failed",
            "different": "GOLDEN DIFFERENT",
        }[verdict]
        print(output)
        return 0 if verdict == "clean" else 1

    if args.compare:
        latex_file, typst_file = args.compare
        return _run_example(
            resume,
            (
                latex_file.read_text(encoding="utf-8"),
                typst_file.read_text(encoding="utf-8"),
            ),
            strict_sections=False,
        )
    return _run_example(resume)


if __name__ == "__main__":
    raise SystemExit(main())
