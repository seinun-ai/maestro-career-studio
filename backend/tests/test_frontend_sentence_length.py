"""Sentence-length ratchet: no sentence a user reads runs past 25 words.

docs/frontend-conventions.md, Microcopy rules, *Sentence length*. The cap is
borrowed from ASD-STE100 Simplified Technical English (20 words for an
instruction, 25 for a description); the looser one applies, since UI copy
mixes both. It reads exactly what the vocabulary ratchet reads (`ui_strings`):
the web app, the Companion panel and the Companion manifest.

A string is cut into sentences at `.`, `!` or `?` followed by a space. JSX
text is read in the chunks between `{…}` expressions, so a sentence with an
interpolation is counted in pieces: the cap catches the long run-ons, not
every long sentence.

`_ALLOWED` takes a deliberate exception as (file, opening words), with its
reason. A row that no longer matches fails `test_allowlist_is_current`, so the
list only shrinks.
"""

from __future__ import annotations

import re

from tests.test_frontend_vocabulary import ui_strings

_CAP = 25
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z0-9][\w'’&;.-]*")
# A Tailwind class list kept in a constant (`POPUP_SURFACE`): tokens like
# `min-w-32`, `data-open:fade-in-0`, `ring-foreground/10`. Prose has few.
_CLASS_TOKEN = re.compile(r"[-:\[/]")

# (file, the sentence's opening words): a deliberate exception, with its reason. Empty today.
_ALLOWED: frozenset[tuple[str, str]] = frozenset()


def _is_class_list(text: str) -> bool:
    tokens = text.split()
    return len(tokens) > 1 and sum(bool(_CLASS_TOKEN.search(t)) for t in tokens) * 2 > len(tokens)


def _words(sentence: str) -> int:
    return len(_WORD.findall(sentence))


def long_sentences() -> list[tuple[str, int, int, str]]:
    """(file, line, word count, sentence) for every sentence over the cap."""
    return [
        (rel, line, _words(sentence), sentence)
        for rel, line, text in ui_strings()
        if not _is_class_list(text)
        for sentence in _SENTENCE_END.split(text)
        if _words(sentence) > _CAP
    ]


def _allowed(rel: str, sentence: str) -> tuple[str, str] | None:
    return next((row for row in _ALLOWED if row[0] == rel and sentence.startswith(row[1])), None)


def test_no_sentence_runs_past_the_cap():
    bad = [hit for hit in long_sentences() if not _allowed(hit[0], hit[3])]
    assert not bad, f"sentences over {_CAP} words (split them, or cut a clause):\n" + "\n".join(
        f"{rel}:{line}: {n} words: {sentence!r}" for rel, line, n, sentence in bad
    )


def test_allowlist_is_current():
    live = {_allowed(rel, sentence) for rel, _l, _n, sentence in long_sentences()}
    stale = sorted(f"{rel} :: {opening}" for rel, opening in _ALLOWED - live)
    assert not stale, stale


def test_the_counter_reads_words_not_marks():
    assert _words("Couldn't load your jobs. Check that it's running.") == 8
    assert _words("Whether you&apos;d relocate — or not") == 5
    assert _SENTENCE_END.split("One. Two? Three!") == ["One.", "Two?", "Three!"]


def test_a_class_list_is_not_prose():
    assert _is_class_list("z-50 max-h-(--available-height) min-w-32 data-open:fade-in-0 ring-foreground/10")
    assert not _is_class_list("Check every form before you submit it. You can turn this off.")
