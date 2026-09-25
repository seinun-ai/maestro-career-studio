"""The health check's word bank: clichés and filler words matched in CODE.

The model never decides what counts as a cliché: the same words always flag,
and the user owns the list (`GET/PUT /api/resume-lint/wording`, plus reset).
Storage is two `Setting` rows holding JSON:

- `health.word_bank` — `{"cliche": [...], "filler": [...]}`. ABSENT until the
  first edit, and absent means the built-in defaults (reset deletes it).
- `health.ignored_words` — the "Never flag" list, lower-cased. It silences a
  bank word AND a classifier slip whose span matches it.

Matching and the Remove / Apply text edits are pure; `resume_lint` turns them
into zero-score `language.*` notes and gates each edited text through
`health_guards` before offering it as a suggestion.
"""
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.setting import Setting

BANK_KEY = "health.word_bank"
IGNORED_KEY = "health.ignored_words"
MAX_ENTRIES = 200
MAX_CHARS = 40

# Sources (docs/health-check-rubric.md, "Word bank"): CareerBuilder/Harris 2014
# "worst resume terms" and the VMock filler list via Boston University.
DEFAULT_CLICHE = (
    "results-driven", "results-oriented", "team player", "go-getter",
    "think outside the box", "synergy", "best of breed", "go-to person",
    "thought leadership", "value add", "detail-oriented", "self-motivated",
    "hard worker", "strategic thinker", "dynamic", "proactive", "track record",
    "self-starter",
)
DEFAULT_FILLER = (
    "successfully", "effectively", "efficiently", "various", "several", "very",
    "really", "basically", "actually",
)


@dataclass(frozen=True)
class WordBank:
    cliche: tuple[str, ...]
    filler: tuple[str, ...]
    ignored: tuple[str, ...] = ()

    def payload(self) -> dict:
        """The `/wording` response shape."""
        return {
            "cliche": list(self.cliche), "filler": list(self.filler),
            "ignored": list(self.ignored),
            "defaults": {"cliche": list(DEFAULT_CLICHE), "filler": list(DEFAULT_FILLER)},
        }


DEFAULT_BANK = WordBank(cliche=DEFAULT_CLICHE, filler=DEFAULT_FILLER)


# --------------------------------------------------------------------------- #
# normalization + storage

def _key(word: str) -> str:
    """The comparison form `normalize` stores: inner whitespace collapsed, lower-cased."""
    return " ".join(str(word).split()).lower()


def normalize(words: Iterable[str]) -> list[str]:
    """Trim, collapse inner whitespace, lower-case, dedupe (first wins).

    Raises ValueError for an entry outside 1–MAX_CHARS characters, or more
    than MAX_ENTRIES entries once deduped."""
    out: list[str] = []
    for word in words:
        norm = _key(word)
        if not 1 <= len(norm) <= MAX_CHARS:
            raise ValueError(f"Each word or phrase must be 1 to {MAX_CHARS} characters.")
        if norm not in out:
            out.append(norm)
    if len(out) > MAX_ENTRIES:
        raise ValueError(f"A list can hold at most {MAX_ENTRIES} words.")
    return out


def _read(db: Session, key: str):
    row = db.get(Setting, key)
    if row is None or not row.value:
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return None


def _stored_list(value) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    try:
        return tuple(normalize(value))
    except ValueError:
        return None


def load(db: Session) -> WordBank:
    """The user's bank; any missing or unreadable part reads as its default."""
    bank = _read(db, BANK_KEY)
    cliche = filler = None
    if isinstance(bank, dict):
        cliche, filler = _stored_list(bank.get("cliche")), _stored_list(bank.get("filler"))
    if cliche is None or filler is None:
        cliche, filler = DEFAULT_CLICHE, DEFAULT_FILLER
    ignored = _stored_list(_read(db, IGNORED_KEY)) or ()
    return WordBank(cliche=cliche, filler=filler, ignored=ignored)


def _write(db: Session, values: dict[str, object]) -> None:
    """Upsert Setting rows and commit. Two first edits can both read "absent" and
    both INSERT; the loser's IntegrityError is rolled back and retried once, when
    the rows exist and the write is an update."""
    for attempt in range(2):
        for key, value in values.items():
            payload = json.dumps(value)
            row = db.get(Setting, key)
            if row is None:
                db.add(Setting(key=key, value=payload))
            else:
                row.value = payload
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            if attempt:
                raise


def save(db: Session, *, cliche: Iterable[str], filler: Iterable[str],
         ignored: Iterable[str]) -> WordBank:
    bank = WordBank(cliche=tuple(normalize(cliche)), filler=tuple(normalize(filler)),
                    ignored=tuple(normalize(ignored)))
    _write(db, {BANK_KEY: {"cliche": list(bank.cliche), "filler": list(bank.filler)},
                IGNORED_KEY: list(bank.ignored)})
    return bank


def reset(db: Session) -> WordBank:
    """Back to the default clichés and filler; the Never flag list is kept."""
    row = db.get(Setting, BANK_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    return load(db)


# --------------------------------------------------------------------------- #
# matching + text edits (pure)

def _pattern(phrase: str) -> re.Pattern:
    body = r"\s+".join(re.escape(part) for part in phrase.split())
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


def is_ignored(word: str, bank: WordBank) -> bool:
    return _key(word) in {_key(w) for w in bank.ignored}


def matches(text: str, bank: WordBank) -> list[tuple[str, str]]:
    """(kind, word) for each bank word in `text`, once each, in bank order;
    a word on the Never flag list is skipped."""
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, words in (("cliche", bank.cliche), ("filler", bank.filler)):
        for word in words:
            if word in seen or is_ignored(word, bank) or not _pattern(word).search(text):
                continue
            seen.add(word)
            hits.append((kind, word))
    return hits


_SENTENCE_END = ".!?"
_JOINING = ",;:"
_DASHES = "-–—"
_BRACKETS = {"(": ")", "[": "]"}
_QUOTES = "'\"‘’“”"
_EDGE_PUNCT = _SENTENCE_END + _JOINING + _QUOTES + "()[]"

# One-click Remove is for FILLER words only (clichés are nouns and adjectives
# the sentence needs; they are rewritten by hand). A filler cut is copy-only
# when the word before it makes the filler part of the claim ("did not really
# own"), sits after a linking verb or "of", or is an article (no a/an guessing);
# or when a non -ly filler is followed by a function word or relative pronoun
# ("several of the").
_BLOCK_PREV = frozenset({"not", "is", "was", "are", "were", "be", "been", "being", "as",
                         "of", "a", "an"})
_BLOCK_NEXT = frozenset({"of", "to", "for", "in", "on", "at", "by", "with", "across",
                         "from", "about", "who", "that", "which"})

# The seam check: "the of", "the." or a sentence-final "the"; an and/or left
# with nothing to join; a sentence opening And/Or; empty quotes.
_THE_END = re.compile(r"\bthe$", re.IGNORECASE)
_FUNCTION_OR_PUNCT = re.compile(
    r"(?:of|for|with|in|on|to|at|and|or|by|as)\b|[.,;:)]|$", re.IGNORECASE)
_CONJ_END = re.compile(r"\b(?:and|or)$", re.IGNORECASE)
_CONJ_START = re.compile(r"(?:and|or)\b", re.IGNORECASE)


def _edge_word(text: str, index: int) -> str:
    words = text.split()
    return words[index].strip(_EDGE_PUNCT).lower() if words else ""


def _filler_ok(before: str, after: str, word: str) -> bool:
    if _edge_word(before, -1) in _BLOCK_PREV:
        return False
    return word.lower().endswith("ly") or _edge_word(after, 0) not in _BLOCK_NEXT


def _unwrap(before: str, after: str) -> tuple[str, str]:
    """Drop what the cut word leaves empty: brackets, a slash, a doubled dash."""
    while before and after and _BRACKETS.get(before[-1]) == after[0]:
        before, after = before[:-1].rstrip(), after[1:].lstrip()
    if after.startswith("/"):  # "very/really" -> "really"
        after = after[1:].lstrip()
    elif before.endswith("/"):
        before = before[:-1].rstrip()
    if before and before[-1] in _DASHES and (not after or after[0] in _DASHES):
        before = before[:-1].rstrip()  # "it - word - on" -> "it - on"
    return before, after


def _commas(before: str, after: str, word: str) -> tuple[str, str]:
    """The comma BEFORE a filler word always stays ("fast, very cheap"). An -ly
    word keeps the comma after it ("effectively, which" -> ", which") unless it
    was parenthetical (", successfully," drops both); any other word takes the
    comma after it along (", various," leaves one)."""
    if not after.startswith(","):
        return before, after
    ly = word.lower().endswith("ly")
    if before.endswith(","):
        return (before[:-1].rstrip() if ly else before), after[1:].lstrip()
    return before, (after if ly else after[1:].lstrip())


def _seam_ok(before: str, after: str) -> bool:
    if _THE_END.search(before) and _FUNCTION_OR_PUNCT.match(after):
        return False
    if _CONJ_START.match(after) or (_CONJ_END.search(before) and _FUNCTION_OR_PUNCT.match(after)):
        return False
    return not (before[-1:] and before[-1] in _QUOTES and after[:1] and after[0] in _QUOTES)


def _glue(before: str, after: str, sep: str) -> str:
    if not before or not after:
        return before or after
    return before + after if before[-1] in "([/" else f"{before}{sep}{after}"


def _open_line(before: str, after: str, capital: bool, sep: str) -> tuple[str, bool]:
    """The cut word opened a sentence or a line: no leading comma or dash, keep
    its capital; the line before it loses a trailing comma."""
    before = before.rstrip(_JOINING + _DASHES + " ")
    after = after.lstrip(_JOINING + _DASHES + " ")
    if capital:
        after = after[:1].upper() + after[1:]
    return _glue(before, after, sep), _seam_ok(before, "") and _seam_ok("", after)


def _cut(text: str, start: int, end: int) -> tuple[str, bool]:
    """`text` without [start, end) with the seam cleaned up, and whether the
    result reads cleanly there (`_filler_ok`, `_seam_ok`)."""
    raw_before, word, raw_after = text[:start], text[start:end], text[end:]
    before, after = _unwrap(raw_before.rstrip(), raw_after.lstrip())
    ok = _filler_ok(before, after, word)
    gap = raw_before[len(raw_before.rstrip()):] + raw_after[:len(raw_after) - len(raw_after.lstrip())]
    sep = "\n" if "\n" in gap else " "
    if not before or before[-1] in _SENTENCE_END or sep == "\n":
        out, seam = _open_line(before, after, word[:1].isupper(), sep)
        return out, ok and seam
    before, after = _commas(before, after, word)
    if not after:
        before = before.rstrip(_JOINING + _DASHES + " ")
        return before, ok and _seam_ok(before, "")
    if after[0] in _JOINING + _SENTENCE_END + ")":
        if before[-1] in _JOINING:
            before = before[:-1].rstrip()
        return before + after, ok and _seam_ok(before, after)  # no space before punctuation
    return _glue(before, after, sep), ok and _seam_ok(before, after)


def removal(text: str, filler: str) -> str | None:
    """`text` with every whole-word occurrence of the FILLER word cut, or None
    when any cut reads broken or risky (`_filler_ok`, `_seam_ok`): the rewrite
    guards check facts, not grammar, so this is the grammar safety net.
    Clichés never come here (`resume_lint._wording_notes`)."""
    pattern = _pattern(filler)
    clean, cut = True, False
    while (m := pattern.search(text)) is not None:  # each cut shortens the text
        text, ok = _cut(text, m.start(), m.end())
        clean, cut = clean and ok, True
    if not clean:
        return None
    return re.sub(r"[ \t]{2,}", " ", text) if cut else text


def _span_pattern(span: str) -> re.Pattern:
    r"""A slip span, verbatim and case-sensitive, with the matcher's `[\w-]`
    boundaries on whichever ends are word characters (so "in" never hits
    "in-house", and ", and" can still follow a word)."""
    edge = re.compile(r"[\w-]")
    lead = r"(?<![\w-])" if edge.match(span[:1]) else ""
    tail = r"(?![\w-])" if edge.match(span[-1:]) else ""
    return re.compile(f"{lead}{re.escape(span)}{tail}")


def span_count(text: str, span: str) -> int:
    return len(_span_pattern(span).findall(text)) if span else 0


def apply_fix(text: str, span: str, fix: str) -> str | None:
    """`text` with the slip `span` replaced by `fix`, or None unless the span
    occurs exactly once: a short span ("a") repeated elsewhere would be fixed
    where it was never wrong."""
    if span_count(text, span) != 1:
        return None
    return _span_pattern(span).sub(lambda _m: fix, text, count=1)
